import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_bilingual_semantic_lint as lint
from paper_compiler.account_credit import billing_rule
from test_account_credit import account, RULE, row

@pytest.fixture
def provider(account,monkeypatch):
    _,path=account
    monkeypatch.setenv('SJTU_API_KEY','test-only')
    monkeypatch.setenv('SJTU_API_BASE_URL','https://models.sjtu.edu.cn/api/v1')
    monkeypatch.setenv('SJTU_API_MODEL','deepseek-chat')
    monkeypatch.setattr(lint,'campus_request',lambda url,headers,timeout,send:send(timeout))
    def install(content):
        raw=json.dumps({'usage':{'prompt_tokens':100,'completion_tokens':20},
             'choices':[{'finish_reason':'stop','message':{'content':content}}]}).encode()
        monkeypatch.setattr(lint.urllib.request,'build_opener',lambda *args:SimpleNamespace(open=lambda *a,**k:io.BytesIO(raw)))
    return path,install

def test_real_request_entry_settles_even_if_answer_json_is_invalid(provider):
    path,install=provider;install('not json')
    with billing_rule(RULE),pytest.raises(Exception):lint.request_json([{'role':'user','content':'test'}])
    assert row(path,"SELECT spent_nano FROM paper_lint_credit_accounts WHERE user_id='alice'")['spent_nano']==180_000

def test_cached_response_does_not_create_a_second_transport_receipt(provider,tmp_path,monkeypatch):
    path,install=provider;install('{"outcome":"consistent"}')
    monkeypatch.setenv('SJTU_API_RESPONSE_CACHE_DIR',str(tmp_path/'responses'))
    with billing_rule(RULE):
        lint.request_json([{'role':'user','content':'same'}])
        _,usage=lint.request_json([{'role':'user','content':'same'}])
    assert usage=={'input_tokens':0,'output_tokens':0}
    assert row(path,'SELECT count(*) AS n FROM paper_lint_credit_calls')['n']==1

def test_rule_context_is_isolated_across_parallel_rule_workers(provider,monkeypatch):
    path,install=provider;install('{"errors":[]}')
    monkeypatch.setattr(lint,'_run_semantic_rule_impl',lambda *args,**kw:lint.request_json([{'role':'user','content':'parallel'}]),raising=False)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=[pool.submit(lint._run_semantic_rule,{}, {},rule) for rule in [RULE,'typo_detection_check']]
        for result in results:result.result()
    with __import__('sqlite3').connect(path) as db:
        assert sorted(r[0] for r in db.execute('SELECT rule_id FROM paper_lint_credit_calls'))==sorted([RULE,'typo_detection_check'])

def test_typo_chunk_threads_keep_their_parent_rule_accounting_context(provider,monkeypatch):
    path,install=provider;install('{"errors":[]}')
    monkeypatch.setattr(lint,'_native_typo_input',lambda ir:(ir,None))
    monkeypatch.setattr(lint,'_body_chunks',lambda ir,size:[{'model_text':'实验使用此方法。'} for _ in range(3)])
    with billing_rule('typo_detection_check'):
        result=lint.run_typo_rule_from_ir({},max_workers=2)
    assert result['execution_status']=='completed'
    with __import__('sqlite3').connect(path) as db:
        assert list(db.execute('SELECT DISTINCT rule_id FROM paper_lint_credit_calls'))==[('typo_detection_check',)]
        assert db.execute('SELECT count(*) FROM paper_lint_credit_calls').fetchone()[0]==3

def test_provider_429_retry_has_a_released_attempt_and_one_final_charge(provider,monkeypatch):
    path,_=provider;attempts=[]
    raw=json.dumps({'usage':{'prompt_tokens':100,'completion_tokens':20},'choices':[{'message':{'content':'{}'}}]}).encode()
    def opened(*args,**kwargs):
        attempts.append(True)
        if len(attempts)==1:raise lint.urllib.error.HTTPError('https://models.sjtu.edu.cn',429,'busy',{},io.BytesIO())
        return io.BytesIO(raw)
    def queued(url,headers,timeout,send):
        try:return send(timeout)
        except lint.urllib.error.HTTPError:return send(timeout)
    monkeypatch.setattr(lint.urllib.request,'build_opener',lambda *args:SimpleNamespace(open=opened))
    monkeypatch.setattr(lint,'campus_request',queued)
    with billing_rule(RULE):lint.request_json([{'role':'user','content':'retry'}])
    with __import__('sqlite3').connect(path) as db:
        assert sorted(r[0] for r in db.execute('SELECT status FROM paper_lint_credit_calls'))==['released','settled']
    assert row(path,"SELECT spent_nano FROM paper_lint_credit_accounts WHERE user_id='alice'")['spent_nano']==180_000


def test_typo_format_retry_settles_both_actual_responses_and_keeps_cache_free(provider,tmp_path,monkeypatch):
    path,_=provider;attempts=[]
    monkeypatch.setenv('SJTU_API_RESPONSE_CACHE_DIR',str(tmp_path/'retry-cache'))
    def opened(*args,**kwargs):
        attempts.append(True)
        content='not JSON' if len(attempts)==1 else '{"errors":[]}'
        return io.BytesIO(json.dumps({'usage':{'prompt_tokens':100,'completion_tokens':20},
            'choices':[{'finish_reason':'stop','message':{'content':content}}]}).encode())
    monkeypatch.setattr(lint.urllib.request,'build_opener',lambda *a:SimpleNamespace(open=opened))
    with billing_rule('typo_detection_check'):
        payload,usage=lint.request_json([{'role':'user','content':'same chunk'}],response_contract='typo-discovery')
        _,cached=lint.request_json([{'role':'user','content':'same chunk'}],response_contract='typo-discovery')
    assert payload=={'errors':[]} and len(attempts)==2
    assert usage=={'input_tokens':200,'output_tokens':40} and cached=={'input_tokens':0,'output_tokens':0}
    assert row(path,'SELECT count(*) AS n FROM paper_lint_credit_calls')['n']==2
    assert row(path,"SELECT spent_nano FROM paper_lint_credit_accounts WHERE user_id='alice'")['spent_nano']==360_000
