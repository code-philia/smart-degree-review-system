"""Bounded public bibliographic retrieval. Empty searches are never exclusions."""
import hashlib
import html
import json
import re
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlencode, quote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from urllib.error import HTTPError
from .storage import json_bytes, write_json_atomic

VERSION='public-evidence/1.1'
CONTENT_VERSION='public-content/1.1-arxiv'
MAX_BYTES=4*1024*1024
HOSTS={'api.crossref.org','api.datacite.org','api.openalex.org','www.ebi.ac.uk','export.arxiv.org'}
_GROUPS={'crossref':'doi-registration','datacite':'doi-registration','openalex':'aggregated-metadata','europepmc':'pubmed-metadata'}
_locks={name:threading.Lock() for name in _GROUPS}
_last={name:0.0 for name in _GROUPS}

class EvidenceError(ValueError):pass

def validate_url(url):
    p=urlsplit(url)
    if p.scheme!='https' or p.netloc not in HOSTS or p.username or p.password or p.port or p.fragment:
        raise EvidenceError('public evidence URL is not allowlisted')
    return url

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def _http(url,proxy=None):
    validate_url(url)
    opener=build_opener(_NoRedirect(),*([ProxyHandler({'https':proxy})] if proxy else []))
    try:
        with opener.open(Request(url,headers={'User-Agent':'SJTU-PaperCompiler/1.0 (scholarly citation validation)','Accept':'application/json, application/xml'}),timeout=20) as response:
            data=response.read(MAX_BYTES+1)
            if len(data)>MAX_BYTES:raise EvidenceError('response too large')
            return response.status,data
    except HTTPError as error:
        return error.code,b''

def _clean(text):return re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]+>',' ',str(text or '')))).strip()
def _year(value):
    try:return int(str(value)[:4])
    except (ValueError,TypeError):return None

def _works(provider,data):
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
            index=d.get('abstract_inverted_index') or {};positions={int(i):word for word,indices in index.items() for i in indices if type(i)is int and 0<=i<50000}
            yield {'title':_clean(d.get('display_name','')),'authors':[_clean(a.get('author',{}).get('display_name','')) for a in d.get('authorships',[])],
                'year':_year(d.get('publication_year')),'doi':(d.get('doi') or '').replace('https://doi.org/','').lower(),
                'abstract':_clean(' '.join(positions[i] for i in sorted(positions))), 'url':(d.get('primary_location') or {}).get('landing_page_url',''),'type':d.get('type','')}
    elif provider=='europepmc':
        for d in data.get('resultList',{}).get('result',[]):
            yield {'title':_clean(d.get('title','')),'authors':[_clean(a.get('fullName','')) for a in d.get('authorList',{}).get('author',[])],
                'year':_year(d.get('pubYear')),'doi':d.get('doi','').lower(),'abstract':_clean(d.get('abstractText','')), 'pmcid':d.get('pmcid',''),
                'url':'https://europepmc.org/article/'+str(d.get('source','MED'))+'/'+str(d.get('id','')),'type':'article'}

def _urls(provider,query):
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

class EvidenceGateway:
    def __init__(self,cache_dir,providers=None,transport=None,*,clock=time.time,proxy=None):
        self.cache_dir=Path(cache_dir);self.cache_dir.mkdir(parents=True,exist_ok=True)
        self.providers=['crossref','datacite','openalex','europepmc'] if providers is None else list(providers)
        if any(p not in _GROUPS for p in self.providers):raise EvidenceError('unknown provider')
        self.transport=transport or (lambda url:_http(url,proxy));self.clock=clock;self.rate_limit=transport is None
    def _retrieve(self,provider,url):
        validate_url(url);key=hashlib.sha256((VERSION+'\n'+url).encode()).hexdigest();path=self.cache_dir/(key+'.json')
        if path.exists():
            cached=json.loads(path.read_text())
            ttl=86400 if cached['status'] in {'ok','empty'} else 600
            if 0<=self.clock()-cached['retrieved_at']<ttl:return cached
        base={'provider':provider,'url':url,'retrieved_at':self.clock(),'source_group':_GROUPS[provider],'coverage':'partial_index','version':VERSION}
        try:
            with _locks[provider]:
                if self.rate_limit:time.sleep(max(0,1-(time.monotonic()-_last[provider])))
                status,body=self.transport(url);_last[provider]=time.monotonic()
            base.update(http_status=status,response_sha256=hashlib.sha256(body).hexdigest())
            if status!=200:base.update(status='unavailable',error='HTTP_'+str(status),works=[])
            elif len(body)>MAX_BYTES:raise EvidenceError('response too large')
            else:
                data=json.loads(body);works=list(_works(provider,data))[:5]
                base.update(status='ok' if works else 'empty',works=works)
        except (OSError,ValueError,TypeError,KeyError,IndexError) as error:
            base.update(status='unavailable',error=type(error).__name__,works=[])
        base['id']='retrieval-'+hashlib.sha256(json_bytes(base)).hexdigest()[:24]
        write_json_atomic(path,base)
        return base
    def lookup(self,query):
        records=[]
        for provider in self.providers:
            for url in _urls(provider,query):
                result=self._retrieve(provider,url)
                if not result['works']:records.append({k:v for k,v in result.items() if k!='works'})
                for index,work in enumerate(result['works']):
                    item={k:v for k,v in result.items() if k!='works'};item['id']=result['id']+'-'+str(index);item['work']=work
                    records.append(item)
        return records
    def content(self,work):
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
                    validate_url(url);status,body=self.transport(url)
                    if status!=200 or len(body)>MAX_BYTES:raise EvidenceError('full text unavailable')
                    xml=ET.fromstring(body);body_node=xml.find('body')
                    if body_node is None:raise EvidenceError('full text body absent')
                    text=' '.join(body_node.itertext())
                    item={'id':'content-'+key[:24],'status':'ok','level':'full_text','text':text[:180000], 'coverage':'full_text' if len(text)<=180000 else 'truncated_full_text',
                        'url':url,'retrieved_at':self.clock(),'response_sha256':hashlib.sha256(body).hexdigest(),'source_evidence_ids':work.get('evidence_ids',[])}
                    write_json_atomic(path,item);records.append(item)
                except (OSError,ValueError,ET.ParseError):pass
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
            if item['status']=='ok' or self.clock()-item['retrieved_at']<600:return item
        item={'id':'content-'+key[:24],'url':url,'retrieved_at':self.clock(),'coverage':'unknown','status':'unavailable','provider':'arxiv'}
        try:
            # One connection and at least three seconds between requests across local processes.
            import fcntl
            with (self.cache_dir/'arxiv-rate.lock').open('a+') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX);stamp=self.cache_dir/'arxiv-rate-time.json'
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
        write_json_atomic(path,item);return item
