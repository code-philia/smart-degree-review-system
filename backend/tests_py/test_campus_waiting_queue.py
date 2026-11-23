"""Rate-limited requests stay queued; only actual transport uses its timeout."""
import hashlib
import os
import sqlite3
from urllib.error import HTTPError

import pytest

from paper_compiler import campus_requests as api


URL = 'https://models.sjtu.edu.cn/api/v1/chat/completions'


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
def queued_api(tmp_path, monkeypatch):
    clock = Clock()
    path = tmp_path / 'queue.sqlite'
    monkeypatch.setattr(api, 'time', clock)
    monkeypatch.setenv('SJTU_API_COORDINATOR_DB', str(path))
    monkeypatch.delenv('SJTU_API_REQUESTS_PER_MINUTE_OVERRIDE', raising=False)
    return clock, path


def test_requests_101_and_later_wait_and_all_reach_transport(queued_api):
    clock, path = queued_api
    starts = []

    def send(timeout):
        starts.append(clock.now)
        assert timeout == pytest.approx(.1)
        return len(starts)

    for expected in range(1, 106):
        assert api.campus_request(URL, {}, .1, send) == expected
    assert len(starts) == 105
    assert 60 - .00001 <= starts[100] - starts[0] < 60.2
    assert all(b - a >= .6 - .00001 for a, b in zip(starts, starts[1:]))
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM waiters').fetchone()[0] == 0


def test_repeated_429_waits_past_http_timeout_then_returns_success(queued_api):
    clock, path = queued_api
    attempts = []

    def send(timeout):
        attempts.append((clock.now, timeout))
        if len(attempts) <= 5:
            raise HTTPError(URL, 429, 'limited', {'Retry-After': '2'}, None)
        return {'ok': True}

    assert api.campus_request(URL, {}, .5, send) == {'ok': True}
    assert len(attempts) == 6
    assert clock.now >= 1010
    assert all(timeout == pytest.approx(.5) for _, timeout in attempts)
    assert all(b[0] - a[0] >= 2 for a, b in zip(attempts, attempts[1:]))
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM waiters').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM leases').fetchone()[0] == 0


def test_long_capacity_wait_keeps_same_fifo_ticket_alive(queued_api, monkeypatch):
    clock, path = queued_api
    monkeypatch.setenv('SJTU_API_MAX_CONCURRENCY', '1')
    gate = api.CampusRequestCoordinator(path, max_concurrent=1)
    headers = {'Authorization': 'Bearer queue-test'}
    account = hashlib.sha256(('models.sjtu.edu.cn\0Bearer queue-test').encode()).hexdigest()
    with gate._connection() as db:
        db.execute('INSERT INTO leases VALUES (?,?,?,?)',
                   ('occupied', account, os.getpid(), clock.now + 40))
    tickets = set()
    sleep = clock.sleep

    def observe_sleep(duration):
        with sqlite3.connect(path) as db:
            rows = db.execute('SELECT ticket,expires_at FROM waiters').fetchall()
        assert len(rows) == 1
        tickets.add(rows[0][0])
        assert rows[0][1] > clock.now
        if 1021 <= clock.now < 1030:
            assert rows[0][1] > 1040, 'The original FIFO ticket must be renewed before expiry'
        sleep(duration)

    monkeypatch.setattr(clock, 'sleep', observe_sleep)
    assert api.campus_request(URL, headers, .1, lambda timeout: timeout) == pytest.approx(.1)
    assert clock.now >= 1040
    assert len(tickets) == 1


@pytest.mark.parametrize('status', [400, 401, 403, 500])
def test_non_rate_limit_errors_still_fail_without_indefinite_retry(queued_api, status):
    attempts = []

    def send(timeout):
        attempts.append(timeout)
        raise HTTPError(URL, status, 'failed', {}, None)

    with pytest.raises(HTTPError) as failure:
        api.campus_request(URL, {}, .5, send)
    assert failure.value.code == status
    assert attempts == [.5]


def test_real_transport_timeout_still_fails_and_releases_slot(queued_api):
    _, path = queued_api

    def send(timeout):
        raise TimeoutError('socket timed out')

    with pytest.raises(TimeoutError, match='socket timed out'):
        api.campus_request(URL, {}, .5, send)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM leases').fetchone()[0] == 0


def test_cancelling_429_wait_releases_queue_and_capacity(queued_api, monkeypatch):
    clock, path = queued_api
    sleep = clock.sleep

    def interrupt(duration):
        if clock.now >= 1004:
            raise KeyboardInterrupt()
        sleep(duration)

    monkeypatch.setattr(clock, 'sleep', interrupt)

    def busy(timeout):
        raise HTTPError(URL, 429, 'limited', {'Retry-After': '2'}, None)

    with pytest.raises(KeyboardInterrupt):
        api.campus_request(URL, {}, .5, busy)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM waiters').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM leases').fetchone()[0] == 0
