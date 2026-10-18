"""Initial capability synthesis is gated by independent cases and pure execution."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from .capability_worker import validate_code
from .storage import json_bytes, write_json_atomic


class CapabilityError(ValueError):
    pass


def _validate_result(result,fields):
    if not isinstance(result,dict) or set(result)!=set(fields):raise CapabilityError('candidate output fields mismatch')
    types={'string':str,'number':(int,float),'boolean':bool,'array':list,'object':dict}
    for key,typ in fields.items():
        if typ not in types or not isinstance(result[key],types[typ]) or (typ=='number' and isinstance(result[key],bool)):
            raise CapabilityError('candidate output type mismatch')


def _execute(code,payload,fields):
    try:validate_code(code)
    except (SyntaxError,ValueError):raise CapabilityError('candidate rejected by code policy') from None
    data=json_bytes({'code':code,'payload':payload})
    if len(data)>256*1024:raise CapabilityError('candidate input too large')
    base=Path('/data/tmp/paper-compiler-capabilities') if os.name!='nt' else Path(tempfile.gettempdir())/'paper-compiler-capabilities'
    base.mkdir(parents=True,exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(dir=base) as directory:
            result=subprocess.run([sys.executable,'-I',str(Path(__file__).with_name('capability_worker.py'))],
                input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=4,cwd=directory,
                env={'PATH':str(Path(sys.executable).parent),'PYTHONUTF8':'1'})
    except subprocess.TimeoutExpired:raise CapabilityError('candidate exceeded execution time limit') from None
    if result.returncode!=0 or len(result.stdout)>128*1024:raise CapabilityError('candidate isolated execution failed')
    try:output=json.loads(result.stdout)
    except (ValueError,UnicodeError):raise CapabilityError('invalid candidate result') from None
    _validate_result(output,fields)
    return output


def run_capability(capability: dict, payload: dict) -> dict:
    path=Path(capability['code_path'])
    code=path.read_text(encoding='utf-8')
    if hashlib.sha256(code.encode()).hexdigest()!=capability['code_sha256']:
        raise CapabilityError('capability code hash mismatch')
    return _execute(code,payload,capability['fields'])


def ensure_capabilities(requests: list[dict], registry: dict, client, output_dir: Path, *, max_attempts=2) -> dict:
    from .contracts import KINDS
    from .capability_worker import ALLOWED_CALLS, ALLOWED_METHODS
    if type(max_attempts)is not int or not 1<=max_attempts<=3:raise CapabilityError('invalid generation attempt limit')
    updated=copy.deepcopy(registry);output_dir=Path(output_dir)
    for request in requests:
        name=request['name']
        if name in updated['capabilities']:continue
        if not name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in name):raise CapabilityError('invalid capability name')
        if not request.get('targets') or any(t not in KINDS for t in request['targets']):raise CapabilityError('invalid target type')
        if not request.get('fields') or any(t not in {'string','number','boolean','array','object'} for t in request['fields'].values()):raise CapabilityError('invalid field type')
        cases=request.get('validation_cases')
        if not isinstance(cases,list) or len(cases)<3:raise CapabilityError('independent validation cases are required; candidate remains unregistered')
        disclosed={k:v for k,v in request.items() if k!='validation_cases'}
        instructions="""Generate a pure analysis capability for the stated contract.
Return JSON with exactly name, targets, fields and code. Code defines one function analyze(payload), returning the declared fields.
Input is JSON {node: {...}, facts: {...}}. Allowed builtins and methods are listed in policy. Use only these names/methods.
No imports, files, network, shell, introspection, decorators, exceptions, recursion, globals or while loops. No private attributes.
Implement the general transformation; do not return placeholder constants. Validation examples and answers are withheld.
"""
        folder=output_dir/name;folder.mkdir(parents=True,exist_ok=True);last_error=None
        for attempt in range(1,max_attempts+1):
            attempt_dir=folder/('attempt-'+str(attempt));attempt_dir.mkdir(parents=True,exist_ok=True)
            candidate=client.complete_json('capability-builder/1.1',instructions,{'request':disclosed,
                'policy':{'builtins':sorted(ALLOWED_CALLS),'methods':sorted(ALLOWED_METHODS)},'previous_failure':last_error},4096)
            write_json_atomic(attempt_dir/'candidate.json',candidate,exclusive=True);results=[]
            try:
                if set(candidate)!={'name','targets','fields','code'} or any(candidate[k]!=request[k] for k in ['name','targets','fields']):raise CapabilityError('candidate contract mismatch')
                for index,case in enumerate(cases):
                    actual=_execute(candidate['code'],case['input'],candidate['fields']);passed=actual==case['output']
                    results.append({'case':index,'passed':passed})
                    if not passed:raise CapabilityError('independent validation failed')
            except CapabilityError as error:
                last_error=str(error)
                write_json_atomic(attempt_dir/'validation.json',{'status':'failed','reason':last_error,'cases':results},exclusive=True)
                if attempt==max_attempts:
                    write_json_atomic(folder/'validation.json',{'status':'failed','attempts':attempt,'reason':last_error},exclusive=True)
                    raise
                continue
            write_json_atomic(attempt_dir/'validation.json',{'status':'passed','cases':results},exclusive=True)
            break
        digest=hashlib.sha256(candidate['code'].encode()).hexdigest();code_path=folder/'analyze.py'
        with code_path.open('x',encoding='utf-8') as stream:stream.write(candidate['code'])
        cap={'version':digest[:16],'targets':candidate['targets'],'fields':candidate['fields'],
            'implementation':'isolated_pure_python','code_path':str(code_path.resolve()),'code_sha256':digest,
            'validation':{'passed':len(results),'independent_cases_sha256':hashlib.sha256(json_bytes(cases)).hexdigest()}}
        write_json_atomic(folder/'candidate.json',candidate,exclusive=True)
        write_json_atomic(folder/'validation.json',{'status':'passed','attempts':attempt,'cases':results},exclusive=True)
        updated['capabilities'][name]=cap
    updated['version']='registry/'+hashlib.sha256(json_bytes(updated['capabilities'])).hexdigest()[:16]
    write_json_atomic(output_dir/'registry.json',updated,exclusive=True)
    return updated
