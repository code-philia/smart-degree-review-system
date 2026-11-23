import json
import os
from pathlib import Path
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from paper_compiler.account_credit import AccountCredit, CreditError, bill_model_request, billing_rule, usage_nano

RULE='bilingual_keywords_correspondence_check'
PAYLOAD={'model':'deepseek-chat','messages':[{'role':'user','content':'native paper facts'}],'max_tokens':100}

@pytest.fixture
def account(tmp_path,monkeypatch):
    path=tmp_path/'credit.sqlite'
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE auth_users(id TEXT PRIMARY KEY);
          CREATE TABLE paper_lint_jobs(id TEXT PRIMARY KEY,user_id TEXT,status TEXT,attempts INTEGER,cancelled_at TEXT,selected_rule_ids_json TEXT);
          INSERT INTO auth_users VALUES ('alice'); INSERT INTO auth_users VALUES ('bob');''')
        db.executescript((Path(__file__).resolve().parents[1]/'src/database/credit_schema.sql').read_text())
        db.execute("INSERT INTO paper_lint_jobs VALUES ('job','alice','running',1,NULL,?)",[json.dumps([RULE,'typo_detection_check'])])
        db.execute("INSERT INTO paper_lint_credit_operations VALUES ('operation','job','alice',1,?,'active','now',NULL)",[os.getpid()])
    monkeypatch.setenv('PAPER_LINT_CREDIT_CONTEXT',json.dumps({'database_file':str(path),'operation_id':'operation'}))
    return AccountCredit(path,'operation'),path

def row(path,sql,params=()):
    with sqlite3.connect(path) as db:
        db.row_factory=sqlite3.Row
        return dict(db.execute(sql,params).fetchone())

def response(**usage):
    return {'usage':{'prompt_tokens':100,'completion_tokens':20,**usage},'choices':[]}

def test_reference_rates_and_cache_are_exact_integer_nanoyuan():
    assert usage_nano({'prompt_tokens':1_000_000,'completion_tokens':1_000_000})[0]==5_000_000_000
    assert usage_nano({'prompt_tokens':1_000_000,'completion_tokens':0,'prompt_cache_hit_tokens':1_000_000,'prompt_cache_miss_tokens':0})[0]==20_000_000
    assert usage_nano({'prompt_tokens':100,'completion_tokens':2,'prompt_tokens_details':{'cached_tokens':60}})[0]==49_200

@pytest.mark.parametrize('usage',[
    None,{}, {'prompt_tokens':True,'completion_tokens':2}, {'prompt_tokens':-1,'completion_tokens':2},
    {'prompt_tokens':100,'completion_tokens':2,'prompt_cache_hit_tokens':101},
    {'prompt_tokens':100,'completion_tokens':2,'prompt_cache_hit_tokens':60,'prompt_cache_miss_tokens':50},
    {'prompt_tokens':100,'completion_tokens':2,'total_tokens':103},
    {'prompt_tokens':2**80,'completion_tokens':1},
])
def test_invalid_or_missing_usage_is_never_invented(usage):
    with pytest.raises(ValueError):usage_nano(usage)

def test_reserve_settle_once_and_isolate_accounts(account):
    client,path=account
    call=client.reserve(RULE,PAYLOAD,call_id='one')
    assert row(path,"SELECT reserved_nano FROM paper_lint_credit_accounts WHERE user_id='alice'")['reserved_nano']>0
    assert client.settle(call,response())==180_000
    assert client.settle(call,response())==180_000
    assert row(path,"SELECT * FROM paper_lint_credit_accounts WHERE user_id='alice'")['spent_nano']==180_000
    assert row(path,"SELECT * FROM paper_lint_credit_accounts WHERE user_id='bob'")['spent_nano']==0
    assert row(path,"SELECT * FROM paper_lint_credit_calls WHERE id='one'")['rate_version']=='deepseek-flash-reference-2026-11-24'

def test_missing_usage_releases_reservation_with_auditable_unknown_receipt(account):
    client,path=account;call=client.reserve(RULE,PAYLOAD)
    assert client.settle(call,{})==0
    receipt=row(path,'SELECT * FROM paper_lint_credit_calls WHERE id=?',[call])
    assert receipt['status']=='unknown' and receipt['failure_code']=='missing_usage'
    assert row(path,"SELECT reserved_nano FROM paper_lint_credit_accounts WHERE user_id='alice'")['reserved_nano']==0

def test_concurrent_reservations_cannot_overspend(account):
    client,path=account
    with sqlite3.connect(path) as db:db.execute("UPDATE paper_lint_credit_accounts SET granted_nano=2000000 WHERE user_id='alice'")
    def attempt(_):
        try:return client.reserve(RULE,PAYLOAD)
        except CreditError:return None
    with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(attempt,range(16)))
    assert sum(r is not None for r in results)==1
    assert row(path,"SELECT * FROM paper_lint_credit_accounts WHERE user_id='alice'")['reserved_nano']<=2_000_000

def test_cancelled_or_stale_operation_cannot_reserve(account):
    client,path=account
    with sqlite3.connect(path) as db:db.execute("UPDATE paper_lint_jobs SET cancelled_at='now' WHERE id='job'")
    with pytest.raises(CreditError):client.reserve(RULE,PAYLOAD)
    with sqlite3.connect(path) as db:db.execute("UPDATE paper_lint_jobs SET cancelled_at=NULL,attempts=2 WHERE id='job'")
    with pytest.raises(CreditError):client.reserve(RULE,PAYLOAD)

def test_unselected_rule_or_unknown_model_fails_before_network(account):
    sent=[]
    with pytest.raises(CreditError):bill_model_request(PAYLOAD,lambda:sent.append(True),rule_id='abstract_numeric_consistency_check')
    with billing_rule(RULE),pytest.raises(CreditError):bill_model_request({**PAYLOAD,'model':'unpriced'},lambda:sent.append(True))
    assert sent==[]

def test_paid_transport_settles_usage_before_content_validation(account):
    _,path=account;raw=json.dumps(response()).encode()
    with billing_rule(RULE):assert bill_model_request(PAYLOAD,lambda:raw)==raw
    assert row(path,"SELECT spent_nano FROM paper_lint_credit_accounts WHERE user_id='alice'")['spent_nano']==180_000

def test_qwen_and_unconfigured_offline_calls_do_not_charge(account,monkeypatch):
    _,path=account
    assert bill_model_request({**PAYLOAD,'model':'qwen'},lambda:b'translation')==b'translation'
    monkeypatch.delenv('PAPER_LINT_CREDIT_CONTEXT')
    assert bill_model_request(PAYLOAD,lambda:b'offline')==b'offline'
    assert row(path,'SELECT count(*) AS n FROM paper_lint_credit_calls')['n']==0

def test_transport_failure_releases_reservation_and_preserves_no_guessed_debit(account):
    _,path=account
    def failed():raise TimeoutError('transport')
    with billing_rule(RULE),pytest.raises(TimeoutError):bill_model_request(PAYLOAD,failed)
    receipt=row(path,'SELECT * FROM paper_lint_credit_calls')
    assert receipt['status']=='unknown' and receipt['charged_nano']==0
    assert row(path,"SELECT reserved_nano FROM paper_lint_credit_accounts WHERE user_id='alice'")['reserved_nano']==0

def test_usage_outside_the_request_bound_is_audited_without_overdrawing(account):
    client,path=account;call=client.reserve(RULE,PAYLOAD)
    assert client.settle(call,response(completion_tokens=1000))==0
    assert row(path,'SELECT status FROM paper_lint_credit_calls WHERE id=?',[call])['status']=='invalid_usage'
    assert row(path,"SELECT reserved_nano FROM paper_lint_credit_accounts WHERE user_id='alice'")['reserved_nano']==0

def test_usage_settles_a_known_inflight_call_after_cancellation(account):
    client,path=account;call=client.reserve(RULE,PAYLOAD)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE paper_lint_jobs SET cancelled_at='now' WHERE id='job'")
        db.execute("UPDATE paper_lint_credit_operations SET state='closing' WHERE id='operation'")
    assert client.settle(call,response())==180_000
    assert row(path,"SELECT spent_nano FROM paper_lint_credit_accounts WHERE user_id='alice'")['spent_nano']==180_000

def test_separate_processes_cannot_spend_the_same_credit(account):
    import subprocess
    client,path=account
    with sqlite3.connect(path) as db:db.execute("UPDATE paper_lint_credit_accounts SET granted_nano=2000000 WHERE user_id='alice'")
    code='''import json,sys
from paper_compiler.account_credit import AccountCredit,CreditError
try:
 AccountCredit(sys.argv[1],'operation').reserve(sys.argv[2],json.loads(sys.argv[3]));print('reserved')
except CreditError: print('blocked')
'''
    env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1])}
    children=[subprocess.Popen([sys.executable,'-c',code,str(path),RULE,json.dumps(PAYLOAD)],env=env,stdout=subprocess.PIPE,text=True) for _ in range(5)]
    results=[child.communicate(timeout=20)[0].strip() for child in children]
    assert results.count('reserved')==1 and results.count('blocked')==4
