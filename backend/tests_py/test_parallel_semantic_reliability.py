"""Regressions from the 2026-11-25 real four-rule load test."""
import copy
import io
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_bilingual_semantic_lint as lint


def test_numeric_navigation_does_not_mutate_ir_while_another_rule_copies_it(tmp_path,monkeypatch):
    import numeric_consistency
    import numeric_navigation
    import numeric_run_trace
    pdf=tmp_path/'paper.pdf';pdf.write_bytes(b'%PDF-test')
    ir={'source_artifacts':[{'kind':'pdf','path':str(pdf)}],'nodes':[]}
    original=copy.deepcopy(ir);reading=Event();written=Event();seen=[]
    def attach(source,model):
        assert reading.wait(2)
        model['numeric_navigation']={'sections':[]}
        seen.append(model)
        written.set()
    monkeypatch.setattr(numeric_navigation,'attach_navigation',attach)
    monkeypatch.setattr(lint,'extract_bilingual_facts',lambda model:{})
    monkeypatch.setattr(numeric_consistency,'run_numeric',lambda *a,**kw:{'execution_status':'completed'})
    monkeypatch.setattr(numeric_run_trace,'NumericRunTrace',lambda *a,**kw:SimpleNamespace(call=None,finish=lambda r:r))
    def reader():
        iterator=iter(ir);next(iterator);reading.set()
        assert written.wait(2)
        return list(iterator)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future=pool.submit(reader)
        result=lint.run_numeric_consistency_rule(ir)
        future.result()
    assert result['execution_status']=='completed'
    assert ir==original and seen[0] is not ir
    assert 'numeric_navigation' in seen[0]


def provider(monkeypatch,responses):
    monkeypatch.setenv('SJTU_API_KEY','test-only')
    monkeypatch.setenv('SJTU_API_BASE_URL','https://example.invalid/api/v1')
    monkeypatch.setenv('SJTU_API_MODEL','test-model')
    monkeypatch.delenv('SJTU_API_RESPONSE_CACHE_DIR',raising=False)
    monkeypatch.delenv('PAPER_LINT_CREDIT_CONTEXT',raising=False)
    calls=[]
    def opened(*args,**kwargs):
        number=len(calls);calls.append(True)
        content,reason=responses[min(number,len(responses)-1)]
        return io.BytesIO(json.dumps({'usage':{'prompt_tokens':100,'completion_tokens':20},'choices':[{'finish_reason':reason,'message':{'content':content}}]}).encode())
    monkeypatch.setattr(lint.urllib.request,'build_opener',lambda *a:SimpleNamespace(open=opened))
    return calls


def test_typo_recovers_one_non_json_response_and_counts_both_attempts(monkeypatch):
    calls=provider(monkeypatch,[('not JSON','stop'),('{"errors":[]}','stop')])
    payload,usage=lint.request_json([{'role':'user','content':'原文。'}],response_contract='typo-discovery')
    assert payload=={'errors':[]} and len(calls)==2
    assert usage=={'input_tokens':200,'output_tokens':40}


def test_typo_never_accepts_a_truncated_object_as_a_clean_result(monkeypatch):
    calls=provider(monkeypatch,[('{"errors":[]}','length'),('{"errors":[]}','stop')])
    _,usage=lint.request_json([{'role':'user','content':'原文。'}],response_contract='typo-discovery')
    assert len(calls)==2 and usage['input_tokens']==200


def test_typo_persistent_bad_json_stays_error_and_retry_is_bounded(monkeypatch):
    calls=provider(monkeypatch,[('not JSON','stop')])
    monkeypatch.setattr(lint,'_native_typo_input',lambda ir:(ir,None))
    monkeypatch.setattr(lint,'_body_chunks',lambda ir,size:[{'model_text':'原文。'}])
    result=lint.run_typo_rule_from_ir({},max_workers=1)
    assert len(calls)==2
    assert result['execution_status']=='error' and not result['findings']
    assert result['model_usage']=={'input_tokens':200,'output_tokens':40}


def test_json_retry_does_not_turn_http_or_balance_failures_into_extra_attempts(monkeypatch):
    calls=provider(monkeypatch,[('{"errors":[]}','stop')])
    def failed(*args,**kwargs):raise TimeoutError('request timed out')
    monkeypatch.setattr(lint,'campus_request',failed)
    with pytest.raises(TimeoutError):lint.request_json([],response_contract='typo-discovery')
    assert not calls


def test_generic_invalid_json_retains_existing_no_retry_behavior(monkeypatch):
    calls=provider(monkeypatch,[('not JSON','stop')])
    with pytest.raises(ValueError):lint.request_json([])
    assert len(calls)==1
