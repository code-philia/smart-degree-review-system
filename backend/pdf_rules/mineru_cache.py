"""Atomic raw-layout cache keyed by exact uploaded bytes and parsing model."""
from hashlib import sha256
import json
import os
from pathlib import Path
import uuid
import re
import time
from contextlib import contextmanager


def content_hash(pages):
    return sha256(json.dumps(pages,ensure_ascii=True,separators=(',',':')).encode('utf-8')).hexdigest()


class RawLayoutCache:
    def __init__(self,folder):
        self.folder=Path(folder)
    def key(self,payload,force_ocr=False):
        return sha256(payload).hexdigest()+('-pipeline-ocr' if force_ocr else '')
    def read(self,key,count):
        path=self.folder/(key+'.json')
        try:
            if path.stat().st_size>150*1024*1024:return None
            record=json.loads(path.read_text(encoding='utf-8'))
            pages=record['pages']
            if (record.get('format')!=1 or record.get('input_sha')!=key
                    or record.get('page_count')!=count or not isinstance(pages,list)
                    or len(pages)!=count or record.get('pages_sha256')!=content_hash(pages)):
                return None
            return pages
        except (OSError,ValueError,KeyError,TypeError):
            return None
    def write(self,key,pages):
        temporary=None
        try:
            self.folder.mkdir(parents=True,exist_ok=True,mode=0o700)
            path=self.folder/(key+'.json')
            temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
            record=dict(format=1,input_sha=key,page_count=len(pages),pages_sha256=content_hash(pages),pages=pages)
            temporary.write_text(json.dumps(record,ensure_ascii=True),encoding='utf-8')
            temporary.replace(path)
            return True
        except OSError:
            return False  # A cache failure cannot invalidate a completed parse.
        finally:
            if temporary is not None:
                try:temporary.unlink(missing_ok=True)
                except OSError:pass


class TaskState:
    """Only an opaque batch identifier is retained; signed URLs are never saved."""
    def __init__(self,cache,key,token):
        self.path=cache.folder/(key+'.pending.json')
        self.account=sha256(token.encode('utf-8')).hexdigest()
    def read(self):
        try:
            record=json.loads(self.path.read_text(encoding='utf-8'))
            batch=record.get('batch_id')
            if (record.get('account_sha')==self.account and isinstance(batch,str)
                    and re.fullmatch(r'[A-Za-z0-9_-]{1,128}',batch)
                    and 0<=time.time()-record['submitted_at']<48*3600):
                return batch
        except (OSError,ValueError,KeyError,TypeError):pass
        return None
    def write(self,batch):
        temporary=self.path.with_name(self.path.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            temporary.write_text(json.dumps(dict(batch_id=batch,account_sha=self.account,submitted_at=time.time())),encoding='utf-8')
            temporary.replace(self.path)
        except OSError:pass
        finally:
            try:temporary.unlink(missing_ok=True)
            except OSError:pass
    def clear(self):
        try:self.path.unlink(missing_ok=True)
        except OSError:pass


@contextmanager
def cache_lock(cache,key,deadline):
    """An OS lock releases on worker exit; a new worker can safely resume."""
    stream=None;locked=False
    try:
        try:
            cache.folder.mkdir(parents=True,exist_ok=True,mode=0o700)
            stream=(cache.folder/(key+'.lock')).open('a+b')
            if stream.tell()==0:stream.write(b'0');stream.flush()
        except OSError:
            if stream:stream.close();stream=None
        if stream:
            while not locked:
                try:
                    if os.name=='nt':
                        import msvcrt
                        stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                    locked=True
                except OSError:
                    left=deadline-time.monotonic()
                    if left<=0:raise TimeoutError('Raw parse cache wait timed out')
                    time.sleep(min(.1,left))
        yield
    finally:
        if stream:
            if locked:
                if os.name=='nt':
                    import msvcrt
                    stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
            stream.close()
