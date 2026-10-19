"""Fake-only live-provider/admission tests; no key or public API read."""
import json,hashlib,threading,time
from concurrent.futures import ThreadPoolExecutor
import pytest
from paper_compiler import evidence as e

PROVIDERS=['crossref','datacite','openalex','europepmc']
URL='https://api.crossref.org/works?query=TEST_ONLY'

def gateway(tmp_path,monkeypatch):
    monkeypatch.setenv('PAPER_COMPILER_LIVE_EVIDENCE_PROVIDERS','openalex')
    return e.EvidenceGateway(tmp_path,transport=lambda u:pytest.fail('network on cache-only provider'),snapshot_id='TEST_ONLY')

def test_cache_only_miss_is_unavailable_without_network_or_cache_pollution(tmp_path,monkeypatch):
    g=gateway(tmp_path,monkeypatch);value=g._retrieve('crossref',URL)
    assert g.providers==PROVIDERS and g.live_providers==['openalex']
    assert value['status']=='unavailable' and value['request_sent'] is False
    assert value['id'] and value['deferred_reason']=='provider_cache_only'
    assert not list(g.cache_dir.glob('*.json'))

def test_cache_only_provider_keeps_exact_existing_snapshot_response(tmp_path,monkeypatch):
    g=gateway(tmp_path,monkeypatch);record={'id':'TEST_ONLY-cached','status':'ok','retrieved_at':0,'works':[{'title':'TEST_ONLY'}]}
    key=hashlib.sha256((e.VERSION+'\n'+URL).encode()).hexdigest();(g.cache_dir/(key+'.json')).write_text(json.dumps(record))
    assert g._retrieve('crossref',URL)==record

def test_public_policy_pins_nondefault_live_set_and_preserves_default(monkeypatch):
    from paper_compiler.program_analysis import analysis_execution_policy
    monkeypatch.delenv('PAPER_COMPILER_LIVE_EVIDENCE_PROVIDERS',raising=False)
    old=analysis_execution_policy();assert 'live_providers' not in old
    monkeypatch.setenv('PAPER_COMPILER_LIVE_EVIDENCE_PROVIDERS','openalex')
    new=analysis_execution_policy();assert new.pop('live_providers')==['openalex'];assert new==old
    monkeypatch.setenv('PAPER_COMPILER_LIVE_EVIDENCE_PROVIDERS','unknown')
    with pytest.raises(ValueError):analysis_execution_policy()

def test_builtin_analysis_cache_policy_binds_live_scope(tmp_path,monkeypatch):
    from test_paper_compiler_compiler import fixture
    from paper_compiler.analysis import enrich
    ir,_=fixture(tmp_path);g=gateway(tmp_path/'evidence',monkeypatch)
    value=enrich(ir,[],client=None,gateway=g,cache_dir=tmp_path/'analysis')
    assert value['policy']['live_providers']==['openalex']

def auth_gateway(tmp_path,transport):
    g=e.EvidenceGateway(tmp_path,transport=transport);g.rate_limit=True;g.openalex_rate_scope='-authenticated-TEST_ONLY'
    return g

def test_authenticated_openalex_overlaps_but_caps_four_inflight_and_five_starts(tmp_path,monkeypatch):
    monkeypatch.delenv('PAPER_COMPILER_LIVE_EVIDENCE_PROVIDERS',raising=False)
    lock=threading.Lock();starts=[];active=0;peak=0
    def transport(url):
        nonlocal active,peak
        with lock:starts.append(time.monotonic());active+=1;peak=max(peak,active)
        time.sleep(.85)
        with lock:active-=1
        return e.HTTPResponse(200,b'{}')
    g=auth_gateway(tmp_path,transport)
    with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(lambda i:g._fetch('openalex','https://api.openalex.org/works/TEST_ONLY'+str(i)),range(8)))
    assert 2<=peak<=4
    assert min(b-a for a,b in zip(sorted(starts),sorted(starts)[1:]))>=.18

def test_parallel_success_does_not_erase_openalex_429_cooldown(tmp_path,monkeypatch):
    monkeypatch.delenv('PAPER_COMPILER_LIVE_EVIDENCE_PROVIDERS',raising=False)
    lock=threading.Lock();calls=[]
    def transport(url):
        with lock:index=len(calls);calls.append(url)
        time.sleep(.35 if index==0 else .5)
        return e.HTTPResponse(429,b'',{'Retry-After':'120'}) if index==0 else e.HTTPResponse(200,b'{}')
    g=auth_gateway(tmp_path,transport)
    with ThreadPoolExecutor(max_workers=2) as pool:values=list(pool.map(lambda i:g._fetch('openalex','https://api.openalex.org/works/TEST_ONLY'+str(i)),range(2)))
    assert len(calls)==2 and sorted(v[0] for v in values)==[200,429]
    deferred=g._fetch('openalex','https://api.openalex.org/works/TEST_ONLY-next')
    assert deferred[0]==429 and deferred.request_sent is False and len(calls)==2
    state=json.loads((tmp_path/'openalex-authenticated-TEST_ONLY-rate-state.json').read_text())
    assert state['cooldown_until']>time.time()+110
