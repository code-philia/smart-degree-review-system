"""Frozen, hash-checked batch manifests with durable per-item checkpoints."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,re,threading
from pathlib import Path
from .storage import json_bytes,write_json_atomic
from .contracts import validate_ir

VERSION='paper-batch/1.1'
def file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(Path(path).read_text())
def safe_id(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',value):raise ValueError('invalid item id')
    return value

def freeze(root,identity):
    root=Path(root);root.mkdir(parents=True,exist_ok=True);path=root/'frozen.json'
    try:write_json_atomic(path,identity,exclusive=True)
    except FileExistsError:
        if load(path)!=identity:raise ValueError('frozen manifest or pipeline version conflict')

def run_batch(manifest:Path,config:dict,output_root:Path):
    data=load(manifest);items=data.get('items',[])
    if not data.get('version') or not config.get('pipeline_version'):raise ValueError('frozen pipeline version is required')
    ids=[safe_id(item['id']) for item in items]
    if len(set(ids))!=len(ids):raise ValueError('duplicate item id')
    root=Path(output_root);identity={'manifest':data,'pipeline_version':config['pipeline_version'],'batch_version':VERSION,'settings':config.get('frozen_settings',{})}
    freeze(root,identity)
    workers=config.get('workers',1)
    if type(workers)is not int or not 1<=workers<=3:raise ValueError('workers must be 1..3')
    runner=config['runner'];stop=threading.Event()
    def process(item):
        folder=root/'items'/item['id'];checkpoint=folder/'checkpoint.json'
        output=folder/'result.json';attempt=folder/'attempt-1.json';started=folder/'started.json'
        ownership={'id':item['id'],'input_sha256':item['sha256'],'pipeline_version':config['pipeline_version']}
        def verify_result(record):
            if record['status']=='completed':
                if record['result_path']!=str(output) or file_hash(output)!=record['result_sha256']:raise ValueError('completed result changed')
            return record
        def finish(record):
            if not attempt.exists():write_json_atomic(attempt,record,exclusive=True)
            write_json_atomic(checkpoint,record,exclusive=True)
            return record
        if checkpoint.exists():
            if file_hash(item['input_path'])!=item['sha256']:raise ValueError('completed frozen input changed')
            return verify_result(load(checkpoint))
        if started.exists():
            if load(started)!=ownership:raise ValueError('attempt ownership changed')
            if file_hash(item['input_path'])!=item['sha256']:raise ValueError('started frozen input changed')
            if attempt.exists():return finish(verify_result(load(attempt)))
            if output.exists():
                if not isinstance(load(output),dict):raise ValueError('committed result invalid')
                return finish({'id':item['id'],'status':'completed','result_path':str(output),'result_sha256':file_hash(output)})
            return finish({'id':item['id'],'status':'error','error_type':'InterruptedAttempt','reason':'started work retained without implicit re-execution'})
        if output.exists() or attempt.exists():raise ValueError('orphan artifacts lack attempt ownership')
        if stop.is_set():return {'id':item['id'],'status':'pending','reason':'budget cap reached'}
        folder.mkdir(parents=True,exist_ok=True)
        write_json_atomic(started,ownership,exclusive=True)
        try:
            path=Path(item['input_path'])
            if file_hash(path)!=item['sha256']:raise ValueError('frozen input hash mismatch')
            if item['input_kind']=='ir':validate_ir(load(path))
            elif item['input_kind']!='pdf':raise ValueError('unsupported input kind')
            result=runner(path)
            if not isinstance(result,dict):raise ValueError('runner must return a result object')
            write_json_atomic(output,result,exclusive=True)
            record={'id':item['id'],'status':'completed','result_path':str(output),'result_sha256':file_hash(output)}
        except Exception as error:
            from .budget import BudgetExceeded
            if isinstance(error,BudgetExceeded):stop.set()
            record={'id':item['id'],'status':'error','error_type':type(error).__name__,'reason':str(error)[:500]}
        return finish(record)
    # A single invocation owns an output folder; the OS lock is released on process exit.
    import fcntl
    with (root/'run.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('batch already running') from None
        with ThreadPoolExecutor(max_workers=workers) as pool:records=list(pool.map(process,items))
        summary={'schema_version':'paper-batch-report/1.0','pipeline_version':config['pipeline_version'],'counts':dict(Counter(r['status'] for r in records)),'items':records}
        write_json_atomic(root/'summary.json',summary)
    return summary
