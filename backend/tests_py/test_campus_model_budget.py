"""Campus requests retain accounting and deadlines without monetary caps."""
import sqlite3
import time

import pytest

from paper_compiler.budget import BudgetExceeded, BudgetLedger
from paper_compiler.llm import MaasClient
from paper_compiler.request_limits import RequestDeadlineExceeded, bounded_client


def campus_config(tmp_path):
    config = tmp_path / 'campus.env'
    config.write_text('SJTU_API_KEY=test-campus-key\nSJTU_API_BASE_URL=https://models.sjtu.edu.cn/api/v1\nSJTU_API_MODEL=deepseek-chat\n')
    return config


def response(*args):
    return {'choices': [{'message': {'content': '{"ok":true}'}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 50}}


def test_campus_reopens_exhausted_ledger_without_resetting_history(tmp_path):
    path = tmp_path / 'ledger.sqlite'
    legacy = BudgetLedger(path, '1')
    legacy.reserve('old', '1', 'website', '1')
    legacy.mark_uncertain('old', 'timeout')
    legacy.ensure_scope('task', '.000001', 1200)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO settings VALUES ('blocked','historical estimate anomaly')")
    ledger = BudgetLedger(path, '0', model_config=campus_config(tmp_path))
    ledger.ensure_scope('task', '0', 1200)
    ledger.reserve('new', '1000', 'website', '0', scope_id='task')
    ledger.settle('new', {'prompt_tokens': 5}, '2000')
    assert ledger.summary()['requests'] == 2
    assert ledger.summary()['uncertain_requests'] == 1
    assert ledger.summary()['limit_cny'] is None
    assert ledger.summary()['remaining_cny'] is None
    assert ledger.summary()['budget_enforced'] is False
    assert ledger.scope_summary('task')['limit_cny'] is None
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT status,reserved_micro FROM requests WHERE id='old'").fetchone() == ('uncertain', 1000000)
        assert db.execute("SELECT value FROM settings WHERE key='limit_micro'").fetchone()[0] == '1000000'
    with pytest.raises(BudgetExceeded):
        legacy.reserve('still-paid', '.1', 'paid', '1')


def test_campus_client_ignores_task_money_cap_but_preserves_cache_and_usage(tmp_path):
    calls = []
    ledger = BudgetLedger(tmp_path / 'ledger.sqlite', '.000001')
    client = MaasClient(campus_config(tmp_path), ledger, tmp_path / 'cache', 'website', '.000001',
                        transport=lambda *args: calls.append(1) or response(), max_attempts=1)
    client = bounded_client(client, 'campus-task', max_cost_cny='.000001', timeout_seconds=30)
    assert client.complete_json('one', 'JSON', {}, 100) == {'ok': True}
    assert client.complete_json('two', 'JSON', {}, 100) == {'ok': True}
    assert client.complete_json('two', 'JSON', {}, 100) == {'ok': True}
    assert len(calls) == 2
    assert client.scope_summary()['budget_enforced'] is False
    assert client.ledger.summary()['prompt_tokens'] == 200


def test_campus_scope_deadline_still_stops_transport(tmp_path, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, 'time', lambda: now[0])
    calls = []
    ledger = BudgetLedger(tmp_path / 'ledger.sqlite', '0', model_config=campus_config(tmp_path))
    client = MaasClient(campus_config(tmp_path), ledger, tmp_path / 'cache', 'website', '0',
                        transport=lambda *args: calls.append(1) or response(), max_attempts=1)
    client = bounded_client(client, 'expires', max_cost_cny='0', timeout_seconds=10)
    now[0] = 1011.0
    with pytest.raises(RequestDeadlineExceeded):
        client.complete_json('late', 'JSON', {}, 100)
    assert calls == []


def test_campus_deadline_is_not_reset_on_resume(tmp_path, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, 'time', lambda: now[0])
    ledger = BudgetLedger(tmp_path / 'ledger.sqlite', '0', model_config=campus_config(tmp_path))
    first = ledger.ensure_scope('same', '0', 20)
    now[0] = 1015.0
    assert ledger.ensure_scope('same', '500', 20)['deadline_at'] == first['deadline_at']
    now[0] = 1021.0
    with pytest.raises(BudgetExceeded, match='deadline'):
        ledger.reserve('late', '.1', 'website', '0', scope_id='same')


def test_campus_repair_suggestion_ignores_old_website_cap(tmp_path):
    import importlib.util
    from pathlib import Path
    script = Path(__file__).parents[1] / 'scripts/repair_model_proposal.py'
    spec = importlib.util.spec_from_file_location('campus_repair_budget_test', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ledger = BudgetLedger(tmp_path / 'repair.sqlite', '1')
    ledger.reserve('old', '1', 'website', '1')
    result = module.execute([{'role': 'system', 'content': 'JSON'}, {'role': 'user', 'content': '{}'}],
                            config_path=campus_config(tmp_path), ledger=ledger,
                            cache=tmp_path / 'repair-cache', transport=response)
    assert result['answer'] == {'ok': True}
    assert result['usage']['input_tokens'] == 100
