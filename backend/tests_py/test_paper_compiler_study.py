import copy
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from paper_compiler.analysis import base_analysis
from paper_compiler.budget import BudgetExceeded, BudgetLedger
from paper_compiler.contracts import ir_hash
from paper_compiler.model_runtime import base_model, extend_model
from paper_compiler.mutations import mutate
from paper_compiler.programs import check_programs, load_program
from paper_compiler.storage import write_json_atomic
from test_paper_compiler_compiler import fixture


OLD="def detect(payload):\n    return [emit(n,'PASS','Initial','check',['req']) for n in nodes(payload,'BibliographyEntry')]\n"
FIX="def detect(payload):\n    return [emit(n,'PASS' if 'Hello' in n['text'] else 'VIOLATION','Checked','check',['req']) for n in nodes(payload,'BibliographyEntry')]\n"


def api():
    assert importlib.util.find_spec('paper_compiler.study') is not None, 'fair study orchestration is missing'
    return importlib.import_module('paper_compiler.study').run_study


def candidate(rid,code=OLD,patch=None,requests=None):
    return {'rule_id':rid,'title':'Source term','requires':[], 'target_kinds':['BibliographyEntry'],
            'code':code,'analysis_requests':requests or [],'model_patch':patch or {}}


def benchmark(tmp_path,rule_ids=('alpha','beta')):
    cases=[];hashes={};groups={};split_by_doc={}
    tasks=[{'rule_id':rid,'rule_text':'Entries must contain Hello.',
            'basis':[{'id':'req','text':'The required source term is Hello.'}]} for rid in rule_ids]
    for split in ['feedback','validation','test']:
        folder=tmp_path/split;folder.mkdir()
        ir,_=fixture(folder)
        source=Path(ir['source_artifacts'][0]['path'])
        source.write_text('Hello [1] '+split,encoding='utf-8')
        ir['source_artifacts'][0]['sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
        ir['document_id']='doc-'+hashlib.sha256(split.encode()).hexdigest()[:12]
        split_by_doc[ir['document_id']]=split
        group='parent-'+split;groups[group]={'split':split}
        original=folder/'original.json';write_json_atomic(original,ir)
        for rid in rule_ids:
            for label,replacement in [('VIOLATION','Wrong'),('PASS','Hello.')]:
                changed,_=mutate(ir,{'mutation_id':rid+'-'+split+'-'+label,'parent_sha256':ir_hash(ir),
                    'operation':'replace_text','node_id':'entry','start':0,'end':5,'old_text':'Hello',
                    'replacement':replacement,'rule_id':rid,'status':label})
                cid=rid+'-'+split+'-'+label
                ip=folder/(cid+'.json');op=folder/(cid+'-oracle.json')
                write_json_atomic(ip,changed)
                write_json_atomic(op,{'valid':True,'status':label,'target_node_id':'entry','mutation_type':'source-replacement'})
                cases.append({'id':cid,'rule_id':rid,'parent_group':group,'split':split,'ir_path':str(ip),
                    'original_ir_path':str(original),'oracle_path':str(op),'target_node_id':'entry',
                    'context_origin':'constructed' if rid==rule_ids[-1] else 'real','evidence_domain':'open',
                    'mutation_type':'source-replacement'})
                for path in [original,ip,op]:hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    manifest=tmp_path/'manifest.json'
    write_json_atomic(manifest,{'schema_version':'paper-benchmark/2.0','status':'complete','cases':cases,
                              'groups':groups,'artifact_sha256':hashes})
    return tasks,manifest,split_by_doc


class Model:
    config={'MAAS_MODEL':'fake','MAAS_MODEL_VERSION':'study-v1'}
    def __init__(self,*,invalid_initial=False,analysis_change=False,budget_after=None):
        self.requests=[];self.invalid_initial=invalid_initial;self.analysis_change=analysis_change
        self.budget_after=budget_after
    def complete_json(self,task,instructions,data,max_tokens):
        assert task=='paper-program-synthesis/2.0'
        if self.budget_after is not None and len(self.requests)>=self.budget_after:raise BudgetExceeded('test cumulative budget exhausted')
        self.requests.append(copy.deepcopy(data))
        rid=data['requested_rule_id'];initial=not data.get('feedback')
        if initial and self.invalid_initial:return candidate(rid,"def detect(payload):\n    while True:\n        pass")
        if not initial and self.analysis_change:
            return candidate(rid,FIX,requests=[{'name':'new_fact','targets':['BibliographyEntry'],
                'fields':{'x':'string'},'instructions':'Read the exact supplied source.'}])
        return candidate(rid,OLD if initial else FIX)


def runner_for(out,splits,calls):
    def run(package,ir):
        split=splits[ir['document_id']]
        if split=='test':assert (out/'selection-frozen.json').is_file(), 'heldout ran before all suite selections were frozen'
        calls.append((package['program_spec']['rule_id'],split,package['manifest']['version_id']))
        from paper_compiler.model_runtime import apply_model
        materialized=apply_model(ir,package['model'])
        return check_programs(materialized,base_analysis(materialized),[package])
    run.study_fingerprint='source-fixture-runner/1'
    return run


def test_conditions_share_one_initial_generation_and_test_only_after_selection_freeze(tmp_path):
    tasks,manifest,splits=benchmark(tmp_path);out=tmp_path/'study';calls=[];model=Model()
    result=api()(tasks,manifest,client=model,output_dir=out,runner=runner_for(out,splits,calls),max_rounds=2)
    assert result['status']=='completed'
    initial=[d for d in model.requests if not d['feedback']]
    assert [d['requested_rule_id'] for d in initial]==['alpha','beta']
    assert len(model.requests)==6
    frozen=json.loads((out/'selection-frozen.json').read_text())
    assert set(frozen['conditions'])=={'joint','program_only'}
    for rid in ['alpha','beta']:
        a=result['conditions']['joint']['rules'][rid]
        b=result['conditions']['program_only']['rules'][rid]
        assert a['initial_version']==b['initial_version']
        assert a['final_test']['metrics']['cases']==b['final_test']['metrics']['cases']==2
        assert a['baseline_test']['metrics']['strict_balanced_accuracy']==.5
        assert a['final_test']['metrics']['strict_balanced_accuracy']==1
        assert a['final_test']['groups']['context_origin']
    prompts=json.dumps(model.requests)
    assert '-validation-' not in prompts and '-test-' not in prompts
    assert len(calls)>0


def test_program_only_cannot_change_the_initial_generated_analysis_contract(tmp_path):
    tasks,manifest,splits=benchmark(tmp_path,('only',));out=tmp_path/'study';calls=[]
    result=api()(tasks,manifest,client=Model(analysis_change=True),output_dir=out,
                 runner=runner_for(out,splits,calls),max_rounds=2)
    record=result['conditions']['program_only']['rules']['only']
    assert record['final_test']['metrics']['strict_balanced_accuracy']==.5
    assert record['rounds'][1]['status']=='candidate_failed'
    assert any('fixed' in f.get('reason','').lower() for f in record['rounds'][1]['failures'])


def test_invalid_initial_is_shared_and_counts_as_round_zero_before_repair(tmp_path):
    tasks,manifest,splits=benchmark(tmp_path,('only',));out=tmp_path/'study';calls=[];model=Model(invalid_initial=True)
    result=api()(tasks,manifest,client=model,output_dir=out,runner=runner_for(out,splits,calls),max_rounds=2)
    assert len([d for d in model.requests if not d['feedback']])==1
    for condition in ['joint','program_only']:
        record=result['conditions'][condition]['rules']['only']
        assert record['rounds'][0]['status']=='candidate_failed' and record['rounds_completed']==2
        assert record['baseline_test']['metrics']['errors']==2
        assert record['final_test']['metrics']['strict_balanced_accuracy']==1


def test_cross_rule_model_regression_rejects_the_locally_repaired_candidate(tmp_path):
    tasks,manifest,splits=benchmark(tmp_path);out=tmp_path/'study';calls=[]
    class ChangesModel(Model):
        def complete_json(self,task,instructions,data,max_tokens):
            answer=super().complete_json(task,instructions,data,max_tokens)
            if data['feedback'] and data['requested_rule_id']=='beta' and data['allow_model_refinement']:
                answer['model_patch']={'node_types':{'Method':{'base_kind':'Section','description':'A method section.','attrs':{}}}}
            return answer
    base_runner=runner_for(out,splits,calls)
    def run(package,ir):
        report=base_runner(package,ir)
        if package['program_spec']['rule_id']=='alpha' and 'Method' in package['model']['node_types']:
            for row in report['rules'][0]['results']:row['status']='UNKNOWN'
        return report
    result=api()(tasks,manifest,client=ChangesModel(),output_dir=out,runner=run,max_rounds=2)
    beta=result['conditions']['joint']['rules']['beta']
    assert beta['final_test']['metrics']['strict_balanced_accuracy']==.5
    rejected=beta['rounds'][1]['cross_rule_validation']
    assert rejected['passed'] is False
    assert any('cross_rule_regression' in f['failure_types'] for f in rejected['failures'])
    assert all('-feedback-' in f['id'] for f in rejected['failures'])


def test_frozen_artifact_tampering_is_rejected_before_api_or_heldout(tmp_path):
    tasks,manifest,splits=benchmark(tmp_path,('only',));out=tmp_path/'study';calls=[];model=Model()
    run=runner_for(out,splits,calls)
    api()(tasks,manifest,client=model,output_dir=out,runner=run,max_rounds=2)
    value=json.loads(manifest.read_text());target=Path(value['cases'][0]['ir_path'])
    changed=json.loads(target.read_text());changed['revision']='tampered';write_json_atomic(target,changed)
    before=len(model.requests)
    with pytest.raises(ValueError,match='frozen|hash|integrity'):
        api()(tasks,manifest,client=model,output_dir=out,runner=run,max_rounds=2)
    assert len(model.requests)==before


def test_shared_source_cannot_hide_in_different_parent_group_splits(tmp_path):
    tasks,manifest,splits=benchmark(tmp_path,('only',));value=json.loads(manifest.read_text())
    feedback=json.loads(Path(value['cases'][0]['original_ir_path']).read_text())
    validation_case=next(c for c in value['cases'] if c['split']=='validation')
    for field in ['ir_path','original_ir_path']:
        path=Path(validation_case[field]);ir=json.loads(path.read_text());ir['source_artifacts']=copy.deepcopy(feedback['source_artifacts'])
        write_json_atomic(path,ir);value['artifact_sha256'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    write_json_atomic(manifest,value);model=Model()
    with pytest.raises(ValueError,match='source|parent|split'):
        api()(tasks,manifest,client=model,output_dir=tmp_path/'study',runner=lambda p,ir:{},max_rounds=2)
    assert model.requests==[]


def test_budget_stop_saves_incomplete_checkpoint_and_does_not_test(tmp_path):
    tasks,manifest,splits=benchmark(tmp_path,('only',));out=tmp_path/'study';calls=[];model=Model(budget_after=1)
    model.ledger=BudgetLedger(tmp_path/'existing-budget.sqlite3',200)
    model.ledger.reserve('prior-real-charge','.5','framework-20261019',200)
    model.ledger.settle('prior-real-charge',{'prompt_tokens':10,'completion_tokens':5},'.1')
    result=api()(tasks,manifest,client=model,output_dir=out,runner=runner_for(out,splits,calls),max_rounds=2)
    assert result['status']=='incomplete' and 'budget' in result['stop_reason']
    assert not any(split=='test' for _,split,_ in calls)
    assert (out/'checkpoint.json').is_file()
    assert result['budget']['spent_cny']=='0.100000' and result['budget']['requests']==1


def test_configured_shared_initial_model_is_used_by_all_initial_generations(tmp_path):
    tasks,manifest,splits=benchmark(tmp_path);out=tmp_path/'study';model=Model();calls=[]
    initial=extend_model(base_model(),{'node_types':{'Method':{'base_kind':'Section','description':'A source-supported method.','attrs':{}}}})
    result=api()(tasks,manifest,client=model,output_dir=out,runner=runner_for(out,splits,calls),max_rounds=2,initial_model=initial)
    assert all(d['paper_model']==initial for d in model.requests if not d['feedback'])
    assert result['initial_model_version']==initial['version']


def test_study_cli_help_is_available_without_instantiating_a_paid_client():
    script=Path(__file__).resolve().parents[1]/'scripts'/'run_paper_compiler_study.py'
    assert script.is_file(), 'study CLI is missing'
    process=subprocess.run([sys.executable,str(script),'--help'],capture_output=True,text=True)
    assert process.returncode==0
    for flag in ['--tasks','--manifest','--resources','--out','--config','--ledger','--budget','--cache','--paper-model']:
        assert flag in process.stdout


def test_accepted_model_semantic_revision_is_retained_in_the_final_shared_suite(tmp_path):
    from paper_compiler.pipeline import load_suite
    tasks,manifest,splits=benchmark(tmp_path);out=tmp_path/'study';calls=[]
    initial=extend_model(base_model(),{'node_types':{'Method':{'base_kind':'Section','description':'Original method semantics.','attrs':{}}}})
    class RevisesDescription(Model):
        def complete_json(self,task,instructions,data,max_tokens):
            answer=super().complete_json(task,instructions,data,max_tokens)
            if data['feedback'] and data['requested_rule_id']=='alpha' and data['allow_model_refinement']:
                answer['model_patch']={'node_types':{'Method':{'description':'Revised source-supported method semantics.'}}}
            return answer
    result=api()(tasks,manifest,client=RevisesDescription(),output_dir=out,
                 runner=runner_for(out,splits,calls),max_rounds=2,initial_model=initial)
    joint=load_suite(result['conditions']['joint']['suite_path'])
    fixed=load_suite(result['conditions']['program_only']['suite_path'])
    assert all(p['model']['node_types']['Method']['description']=='Revised source-supported method semantics.' for p in joint)
    assert all(p['model']['node_types']['Method']['description']=='Original method semantics.' for p in fixed)


def test_invalid_initial_model_patch_remains_a_failed_round_zero_in_both_conditions(tmp_path):
    tasks,manifest,splits=benchmark(tmp_path,('only',));out=tmp_path/'study';calls=[]
    class InvalidInitialPatch(Model):
        def complete_json(self,task,instructions,data,max_tokens):
            answer=super().complete_json(task,instructions,data,max_tokens)
            if not data['feedback']:
                answer['model_patch']={'node_types':{'Method':{'base_kind':'MissingBase','description':'Invalid type.','attrs':{}}}}
            return answer
    result=api()(tasks,manifest,client=InvalidInitialPatch(),output_dir=out,
                 runner=runner_for(out,splits,calls),max_rounds=2)
    for condition in ['joint','program_only']:
        record=result['conditions'][condition]['rules']['only']
        assert record['rounds'][0]['status']=='candidate_failed'
        assert record['baseline_test']['metrics']['errors']==2


def test_completed_study_rejects_tampered_frozen_suite_artifacts_without_more_calls(tmp_path):
    tasks,manifest,splits=benchmark(tmp_path,('only',));out=tmp_path/'study';calls=[];model=Model()
    run=runner_for(out,splits,calls)
    result=api()(tasks,manifest,client=model,output_dir=out,runner=run,max_rounds=2)
    suite=Path(result['conditions']['joint']['suite_path'])
    code=next(suite.glob('program-*/checks.py'))
    code.write_text(OLD)
    before=len(model.requests)
    with pytest.raises(ValueError,match='frozen|hash|integrity'):
        api()(tasks,manifest,client=model,output_dir=out,runner=run,max_rounds=2)
    assert len(model.requests)==before


def test_reported_initial_model_is_the_actual_common_initial_ontology(tmp_path):
    tasks,manifest,splits=benchmark(tmp_path,('only',));out=tmp_path/'study';calls=[]
    class ExtendsAtInitial(Model):
        def complete_json(self,task,instructions,data,max_tokens):
            answer=super().complete_json(task,instructions,data,max_tokens)
            if not data['feedback']:
                answer['model_patch']={'node_types':{'Method':{'base_kind':'Section','description':'Initial source method.','attrs':{}}}}
            return answer
    result=api()(tasks,manifest,client=ExtendsAtInitial(),output_dir=out,
                 runner=runner_for(out,splits,calls),max_rounds=2)
    shared=json.loads((out/'shared-initial.json').read_text())['model']
    assert result['initial_model_version']==shared['version']
    assert result['configured_model_version']=='paper-model/1.0'


def test_cli_uses_one_metered_client_and_task_data_for_evidence_environment(tmp_path,monkeypatch):
    import argparse
    import importlib.util
    import paper_compiler.llm as llm
    import paper_compiler.evidence as evidence
    import paper_compiler.pipeline as pipeline
    import paper_compiler.study as study
    script=Path(__file__).resolve().parents[1]/'scripts'/'run_paper_compiler_study.py'
    spec=importlib.util.spec_from_file_location('study_cli_for_test',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    task_path=tmp_path/'tasks.json';manifest_path=tmp_path/'manifest.json';resources_path=tmp_path/'resources.json'
    tasks=[{'rule_id':'arbitrary-X','evidence_environment':'controlled_catalog'},
           {'rule_id':'arbitrary-Y','evidence_environment':'open'}]
    environment={'domain':'controlled_catalog','catalog':[]}
    write_json_atomic(task_path,tasks);write_json_atomic(manifest_path,{'frozen':'input'})
    write_json_atomic(resources_path,{'evidence_environment':environment,'evidence_snapshot':'fixed-evidence'})
    captured={'environments':[]}
    class FakeClient:
        def __init__(self,config,ledger,cache,phase,phase_limit_cny,**kwargs):
            captured.update(client=self,phase=phase,attempts=kwargs['max_attempts'],ledger=ledger,
                            phase_limit=str(phase_limit_cny))
    class FakeGateway:
        providers=['test']
        def __init__(self,cache,**kwargs):captured['snapshot']=kwargs['snapshot_id']
    def detect(ir,packages,**kwargs):
        captured['environments'].append(kwargs['evidence_environment'])
        assert kwargs['client'] is captured['client']
        return ir,{},{}
    def run(tasks,manifest,**kwargs):
        for task in tasks:kwargs['runner']({'program_spec':{'rule_id':task['rule_id']}},{})
        assert kwargs['client'] is captured['client']
        return {'status':'completed'}
    monkeypatch.setattr(llm,'MaasClient',FakeClient)
    monkeypatch.setattr(evidence,'EvidenceGateway',FakeGateway)
    monkeypatch.setattr(pipeline,'detect',detect)
    monkeypatch.setattr(study,'run_study',run)
    args=module.parser().parse_args(['--tasks',str(task_path),'--manifest',str(manifest_path),
        '--resources',str(resources_path),'--out',str(tmp_path/'out'),'--ledger',str(tmp_path/'same-ledger.sqlite3'),
        '--cache',str(tmp_path/'cache')])
    assert module.execute(args)['status']=='completed'
    assert captured['phase']=='framework-20261019' and captured['attempts']==1
    assert captured['phase_limit']=='200' and captured['ledger'].path==tmp_path/'same-ledger.sqlite3'
    assert captured['environments']==[environment,None] and captured['snapshot']=='fixed-evidence'


def test_program_only_repairs_failed_initial_code_under_the_configured_shared_model(tmp_path):
    tasks,manifest,splits=benchmark(tmp_path,('only',));out=tmp_path/'study';calls=[]
    model=extend_model(base_model(),{'node_types':{'Method':{'base_kind':'Section','description':'Shared initial methods.','attrs':{}}}})
    result=api()(tasks,manifest,client=Model(invalid_initial=True),output_dir=out,
                 runner=runner_for(out,splits,calls),max_rounds=2,initial_model=model)
    assert result['status']=='completed'
    fixed=result['conditions']['program_only']['rules']['only']
    assert fixed['rounds'][0]['status']=='candidate_failed'
    assert fixed['final_test']['metrics']['strict_balanced_accuracy']==1
    assert result['conditions']['program_only']['model_version']==model['version']

def test_resume_rejects_changed_semantic_runtime_even_with_same_declared_version(tmp_path,monkeypatch):
    import paper_compiler.study as study
    tasks,manifest,splits=benchmark(tmp_path,('only',));out=tmp_path/'study';calls=[]
    runner=runner_for(out,splits,calls)
    study.run_study(tasks,manifest,client=Model(),output_dir=out,runner=runner,max_rounds=1)
    original=study._sha
    monkeypatch.setattr(study,'_sha',lambda path:'0'*64 if Path(path).name=='program_analysis.py' else original(path))
    with pytest.raises(ValueError,match='frozen study artifact changed'):
        study.run_study(tasks,manifest,client=Model(),output_dir=out,runner=runner,max_rounds=1)


class ReservedInitialAnalysisModel(Model):
    """A joint repair can remove an invalid contract; program_only cannot."""
    def __init__(self, pause_fixed_repair=None):
        super().__init__()
        self.pause_fixed_repair = pause_fixed_repair

    def complete_json(self, task, instructions, data, max_tokens):
        blocked = data['requested_rule_id'] == 'blocked'
        initial = not data.get('feedback')
        fixed_repair = blocked and not initial and not data['allow_model_refinement']
        if fixed_repair and self.pause_fixed_repair == 'budget':
            raise BudgetExceeded('fake cumulative budget exhausted before fixed repair')
        if fixed_repair and self.pause_fixed_repair == 'interrupted':
            raise KeyboardInterrupt('fake interrupted process before fixed repair')
        answer = super().complete_json(task, instructions, data, max_tokens)
        if blocked and (initial or fixed_repair):
            answer['requires'] = ['citation_relevance']
            answer['analysis_requests'] = [{
                'name': 'citation_relevance',
                'targets': ['BibliographyEntry'],
                'fields': {'related': 'boolean'},
                'instructions': 'Read only the supplied source.'}]
        return answer


def test_exhausted_frozen_invalid_contract_does_not_block_all_heldout_results(tmp_path):
    tasks, manifest, splits = benchmark(tmp_path, ('healthy', 'blocked'))
    out = tmp_path / 'study'
    calls = []
    model = ReservedInitialAnalysisModel()
    result = api()(tasks, manifest, client=model, output_dir=out,
                   runner=runner_for(out, splits, calls), max_rounds=2)

    blocked = result['conditions']['program_only']['rules']['blocked']
    assert blocked['rounds_completed'] == 2
    assert blocked['stop_reason'] == 'round_limit'
    assert all(r['status'] == 'candidate_failed' for r in blocked['rounds'])
    assert all('already registered' in r['failures'][0]['reason'] for r in blocked['rounds'])
    assert len([d for d in model.requests if not d['feedback'] and
                d['requested_rule_id'] == 'blocked']) == 1
    raw = json.loads(Path(result['initial']['blocked']['raw_path']).read_text())
    assert raw['analysis_requests'][0]['name'] == 'citation_relevance'
    assert (out / 'conditions' / 'joint' / 'suite' / 'manifest.json').is_file()

    # Exhausting the allowed rounds is a terminal failed selection, not an
    # interrupted study. All condition selections (including this failure)
    # must freeze before any heldout evaluation, with no program fabricated.
    assert result['status'] == 'completed', (
        'A frozen invalid contract exhausted every round but prevented the '
        'otherwise selected conditions from reaching heldout evaluation: '
        + result.get('stop_reason', ''))
    assert (out / 'selection-frozen.json').is_file()
    assert any(split == 'test' for _, split, _ in calls)
    assert result['conditions']['joint']['rules']['blocked']['final_test']['metrics']['strict_balanced_accuracy'] == 1
    failed = result['conditions']['program_only']['rules']['blocked']['final_test']['metrics']
    assert failed['cases'] == 2 and failed['errors'] == 2
    assert failed['strict_balanced_accuracy'] == 0
    assert result['conditions']['program_only']['rules']['healthy']['final_test']['metrics']['cases'] == 2
    assert result['has_failed_selections'] is True
    condition = result['conditions']['program_only']
    failure = {'status': 'terminal_failure', 'reason': 'no_executable_candidate',
               'stop_reason': 'round_limit', 'rounds_completed': 2}
    assert condition['failed_selections'] == {'blocked': failure}
    assert condition['has_complete_executable_suite'] is False
    frozen = json.loads((out / 'selection-frozen.json').read_text())
    assert frozen['conditions']['program_only']['failed_selections'] == {'blocked': failure}
    assert set(frozen['conditions']['program_only']['program_versions']) == {'healthy'}
    from paper_compiler.pipeline import load_suite
    assert [p['program_spec']['rule_id'] for p in load_suite(condition['suite_path'])] == ['healthy']
    validation = json.loads((Path(condition['suite_path']) / 'validation.json').read_text())
    assert validation['complete_rule_coverage'] is False
    assert validation['failed_selections'] == {'blocked': failure}
    final = blocked['final_test']
    assert final['metrics']['mutant_detection_rate'] is None
    assert final['metrics']['control_false_positive_rate'] is None
    for groups in final['groups'].values():
        for metrics in groups.values():
            assert metrics['mutant_detection_rate'] is None
            assert metrics['control_false_positive_rate'] is None
    for row in final['records']:
        assert row['before'] == row['after'] == 'ERROR'
        assert row['correct'] is False and row['execution_performed'] is False
        assert row['failure_types'] == ['no_executable_candidate']
    before = (len(model.requests), len(calls))
    again = api()(tasks, manifest, client=model, output_dir=out,
                  runner=runner_for(out, splits, calls), max_rounds=2)
    assert again == result and (len(model.requests), len(calls)) == before
    failed_round = next(p for p in (out / 'conditions' / 'program_only').glob('task-*/round-001/round.json')
                        if json.loads(p.read_text())['status'] == 'candidate_failed')
    failed_round.write_text('{}')
    with pytest.raises(ValueError, match='integrity|hash'):
        api()(tasks, manifest, client=model, output_dir=out,
              runner=runner_for(out, splits, calls), max_rounds=2)
    assert (len(model.requests), len(calls)) == before


@pytest.mark.parametrize('pause', ['budget', 'interrupted'])
def test_unfinished_invalid_contract_selection_stays_incomplete_without_heldout(tmp_path, pause):
    tasks, manifest, splits = benchmark(tmp_path, ('healthy', 'blocked'))
    out = tmp_path / 'study'
    calls = []
    model = ReservedInitialAnalysisModel(pause_fixed_repair=pause)
    invoke = lambda: api()(tasks, manifest, client=model, output_dir=out,
                          runner=runner_for(out, splits, calls), max_rounds=2)
    if pause == 'interrupted':
        with pytest.raises(KeyboardInterrupt, match='fake interrupted'):
            invoke()
        result = json.loads((out / 'checkpoint.json').read_text())
        assert result['stop_reason'] == 'interrupted'
    else:
        result = invoke()
        assert result['stop_reason'] == 'budget_limit_selection'
        blocked = result['conditions']['program_only']['rules']['blocked']
        assert blocked['rounds_completed'] == 1
        assert blocked['stop_reason'] == 'budget_limit'
    assert result['status'] == 'incomplete'
    assert (out / 'checkpoint.json').is_file()
    assert not (out / 'summary.json').exists()
    assert not (out / 'selection-frozen.json').exists()
    assert not any(split == 'test' for _, split, _ in calls)


def test_zero_successful_selections_have_no_fake_suite_or_package(tmp_path):
    tasks, manifest, splits = benchmark(tmp_path, ('blocked',))
    out = tmp_path / 'study'
    calls = []
    result = api()(tasks, manifest, client=ReservedInitialAnalysisModel(), output_dir=out,
                   runner=runner_for(out, splits, calls), max_rounds=2)
    assert result['status'] == 'completed'
    condition = result['conditions']['program_only']
    assert condition['suite_version'] is None and condition['suite_path'] is None
    assert condition['has_complete_executable_suite'] is False
    assert not (out / 'conditions' / 'program_only' / 'suite').exists()
    assert condition['failed_selections']['blocked']['status'] == 'terminal_failure'
    frozen = json.loads((out / 'selection-frozen.json').read_text())
    assert frozen['conditions']['program_only']['program_versions'] == {}
    assert frozen['conditions']['program_only']['suite_version'] is None
    metrics = condition['rules']['blocked']['final_test']['metrics']
    assert metrics['cases'] == 2 and metrics['errors'] == 2
    assert metrics['strict_balanced_accuracy'] == 0
    assert metrics['mutant_detection_rate'] is None
    assert metrics['control_false_positive_rate'] is None



def study_cli_policy_fixture(tmp_path,monkeypatch,*,real_study=False):
    """TEST ONLY clients isolate the official CLI's public resume identity."""
    import os
    import paper_compiler.llm as llm
    import paper_compiler.evidence as evidence
    import paper_compiler.pipeline as pipeline
    import paper_compiler.program_analysis as analysis
    import paper_compiler.study as study
    tasks,manifest,splits=benchmark(tmp_path,('policy-task',));out=tmp_path/'study'
    task_path=tmp_path/'tasks.json';write_json_atomic(task_path,tasks)
    script=Path(__file__).resolve().parents[1]/'scripts/run_paper_compiler_study.py'
    spec=importlib.util.spec_from_file_location('study_cli_policy_test',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    captured={'fingerprints':[],'clients':[]}
    def policy():return {'schema_version':'TEST-ONLY-analysis-execution/1','batch_size':int(os.environ.get('PAPER_COMPILER_ANALYSIS_BATCH_SIZE','1')),
                         'opaque_public_contract':{'max_bytes':131072,'no_target_truncation':True}}
    monkeypatch.setattr(analysis,'analysis_execution_policy',policy,raising=False)
    def client(*args,**kwargs):
        assert kwargs['max_attempts']==1
        value=Model();captured['clients'].append(value);return value
    class Gateway:
        providers=['TEST ONLY provider']
        def __init__(self,*args,**kwargs):pass
    check=runner_for(out,splits,[])
    monkeypatch.setattr(llm,'MaasClient',client);monkeypatch.setattr(evidence,'EvidenceGateway',Gateway)
    monkeypatch.setattr(pipeline,'detect',lambda ir,packages,**kwargs:(ir,{},check(packages[0],ir)))
    actual=study.run_study
    if real_study:
        # Keep parallel runtime implementation edits outside this policy-only test.
        old_sha=study._sha;core=Path(study.__file__).resolve().parent
        monkeypatch.setattr(study,'_sha',lambda path:'b'*64 if Path(path).resolve().is_relative_to(core) else old_sha(path))
    def run(*args,**kwargs):
        captured['fingerprints'].append(kwargs['runner'].study_fingerprint)
        return actual(*args,**kwargs) if real_study else {'status':'completed'}
    monkeypatch.setattr(study,'run_study',run)
    args=module.parser().parse_args(['--tasks',str(task_path),'--manifest',str(manifest),'--out',str(out),
        '--max-rounds','1','--ledger',str(tmp_path/'test-only-ledger.sqlite3'),'--cache',str(tmp_path/'cache')])
    return module,args,captured,policy


def test_study_cli_modes_have_distinct_fingerprints_containing_the_entire_public_policy(tmp_path,monkeypatch):
    from paper_compiler.programs import digest
    module,args,captured,policy=study_cli_policy_fixture(tmp_path,monkeypatch)
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE','1');module.execute(args)
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE','8');module.execute(args)
    assert captured['fingerprints'][0]!=captured['fingerprints'][1]
    expected={'evidence_snapshot':'study-'+hashlib.sha256(args.manifest.read_bytes()).hexdigest()[:24],
        'resources':{},'task_environments':{'policy-task':None},'providers':['TEST ONLY provider'],
        'analysis_execution_policy':policy()}
    assert captured['fingerprints'][1]==digest(expected)
    assert all(not client.requests for client in captured['clients'])


def test_study_cli_analysis_mode_change_rejects_the_same_output_before_new_model_calls(tmp_path,monkeypatch):
    module,args,captured,_=study_cli_policy_fixture(tmp_path,monkeypatch,real_study=True)
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE','1');assert module.execute(args)['status']=='completed'
    frozen=(args.out/'protocol.json').read_bytes();assert captured['clients'][0].requests
    assert module.execute(args)['status']=='completed' and not captured['clients'][-1].requests
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE','8')
    with pytest.raises(ValueError,match='frozen study artifact changed'):module.execute(args)
    assert not captured['clients'][-1].requests and (args.out/'protocol.json').read_bytes()==frozen



def test_study_cli_invalid_analysis_policy_fails_before_ledger_or_client_creation(tmp_path,monkeypatch):
    import paper_compiler.program_analysis as analysis
    module,args,captured,_=study_cli_policy_fixture(tmp_path,monkeypatch)
    def invalid():raise ValueError('TEST ONLY invalid analysis execution policy')
    monkeypatch.setattr(analysis,'analysis_execution_policy',invalid,raising=False)
    with pytest.raises(ValueError,match='invalid analysis execution policy'):module.execute(args)
    assert not args.ledger.exists() and not captured['clients']
