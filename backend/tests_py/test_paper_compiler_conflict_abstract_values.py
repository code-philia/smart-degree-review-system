"""Actual abstract-only review counterexamples: retain raw, conservatively withhold alerts."""
from copy import deepcopy
from pathlib import Path
import hashlib,json
import pytest
from paper_compiler import conflict_review as review
from paper_compiler.program_analysis import _ground_fields
from paper_compiler.llm import MaasClient
from paper_compiler.budget import BudgetLedger
from paper_compiler.storage import json_bytes,write_json_atomic
from test_paper_compiler_llm import config
from test_paper_compiler_conflict_witness import FIXTURES,answered

ACTUAL=json.loads((Path(__file__).parent/'fixtures/r33_abstract_mutual_value_counterexamples.json').read_text())

@pytest.mark.parametrize('fixture',ACTUAL,ids=lambda f:f['node_id'])
def test_actual_abstract_numeric_role_and_comparison_do_not_seal_conflict(fixture):
    before=deepcopy(fixture)
    packet=review.prepare_review(fixture['request'],fixture['raw'],fixture['data'])
    proofs=review.accept_review(packet,fixture['receipt']['answer'])
    facts,_=_ground_fields(fixture['request'],fixture['raw'],fixture['data'],True,conflict_verifications=proofs)
    assert proofs=={} and facts['relation']['state']=='unknown'
    assert fixture==before

@pytest.mark.parametrize('coverage,complete,accepted',[
    ('abstract_only',False,False),('abstract_only',True,False),('full_text',False,False),
    ('partial',True,False),('full_text',True,True)])
def test_mutual_values_require_complete_full_text_source(coverage,complete,accepted):
    f=deepcopy(FIXTURES[0])
    for source in f['data']['sources']:
        if source['origin']=='external':source.update(coverage=coverage,complete=complete)
    packet=review.prepare_review(f['request'],f['raw'],f['data']);answer=answered(packet)
    next(iter(answer['results'].values()))['relation']='mutually_exclusive_values'
    assert bool(review.accept_review(packet,answer)) is accepted


def test_abstract_explicit_affirmation_denial_still_seals():
    f=deepcopy(FIXTURES[0])
    for source in f['data']['sources']:
        if source['origin']=='external':source.update(coverage='abstract_only',complete=False)
    packet=review.prepare_review(f['request'],f['raw'],f['data'])
    assert review.accept_review(packet,answered(packet))


def test_new_host_policy_rechecks_old_review_using_exact_successful_wire_cache(tmp_path):
    f=deepcopy(ACTUAL[0]);before=deepcopy(f)
    packet=review.prepare_review(f['request'],f['raw'],f['data'])
    assert review.model_input(packet)==f['old_wire']
    assert review.POLICY!=f['receipt']['policy']
    def forbidden_transport(*args):raise AssertionError('no HTTP permitted')
    client=MaasClient(config(tmp_path),BudgetLedger(tmp_path/'ledger.sqlite3','10'),tmp_path/'cache','test','5',
        transport=forbidden_transport,max_attempts=1,semantic_thinking=True,json_output=True,input_serialization='unicode-json/1.0')
    key=hashlib.sha256(json_bytes(client.request_fingerprint(review.TASK,review.INSTRUCTIONS,f['old_wire'],24000))).hexdigest()
    cache=client.cache_dir/'responses'/(key+'.json')
    write_json_atomic(cache,{'input_hash':key,'result':f['receipt']['answer'],'request_id':'old-success','usage':{'prompt_tokens':1,'completion_tokens':1}})
    raw_bytes=cache.read_bytes()
    proofs,record,reason=review.resolve_review(f['request'],f['raw'],f['data'],client=client,receipt=f['receipt'])
    assert proofs=={} and record['policy']==review.POLICY and record['input_hash']!=f['receipt']['input_hash']
    assert reason and client.ledger.summary()['requests']==0
    assert cache.read_bytes()==raw_bytes and f==before
