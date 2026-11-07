"""Real gateway and identity matching with deterministic HTTP fixtures."""
import json
from urllib.parse import urlsplit
import pytest
from paper_compiler.evidence import EvidenceGateway, _http
from paper_compiler.identity import resolve_identity

QUERY = {'title': 'Tree Models for Lakes', 'authors': ['John Smith'], 'year': 2020, 'doi': '10.1000/tree'}

def body(provider, title=QUERY['title'], author='John Smith'):
    if provider == 'openalex':
        return {'id': 'https://openalex.org/W123', 'display_name': title, 'publication_year': 2020,
                'doi': 'https://doi.org/10.1000/tree', 'authorships': [{'author': {'display_name': author}}]}
    return {'message': {'items': [{'title': [title], 'DOI': '10.1000/tree',
             'issued': {'date-parts': [[2020]]}, 'author': [{'given': author.split()[0], 'family': author.split()[-1]}]}]}}

def test_openalex_exact_identity_avoids_unnecessary_search_and_serpapi(tmp_path, monkeypatch):
    monkeypatch.delenv('SERPAPI_API_KEY', raising=False)
    calls = []
    def transport(url):
        calls.append(url)
        return 200, json.dumps(body('openalex')).encode()
    gateway = EvidenceGateway(tmp_path, providers=['openalex', 'crossref'], transport=transport)
    records = gateway.lookup_public_reference(QUERY)
    assert resolve_identity(QUERY, records)['value'] is True
    assert len(calls) == 1 and urlsplit(calls[0]).path.startswith('/works/https:')

def test_openalex_failure_falls_back_to_crossref_and_reuses_positive_cache(tmp_path):
    calls = []
    def transport(url):
        calls.append(url)
        if urlsplit(url).hostname == 'api.openalex.org': return 429, b'{}'
        return 200, json.dumps(body('crossref')).encode()
    gateway = EvidenceGateway(tmp_path, providers=['openalex', 'crossref'], transport=transport)
    records = gateway.lookup_public_reference(QUERY)
    assert resolve_identity(QUERY, records)['value'] is True
    count = len(calls)
    assert gateway.lookup_public_reference(QUERY) == records and len(calls) == count

@pytest.mark.parametrize('status', [200, 429, 503])
def test_empty_or_failed_sources_never_prove_nonexistence(tmp_path, status):
    gateway = EvidenceGateway(tmp_path, providers=['crossref'], transport=lambda url: (status, b'{"message":{"items":[]}}'))
    result = resolve_identity(QUERY, gateway.lookup_public_reference(QUERY))
    assert result['state'] == 'unknown' and result.get('value') is not False

def test_existing_doi_for_a_different_work_is_not_a_success(tmp_path):
    gateway = EvidenceGateway(tmp_path, providers=['openalex'], transport=lambda url: (200, json.dumps(body('openalex', title='A Different Article', author='Jane Jones')).encode()))
    assert resolve_identity(QUERY, gateway.lookup_public_reference(QUERY))['state'] == 'unknown'

def test_unregistered_doi_still_allows_title_author_year_verification(tmp_path):
    calls=[]
    def transport(url):
        calls.append(url)
        if urlsplit(url).query:return 200,json.dumps(body('crossref')).encode()
        return 404,b'{}'
    gateway=EvidenceGateway(tmp_path,providers=['crossref'],transport=transport)
    assert resolve_identity(QUERY,gateway.lookup_public_reference(QUERY))['value'] is True
    assert len(calls)==2

def test_chinese_identity_requires_author_and_year_support(tmp_path):
    query = {**QUERY, 'title': '中文参考文献身份核验研究', 'authors': ['张三']}
    value = body('openalex', title=query['title'], author='张三')
    gateway = EvidenceGateway(tmp_path, providers=['openalex'], transport=lambda url: (200, json.dumps(value).encode()))
    assert resolve_identity(query, gateway.lookup_public_reference(query))['value'] is True

def test_reference_cache_retries_service_failure_after_short_ttl(tmp_path):
    now = [1000.0]; calls = []
    def transport(url):
        calls.append(url)
        return (503, b'{}') if now[0] == 1000 else (200, json.dumps(body('openalex')).encode())
    gateway = EvidenceGateway(tmp_path, providers=['openalex'], transport=transport, clock=lambda: now[0])
    assert resolve_identity(QUERY, gateway.lookup_public_reference(QUERY))['state'] == 'unknown'
    now[0] += 601
    assert resolve_identity(QUERY, gateway.lookup_public_reference(QUERY))['value'] is True

def test_frozen_reference_failure_remains_reproducible(tmp_path):
    now = [1000.0]
    gateway = EvidenceGateway(tmp_path, providers=['crossref'], snapshot_id='frozen',
        transport=lambda url: (503, b'{}'), clock=lambda: now[0])
    old = gateway.lookup_public_reference(QUERY)
    now[0] += 601
    gateway.transport = lambda url: pytest.fail('frozen evidence must not refresh')
    assert gateway.lookup_public_reference(QUERY) == old

def test_frozen_reference_failure_does_not_change_when_sources_are_enabled(tmp_path):
    old=EvidenceGateway(tmp_path,providers=['openalex','crossref'],live_providers=['crossref'],
        snapshot_id='frozen',transport=lambda url:(503,b'{}')).lookup_public_reference(QUERY)
    new=EvidenceGateway(tmp_path,providers=['openalex','crossref'],snapshot_id='frozen',
        transport=lambda url:pytest.fail('a frozen query cannot gain new sources')).lookup_public_reference(QUERY)
    assert new==old

def test_a_different_arxiv_version_cannot_verify_an_explicit_cited_version():
    from paper_compiler.identity import resolve_reference_identity
    query={**QUERY,'doi':None,'url':'https://arxiv.org/abs/2001.00001v99'}
    rows=[{'id':'other-version','provider':'openalex','status':'ok','work':{
        **QUERY,'url':'https://arxiv.org/abs/2001.00001v1','doi':'10.48550/arxiv.2001.00001'}}]
    assert resolve_reference_identity(query,rows)['state']=='unknown'

def test_exact_short_chinese_title_and_doi_can_be_verified_without_loosening_author_conflicts():
    from paper_compiler.identity import resolve_reference_identity
    query={**QUERY,'title':'数据库系统研究','authors':['张三']}
    row={'id':'source','provider':'crossref','status':'ok','work':dict(query)}
    assert resolve_reference_identity(query,[row])['value'] is True
    row['work']['authors']=['李四']
    assert resolve_reference_identity(query,[row])['state']=='unknown'

def test_unreadable_openalex_config_cannot_abort_other_sources(tmp_path,monkeypatch):
    from paper_compiler import evidence
    def bad_keys(*args):raise evidence.EvidenceError('OpenAlex credential configuration is unreadable')
    monkeypatch.setattr(evidence,'_openalex_keys',bad_keys)
    gateway=EvidenceGateway(tmp_path,providers=['openalex','crossref'])
    gateway.transport=lambda url:(200,json.dumps(body('crossref')).encode())
    gateway.rate_limit=False
    assert resolve_identity(QUERY,gateway.lookup_public_reference(QUERY))['value'] is True

def test_multiple_private_keys_are_host_scoped_and_never_serialized(tmp_path, monkeypatch):
    from paper_compiler import evidence
    keys = ['test-key-one', 'test-key-two', 'test-key-three']
    monkeypatch.setenv('OPENALEX_API_KEYS', ','.join(keys))
    monkeypatch.delenv('OPENALEX_API_KEY', raising=False)
    seen = []
    class Reply:
        status = 200; headers = {}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size): return json.dumps({'echo': keys}).encode()
    class Opener:
        def open(self, request, timeout): seen.append(request); return Reply()
    monkeypatch.setattr(evidence, 'build_opener', lambda *args: Opener())
    for n in range(30):
        response = _http('https://api.openalex.org/works/W'+str(n))
        assert not any(key.encode() in response[1] for key in keys)
    assert {r.get_header('Authorization') for r in seen} == {'Bearer '+k for k in keys}
    seen.clear()
    _http('https://api.crossref.org/works/10.1000/tree')
    assert seen[0].get_header('Authorization') is None

def test_unresolved_analysis_can_be_retried_without_changing_historical_evidence(tmp_path):
    from test_paper_compiler_fixed_r32 import checked
    class Gateway:
        providers = ['crossref']; snapshot_id = None
        def __init__(self): self.available = False; self.calls = 0
        def lookup_rule32(self, query):
            self.calls += 1
            return [{'id': 'real-source', 'provider': 'crossref', 'status': 'ok', 'work': {
                'title': 'Tree Models for Lakes', 'authors': ['John Smith'], 'year': 2020, 'doi': '10.1000/correct'}}] if self.available else []
    gateway = Gateway()
    first = checked(tmp_path, gateway=gateway)[3]
    assert first['status'] == 'UNKNOWN'
    gateway.available = True
    assert checked(tmp_path, gateway=gateway)[3]['status'] == 'PASS'
    assert first['status'] == 'UNKNOWN' and gateway.calls == 2
