"""Exact source URL discovery adds evidence; it does not bypass identity guards."""
from copy import deepcopy
import json
from paper_compiler.evidence import EvidenceGateway
from paper_compiler.identity import resolve_identity

DOI = '10.48550/arxiv.1807.01234'
URL = 'https://arxiv.org/abs/1807.01234'
EXACT = 'https://api.datacite.org/dois/10.48550%2Farxiv.1807.01234'
ENTRY = {'title':'A General Research Study','authors':['Jane Smith'],'year':2018,'url':URL}


def response(year=2018, doi=DOI, authors=None):
    return json.dumps({'data': {'attributes': {'doi':doi,'url':URL,
        'titles':[{'title':ENTRY['title']}], 'creators':[{'name':n} for n in (authors or ['Jane Smith'])],
        'publicationYear':year,'types':{'resourceTypeGeneral':'Preprint'}}}}).encode()


def test_exact_source_arxiv_lookup_is_one_datacite_singleton_with_existing_cache(tmp_path):
    calls = []
    def transport(url):
        calls.append(url)
        assert url == EXACT
        return 200, response()
    gateway = EvidenceGateway(tmp_path,transport=transport,live_providers=['openalex'],snapshot_id='fake-exact')
    records = gateway.lookup_arxiv_url(URL)
    assert calls == [EXACT] and records[0]['provider'] == 'datacite'
    result = resolve_identity(deepcopy(ENTRY),records)
    assert result['state'] == 'observed' and result['work']['doi'] == DOI
    assert gateway.lookup_arxiv_url(URL) == records and calls == [EXACT]
    for bad in ['https://arxiv.org.evil.example/abs/1807.01234', 'https://[invalid']:
        assert gateway.lookup_arxiv_url(bad) == []
    assert calls == [EXACT]


def test_exact_metadata_cannot_bypass_year_author_identifier_or_provider_scope(tmp_path):
    for label, body in [('year',response(year=2025)),('authors',response(authors=['Other Author'])),
                        ('identifier',response(doi='10.48550/arxiv.1807.99999'))]:
        calls = []
        def transport(url):
            calls.append(url)
            assert url == EXACT
            return 200, body
        gateway = EvidenceGateway(tmp_path/label,transport=transport,live_providers=['openalex'])
        records = gateway.lookup_arxiv_url(URL)
        assert calls == [EXACT] and resolve_identity(deepcopy(ENTRY),records)['state'] == 'unknown'
    def forbidden(url): raise AssertionError('no provider scope escape')
    gateway = EvidenceGateway(tmp_path/'scoped',providers=['openalex'],transport=forbidden,live_providers=['openalex'])
    assert gateway.lookup_arxiv_url(URL) == []
