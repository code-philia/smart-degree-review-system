import io
import json
from types import SimpleNamespace
import pytest
from test_semantic_response_cache import semantic


def test_truncated_errors_array_keeps_complete_candidates_for_verification(semantic,monkeypatch):
    module,_,_,_=semantic;calls=[]
    row=dict(original='表名',corrected='表明',context='实验表名有效。',reason='用字')
    def opened(request,**kwargs):
        calls.append(json.loads(request.data));n=len(calls)
        content='{"errors":['+json.dumps(row)+',{"original":"' if n==1 else '{"errors":[]}' if n==2 else '{"accepted":true,"reason":"确认用字错误"}'
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':'length' if n==1 else 'stop','message':{'content':content}}],
            'usage':{'prompt_tokens':12,'completion_tokens':7}}).encode())
    monkeypatch.setattr(module.urllib.request,'build_opener',lambda *a:SimpleNamespace(open=opened))
    monkeypatch.setattr(module,'_native_typo_input',lambda ir:(ir,None))
    monkeypatch.setattr(module,'_body_chunks',lambda ir,size:[{'model_text':row['context'],'segments':[dict(start=0,end=7,page=2,bbox=[10,10,50,20])]}])
    result=module.run_typo_rule_from_ir({},max_workers=1)
    assert result['execution_status']=='completed' and len(result['findings'])==1
    assert result['findings'][0]['suggestion']=='明'
    assert [x['max_tokens'] for x in calls]==[2048,4096,512]
    assert result['model_usage']=={'input_tokens':36,'output_tokens':21}


@pytest.mark.parametrize('finish',['content_filter',None,'tool_calls'])
def test_unconfirmed_finish_needs_a_complete_retry(semantic,monkeypatch,finish):
    module,_,_,_=semantic;calls=[]
    def opened(*args,**kwargs):
        calls.append(1)
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':finish if len(calls)==1 else 'stop','message':{'content':'{"errors":[]}'}}],
            'usage':{'prompt_tokens':12,'completion_tokens':7}}).encode())
    monkeypatch.setattr(module.urllib.request,'build_opener',lambda *a:SimpleNamespace(open=opened))
    result,usage=module.request_json([{'role':'user','content':'原文。'}],response_contract='typo-discovery')
    assert result=={'errors':[]} and len(calls)==2
    assert usage=={'input_tokens':24,'output_tokens':14}


def test_nested_json_cannot_be_promoted_to_a_clean_top_level_answer(semantic):
    module,calls,response,root=semantic
    response['choices'][0]['message']['content']='{"oops":{"errors":[]},'
    with pytest.raises(ValueError):
        module.request_json([{'role':'user','content':'原文。'}],response_contract='typo-discovery')
    assert len(calls)==2 and not list(root.glob('*.json'))
