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

def test_pipeline_version_tracks_semantic_model_configuration(tmp_path):
    class Client:
        def __init__(self,version):self.config={'MAAS_MODEL':'same-model','MAAS_MODEL_VERSION':version}
        def complete_json(self,*args):raise AssertionError('this program needs no model calls')
    pkg=build_program(candidate(),rule_text='rule',basis=[{'id':'test','text':'basis'}]);ir,_=fixture(tmp_path)
    reports=[pipeline.detect(ir,[pkg],client=Client(v),gateway=None,cache_dir=tmp_path/'cache')[2] for v in ['v1','v2']]
    assert reports[0]['pipeline_version']!=reports[1]['pipeline_version']
    assert reports[0]['analysis_sha256']

def test_plan_cli_turns_natural_language_into_a_task_without_handwritten_scope(tmp_path,monkeypatch):
    import importlib.util
    import paper_compiler.llm
    class Planner:
        config={}
        def complete_json(self,*args):
            return {'target_kinds':['BibliographyEntry'],'generation_guidance':'Generate genuine source edits and verify both labels.','evidence_environment':None}
    monkeypatch.setattr(paper_compiler.llm,'MaasClient',lambda *a,**kw:Planner())
    path=Path(__file__).resolve().parents[1]/'scripts'/'paper_compiler_cli.py'
    spec=importlib.util.spec_from_file_location('planner_cli_test',path);cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    rule=tmp_path/'rule.txt';rule.write_text('Bibliography entries require titles.')
    basis=tmp_path/'basis.json';basis.write_text(json.dumps([{'id':'norm','text':'Titles are required.'}]))
    args=cli.parser().parse_args(['plan','--rule-id','unseen-rule','--rule-text',str(rule),'--basis',str(basis),
        '--out',str(tmp_path/'plan'),'--ledger',str(tmp_path/'ledger.db'),'--cache',str(tmp_path/'cache')])
    result=cli.execute(args)
    assert result['status']=='planned'
    planned=json.loads((tmp_path/'plan'/'plan.json').read_text())
    assert planned['rule_text']==rule.read_text() and planned['target_kinds']==['BibliographyEntry']

def test_online_cli_preserves_full_release_when_requested_rule_differs_from_active_partial_suite(tmp_path):
    import subprocess,sys
    from paper_compiler.runtime_control import RuntimeControl
    programs=[]
    for rid in ['31','32','33']:
        spec=candidate();spec['rule_id']=rid
        pkg=build_program(spec,rule_text='Check entry',basis=[{'id':'test','text':'Check entry'}])
        folder=tmp_path/rid;save_program(pkg,folder);programs.append((pkg,folder))
    control=RuntimeControl(tmp_path/'control')
    active=pipeline.save_suite([programs[0][0]],tmp_path/'active',validated=True,validation={'fixture':True})
    control.promote(active['version_id'],tmp_path/'active',None,expected_generation=0);control.set_freeze(True)
    ir,_=fixture(tmp_path);source=tmp_path/'input.json';source.write_text(json.dumps(ir))
    script=Path(__file__).resolve().parents[1]/'scripts'/'paper_compiler_cli.py'
    command=[sys.executable,str(script),'check','--ir',str(source),'--out',str(tmp_path/'report.json'),
        '--package',str(programs[1][1]),'--online','--control-root',str(tmp_path/'control'),'--offline',
        '--cache',str(tmp_path/'cache'),'--ledger',str(tmp_path/'budget.sqlite3'),'--stdout-report']
    for pkg,folder in programs:command.extend(['--release-package',str(folder)])
    result=subprocess.run(command,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    report=json.loads(result.stdout)
    assert [row['rule_id'] for row in report['rules']]==['32']
    assert set(report['runtime']['release_rule_ids'])=={'31','32','33'}

def test_online_cli_bounds_all_model_stages_before_building_pdf(tmp_path,monkeypatch):
    import importlib.util
    import paper_compiler.llm,paper_compiler.frontend,paper_compiler.request_limits
    class Client:
        config={}
        def complete_json(self,*args):raise AssertionError('no real API')
    raw=Client();wrapped=Client();events=[]
    monkeypatch.setattr(paper_compiler.llm,'MaasClient',lambda *a,**kw:raw)
    def bound(client,scope_id,max_cost_cny='5',timeout_seconds=1200):
        assert client is raw and scope_id.startswith('online-task/')
        assert str(max_cost_cny)=='5' and timeout_seconds==1200
        events.append('bounded');return wrapped
    monkeypatch.setattr(paper_compiler.request_limits,'bounded_client',bound)
    ir,_=fixture(tmp_path)
    def build(*args,client=None,**kw):
        assert events==['bounded'] and client is wrapped
        events.append('pdf');return ir
    monkeypatch.setattr(paper_compiler.frontend,'build_paper',build)
    pkg=build_program(candidate(),rule_text='Entry',basis=[{'id':'test','text':'Entry'}])
    folder=tmp_path/'program';save_program(pkg,folder)
    from paper_compiler.runtime_control import RuntimeControl
    RuntimeControl(tmp_path/'control').set_freeze(True)
    path=Path(__file__).resolve().parents[1]/'scripts'/'paper_compiler_cli.py'
    spec=importlib.util.spec_from_file_location('bounded_cli_test',path);cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    args=cli.parser().parse_args(['check','--pdf',str(tmp_path/'input.pdf'),'--out',str(tmp_path/'output.json'),
        '--package',str(folder),'--online','--control-root',str(tmp_path/'control'),
        '--cache',str(tmp_path/'cache'),'--ledger',str(tmp_path/'ledger.db')])
    assert cli.execute(args)['status']=='completed'
    assert events==['bounded','pdf']
