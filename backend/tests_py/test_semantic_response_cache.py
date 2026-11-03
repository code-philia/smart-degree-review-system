import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def semantic(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('cached_semantic', Path(__file__).parents[1] / 'scripts/run_bilingual_semantic_lint.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for key, value in {'SJTU_API_KEY': 'private-test-token', 'SJTU_API_BASE_URL': 'https://models.sjtu.edu.cn/api/v1',
                       'SJTU_API_MODEL': 'deepseek-chat', 'SJTU_API_RESPONSE_CACHE_DIR': str(tmp_path / 'responses')}.items():
        monkeypatch.setenv(key, value)
    calls = []
    response = {'choices': [{'finish_reason': 'stop', 'message': {'content': '{"findings":[]}'}}],
                'usage': {'prompt_tokens': 12, 'completion_tokens': 7}}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size): return json.dumps(response).encode()
    class Opener:
        def open(self, request, *, timeout):
            calls.append(json.loads(request.data))
            return Response()
    monkeypatch.setattr(module.urllib.request, 'build_opener', lambda *args: Opener())
    monkeypatch.setattr(module, 'campus_request', lambda url, headers, timeout, send: send(10))
    return module, calls, response, tmp_path / 'responses'


def test_repeat_request_reuses_result_without_reporting_new_model_usage(semantic):
    module, calls, _, root = semantic
    messages = [{'role': 'user', 'content': 'same complete text'}]
    first, usage = module.request_json(messages)
    second, second_usage = module.request_json(messages)
    assert first == second == {'findings': []}
    assert usage == {'input_tokens': 12, 'output_tokens': 7}
    assert second_usage == {'input_tokens': 0, 'output_tokens': 0}
    assert len(calls) == 1
    files = list(root.glob('*.json'))
    assert len(files) == 1
    assert 'private-test-token' not in files[0].read_text()
    assert 'same complete text' not in files[0].read_text()


@pytest.mark.parametrize('changed', ['text', 'key', 'model', 'version', 'endpoint'])
def test_changed_request_or_model_identity_cannot_reuse_cached_result(semantic, monkeypatch, changed):
    module, calls, _, _ = semantic
    messages = [{'role': 'user', 'content': 'original'}]
    module.request_json(messages)
    if changed == 'text': messages = [{'role': 'user', 'content': 'edited'}]
    else:
        key, value = {'key': ('SJTU_API_KEY', 'another-account'), 'model': ('SJTU_API_MODEL', 'new-model'),
                      'version': ('SJTU_API_MODEL_VERSION', 'new-version'),
                      'endpoint': ('SJTU_API_BASE_URL', 'https://models.sjtu.edu.cn/another-version')}[changed]
        monkeypatch.setenv(key, value)
    module.request_json(messages)
    module.request_json(messages)
    assert len(calls) == 2


def test_expired_and_corrupt_cache_entries_are_refetched(semantic):
    module, calls, _, root = semantic
    messages = [{'role': 'user', 'content': 'source'}]
    module.request_json(messages)
    file = next(root.glob('*.json'))
    record = json.loads(file.read_text()); record['expires_at'] = 0
    file.write_text(json.dumps(record))
    module.request_json(messages)
    file.write_text('broken JSON')
    module.request_json(messages)
    assert len(calls) == 3


def test_audited_requests_bypass_cache_and_still_emit_real_request_events(semantic):
    module, calls, _, _ = semantic
    messages = [{'role': 'user', 'content': 'source'}]
    module.request_json(messages)
    events = []
    module.request_json(messages, observer=lambda kind, value: events.append(kind))
    module.request_json(messages)
    assert len(calls) == 2
    assert 'request_attempt' in events and 'raw_response' in events


@pytest.mark.parametrize('mode', ['truncated', 'inconclusive'])
def test_incomplete_or_uncertain_responses_are_not_cached(semantic, mode):
    module, calls, response, _ = semantic
    if mode == 'truncated': response['choices'][0]['finish_reason'] = 'length'
    else: response['choices'][0]['message']['content'] = '{"outcome":"inconclusive","summary":"uncertain"}'
    for _ in range(2): module.request_json([{'role': 'user', 'content': 'source'}])
    assert len(calls) == 2


def test_disabled_or_unwritable_cache_does_not_prevent_model_requests(semantic, monkeypatch, tmp_path):
    module, calls, _, _ = semantic
    file = tmp_path / 'not-a-directory'; file.write_text('occupied')
    monkeypatch.setenv('SJTU_API_RESPONSE_CACHE_DIR', str(file))
    for _ in range(2): module.request_json([{'role': 'user', 'content': 'source'}])
    monkeypatch.delenv('SJTU_API_RESPONSE_CACHE_DIR')
    module.request_json([{'role': 'user', 'content': 'source'}])
    assert len(calls) == 3


def test_cache_is_private_and_noncampus_requests_cannot_reuse_it(semantic, monkeypatch):
    import os
    import stat
    module, calls, _, root = semantic
    messages = [{'role':'user','content':'source'}]
    module.request_json(messages)
    if os.name != 'nt':
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        assert stat.S_IMODE(next(root.glob('*.json')).stat().st_mode) == 0o600
    config = module.api_config()
    monkeypatch.setattr(module, 'api_config', lambda: (*config[:3], 'deepseek'))
    monkeypatch.setenv('SJTU_API_MIN_INTERVAL_SECONDS', '0')
    module.request_json(messages)
    module.request_json(messages)
    assert len(calls) == 3


def test_campus_semantic_requests_explicitly_disable_thinking_but_audited_requests_keep_their_contract(semantic):
    module, calls, _, _ = semantic
    messages = [{'role':'user','content':'source'}]
    module.request_json(messages)
    assert calls[0]['chat_template_kwargs'] == {'thinking': False}
    module.request_json(messages, observer=lambda *args: None)
    assert 'chat_template_kwargs' not in calls[1]


@pytest.mark.parametrize('audited', [False, True])
def test_semantic_transport_preserves_pdf_surrogates_and_valid_unicode(semantic, audited):
    import copy
    module, calls, _, _ = semantic
    messages = [{'role': 'user', 'content': '中文 α∑𝛼 source \ud8351 and \udc00'}]
    original = copy.deepcopy(messages)
    options = {'observer': lambda *args: None} if audited else {}
    result, usage = module.request_json(messages, **options)
    assert result == {'findings': []}
    assert usage == {'input_tokens': 12, 'output_tokens': 7}
    assert calls[0]['messages'] == original
    assert messages == original
