import json
from decimal import Decimal
import pytest

from paper_compiler.budget import BudgetLedger, BudgetExceeded
from paper_compiler.llm import MaasClient, ModelError


def config(tmp_path, version='20260910'):
    path = tmp_path / 'private.env'
    path.write_text('MAAS_API_KEY=test-secret-value\nMAAS_BASE_URL=https://api.modelarts-maas.com/openai/v1\nMAAS_MODEL=deepseek-v4.1-flash\nMAAS_MODEL_VERSION=' + version + '\nMAAS_REGION=cn-southwest-2\n')
    path.chmod(0o600)
    return path


def response(content='{"answer":42}', usage=None, finish='stop'):
    return {'choices': [{'message': {'content': content}, 'finish_reason': finish}],
            'usage': usage if usage is not None else {'prompt_tokens': 100, 'completion_tokens': 50}}


def make_client(tmp_path, transport, total='10', attempts=2):
    ledger = BudgetLedger(tmp_path / 'budget.db', Decimal(total))
    client = MaasClient(config(tmp_path), ledger, tmp_path/'cache', 'pilot', Decimal('5'),
                        transport=transport, max_attempts=attempts, retry_delay=0)
    return client, ledger


def test_structured_result_cache_avoids_rebilling_and_never_logs_key(tmp_path):
    calls = []
    def transport(url, headers, payload, timeout):
        calls.append(payload)
        assert headers['Authorization'] == 'Bearer test-secret-value'
        return response()
    client, ledger = make_client(tmp_path, transport)
    assert client.complete_json('extract-v1', 'Return JSON', {'text':'原文'}, 100) == {'answer':42}
    assert client.complete_json('extract-v1', 'Return JSON', {'text':'原文'}, 100) == {'answer':42}
    assert len(calls) == 1
    assert calls[0]['max_completion_tokens'] == 100
    assert 'max_tokens' not in calls[0]
    assert 'version' not in calls[0]
    assert ledger.summary()['requests'] == 1
    assert ledger.summary()['spent_cny'] == '0.000600'
    for path in (tmp_path/'cache').rglob('*.json'):
        assert 'test-secret-value' not in path.read_text()


def test_invalid_output_is_billed_before_bounded_retry(tmp_path):
    responses = iter([response('not json'), response()])
    client, ledger = make_client(tmp_path, lambda *args: next(responses))
    assert client.complete_json('extract', 'JSON', {}, 100) == {'answer':42}
    assert ledger.summary()['requests'] == 2
    assert ledger.summary()['spent_cny'] == '0.001200'


def test_missing_usage_and_timeout_keep_cost_reservations(tmp_path):
    client, ledger = make_client(tmp_path, lambda *args: response(usage={}), attempts=1)
    with pytest.raises(ModelError):
        client.complete_json('extract', 'JSON', {}, 100)
    assert Decimal(ledger.summary()['committed_cny']) > 0
    assert ledger.summary()['uncertain_requests'] == 1


def test_exception_content_is_redacted_and_retry_bounded(tmp_path):
    calls = []
    def fail(*args):
        calls.append(1)
        raise TimeoutError('Bearer test-secret-value private document text')
    client, ledger = make_client(tmp_path, fail)
    with pytest.raises(ModelError) as error:
        client.complete_json('extract', 'JSON', {}, 100)
    assert len(calls) == 2
    assert 'test-secret' not in str(error.value)
    assert 'private document' not in str(error.value)
    assert ledger.summary()['uncertain_requests'] == 2


def test_insufficient_budget_stops_before_request(tmp_path):
    calls = []
    client, ledger = make_client(tmp_path, lambda *args: calls.append(1), total='0.000001')
    with pytest.raises(BudgetExceeded):
        client.complete_json('extract', 'JSON', {}, 100)
    assert calls == []
    assert ledger.summary()['requests'] == 0


def test_changed_prompt_and_model_version_do_not_reuse_cached_result(tmp_path):
    calls = []
    def transport(*args):
        calls.append(1)
        return response()
    client, ledger = make_client(tmp_path, transport)
    client.complete_json('extract', 'Prompt A', {}, 100)
    client.complete_json('extract', 'Prompt B', {}, 100)
    changed = MaasClient(config(tmp_path, 'new-version'), ledger, tmp_path/'cache', 'pilot', Decimal('5'), transport=transport)
    changed.complete_json('extract', 'Prompt A', {}, 100)
    assert len(calls) == 3


def test_truncated_model_json_is_not_a_valid_cache_entry(tmp_path):
    client, ledger = make_client(tmp_path, lambda *args: response(finish='length'), attempts=1)
    with pytest.raises(ModelError):
        client.complete_json('extract', 'JSON', {}, 100)
    assert ledger.summary()['spent_cny'] == '0.000600'
    assert not list((tmp_path/'cache'/'responses').glob('*.json'))


def test_output_budget_includes_reasoning_even_if_provider_default_changes(tmp_path):
    def transport(url, headers, payload, timeout):
        maximum = payload.get('max_completion_tokens', 100000)
        return response(usage={'prompt_tokens': 100, 'completion_tokens': min(10000, maximum)})
    client, ledger = make_client(tmp_path, transport, attempts=1)
    assert client.complete_json('extract', 'JSON', {}, 100) == {'answer':42}
    assert ledger.summary()['completion_tokens'] == 100
    assert not ledger.summary()['blocked']


def test_invalid_output_preserves_finish_reason_and_content_for_diagnosis(tmp_path):
    client,_=make_client(tmp_path,lambda *args:response('```json\n{}\n```',finish='length'),attempts=1)
    with pytest.raises(ModelError):client.complete_json('diagnostic','JSON',{},100)
    record=json.loads(next((tmp_path/'cache/attempts').glob('*.json')).read_text())
    assert record['finish_reason']=='length'
    assert record['output_content'].startswith('```json')

def test_effective_model_fingerprint_binds_versions_but_not_credentials():
    from paper_compiler.llm import public_model_config,model_fingerprint
    a={'MAAS_BASE_URL':'https://api.modelarts-maas.com/openai/v1','MAAS_MODEL':'deepseek-v4.1-flash','MAAS_MODEL_VERSION':'one','MAAS_API_KEY':'private-one'}
    assert 'API_KEY' not in str(public_model_config(a))
    assert model_fingerprint(a)==model_fingerprint({**a,'MAAS_API_KEY':'rotated'})
    assert model_fingerprint(a)!=model_fingerprint({**a,'MAAS_MODEL_VERSION':'two'})
