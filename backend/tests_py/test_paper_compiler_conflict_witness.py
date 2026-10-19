import inspect,json
from copy import deepcopy
from pathlib import Path
import pytest
from paper_compiler.program_analysis import _ground_fields
try:
    from paper_compiler import conflict_review as review
except ImportError:
    review=None
FIXTURES=json.loads((Path(__file__).parent/'fixtures'/'r33_positive_conflict_quotes.json').read_text())

def answered_wire(data):
    results={}
    for node in data['nodes']:
        paper=next(q for q in node['assertions'] if q['origin']=='paper')
        ext=next(q for q in reversed(node['assertions']) if q['origin']=='external')
        results[node['node']['id']]={'decision':'confirmed_conflict','same_entity':True,'same_property':True,'same_scope':True,'citation_purpose':'assertion','relation':'affirmation_vs_denial','reason':'The cited method positively has the property the citing assertion denies.','witness':{'citing':{'quote_span_id':paper['assertion_span_ids'][0],'entity':'cited method','property':'method capability','value':'denied','scope':'this method'},'cited':{'quote_span_id':ext['assertion_span_ids'][0],'entity':'cited method','property':'method capability','value':'affirmed','scope':'this method'}}}
    return {'results':results}

def answered(packet):
    return answered_wire(review.model_input(packet))

@pytest.mark.parametrize('fixture',FIXTURES,ids=lambda x:x['case_id'])
def test_real_positive_conflict_requires_independent_host_verification(fixture):
    f=deepcopy(fixture)
    unverified,_=_ground_fields(f['request'],f['raw'],f['data'],True)
    assert unverified['conflict']['state']=='unknown'
    if review is None:
        facts=unverified
    else:
        packet=review.prepare_review(f['request'],f['raw'],f['data'])
        proofs=review.accept_review(packet,answered(packet))
        facts,_=_ground_fields(f['request'],f['raw'],f['data'],True,conflict_verifications=proofs)
    assert facts['conflict']['state']=='observed'

def test_model_cannot_self_verify_in_raw():
    f=deepcopy(FIXTURES[0]);f['raw']['fields']['conflict']['verified']=True
    f['raw']['fields']['conflict']['witness']={'verified':True,'same_entity':True}
    facts,_=_ground_fields(f['request'],f['raw'],f['data'],True)
    assert facts['conflict']['state']=='unknown'

@pytest.mark.parametrize('decision',['insufficient','supported_nonconflict','missing_detail','topic_mismatch'])
def test_non_conflicts_never_mint_trusted_proof(decision):
    assert review is not None
    f=deepcopy(FIXTURES[0]);packet=review.prepare_review(f['request'],f['raw'],f['data']);answer=answered(packet)
    next(iter(answer['results'].values()))['decision']=decision
    assert review.accept_review(packet,answer)=={}

@pytest.mark.parametrize('change',[{'same_entity':False},{'same_scope':False},{'same_property':False},{'citation_purpose':'criticism'},{'citation_purpose':'comparison'},{'relation':'topic_difference'}])
def test_unsupported_entity_scope_or_purpose_cannot_be_a_conflict(change):
    assert review is not None
    f=deepcopy(FIXTURES[0]);packet=review.prepare_review(f['request'],f['raw'],f['data']);answer=answered(packet)
    next(iter(answer['results'].values())).update(change)
    assert review.accept_review(packet,answer)=={}

def test_review_packet_is_blind_to_analysis_answer_and_model_witness():
    assert review is not None
    f=deepcopy(FIXTURES[0]);f['raw']['fields']['conflict'].update(reason='SECRET_ANALYSIS_REASON',value='SECRET_ANALYSIS_VALUE',verified='SECRET_MODEL_VERIFIED')
    packet=review.prepare_review(f['request'],f['raw'],f['data'])
    wire=json.dumps(review.model_input(packet))
    assert 'SECRET_' not in wire
    assert 'expected' not in review.model_input(packet)

def test_false_quote_and_foreign_work_do_not_enter_review():
    assert review is not None
    f=deepcopy(FIXTURES[0]);f['raw']['fields']['conflict']['quotes'][0]['quote']='fabricated asserting text'
    assert review.prepare_review(f['request'],f['raw'],f['data'])['items']==[]
    f=deepcopy(FIXTURES[0]);f['data']['external_works']=[]
    assert review.prepare_review(f['request'],f['raw'],f['data'])['items']==[]

def test_review_cannot_quote_other_source_or_nonexact_text():
    assert review is not None
    f=deepcopy(FIXTURES[0]);packet=review.prepare_review(f['request'],f['raw'],f['data']);answer=answered(packet)
    next(iter(answer['results'].values()))['witness']['cited']['quote']='invented conflict'
    assert review.accept_review(packet,answer)=={}

def test_trusted_proof_is_invalidated_by_current_source_or_raw_change():
    assert review is not None
    f=deepcopy(FIXTURES[0]);packet=review.prepare_review(f['request'],f['raw'],f['data']);proofs=review.accept_review(packet,answered(packet))
    f['data']['sources'][0]['text']+=' extra'
    facts,_=_ground_fields(f['request'],f['raw'],f['data'],True,conflict_verifications=proofs)
    assert facts['conflict']['state']=='unknown'

def test_json_proof_and_raw_review_answer_do_not_bypass_trust_boundary():
    assert review is not None
    f=deepcopy(FIXTURES[0]);packet=review.prepare_review(f['request'],f['raw'],f['data']);answer=answered(packet)
    forged={packet['items'][0]['id']:{'verified':True,'answer':answer}}
    facts,_=_ground_fields(f['request'],f['raw'],f['data'],True,conflict_verifications=forged)
    assert facts['conflict']['state']=='unknown'

def test_no_conflict_proposal_means_no_review_items():
    assert review is not None
    f=deepcopy(FIXTURES[0]);f['raw']['fields']['conflict']['basis']='explicit_support'
    assert review.prepare_review(f['request'],f['raw'],f['data'])['items']==[]

@pytest.mark.parametrize('reason',['The paper never mentions this method.','A different topic is discussed.'])
def test_absence_or_topic_reason_remains_unknown_even_with_review(reason):
    assert review is not None
    f=deepcopy(FIXTURES[0]);f['raw']['fields']['conflict']['reason']=reason
    packet=review.prepare_review(f['request'],f['raw'],f['data']);proofs=review.accept_review(packet,answered(packet))
    facts,_=_ground_fields(f['request'],f['raw'],f['data'],True,conflict_verifications=proofs)
    assert facts['conflict']['state']=='unknown'


def test_host_token_does_not_survive_changed_model_value():
    f=deepcopy(FIXTURES[0]);packet=review.prepare_review(f['request'],f['raw'],f['data']);proofs=review.accept_review(packet,answered(packet))
    f['raw']['fields']['conflict']['value']=False
    facts,_=_ground_fields(f['request'],f['raw'],f['data'],True,conflict_verifications=proofs)
    assert facts['conflict']['state']=='unknown'

def test_review_witness_entity_and_property_must_match_both_assertions():
    f=deepcopy(FIXTURES[0]);packet=review.prepare_review(f['request'],f['raw'],f['data']);answer=answered(packet)
    next(iter(answer['results'].values()))['witness']['cited']['entity']='prior baseline'
    assert review.accept_review(packet,answer)=={}

def test_verified_observation_retains_auditable_review_spans():
    f=deepcopy(FIXTURES[0]);packet=review.prepare_review(f['request'],f['raw'],f['data']);proofs=review.accept_review(packet,answered(packet))
    facts,_=_ground_fields(f['request'],f['raw'],f['data'],True,conflict_verifications=proofs)
    receipt=facts['conflict']['conflict_verification'];assert receipt['policy']==review.POLICY
    sources={s['source_id']:s['text'] for s in f['data']['sources']}
    for side in ['citing','cited']:
        witness=receipt['witness'][side];start,end=witness['source_range']
        assert sources[witness['source_id']][start:end]==witness['quote']


@pytest.mark.parametrize('bad_id',[[],{}])
def test_malformed_independent_review_source_id_is_not_a_proof(bad_id):
    f=deepcopy(FIXTURES[0]);packet=review.prepare_review(f['request'],f['raw'],f['data']);answer=answered(packet)
    next(iter(answer['results'].values()))['witness']['cited']['source_id']=bad_id
    assert review.accept_review(packet,answer)=={}

def test_nonfinite_independent_review_metadata_is_not_a_proof():
    f=deepcopy(FIXTURES[0]);packet=review.prepare_review(f['request'],f['raw'],f['data']);answer=answered(packet)
    answer['non_json_score']=float('nan')
    assert review.accept_review(packet,answer)=={}

def test_invalid_raw_cannot_raise_while_checking_host_proof():
    f=deepcopy(FIXTURES[0]);f['raw']['fields']['conflict']['value']=float('nan')
    assert review.trusted_verification(f['raw']['fields']['conflict'],f['data'],{}) is None
