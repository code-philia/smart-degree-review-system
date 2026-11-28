"""TPM budget lifecycle and shared quota behavior across campus transports."""
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import time
from urllib.error import HTTPError

import pytest

from paper_compiler import campus_requests as api

URL='https://models.sjtu.edu.cn/api/v1/chat/completions'

class Clock:
    def __init__(self):self.now=1000.0
    def time(self):return self.now
    def monotonic(self):return self.now
    def sleep(self,seconds):self.now+=seconds

@pytest.fixture
def controlled(tmp_path,monkeypatch):
    clock=Clock();path=tmp_path/'campus.sqlite'
    monkeypatch.setattr(api,'time',clock)
    monkeypatch.setenv('SJTU_API_COORDINATOR_DB',str(path))
    monkeypatch.setenv('SJTU_API_TOKENS_PER_MINUTE','100')
    monkeypatch.delenv('SJTU_API_REQUESTS_PER_MINUTE_OVERRIDE',raising=False)
    return clock,path

def payload(cap=60):return {'model':'test','messages':[{'role':'user','content':'abcd'}],'max_tokens':cap}
def usage(before=1,after=9):return {'usage':{'prompt_tokens':before,'completion_tokens':after,'total_tokens':before+after}}
def counts(path):
    with sqlite3.connect(path) as db:
        return {name:db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ['waiters','leases','token_waiters','token_reservations']}

@pytest.mark.parametrize('body,expected',[
    ({'messages':[{'content':'abc'},{'content':'12345'}],'max_tokens':8192},8194),
    ({'messages':[{'content':[{'text':'甲乙'},{'text':'丙丁'}]}],'max_tokens':10},11),
    ({'messages':[{'content':'abcd'}],'max_completion_tokens':17},18),
    ({'prompt':'abcdefgh','max_tokens':10},12),
    ({'input':['abc','de']},1),
    ({'messages':[{'content':'a'*100}]},1049),
])
def test_estimate_matches_verified_gateway_text_policy(body,expected):
    assert api.estimate_request_tokens(body)==expected

@pytest.mark.parametrize('bad',[-1,True,1.5,'8192'])
def test_invalid_declared_output_budget_is_rejected(bad):
    with pytest.raises(ValueError):api.estimate_request_tokens(payload(bad))

def test_window_reservations_preserve_rpm_pacing_and_bound_tpm(controlled):
    clock,path=controlled;starts=[]
    def send(timeout):
        starts.append(clock.now)
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT sum(tokens) FROM token_reservations').fetchone()[0]<=100
        return usage()
    for _ in range(10):api.campus_request(URL,{},.1,send,payload=payload(10))
    assert starts[:4]==pytest.approx([1000,1000.6,1001.2,1001.8])
    assert starts[9]>=1060
    assert counts(path)['leases']==counts(path)['waiters']==counts(path)['token_waiters']==0

def test_tpm_wait_uses_no_rpm_ticket_or_concurrent_slot(controlled):
    _,path=controlled;gate=api.CampusRequestCoordinator(path,tokens_per_minute=100)
    with gate.token_slot('same',{'estimated':80},timeout=10):
        with pytest.raises(TimeoutError):
            with gate.token_slot('same',{'estimated':30},timeout=.1):pytest.fail('Budget must queue')
        assert counts(path)==dict(waiters=0,leases=0,token_waiters=0,token_reservations=1)
    assert counts(path)['token_reservations']==0

def test_unsent_budget_is_returned_if_cancelled_while_in_rpm_queue(controlled,monkeypatch):
    clock,path=controlled;gate=api.CampusRequestCoordinator(path,max_concurrent=1,tokens_per_minute=100)
    with gate.slot('same',timeout=10):
        def interrupt(_):raise KeyboardInterrupt()
        monkeypatch.setattr(clock,'sleep',interrupt)
        with pytest.raises(KeyboardInterrupt):
            budget={'estimated':80}
            with gate.token_slot('same',budget,timeout=10) as identity:
                with gate.slot('same',timeout=2,token_reservation=identity):pytest.fail('Concurrent slot is occupied')
        assert counts(path)==dict(waiters=0,leases=1,token_waiters=0,token_reservations=0)

def test_scope_expiring_just_before_send_refunds_unsent_budget(controlled):
    _,path=controlled;gate=api.CampusRequestCoordinator(path,tokens_per_minute=100);checks=[]
    def remaining():
        checks.append(1)
        if len(checks)==2:raise TimeoutError('scope expired')
        return 1
    with pytest.raises(TimeoutError,match='scope expired'):
        with gate.token_slot('same',{'estimated':80},timeout=1) as identity:
            with gate.slot('same',timeout=1,token_reservation=identity,remaining_time=remaining):pytest.fail('unsent')
    assert all(value==0 for value in counts(path).values())

def test_large_actual_usage_saturates_budget_without_sql_integer_overflow(controlled):
    clock,_=controlled;starts=[]
    def send(timeout):
        starts.append(clock.now)
        return usage() if len(starts)==1 else usage(2**63-2,1)
    for _ in range(3):api.campus_request(URL,{},1,send,payload=payload(79))
    assert starts[2]>=starts[1]+60

def test_inflight_budget_is_shared_and_does_not_expire_after_one_minute(controlled):
    clock,path=controlled
    first=api.CampusRequestCoordinator(path,tokens_per_minute=100)
    second=api.CampusRequestCoordinator(path,tokens_per_minute=100)
    budget={'estimated':80}
    with first.token_slot('same',budget,timeout=120) as identity:
        with first.slot('same',timeout=120,token_reservation=identity):
            clock.now+=61
            with pytest.raises(TimeoutError):
                with second.token_slot('same',{'estimated':30},timeout=.1):pytest.fail('In-flight budget was lost')
            with second.token_slot('other',{'estimated':100},timeout=.1):pass
            budget['actual']=10
    clock.now+=61
    with second.token_slot('same',{'estimated':80},timeout=1):pass
    assert counts(path)['token_waiters']==0

def test_live_reservation_and_api_lease_renew_past_socket_timeout(controlled,monkeypatch):
    clock,path=controlled;gate=api.CampusRequestCoordinator(path,max_concurrent=1,tokens_per_minute=100)
    monkeypatch.setattr(api,'_RESERVATION_HEARTBEAT_SECONDS',.01,raising=False)
    with gate.token_slot('same',{'estimated':80},timeout=.1) as identity:
        with gate.slot('same',timeout=.1,token_reservation=identity):
            clock.now+=61;time.sleep(.08)
            with sqlite3.connect(path) as db:
                assert db.execute('SELECT expires_at FROM token_reservations WHERE id=?',(identity,)).fetchone()[0]>clock.now
                assert db.execute('SELECT expires_at FROM leases WHERE id=?',(identity,)).fetchone()[0]>clock.now
            with pytest.raises(TimeoutError):
                with gate.token_slot('same',{'estimated':30},timeout=.1):pytest.fail('in-flight budget lost')

def test_abandoned_unsent_budget_expires_even_if_pid_was_reused(controlled,monkeypatch):
    clock,path=controlled;gate=api.CampusRequestCoordinator(path,tokens_per_minute=100)
    monkeypatch.setattr(gate,'_process_alive',lambda pid:True)
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO token_reservations VALUES (?,?,?,?,0,?)',('old','same',100,os.getpid(),clock.now+.1))
    clock.now+=.2
    with gate.token_slot('same',{'estimated':30},timeout=.1):pass
    assert counts(path)['token_reservations']==0

@pytest.mark.parametrize('phase',['reserve','settle'])
def test_only_pre_send_credit_rejection_refunds_tpm_budget(controlled,monkeypatch,phase):
    from paper_compiler import account_credit as credit
    from types import SimpleNamespace
    clock,path=controlled;sent=[]
    def reject(*args):raise credit.CreditError('credit rejected')
    account=SimpleNamespace(reserve=reject if phase=='reserve' else lambda *args:'call',
                            settle=reject if phase=='settle' else lambda *args:None,failed=lambda *args:None)
    monkeypatch.setattr(credit,'AccountCredit',lambda *args:account)
    monkeypatch.setenv('PAPER_LINT_CREDIT_CONTEXT',json.dumps({'database_file':'test','operation_id':'test'}))
    def send(timeout):return credit.bill_model_request(payload(79),lambda:sent.append(clock.now) or usage())
    with pytest.raises(credit.CreditError):api.campus_request(URL,{},.1,send,payload=payload(79))
    assert counts(path)['token_reservations']==(0 if phase=='reserve' else 1)
    assert len(sent)==(0 if phase=='reserve' else 1)

def test_upgrading_legacy_database_holds_first_token_window(controlled):
    clock,path=controlled
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE accounts (id TEXT PRIMARY KEY,next_at REAL NOT NULL,blocked_until REAL NOT NULL)')
        db.execute('INSERT INTO accounts VALUES (?,0,0)',('same',))
    first=api.CampusRequestCoordinator(path,tokens_per_minute=100)
    with pytest.raises(TimeoutError):
        with first.token_slot('same',{'estimated':30},timeout=.1):pytest.fail('legacy usage is unknown')
    clock.now=1061
    second=api.CampusRequestCoordinator(path,tokens_per_minute=100)
    with second.token_slot('same',{'estimated':30},timeout=.1):pass

@pytest.mark.parametrize('response',[
    {},{'usage':{'prompt_tokens':True,'completion_tokens':1}},
    {'usage':{'prompt_tokens':-1,'completion_tokens':1}},
    {'usage':{'prompt_tokens':1,'completion_tokens':2,'total_tokens':99}},
    {'usage':{'prompt_tokens':10**40,'completion_tokens':1}},
])
def test_missing_or_invalid_usage_keeps_conservative_budget_for_a_minute(controlled,response):
    clock,_=controlled;starts=[]
    for _ in range(2):api.campus_request(URL,{},.1,lambda timeout:starts.append(clock.now) or response,payload=payload(79))
    assert starts[1]>=starts[0]+60

def test_known_429_rejection_refunds_budget_and_retains_shared_retry_after(controlled):
    clock,path=controlled;starts=[]
    def send(timeout):
        starts.append(clock.now)
        if len(starts)==1:raise HTTPError(URL,429,'limited',{'Retry-After':'2'},None)
        return usage()
    api.campus_request(URL,{},.1,send,payload=payload(79))
    assert starts==pytest.approx([1000,1002])
    with sqlite3.connect(path) as db:assert db.execute('SELECT sum(tokens) FROM token_reservations').fetchone()[0]==80

def test_transport_timeout_releases_slot_but_keeps_uncertain_budget(controlled):
    clock,path=controlled
    def failed(timeout):raise TimeoutError('socket read')
    with pytest.raises(TimeoutError,match='socket read'):api.campus_request(URL,{},.1,failed,payload=payload(79))
    assert counts(path)['leases']==counts(path)['waiters']==counts(path)['token_waiters']==0
    starts=[];api.campus_request(URL,{},.1,lambda timeout:starts.append(clock.now) or usage(),payload=payload(79))
    assert starts[0]>=1060

def test_cancelling_tpm_wait_preserves_other_owner_budget(controlled,monkeypatch):
    clock,path=controlled;gate=api.CampusRequestCoordinator(path,tokens_per_minute=100)
    with gate.token_slot('same',{'estimated':80},timeout=10):
        monkeypatch.setattr(clock,'sleep',lambda _:(_ for _ in ()).throw(KeyboardInterrupt()))
        with pytest.raises(KeyboardInterrupt):
            with gate.token_slot('same',{'estimated':30},timeout=1):pass
        assert counts(path)==dict(waiters=0,leases=0,token_waiters=0,token_reservations=1)
    assert counts(path)['token_reservations']==0

@pytest.mark.parametrize('inflight',[False,True])
def test_dead_owner_refunds_unsent_only_and_bounds_uncertain_inflight(controlled,monkeypatch,inflight):
    clock,path=controlled;gate=api.CampusRequestCoordinator(path,tokens_per_minute=100)
    monkeypatch.setattr(gate,'_process_alive',lambda pid:pid!=999999999)
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO token_reservations (id,account_id,tokens,pid,state,expires_at) VALUES (?,?,?,?,?,?)',('dead','same',80,999999999,1 if inflight else 0,clock.now+300))
    if inflight:
        with pytest.raises(TimeoutError):
            with gate.token_slot('same',{'estimated':30},timeout=.1):pass
        clock.now=1061
    with gate.token_slot('same',{'estimated':30},timeout=1):pass
    assert counts(path)['token_reservations']==0

def test_oversized_single_request_fails_before_any_http_or_queue_leak(controlled):
    _,path=controlled;sent=[]
    with pytest.raises(ValueError,match='token budget'):
        api.campus_request(URL,{},1,lambda timeout:sent.append(1),payload=payload(100))
    assert sent==[]
    assert all(value==0 for value in counts(path).values())

def test_compiler_transport_supplies_budget_before_sending(controlled,monkeypatch):
    clock,_=controlled;from paper_compiler import llm
    monkeypatch.setenv('SJTU_API_TOKENS_PER_MINUTE','7000');starts=[]
    monkeypatch.setattr(llm,'_http_request',lambda *args:starts.append(clock.now) or usage(1499,1))
    body={'messages':[{'role':'user','content':'x'*2000}],'max_tokens':5500}
    llm._http(URL,{},body,1);llm._http(URL,{},body,1)
    assert starts[1]>=starts[0]+60

def test_semantic_transport_supplies_budget_before_sending(controlled,monkeypatch):
    clock,_=controlled;monkeypatch.setenv('SJTU_API_TOKENS_PER_MINUTE','10000')
    monkeypatch.setenv('SJTU_API_KEY','private-test');monkeypatch.setenv('SJTU_API_BASE_URL',URL.rsplit('/chat/',1)[0]);monkeypatch.setenv('SJTU_API_MODEL','test')
    monkeypatch.delenv('SJTU_API_RESPONSE_CACHE_DIR',raising=False)
    spec=importlib.util.spec_from_file_location('token_semantic',Path(__file__).parents[1]/'scripts/run_bilingual_semantic_lint.py');semantic=importlib.util.module_from_spec(spec);spec.loader.exec_module(semantic)
    starts=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,_):return json.dumps({'choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}],**usage(3999,1)}).encode()
    class Opener:
        def open(self,*args,**kwargs):starts.append(clock.now);return Response()
    monkeypatch.setattr(semantic.urllib.request,'build_opener',lambda *args:Opener())
    semantic.request_json([{'role':'user','content':'abcd'}]);semantic.request_json([{'role':'user','content':'abcd'}])
    assert starts[1]>=starts[0]+60

def _budget_process(path,ready,start,result):
    gate=api.CampusRequestCoordinator(path,max_concurrent=32,tokens_per_minute=100)
    ready.put(True);assert start.wait(10)
    budget={'estimated':70}
    with gate.slot('shared',timeout=10,wait_for_capacity=True,token_budget=budget):
        began=time.time();time.sleep(1.2);budget['rejected']=True;result.put((began,time.time()))

def test_tpm_reservation_is_atomic_across_real_processes(tmp_path):
    context=multiprocessing.get_context('spawn');ready=context.Queue();result=context.Queue();start=context.Event()
    processes=[context.Process(target=_budget_process,args=(tmp_path/'process.sqlite',ready,start,result)) for _ in range(3)]
    try:
        for p in processes:p.start()
        for _ in processes:assert ready.get(timeout=5)
        start.set();intervals=[result.get(timeout=10) for _ in processes]
        events=sorted([(a,1) for a,b in intervals]+[(b,-1) for a,b in intervals]);active=peak=0
        for _,delta in events:active+=delta;peak=max(peak,active)
        assert peak==1
    finally:
        for p in processes:
            p.join(3)
            if p.is_alive():p.terminate();p.join(3)
    assert all(p.exitcode==0 for p in processes)
