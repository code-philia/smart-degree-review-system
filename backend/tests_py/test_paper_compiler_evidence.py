import copy
import json
from urllib.error import HTTPError, URLError
import pytest
from paper_compiler.evidence import EvidenceGateway, EvidenceError, validate_url
from paper_compiler.identity import resolve_identity


def crossref(title='Attention Is All You Need',doi='10.5555/3295222.3295349'):
    return {'message':{'items':[{'DOI':doi,'title':[title], 'author':[{'family':'Vaswani','given':'Ashish'}],
        'issued':{'date-parts':[[2017]]},'abstract':'<jats:p>A model based on attention mechanisms.</jats:p>'}]}}


def transport(data):
    calls=[]
    def request(url):calls.append(url);return 200,json.dumps(data).encode()
    return calls,request


def record(title='Attention Is All You Need',doi='10.5555/3295222.3295349',year=2017,authors=None):
    return {'id':'e1','provider':'crossref','status':'ok','source_group':'doi-registration',
        'work':{'title':title,'doi':doi,'year':year,'authors':authors or ['Ashish Vaswani'],'abstract':''}}


def test_metadata_normalization_and_cache_provenance(tmp_path):
    calls,http=transport(crossref())
    gateway=EvidenceGateway(tmp_path,providers=['crossref'],transport=http)
    records=gateway.lookup({'title':'Attention Is All You Need'})
    assert records[0]['work']['title']=='Attention Is All You Need'
    assert records[0]['work']['year']==2017
    assert '<' not in records[0]['work']['abstract']
    assert records[0]['retrieved_at'] and records[0]['response_sha256'] and records[0]['url'].startswith('https://api.crossref.org/')
    assert gateway.lookup({'title':'Attention Is All You Need'})==records
    assert len(calls)==1


@pytest.mark.parametrize('status',[404,429,500])
def test_http_failures_are_evidence_gaps_not_nonexistence(tmp_path,status):
    gateway=EvidenceGateway(tmp_path,providers=['crossref'],transport=lambda url:(status,b'{}'))
    records=gateway.lookup({'title':'An article'})
    assert records[0]['status']=='unavailable'
    assert resolve_identity({'title':'An article'},records)['state']=='unknown'


def test_timeout_and_malformed_body_are_retained(tmp_path):
    def timeout(url):raise TimeoutError()
    records=EvidenceGateway(tmp_path/'one',providers=['crossref'],transport=timeout).lookup({'title':'An article'})
    assert records[0]['error']=='TimeoutError'
    records=EvidenceGateway(tmp_path/'two',providers=['crossref'],transport=lambda u:(200,b'not json')).lookup({'title':'An article'})
    assert records[0]['status']=='unavailable'


def test_empty_search_does_not_prove_nonexistence(tmp_path):
    _,http=transport({'message':{'items':[]}})
    records=EvidenceGateway(tmp_path,providers=['crossref'],transport=http).lookup({'title':'Missing article'})
    assert records[0]['status']=='empty'
    assert resolve_identity({'title':'Missing article'},records)['state']=='unknown'


@pytest.mark.parametrize('url',['http://127.0.0.1/admin','https://localhost/', 'https://api.crossref.org@127.0.0.1/',
    'https://api.crossref.org.evil.test/','file:///etc/passwd','https://api.crossref.org:443/','https://api.crossref.org/works#secret'])
def test_private_or_unapproved_urls_rejected(url):
    with pytest.raises(EvidenceError):validate_url(url)


def test_oversize_response_and_redirect_are_not_followed(tmp_path):
    records=EvidenceGateway(tmp_path,providers=['crossref'],transport=lambda u:(302,b'{}')).lookup({'title':'An article'})
    assert records[0]['status']=='unavailable'
    records=EvidenceGateway(tmp_path/'large',providers=['crossref'],transport=lambda u:(200,b' '* (4*1024*1024+1))).lookup({'title':'An article'})
    assert records[0]['status']=='unavailable'


def test_wrong_doi_does_not_hide_real_alternate_work():
    entry={'title':'Attention Is All You Need','year':2017,'authors':['Vaswani'],'doi':'10.1234/wrong'}
    wrong=record('Other paper','10.1234/wrong',2001,['Other']);wrong['id']='e0'
    result=resolve_identity(entry,[wrong,record()])
    assert result['state']=='observed' and result['value'] is True
    assert result['work']['doi']=='10.5555/3295222.3295349'
    assert result['metadata_conflicts']==['doi']


def test_identifier_alone_with_conflicting_title_cannot_establish_work():
    result=resolve_identity({'title':'Completely different work','doi':'10.5555/3295222.3295349'},[record()])
    assert result['state']=='unknown'


def test_same_title_different_authors_is_not_a_match():
    result=resolve_identity({'title':'Attention Is All You Need','year':2017,'authors':['Alice Smith']},[record()])
    assert result['state']=='unknown'


def test_translation_can_be_resolved_only_with_cited_metadata_support():
    class Model:
        def complete_json(self,*args):return {'same_work':True,'candidate_id':'e1','reason':'translated title and matching author/year','title_relation':'translation','author_supported':True,'year_supported':True}
    result=resolve_identity({'title':'注意力就是你所需要的一切','year':2017,'authors':['Vaswani']},[record()],client=Model())
    assert result['state']=='observed' and result['value'] is True
    result=resolve_identity({'title':'注意力就是你所需要的一切','year':2017,'authors':['Unknown person']},[record()],client=Model())
    assert result['state']=='unknown'


def test_search_records_cannot_declare_negative_identity():
    r=record('Totally different');r['excludes']=True;r['complete']=True
    assert resolve_identity({'title':'Invented title'},[r])['state']=='unknown'


def test_abstract_absence_is_not_relevance_evidence(tmp_path):
    gateway=EvidenceGateway(tmp_path,providers=[],transport=lambda u:None)
    result=gateway.content({'title':'Some work','abstract':''})
    assert result and result[0]['status']=='unavailable'


def test_failure_cache_has_bounded_lifetime(tmp_path):
    times=[100.0];calls=[]
    def http(url):calls.append(url);return 429,b'{}'
    gateway=EvidenceGateway(tmp_path,providers=['crossref'],transport=http,clock=lambda:times[0])
    gateway.lookup({'title':'retry'});gateway.lookup({'title':'retry'})
    assert len(calls)==1
    times[0]+=601;gateway.lookup({'title':'retry'})
    assert len(calls)==2


def test_fulltext_timeout_retains_abstract(tmp_path):
    def timeout(url):raise TimeoutError()
    gateway=EvidenceGateway(tmp_path,providers=[],transport=timeout)
    result=gateway.content({'pmcid':'PMC123','abstract':'Available abstract'})
    assert result[0]['text']=='Available abstract'


def test_known_year_and_author_constrain_discovery(tmp_path):
    calls,http=transport({'message':{'items':[]}})
    EvidenceGateway(tmp_path,providers=['crossref','openalex'],transport=http).lookup({'title':'Attention Is All You Need','year':2017,'authors':['Vaswani']})
    assert any('query.author=Vaswani' in u and '2017' in u for u in calls)
    assert any('publication_year' in u and '2017' in u for u in calls)


def test_short_surname_with_initials_can_match_full_name_without_merging_people():
    r=record('Deep Residual Learning for Image Recognition','10.1109/cvpr.2016.90',2016,['Kaiming He'])
    assert resolve_identity({'title':r['work']['title'],'year':2016,'authors':['He K'],'doi':r['work']['doi']},[r])['state']=='observed'
    r=record(authors=['Bob Smith'])
    assert resolve_identity({'title':r['work']['title'],'year':2017,'authors':['Alice Smith'],'doi':r['work']['doi']},[r])['state']=='unknown'


def test_exact_identifier_disambiguates_same_title_versions():
    one=record();two=record(doi='10.48550/other');two['id']='e2'
    result=resolve_identity({'title':one['work']['title'],'year':2017,'authors':['Vaswani'],'doi':one['work']['doi']},[one,two])
    assert result['state']=='observed' and result['work']['doi']==one['work']['doi']


def test_verified_arxiv_work_can_supply_cached_full_text(tmp_path):
    import pymupdf
    doc=pymupdf.open();doc.new_page().insert_text((30,30),'Transformer architecture for machine translation.');body=doc.tobytes();doc.close();calls=[]
    def transport(url):calls.append(url);return 200,body
    gateway=EvidenceGateway(tmp_path,providers=[],transport=transport)
    work={'doi':'10.48550/arXiv.1706.03762','title':'Attention Is All You Need'}
    first=gateway.content(work);second=gateway.content(work)
    assert len(calls)==1 and calls[0]=='https://export.arxiv.org/pdf/1706.03762'
    assert first==second and first[0]['level']=='full_text'
    assert 'machine translation' in first[0]['text'] and first[0]['response_sha256']


def test_failed_full_text_fetch_retains_abstract_and_records_gap(tmp_path):
    gateway=EvidenceGateway(tmp_path,providers=[],transport=lambda url:(429,b''))
    content=gateway.content({'doi':'10.48550/arXiv.1706.03762','abstract':'An available abstract'})
    assert any(c.get('level')=='abstract' and c['status']=='ok' for c in content)
    assert any(c['status']=='unavailable' and c.get('coverage')=='unknown' for c in content)


def test_untrusted_work_url_is_never_fetched_as_a_full_text_source(tmp_path):
    calls=[];gateway=EvidenceGateway(tmp_path,providers=[],transport=lambda url:calls.append(url))
    gateway.content({'url':'https://example.org/private.pdf','title':'Work'})
    assert calls==[]

def test_corroborated_repository_identifier_survives_metadata_selection():
    from paper_compiler.identity import resolve_identity
    entry={'title':'A sufficiently specific scientific paper','authors':['Smith J'],'year':'2020','doi':'10.1/example'}
    records=[{'id':'publisher','status':'ok','work':{**entry,'abstract':'Publisher abstract'}},{'id':'repository','status':'ok','work':{**entry,'pmcid':'PMC123456'}}]
    answer=resolve_identity(entry,records)
    assert answer['value'] is True and answer['work']['pmcid']=='PMC123456'

def test_multiple_author_initials_match_full_names_without_merging_conflicts():
    from paper_compiler.identity import _author_match
    assert _author_match(['Fernando P. Polack'],['Polack FP'])
    assert not _author_match(['Fernando P. Polack'],['Polack FA'])
    assert not _author_match(['John Smith'],['James Smith'])

def test_crossref_optional_metadata_and_field_provenance_are_retained(tmp_path):
    data=crossref();raw=data['message']['items'][0]
    raw.update(volume='12',issue='3',page='20-25',**{'container-title':['Journal of Tests'],'publisher':'Example Press'})
    _,http=transport(data)
    work=EvidenceGateway(tmp_path,providers=['crossref'],transport=http).lookup({'title':'Attention Is All You Need'})[0]['work']
    assert {k:work[k] for k in ['volume','issue','pages','container','publisher']}=={'volume':'12','issue':'3','pages':'20-25','container':'Journal of Tests','publisher':'Example Press'}
    assert work['field_provenance']['volume']=='volume'

def test_frozen_evidence_does_not_refresh_after_live_cache_expiry(tmp_path):
    now=[1000];calls=[]
    def http(url):
        calls.append(url);return 200,json.dumps(crossref(title='Version '+str(len(calls)))).encode()
    frozen=EvidenceGateway(tmp_path,providers=['crossref'],transport=http,clock=lambda:now[0],snapshot_id='round-one')
    one=frozen.lookup({'title':'target'});now[0]+=90000
    again=EvidenceGateway(tmp_path,providers=['crossref'],transport=http,clock=lambda:now[0],snapshot_id='round-one').lookup({'title':'target'})
    assert one==again and len(calls)==1
    two=EvidenceGateway(tmp_path,providers=['crossref'],transport=http,clock=lambda:now[0],snapshot_id='round-two').lookup({'title':'target'})
    assert two!=one and len(calls)==2

def test_frozen_failure_and_content_are_pinned(tmp_path):
    calls=[]
    def http(url):calls.append(url);return 503,b''
    g=EvidenceGateway(tmp_path,providers=['crossref'],transport=http,snapshot_id='fixed')
    query={'title':'target'};first=g.lookup(query)
    g.clock=lambda:10**12
    assert g.lookup(query)==first
    work={'title':'target','pmcid':'PMC123456','doi':'10.1234/test'}
    a=g.content(work);b=g.content(work)
    assert a==b and len(calls)==2

def test_concurrent_snapshot_queries_observe_one_immutable_winner(tmp_path):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    counter=[0];barrier=threading.Barrier(2)
    def http(url):
        counter[0]+=1
        return 200,json.dumps(crossref(title='Concurrent version '+str(counter[0]))).encode()
    gateway=EvidenceGateway(tmp_path,providers=['crossref'],transport=http,snapshot_id='concurrent')
    save=gateway._cache_result
    def synchronized_save(path,value):
        barrier.wait(timeout=5)
        return save(path,value)
    gateway._cache_result=synchronized_save
    with ThreadPoolExecutor(max_workers=2) as pool:
        values=list(pool.map(gateway.lookup,[{'title':'target'},{'title':'target'}]))
    assert values[0]==values[1] and counter[0]==2
    gateway._cache_result=save
    assert gateway.lookup({'title':'target'})==values[0] and counter[0]==2

def test_independent_providers_overlap_io_but_keep_deterministic_record_order(tmp_path):
    import threading,time
    active=[0];maximum=[0];lock=threading.Lock()
    gateway=EvidenceGateway(tmp_path,providers=['crossref','datacite'],transport=lambda url:None)
    def retrieve(provider,url):
        with lock:active[0]+=1;maximum[0]=max(maximum[0],active[0])
        time.sleep(.04 if provider=='crossref' else .01)
        with lock:active[0]-=1
        return {'provider':provider,'id':provider,'works':[],'status':'empty'}
    gateway._retrieve=retrieve
    records=gateway.lookup({'title':'work'})
    assert maximum[0]==2
    assert [r['provider'] for r in records]==['crossref','datacite']

def test_provider_admission_is_shared_across_processes_and_snapshots(tmp_path):
    import multiprocessing,time
    if 'fork' not in multiprocessing.get_all_start_methods():pytest.skip('POSIX development service')
    ctx=multiprocessing.get_context('fork');events=ctx.Queue()
    def worker(ident):
        def http(url):
            events.put(('start',ident,time.time()));time.sleep(.15)
            events.put(('end',ident,time.time()))
            return 200,b'{"message":{"items":[]}}'
        gateway=EvidenceGateway(tmp_path,providers=['crossref'],transport=http,snapshot_id=str(ident))
        gateway.rate_limit=True;gateway.lookup({'title':'work-'+str(ident)})
    children=[ctx.Process(target=worker,args=(i,)) for i in range(2)]
    for child in children:child.start()
    for child in children:child.join(8);assert child.exitcode==0
    values=[events.get(timeout=2) for _ in range(4)]
    starts=sorted((t,i) for kind,i,t in values if kind=='start')
    ends={i:t for kind,i,t in values if kind=='end'}
    assert starts[1][0]-starts[0][0]>=.9
    assert ends[starts[0][1]]<=starts[1][0]

def test_retry_after_defers_new_queries_across_gateway_instances(tmp_path):
    calls=[]
    class Limited(tuple):
        headers={'retry-after':'3600'}
    def http(url):
        calls.append(url)
        return Limited((429,b''))
    one=EvidenceGateway(tmp_path,providers=['crossref'],transport=http,snapshot_id='one');one.rate_limit=True
    two=EvidenceGateway(tmp_path,providers=['crossref'],transport=http,snapshot_id='two');two.rate_limit=True
    first=one.lookup({'title':'first'});second=two.lookup({'title':'different'})
    assert len(calls)==1
    assert first[0]['http_status']==429 and second[0]['status']=='unavailable'
    assert second[0]['request_sent'] is False
    assert second[0]['deferred_reason']=='provider_retry_after_or_backoff'
