"""An incomplete but parseable typo answer receives one validated format retry."""
import io
import json
from types import SimpleNamespace
import pytest
from test_semantic_response_cache import semantic


@pytest.mark.parametrize('contract,incomplete,complete',[
    ('typo-discovery', {}, {'errors':[]}),
    ('typo-discovery', {'errors':[{'original':'布'}]}, {'errors':[]}),
    ('typo-review', {'accepted':True}, {'accepted':False,'reason':'上下文不足'}),
    ('typo-fields', {'accepted':True,'reason':'字段不完整'}, {'accepted':False,'reason':'无法确认替换'}),
])
def test_incomplete_schema_retries_once_and_caches_validated_result(semantic, monkeypatch, contract, incomplete, complete):
    module,_,_,root=semantic
    calls=[]
    def opened(request,**kwargs):
        calls.append(json.loads(request.data))
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(incomplete if len(calls)==1 else complete)}}],
            'usage':{'prompt_tokens':12,'completion_tokens':7}}).encode())
    monkeypatch.setattr(module.urllib.request,'build_opener',lambda *args:SimpleNamespace(open=opened))
    messages=[{'role':'user','content':'仅检查这段原文。'}]
    result,usage=module.request_json(messages,response_contract=contract)
    assert result==complete and usage=={'input_tokens':24,'output_tokens':14}
    assert len(calls)==2 and calls[1]['messages']!=calls[0]['messages']
    assert calls[1]['messages'][0]==messages[0]
    assert messages==[{'role':'user','content':'仅检查这段原文。'}]
    result,cached=module.request_json(messages,response_contract=contract)
    assert result==complete and cached=={'input_tokens':0,'output_tokens':0} and len(calls)==2


def test_persistently_incomplete_discovery_is_not_a_clean_chunk_or_unbounded_retry(semantic, monkeypatch):
    module,calls,response,root=semantic
    response['choices'][0]['message']['content']='{"errors":[{"original":"布"}]}'
    monkeypatch.setattr(module,'_native_typo_input',lambda ir:(ir,None))
    monkeypatch.setattr(module,'_body_chunks',lambda ir,size:[{'model_text':'仅检查这段原文。'}])
    result=module.run_typo_rule_from_ir({},max_workers=1)
    assert result['execution_status']=='error' and result['params']['failed_chunk_indices']==[0]
    assert result['params']['completed_chunk_count']==0
    assert len(calls)==2
    assert result['model_usage']=={'input_tokens':24,'output_tokens':14}
    assert not list(root.glob('*.json'))


def test_cached_repair_restores_original_key_after_unconfirmed_response(semantic,monkeypatch):
    module,_,_,root=semantic;calls=[]
    def opened(request,**kwargs):
        calls.append(json.loads(request.data));n=len(calls)
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':None if n==3 else 'stop',
            'message':{'content':'{}' if n in (1,3) else '{"errors":[]}'}}],
            'usage':{'prompt_tokens':12,'completion_tokens':7}}).encode())
    monkeypatch.setattr(module.urllib.request,'build_opener',lambda *a:SimpleNamespace(open=opened))
    messages=[{'role':'user','content':'same source'}]
    module.request_json(messages,response_contract='typo-discovery')
    key,endpoint,_,_=module.api_config()
    original=module.SemanticResponseCache(root,endpoint,key,calls[0],response_contract='typo-discovery')
    original.path.unlink()
    result,usage=module.request_json(messages,response_contract='typo-discovery')
    assert result=={'errors':[]} and usage=={'input_tokens':12,'output_tokens':7}
    assert len(calls)==3
    _,cached=module.request_json(messages,response_contract='typo-discovery')
    assert cached=={'input_tokens':0,'output_tokens':0} and len(calls)==3


@pytest.mark.parametrize('retry_valid',[False,True])
def test_partial_discovery_keeps_valid_candidates_for_source_verification(semantic,monkeypatch,retry_valid):
    module,_,_,root=semantic;calls=[]
    candidate=dict(original='表名',corrected='表明',context='实验表名有效。',reason='固定用语')
    def opened(request,**kwargs):
        payload=json.loads(request.data);calls.append(payload)
        if len(calls)==1:content={'errors':[candidate,{'original':'缺字段'}]}
        elif len(calls)==2:content={'errors':[]} if retry_valid else {'errors':[candidate,{'original':'缺字段'}]}
        else:content={'accepted':True,'reason':'确认该字误用'}
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(content)}}],
            'usage':{'prompt_tokens':12,'completion_tokens':7}}).encode())
    monkeypatch.setattr(module.urllib.request,'build_opener',lambda *a:SimpleNamespace(open=opened))
    monkeypatch.setattr(module,'_native_typo_input',lambda ir:(ir,None))
    monkeypatch.setattr(module,'_body_chunks',lambda ir,size:[{'model_text':'实验表名有效。','segments':[dict(start=0,end=7,page=2,bbox=[10,10,50,20])]}])
    result=module.run_typo_rule_from_ir({},max_workers=1)
    assert len(result['findings'])==1 and result['findings'][0]['suggestion']=='明'
    assert result['execution_status']==('completed' if retry_valid else 'error')
    assert len(calls)==3 and result['model_usage']=={'input_tokens':36,'output_tokens':21}


def test_indivisible_timeout_preserves_candidates_from_prior_format_attempt():
    from paper_compiler.timeout_recovery import recover_typo_chunk,ReadTimeoutExhausted
    candidate=dict(original='表名',corrected='表明',context='实验表名有效。',reason='用字')
    def ask(text):
        error=ReadTimeoutExhausted('read timed out')
        error.partial_typo_result={'errors':[candidate]};error.known_model_usage={'input_tokens':10,'output_tokens':2}
        raise error
    payload,usage,failure,recovered=recover_typo_chunk('实验表名有效。',ask)
    assert payload=={'errors':[candidate]} and usage=={'input_tokens':10,'output_tokens':2}
    assert isinstance(failure,ReadTimeoutExhausted) and recovered is False


def test_split_timeout_preserves_parent_and_incomplete_child_candidates():
    from paper_compiler.timeout_recovery import recover_typo_chunk,ReadTimeoutExhausted,TypoDiscoveryFormatError
    text='第一句表名错误。第二句布署错误。第三句结束。'
    first=dict(original='表名',corrected='表明',context='第一句表名错误。',reason='用字')
    second=dict(original='布署',corrected='部署',context='第二句布署错误。',reason='固定用语')
    def ask(piece):
        if piece==text:
            error=ReadTimeoutExhausted('read timed out');error.partial_typo_result={'errors':[first]}
        elif piece.startswith('第一句'):
            error=TypoDiscoveryFormatError({'errors':[second,{}]})
        else:return {'errors':[]},{'input_tokens':20,'output_tokens':3}
        error.known_model_usage={'input_tokens':10,'output_tokens':2};raise error
    payload,usage,failure,recovered=recover_typo_chunk(text,ask)
    assert {row['context'] for row in payload['errors']}=={first['context'],second['context']}
    assert usage=={'input_tokens':40,'output_tokens':7} and recovered and failure is not None
