"""Gateway refunds are asynchronous; small task caps keep single papers responsive."""
import io
import json
import sqlite3
import os
from types import SimpleNamespace
import pytest
from paper_compiler import campus_requests as api
from test_campus_token_budget import controlled,usage
from test_semantic_response_cache import semantic


def test_completed_response_does_not_release_unacknowledged_gateway_budget(controlled):
    clock,path=controlled;gate=api.CampusRequestCoordinator(path,tokens_per_minute=100)
    budget={'estimated':80}
    with gate.slot('same',timeout=1,token_budget=budget):budget['actual']=10
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT sum(tokens) FROM token_reservations').fetchone()[0]==80
    with pytest.raises(TimeoutError):
        with gate.slot('same',timeout=.1,token_budget={'estimated':30}):pytest.fail('gateway has not acknowledged a refund')
    clock.now+=61
    with gate.slot('same',timeout=1,token_budget={'estimated':30,'rejected':True}):pass


def test_successful_zero_usage_is_distinct_from_known_preflight_rejection(controlled):
    _,path=controlled;gate=api.CampusRequestCoordinator(path,tokens_per_minute=100)
    with gate.slot('zero',timeout=1,token_budget={'estimated':80,'actual':0}):pass
    with gate.slot('rejected',timeout=1,token_budget={'estimated':80,'rejected':True}):pass
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT account_id,tokens FROM token_reservations').fetchall()==[('zero',80)]


@pytest.mark.parametrize('contract,first_cap', [('typo-discovery',2048),('typo-review',512),('typo-fields',512)])
def test_stage_caps_expand_on_truncation_without_losing_usage(semantic,monkeypatch,contract,first_cap):
    module,_,_,_=semantic;calls=[]
    def opened(request,**kwargs):
        calls.append(json.loads(request.data))
        content={'errors':[]} if contract=='typo-discovery' else {'accepted':False,'reason':'无法确认'}
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':'length' if len(calls)==1 else 'stop','message':{'content':json.dumps(content)}}],
            'usage':{'prompt_tokens':12,'completion_tokens':7}}).encode())
    monkeypatch.setattr(module.urllib.request,'build_opener',lambda *a:SimpleNamespace(open=opened))
    result,total=module.request_json([{'role':'user','content':'原文。'}],response_contract=contract)
    assert [x['max_tokens'] for x in calls]==[first_cap,first_cap*2]
    assert total=={'input_tokens':24,'output_tokens':14}


def test_output_expansion_is_bounded_at_original_ceiling(semantic,monkeypatch):
    module,calls,response,_=semantic
    response['choices'][0]['finish_reason']='length';response['choices'][0]['message']['content']='{"errors":[]}'
    with pytest.raises(ValueError,match='输出达到上限') as caught:
        module.request_json([{'role':'user','content':'原文。'}],response_contract='typo-discovery')
    assert [x['max_tokens'] for x in calls]==[2048,4096,8192]
    assert caught.value.known_model_usage=={'input_tokens':36,'output_tokens':21}


def test_upgrade_from_immediate_settlement_waits_only_one_window(controlled):
    clock,path=controlled;api.CampusRequestCoordinator(path,tokens_per_minute=100)
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM quota_meta WHERE id='tpm-safe-window-v2'")
        db.execute("INSERT OR IGNORE INTO quota_meta VALUES ('tpm-deferred-refund-v1',0)")
        db.execute('INSERT INTO token_reservations VALUES (?,?,?,?,2,?)',('old','same',5,os.getpid(),1060))
    gate=api.CampusRequestCoordinator(path,tokens_per_minute=100)
    with pytest.raises(TimeoutError):
        with gate.slot('same',timeout=.1,token_budget={'estimated':30}):pytest.fail('old refunds may not be acknowledged')
    clock.now=1030
    api.CampusRequestCoordinator(path,tokens_per_minute=100)
    clock.now=1061
    with gate.slot('same',timeout=1,token_budget={'estimated':30,'rejected':True}):pass
