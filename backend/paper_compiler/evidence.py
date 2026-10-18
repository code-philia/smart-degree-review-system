"""Bounded public bibliographic retrieval. Empty searches are never exclusions."""
import hashlib
import html
import json
import os
import stat
import re
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlencode, quote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from urllib.error import HTTPError
from .storage import json_bytes, write_json_atomic
from .identity import normalize_doi

VERSION='public-evidence/1.2'
CONTENT_VERSION='public-content/1.1-arxiv'
DISCOVERY_VERSION='openalex-discovery/1.0'
MAX_BYTES=4*1024*1024
HOSTS={'api.crossref.org','api.datacite.org','api.openalex.org','www.ebi.ac.uk','export.arxiv.org'}
_GROUPS={'crossref':'doi-registration','datacite':'doi-registration','openalex':'aggregated-metadata','europepmc':'pubmed-metadata'}
_locks={name:threading.Lock() for name in _GROUPS}

class EvidenceError(ValueError):pass

class HTTPResponse(tuple):
    def __new__(cls,status,body,headers=None,request_sent=True):
        item=super().__new__(cls,(status,body))
        item.headers={str(k).lower():str(v) for k,v in (headers or {}).items()}
        item.request_sent=request_sent
        return item


def validate_url(url):
    p=urlsplit(url)
    if p.scheme!='https' or p.netloc not in HOSTS or p.username or p.password or p.port or p.fragment:
        raise EvidenceError('public evidence URL is not allowlisted')
    return url

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def _openalex_key():
    """Load a private credential; no key is added to URLs or evidence artifacts."""
    value=os.environ.get('OPENALEX_API_KEY')
    if value is None:
        path=Path(os.environ.get('PAPER_COMPILER_EVIDENCE_CONFIG',
            '/data/apps/smart-degree-review/config/paper-model-evidence.env'))
        try:
            if path.is_symlink():raise EvidenceError('OpenAlex configuration must be a private regular file')
            info=path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
                raise EvidenceError('OpenAlex configuration must have private permissions')
            for line in path.read_text(encoding='utf-8').splitlines():
                name,separator,setting=line.partition('=')
                if separator and name.strip()=='OPENALEX_API_KEY':
                    value=setting.strip()
                    if len(value)>=2 and value[0] in "\"'" and value[-1]==value[0]:value=value[1:-1]
        except FileNotFoundError:return None
        except OSError:raise EvidenceError('OpenAlex credential configuration is unreadable') from None
    if value is None or value=='':return None
    if not re.fullmatch(r'[A-Za-z0-9._~-]{1,512}',value):
        raise EvidenceError('Invalid OpenAlex credential format')
    return value


def _http(url,proxy=None):
    validate_url(url)
    key=_openalex_key() if urlsplit(url).hostname=='api.openalex.org' else None
    headers={'User-Agent':'SJTU-PaperCompiler/1.0 (scholarly citation validation)','Accept':'application/json, application/xml'}
    if key:headers['Authorization']='Bearer '+key
    def public_headers(values):
        return {str(k):str(v).replace(key,'[REDACTED]') if key else str(v) for k,v in values.items()}
    opener=build_opener(_NoRedirect(),*([ProxyHandler({'https':proxy})] if proxy else []))
    try:
        with opener.open(Request(url,headers=headers),timeout=20) as response:
            data=response.read(MAX_BYTES+1)
            if len(data)>MAX_BYTES:raise EvidenceError('response too large')
            if key:data=data.replace(key.encode(),b'[REDACTED]')
            return HTTPResponse(response.status,data,public_headers(response.headers))
    except HTTPError as error:
        return HTTPResponse(error.code,b'',public_headers(error.headers))

def _clean(text):return re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]+>',' ',str(text or '')))).strip()
def _year(value):
    try:return int(str(value)[:4])
    except (ValueError,TypeError):return None

def _identity_works(provider,data):
    if provider=='crossref':
        message=data.get('message',{});items=message.get('items',[message] if message.get('DOI') else [])
        for d in items:
            years=d.get('issued',d.get('published',{})).get('date-parts',[[None]])
            yield {'title':_clean((d.get('title') or [''])[0]),'authors':[_clean(a.get('given','')+' '+a.get('family','')) for a in d.get('author',[])],
                'year':_year(years[0][0]),'doi':d.get('DOI','').lower(),'abstract':_clean(d.get('abstract','')),'url':d.get('URL',''),'type':d.get('type','')}
    elif provider=='datacite':
        items=data.get('data',[]);items=items if isinstance(items,list) else [items]
        for obj in items:
            d=obj.get('attributes',{})
            yield {'title':_clean((d.get('titles') or [{}])[0].get('title','')),'authors':[_clean(a.get('name','')) for a in d.get('creators',[])],
                'year':_year(d.get('publicationYear')),'doi':d.get('doi','').lower(),'abstract':_clean(' '.join(x.get('description','') for x in d.get('descriptions',[]) if x.get('descriptionType')=='Abstract')),
                'url':d.get('url',''),'type':d.get('types',{}).get('resourceTypeGeneral','')}
    elif provider=='openalex':
        for d in data.get('results',[]):
            canonical=normalize_doi(d.get('doi'))
            aliases=sorted({normalize_doi(location.get('doi')) for location in d.get('locations',[])
                if isinstance(location,dict) and re.fullmatch(r'10\.\d{4,9}/[^\s]{1,250}',normalize_doi(location.get('doi')))}-{canonical})
            index=d.get('abstract_inverted_index') or {};positions={int(i):word for word,indices in index.items() for i in indices if type(i)is int and 0<=i<50000}
            yield {'title':_clean(d.get('display_name','')),'authors':[_clean(a.get('author',{}).get('display_name','')) for a in d.get('authorships',[])],
                'year':_year(d.get('publication_year')),'doi':canonical,'doi_aliases':aliases,
                'openalex_id':d.get('id') if re.fullmatch(r'https://openalex\.org/W\d+',str(d.get('id',''))) else None,
                'abstract':_clean(' '.join(positions[i] for i in sorted(positions))), 'url':(d.get('primary_location') or {}).get('landing_page_url',''),'type':d.get('type','')}
    elif provider=='europepmc':
        for d in data.get('resultList',{}).get('result',[]):
            yield {'title':_clean(d.get('title','')),'authors':[_clean(a.get('fullName','')) for a in d.get('authorList',{}).get('author',[])],
                'year':_year(d.get('pubYear')),'doi':d.get('doi','').lower(),'abstract':_clean(d.get('abstractText','')), 'pmcid':d.get('pmcid',''),
                'url':'https://europepmc.org/article/'+str(d.get('source','MED'))+'/'+str(d.get('id','')),'type':'article'}

def _works(provider,data):
    if provider=='crossref':
        message=data.get('message',{});raw=message.get('items',[message] if message.get('DOI') else [])
    elif provider=='datacite':
        raw=data.get('data',[]);raw=raw if isinstance(raw,list) else [raw]
        raw=[x.get('attributes',{}) for x in raw]
    elif provider=='openalex':raw=data.get('results',[])
    else:raw=data.get('resultList',{}).get('result',[])
    for work,item in zip(_identity_works(provider,data),raw):
        if provider=='crossref':
            extras={'container':((item.get('container-title') or [''])[0],'container-title[0]'),
                'volume':(item.get('volume'),'volume'),'issue':(item.get('issue'),'issue'),
                'pages':(item.get('page'),'page'),'publisher':(item.get('publisher'),'publisher'),
                'place':(item.get('publisher-location'),'publisher-location')}
        elif provider=='datacite':
            publisher=item.get('publisher');publisher=publisher.get('name') if isinstance(publisher,dict) else publisher
            container=item.get('container') or {}
            extras={'publisher':(publisher,'publisher'),'container':(container.get('title'),'container.title'),
                'volume':(container.get('volume'),'container.volume'),'issue':(container.get('issue'),'container.issue'),
                'pages':(container.get('firstPage'),'container.firstPage'),'version':(item.get('version'),'version')}
        elif provider=='openalex':
            b=item.get('biblio') or {};source=(item.get('primary_location') or {}).get('source') or {}
            pages='-'.join(str(v) for v in [b.get('first_page'),b.get('last_page')] if v)
            extras={'container':(source.get('display_name'),'primary_location.source.display_name'),
                'volume':(b.get('volume'),'biblio.volume'),'issue':(b.get('issue'),'biblio.issue'),
                'pages':(pages,'biblio.first_page,last_page')}
        else:
            journal=item.get('journalInfo') or {}
            extras={'container':((journal.get('journal') or {}).get('title'),'journalInfo.journal.title'),
                'volume':(journal.get('volume'),'journalInfo.volume'),'issue':(journal.get('issue'),'journalInfo.issueId'),
                'pages':(item.get('pageInfo'),'pageInfo')}
        provenance=({'openalex_id':'id',**({'doi_aliases':'locations[].doi'} if work.get('doi_aliases') else {})} if provider=='openalex' else {})
        for field,(value,path) in extras.items():
            if isinstance(value,(str,int,float)) and str(value).strip():
                work[field]=_clean(value);provenance[field]=path
        work['field_provenance']=provenance
        yield work

def _legacy_urls(provider,query):
    title=str(query.get('title','')).strip()[:1000];doi=str(query.get('doi','')).strip().lower()
    if doi and not re.fullmatch(r'10\.\d{4,9}/[^\s]{1,250}',doi):doi=''
    year=_year(query.get('year'));author=' '.join(str(a) for a in query.get('authors',[])[:2])[:120]
    if provider=='crossref':
        if doi:yield 'https://api.crossref.org/works/'+quote(doi,safe='')
        if title:yield 'https://api.crossref.org/works?'+urlencode({'query.bibliographic':title,'rows':5,**({'query.author':author} if author else {}),**({'filter':f'from-pub-date:{year},until-pub-date:{year}'} if year else {})})
    elif provider=='datacite':
        if doi:yield 'https://api.datacite.org/dois/'+quote(doi,safe='')
        if title:yield 'https://api.datacite.org/dois?'+urlencode({'query':'titles.title:"'+title.replace('"','')+'"'+(' AND publicationYear:'+str(year) if year else ''),'page[size]':5})
    elif provider=='openalex':
        if title:yield 'https://api.openalex.org/works?'+urlencode({'search':title,'per-page':5,**({'filter':'publication_year:'+str(year)} if year else {})})
    elif provider=='europepmc':
        term='DOI:"'+doi+'"' if doi else 'TITLE:"'+title.replace('"','')+'"'
        if doi or title:yield 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urlencode({'query':term,'format':'json','resultType':'core','pageSize':5})

def _urls(provider,query):
    normalized={**query,'doi':normalize_doi(query.get('doi'))}
    if provider!='openalex':
        yield from _legacy_urls(provider,normalized)
        return
    doi=normalized['doi']
    if re.fullmatch(r'10\.\d{4,9}/[^\s]{1,250}',doi):
        yield 'https://api.openalex.org/works?'+urlencode({'filter':'doi:https://doi.org/'+doi,'per-page':10})
    title=str(query.get('title','')).strip()
    if title:
        literal=title[:300].replace('\\','\\\\').replace('"','\\"')
        # Work-level dates can describe a later merged version; verify year after discovery.
        yield 'https://api.openalex.org/works?'+urlencode({'search.title':'"'+literal+'"','per-page':10})
        for url in _legacy_urls('openalex',query):
            if len(url.encode('utf-8'))<4094:yield url


class EvidenceGateway:
    def __init__(self,cache_dir,providers=None,transport=None,*,clock=time.time,proxy=None,snapshot_id=None):
        self.snapshot_id=snapshot_id;self.rate_dir=Path(cache_dir);self.rate_dir.mkdir(parents=True,exist_ok=True)
        self.cache_dir=self.rate_dir/'snapshots'/hashlib.sha256(str(snapshot_id).encode()).hexdigest() if snapshot_id else self.rate_dir
        self.cache_dir.mkdir(parents=True,exist_ok=True)
        self.providers=['crossref','datacite','openalex','europepmc'] if providers is None else list(providers)
        if any(p not in _GROUPS for p in self.providers):raise EvidenceError('unknown provider')
        self.transport=transport or (lambda url:_http(url,proxy));self.clock=clock;self.rate_limit=transport is None
        key=_openalex_key() if self.rate_limit and 'openalex' in self.providers else None
        self.openalex_rate_scope='-authenticated-'+hashlib.sha256(key.encode()).hexdigest()[:16] if key else ''
    def _cache_result(self,path,value):
        if self.snapshot_id:
            try:write_json_atomic(path,value,exclusive=True)
            except FileExistsError:return json.loads(path.read_text())
        else:write_json_atomic(path,value)
        return value
    def _fetch(self,provider,url):
        with _locks[provider]:
            if not self.rate_limit:return self.transport(url)
            import fcntl
            from email.utils import parsedate_to_datetime
            rate_name=provider+(self.openalex_rate_scope if provider=='openalex' else '')
            state_path=self.rate_dir/(rate_name+'-rate-state.json')
            # One in-flight request per provider across all local processes.
            with (self.rate_dir/(rate_name+'-rate.lock')).open('a+') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                state=json.loads(state_path.read_text()) if state_path.exists() else {}
                now=time.time();until=state.get('cooldown_until',0)
                if until>now:return HTTPResponse(429,b'',{'retry-after':str(until-now)},request_sent=False)
                time.sleep(max(0,1-(now-state.get('last_started',0))))
                state['last_started']=time.time()
                # Persist admission before I/O, including failed or interrupted requests.
                write_json_atomic(state_path,state)
                response=self.transport(url);status,_=response
                if status==429:
                    failures=state.get('rate_limit_failures',0)+1;delay=min(3600,60*2**min(failures-1,6))
                    header=getattr(response,'headers',{}).get('retry-after')
                    if header:
                        try:seconds=float(header)
                        except ValueError:
                            try:seconds=parsedate_to_datetime(header).timestamp()-time.time()
                            except (ValueError,TypeError,OverflowError):seconds=delay
                        if seconds==seconds and abs(seconds)!=float('inf'):delay=max(delay,seconds)
                    state.update(rate_limit_failures=failures,cooldown_until=time.time()+delay)
                elif status==200:state.update(rate_limit_failures=0,cooldown_until=0)
                write_json_atomic(state_path,state)
                return response

    def _retrieve(self,provider,url):
        validate_url(url);key=hashlib.sha256((VERSION+'\n'+url).encode()).hexdigest();path=self.cache_dir/(key+'.json')
        if path.exists():
            cached=json.loads(path.read_text())
            ttl=86400 if cached['status'] in {'ok','empty'} else 600
            if self.snapshot_id or 0<=self.clock()-cached['retrieved_at']<ttl:return cached
        base={'provider':provider,'url':url,'retrieved_at':self.clock(),'source_group':_GROUPS[provider],'coverage':'partial_index','version':VERSION}
        try:
            response=self._fetch(provider,url);status,body=response
            base['request_sent']=getattr(response,'request_sent',True)
            if not base['request_sent']:base['deferred_reason']='provider_retry_after_or_backoff'
            base.update(http_status=status,response_sha256=hashlib.sha256(body).hexdigest())
            if status!=200:base.update(status='unavailable',error='HTTP_'+str(status),works=[])
            elif len(body)>MAX_BYTES:raise EvidenceError('response too large')
            else:
                data=json.loads(body);works=list(_works(provider,data))[:10 if provider=='openalex' else 5]
                base.update(status='ok' if works else 'empty',works=works)
        except (OSError,ValueError,TypeError,KeyError,IndexError) as error:
            base.update(status='unavailable',error=type(error).__name__,works=[])
        base['id']='retrieval-'+hashlib.sha256(json_bytes(base)).hexdigest()[:24]
        return self._cache_result(path,base)
    def _lookup_urls(self,query):
        if not self.snapshot_id:return {provider:list(_urls(provider,query)) for provider in self.providers}
        key=hashlib.sha256(json_bytes({'providers':self.providers,'query':query})).hexdigest()
        path=self.cache_dir/('lookup-plan-'+key+'.json')
        if path.exists():return json.loads(path.read_text())['urls']
        policy_path=self.cache_dir/'discovery-policy.json'
        if policy_path.exists():policy=json.loads(policy_path.read_text())
        else:
            has_plans=any(self.cache_dir.glob('lookup-plan-*.json'))
            has_old_cache=any(re.fullmatch(r'[0-9a-f]{64}\.json',p.name) for p in self.cache_dir.glob('*.json'))
            policy=self._cache_result(policy_path,{'discovery_version':DISCOVERY_VERSION,
                'legacy':has_old_cache and not has_plans})
        planner=_legacy_urls if policy['legacy'] else _urls
        plans={provider:list(planner(provider,query)) for provider in self.providers}
        # Pin query strategy before I/O. Old snapshots retain their original URLs.
        return self._cache_result(path,{'schema_version':'public-lookup-plan/1.0',
            'discovery_version':DISCOVERY_VERSION,'urls':plans})['urls']

    def lookup(self,query):
        from concurrent.futures import ThreadPoolExecutor
        plans=self._lookup_urls(query)
        def retrieve_provider(provider):
            records=[]
            for url in plans[provider]:
                result=self._retrieve(provider,url)
                if not result['works']:records.append({k:v for k,v in result.items() if k!='works'})
                for index,work in enumerate(result['works']):
                    item={k:v for k,v in result.items() if k!='works'};item['id']=result['id']+'-'+str(index);item['work']=work
                    records.append(item)
            return records
        if not self.providers:return []
        # Independent providers overlap I/O; each provider keeps its existing lock,
        # request interval and URL order. map preserves the configured provider order.
        with ThreadPoolExecutor(max_workers=min(4,len(self.providers))) as pool:
            return [item for records in pool.map(retrieve_provider,self.providers) for item in records]
    def content(self,work):
        if not self.snapshot_id:return self._content(work)
        key=hashlib.sha256(json_bytes({'version':CONTENT_VERSION,'work':work})).hexdigest();path=self.cache_dir/('content-map-'+key+'.json')
        if path.exists():return json.loads(path.read_text())
        return self._cache_result(path,self._content(work))

    def _content(self,work):
        records=[]
        if work.get('abstract'):
            records.append({'id':'content-'+hashlib.sha256(json_bytes(work)).hexdigest()[:24],'status':'ok','level':'abstract','text':work['abstract'],
                'source_evidence_ids':work.get('evidence_ids',[]),'url':work.get('url',''),'coverage':'abstract_only'})
        pmcid=work.get('pmcid','')
        if re.fullmatch(r'PMC\d+',pmcid):
            url='https://www.ebi.ac.uk/europepmc/webservices/rest/'+pmcid+'/fullTextXML'
            # Full text is only from the explicit public archive endpoint; no arbitrary publisher URL is fetched.
            key=hashlib.sha256((VERSION+url).encode()).hexdigest();path=self.cache_dir/('content-'+key+'.json')
            if path.exists():records.append(json.loads(path.read_text()))
            else:
                try:
                    validate_url(url);status,body=self._fetch('europepmc',url)
                    if status!=200 or len(body)>MAX_BYTES:raise EvidenceError('full text unavailable')
                    xml=ET.fromstring(body);body_node=xml.find('body')
                    if body_node is None:raise EvidenceError('full text body absent')
                    text=' '.join(body_node.itertext())
                    item={'id':'content-'+key[:24],'status':'ok','level':'full_text','text':text[:180000], 'coverage':'full_text' if len(text)<=180000 else 'truncated_full_text',
                        'url':url,'retrieved_at':self.clock(),'response_sha256':hashlib.sha256(body).hexdigest(),'source_evidence_ids':work.get('evidence_ids',[])}
                    item=self._cache_result(path,item);records.append(item)
                except (OSError,ValueError,ET.ParseError) as error:
                    if self.snapshot_id:
                        item=self._cache_result(path,{'id':'content-'+key[:24],'status':'unavailable','url':url,'coverage':'unknown','reason':type(error).__name__,'retrieved_at':self.clock()});records.append(item)
        arxiv_id=re.fullmatch(r'10\.48550/arxiv\.(\d{4}\.\d{4,5}(?:v\d+)?)',str(work.get('doi','')).lower())
        if arxiv_id:
            records.append(self._arxiv_content(arxiv_id.group(1)))
        if not records:records=[{'id':'gap-'+hashlib.sha256(json_bytes(work)).hexdigest()[:24],'status':'unavailable','reason':'no public abstract or supported full text','coverage':'unknown'}]
        return records

    def _arxiv_content(self,identifier):
        """Research-use full text from a confirmed arXiv identity, not arbitrary URLs."""
        url='https://export.arxiv.org/pdf/'+identifier
        key=hashlib.sha256(('arxiv-text/1.0'+url).encode()).hexdigest();path=self.cache_dir/('content-'+key+'.json')
        if path.exists():
            item=json.loads(path.read_text())
            if self.snapshot_id or item['status']=='ok' or self.clock()-item['retrieved_at']<600:return item
        item={'id':'content-'+key[:24],'url':url,'retrieved_at':self.clock(),'coverage':'unknown','status':'unavailable','provider':'arxiv'}
        try:
            # One connection and at least three seconds between requests across local processes.
            import fcntl
            with (self.rate_dir/'arxiv-rate.lock').open('a+') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX);stamp=self.rate_dir/'arxiv-rate-time.json'
                if self.rate_limit:
                    previous=json.loads(stamp.read_text()).get('time',0) if stamp.exists() else 0
                    time.sleep(max(0,3-(time.time()-previous)))
                try:status,body=self.transport(url)
                finally:
                    if self.rate_limit:write_json_atomic(stamp,{'time':time.time()})
            item['http_status']=status
            if status!=200 or len(body)>MAX_BYTES or not body.startswith(b'%PDF-'):raise EvidenceError('public PDF unavailable')
            import pymupdf
            with pymupdf.open(stream=body,filetype='pdf') as document:
                if document.page_count>200:raise EvidenceError('public PDF exceeds page limit')
                text='\n'.join(page.get_text() for page in document)
            if not text.strip():raise EvidenceError('public PDF has no readable text')
            digest=hashlib.sha256(body).hexdigest()
            item.update(id='content-'+hashlib.sha256((url+digest).encode()).hexdigest()[:24],status='ok',level='full_text',
                text=text[:100000],coverage='full_text' if len(text)<=100000 else 'truncated_full_text',response_sha256=digest)
            pdf_path=self.cache_dir/('arxiv-'+digest+'.pdf')
            try:
                with pdf_path.open('xb') as stream:stream.write(body)
            except FileExistsError:pass
        except (OSError,ValueError,TypeError,RuntimeError) as error:item['reason']=type(error).__name__
        return self._cache_result(path,item)
