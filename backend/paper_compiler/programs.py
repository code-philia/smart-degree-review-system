"""Versioned direct-Python checking passes, independent of the old expression DSL."""
from collections import Counter
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from .contracts import validate_ir, validate_analysis, reject_answers, ir_hash
from .storage import json_bytes, write_json_atomic
from .registry import REGISTRY
from .program_worker import validate_code, ERROR_PREFIX, ERROR_MESSAGE_LIMIT, ERROR_LINE_LIMIT, ERROR_RECORD_LIMIT

VERSION='paper-program/2.0'
STATUSES={'PASS','VIOLATION','UNKNOWN','NOT_APPLICABLE','ERROR'}

class ProgramError(ValueError):
    pass

def digest(value):
    return hashlib.sha256(json_bytes(value)).hexdigest()

def build_program(candidate, *, rule_text, basis, model=None):
    if not isinstance(candidate,dict):raise ProgramError('candidate must be an object')
    required={'rule_id','title','requires','target_kinds','code','analysis_requests','model_patch'}
    if set(candidate)!=required:raise ProgramError('candidate fields mismatch')
    if not isinstance(candidate['rule_id'],str) or not candidate['rule_id'] or not isinstance(candidate['title'],str):
        raise ProgramError('rule identity required')
    if not isinstance(candidate['requires'],list) or not all(isinstance(v,str) for v in candidate['requires']):
        raise ProgramError('invalid analysis dependencies')
    if not isinstance(candidate['target_kinds'],list) or not candidate['target_kinds'] or not all(isinstance(v,str) for v in candidate['target_kinds']):
        raise ProgramError('target kinds required')
    if not isinstance(candidate['analysis_requests'],list) or not isinstance(candidate['model_patch'],dict):
        raise ProgramError('invalid analysis or model patch')
    from .model_runtime import base_model,validate_model
    from .contracts import KINDS
    model=copy.deepcopy(model or base_model())
    validate_model(model)
    if not set(candidate['target_kinds']) <= KINDS|set(model.get('node_types',{})):
        raise ProgramError('unknown target kind')
    registry=copy.deepcopy(REGISTRY)
    requests=[]
    for request in candidate['analysis_requests']:
        if not isinstance(request,dict) or set(request)!={'name','targets','fields','instructions'}:
            raise ProgramError('invalid generated analysis contract')
        name=request['name']
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,79}',name) or name in registry['capabilities']:
            raise ProgramError('analysis name is invalid or already registered')
        if not isinstance(request['targets'],list) or not request['targets'] or not set(request['targets'])<=KINDS|set(model.get('node_types',{})):
            raise ProgramError('analysis targets invalid')
        if not isinstance(request['fields'],dict) or not request['fields'] or not all(v in {'string','number','boolean','array','object'} for v in request['fields'].values()):
            raise ProgramError('analysis fields invalid')
        if not isinstance(request['instructions'],str) or not request['instructions'].strip():
            raise ProgramError('analysis instructions required')
        registry['capabilities'][name]={'version':digest(request)[:20],'targets':request['targets'],
            'fields':request['fields'],'implementation':'grounded_semantic_extraction'}
        requests.append(copy.deepcopy(request))
    if set(candidate['requires'])-set(registry['capabilities']):
        raise ProgramError('missing analysis declaration')
    try:validate_code(candidate['code'])
    except (ValueError,SyntaxError,TypeError) as error:raise ProgramError(str(error)) from error
    inputs={'rule_text':rule_text,'basis':copy.deepcopy(basis),'registry':registry}
    spec={k:copy.deepcopy(candidate[k]) for k in ['rule_id','title','requires','target_kinds','analysis_requests','model_patch']}
    hashes={'code_sha256':hashlib.sha256(candidate['code'].encode()).hexdigest(),
            'model_sha256':digest(model),'inputs_sha256':digest(inputs),'spec_sha256':digest(spec)}
    version_id=digest({'format':VERSION,**hashes})
    manifest={'schema_version':VERSION,'version_id':version_id,**hashes,
              'model_version':model['version'],'status':'candidate_not_activated',
              'capability_versions':{n:registry['capabilities'][n]['version'] for n in spec['requires']}}
    return {'program_spec':spec,'rule_ir':{'schema_version':'rule-program/2.0',
        'rule_id':spec['rule_id'],'title':spec['title'],'requires':spec['requires'],
        'checks':[{'target_kind':k} for k in spec['target_kinds']]},
        'code':candidate['code'],'model':model,'manifest':manifest,'input':inputs,'registry':registry}

def verify_program(package):
    manifest=package['manifest']
    if manifest.get('schema_version')!=VERSION:raise ProgramError('unsupported program format')
    hashes={'code_sha256':hashlib.sha256(package['code'].encode()).hexdigest(),
        'model_sha256':digest(package['model']),'inputs_sha256':digest(package['input']),
        'spec_sha256':digest(package['program_spec'])}
    if any(manifest.get(k)!=v for k,v in hashes.items()) or manifest.get('version_id')!=digest({'format':VERSION,**hashes}):
        raise ProgramError('program package hash mismatch')
    from .model_runtime import validate_model
    validate_model(package['model'])
    if manifest.get('model_version')!=package['model']['version']:raise ProgramError('manifest model version mismatch')
    expected_caps={n:package['input']['registry']['capabilities'][n]['version'] for n in package['program_spec']['requires']}
    if manifest.get('capability_versions')!=expected_caps or package['registry']!=package['input']['registry']:
        raise ProgramError('manifest capability contract mismatch')
    try:validate_code(package['code'])
    except (ValueError,SyntaxError,TypeError) as error:raise ProgramError(str(error)) from error

def save_program(package, path):
    verify_program(package)
    path=Path(path);path.mkdir(parents=True,exist_ok=True)
    for name,key in [('input.json','input'),('program-spec.json','program_spec'),('model.json','model'),('manifest.json','manifest')]:
        write_json_atomic(path/name,package[key],exclusive=True)
    with (path/'checks.py').open('x') as stream:stream.write(package['code'])
    write_json_atomic(path/'validation.json',{'status':'syntax_passed','behavior':'not_yet_evaluated'},exclusive=True)

def load_program(path):
    path=Path(path)
    manifest=json.loads((path/'manifest.json').read_text())
    inputs=json.loads((path/'input.json').read_text())
    spec=json.loads((path/'program-spec.json').read_text())
    package={'manifest':manifest,'input':inputs,'registry':inputs['registry'],
        'program_spec':spec,'code':(path/'checks.py').read_text(),'model':json.loads((path/'model.json').read_text()),
        'rule_ir':{'schema_version':'rule-program/2.0','rule_id':spec['rule_id'],'title':spec['title'],
                   'requires':spec['requires'],'checks':[{'target_kind':k} for k in spec['target_kinds']]}}
    verify_program(package)
    return package


def _worker_error_reason(stderr,code):
    if not isinstance(stderr,bytes) or not stderr.endswith(b'\n'):return None
    line=stderr[-(ERROR_RECORD_LIMIT+2):][:-1].rsplit(b'\n',1)[-1]
    prefix=ERROR_PREFIX.encode('ascii')
    if len(line)>ERROR_RECORD_LIMIT or not line.startswith(prefix):return None
    def unique_object(pairs):
        if len({key for key,_ in pairs})!=len(pairs):raise ValueError('duplicate error field')
        return dict(pairs)
    try:record=json.loads(line[len(prefix):].decode('utf-8'),object_pairs_hook=unique_object)
    except (ValueError,UnicodeError):return None
    if not isinstance(record,dict) or set(record)!={'type','message','generated_lines'}:return None
    name,message,lines=record['type'],record['message'],record['generated_lines']
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}',name):return None
    if not isinstance(message,str) or len(message)>ERROR_MESSAGE_LIMIT:return None
    if (not isinstance(lines,list) or len(lines)>ERROR_LINE_LIMIT or
            any(type(n) is not int or not 1<=n<=len(code.splitlines()) for n in lines)):
        return None
    if lines!=sorted(set(lines)):return None
    location=' at <paper-program> lines '+','.join(str(n) for n in lines) if lines else ''
    return name+location+': '+message


def execute_pure(code,payload,entry='detect'):
    reject_answers(payload)
    try:validate_code(code,entry)
    except (ValueError,SyntaxError,TypeError) as error:raise ProgramError(str(error)) from error
    request=json_bytes({'code':code,'payload':payload,'entry':entry})
    if len(request)>32*1024*1024:raise ProgramError('program input exceeds limit')
    try:
        process=subprocess.run([sys.executable,str(Path(__file__).with_name('program_worker.py'))],
            input=request,capture_output=True,timeout=12,
            env={'PATH':os.defpath,'PYTHONIOENCODING':'utf-8','LANG':'C.UTF-8'})
    except (subprocess.TimeoutExpired,OSError) as error:raise ProgramError('isolated execution timed out or unavailable') from error
    if len(process.stdout)>8*1024*1024:raise ProgramError('isolated program rejected')
    if process.returncode:
        reason=_worker_error_reason(process.stderr,code) if process.returncode==2 else None
        raise ProgramError('isolated program rejected'+(': '+reason if reason is not None else ''))
    try:return json.loads(process.stdout)
    except (ValueError,UnicodeError) as error:raise ProgramError('invalid program output') from error

def target_nodes(package,ir):
    from .program_worker import nodes
    found={}
    for kind in package['program_spec']['target_kinds']:
        for node in nodes({'ir':ir},kind):found[node['id']]=node
    return found

def run_program(package,ir,analysis):
    verify_program(package);validate_ir(ir);validate_analysis(ir,analysis)
    if ir['model_version']!=package['manifest']['model_version']:raise ProgramError('incompatible paper model version')
    for name,version in package['manifest']['capability_versions'].items():
        if analysis['capability_versions'].get(name)!=version:raise ProgramError('stale analysis capability version: '+name)
    types={'string':str,'number':(int,float),'boolean':bool,'array':list,'object':dict}
    for name in package['program_spec']['requires']:
        fields=package['registry']['capabilities'][name]['fields']
        for facts in analysis['results'].get(name,{}).values():
            for field,observation in facts.items():
                if field not in fields:raise ProgramError('unknown analysis field type: '+name+'.'+field)
                if observation.get('state')=='observed':
                    value=observation.get('value');kind=fields[field]
                    if kind not in types or not isinstance(value,types[kind]) or (kind=='number' and isinstance(value,bool)):
                        raise ProgramError('analysis field type mismatch: '+name+'.'+field)
    from .runtime import _evidence_check
    _evidence_check(ir,analysis)
    compact=copy.deepcopy({key:value for key,value in ir.items() if key!='layout'})
    compact['layout']={'pages':[{k:v for k,v in p.items() if k in {'page_index','width','height','rotation'}}
                                for p in ir.get('layout',{}).get('pages',[])]}
    rows=execute_pure(package['code'],{'ir':compact,'analysis':analysis})
    if not isinstance(rows,list) or len(rows)>50000:raise ProgramError('diagnostics must be a bounded list')
    targets=target_nodes(package,ir)
    basis_ids={b['id'] for b in package['input']['basis']}
    evidence_ids={n['id'] for n in ir['nodes']}|{e['id'] for e in analysis.get('evidence',[])}
    output=[];seen=set()
    for row in rows:
        if not isinstance(row,dict) or row.get('node_id') not in targets or row.get('status') not in STATUSES:
            raise ProgramError('invalid diagnostic target or status')
        if not isinstance(row.get('check_id'),str) or not row['check_id'] or not isinstance(row.get('message'),str):
            raise ProgramError('diagnostic identity and message required')
        if not isinstance(row.get('basis',[]),list) or not set(row.get('basis',[]))<=basis_ids:
            raise ProgramError('unknown diagnostic basis')
        if not isinstance(row.get('evidence_ids',[]),list) or not set(row.get('evidence_ids',[]))<=evidence_ids:
            raise ProgramError('unknown diagnostic evidence')
        if row['status'] in {'PASS','VIOLATION'} and not row.get('evidence_ids'):
            raise ProgramError('conclusive diagnostic requires evidence')
        node=targets[row['node_id']]
        output.append({**row,'rule_id':package['program_spec']['rule_id'],
                       'provenance':copy.deepcopy(node['provenance']),'reasons':row.get('reasons',[])})
        seen.add(node['id'])
    for node_id in targets.keys()-seen:
        output.append({'rule_id':package['program_spec']['rule_id'],'node_id':node_id,
            'check_id':'coverage','status':'UNKNOWN','message':'Program did not check this target',
            'basis':[],'evidence_ids':[],'reasons':['missing_target_diagnostic'],
            'provenance':copy.deepcopy(targets[node_id]['provenance'])})
    return output

def check_programs(ir,analysis,packages):
    validate_ir(ir);validate_analysis(ir,analysis);rules=[]
    for package in packages:
        spec=package['program_spec'];rows=run_program(package,ir,analysis)
        counts=Counter(r['status'] for r in rows)
        scopes={{'BibliographyEntry':'bibliography','ReferenceUse':'reference_uses','CitationGroup':'reference_uses'}.get(k,k)
                for k in spec['target_kinds']}
        gaps=[s for s in sorted(scopes) if ir['coverage'].get(s,{}).get('status')!='complete']
        if counts['ERROR']:status='ERROR'
        elif counts['VIOLATION']:status='VIOLATION'
        elif counts['UNKNOWN'] or gaps or not rows:status='UNKNOWN'
        elif counts['PASS']:status='PASS'
        else:status='NOT_APPLICABLE'
        rules.append({'rule_id':spec['rule_id'],'title':spec['title'],'status':status,
            'counts':dict(counts),'results':rows,'basis_catalog':package['input']['basis'],
            'coverage':{'incomplete_scopes':gaps},'package_sha256':digest(package['manifest']),
            'program_version':package['manifest']['version_id'],'model_version':ir['model_version']})
    return {'schema_version':'paper-check/1.0','document_id':ir['document_id'],'paper_ir_sha256':ir_hash(ir),
        'rules':rules,'evidence':analysis.get('evidence',[]),'bindings':analysis.get('bindings',[]),
        'coverage':ir['coverage']}
