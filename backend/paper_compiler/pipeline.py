"""One shared version of the paper model and compatible generated checking passes."""
import copy,json,hashlib
from pathlib import Path
from .programs import build_program,save_program,load_program,check_programs,digest
from .model_runtime import base_model,extend_model,apply_model
from .storage import write_json_atomic
from .contracts import ir_hash

def runtime_sources():
    root=Path(__file__).resolve().parent
    return {str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob('*')) if path.is_file() and path.suffix in {'.py','.json'}}


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
    config=getattr(client,'config',{})
    execution={'semantic_model':{k:config.get(k) for k in ['MAAS_MODEL','MAAS_MODEL_VERSION']},
               'offline':client is None,'evidence_environment_sha256':digest(evidence_environment),
               'evidence_snapshot':getattr(gateway,'snapshot_id',None),'runtime_source_sha256':digest(runtime_sources())}
    report['execution_config']=execution
    report['analysis_sha256']=digest(analysis)
    report['pipeline_version']=digest({'model':model,'programs':[p['manifest']['version_id'] for p in packages],'execution':execution})
    return materialized,analysis,report

def save_suite(packages,folder,*,validated=False,validation=None,regression_cases=None):
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
    sources=runtime_sources()
    for name,expected in sources.items():
        archived=folder/'runtime'/name
        archived.parent.mkdir(parents=True,exist_ok=True)
        payload=Path(__file__).resolve().parent.joinpath(name).read_bytes()
        if archived.exists():
            if hashlib.sha256(archived.read_bytes()).hexdigest()!=expected:
                raise ValueError('suite runtime artifact is immutable')
        else:
            with archived.open('xb') as handle:handle.write(payload)
    content={'schema_version':'paper-suite/1.0','model':model,'packages':names,'runtime_source_sha256':sources,
             'program_versions':[p['manifest']['version_id'] for p in packages]}
    if regression_cases is not None:
        if not isinstance(regression_cases,list):raise ValueError('online regressions must be a list')
        content['online_regression_sha256']=digest(regression_cases)
        content['online_regression_count']=len(regression_cases)
        regression_path=folder/'online-regressions.json'
        if regression_path.exists() and json.loads(regression_path.read_text())!=regression_cases:
            raise ValueError('suite regression inventory is immutable')
        if not regression_path.exists():write_json_atomic(regression_path,regression_cases,exclusive=True)
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
    if 'runtime_source_sha256' in manifest:
        sources=manifest['runtime_source_sha256']
        if not isinstance(sources,dict) or not sources:raise ValueError('invalid runtime source manifest')
        root=(folder/'runtime').resolve()
        for name,expected in sources.items():
            if not isinstance(name,str):raise ValueError('invalid runtime artifact path')
            path=(root/name).resolve()
            if not path.is_relative_to(root) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise ValueError('suite runtime artifact hash mismatch')
        if sources!=runtime_sources():raise ValueError('suite runtime implementation mismatch')
    if 'online_regression_sha256' in manifest:
        cases=json.loads((folder/'online-regressions.json').read_text())
        if not isinstance(cases,list) or digest(cases)!=manifest['online_regression_sha256'] or len(cases)!=manifest.get('online_regression_count'):
            raise ValueError('suite regression inventory hash mismatch')
    packages=[]
    for name,version in zip(manifest['packages'],manifest['program_versions'],strict=True):
        if not isinstance(name,str) or Path(name).name!=name:raise ValueError('unsafe suite path')
        package=load_program(folder/name)
        if package['manifest']['version_id']!=version or package['model']!=manifest['model']:
            raise ValueError('incompatible suite program')
        packages.append(package)
    return packages


def release_inventory(configured,snapshot):
    """Merge the complete configured inventory with the pinned active release.

    Active definitions take precedence; newly configured rules are retained.
    A selected report subset never becomes the release inventory.
    """
    active=load_suite(snapshot['active_path']) if snapshot.get('active_path') else []
    def rid(package):
        return str(package.get('program_spec',package.get('rule_ir',{}))['rule_id'])
    active_ids={rid(p) for p in active}
    merged={rid(p):p for p in configured if rid(p) not in active_ids}
    for package in active:merged[rid(package)]=package
    packages=list(merged.values())
    generated=[p for p in packages if p['manifest'].get('schema_version')=='paper-program/2.0']
    legacy=[p for p in packages if p not in generated]
    return rebind(generated,shared_model(generated))+legacy if generated else legacy


def report_suite_version(packages,snapshot):
    if not snapshot.get('active_path'):return None
    active=load_suite(snapshot['active_path'])
    versions=sorted(p['manifest']['version_id'] for p in packages)
    return snapshot['active_version'] if versions==sorted(p['manifest']['version_id'] for p in active) else None
