import copy,json
from pathlib import Path
import pytest
import paper_compiler.online_loop as online
from paper_compiler.pipeline import detect
from paper_compiler.programs import ProgramError,build_program
from paper_compiler.runtime_control import RuntimeControl
from paper_compiler.budget import BudgetExceeded
from test_paper_compiler_online_loop import FIX,OLD,BAD,candidate
from test_paper_compiler_online_mutants import document,package,Model as SourceModel
BROKEN="def detect(payload):\n    value = 1 / 0\n    return []\n"

def broken_package():
 p=package();return build_program(candidate(BROKEN),rule_text=p['input']['rule_text'],basis=p['input']['basis'],model=p['model'])

class Model(SourceModel):
 def __init__(self,code=FIX,*,audit_unknown=False,on_synthesis=None,**kwargs):
  super().__init__(code,**kwargs);self.audit_unknown=audit_unknown;self.on_synthesis=on_synthesis
 def complete_json(self,task,instructions,data,max_tokens):
  if task=='paper-program-synthesis/2.0':
   self.requests.append((task,copy.deepcopy(data)))
   if self.on_synthesis:self.on_synthesis()
   return candidate(self.code)
  result=super().complete_json(task,instructions,data,max_tokens)
  if self.audit_unknown and task.startswith('online-evidence-'):
   for row in result['judgments']:row['status']='UNKNOWN'
  return result

def run(tmp_path,*,model=None,control=None,resources=None,packages=None,ir=None):
 return online.online_refine(ir or document(tmp_path),packages or [broken_package()],client=model,
  gateway=None,cache_dir=tmp_path/'cache',control=control or RuntimeControl(tmp_path/'control'),
  output_dir=tmp_path/'online',resources=resources,max_rounds=1)

def test_real_initial_execution_failure_reaches_repair_unlabeled_and_promotes_with_real_local_pv(tmp_path):
 model=Model(audit_unknown=True);control=RuntimeControl(tmp_path/'control');old=broken_package();ir=document(tmp_path)
 result=run(tmp_path,model=model,control=control,packages=[old],ir=ir)
 assert result['runtime']['status']=='promoted'
 assert result['packages'][0]['code']==FIX
 request=next(data for task,data in model.requests if task=='paper-program-synthesis/2.0')
 error=next(row for row in request['feedback'] if row.get('failure_types')==['execution_error'])
 assert error['rule_id']=='word' and error['program_version']==old['manifest']['version_id']
 assert error['error_type']=='ProgramError' and 'ZeroDivisionError' in error['reason']
 assert not {'expected','status','before','after','actual','node_id'}&set(error)
 assert error['paper_ir_sha256'] and error['analysis_sha256']
 assert all('expected' not in target for task,data in model.requests if task.startswith('online-evidence-') for target in data['targets'])
 gate=result['runtime']['rounds'][0]['gate']
 assert gate['verified_local_cases']==2 and gate['verified_local_controls']==1 and gate['local_mutation_improvements']==1
 assert result['report']['rules'][0]['results'][0]['status']=='PASS'
 assert control.snapshot()['active_version']==result['runtime']['promoted_version']

def test_strict_detect_keeps_existing_exception_behavior_and_partial_recovery_preserves_other_rule_baseline(tmp_path):
 ir=document(tmp_path);ir['coverage']['Paragraph']={'status':'complete','protocol':'synthetic-source-fixture/1.0','evidence_ids':['p']};other=candidate(OLD);other['rule_id']='other';good=build_program(other,rule_text='Other source check.',basis=package()['input']['basis'])
 with pytest.raises(ProgramError,match='ZeroDivisionError'):detect(ir,[broken_package(),good],client=None,gateway=None,cache_dir=tmp_path/'strict')
 materialized,analysis,report=detect(ir,[broken_package(),good],client=None,gateway=None,cache_dir=tmp_path/'baseline',recover_program_errors=True)
 failed,ok=report['rules'];assert failed['status']=='ERROR' and failed['results']==[] and failed['counts']=={}
 assert failed['execution_error']['program_version']==broken_package()['manifest']['version_id']
 assert ok['status']=='PASS' and ok['results'][0]['status']=='PASS'
 assert report['analysis_sha256'] and report['pipeline_version']
 # Existing cross-rule gate still rejects an independently executed unaffected-rule regression.
 other['code']=BAD;bad=build_program(other,rule_text='Other source check.',basis=good['input']['basis'])
 fixed=build_program(candidate(FIX),rule_text=package()['input']['rule_text'],basis=package()['input']['basis'])
 _,_,after=detect(ir,[fixed,bad],client=None,gateway=None,cache_dir=tmp_path/'after')
 gate=online._gate(report,after,{('word','p'):'PASS'},[],[])
 assert not gate['passed'] and gate['cross_rule_regressions']==1

@pytest.mark.parametrize('control_state,want',[('frozen','frozen'),('no-client','no_client'),('disabled','mutation_validation_required')])
def test_initial_error_cannot_bypass_frozen_missing_client_or_disabled_local_validation(tmp_path,control_state,want):
 control=RuntimeControl(tmp_path/'control');model=Model()
 if control_state=='frozen':control.set_freeze(True)
 result=run(tmp_path,control=control,model=None if control_state=='no-client' else model,
  resources={'online_mutation_validation':False} if control_state=='disabled' else None)
 assert result['runtime']['status']==want and result['packages'][0]['code']==BROKEN
 assert result['report']['rules'][0]['status']=='ERROR' and result['report']['rules'][0]['results']==[]
 assert not model.requests and control.snapshot()['active_version'] is None
 assert not list((tmp_path/'online').rglob('validation.json'))

def test_initial_error_and_unknown_local_labels_keeps_old_suite(tmp_path):
 control=RuntimeControl(tmp_path/'control');model=Model(mode='unknown',audit_unknown=True)
 result=run(tmp_path,model=model,control=control)
 assert result['runtime']['status']=='mutation_validation_incomplete' and result['packages'][0]['code']==BROKEN
 assert not any(task=='paper-program-synthesis/2.0' for task,data in model.requests)
 assert control.snapshot()['active_version'] is None

@pytest.mark.parametrize('event,want',[('freeze','frozen'),('generation','version_conflict'),('budget','budget_limit')])
def test_initial_error_repair_preserves_racing_control_and_budget_guards(tmp_path,event,want):
 control=RuntimeControl(tmp_path/'control')
 def on_synthesis():
  if event=='budget':raise BudgetExceeded('synthetic bounded budget exhausted')
  control.set_freeze(True)
  if event=='generation':control.set_freeze(False)
 model=Model(on_synthesis=on_synthesis)
 result=run(tmp_path,model=model,control=control)
 assert result['runtime']['status']==want and result['packages'][0]['code']==BROKEN
 assert control.snapshot()['active_version'] is None and result['report']['rules'][0]['status']=='ERROR'

def test_initial_error_candidate_must_pass_inherited_regression(tmp_path):
 folder=tmp_path/'inherited';folder.mkdir();ir=document(folder)
 control=RuntimeControl(tmp_path/'control');model=Model(BAD)
 case={'id':'source-verified-control','verified':True,'origin':'online-regression','ir':ir,
  'expected':[{'rule_id':'word','node_id':'p','status':'PASS'}]}
 result=run(tmp_path,model=model,control=control,resources={'regression_cases':[case]})
 assert result['runtime']['status']=='candidate_rejected' and result['packages'][0]['code']==BROKEN
 assert result['runtime']['rounds'][0]['gate']['regressions']>0 and control.snapshot()['active_version'] is None

def test_new_unattributed_baseline_failure_on_unaffected_rule_is_terminal(tmp_path):
 other=candidate("def detect(payload):\n    output=[]\n    for n in nodes(payload,'Paragraph'):\n        if 'trap' in n['text']:\n            value = 1 / 0\n        output.append(emit(n,'PASS' if 'tree' in n['text'] else 'VIOLATION','Source rule'))\n    return output\n");other['rule_id']='other'
 good=build_program(other,rule_text=package()['input']['rule_text'],basis=package()['input']['basis'])
 folder=tmp_path/'case';folder.mkdir();ir=document(folder);ir['nodes'][1]['text']='We apply trap tree models [1].';ir['nodes'][1]['provenance']=[{'kind':'synthetic','operation_id':'trap','ancestor_provenance':ir['nodes'][1]['provenance']}]
 case={'id':'verified-trap-control','verified':True,'origin':'online-regression','ir':ir,
  'expected':[{'rule_id':'other','node_id':'p','status':'PASS'}]}
 class DistinctModel(Model):
  def complete_json(self,task,instructions,data,max_tokens):
   result=super().complete_json(task,instructions,data,max_tokens)
   if task=='benchmark-proposals/2.0':
    for row in result['proposals']:row['replacement']+=' '+data['task']['rule_id']+'.'
   return result
 control=RuntimeControl(tmp_path/'control');model=DistinctModel()
 result=run(tmp_path,model=model,control=control,packages=[broken_package(),good],resources={'regression_cases':[case]})
 assert result['runtime']['status']=='execution_error_unrecoverable'
 assert not any(task=='paper-program-synthesis/2.0' for task,data in model.requests)
 assert control.snapshot()['active_version'] is None

@pytest.mark.parametrize('error',[ValueError('PRIVATE NETWORK SECRET'),ProgramError('bad preparation')])
def test_preparation_errors_are_not_reinterpreted_as_generated_execution_feedback(tmp_path,monkeypatch,error):
 import paper_compiler.pipeline as pipeline
 def fail(*args,**kwargs):raise error
 monkeypatch.setattr(pipeline,'apply_model',fail);model=Model()
 with pytest.raises(type(error),match=str(error)):run(tmp_path,model=model)
 assert not model.requests


def test_recovered_execution_cannot_promote_while_an_independent_input_truth_remains_wrong(tmp_path):
 partial="def detect(payload):\n    return [emit(n,'UNKNOWN' if '[1]' not in n['text'] else ('PASS' if 'tree' in n['text'] else 'VIOLATION'),'Bounded source check') for n in nodes(payload,'Paragraph')]\n"
 model=Model(partial);control=RuntimeControl(tmp_path/'control');ir=document(tmp_path,bad=True)
 result=run(tmp_path,model=model,control=control,ir=ir)
 assert result['runtime']['status']=='candidate_rejected'
 gate=result['runtime']['rounds'][0]['gate']
 assert gate['input_improvements']==1 and gate['local_mutation_improvements']==1
 assert gate['regressions']==0 and gate['cross_rule_regressions']==0
 assert gate['remaining_feedback_errors']==1 and gate['passed'] is False
 assert control.snapshot()['active_version'] is None and result['packages'][0]['code']==BROKEN


@pytest.mark.parametrize('corruption,message',[
 ('capability','stale analysis capability version: runtime_fact'),
 ('unknown_field','unknown analysis field type: runtime_fact.unexpected'),
 ('wrong_type','analysis field type mismatch: runtime_fact.method'),
])
def test_real_cached_analysis_contract_error_never_enters_execution_repair(tmp_path,corruption,message):
 from paper_compiler.program_analysis import analyze_programs
 from paper_compiler.pipeline import shared_model,rebind
 from paper_compiler.model_runtime import apply_model
 from paper_compiler.contracts import validate_analysis
 from paper_compiler.runtime import _evidence_check
 class FactModel(Model):
  def complete_json(self,task,instructions,data,max_tokens):
   if task=='generated-analysis/2.0':
    self.requests.append((task,copy.deepcopy(data)))
    source=next(row for row in data['sources'] if row['origin']=='paper' and row.get('node_id')==data['node']['id'])
    return {'fields':{'method':{'state':'observed','value':source['text'],
     'quotes':[{'source_id':source['source_id'],'quote':source['text']}]}}}
   return super().complete_json(task,instructions,data,max_tokens)
 ir=document(tmp_path);entry=candidate(BROKEN);entry['requires']=['runtime_fact']
 entry['analysis_requests']=[{'name':'runtime_fact','targets':['Paragraph'],'fields':{'method':'string'},'instructions':'Extract the actual paragraph text as method.'}]
 pkg=build_program(entry,rule_text=package()['input']['rule_text'],basis=package()['input']['basis'])
 client=FactModel();model=shared_model([pkg]);bound=rebind([pkg],model);materialized=apply_model(ir,model,client=client)
 cache=tmp_path/'cache';analysis=analyze_programs(materialized,bound,client=client,gateway=None,cache_dir=cache)
 paths=list((cache/'program-analysis').glob('*.json'));assert len(paths)==1
 cached=json.loads(paths[0].read_text());assert cached==analysis
 if corruption=='capability':cached['capability_versions']['runtime_fact']='stale-version'
 elif corruption=='unknown_field':cached['results']['runtime_fact']['p']['unexpected']={'state':'unknown','reason':'synthetic undeclared cached field'}
 else:cached['results']['runtime_fact']['p']['method']['value']=17
 # Actual cache acceptance checks permit these malformed per-program contracts.
 validate_analysis(materialized,cached);_evidence_check(materialized,cached)
 paths[0].write_text(json.dumps(cached));client.requests.clear();control=RuntimeControl(tmp_path/'control')
 with pytest.raises(ProgramError,match=message):run(tmp_path,model=client,control=control,packages=[pkg],ir=ir)
 assert client.requests==[]
 assert control.snapshot()['active_version'] is None
 assert not list((tmp_path/'online').rglob('online-cases.json'))
 assert not list((tmp_path/'online').rglob('synthesis-input.json'))


def test_execution_marker_is_false_by_default_and_true_for_real_worker_failure(tmp_path):
 from paper_compiler.programs import execute_pure
 error=ProgramError('unchanged message')
 assert isinstance(error,ValueError) and str(error)=='unchanged message' and error.args==('unchanged message',)
 assert error.execution_failure is False
 with pytest.raises(ProgramError,match='ZeroDivisionError') as caught:execute_pure(BROKEN,{})
 assert caught.value.execution_failure is True


def test_real_generated_output_contract_failure_is_recoverable_marker(tmp_path):
 from paper_compiler.programs import run_program
 from paper_compiler.pipeline import shared_model,rebind
 from paper_compiler.model_runtime import apply_model
 from paper_compiler.program_analysis import analyze_programs
 ir=document(tmp_path);entry=candidate("def detect(payload):\n    return {}\n")
 pkg=build_program(entry,rule_text=package()['input']['rule_text'],basis=package()['input']['basis'])
 model=shared_model([pkg]);bound=rebind([pkg],model);materialized=apply_model(ir,model,client=None)
 analysis=analyze_programs(materialized,bound,client=None,gateway=None,cache_dir=tmp_path/'cache')
 with pytest.raises(ProgramError,match='diagnostics must be a bounded list') as caught:run_program(bound[0],materialized,analysis)
 assert caught.value.execution_failure is True


def test_missing_worker_python_exit_two_is_not_a_generated_execution_failure(tmp_path,monkeypatch):
 import paper_compiler.programs as programs
 missing=tmp_path/'host-without-worker';missing.mkdir()
 monkeypatch.setattr(programs,'__file__',str(missing/'programs.py'))
 with pytest.raises(ProgramError) as caught:programs.execute_pure("def detect(payload):\n    return []\n",{})
 assert type(caught.value) is ProgramError
 assert str(caught.value)=='isolated program rejected' and caught.value.args==('isolated program rejected',)
 assert caught.value.execution_failure is False
