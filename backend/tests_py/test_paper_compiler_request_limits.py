"""Task bounds use the existing ledger and fake transports only."""
from concurrent.futures import ProcessPoolExecutor
from decimal import Decimal
import json
import multiprocessing
import sqlite3

import pytest

from paper_compiler.budget import BudgetExceeded, BudgetLedger
from paper_compiler.llm import MaasClient, ModelError


def _bounded(*args, **kwargs):
    from paper_compiler.request_limits import bounded_client
    return bounded_client(*args, **kwargs)


def _client(tmp_path, transport, *, timeout=120, attempts=3):
    config = tmp_path / 'private.env'
    config.write_text('MAAS_API_KEY=private-do-not-print\n'
                      'MAAS_BASE_URL=https://api.modelarts-maas.com/openai/v1\n'
                      'MAAS_MODEL=deepseek-v4.1-flash\nMAAS_MODEL_VERSION=fake-v1\n')
    ledger = BudgetLedger(tmp_path / 'budget.db', Decimal('200'))
    client = MaasClient(config, ledger, tmp_path / 'cache', 'framework-20261019',
                        Decimal('200'), transport=transport, timeout=timeout,
                        max_attempts=attempts, retry_delay=0)
    return client, ledger


def _response():
    return {'usage': {'prompt_tokens': 100, 'completion_tokens': 50},
            'choices': [{'finish_reason': 'stop', 'message': {'content': '{"answer":42}'}}]}


def _reserve_in_process(args):
    path, request_id = args
    ledger = BudgetLedger(path, Decimal('200'))
    ledger.ensure_scope('concurrent-task', '1', 1200)
    try:
        ledger.reserve(request_id, '.2', 'framework-20261019', '200', scope_id='concurrent-task')
        return True
    except BudgetExceeded:
        return False


def test_paid_reservation_checks_scope_before_transport_without_replacing_global_ledger(tmp_path):
    calls = []
    client, ledger = _client(tmp_path, lambda *args: calls.append(args) or _response())
    limited = _bounded(client, 'pdf-one', max_cost_cny='.004')
    assert limited.ledger is ledger
    assert limited.complete_json('parse', 'JSON', {}, 100) == {'answer': 42}
    with pytest.raises(BudgetExceeded, match='scope'):
        limited.complete_json('normal-semantics', 'JSON', {}, 100)
    assert len(calls) == 1
    assert limited.scope_summary()['spent_cny'] == '0.000600'
    assert ledger.summary()['limit_cny'] == '200.000000'
    assert ledger.summary()['requests'] == 1


def test_scope_reservations_are_atomic_across_processes(tmp_path):
    path = tmp_path / 'budget.db'
    ledger = BudgetLedger(path, Decimal('200'))
    ledger.ensure_scope('concurrent-task', '1', 1200)
    with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context('spawn')) as pool:
        accepted = list(pool.map(_reserve_in_process, [(path, str(i)) for i in range(16)]))
    assert sum(accepted) == 5
    assert ledger.scope_summary('concurrent-task')['committed_cny'] == '1.000000'
    assert ledger.summary()['committed_cny'] == '1.000000'


def test_scope_is_additional_to_global_cap_and_does_not_hide_existing_spend(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.db', Decimal('200'))
    ledger.reserve('previous-study', '199.99', 'framework-20261019', '200')
    ledger.ensure_scope('online-task', '5', 1200)
    ledger.reserve('last-room', '.01', 'framework-20261019', '200', scope_id='online-task')
    with pytest.raises(BudgetExceeded):
        ledger.reserve('more', '.01', 'framework-20261019', '200', scope_id='online-task')
    assert ledger.scope_summary('online-task')['committed_cny'] == '0.010000'
    assert ledger.summary()['committed_cny'] == '200.000000'


def test_uncertain_charge_occupies_scope_and_resume_cannot_reset_it(tmp_path):
    calls = []
    def fail(*args):
        calls.append(1)
        raise TimeoutError('private-do-not-print')
    client, ledger = _client(tmp_path, fail)
    limited = _bounded(client, 'resume-me', max_cost_cny='.005')
    with pytest.raises(ModelError):
        limited.complete_json('audit', 'JSON', {}, 100)
    resumed = _bounded(client, 'resume-me', max_cost_cny='.005')
    with pytest.raises(BudgetExceeded):
        resumed.complete_json('revision', 'JSON', {}, 100)
    assert len(calls) == 1
    summary = resumed.scope_summary()
    assert summary['uncertain_requests'] == 1
    assert Decimal(summary['committed_cny']) > 0
    assert ledger.summary()['uncertain_requests'] == 1


def test_scope_persists_deadline_and_rejects_changed_resume_configuration(tmp_path, monkeypatch):
    import time
    now = [1000.0]
    monkeypatch.setattr(time, 'time', lambda: now[0])
    client, _ = _client(tmp_path, lambda *args: _response())
    first = _bounded(client, 'same-task', max_cost_cny='5', timeout_seconds=20)
    assert first.scope_summary()['deadline_at'] == 1020.0
    now[0] = 1015.0
    resumed = _bounded(client, 'same-task', max_cost_cny='5', timeout_seconds=20)
    assert resumed.scope_summary()['deadline_at'] == 1020.0
    assert 0 < resumed.scope_summary()['remaining_seconds'] <= 5
    for kwargs in [dict(max_cost_cny='6', timeout_seconds=20),
                   dict(max_cost_cny='5', timeout_seconds=21)]:
        with pytest.raises(ValueError, match='scope'):
            _bounded(client, 'same-task', **kwargs)


def test_expired_scope_stops_new_requests_without_transport_or_reservation(tmp_path, monkeypatch):
    import time
    now = [1000.0]
    monkeypatch.setattr(time, 'time', lambda: now[0])
    calls = []
    client, ledger = _client(tmp_path, lambda *args: calls.append(1) or _response())
    limited = _bounded(client, 'short-task', timeout_seconds=5)
    now[0] = 1005.0
    with pytest.raises(BudgetExceeded, match='deadline'):
        limited.complete_json('revision', 'JSON', {}, 100)
    assert calls == []
    assert ledger.summary()['requests'] == 0


def test_transport_timeout_is_recalculated_after_waiting_for_slot(tmp_path, monkeypatch):
    import time
    import paper_compiler.llm as llm
    now = [1000.0]
    monkeypatch.setattr(time, 'time', lambda: now[0])
    waits, timeouts, released = [], [], []
    class Slot:
        def acquire(self, timeout=None):
            waits.append(timeout)
            now[0] += 4
            return True
        def release(self):
            released.append(True)
    monkeypatch.setattr(llm, '_PROCESS_SLOTS', Slot())
    client, _ = _client(tmp_path, lambda url, headers, payload, timeout: timeouts.append(timeout) or _response())
    limited = _bounded(client, 'queue-task', timeout_seconds=6)
    limited.complete_json('parse', 'JSON', {}, 100)
    assert 0 < waits[0] <= 6
    assert 0 < timeouts[0] <= 2
    assert released == [True]


def test_expired_waiting_for_transport_slot_does_not_reserve_or_send(tmp_path, monkeypatch):
    import paper_compiler.llm as llm
    waits, calls = [], []
    class FullSlot:
        def acquire(self, timeout=None):
            waits.append(timeout)
            return False
        def release(self):
            raise AssertionError('unacquired slot must not be released')
    monkeypatch.setattr(llm, '_PROCESS_SLOTS', FullSlot())
    client, ledger = _client(tmp_path, lambda *args: calls.append(1))
    limited = _bounded(client, 'queue-task', timeout_seconds=6)
    with pytest.raises(BudgetExceeded, match='deadline'):
        limited.complete_json('parse', 'JSON', {}, 100)
    assert 0 < waits[0] <= 6
    assert calls == []
    assert ledger.summary()['requests'] == 0


def test_shorter_original_transport_timeout_is_preserved(tmp_path):
    timeouts = []
    client, _ = _client(tmp_path, lambda url, headers, payload, timeout: timeouts.append(timeout) or _response(), timeout=.5)
    _bounded(client, 'task', timeout_seconds=100).complete_json('parse', 'JSON', {}, 100)
    assert timeouts == [.5]


def test_cache_hit_remains_free_even_when_scope_cost_is_exhausted(tmp_path):
    calls = []
    client, ledger = _client(tmp_path, lambda *args: calls.append(1) or _response())
    limited = _bounded(client, 'cached-task', max_cost_cny='5')
    assert limited.complete_json('parse', 'JSON', {}, 100) == {'answer': 42}
    ledger.reserve('consume-rest', '4.9994', client.phase, '200', scope_id='cached-task')
    ledger.settle('consume-rest', {}, '4.9994')
    before = ledger.summary()
    assert limited.complete_json('parse', 'JSON', {}, 100) == {'answer': 42}
    assert ledger.summary() == before
    with pytest.raises(BudgetExceeded):
        limited.complete_json('parse', 'changed instruction', {}, 100)
    assert calls == [1]


def test_bounded_clone_disables_retries_without_mutating_client_or_logging_secret(tmp_path):
    calls = []
    def fail(*args):
        calls.append(1)
        raise TimeoutError('private-do-not-print')
    client, _ = _client(tmp_path, fail, attempts=3)
    limited = _bounded(client, 'one-attempt')
    assert limited.max_attempts == 1
    assert client.max_attempts == 3
    assert limited.config == client.config
    assert limited.cache_dir == client.cache_dir
    with pytest.raises(ModelError) as error:
        limited.complete_json('revision', 'JSON', {}, 100)
    assert calls == [1]
    assert 'private-do-not-print' not in str(error.value)
    assert 'private-do-not-print' not in repr(limited)
    for path in (tmp_path / 'cache').rglob('*.json'):
        assert 'private-do-not-print' not in path.read_text()


def test_fake_client_ledger_reservations_receive_the_same_scope_cap(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.db', Decimal('200'))
    class FakeClient:
        config = {'MAAS_MODEL': 'fake'}
        max_attempts = 3
        def __init__(self):
            self.ledger = ledger
            self.calls = []
        def complete_json(self, task, instructions, data, max_tokens):
            request_id = str(len(self.calls))
            self.ledger.reserve(request_id, '3', 'fake', '200')
            self.calls.append(task)
            self.ledger.settle(request_id, {}, '3')
            return {'answer': task}
    original = FakeClient()
    limited = _bounded(original, 'fake-task')
    assert limited.complete_json('parse', 'JSON', {}, 100) == {'answer': 'parse'}
    with pytest.raises(BudgetExceeded):
        limited.complete_json('audit', 'JSON', {}, 100)
    assert limited.ledger is ledger
    assert original.ledger is ledger
    assert original.calls == ['parse']
    assert limited.scope_summary()['spent_cny'] == '3.000000'


def test_unmetered_fake_client_still_has_deadline_without_fabricating_cost(tmp_path, monkeypatch):
    import time
    now = [1000.0]
    monkeypatch.setattr(time, 'time', lambda: now[0])
    class FakeClient:
        config = {'MAAS_MODEL': 'fake'}
        def complete_json(self, *args):
            return {'fake': True}
    limited = _bounded(FakeClient(), 'unit-test', timeout_seconds=5)
    assert limited.complete_json('parse', 'JSON', {}, 100) == {'fake': True}
    assert limited.scope_summary()['cost_accounting'] == 'unavailable'
    now[0] = 1006
    with pytest.raises(BudgetExceeded):
        limited.complete_json('audit', 'JSON', {}, 100)


def test_existing_legacy_ledger_keeps_all_requests_when_scope_tables_are_added(tmp_path):
    path = tmp_path / 'budget.db'
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO settings VALUES ('limit_micro','200000000');
            CREATE TABLE phases (name TEXT PRIMARY KEY, limit_micro INTEGER NOT NULL);
            INSERT INTO phases VALUES ('old',200000000);
            CREATE TABLE requests (id TEXT PRIMARY KEY, phase TEXT NOT NULL,
              reserved_micro INTEGER NOT NULL, charged_micro INTEGER, status TEXT NOT NULL,
              created_at REAL NOT NULL, updated_at REAL NOT NULL, usage_json TEXT, reason TEXT);
            INSERT INTO requests VALUES ('old-call','old',1000000,NULL,'uncertain',1,1,NULL,'timeout');
        """)
    ledger = BudgetLedger(path, Decimal('200'))
    ledger.ensure_scope('new-task', '5', 1200)
    assert ledger.summary()['committed_cny'] == '1.000000'
    assert ledger.scope_summary('new-task')['committed_cny'] == '0.000000'
    ledger.reserve('new-call', '2', 'new', '200', scope_id='new-task')
    assert ledger.summary()['committed_cny'] == '3.000000'


@pytest.mark.parametrize('kwargs', [dict(scope_id=''), dict(scope_id=42),
    dict(max_cost_cny='0'), dict(max_cost_cny='NaN'), dict(max_cost_cny='-1'),
    dict(timeout_seconds=0), dict(timeout_seconds=-1), dict(timeout_seconds=float('inf')),
    dict(timeout_seconds=float('nan')), dict(timeout_seconds=True)])
def test_invalid_limits_are_rejected_before_any_call(tmp_path, kwargs):
    client, ledger = _client(tmp_path, lambda *args: _response())
    arguments = {'scope_id': 'task', **kwargs}
    with pytest.raises((ValueError, TypeError)):
        _bounded(client, **arguments)
    assert ledger.summary()['requests'] == 0


def test_phase_limit_remains_independent_of_task_scope(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.db', Decimal('200'))
    ledger.ensure_scope('task', '5', 1200)
    ledger.reserve('phase-used', '.9', 'small-phase', '1')
    with pytest.raises(BudgetExceeded, match='phase'):
        ledger.reserve('scope-has-room', '.2', 'small-phase', '1', scope_id='task')
    assert ledger.scope_summary('task')['requests'] == 0
    assert ledger.summary()['committed_cny'] == '0.900000'


def test_direct_ledger_reservation_checks_persisted_deadline_in_transaction(tmp_path, monkeypatch):
    import time
    now = [1000.0]
    monkeypatch.setattr(time, 'time', lambda: now[0])
    ledger = BudgetLedger(tmp_path / 'budget.db', Decimal('200'))
    ledger.ensure_scope('task', '5', 1)
    now[0] = 1001.0
    with pytest.raises(BudgetExceeded, match='deadline'):
        ledger.reserve('late', '1', 'phase', '200', scope_id='task')
    assert ledger.scope_summary('task')['requests'] == 0


def test_wall_clock_rollback_does_not_extend_current_process_deadline(tmp_path, monkeypatch):
    import time
    wall, monotonic = [1000.0], [50.0]
    monkeypatch.setattr(time, 'time', lambda: wall[0])
    monkeypatch.setattr(time, 'monotonic', lambda: monotonic[0])
    client, ledger = _client(tmp_path, lambda *args: _response())
    limited = _bounded(client, 'task', timeout_seconds=5)
    wall[0], monotonic[0] = 900.0, 55.0
    with pytest.raises(BudgetExceeded, match='deadline'):
        limited.complete_json('parse', 'JSON', {}, 100)
    assert ledger.summary()['requests'] == 0


def test_nested_wrapper_is_idempotent_and_cannot_replace_outer_task_limits(tmp_path):
    client, _ = _client(tmp_path, lambda *args: _response())
    limited = _bounded(client, 'task')
    assert _bounded(limited, 'task') is limited
    with pytest.raises(ValueError, match='scope'):
        _bounded(limited, 'different-task')


def test_expiry_exactly_as_slot_opens_releases_slot_without_reserving(tmp_path, monkeypatch):
    import time
    import paper_compiler.llm as llm
    now, released = [1000.0], []
    monkeypatch.setattr(time, 'time', lambda: now[0])
    class Slot:
        def acquire(self, timeout=None):
            now[0] += 5
            return True
        def release(self):
            released.append(True)
    monkeypatch.setattr(llm, '_PROCESS_SLOTS', Slot())
    client, ledger = _client(tmp_path, lambda *args: pytest.fail('expired request was sent'))
    limited = _bounded(client, 'task', timeout_seconds=5)
    with pytest.raises(BudgetExceeded, match='deadline'):
        limited.complete_json('parse', 'JSON', {}, 100)
    assert ledger.summary()['requests'] == 0
    assert released == [True]


def test_missing_usage_is_conservatively_committed_to_the_task_scope(tmp_path):
    response = _response()
    response.pop('usage')
    client, ledger = _client(tmp_path, lambda *args: response)
    limited = _bounded(client, 'task', max_cost_cny='.005')
    with pytest.raises(ModelError):
        limited.complete_json('semantic', 'JSON', {}, 100)
    with pytest.raises(BudgetExceeded):
        limited.complete_json('audit', 'JSON', {}, 100)
    assert limited.scope_summary()['uncertain_requests'] == 1
    assert limited.scope_summary()['committed_cny'] == ledger.summary()['committed_cny']
