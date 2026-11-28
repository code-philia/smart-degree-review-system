"""Complete missing status without making the model rewrite valid source fields."""
import copy
import pytest
import numeric_consistency as n
from test_numeric_consistency import fixture,valid_output


@pytest.mark.parametrize('missing',[True,False])
def test_status_only_reply_preserves_source_validated_reason_evidence_and_usage(missing):
    ir,facts,structure=fixture();candidates,_=n.retrieve_candidates(structure['declarations'],structure['mappings'],n.source_model(ir))
    initial=valid_output(candidates[0]);row=initial['results'][0]
    if missing:row.pop('status')
    else:row['status']='unknown'
    before=copy.deepcopy(initial);calls=[]
    def request(messages):
        calls.append(messages)
        return [structure,initial,{'results':[{'declaration_id':'d1','status':'inconsistent'}]}][len(calls)-1],{'input_tokens':2,'output_tokens':3}
    result=n.run_numeric(ir,facts,request)
    assert result['execution_status']=='completed' and len(calls)==3
    actual=result['params']['numeric_results'][0]
    assert actual['status']=='inconsistent' and actual['reason']==row['reason']
    assert actual['evidence'][0]['quote']==row['evidence'][0]['quote']
    assert initial==before and result['model_usage']=={'input_tokens':6,'output_tokens':9}


def test_source_repair_that_omits_status_gets_one_compact_completion():
    ir,facts,structure=fixture();candidates,_=n.retrieve_candidates(structure['declarations'],structure['mappings'],n.source_model(ir))
    valid=valid_output(candidates[0]);initial=copy.deepcopy(valid);initial['results'][0]['evidence'][0]['quote']='伪造原文'
    repaired=copy.deepcopy(valid);repaired['results'][0].pop('status');calls=[]
    def request(messages):
        calls.append(messages)
        return [structure,initial,repaired,{'results':[{'declaration_id':'d1','status':'inconsistent'}]}][len(calls)-1],{}
    result=n.run_numeric(ir,facts,request)
    assert result['execution_status']=='completed' and len(calls)==4
    assert result['params']['numeric_results'][0]['evidence'][0]['quote']==candidates[0]['text']


@pytest.mark.parametrize('answer',[
    {'results':[{'declaration_id':'wrong','status':'consistent'}]},
    {'results':[{'declaration_id':'d1','status':'PASS'}]},
    {'results':[{'declaration_id':'d1','status':'consistent'},{'declaration_id':'d1','status':'inconsistent'}]},
    {'results':[{'declaration_id':'d1','reason':'没有状态'}]},
])
def test_bad_status_completion_is_bounded_and_never_becomes_a_verdict(answer):
    ir,facts,structure=fixture();candidates,_=n.retrieve_candidates(structure['declarations'],structure['mappings'],n.source_model(ir))
    initial=valid_output(candidates[0]);initial['results'][0].pop('status');calls=[]
    def request(messages):
        calls.append(messages);return (structure if len(calls)==1 else initial if len(calls)==2 else answer),{}
    result=n.run_numeric(ir,facts,request)
    assert result['execution_status']=='error' and len(calls)==3
    assert result['params']['numeric_results'][0]['status']=='execution_error'


def test_status_completion_cannot_replace_valid_reason_or_evidence():
    ir,facts,structure=fixture();candidates,_=n.retrieve_candidates(structure['declarations'],structure['mappings'],n.source_model(ir))
    initial=valid_output(candidates[0]);initial['results'][0].pop('status');calls=[]
    answer={'results':[dict(declaration_id='d1',status='inconsistent',reason='替换原理由',evidence=[{'candidate_id':'fake'}])]}
    def request(messages):
        calls.append(messages);return (structure if len(calls)==1 else initial if len(calls)==2 else answer),{}
    result=n.run_numeric(ir,facts,request)
    assert result['execution_status']=='completed'
    actual=result['params']['numeric_results'][0]
    assert actual['reason']==initial['results'][0]['reason'] and actual['evidence'][0]['candidate_id']==candidates[0]['candidate_id']
