"""Evidence absence is uncertainty; malformed citations remain technical errors."""
import copy
import pytest
import numeric_consistency as n
from test_numeric_consistency import fixture, valid_output


@pytest.mark.parametrize('status',['consistent','inconsistent'])
def test_no_cited_evidence_is_an_info_finding_without_a_verdict_or_retry(status):
    ir,facts,structure=fixture();calls=[]
    answer={'results':[dict(declaration_id='d1',status=status,reason='未找到目标数值的直接证据。',suggestion='请补充实验依据。',evidence=[])]}
    before=copy.deepcopy(answer)
    def request(messages):
        calls.append(messages)
        return (structure if len(calls)==1 else answer),{'input_tokens':2,'output_tokens':3}
    result=n.run_numeric(ir,facts,request)
    assert result['execution_status']=='completed'
    assert result['params']['coverage']=={'expected':1,'returned_valid':1,'complete':True}
    row=result['params']['numeric_results'][0]
    assert row['status']=='inconclusive' and row['evidence']==[]
    assert row['reason']==answer['results'][0]['reason']
    assert row['contract_normalizations']==['verdict_without_cited_evidence']
    assert result['findings'][0]['severity']=='info' and '论据不明确' in result['findings'][0]['message']
    assert len(calls)==2 and result['model_usage']=={'input_tokens':4,'output_tokens':6}
    assert answer==before


@pytest.mark.parametrize('missing',[False,True])
def test_empty_optional_suggestion_preserves_model_uncertainty(missing):
    ir,facts,structure=fixture();calls=[]
    answer={'results':[dict(declaration_id='d1',status='inconclusive',reason='候选证据不足以确认该声明。',suggestion=None,evidence=[])]}
    if missing:answer['results'][0].pop('suggestion')
    def request(messages):
        calls.append(messages);return (structure if len(calls)==1 else answer),{}
    result=n.run_numeric(ir,facts,request)
    assert result['execution_status']=='completed' and len(calls)==2
    assert result['params']['numeric_results'][0]['suggestion']==''
    assert result['findings'][0]['suggestion']=='' and result['findings'][0]['severity']=='info'
    assert answer['results'][0].get('suggestion') is None


@pytest.mark.parametrize('failure',['reason','missing_reason','bad_suggestion','quote','page','candidate'])
def test_compatibility_does_not_hide_malformed_or_ungrounded_results(failure):
    ir,facts,structure=fixture()
    candidates,_=n.retrieve_candidates(structure['declarations'],structure['mappings'],n.source_model(ir))
    payload=valid_output(candidates[0]);row=payload['results'][0]
    if failure=='reason':row.update(reason='',evidence=[])
    elif failure=='missing_reason':row.pop('reason');row['evidence']=[]
    elif failure=='bad_suggestion':row.update(suggestion=37,evidence=[])
    else:row['evidence'][0][{'quote':'quote','page':'page','candidate':'candidate_id'}[failure]]={'quote':'伪造原文','page':999,'candidate':'不存在'}[failure]
    results,errors=n.validated_results(payload,structure['declarations'],candidates)
    assert errors and results[0]['status']=='execution_error'
