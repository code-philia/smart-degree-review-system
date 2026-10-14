"""Private-PDF MinerU API transport. No token or signed URL is included in errors."""
from hashlib import sha256
import io
import http.client
import os
import socket
import ssl
import urllib.error
from dataclasses import replace
import json
import time
import urllib.request
import zipfile
import re
from contextlib import contextmanager, nullcontext
from urllib.parse import quote, urlsplit
from pathlib import Path

import pymupdf

from .mineru_layout import normalize_layout, remap_layout_object
from .mineru_cache import RawLayoutCache, TaskState, cache_lock


BASE = "https://mineru.net/api/v4"
MAX_POLL_SECONDS = 17 * 60
MAX_ARCHIVE_BYTES = 150 * 1024 * 1024


class MinerUError(Exception):
    def __init__(self,message,*,retryable=False,diagnostics=None):
        super().__init__(message)
        self.retryable=retryable
        self.diagnostics=dict(diagnostics or {})



_ACCOUNT_FAILURES={'pool_invalid','pool_unavailable','pool_permissions',
    'legacy_invalid','legacy_unavailable','legacy_permissions','legacy_missing',
    'owner_invalid','owner_missing','owner_conflict','pdf_identity_invalid'}


def _account_error(code):
    safe=code if code in _ACCOUNT_FAILURES else 'pool_invalid'
    return MinerUError('MinerU PDF account ownership is unavailable',
                       diagnostics={'account_failure':safe})


class MinerUTaskBinding:
    """One private account for all chunks and OCR passes of one PDF job."""
    def __init__(self,pool,pdf_identity):
        from .mineru_account_pool import MinerUAccountPoolError
        failure=None
        try:account=pool.select_for_pdf(pdf_identity)
        except MinerUAccountPoolError as exc:failure=exc.reason_code
        if failure is not None:raise _account_error(failure)
        self._pool=pool
        self._account=account
        self._started=False
        self._pending_pinned=False
        self._failure=None
    def __repr__(self):
        return 'MinerUTaskBinding(account_bound=True)'
    @property
    def token(self):
        if self._failure is not None:raise _account_error(self._failure)
        return self._account.token
    @property
    def account_alias(self):
        legacy=self._pool.legacy_account
        ordered=[legacy]+sorted((a for a in self._pool.accounts
                                if a.account_id!=legacy.account_id),
                               key=lambda a:a.account_id)
        return 'account_'+str(next(i+1 for i,a in enumerate(ordered)
                                  if a.account_id==self._account.account_id))
    def pin_pending(self,state):
        from .mineru_account_pool import MinerUAccountPoolError
        metadata=state.pending_owner()
        if metadata is None:return False
        owner,legacy_unmarked=metadata
        failure=None
        if owner is None and not legacy_unmarked:
            failure='owner_invalid'
        else:
            try:account=self._pool.resolve_pending_owner(owner)
            except MinerUAccountPoolError as exc:failure=exc.reason_code
        if failure is not None:
            self._failure=failure
            raise _account_error(failure)
        if ((self._started or self._pending_pinned)
                and account.account_id!=self._account.account_id):
            self._failure='owner_conflict'
            raise _account_error('owner_conflict')
        self._account=account
        self._pending_pinned=True
        return legacy_unmarked
    def request_started(self):
        if self._failure is not None:raise _account_error(self._failure)
        self._started=True

def _proxy_configuration():
    """Detached scans must not inherit a short-lived SSH shell proxy."""
    dedicated=os.environ.get('MINERU_PROXY_URL','').strip()
    if dedicated:
        invalid=False
        try:
            parsed=urlsplit(dedicated)
            if (parsed.scheme not in {'http','https'} or not parsed.hostname
                    or parsed.path not in {'','/'} or parsed.query or parsed.fragment
                    or any(ord(char)<32 for char in dedicated)):
                raise ValueError
            if parsed.port is not None and not 0<parsed.port<65536:
                raise ValueError
        except ValueError:
            invalid=True
        if invalid:raise MinerUError('MinerU proxy configuration is invalid')
        return 'dedicated_proxy',{'http':dedicated,'https':dedicated}
    trust=os.environ.get('MINERU_TRUST_ENV_PROXY','').strip().lower()
    if trust in {'1','true','yes','on'}:
        return 'environment_proxy',None
    if trust not in {'','0','false','no','off'}:
        raise MinerUError('MinerU proxy configuration is invalid')
    return 'direct',{}


def _transport_diagnostics(exc,method,attempts,client):
    """Keep only structural network facts; never messages, URLs or headers."""
    known={'HTTPError','URLError','OSError','TimeoutError','ConnectionResetError',
           'ConnectionRefusedError','BrokenPipeError','SSLError','SSLEOFError',
           'SSLCertVerificationError','IncompleteRead','RemoteDisconnected','MinerUError'}
    def name(error):
        value=type(error).__name__
        return value if value in known else 'unknown'
    details={'operation':method if method in {'GET','POST','PUT','HEAD'} else 'other',
             'attempts':attempts,'exception_type':name(exc)}
    if isinstance(client,UrllibHttpClient):
        try:details['transport_mode']=_proxy_configuration()[0]
        except MinerUError:details['transport_mode']='invalid'
    else:details['transport_mode']='custom_client'
    reason=getattr(exc,'reason',None)
    error=reason if isinstance(reason,OSError) else exc
    if isinstance(exc,urllib.error.URLError) and not isinstance(exc,urllib.error.HTTPError):
        details['reason_type']=name(reason)
    phase=getattr(error,'_mineru_timeout_phase',None)
    if type(phase) is str and phase in {'connect','request_send','response_read','upload_slot'}:
        details['timeout_phase']=phase
    number=getattr(error,'errno',None)
    if isinstance(number,int):details['errno']=number
    if isinstance(exc,urllib.error.HTTPError) and isinstance(exc.code,int):
        details['http_status']=exc.code
    if isinstance(error,ssl.SSLError):
        value=getattr(error,'reason',None)
        if isinstance(value,str) and value and re.fullmatch('[A-Z_0-9]{1,80}',value):
            details['tls_reason']=value
    return details


@contextmanager
def _upload_slot(deadline):
    """Coordinate signed-body transfers across processes, within the same deadline."""
    configured = os.environ.get('MINERU_UPLOAD_CONCURRENCY', '2').strip()
    if (len(configured)>2 or not configured.isascii() or not configured.isdecimal()
            or not 1 <= int(configured) <= 32):
        raise MinerUError('MinerU upload concurrency configuration is invalid')
    limit = int(configured)
    explicit = os.environ.get('MINERU_UPLOAD_LOCK_DIR', '').strip()
    if explicit:
        folder = Path(explicit)
        if not folder.is_absolute():
            raise MinerUError('MinerU upload concurrency configuration is invalid')
    else:
        base = os.environ.get('XDG_CACHE_HOME', '').strip()
        folder = (Path(base) / 'mineru-upload-slots' if base
                  else Path(__file__).resolve().parents[1] / 'data/mineru-upload-slots')
    def remaining():
        left = deadline - time.monotonic()
        if left <= 0:
            raise MinerUError('MinerU task timed out', retryable=True,
                             diagnostics={'timeout_phase': 'upload_slot'})
        return left
    remaining()
    try:
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError:
        raise MinerUError('MinerU upload concurrency storage is unavailable') from None
    stream = None
    while stream is None:
        remaining()
        for index in range(limit):
            candidate = None
            try:
                descriptor = os.open(folder / (str(index) + '.lock'), os.O_RDWR | os.O_CREAT, 0o600)
                candidate = os.fdopen(descriptor, 'r+b')
                if os.name == 'nt':
                    import msvcrt
                    if candidate.seek(0, os.SEEK_END) == 0:
                        candidate.write(b'0'); candidate.flush()
                    candidate.seek(0)
                    msvcrt.locking(candidate.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(candidate.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                stream = candidate
                break
            except BlockingIOError:
                if candidate is not None: candidate.close()
            except OSError as exc:
                if candidate is not None: candidate.close()
                if os.name == 'nt' and getattr(exc, 'errno', None) in {13, 36}:
                    continue
                raise MinerUError('MinerU upload concurrency storage is unavailable') from None
        if stream is None:
            time.sleep(min(.05, remaining()))
    try:
        remaining()
        yield
    finally:
        try:
            if os.name == 'nt':
                import msvcrt
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()


class SignedPutRequest(urllib.request.Request):
    """Suppress urllib's form Content-Type on a presigned binary upload."""

    def has_header(self, header_name):
        if header_name.lower() == "content-type":
            return True
        return super().has_header(header_name)

class _DeadlineSocket:
    """Apply one absolute deadline to sends, headers and response-body I/O."""
    def __init__(self,sock,deadline):
        self.sock=sock;self.deadline=deadline;self.timeout=sock.gettimeout()
    def __getattr__(self,name):return getattr(self.sock,name)
    def _bound(self):
        left=_remaining(self.deadline)
        self.sock.settimeout(min(self.timeout,left) if self.timeout is not None else left)
    def recv_into(self,*args,**kwargs):
        try:
            self._bound();return self.sock.recv_into(*args,**kwargs)
        except (TimeoutError,MinerUError) as exc:
            exc._mineru_timeout_phase='response_read'
            raise
    def sendall(self,*args,**kwargs):
        try:
            data=memoryview(args[0])
            # A whole large byte body makes socket.sendall's timeout cover
            # its complete transfer, even with continuous forward progress.
            # Bound each small send by the same immutable absolute deadline.
            for offset in range(0,len(data),64*1024):
                self._bound()
                self.sock.sendall(data[offset:offset+64*1024],*args[1:],**kwargs)
                _remaining(self.deadline)
            return None
        except (TimeoutError,MinerUError) as exc:
            exc._mineru_timeout_phase='request_send'
            raise
    def makefile(self,*args,**kwargs):
        stream=self.sock.makefile(*args,**kwargs)
        raw=getattr(stream,'raw',stream)
        if hasattr(raw,'_sock'):raw._sock=self
        return stream


def _open(request,timeout,deadline):
    class HttpConnection(http.client.HTTPConnection):
        def connect(self):
            self.timeout=min(timeout,30,_remaining(deadline))
            try:
                super().connect()
            except TimeoutError as exc:
                exc._mineru_timeout_phase='connect'
                raise
            self.sock.settimeout(min(timeout,_remaining(deadline)))
            self.sock=_DeadlineSocket(self.sock,deadline)
    class HttpsConnection(http.client.HTTPSConnection):
        def connect(self):
            self.timeout=min(timeout,30,_remaining(deadline))
            try:
                super().connect()
            except TimeoutError as exc:
                exc._mineru_timeout_phase='connect'
                raise
            self.sock.settimeout(min(timeout,_remaining(deadline)))
            self.sock=_DeadlineSocket(self.sock,deadline)
    class HttpHandler(urllib.request.HTTPHandler):
        def http_open(self,req):return self.do_open(HttpConnection,req)
    class HttpsHandler(urllib.request.HTTPSHandler):
        def https_open(self,req):return self.do_open(HttpsConnection,req,context=self._context)
    _,proxies=_proxy_configuration()
    proxy=urllib.request.ProxyHandler(proxies) if proxies is not None else urllib.request.ProxyHandler()
    return urllib.request.build_opener(proxy,HttpHandler(),HttpsHandler()).open(request,timeout=timeout)


class UrllibHttpClient:
    def request(self, method, url, *, headers=None, data=None, timeout=30, deadline=None,
                range_response=False, max_response_bytes=MAX_ARCHIVE_BYTES):
        deadline=deadline if deadline is not None else time.monotonic()+timeout
        request_type = SignedPutRequest if method == "PUT" else urllib.request.Request
        request = request_type(url, data=data, method=method, headers=headers or {})
        slot = _upload_slot(deadline) if method == 'PUT' else nullcontext()
        with slot, _open(request,min(timeout,_remaining(deadline)),deadline) as response:
            if method=="PUT":return {}
            if range_response:
                if response.status==200:
                    # A server may ignore Range. Close before reading its
                    # potentially large image payload; use the full fallback.
                    return {'range_supported':False}
                if response.status!=206:
                    raise MinerUError('MinerU result range response is invalid')
            parts=[];size=0
            while True:
                _remaining(deadline)
                # read1 returns after available I/O rather than filling a large
                # buffer indefinitely during a slow continuous transmission.
                reader=getattr(response,'read1',response.read)
                piece=reader(min(64*1024,max_response_bytes+1-size))
                _remaining(deadline)
                if not piece:
                    missing=getattr(response,"length",None)
                    if isinstance(missing,int) and missing>0:
                        raise http.client.IncompleteRead(b"",missing)
                    break
                parts.append(piece);size+=len(piece)
                if size>max_response_bytes:raise MinerUError("MinerU result is too large")
            if range_response:
                return {'range_supported':True,'body':b''.join(parts),
                    'headers':{str(k).lower():str(v) for k,v in response.headers.items()}}
        payload=b''.join(parts)
        try:
            return json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            return payload


def _remaining(deadline):
    remaining=deadline-time.monotonic()
    if remaining<=0:raise MinerUError("MinerU task timed out",retryable=True)
    return remaining


def _call(client, method, url, *, deadline=None, **kwargs):
    """Retry temporary transport/service errors on the same operation."""
    requested=kwargs.get('timeout',30)
    for attempt in range(4):
        if deadline is not None:kwargs['timeout']=min(requested,_remaining(deadline))
        try:
            options={'deadline':deadline} if deadline is not None and isinstance(client,UrllibHttpClient) else {}
            result=client.request(method,url,**kwargs,**options)
            if isinstance(result,dict) and result.get('code') in {-10001,-60001,-60007,-60009}:
                raise MinerUError('MinerU service is temporarily unavailable',retryable=True)
            return result
        except urllib.error.HTTPError as exc:
            temporary=exc.code in {408,429,500,502,503,504}
            error=MinerUError('MinerU network request failed' if temporary else 'MinerU API rejected the request',retryable=temporary,
                             diagnostics=_transport_diagnostics(exc,method,attempt+1,client))
        except (urllib.error.URLError,OSError,socket.timeout,http.client.IncompleteRead,http.client.RemoteDisconnected) as exc:
            error=MinerUError('MinerU network request failed',retryable=True,
                             diagnostics=_transport_diagnostics(exc,method,attempt+1,client))
        except MinerUError as exc:
            error=exc
            error.diagnostics={**_transport_diagnostics(exc,method,attempt+1,client),**error.diagnostics}
        except Exception as exc:
            error=MinerUError('MinerU network request failed',
                             diagnostics=_transport_diagnostics(exc,method,attempt+1,client))
        if not error.retryable or attempt==3:raise error from None
        delay=min(2**attempt,4)
        if deadline is not None:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise error from None
            delay=min(delay,remaining)
        time.sleep(delay)
        if deadline is not None and time.monotonic()>=deadline:raise error from None


def _data(result):
    if not isinstance(result, dict) or result.get("code") != 0:
        raise MinerUError("MinerU API rejected the request")
    data = result.get("data")
    if not isinstance(data, dict):
        raise MinerUError("MinerU API response is incomplete")
    return data


def _layout_from_zip(payload):
    try:
        if not isinstance(payload, bytes) or len(payload) > MAX_ARCHIVE_BYTES:
            raise ValueError("Invalid archive")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            return _layout_member(archive)
    except (KeyError, ValueError, TypeError, zipfile.BadZipFile):
        pass
    # Raising after the handler avoids retaining JSONDecodeError.doc or other
    # private archive/parser inputs in an otherwise sanitized error context.
    raise MinerUError("MinerU layout archive is invalid")


def _layout_member(archive):
    names=[n for n in archive.namelist() if n=='layout.json' or n.endswith('/layout.json')]
    if len(names)!=1:raise ValueError('layout.json missing or ambiguous')
    info=archive.getinfo(names[0])
    if info.file_size>MAX_ARCHIVE_BYTES or info.compress_size>MAX_ARCHIVE_BYTES:
        raise ValueError('Oversized layout')
    data=json.loads(archive.read(info))  # zipfile verifies the member CRC.
    pages=data['pdf_info']
    if not isinstance(pages,list):raise ValueError('Invalid pages')
    return pages


class _RangeUnavailable(Exception):
    pass


class _ArchiveRangeReader:
    """Seekable ZIP view; unrelated image assets are never requested."""
    def __init__(self,client,url,deadline):
        self.client=client;self.url=url;self.deadline=deadline;self.position=0
        self.blocks=[];self.total=None;self.etag=None
        answer=self._request('bytes=-65557',65557)
        if not answer.get('range_supported'):raise _RangeUnavailable()
        first,last,total=self._bounds(answer)
        if last!=total-1 or first!=max(0,total-65557):raise _RangeUnavailable()
        self.total=total;self.etag=answer['headers'].get('etag')
        self.blocks.append((first,last+1,answer['body']))

    def _request(self,header,limit):
        headers={'Range':header,'Accept-Encoding':'identity'}
        if self.etag and not self.etag.startswith('W/'):
            headers['If-Range']=self.etag
        return _call(self.client,'GET',self.url,headers=headers,timeout=90,deadline=self.deadline,
                     range_response=True,max_response_bytes=limit)

    @staticmethod
    def _bounds(answer):
        match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',answer.get('headers',{}).get('content-range',''))
        if not match:raise _RangeUnavailable()
        first,last,total=map(int,match.groups())
        if first>last or last>=total or len(answer.get('body',b''))!=last-first+1:
            raise _RangeUnavailable()
        if answer.get('headers',{}).get('content-encoding','identity') not in ('','identity'):
            raise _RangeUnavailable()
        return first,last,total

    def seek(self,offset,whence=0):
        base={0:0,1:self.position,2:self.total}.get(whence)
        if base is None or not 0<=base+offset<=self.total:raise ValueError('Invalid ZIP offset')
        self.position=base+offset;return self.position

    def tell(self):return self.position
    def seekable(self):return True

    def read(self,count=-1):
        _remaining(self.deadline)
        end=self.total if count<0 else min(self.total,self.position+count)
        if end-self.position>MAX_ARCHIVE_BYTES:raise ValueError('Oversized ZIP read')
        if end==self.position:return b''
        for first,last,payload in self.blocks:
            if first<=self.position and end<=last:
                result=payload[self.position-first:end-first];self.position=end;return result
        first=self.position;last=min(self.total,max(end,first+65536))
        answer=self._request(f'bytes={first}-{last-1}',last-first)
        try:
            bounds=self._bounds(answer) if answer.get('range_supported') else None
        except _RangeUnavailable:
            bounds=None
        if (bounds!=(first,last-1,self.total)
            or self.etag and answer.get('headers',{}).get('etag')!=self.etag):
            raise MinerUError('MinerU result archive changed during download',retryable=True)
        result=answer['body'][:end-first]
        # Keep the small directory/header blocks; a large layout is read once.
        if len(answer['body'])<=65557 and len(self.blocks)<8:
            self.blocks.append((first,last,answer['body']))
        self.position=end;return result


def _fetch_layout_pages(client,url,*,deadline):
    if isinstance(client,UrllibHttpClient):
        invalid=False
        try:
            source=_ArchiveRangeReader(client,url,deadline)
            with zipfile.ZipFile(source) as archive:return _layout_member(archive)
        except _RangeUnavailable:
            pass
        except (KeyError,ValueError,TypeError,zipfile.BadZipFile,NotImplementedError):
            invalid=True
        if invalid:raise MinerUError('MinerU layout archive is invalid')
    return _layout_from_zip(_call(client,'GET',url,headers={},timeout=90,deadline=deadline))


def _submit_and_fetch(payload, token, client, *, poll_interval, deadline, force_ocr=False,
                      state_store=None, stall_seconds=None, legacy_owned=False):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    file = {"name": "paper.pdf", "data_id": "pdf-rule-scan"}
    if force_ocr:
        file["is_ocr"] = True
    post = json.dumps({"files": [file], "model_version": "pipeline" if force_ocr else "vlm"},
                      ensure_ascii=False).encode("utf-8")
    batch_id=state_store.read(legacy_owned=True) if state_store and legacy_owned else (state_store.read() if state_store else None)
    poll_deadline = deadline
    if batch_id is None:
        data = _data(_call(client, "POST", f"{BASE}/file-urls/batch",
                           headers=headers, data=post, timeout=30, deadline=deadline))
        upload_urls = data.get("file_urls")
        batch_id = data.get("batch_id")
        if not isinstance(upload_urls, list) or len(upload_urls) != 1 or not isinstance(batch_id, str):
            raise MinerUError("MinerU upload response is incomplete")
        _call(client, "PUT", upload_urls[0], headers={}, data=payload, timeout=120, deadline=deadline)
        if state_store:state_store.write(batch_id)
        # The split watchdog applies to a newly submitted running task. A
        # retained task has already spent that time in the cloud and must be
        # checked on its own batch before another upload is considered.
        if stall_seconds is not None:
            poll_deadline = min(deadline, time.monotonic() + stall_seconds)
    while time.monotonic() < poll_deadline:
        result = _data(_call(client, "GET", f"{BASE}/extract-results/batch/{quote(batch_id,safe='')}",
                             headers={"Authorization": f"Bearer {token}"}, timeout=30, deadline=poll_deadline))
        entries = result.get("extract_result")
        if not isinstance(entries, list) or len(entries) != 1:
            raise MinerUError("MinerU task response is incomplete")
        state = entries[0].get("state")
        if state == "done":
            zip_url = entries[0].get("full_zip_url")
            if not isinstance(zip_url, str):
                raise MinerUError("MinerU result URL is missing")
            pages=_fetch_layout_pages(client,zip_url,deadline=deadline)
            if state_store:state_store.clear()
            return pages
        if state in ("failed", "error"):
            if state_store:state_store.clear()
            raise MinerUError("MinerU could not parse this PDF")
        if state not in ("pending", "running", "converting", "waiting-file", "waiting"):
            raise MinerUError("MinerU returned an unknown task state")
        time.sleep(min(poll_interval,_remaining(poll_deadline)))
    raise MinerUError("MinerU task timed out",retryable=True)


def parse_layout(pdf_path, token=None, http_client=None, page_limit=180, *,
                 poll_interval=2.0, max_seconds=MAX_POLL_SECONDS, force_ocr=False, respect_rotation=False,
                 account_pool=None, pdf_identity=None, account_binding=None):
    if account_binding is None and account_pool is not None:
        identity=pdf_identity if pdf_identity is not None else sha256(Path(pdf_path).read_bytes()).hexdigest()
        account_binding=MinerUTaskBinding(account_pool,identity)
    if not token and account_binding is None:
        raise MinerUError("MinerU API token is not configured")
    if not 1 <= page_limit <= 200:
        raise ValueError("page_limit must be between 1 and 200")
    client = http_client or UrllibHttpClient()
    cache_folder=os.environ.get('MINERU_CACHE_DIR')
    if cache_folder is None and http_client is None:
        cache_folder=Path(__file__).resolve().parents[1]/'data/mineru-layout-cache'
    cache=RawLayoutCache(cache_folder) if cache_folder else None
    try:
        document = pymupdf.open(Path(pdf_path))
        try:
            total = len(document)
            if total < 1:
                raise MinerUError("PDF has no pages")
            rotated = {i for i, page in enumerate(document) if page.rotation}
            if not respect_rotation:
                for index in rotated:
                    document[index].set_rotation(0)
            deadline = time.monotonic() + max_seconds
            def segment_payload(start,stop):
                if start == 0 and stop == total and (not rotated or respect_rotation):
                    return Path(pdf_path).read_bytes()
                with pymupdf.open() as chunk:
                    chunk.insert_pdf(document, from_page=start, to_page=stop - 1)
                    return chunk.tobytes(garbage=4, deflate=True, no_new_id=True)
            if account_binding is not None and cache:
                # Resolve all ordinary chunk owners before the first new upload,
                # so a later retained chunk pins the entire PDF to its creator.
                for first in range(0,total,page_limit):
                    last=min(first+page_limit,total)
                    payload=segment_payload(first,last)
                    key=cache.key(payload,force_ocr)
                    if cache.read(key,last-first) is None:
                        account_binding.pin_pending(TaskState(cache,key,account_binding.token))
                    if time.monotonic()>=deadline:
                        raise MinerUError("MinerU task timed out",retryable=True)
            def segment(start, stop):
                if time.monotonic() >= deadline:
                    raise MinerUError("MinerU task timed out",retryable=True)
                payload=segment_payload(start,stop)
                sizes = [(float(document[i].rect.width), float(document[i].rect.height))
                         for i in range(start, stop)]
                try:
                    if len(payload) > 200 * 1024 * 1024:
                        raise MinerUError("MinerU PDF segment exceeds 200 MB")
                    key=cache.key(payload,force_ocr) if cache else None
                    with cache_lock(cache,key,deadline) if cache else nullcontext():
                        pages=cache.read(key,stop-start) if cache else None
                        if pages is None:
                            current_token=account_binding.token if account_binding is not None else token
                            state=TaskState(cache,key,current_token) if cache else None
                            legacy_owned=False
                            if account_binding is not None:
                                if state:
                                    legacy_owned=account_binding.pin_pending(state)
                                    current_token=account_binding.token
                                    state=TaskState(cache,key,current_token)
                                account_binding.request_started()
                            options={'state_store':state} if state else {}
                            if legacy_owned:options['legacy_owned']=True
                            pages = _submit_and_fetch(payload, current_token, client, poll_interval=poll_interval,
                                                      deadline=deadline, force_ocr=force_ocr,
                                                      stall_seconds=180 if stop-start>1 else None, **options)
                        objects=normalize_layout(pages, start + 1, sizes,
                            source_namespace=key or (sha256(payload).hexdigest()+
                                                     ('-pipeline-ocr' if force_ocr else '')))
                        if cache:cache.write(key,pages)
                    if respect_rotation:
                        def canonical(obj):
                            source=document[obj.page_number-1]
                            def box(b):return tuple(pymupdf.Rect(b)*source.derotation_matrix)
                            return remap_layout_object(obj,box,page_width=float(source.cropbox.width),
                                                       page_height=float(source.cropbox.height))
                        objects=[canonical(obj) for obj in objects]
                    return objects
                except MinerUError as exc:
                    # Retry only structural/size failures using smaller original
                    # page subsets. Auth and transport failures never fan out.
                    if time.monotonic() >= deadline:
                        # An expired absolute budget cannot make progress by
                        # splitting; preserve the original safe failure phase.
                        raise
                    if stop - start <= 1 or str(exc) not in {
                            "MinerU PDF segment exceeds 200 MB", "MinerU result is too large",
                            "MinerU could not parse this PDF", "MinerU task timed out"}:
                        raise
                    middle = start + (stop - start) // 2
                    return segment(start, middle) + segment(middle, stop)
            objects = []
            for start in range(0, total, page_limit):
                objects.extend(segment(start, min(start + page_limit, total)))
            return objects
        finally:
            document.close()
    except MinerUError:
        raise
    except TimeoutError:
        failure=MinerUError("MinerU task timed out",retryable=True)
    except Exception:
        failure=MinerUError("PDF layout parsing failed")
    raise failure
