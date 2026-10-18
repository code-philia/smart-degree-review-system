"""Mutation-admission policy cannot become detector or independent rule truth."""
import copy
import json
from paper_compiler.analysis import base_analysis
from paper_compiler.programs import check_programs

POLICY = {'id':'fault-admission','purpose':'mutation_admission',
          'text':'BENCHMARK_ONLY_SECRET: only a completely fabricated identity is an admissible negative.'}

def test_synthesis_prompt_and_package_exclude_mutation_admission(tmp_path):
    from paper_compiler.synthesis import synthesize_program
    from test_paper_compiler_feedback_loop import candidate,CODE
    class Recorder:
        def complete_json(self,task,instructions,data,max_tokens):
            self.data=copy.deepcopy(data)
            return candidate(CODE)
    norm=[{'id':'test','text':'Hello'}]; task={'rule_id':'new-rule','rule_text':'Hello',
        'basis':norm+[copy.deepcopy(POLICY)]}; original=copy.deepcopy(task);model=Recorder()
    package=synthesize_program(task,model,tmp_path/'synthesis')
    assert model.data['basis']==norm
    assert 'BENCHMARK_ONLY_SECRET' not in json.dumps(model.data)
    assert package['input']['basis']==norm and task==original

def test_supplied_round_zero_candidate_uses_only_rule_basis(tmp_path):
    from paper_compiler.feedback_loop import run_feedback_loop
    from test_paper_compiler_feedback_loop import candidate,CODE,make_cases
    class NoAPI:
        config={}
        def complete_json(self,*args): raise AssertionError('round zero must reuse supplied raw')
    seen=[]
    def runner(package,ir):
        seen.append(copy.deepcopy(package['input']['basis']))
        return check_programs(ir,base_analysis(ir),[package])
    norm=[{'id':'test','text':'Hello'}]
    task={'rule_id':'new-rule','rule_text':'Hello','basis':norm+[copy.deepcopy(POLICY)]}
    run_feedback_loop(task,make_cases(tmp_path),client=NoAPI(),output_dir=tmp_path/'loop',
        runner=runner,max_rounds=1,initial_candidate=candidate(CODE),defer_test=True)
    assert seen and all(basis==norm for basis in seen)

def test_study_common_initial_rebuild_preserves_rule_only_basis(tmp_path):
    from paper_compiler.study import run_study
    from test_paper_compiler_study import benchmark,Model,runner_for
    tasks,manifest,splits=benchmark(tmp_path,rule_ids=('alpha',));norm=copy.deepcopy(tasks[0]['basis'])
    tasks[0]['basis'].append(copy.deepcopy(POLICY));out=tmp_path/'study';seen=[];calls=[]
    execute=runner_for(out,splits,calls)
    def runner(package,ir):
        seen.append(copy.deepcopy(package['input']['basis']))
        return execute(package,ir)
    runner.study_fingerprint=execute.study_fingerprint
    result=run_study(tasks,manifest,client=Model(),output_dir=out,runner=runner,max_rounds=2)
    assert result['status']=='completed'
    assert seen and all(basis==norm for basis in seen)

def test_planner_reads_rule_basis_but_preserves_host_admission_data():
    from paper_compiler.task_planner import plan_task
    from test_paper_compiler_task_planner import ExternalModel,BASIS,RULE_ID,RULE_TEXT
    model=ExternalModel();basis=copy.deepcopy(BASIS)+[copy.deepcopy(POLICY)]
    result=plan_task(RULE_ID,RULE_TEXT,basis,client=model)
    assert model.requests[0][2]['basis']==BASIS
    assert result['basis']==basis
    assert 'BENCHMARK_ONLY_SECRET' not in json.dumps(model.requests)

def test_existing_initial_package_matches_projected_rule_basis(tmp_path):
    from paper_compiler.synthesis import synthesize_program
    from paper_compiler.feedback_loop import run_feedback_loop
    from test_paper_compiler_feedback_loop import candidate,CODE,make_cases
    class Initial:
        config={}
        def complete_json(self,*args):return candidate(CODE)
    class NoMoreAPI:
        config={}
        def complete_json(self,*args):raise AssertionError('valid initial must be reused without regeneration')
    norm=[{'id':'test','text':'Hello'}]
    task={'rule_id':'new-rule','rule_text':'Hello','basis':norm+[copy.deepcopy(POLICY)]}
    raw_task={**task,'basis':norm}
    package=synthesize_program(raw_task,Initial(),tmp_path/'initial')
    result=run_feedback_loop(task,make_cases(tmp_path),client=NoMoreAPI(),output_dir=tmp_path/'loop',
        runner=lambda p,ir:check_programs(ir,base_analysis(ir),[p]),
        max_rounds=1,initial_package=package,defer_test=True)
    assert result['status']=='selected_pending_test'

def test_feedback_prompt_cannot_reintroduce_admission_policy_from_sealed_oracle(tmp_path):
    from pathlib import Path
    import hashlib
    from paper_compiler.feedback_loop import run_feedback_loop
    from test_paper_compiler_feedback_loop import candidate,CODE,make_cases
    manifest=make_cases(tmp_path);value=json.loads(Path(manifest).read_text())
    for case in value['cases']:
        if case['split']!='feedback':continue
        path=Path(case['oracle_path']);oracle=json.loads(path.read_text())
        oracle['admission_policy']={'conditions':[{'basis_id':'fault-admission','text':POLICY['text']}]}
        oracle['generation_proposal']={'generation_guidance':POLICY['text']}
        oracle['label']={'status':oracle['status'],'original_compliant':True,'basis_ids':['test'],
            'reason':POLICY['text'],'quotes':[{'source_id':'original-node','quote':'Hello'},
                {'source_id':'admission:fault-admission:VIOLATION:0-20','quote':POLICY['text']}]}
        path.write_text(json.dumps(oracle))
        if str(path) in value.get('artifact_sha256',{}):
            value['artifact_sha256'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    Path(manifest).write_text(json.dumps(value))
    class Repair:
        config={}
        def __init__(self):self.requests=[]
        def complete_json(self,task,instructions,data,max_tokens):
            self.requests.append(copy.deepcopy(data))
            return candidate("def detect(payload):\n    return [emit(n,'PASS','initial','text',['test']) for n in nodes(payload,'BibliographyEntry')]" if len(self.requests)==1 else CODE)
    model=Repair()
    run_feedback_loop({'rule_id':'new-rule','rule_text':'Hello','basis':[{'id':'test','text':'Hello'}]},
        manifest,client=model,output_dir=tmp_path/'loop',
        runner=lambda p,ir:check_programs(ir,base_analysis(ir),[p]),max_rounds=2)
    assert len(model.requests)==2
    feedback=json.dumps(model.requests[1]['feedback'])
    assert 'BENCHMARK_ONLY_SECRET' not in feedback
    assert 'original-node' in feedback and 'Hello' in feedback

def test_online_local_feedback_cannot_reintroduce_generation_policy():
    from paper_compiler.online_loop import _case_failures
    case={'id':'local-1','ir':{'nodes':[{'id':'p','text':'Observed source'}]},
        'expected':[{'rule_id':'future-rule','node_id':'p','status':'VIOLATION'}],
        'label_evidence':{'admission_policy':{'text':POLICY['text']},
            'label':{'status':'VIOLATION','reason':POLICY['text'],'quotes':[
                {'source_id':'mutated-node','quote':'Observed source'},
                {'source_id':'admission:construction:VIOLATION','quote':POLICY['text']}]}}}
    report={'rules':[{'rule_id':'future-rule','results':[{'node_id':'p','status':'PASS'}]}]}
    failures=_case_failures(case,report)
    assert len(failures)==1
    assert 'BENCHMARK_ONLY_SECRET' not in json.dumps(failures)
    assert 'Observed source' in json.dumps(failures)
