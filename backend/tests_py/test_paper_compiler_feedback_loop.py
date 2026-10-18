import copy,json
from pathlib import Path
from test_paper_compiler_programs import candidate, CODE
from test_paper_compiler_compiler import fixture
from paper_compiler.contracts import ir_hash
from paper_compiler.analysis import base_analysis
from paper_compiler.mutations import mutate
from paper_compiler.storage import write_json_atomic

class ExternalModel:
    def __init__(self):self.requests=[]
    def complete_json(self,task,instructions,data,max_tokens):
        self.requests.append(copy.deepcopy(data))
        code="def detect(payload):\n    return [emit(n, 'PASS', 'initial', 'text', ['test']) for n in nodes(payload, 'BibliographyEntry')]"
        return candidate(CODE if data.get('feedback') else code)

def make_cases(tmp_path):
    cases=[]
    for split in ['feedback','validation','test']:
        folder=tmp_path/split;folder.mkdir()
        ir,_=fixture(folder)
        changed,_=mutate(ir,{'mutation_id':split+'-edit','parent_sha256':ir_hash(ir),
            'operation':'replace_text','node_id':'entry','start':0,'end':5,'old_text':'Hello',
            'replacement':'Wrong','rule_id':'new-rule','status':'VIOLATION'})
        for name,data in [('original',ir),('mutant',changed)]:
            write_json_atomic(folder/(name+'.json'),data)
        for label in ['VIOLATION','PASS']:
            case_id=split+('-secret' if split!='feedback' else '-failure')+label
            oracle=folder/(label+'.oracle.json')
            write_json_atomic(oracle,{'valid':True,'status':label,'target_node_id':'entry'})
            cases.append({'id':case_id,'rule_id':'new-rule','parent_group':split+'-parent','split':split,
                'ir_path':str(folder/('mutant.json' if label=='VIOLATION' else 'original.json')),
                'original_ir_path':str(folder/'original.json'),'oracle_path':str(oracle),
                'target_node_id':'entry','context_origin':'real','evidence_domain':'test'})
    manifest=tmp_path/'benchmark.json'
    write_json_atomic(manifest,{'schema_version':'paper-benchmark/2.0','status':'complete','cases':cases})
    return manifest

def test_feedback_repairs_executable_behavior_without_disclosing_holdout(tmp_path):
    from paper_compiler.feedback_loop import run_feedback_loop
    from paper_compiler.programs import check_programs
    manifest=make_cases(tmp_path)
    model=ExternalModel()
    def runner(package,ir):
        return check_programs(ir,base_analysis(ir),[package])
    result=run_feedback_loop({'rule_id':'new-rule','rule_text':'The entry must be Hello',
        'basis':[{'id':'test','text':'The entry must be Hello'}]},manifest,client=model,
        output_dir=tmp_path/'loop',runner=runner)
    assert result['status']=='completed'
    assert result['rounds_completed']==2
    assert result['baseline_test']['strict_balanced_accuracy']==0.5
    assert result['final_test']['strict_balanced_accuracy']==1
    assert result['best_version']!=result['initial_version']
    assert result['remaining_feedback_errors']==0
    requests=json.dumps(model.requests)
    assert 'validation-secret' not in requests and 'test-secret' not in requests
    assert json.loads((tmp_path/'loop'/'round-001'/'feedback.json').read_text())['failures']==[]

def test_loop_enforces_the_five_round_ceiling(tmp_path):
    from paper_compiler.feedback_loop import run_feedback_loop
    from paper_compiler.programs import check_programs
    manifest=make_cases(tmp_path)
    class NeverRepairs(ExternalModel):
        def complete_json(self,task,instructions,data,max_tokens):
            data=copy.deepcopy(data);data['feedback']=[]
            return super().complete_json(task,instructions,data,max_tokens)
    model=NeverRepairs()
    result=run_feedback_loop({'rule_id':'new-rule','rule_text':'Hello','basis':[{'id':'test','text':'Hello'}]},
        manifest,client=model,output_dir=tmp_path/'loop',max_rounds=5,
        runner=lambda p,ir:check_programs(ir,base_analysis(ir),[p]))
    assert result['rounds_completed']==5 and result['stop_reason']=='round_limit'
    assert result['final_test']['strict_balanced_accuracy']==0.5
    assert result['remaining_feedback_errors']>0

def test_changed_frozen_manifest_cannot_resume_a_loop(tmp_path):
    from paper_compiler.feedback_loop import run_feedback_loop, FeedbackError
    from paper_compiler.programs import check_programs
    import pytest
    manifest=make_cases(tmp_path);model=ExternalModel()
    task={'rule_id':'new-rule','rule_text':'Hello','basis':[{'id':'test','text':'Hello'}]}
    runner=lambda p,ir:check_programs(ir,base_analysis(ir),[p])
    run_feedback_loop(task,manifest,client=model,output_dir=tmp_path/'loop',runner=runner)
    value=json.loads(manifest.read_text());value['cases'][0]['split']='test'
    write_json_atomic(manifest,value)
    with pytest.raises(FeedbackError,match='frozen'):
        run_feedback_loop(task,manifest,client=model,output_dir=tmp_path/'loop',runner=runner)

def test_resume_preserves_the_last_shared_model_revision(tmp_path):
    import pytest
    from paper_compiler.feedback_loop import run_feedback_loop
    from paper_compiler.model_runtime import base_model
    from paper_compiler.pipeline import detect
    class CrashAfterFirst(ExternalModel):
        def complete_json(self,task,instructions,data,max_tokens):
            if self.requests:raise SystemExit('simulated host restart')
            answer=super().complete_json(task,instructions,data,max_tokens)
            answer['model_patch']={'node_types':{'Method':{'base_kind':'Section','description':'methods','attrs':{}}}}
            return answer
    manifest=make_cases(tmp_path)
    task={'rule_id':'new-rule','rule_text':'Hello','basis':[{'id':'test','text':'Hello'}]}
    run=lambda p,ir:detect(ir,[p],client=None,gateway=None,cache_dir=tmp_path/'cache')[2]
    with pytest.raises(SystemExit):
        run_feedback_loop(task,manifest,client=CrashAfterFirst(),output_dir=tmp_path/'loop',runner=run,model=base_model())
    client=ExternalModel()
    result=run_feedback_loop(task,manifest,client=client,output_dir=tmp_path/'loop',runner=run,model=base_model())
    assert result['rounds'][1]['status']=='evaluated'
    assert 'Method' in client.requests[0]['paper_model']['node_types']
