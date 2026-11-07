import threading
import time
from urllib.parse import parse_qs,urlsplit

from paper_compiler.evidence import EvidenceGateway
from paper_compiler import analysis


def atom(identifiers):
    return ('<feed xmlns="http://www.w3.org/2005/Atom">'+''.join(
        '<entry><id>https://arxiv.org/abs/'+value+'</id><title>Verified scholarly title '+value+'</title>'
        '<published>2020-01-01T00:00:00Z</published><author><name>John Smith</name></author></entry>'
        for value in identifiers)+'</feed>').encode()


def test_bulk_arxiv_warms_individual_metadata_cache_with_two_requests_for_forty_ids(tmp_path):
    calls=[]
    def transport(url):
        calls.append(url)
        values=parse_qs(urlsplit(url).query)
        ids=values['id_list'][0].split(',')
        assert len(ids)<=20 and int(values.get('max_results',[1])[0])>=len(ids)
        return 200,atom([value+'v1' for value in reversed(ids)])
    gateway=EvidenceGateway(tmp_path,transport=transport)
    ids=['2001.'+str(index).zfill(5) for index in range(1,41)]
    queries=[{'url':'https://arxiv.org/abs/'+value} for value in ids+ids[:5]]
    warm=getattr(gateway,'prefetch_rule32',None)
    assert callable(warm),'bulk exact-metadata prefetch is missing'
    warm(queries)
    for value in ids:
        row=gateway.lookup_arxiv_metadata(value)[0]
        assert row['status']=='ok' and row['work']['doi']=='10.48550/arxiv.'+value
    assert len(calls)==2
    warm(queries)
    assert len(calls)==2


def test_bulk_does_not_accept_wrong_versions_or_poison_missing_id_fallback(tmp_path):
    calls=[]
    def transport(url):
        calls.append(url)
        ids=parse_qs(urlsplit(url).query)['id_list'][0].split(',')
        return (200,atom(['2001.00001v1'])) if len(ids)>1 else (200,atom(ids))
    gateway=EvidenceGateway(tmp_path,transport=transport)
    warm=getattr(gateway,'prefetch_rule32',None)
    assert callable(warm),'bulk exact-metadata prefetch is missing'
    warm([{'url':'https://arxiv.org/abs/'+value} for value in ['2001.00001v99','2001.00002']])
    assert gateway.lookup_arxiv_metadata('2001.00001v99')[0]['work']['url'].endswith('v99')
    assert gateway.lookup_arxiv_metadata('2001.00002')[0]['status']=='ok'
    assert len(calls)==3


def test_frozen_arxiv_prefetch_does_not_fetch_or_mutate_snapshot(tmp_path):
    gateway=EvidenceGateway(tmp_path,snapshot_id='original',transport=lambda url:(_ for _ in ()).throw(AssertionError('frozen prefetch must not fetch')))
    warm=getattr(gateway,'prefetch_rule32',None)
    assert callable(warm),'bulk exact-metadata prefetch is missing'
    warm([{'url':'https://arxiv.org/abs/'+value} for value in ['2001.00001','2001.00002']])
    assert not list(gateway.cache_dir.glob('arxiv-identity-*.json'))


def test_successful_reference_cache_skips_bulk_refresh_even_after_metadata_ttl(tmp_path):
    now=[1000.0];calls=[]
    def transport(url):
        calls.append(url)
        return 200,atom([value+'v1' for value in parse_qs(urlsplit(url).query)['id_list'][0].split(',')])
    gateway=EvidenceGateway(tmp_path,transport=transport,clock=lambda:now[0])
    queries=[{'title':'Verified scholarly title '+value+'v1','authors':['John Smith'],'year':2020,
              'doi':'10.48550/arxiv.'+value,'url':'https://arxiv.org/abs/'+value}
             for value in ['2001.00001','2001.00002']]
    for query in queries:gateway.lookup_public_reference(query)
    assert len(calls)==2
    now[0]+=2*86400
    gateway.prefetch_rule32(queries)
    for query in queries:gateway.lookup_public_reference(query)
    assert len(calls)==2


def test_failed_bulk_request_does_not_poison_individual_metadata_lookup(tmp_path):
    calls=[]
    def transport(url):
        calls.append(url)
        ids=parse_qs(urlsplit(url).query)['id_list'][0].split(',')
        return (503,b'') if len(ids)>1 else (200,atom([ids[0]+'v1']))
    gateway=EvidenceGateway(tmp_path,transport=transport)
    gateway.prefetch_rule32([{'url':'https://arxiv.org/abs/'+value} for value in ['2001.00001','2001.00002']])
    assert gateway.lookup_arxiv_metadata('2001.00001')[0]['status']=='ok'
    assert len(calls)==2


def test_parallel_reference_queries_are_deduplicated_bounded_and_isolate_failures():
    lock=threading.Lock();active=0;peak=0;calls=[]
    class Gateway:
        def lookup_rule32(self,query):
            nonlocal active,peak
            with lock:active+=1;peak=max(peak,active);calls.append(query['title'])
            try:
                time.sleep(.02)
                if query['title']=='Reference 3':raise OSError('temporary failure')
                return [{'id':query['title']}]
            finally:
                with lock:active-=1
    nodes=[{'id':str(index)} for index in range(24)]
    fields={node['id']:{'title':{'state':'observed','value':'Reference '+str(index%12)}} for index,node in enumerate(nodes)}
    prefetch=getattr(analysis,'_prefetch_rule32',None)
    assert callable(prefetch),'deduplicated bounded reference prefetch is missing'
    results=prefetch(nodes,fields,Gateway())
    assert len(calls)==12 and 1<peak<=8
    assert len(results)==24 and results['0']==results['12']
    assert results['3']==([], 'OSError') and results['4'][0]
