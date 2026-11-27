import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

spec=importlib.util.spec_from_file_location('timeout_lint',Path(__file__).parents[1]/'scripts/run_bilingual_semantic_lint.py')
lint=importlib.util.module_from_spec(spec);spec.loader.exec_module(lint)


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv('SJTU_API_KEY','fixture');monkeypatch.setenv('SJTU_API_BASE_URL','https://models.sjtu.edu.cn/api/v1')
    monkeypatch.setenv('SJTU_API_MODEL','fixture');monkeypatch.delenv('SJTU_API_RESPONSE_CACHE_DIR',raising=False)
    monkeypatch.delenv('PAPER_LINT_CREDIT_CONTEXT',raising=False)
    monkeypatch.setattr(lint,'campus_request',lambda url,headers,timeout,send,**kwargs:send(timeout))
    return monkeypatch


def raw(content='{"errors":[]}'):
    return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':content}}],
        'usage':{'prompt_tokens':10,'completion_tokens':2,'total_tokens':12}}).encode())


def test_read_timeout_retries_once_and_keeps_one_logical_identity(provider):
    from paper_compiler import timeout_recovery as recovery
    provider.setattr(recovery.time,'sleep',lambda _:None)
    attempts=[]
    def opened(*args,**kwargs):
        attempts.append(dict(recovery.current_attempt()))
        if len(attempts)==1:raise URLError(TimeoutError('The read operation timed out'))
        return raw()
    provider.setattr(lint.urllib.request,'build_opener',lambda *args:SimpleNamespace(open=opened))
    result,usage=lint.request_json([],response_contract='typo-discovery')
    assert result=={'errors':[]} and usage=={'input_tokens':10,'output_tokens':2}
    assert [r['attempt'] for r in attempts]==[1,2] and len({r['request_id'] for r in attempts})==1


def test_timeout_allowance_is_shared_with_format_retry(provider):
    from paper_compiler import timeout_recovery as recovery
    provider.setattr(recovery.time,'sleep',lambda _:None);calls=[]
    def opened(*args,**kwargs):
        calls.append(1)
        if len(calls)==2:return raw('not JSON')
        raise TimeoutError('The read operation timed out')
    provider.setattr(lint.urllib.request,'build_opener',lambda *args:SimpleNamespace(open=opened))
    with pytest.raises(TimeoutError) as caught:lint.request_json([],response_contract='typo-discovery')
    assert len(calls)==3
    assert caught.value.known_model_usage=={'input_tokens':10,'output_tokens':2}


def test_remaining_deadline_stops_retry(provider):
    calls=[]
    def opened(*args,**kwargs):calls.append(1);raise TimeoutError('read timed out')
    def remaining():
        if calls:raise RuntimeError('task deadline exhausted')
        return 1
    provider.setattr(lint.urllib.request,'build_opener',lambda *args:SimpleNamespace(open=opened))
    with pytest.raises(RuntimeError,match='deadline'):lint.request_json([],remaining_time=remaining)
    assert calls==[1]


@pytest.mark.parametrize('error',[HTTPError('https://fixture',401,'denied',{},None),RuntimeError('credit rejected'),KeyboardInterrupt()])
def test_other_failures_are_not_retried(provider,error):
    calls=[]
    def opened(*args,**kwargs):calls.append(1);raise error
    provider.setattr(lint.urllib.request,'build_opener',lambda *args:SimpleNamespace(open=opened))
    with pytest.raises(RuntimeError if isinstance(error,HTTPError) else type(error)):lint.request_json([])
    assert calls==[1]


def test_timeout_copy_reports_actual_reason():
    message=lint.public_failure_message('The read operation timed out')
    assert '响应超时' in message and '已完成' in message and '使用人数' not in message


def test_sentence_fallback_keeps_partial_results_and_original_offsets():
    from paper_compiler.timeout_recovery import recover_typo_chunk,ReadTimeoutExhausted
    text='研究方法正确。实验结果表名有效。讨论仍需完善。';calls=[]
    def ask(piece):
        calls.append(piece)
        if piece==text:raise ReadTimeoutExhausted('read timed out')
        if piece.endswith('讨论仍需完善。'):raise ReadTimeoutExhausted('read timed out')
        return {'errors':[{'original':'表名','corrected':'表明','context':'实验结果表名有效。','reason':'用字'}]},dict(input_tokens=10,output_tokens=2)
    payload,usage,failure,recovered=recover_typo_chunk(text,ask)
    assert recovered and failure is not None and usage==dict(input_tokens=10,output_tokens=2)
    assert len(payload['errors'])==1 and len(calls)==3
    assert payload['errors'][0]['_recovery_span'][0]==0
    assert all(len(piece)<len(text) for piece in calls[1:])


def test_indivisible_sentence_is_not_cut_by_character():
    from paper_compiler.timeout_recovery import recover_typo_chunk,ReadTimeoutExhausted
    calls=[]
    def ask(piece):calls.append(piece);raise ReadTimeoutExhausted('read timed out')
    with pytest.raises(TimeoutError):recover_typo_chunk('一段没有句内分隔符的原文。',ask)
    assert len(calls)==1


def test_partial_split_findings_keep_source_location_and_good_chunk_is_not_repeated(monkeypatch):
    from paper_compiler.timeout_recovery import ReadTimeoutExhausted
    text='研究方法正确。实验结果表名有效。讨论仍需完善。';good='另一段内容正常。';calls=[]
    chunks=[dict(model_text=text,segments=[dict(start=0,end=len(text),page=2,bbox=[10,20,100,40],page_width=595,page_height=842)]),
            dict(model_text=good,segments=[])]
    monkeypatch.setattr(lint,'_native_typo_input',lambda ir:(ir,None))
    monkeypatch.setattr(lint,'_body_chunks',lambda ir,size:chunks)
    def ask(messages,**kwargs):
        prompt=messages[0]['content'];calls.append(prompt)
        if '候选复核器' in prompt:return {'accepted':True,'reason':'明确误用'},dict(input_tokens=1,output_tokens=1)
        if prompt.endswith(good):return {'errors':[]},dict(input_tokens=1,output_tokens=1)
        if prompt.endswith(text) or prompt.endswith('讨论仍需完善。'):raise ReadTimeoutExhausted('read timed out')
        return {'errors':[dict(original='表名',corrected='表明',context='实验结果表名有效。',reason='固定用语')]},dict(input_tokens=10,output_tokens=2)
    monkeypatch.setattr(lint,'request_json',ask)
    result=lint.run_typo_rule_from_ir({},max_workers=1)
    assert result['execution_status']=='error' and result['outcome']=='inconclusive'
    assert len(result['findings'])==1 and result['findings'][0]['location']['page_number']==2
    assert result['params']['completed_chunk_count']==1 and result['params']['failed_chunk_indices']==[0]
    assert result['params']['timeout_split_chunk_indices']==[0]
    assert sum(prompt.endswith(good) for prompt in calls)==1
    assert result['model_usage']==dict(input_tokens=12,output_tokens=4)


def test_invalid_discovery_cannot_claim_completed_coverage(monkeypatch):
    monkeypatch.setattr(lint,'_native_typo_input',lambda ir:(ir,None))
    monkeypatch.setattr(lint,'_body_chunks',lambda ir,size:[dict(model_text='原文。')])
    monkeypatch.setattr(lint,'request_json',lambda *args,**kwargs:({},dict(input_tokens=1,output_tokens=1)))
    result=lint.run_typo_rule_from_ir({},max_workers=1)
    assert result['execution_status']=='error' and result['outcome']=='inconclusive'


def test_timeout_retry_reacquires_tpm_budget_and_keeps_unknown_attempt(provider,tmp_path):
    from paper_compiler import campus_requests as api,timeout_recovery as recovery
    class Clock:
        now=1000.0
        def time(self):return self.now
        def monotonic(self):return self.now
        def sleep(self,seconds):self.now+=seconds
    clock=Clock();path=tmp_path/'quota.sqlite';starts=[]
    provider.setattr(api,'time',clock);provider.setattr(recovery.time,'sleep',clock.sleep)
    provider.setenv('SJTU_API_COORDINATOR_DB',str(path));provider.setenv('SJTU_API_TOKENS_PER_MINUTE','10000')
    provider.setattr(lint,'campus_request',api.campus_request)
    def opened(*args,**kwargs):
        starts.append(clock.now)
        if len(starts)==1:raise TimeoutError('read timed out')
        return raw()
    provider.setattr(lint.urllib.request,'build_opener',lambda *args:SimpleNamespace(open=opened))
    lint.request_json([],response_contract='typo-discovery')
    assert len(starts)==2 and starts[1]>=starts[0]+60


def test_task_timeout_never_causes_sentence_split():
    from paper_compiler.timeout_recovery import recover_typo_chunk
    calls=[]
    def ask(text):calls.append(text);raise TimeoutError('job deadline expired')
    with pytest.raises(TimeoutError):recover_typo_chunk('第一句。第二句。第三句。',ask)
    assert len(calls)==1


@pytest.mark.parametrize('kind',['many_rows','repeated','forged'])
def test_recovery_rows_do_not_drop_or_misplace_source_findings(monkeypatch,kind):
    from paper_compiler import timeout_recovery as recovery
    text=('初始句。实验表名错误。实验表名错误。最后一句。' if kind=='repeated'
          else '第一句表名错误。第二句布署错误。第三句结束。')
    split=text.find('实验表名错误。',5) if kind=='repeated' else len('第一句表名错误。')
    segments=[dict(start=0,end=split,page=2,bbox=[10,20,100,40]),dict(start=split,end=len(text),page=4,bbox=[10,50,100,70])]
    monkeypatch.setattr(lint,'_native_typo_input',lambda ir:(ir,None))
    monkeypatch.setattr(lint,'_body_chunks',lambda ir,size:[dict(model_text=text,segments=segments)])
    def ask(messages,**kwargs):
        prompt=messages[0]['content']
        if '候选复核器' in prompt:return {'accepted':True,'reason':'确认'},dict(input_tokens=1,output_tokens=1)
        if kind=='forged':return {'errors':[dict(original='表名',corrected='表明',context='第一句表名错误。',reason='用字',_recovery_span=(999,1000))]},dict(input_tokens=1,output_tokens=1)
        if prompt.endswith(text):raise getattr(recovery,'ReadTimeoutExhausted',TimeoutError)('read timed out')
        right=prompt.endswith('最后一句。' if kind=='repeated' else '第三句结束。')
        row=(dict(original='表名',corrected='表明',context='实验表名错误。',reason='用字') if kind=='repeated' else
             dict(original='布署',corrected='部署',context='第二句布署错误。',reason='用字') if right else
             dict(original='表名',corrected='表明',context='第一句表名错误。',reason='用字'))
        return {'errors':[row]*(20 if kind=='many_rows' and not right else 1)},dict(input_tokens=1,output_tokens=1)
    monkeypatch.setattr(lint,'request_json',ask)
    result=lint.run_typo_rule_from_ir({},max_workers=1)
    assert result['execution_status']=='completed'
    assert {item['location']['page_number'] for item in result['findings']}==({2} if kind=='forged' else {2,4})


def test_noncampus_transport_respects_remaining_deadline(provider):
    provider.setattr(lint,'api_config',lambda:('key','https://api.deepseek.com','model','deepseek'))
    provider.setenv('SJTU_API_MIN_INTERVAL_SECONDS','0');timeouts=[]
    def opened(*args,**kwargs):timeouts.append(kwargs['timeout']);return raw()
    provider.setattr(lint.urllib.request,'build_opener',lambda *args:SimpleNamespace(open=opened))
    lint.request_json([],remaining_time=lambda:1)
    assert timeouts and max(timeouts)<=1


def test_noncampus_pacing_does_not_overrun_remaining_deadline(provider):
    class Clock:
        now=1000
        def monotonic(self):return self.now
        def sleep(self,value):self.now+=value
    clock=Clock();provider.setattr(lint,'time',clock);provider.setattr(lint,'_LAST_REQUEST_AT',1000)
    provider.setattr(lint,'api_config',lambda:('key','https://api.deepseek.com','model','deepseek'))
    provider.setenv('SJTU_API_MIN_INTERVAL_SECONDS','6')
    def remaining():
        if clock.now>=1001:raise RuntimeError('deadline exhausted')
        return 1001-clock.now
    with pytest.raises(RuntimeError,match='deadline'):lint.request_json([],remaining_time=remaining)
    assert clock.now<=1001


def test_connection_timeout_is_not_retried_or_split(provider):
    calls=[]
    def opened(*args,**kwargs):calls.append(1);raise TimeoutError('connect timed out')
    provider.setattr(lint.urllib.request,'build_opener',lambda *args:SimpleNamespace(open=opened))
    with pytest.raises(TimeoutError):lint.request_json([])
    assert calls==[1]


def test_empty_body_timeout_keeps_truthful_public_reason(provider):
    from paper_compiler import timeout_recovery
    provider.setattr(timeout_recovery.time,'sleep',lambda _:None)
    provider.setattr(lint,'_native_typo_input',lambda ir:(ir,None))
    provider.setattr(lint,'_body_chunks',lambda ir,size:[dict(model_text='原文。')])
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,*args):raise TimeoutError()
    provider.setattr(lint.urllib.request,'build_opener',lambda *args:SimpleNamespace(open=lambda *args,**kwargs:Response()))
    result=lint.run_typo_rule_from_ir({},max_workers=1)
    assert result['execution_status']=='error' and '响应超时' in result['message'] and '人数' not in result['message']
