import copy,json
from pathlib import Path
import pytest
from paper_compiler import pipeline
from paper_compiler.programs import build_program,save_program
from paper_compiler.model_runtime import base_model
from test_paper_compiler_programs import candidate
from test_paper_compiler_compiler import fixture

def test_direct_package_dispatch_and_source_mutation(tmp_path):
    pkg=build_program(candidate(),rule_text='title required',basis=[{'id':'test','text':'title required'}])
    folder=tmp_path/'program';save_program(pkg,folder)
    from paper_compiler.runtime import load_package
    assert load_package(folder)['manifest']['schema_version']=='paper-program/2.0'
    ir,_=fixture(tmp_path)
    materialized,analysis,report=pipeline.detect(ir,[pkg],client=None,gateway=None,cache_dir=tmp_path/'cache')
    assert report['rules'][0]['results'][0]['status']=='PASS'
    assert report['pipeline_version']
    assert materialized['model_version']==pkg['model']['version']

def test_suite_freezes_hashes_and_requires_behavior_for_activation(tmp_path):
    pkg=build_program(candidate(),rule_text='title required',basis=[{'id':'test','text':'title required'}])
    folder=tmp_path/'suite'
    manifest=pipeline.save_suite([pkg],folder)
    assert json.loads((folder/'validation.json').read_text())['status']!='passed'
    assert pipeline.load_suite(folder)[0]['manifest']['version_id']==pkg['manifest']['version_id']
    code=folder/manifest['packages'][0]/'checks.py';code.write_text(code.read_text()+'\n# altered')
    with pytest.raises(ValueError):pipeline.load_suite(folder)

def test_control_cli_does_not_require_model_config(tmp_path):
    import subprocess,sys
    script=Path(__file__).resolve().parents[1]/'scripts'/'paper_compiler_cli.py'
    def invoke(action):
        p=subprocess.run([sys.executable,str(script),'control','--action',action,'--control-root',str(tmp_path/'control')],capture_output=True,text=True)
        assert p.returncode==0,p.stdout+p.stderr
        return json.loads(p.stdout)
    assert invoke('status')['freeze'] is False
    assert invoke('freeze')['freeze'] is True
    assert invoke('unfreeze')['freeze'] is False
    assert len(invoke('history')['events'])==2

def test_shared_model_merges_extension_dependencies_independent_of_key_order():
    from paper_compiler.model_runtime import base_model,extend_model
    model=extend_model(base_model(),{'node_types':{
        'Method':{'base_kind':'Section','description':'method','attrs':{}},
        'Experiment':{'base_kind':'Method','description':'experimental method','attrs':{}}}})
    pkg=build_program(candidate(),rule_text='rule',basis=[],model=model)
    pkg['model']=json.loads(json.dumps(pkg['model'],sort_keys=True))
    assert pipeline.shared_model([pkg])==model

def test_check_cli_loads_direct_program_with_frozen_runtime_snapshot(tmp_path):
    import subprocess,sys
    from paper_compiler.runtime_control import RuntimeControl
    pkg=build_program(candidate(),rule_text='rule',basis=[{'id':'test','text':'basis'}])
    folder=tmp_path/'program';save_program(pkg,folder)
    ir,_=fixture(tmp_path);source=tmp_path/'input.json';source.write_text(json.dumps(ir))
    control_root=tmp_path/'control';RuntimeControl(control_root).set_freeze(True)
    script=Path(__file__).resolve().parents[1]/'scripts'/'paper_compiler_cli.py'
    p=subprocess.run([sys.executable,str(script),'check','--ir',str(source),'--out',str(tmp_path/'result.json'),
        '--package',str(folder),'--online','--control-root',str(control_root),'--offline',
        '--ledger',str(tmp_path/'ledger.sqlite3'),'--cache',str(tmp_path/'cache'),'--stdout-report'],
        capture_output=True,text=True)
    assert p.returncode==0,p.stdout+p.stderr
    report=json.loads(p.stdout)
    assert report['runtime']['freeze'] is True and report['runtime']['generation']==1
    assert report['rules'][0]['results'][0]['status']=='PASS'
    assert report['pipeline_version']
