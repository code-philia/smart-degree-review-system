"""Zero-network decoder/receipt/recovery regressions; candidate copies stay external."""
from copy import deepcopy
from importlib.util import module_from_spec,spec_from_file_location
import json
import os
from pathlib import Path
import sqlite3
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from paper_compiler import llm as official_llm, conflict_review as official_review
from paper_compiler.storage import json_bytes

def modules():
    return official_llm,official_review,None


def test_single_extra_brace_preserves_object_and_rejects_other_content_and_length(tmp_path):
    llm,_,_ = modules()
    for content in ['{"x":{"value":2}}}', ' \n{"x":{"value":2}}  } \t', '```json\n{"x":{"value":2}}}\n```']:
        assert llm._decode_json_object(content) == {'x':{'value':2}}
    for content in ['{}{}','{} extra','{}}}', '{"x":}', '[]}', '"a"}', '{"x":NaN}}', '```json\n{}\n``` explanation']:
        with pytest.raises(ValueError): llm._decode_json_object(content)
    class Ledger:
        def reserve(self,*args): pass
        def settle(self,*args): pass
        def mark_uncertain(self,*args): pass
    config = tmp_path/'fake.env'
    config.write_text('MAAS_API_KEY=fake\nMAAS_BASE_URL='+llm.ALLOWED_BASE+'\nMAAS_MODEL=deepseek-v4.1-flash\nMAAS_MODEL_VERSION=20260910\n')
    def transport(url,headers,payload,timeout):
        return {'usage':{'prompt_tokens':2,'completion_tokens':3},
                'choices':[{'finish_reason':'length','message':{'content':'{"x":2}}'}}]}
    client = llm.MaasClient(config,Ledger(),tmp_path/'cache','fake',1,transport=transport,max_attempts=1)
    with pytest.raises(llm.ModelError): client.complete_json('fake/1.0','data',{},100)
    legacy = official_llm.MaasClient.__new__(official_llm.MaasClient)
    legacy.__dict__.update(client.__dict__)
    assert legacy.request_fingerprint('fake/1.0','data',{},100) == client.request_fingerprint('fake/1.0','data',{},100)


def test_decoder_policy_invalidates_old_error_receipt_without_changing_review_wire():
    llm,review,_ = modules()
    text = 'This method has no recurrence [1].'; body = 'This method uses recurrence.'
    request = {'fields':{'conflict':'boolean'}}
    raw = {'fields':{'conflict':{'state':'observed','value':True,'basis':'explicit_scope_contradiction',
        'reason':'Source states the opposite method property.','quotes':[
            {'source_id':'p','quote':text},{'source_id':'e','quote':body}]}}}
    data = {'node':{'id':'use'},'citation_context':{'node_id':'p','text':text},'external_works':[{'id':'w'}],
        'sources':[{'source_id':'p','origin':'paper','node_id':'p','text':text},
                   {'source_id':'e','origin':'external','work_id':'w','content_id':'e','text':body}]}
    packet = review.prepare_review(request,raw,data); wire = review.model_input(packet)
    old_identity = {'task':review.TASK,'instructions':review.INSTRUCTIONS,'data':wire,
                    'semantic_thinking':True,'max_tokens':24000}
    old = {'policy':review.POLICY,'input_hash':review._hash(old_identity),'status':'error','reason':'old invalid JSON'}
    class CachedReviewer:
        max_attempts=1
        semantic_thinking=True
        def __init__(self): self.calls=[]
        def complete_json(self,task,instructions,data,max_tokens):
            self.calls.append((task,instructions,deepcopy(data),max_tokens))
            return {'results':{'review-0':{'decision':'insufficient'}}}
    client=CachedReviewer()
    proofs,record,reason = review.resolve_review(request,raw,data,client=client,receipt=old)
    assert len(client.calls)==1 and record['status']=='completed' and not proofs
    assert client.calls[0] == (review.TASK,review.INSTRUCTIONS,wire,24000)
    assert record['response_decoder'] == llm.response_decoder_policy()
    review.resolve_review(request,raw,data,client=client,receipt=record)
    assert len(client.calls)==1

