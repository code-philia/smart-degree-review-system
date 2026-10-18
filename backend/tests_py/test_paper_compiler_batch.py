import hashlib,json
import pytest
from paper_compiler.storage import write_json_atomic

def manifest(tmp_path):
    source=tmp_path/'source.pdf';source.write_bytes(b'%PDF-test')
    m=tmp_path/'manifest.json';write_json_atomic(m,{'version':'frozen/1','items':[{'id':'paper-1','input_path':str(source),'input_kind':'pdf','sha256':hashlib.sha256(source.read_bytes()).hexdigest()}]})
    return m

def test_resume_skips_completed_inputs_and_conflicting_version_fails(tmp_path):
    from paper_compiler.batch import run_batch
    calls=[];m=manifest(tmp_path);config={'pipeline_version':'v1','runner':lambda path: calls.append(path) or {'status':'ok'},'workers':1}
    a=run_batch(m,config,tmp_path/'out');b=run_batch(m,config,tmp_path/'out')
    assert len(calls)==1 and a['counts']==b['counts']=={'completed':1}
    with pytest.raises(ValueError,match='frozen'):run_batch(m,{**config,'pipeline_version':'v2'},tmp_path/'out')

def test_failed_results_are_retained_and_not_retried_implicitly(tmp_path):
    from paper_compiler.batch import run_batch
    def fail(path):raise RuntimeError('test failure')
    m=manifest(tmp_path);config={'pipeline_version':'v1','runner':fail}
    a=run_batch(m,config,tmp_path/'out')
    assert a['counts']=={'error':1}
    b=run_batch(m,{**config,'runner':lambda path:pytest.fail('must not retry')},tmp_path/'out')
    assert b['counts']=={'error':1}
    assert (tmp_path/'out/items/paper-1/attempt-1.json').is_file()

def test_mutated_frozen_input_is_error_without_running_detector(tmp_path):
    from paper_compiler.batch import run_batch
    m=manifest(tmp_path);(tmp_path/'source.pdf').write_bytes(b'changed')
    a=run_batch(m,{'pipeline_version':'v1','runner':lambda p:pytest.fail('unverified input')},tmp_path/'out')
    assert a['counts']=={'error':1}

def test_duplicate_or_escaping_item_ids_rejected(tmp_path):
    from paper_compiler.batch import run_batch
    m=manifest(tmp_path);data=json.loads(m.read_text());data['items'][0]['id']='../oracle';write_json_atomic(m,data)
    with pytest.raises(ValueError):run_batch(m,{'pipeline_version':'v1','runner':lambda p:{}},tmp_path/'out')

def test_evaluator_does_not_send_oracle_to_runner_and_freezes_report(tmp_path):
    from paper_compiler.evaluation import evaluate
    from test_paper_compiler_compiler import fixture
    from paper_compiler.contracts import ir_hash
    from test_paper_compiler_evaluation import report,oracle
    ir,_=fixture(tmp_path);original=tmp_path/'original.json';write_json_atomic(original,ir)
    import copy
    mutant=copy.deepcopy(ir);mutant['revision']='2';mp=tmp_path/'mutant.json';write_json_atomic(mp,mutant)
    o={**oracle(ir_hash(ir)),'mutation_id':'m1','mutant_sha256':ir_hash(mutant)};op=tmp_path/'sealed-oracle.json';write_json_atomic(op,o)
    m=tmp_path/'cases.json';write_json_atomic(m,{'version':'case/1','cases':[{'id':'m1','original':str(original),'mutant':str(mp),'oracle':str(op)}]})
    calls=[]
    def runner(path):
        calls.append(path);assert path in [original,mp];return report('PASS' if path==original else 'VIOLATION')
    r=evaluate(m,tmp_path/'report',runner);evaluate(m,tmp_path/'report',runner)
    assert len(calls)==2 and r['by_rule']['31']['detected']==1
