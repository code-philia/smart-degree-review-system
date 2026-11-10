import importlib.util
import json
from pathlib import Path
from unittest.mock import patch
import pytest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts'/'report_translation.py'

def module():
    spec=importlib.util.spec_from_file_location('report_translation',SCRIPT)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod

def test_translation_model_is_qwen_without_changing_detection_environment(monkeypatch):
    monkeypatch.setenv('SJTU_API_MODEL','deepseek-chat')
    monkeypatch.setenv('SJTU_API_KEY','test-secret')
    monkeypatch.setenv('SJTU_API_BASE_URL','https://models.sjtu.edu.cn/api/v1')
    monkeypatch.delenv('REPORT_TRANSLATION_MODEL',raising=False)
    import os
    with module().translation_environment():
        assert os.environ['SJTU_API_MODEL']=='qwen'
        assert os.environ['SJTU_API_REQUESTS_PER_MINUTE']=='10'
    assert os.environ['SJTU_API_MODEL']=='deepseek-chat'

def test_transport_uses_existing_ledger_client_with_one_attempt_and_bounded_tokens(tmp_path):
    mod=module()
    class Client:
        def __init__(self,*args,**kwargs):
            assert kwargs['max_attempts']==1
            assert kwargs['timeout']==55
            assert kwargs['json_output'] is True
        def complete_json(self,task,prompt,data,max_tokens):
            assert max_tokens<=4096
            assert data['items']==[{'id':'i0','text':'需要说明 __P0__'}]
            return {'items':[{'id':'i0','text':'Explain __P0__'}]}
    with patch.object(mod,'MaasClient',Client):
        assert mod.execute([{'id':'i0','text':'需要说明 __P0__'}],ledger=object(),cache=tmp_path)['items'][0]['id']=='i0'

def test_rejects_oversized_or_wrong_schema_without_transport(tmp_path):
    mod=module()
    with patch.object(mod,'MaasClient',side_effect=AssertionError('transport must not run')):
        with pytest.raises(ValueError):
            mod.execute([{'id':'i0','text':'x'*12001}],ledger=object(),cache=tmp_path)
        with pytest.raises(ValueError):
            mod.execute([{'id':'i0','text':'hello','extra':'forbidden'}],ledger=object(),cache=tmp_path)

def test_bilingual_omission_glossary_is_versioned_for_content_not_entire_abstract():
    mod=module()
    assert mod.PROMPT_VERSION=='report-presentation-en-v2'
    for prefix in ('中文摘要缺失', '英文摘要缺失'):
        assert prefix in mod.PROMPT
    assert 'omitted corresponding content' in mod.PROMPT
    assert 'not that the entire abstract is absent' in mod.PROMPT
    service=(SCRIPT.parents[1]/'src'/'normative'/'reportTranslationService.js').read_text()
    assert "const PROMPT_VERSION = '"+mod.PROMPT_VERSION+"'" in service
