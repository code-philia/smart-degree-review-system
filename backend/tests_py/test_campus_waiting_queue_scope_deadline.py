"""Campus queue waits must preserve an explicitly bounded client deadline."""
from contextlib import closing
import hashlib
import os
import sqlite3

import pytest

from paper_compiler import budget, campus_requests, llm, request_limits


class Clock:
    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now

    def monotonic(self):
        return self.now

    def sleep(self, duration):
        self.now += duration


@pytest.fixture
def scoped_campus_client(tmp_path, monkeypatch):
    clock = Clock()
    for module in (budget, campus_requests, llm, request_limits):
        monkeypatch.setattr(module, 'time', clock)
    monkeypatch.setenv('SJTU_API_KEY', 'scope-test-placeholder')
    monkeypatch.setenv('SJTU_API_BASE_URL', 'https://models.sjtu.edu.cn/api/v1')
    monkeypatch.setenv('SJTU_API_MODEL', 'deepseek-chat')
    monkeypatch.setenv('SJTU_API_MODEL_VERSION', 'scope-test')
    monkeypatch.setenv('SJTU_API_MAX_CONCURRENCY', '1')
    monkeypatch.delenv('SJTU_API_REQUESTS_PER_MINUTE_OVERRIDE', raising=False)
    path = tmp_path / 'queue.sqlite'
    monkeypatch.setenv('SJTU_API_COORDINATOR_DB', str(path))
    config = tmp_path / 'campus.env'
    config.write_text('SJTU_API_KEY=scope-test-placeholder\n'
                      'SJTU_API_BASE_URL=https://models.sjtu.edu.cn/api/v1\n'
                      'SJTU_API_MODEL=deepseek-chat\n', encoding='utf-8')
    ledger = budget.BudgetLedger(tmp_path / 'ledger.sqlite', '0', model_config=config)
    client = llm.MaasClient(config, ledger, tmp_path / 'cache', 'website', '0',
                            max_attempts=1, timeout=5)
    client = request_limits.bounded_client(client, 'one-second-scope',
                                           max_cost_cny='0', timeout_seconds=1)
    return clock, path, client


def successful_response():
    return {'choices': [{'finish_reason': 'stop', 'message': {'content': '{"ok":true}'}}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}


def assert_no_pending_requests(path):
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT count(*) FROM waiters').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM leases WHERE id!=?', ('occupied',)).fetchone()[0] == 0


def test_explicit_scope_expires_while_waiting_for_capacity(scoped_campus_client, monkeypatch):
    clock, path, client = scoped_campus_client
    campus_requests.CampusRequestCoordinator(path, max_concurrent=1)
    account = hashlib.sha256(b'models.sjtu.edu.cn\0Bearer scope-test-placeholder').hexdigest()
    with closing(sqlite3.connect(path)) as db:
        db.execute('INSERT INTO leases VALUES (?,?,?,?)',
                   ('occupied', account, os.getpid(), 1004.0))
        db.commit()
    starts = []

    def send(url, headers, payload, timeout):
        starts.append(clock.now)
        return successful_response()

    monkeypatch.setattr(llm, '_http_request', send)
    with pytest.raises((llm.ModelError, budget.BudgetExceeded)):
        client.complete_json('scope-capacity', 'JSON', {}, 10)
    assert starts == []
    assert clock.now <= 1001.25
    assert_no_pending_requests(path)


def test_explicit_scope_expires_during_429_cooldown(scoped_campus_client, monkeypatch):
    clock, path, client = scoped_campus_client
    starts = []

    def send(url, headers, payload, timeout):
        starts.append(clock.now)
        if len(starts) == 1:
            raise llm.ModelHTTPError(429, retry_after=2)
        return successful_response()

    monkeypatch.setattr(llm, '_http_request', send)
    with pytest.raises((llm.ModelError, budget.BudgetExceeded)):
        client.complete_json('scope-cooldown', 'JSON', {}, 10)
    assert starts == [1000.0]
    assert clock.now <= 1001.25
    assert_no_pending_requests(path)
