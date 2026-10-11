"""Private-PDF MinerU API transport. No token or signed URL is included in errors."""
from hashlib import sha256
import io
import http.client
import os
import socket
import urllib.error
from dataclasses import replace
import json
import time
import urllib.request
import zipfile
from contextlib import nullcontext
from urllib.parse import quote
from pathlib import Path

import pymupdf

from .mineru_layout import normalize_layout, remap_layout_object
from .mineru_cache import RawLayoutCache, TaskState, cache_lock


BASE = "https://mineru.net/api/v4"
MAX_POLL_SECONDS = 17 * 60
MAX_ARCHIVE_BYTES = 150 * 1024 * 1024


class MinerUError(Exception):
    def __init__(self,message,*,retryable=False):
        super().__init__(message)
        self.retryable=retryable


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
        self._bound();return self.sock.recv_into(*args,**kwargs)
    def sendall(self,*args,**kwargs):
        self._bound();answer=self.sock.sendall(*args,**kwargs)
        _remaining(self.deadline);return answer
    def makefile(self,*args,**kwargs):
        stream=self.sock.makefile(*args,**kwargs)
        raw=getattr(stream,'raw',stream)
        if hasattr(raw,'_sock'):raw._sock=self
        return stream


def _open(request,timeout,deadline):
    class HttpConnection(http.client.HTTPConnection):
        def connect(self):
            self.timeout=min(timeout,_remaining(deadline))
            super().connect();self.sock=_DeadlineSocket(self.sock,deadline)
    class HttpsConnection(http.client.HTTPSConnection):
        def connect(self):
            self.timeout=min(timeout,_remaining(deadline))
            super().connect();self.sock=_DeadlineSocket(self.sock,deadline)
    class HttpHandler(urllib.request.HTTPHandler):
        def http_open(self,req):return self.do_open(HttpConnection,req)
    class HttpsHandler(urllib.request.HTTPSHandler):
        def https_open(self,req):return self.do_open(HttpsConnection,req,context=self._context)
    return urllib.request.build_opener(HttpHandler(),HttpsHandler()).open(request,timeout=timeout)


class UrllibHttpClient:
    def request(self, method, url, *, headers=None, data=None, timeout=30, deadline=None):
        deadline=deadline if deadline is not None else time.monotonic()+timeout
        request_type = SignedPutRequest if method == "PUT" else urllib.request.Request
        request = request_type(url, data=data, method=method, headers=headers or {})
        with _open(request,min(timeout,_remaining(deadline)),deadline) as response:
            if method=="PUT":return {}
            parts=[];size=0
            while True:
                _remaining(deadline)
                # read1 returns after available I/O rather than filling a large
                # buffer indefinitely during a slow continuous transmission.
                reader=getattr(response,'read1',response.read)
                piece=reader(min(64*1024,MAX_ARCHIVE_BYTES+1-size))
                _remaining(deadline)
                if not piece:
                    missing=getattr(response,"length",None)
                    if isinstance(missing,int) and missing>0:
                        raise http.client.IncompleteRead(b"",missing)
                    break
                parts.append(piece);size+=len(piece)
                if size>MAX_ARCHIVE_BYTES:raise MinerUError("MinerU result is too large")
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
            error=MinerUError('MinerU network request failed' if temporary else 'MinerU API rejected the request',retryable=temporary)
        except (urllib.error.URLError,OSError,socket.timeout,http.client.IncompleteRead,http.client.RemoteDisconnected):
            error=MinerUError('MinerU network request failed',retryable=True)
        except MinerUError as exc:
            error=exc
        except Exception:
            error=MinerUError('MinerU network request failed')
        if not error.retryable or attempt==3:raise error from None
        delay=min(2**attempt,4)
        if deadline is not None:delay=min(delay,_remaining(deadline))
        time.sleep(delay)


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
            names = [n for n in archive.namelist() if n == "layout.json" or n.endswith("/layout.json")]
            if len(names) != 1:
                raise ValueError("layout.json missing or ambiguous")
            info = archive.getinfo(names[0])
            if info.file_size > MAX_ARCHIVE_BYTES:
                raise ValueError("Oversized layout")
            data = json.loads(archive.read(info))
        pages = data["pdf_info"]
        if not isinstance(pages, list):
            raise ValueError("Invalid pages")
        return pages
    except (KeyError, ValueError, TypeError, zipfile.BadZipFile) as exc:
        raise MinerUError("MinerU layout archive is invalid") from None


def _submit_and_fetch(payload, token, client, *, poll_interval, deadline, force_ocr=False, state_store=None):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    file = {"name": "paper.pdf", "data_id": "pdf-rule-scan"}
    if force_ocr:
        file["is_ocr"] = True
    post = json.dumps({"files": [file], "model_version": "pipeline" if force_ocr else "vlm"},
                      ensure_ascii=False).encode("utf-8")
    batch_id=state_store.read() if state_store else None
    if batch_id is None:
        data = _data(_call(client, "POST", f"{BASE}/file-urls/batch",
                           headers=headers, data=post, timeout=30, deadline=deadline))
        upload_urls = data.get("file_urls")
        batch_id = data.get("batch_id")
        if not isinstance(upload_urls, list) or len(upload_urls) != 1 or not isinstance(batch_id, str):
            raise MinerUError("MinerU upload response is incomplete")
        _call(client, "PUT", upload_urls[0], headers={}, data=payload, timeout=120, deadline=deadline)
        if state_store:state_store.write(batch_id)
    while time.monotonic() < deadline:
        result = _data(_call(client, "GET", f"{BASE}/extract-results/batch/{quote(batch_id,safe='')}",
                             headers={"Authorization": f"Bearer {token}"}, timeout=30, deadline=deadline))
        entries = result.get("extract_result")
        if not isinstance(entries, list) or len(entries) != 1:
            raise MinerUError("MinerU task response is incomplete")
        state = entries[0].get("state")
        if state == "done":
            zip_url = entries[0].get("full_zip_url")
            if not isinstance(zip_url, str):
                raise MinerUError("MinerU result URL is missing")
            archive = _call(client, "GET", zip_url, headers={}, timeout=90, deadline=deadline)
            pages=_layout_from_zip(archive)
            if state_store:state_store.clear()
            return pages
        if state in ("failed", "error"):
            if state_store:state_store.clear()
            raise MinerUError("MinerU could not parse this PDF")
        if state not in ("pending", "running", "converting", "waiting-file", "waiting"):
            raise MinerUError("MinerU returned an unknown task state")
        time.sleep(min(poll_interval,_remaining(deadline)))
    raise MinerUError("MinerU task timed out",retryable=True)


def parse_layout(pdf_path, token, http_client=None, page_limit=180, *,
                 poll_interval=2.0, max_seconds=MAX_POLL_SECONDS, force_ocr=False, respect_rotation=False):
    if not token:
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
            def segment(start, stop):
                if time.monotonic() >= deadline:
                    raise MinerUError("MinerU task timed out",retryable=True)
                if start == 0 and stop == total and (not rotated or respect_rotation):
                    payload = Path(pdf_path).read_bytes()
                else:
                    with pymupdf.open() as chunk:
                        chunk.insert_pdf(document, from_page=start, to_page=stop - 1)
                        payload = chunk.tobytes(garbage=4, deflate=True, no_new_id=True)
                sizes = [(float(document[i].rect.width), float(document[i].rect.height))
                         for i in range(start, stop)]
                try:
                    if len(payload) > 200 * 1024 * 1024:
                        raise MinerUError("MinerU PDF segment exceeds 200 MB")
                    key=cache.key(payload,force_ocr) if cache else None
                    state=TaskState(cache,key,token) if cache else None
                    with cache_lock(cache,key,deadline) if cache else nullcontext():
                        pages=cache.read(key,stop-start) if cache else None
                        if pages is None:
                            options={'state_store':state} if state else {}
                            task_deadline=min(deadline,time.monotonic()+180) if stop-start>1 else deadline
                            pages = _submit_and_fetch(payload, token, client, poll_interval=poll_interval,
                                                      deadline=task_deadline, force_ocr=force_ocr,**options)
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
        raise MinerUError("MinerU task timed out",retryable=True) from None
    except Exception:
        raise MinerUError("PDF layout parsing failed") from None
