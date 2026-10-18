"""End-to-end regressions for independently reviewed online integration failures."""
import copy
import pytest
from paper_compiler.model_runtime import base_model,extend_model
from paper_compiler.programs import build_program
from paper_compiler.pipeline import save_suite,load_suite
from paper_compiler.runtime_control import RuntimeControl
from test_paper_compiler_online_loop import Model,package,candidate,call,mutant,OLD,FIX
from test_paper_compiler_program_analysis import paper

def activate(control,packages,path):
    manifest=save_suite(packages,path,validated=True,validation={'test_fixture':True})
    parent=control.snapshot()
    control.promote(manifest['version_id'],path,parent['active_version'],expected_generation=parent['generation'])
    return control.snapshot()

def test_snapshot_loaded_before_concurrent_release_cannot_be_reparented(tmp_path):
    old=package();control=RuntimeControl(tmp_path/'control')
    loaded=activate(control,[old],tmp_path/'a')
    other=build_program(candidate(FIX),rule_text=old['input']['rule_text'],basis=old['input']['basis'])
    active=activate(control,[other],tmp_path/'b')
    model=Model()
    result=call(tmp_path,mutant(tmp_path),[old],model,control,parent_snapshot=loaded)
    assert result['runtime']['status']=='version_conflict'
    assert result['runtime']['report_version']['suite_version']==loaded['active_version']
    assert control.snapshot()['active_version']==active['active_version']
    assert model.tasks==[]

def test_shared_model_refinement_survives_unchanged_later_program(tmp_path):
    initial=extend_model(base_model(),{'node_types':{'Method':{'base_kind':'Section','description':'old scope','attrs':{}}}})
    old=package()
    one=build_program(candidate(OLD),rule_text=old['input']['rule_text'],basis=old['input']['basis'],model=initial)
    spec=candidate(OLD);spec['rule_id']='second'
    two=build_program(spec,rule_text=old['input']['rule_text'],basis=old['input']['basis'],model=initial)
    class Refiner(Model):
        def complete_json(self,task,instructions,data,max_tokens):
            response=super().complete_json(task,instructions,data,max_tokens)
            if 'judgments' in response:
                for row in response['judgments']:
                    if row['rule_id']=='second':row['status']='UNKNOWN'
            else:response['model_patch']={'node_types':{'Method':{'base_kind':'Section','description':'refined scope','attrs':{}}}}
            return response
    control=RuntimeControl(tmp_path/'control')
    result=call(tmp_path,mutant(tmp_path),[one,two],Refiner(),control)
    assert result['runtime']['status']=='promoted'
    assert all(p['model']['node_types']['Method']['description']=='refined scope' for p in result['packages'])
    assert len({p['model']['version'] for p in result['packages']})==1

def test_bounded_audit_allocates_targets_across_rules(tmp_path):
    from paper_compiler.online_loop import _packet
    from paper_compiler.analysis import base_analysis
    ir=paper(tmp_path)
    for index in range(12):
        node=copy.deepcopy(ir['nodes'][1]);node.update(id='extra'+str(index),children=[])
        ir['nodes'].append(node);ir['nodes'][0]['children'].append(node['id'])
    packages=[]
    for rid in ['first','second','third']:
        spec=candidate(OLD);spec['rule_id']=rid
        packages.append(build_program(spec,rule_text='Check paragraphs',basis=[]))
    packet,views=_packet(ir,base_analysis(ir),packages,None,None,limit=8)
    assert len(packet['targets'])==8
    assert {t['rule_id'] for t in packet['targets']}=={'first','second','third'}

def test_new_upload_cannot_undo_prior_verified_online_repair(tmp_path):
    control=RuntimeControl(tmp_path/'control')
    initial=call(tmp_path,mutant(tmp_path),[package()],Model(),control)
    assert initial['runtime']['status']=='promoted'
    first_version=control.snapshot()['active_version']
    ir=paper(tmp_path);ir['nodes'][1]['text']='We apply tree models with a forbidden assertion [1].'
    ir['nodes'][1]['provenance']=[{'kind':'synthetic','operation_id':'second-upload'}]
    class Overfits(Model):
        def complete_json(self,task,instructions,data,max_tokens):
            if task in {'online-evidence-audit/1.0','online-evidence-review/1.0'}:
                answer=super().complete_json(task,instructions,data,max_tokens)
                for row in answer['judgments']:row['status']='VIOLATION'
                return answer
            self.tasks.append(task)
            return candidate("def detect(payload):\n    return [emit(n,'VIOLATION' if 'forbidden' in n['text'] else 'PASS','Checked source') for n in nodes(payload,'Paragraph')]")
    model=Overfits()
    result=call(tmp_path,ir,initial['packages'],model,control,max_rounds=1)
    assert result['runtime']['status']=='candidate_rejected'
    assert control.snapshot()['active_version']==first_version
    gate=result['runtime']['rounds'][0]['gate']
    assert gate['verified_regression_cases']>=1 and gate['regressions']>0
