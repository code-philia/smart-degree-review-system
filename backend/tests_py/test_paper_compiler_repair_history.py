"""Substantive repair attempts, without held-out or incidental cache salt."""
import copy
import hashlib
import json

import pytest

from paper_compiler.analysis import base_analysis
from paper_compiler.feedback_loop import run_feedback_loop
from paper_compiler.programs import check_programs, digest
from paper_compiler.synthesis import INSTRUCTIONS, synthesize_program
from test_paper_compiler_feedback_loop import make_cases
from test_paper_compiler_programs import candidate, CODE
from test_paper_compiler_online_loop import Model, OLD, FIX, call, mutant, package
from paper_compiler.runtime_control import RuntimeControl

TASK={'rule_id':'new-rule','rule_text':'Check greeting',
      'basis':[{'id':'test','text':'Greeting is Hello.'}],'target_kinds':['BibliographyEntry']}
NOOP="def detect(payload):\n    return [emit(n, 'PASS', 'initial', 'text', ['test']) for n in nodes(payload, 'BibliographyEntry')]"

class Client:
    def __init__(self, answers=None, crash_at=None):
        self.requests=[];self.answers=answers or [candidate(NOOP)];self.crash_at=crash_at
    def complete_json(self,task,instructions,data,max_tokens):
        self.requests.append(copy.deepcopy(data))
        if len(self.requests)==self.crash_at:raise SystemExit('restart')
        return copy.deepcopy(self.answers[min(len(self.requests)-1,len(self.answers)-1)])

def run(tmp_path,client,**kwargs):
    manifest=tmp_path/'benchmark.json'
    if not manifest.exists():manifest=make_cases(tmp_path)
    return run_feedback_loop(TASK,manifest,client=client,output_dir=tmp_path/'loop',
        runner=lambda p,ir:check_programs(ir,base_analysis(ir),[p]),**kwargs)

def test_initial_default_fingerprint_is_byte_compatible(tmp_path):
    synthesize_program(TASK,Client([candidate(CODE)]),tmp_path)
    saved=json.loads((tmp_path/'synthesis-input.json').read_text())
    assert saved['input_sha256']=='21cbda1c79f06a7f55559d2cec1eaf825f6c61cf87e044418af4421c548480a0'
    assert hashlib.sha256(INSTRUCTIONS.encode()).hexdigest()=='e75cb886e9791ef3d93a6e850fa578e569aae13fea38590e0df215ea26515078'
    assert 'repair_context' not in saved['data']

def test_offline_noop_history_changes_next_real_attempt_and_counts_five(tmp_path):
    client=Client();result=run(tmp_path,client,max_rounds=5)
    assert result['rounds_completed']==5 and result['stop_reason']=='round_limit'
    assert len({digest(r) for r in client.requests})==5
    assert 'repair_context' not in client.requests[0]
    for index,data in enumerate(client.requests[1:],1):
        context=data['repair_context']
        assert context['attempt']==index and len(context['history'])==index
        assert context['history'][-1]['candidate']['code']==NOOP
        assert context['history'][-1]['feedback_metrics']['strict_errors']>0
        encoded=json.dumps(context)
        assert all(s not in encoded for s in ['validation_metrics','validation_score','test-secret','validation-secret','resource_usage','elapsed'])
    assert all(r['revision_effect']['unchanged'] for r in result['rounds'][1:])
    assert result['remaining_feedback_errors']>0

def test_offline_invalid_raw_is_history_without_replacing_valid_candidate(tmp_path):
    bad={**candidate(CODE),'unrecognized_field':'actual rejected raw'}
    client=Client([candidate(NOOP),bad,candidate(CODE)])
    result=run(tmp_path,client,max_rounds=3)
    context=client.requests[2]['repair_context']
    failed=context['history'][-1]
    assert failed['candidate']==bad and failed['status']=='candidate_failed'
    assert 'compile_or_contract' in failed['failure_types']
    assert client.requests[2]['previous_candidate']['code']==NOOP
    assert result['rounds'][1]['status']=='candidate_failed'
    assert result['remaining_feedback_errors']==0

def test_offline_resume_reuses_same_pending_context_and_skips_completed(tmp_path):
    interrupted=Client(crash_at=3)
    with pytest.raises(SystemExit):run(tmp_path,interrupted,max_rounds=4)
    client=Client();result=run(tmp_path,client,max_rounds=4)
    assert client.requests[0]==interrupted.requests[-1]
    assert [r['repair_context']['attempt'] for r in client.requests]==[2,3]
    assert result['rounds_completed']==4

class OnlineClient(Model):
    def __init__(self,answers=None,crash_at=None,on_synthesis=None):
        super().__init__(on_synthesis=on_synthesis);self.inputs=[]
        self.answers=answers or [OLD];self.crash_at=crash_at
    def complete_json(self,task,instructions,data,max_tokens):
        if task!='paper-program-synthesis/2.0':return super().complete_json(task,instructions,data,max_tokens)
        self.inputs.append(copy.deepcopy(data))
        if len(self.inputs)==self.crash_at:raise SystemExit('restart')
        if self.on_synthesis:self.on_synthesis()
        value=self.answers[min(len(self.inputs)-1,len(self.answers)-1)]
        from test_paper_compiler_online_loop import candidate as online_candidate
        return copy.deepcopy(online_candidate(value) if isinstance(value,str) else value)

def test_online_noop_keeps_unresolved_rounds_and_real_history(tmp_path):
    client=OnlineClient();control=RuntimeControl(tmp_path/'control')
    result=call(tmp_path,mutant(tmp_path),[package()],client,control,max_rounds=5)
    assert result['runtime']['status']=='candidate_rejected'
    assert len(result['runtime']['rounds'])==5
    assert len({digest(d) for d in client.inputs})==5
    assert all(r['revision_effect']['word']['unchanged'] for r in result['runtime']['rounds'])
    assert all(d['repair_context']['history'][-1]['candidate']['code']==OLD for d in client.inputs[1:])
    assert control.snapshot()['active_version'] is None

def test_online_failed_raw_does_not_replace_working_model_or_program(tmp_path):
    from test_paper_compiler_online_loop import candidate as online_candidate
    bad=online_candidate("def detect(payload):\n    return open('/private/data')")
    bad['model_patch']={'node_types':{'FailedKind':{'base_kind':'Section','description':'failed','attrs':{}}}}
    client=OnlineClient([bad,FIX]);control=RuntimeControl(tmp_path/'control')
    result=call(tmp_path,mutant(tmp_path),[package()],client,control,max_rounds=2)
    assert result['runtime']['status']=='promoted'
    assert client.inputs[1]['previous_candidate']['code']==OLD
    assert 'FailedKind' not in client.inputs[1]['paper_model']['node_types']
    assert client.inputs[1]['repair_context']['history'][-1]['candidate']==bad

def test_online_resume_completed_attempt_is_not_regenerated(tmp_path):
    ir=mutant(tmp_path);control=RuntimeControl(tmp_path/'control');crashed=OnlineClient(crash_at=2)
    with pytest.raises(SystemExit):call(tmp_path,ir,[package()],crashed,control,max_rounds=3)
    client=OnlineClient()
    result=call(tmp_path,ir,[package()],client,control,max_rounds=3)
    assert client.inputs[0]==crashed.inputs[-1]
    assert [d['repair_context']['attempt'] for d in client.inputs]==[2,3]
    assert len(result['runtime']['rounds'])==3

def test_online_freeze_during_history_repair_never_promotes(tmp_path):
    control=RuntimeControl(tmp_path/'control')
    client=OnlineClient([FIX],on_synthesis=lambda:control.set_freeze(True,actor='test'))
    result=call(tmp_path,mutant(tmp_path),[package()],client,control,max_rounds=2)
    assert result['runtime']['status']=='frozen'
    assert control.snapshot()['active_version'] is None


def test_legacy_offline_rounds_rebuild_same_substantive_history(tmp_path):
    interrupted=Client(crash_at=3)
    with pytest.raises(SystemExit):run(tmp_path,interrupted,max_rounds=4)
    for checkpoint in (tmp_path/'loop').glob('round-*/round.json'):
        value=json.loads(checkpoint.read_text());value.pop('repair_history',None)
        checkpoint.write_text(json.dumps(value))
    client=Client();run(tmp_path,client,max_rounds=4)
    assert client.requests[0]==interrupted.requests[-1]

def test_online_execution_failure_keeps_last_valid_repair_model(tmp_path,monkeypatch):
    import paper_compiler.online_loop as online
    from test_paper_compiler_online_loop import candidate as online_candidate
    actual=online.detect;failed=[]
    def detect(ir,packages,**kwargs):
        if not failed and any('AttemptKind' in p['model']['node_types'] for p in packages):
            failed.append(True);raise RuntimeError('actual candidate execution failed')
        return actual(ir,packages,**kwargs)
    monkeypatch.setattr(online,'detect',detect)
    raw=online_candidate(FIX)
    raw['model_patch']={'node_types':{'AttemptKind':{'base_kind':'Section','description':'attempt','attrs':{}}}}
    client=OnlineClient([raw,FIX]);control=RuntimeControl(tmp_path/'control')
    result=call(tmp_path,mutant(tmp_path),[package()],client,control,max_rounds=2)
    assert result['runtime']['status']=='promoted'
    assert client.inputs[1]['previous_candidate']['code']==OLD
    assert 'AttemptKind' not in client.inputs[1]['paper_model']['node_types']
    assert client.inputs[1]['repair_context']['history'][-1]['errors']==[
        {'error_type':'RuntimeError','reason':'actual candidate execution failed'}]


def test_initial_revision_is_not_a_model_extension():
    from paper_compiler.synthesis import revision_effect
    effect=revision_effect(None,package())
    assert effect=={'comparison':'no_comparable_previous','unchanged':None,
                    'code_changed':None,'contract_changed':None,'model_changed':None}
