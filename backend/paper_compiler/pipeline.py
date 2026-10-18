"""One shared version of the paper model and compatible generated checking passes."""
import copy,json
from pathlib import Path
from .programs import build_program,save_program,load_program,check_programs,digest
from .model_runtime import base_model,extend_model,apply_model
from .storage import write_json_atomic
from .contracts import ir_hash

def shared_model(packages):
    model=base_model()
    for package in packages:
        for kind,definition in package['model'].get('node_types',{}).items():
            old=model['node_types'].get(kind)
            if old and (old['base_kind']!=definition['base_kind'] or
                        any(k in definition['attrs'] and definition['attrs'][k]!=v for k,v in old['attrs'].items())):
                raise ValueError('incompatible shared model definitions')
        if package['model'].get('node_types'):model=extend_model(model,{'node_types':package['model']['node_types']})
    return model

def rebind(packages,model):
    result=[]
    for package in packages:
        candidate={**copy.deepcopy(package['program_spec']),'code':package['code']}
        result.append(build_program(candidate,rule_text=package['input']['rule_text'],
                                    basis=package['input']['basis'],model=model))
    return result

def detect(ir,packages,*,client,gateway,cache_dir,evidence_environment=None):
    if not packages:raise ValueError('at least one package required')
    from .program_analysis import analyze_programs
    model=shared_model(packages)
    packages=rebind(packages,model)
    materialized=apply_model(ir,model,client=client)
    analysis=analyze_programs(materialized,packages,client=client,gateway=gateway,
        cache_dir=Path(cache_dir),evidence_environment=evidence_environment)
    report=check_programs(materialized,analysis,packages)
    report['pipeline_version']=digest({'model':model,'programs':[p['manifest']['version_id'] for p in packages]})
    return materialized,analysis,report

def save_suite(packages,folder,*,validated=False,validation=None):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    model=shared_model(packages);packages=rebind(packages,model)
    names=[]
    for index,package in enumerate(packages):
        name='program-'+str(index)+'-'+package['manifest']['version_id'][:16]
        path=folder/name
        if path.exists():
            if load_program(path)['manifest']!=package['manifest']:raise ValueError('suite program changed')
        else:save_program(package,path)
        names.append(name)
    content={'schema_version':'paper-suite/1.0','model':model,'packages':names,
             'program_versions':[p['manifest']['version_id'] for p in packages]}
    manifest={**content,'version_id':digest(content)}
    target=folder/'manifest.json'
    if target.exists() and json.loads(target.read_text())!=manifest:raise ValueError('suite is immutable')
    if not target.exists():write_json_atomic(target,manifest,exclusive=True)
    if validated and not isinstance(validation,dict):raise ValueError('behavior validation record required')
    status={'status':'passed' if validated else 'not_evaluated',**(validation or {})}
    if status['status']!=('passed' if validated else 'not_evaluated'):raise ValueError('validation status mismatch')
    write_json_atomic(folder/'validation.json',status)
    return manifest

def load_suite(folder):
    folder=Path(folder);manifest=json.loads((folder/'manifest.json').read_text())
    content={k:v for k,v in manifest.items() if k!='version_id'}
    if manifest.get('schema_version')!='paper-suite/1.0' or digest(content)!=manifest.get('version_id'):
        raise ValueError('suite hash mismatch')
    packages=[]
    for name,version in zip(manifest['packages'],manifest['program_versions'],strict=True):
        if not isinstance(name,str) or Path(name).name!=name:raise ValueError('unsafe suite path')
        package=load_program(folder/name)
        if package['manifest']['version_id']!=version or package['model']!=manifest['model']:
            raise ValueError('incompatible suite program')
        packages.append(package)
    return packages
