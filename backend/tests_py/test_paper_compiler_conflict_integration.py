import json
from copy import deepcopy
from pathlib import Path
import pytest
from test_paper_compiler_conflict_witness import FIXTURES,answered,answered_wire
from test_paper_compiler_program_analysis import Model,Gateway,paper,package,grounded_reference
from paper_compiler import conflict_review as review
from paper_compiler.program_analysis import analyze_programs
from paper_compiler.budget import BudgetExceeded
from paper_compiler.runtime_control import RuntimeFrozen

class Reviewer:
    max_attempts=1
    def __init__(self,error=None):self.calls=0;self.error=error;self.inputs=[]
    def complete_json(self,task,instructions,data,max_tokens):
        self.calls+=1;self.inputs.append(deepcopy(data))
        assert task==review.TASK
        if self.error:raise self.error
        return answered_wire(data)

def resolve(f,client,receipt=None):
    assert hasattr(review,'resolve_review'),'independent review orchestration not wired'
    return review.resolve_review(f['request'],f['raw'],f['data'],client=client,receipt=receipt)

def test_review_receipt_replays_without_second_paid_call():
    f=deepcopy(FIXTURES[0]);client=Reviewer()
    proofs,receipt,reason=resolve(f,client)
    assert proofs and reason is None and client.calls==1
    again,record,reason=resolve(f,Reviewer(AssertionError('must use receipt')),receipt)
    assert again and reason is None

def test_ordinary_review_error_is_reasoned_and_cached():
    f=deepcopy(FIXTURES[0]);client=Reviewer(ValueError('bad output'))
    proofs,receipt,reason=resolve(f,client)
    assert not proofs and reason and receipt['status']=='error'
    assert resolve(f,Reviewer(AssertionError('must not resend')),receipt)[2]==reason

@pytest.mark.parametrize('error',[BudgetExceeded('cap'),RuntimeFrozen('freeze')])
def test_budget_and_freeze_propagate(error):
    with pytest.raises(type(error)):resolve(deepcopy(FIXTURES[0]),Reviewer(error))

def test_source_change_invalidates_review_receipt():
    f=deepcopy(FIXTURES[0]);client=Reviewer();_,receipt,_=resolve(f,client)
    f['data']['sources'][0]['text']+=' new context'
    resolve(f,client,receipt);assert client.calls==2

def test_old_success_or_missing_topic_paths_do_not_call_review():
    for change in [{'basis':'explicit_support'},{'reason':'The source never mentions this fact.'}]:
        f=deepcopy(FIXTURES[0]);f['raw']['fields']['conflict'].update(change)
        assert resolve(f,Reviewer(AssertionError('unexpected review')))[0]=={}

class AnalysisModel(Model):
    max_attempts=1
    def __init__(self,error=None):
        super().__init__(lambda d:grounded_reference(d,False,'explicit_scope_contradiction','The asserted method property conflicts with the cited property.'))
        self.reviewer=Reviewer(error)
    def complete_json(self,task,instructions,data,max_tokens):
        if task==review.TASK:return self.reviewer.complete_json(task,instructions,data,max_tokens)
        return super().complete_json(task,instructions,data,max_tokens)

def test_real_analysis_commit_and_node_cache_reuse_trusted_review(tmp_path):
    model=AnalysisModel();ir=paper(tmp_path);pkg=package('ReferenceUse',{'related':'boolean'});gateway=Gateway();cache=tmp_path/'cache'
    first=analyze_programs(ir,[pkg],client=model,gateway=gateway,cache_dir=cache)
    assert first['results']['method_facts']['use']['related']['state']=='observed'
    assert model.reviewer.calls==1
    node=list((cache/'generated-nodes').glob('*.json'))[0]
    assert json.loads(node.read_text())['conflict_review']['status']=='completed'
    for f in (cache/'program-analysis').glob('*.json'):f.unlink()
    second=analyze_programs(ir,[pkg],client=model,gateway=gateway,cache_dir=cache)
    assert second['results']['method_facts']['use']['related']==first['results']['method_facts']['use']['related']
    assert model.reviewer.calls==1

def test_analysis_caches_review_error_as_unknown(tmp_path):
    model=AnalysisModel(ValueError('bad review'));ir=paper(tmp_path);pkg=package('ReferenceUse',{'related':'boolean'});gateway=Gateway();cache=tmp_path/'cache'
    first=analyze_programs(ir,[pkg],client=model,gateway=gateway,cache_dir=cache)
    fact=first['results']['method_facts']['use']['related'];assert fact['state']=='unknown' and 'review' in fact['reason']
    for f in (cache/'program-analysis').glob('*.json'):f.unlink()
    second=analyze_programs(ir,[pkg],client=model,gateway=gateway,cache_dir=cache)
    assert second['results']['method_facts']['use']['related']==fact and model.reviewer.calls==1


def test_online_ground_judgments_uses_independent_review_and_receipt(tmp_path):
    from paper_compiler.online_loop import _ground_judgments
    f=deepcopy(FIXTURES[0]);ir=paper(tmp_path);node=next(n for n in ir['nodes'] if n['id']=='use')
    data=f['data'];norm={'id':'purpose','text':'The cited work must support this specific attributed property.'}
    program={'input':{'basis':[norm]}}
    item=f['raw']['fields']['conflict']
    row={'rule_id':'33','node_id':'use','status':'VIOLATION','reason':item['reason'],'basis':'explicit_scope_contradiction','basis_ids':['purpose'],'quotes':item['quotes']+[{'source_id':'purpose','quote':norm['text']}]}
    views={('33','use'):(data,program,node)};answer={'judgments':[row]}
    assert _ground_judgments(answer,views,ir)=={}
    client=Reviewer();receipts={}
    result=_ground_judgments(answer,views,ir,client=client,review_receipts=receipts)
    assert result[('33','use')]['status']=='VIOLATION' and client.calls==1
    assert _ground_judgments(answer,views,ir,client=client,review_receipts=receipts)==result
    assert client.calls==1
    with pytest.raises(RuntimeFrozen):_ground_judgments(answer,views,ir,client=Reviewer(RuntimeFrozen('frozen')))


@pytest.mark.parametrize('bad_id',[[],{}])
def test_malformed_quote_source_id_is_unknown_without_review(bad_id):
    f=deepcopy(FIXTURES[0]);f['raw']['fields']['conflict']['quotes'][0]['source_id']=bad_id
    assert resolve(f,Reviewer(AssertionError('malformed input must not call'))) == ({},None,None)

@pytest.mark.parametrize('field,value',[
    ('source_id',[]),('source_id',{}),('text',[]),('text',None),('node_id',[]),('origin',[]),
])
def test_malformed_source_metadata_does_not_raise_or_request(field,value):
    f=deepcopy(FIXTURES[0]);f['data']['sources'][0][field]=value
    assert resolve(f,Reviewer(AssertionError('malformed input must not call'))) == ({},None,None)

@pytest.mark.parametrize('kind,value',[
    ('context',[]),('context',{'node_id':[]}),('context',{'node_id':{}}),
    ('works',None),('works',[{'id':[]}]),('works',[{'id':{}}]),
])
def test_malformed_context_and_work_binding_fail_closed(kind,value):
    f=deepcopy(FIXTURES[0]);f['data']['citation_context' if kind=='context' else 'external_works']=value
    assert resolve(f,Reviewer(AssertionError('malformed input must not call'))) == ({},None,None)

def test_unrelated_nan_field_keeps_original_unknown_on_review_error(tmp_path):
    def response(data):
        raw=grounded_reference(data,False,'explicit_scope_contradiction','The asserted method property conflicts with the cited property.')
        raw['fields']['score']={'state':'observed','value':float('nan'),'quotes':raw['fields']['related']['quotes'],'basis':'explicit_scope_contradiction','reason':'An invalid numeric producer field.'}
        return raw
    class BadReview(Model):
        max_attempts=1
        def complete_json(self,task,instructions,data,max_tokens):
            if task==review.TASK:raise ValueError('ordinary independent review failure')
            return super().complete_json(task,instructions,data,max_tokens)
    result=analyze_programs(paper(tmp_path),[package('ReferenceUse',{'related':'boolean','score':'number'})],client=BadReview(response),gateway=Gateway(),cache_dir=tmp_path/'cache')
    facts=result['results']['method_facts']['use']
    assert facts['related']['state']=='unknown' and 'review' in facts['related']['reason']
    assert facts['score']['state']=='unknown' and 'review' not in facts['score']['reason']
