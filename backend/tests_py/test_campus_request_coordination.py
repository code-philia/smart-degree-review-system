from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack
import hashlib
import importlib
import json
import multiprocessing
import sqlite3
import time
from urllib.error import HTTPError

import pytest


def coordinator():
    return importlib.import_module('paper_compiler.campus_requests')


class Clock:
    def __init__(self): self.now = 1000.0
    def time(self): return self.now
    def monotonic(self): return self.now
    def sleep(self, value): self.now += value


def fake_clock(monkeypatch):
    api = coordinator()
    clock = Clock()
    monkeypatch.setattr(api, 'time', clock)
    return api, clock


def test_request_starts_are_spaced_across_coordinator_instances(tmp_path, monkeypatch):
    api, clock = fake_clock(monkeypatch)
    path = tmp_path / 'rate.sqlite'
    starts = []
    for _ in range(5):
        gate = api.CampusRequestCoordinator(path, max_concurrent=8, requests_per_minute=90)
        with gate.slot('account', timeout=10):
            starts.append(clock.now)
    assert all(b - a >= 60 / 90 - .00001 for a, b in zip(starts, starts[1:]))


@pytest.mark.parametrize('transport', [False, True])
def test_default_capacity_allows_sixteen_inflight_requests_then_waits(tmp_path, monkeypatch, transport):
    api, clock = fake_clock(monkeypatch)
    path = tmp_path / 'rate.sqlite'
    monkeypatch.setenv('SJTU_API_COORDINATOR_DB', str(path))
    monkeypatch.delenv('SJTU_API_MAX_CONCURRENCY', raising=False)
    gate = api.CampusRequestCoordinator(path)
    def slot(timeout):
        return (api.campus_request_slot('https://models.sjtu.edu.cn/api/v1/chat/completions',
                                       {'Authorization': 'Bearer capacity-test'}, timeout)
                if transport else gate.slot('same-account', timeout=timeout))
    with ExitStack() as slots:
        for _ in range(16):
            slots.enter_context(slot(15))
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT count(*) FROM leases').fetchone()[0] == 16
        with pytest.raises(TimeoutError):
            with slot(.2):
                pytest.fail('The seventeenth request must wait for capacity')
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM leases').fetchone()[0] == 0


def _process_request(values):
    path, duration = values
    api = coordinator()
    gate = api.CampusRequestCoordinator(path, max_concurrent=2, requests_per_minute=100)
    with gate.slot('same-account', timeout=10):
        begin = time.time()
        time.sleep(duration)
        return begin, time.time()


def test_concurrency_limit_is_shared_by_processes(tmp_path):
    with ProcessPoolExecutor(max_workers=3, mp_context=multiprocessing.get_context('spawn')) as pool:
        intervals = list(pool.map(_process_request, [(tmp_path / 'rate.sqlite', 1.3)] * 3))
    events = sorted([(begin, 1) for begin, _ in intervals] + [(end, -1) for _, end in intervals])
    active = peak = 0
    for _, change in events:
        active += change
        peak = max(peak, active)
    assert peak == 2
    assert max(end for _, end in intervals) - min(start for start, _ in intervals) < 3.8


def test_429_cooldown_and_wait_deadline_apply_to_all_workers(tmp_path, monkeypatch):
    api, clock = fake_clock(monkeypatch)
    gate = api.CampusRequestCoordinator(tmp_path / 'rate.sqlite', max_concurrent=8, requests_per_minute=90)
    with pytest.raises(HTTPError):
        with gate.slot('same', timeout=10):
            raise HTTPError('https://models.sjtu.edu.cn/api/v1', 429, 'rate limit', {'Retry-After': '2'}, None)
    with pytest.raises(TimeoutError):
        with gate.slot('same', timeout=.5):
            pytest.fail('A different worker must honor the shared cooldown')
    clock.now += 2
    with gate.slot('same', timeout=1):
        pass


def test_failed_request_releases_its_concurrent_slot(tmp_path, monkeypatch):
    api, clock = fake_clock(monkeypatch)
    gate = api.CampusRequestCoordinator(tmp_path / 'rate.sqlite', max_concurrent=1, requests_per_minute=90)
    with pytest.raises(RuntimeError):
        with gate.slot('same', timeout=10): raise RuntimeError('transport')
    with gate.slot('same', timeout=2): pass


def test_noncampus_transport_does_not_use_campus_coordination(tmp_path, monkeypatch):
    api = coordinator()
    path = tmp_path / 'unused.sqlite'
    monkeypatch.setenv('SJTU_API_COORDINATOR_DB', str(path))
    with api.campus_request_slot('https://api.modelarts-maas.com/openai/v1/chat/completions', {}, 4) as timeout:
        assert timeout == 4
    assert not path.exists()


def test_compiler_and_semantic_transports_share_one_account_without_storing_key(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    from paper_compiler.llm import _http
    path = tmp_path / 'shared.sqlite'
    monkeypatch.setenv('SJTU_API_COORDINATOR_DB', str(path))
    monkeypatch.setenv('SJTU_API_KEY', 'private-campus-test-token')
    monkeypatch.setenv('SJTU_API_BASE_URL', 'https://models.sjtu.edu.cn/api/v1')
    monkeypatch.setenv('SJTU_API_MODEL', 'deepseek-chat')
    script = Path(__file__).parents[1] / 'scripts/run_bilingual_semantic_lint.py'
    spec = importlib.util.spec_from_file_location('coordinated_semantic_transport', script)
    semantic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(semantic)
    payload = {'choices': [{'finish_reason': 'stop', 'message': {'content': '{"ok":true}'}}],
               'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size): return json.dumps(payload).encode()
    class Opener:
        def open(self, request, *, timeout): return Response()
    monkeypatch.setattr(semantic.urllib.request, 'build_opener', lambda *a: Opener())
    _http('https://models.sjtu.edu.cn/api/v1/chat/completions',
          {'Authorization': 'Bearer private-campus-test-token'}, {}, 5)
    assert semantic.request_json([{'role': 'user', 'content': 'test'}])[0] == {'ok': True}
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM accounts').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM leases').fetchone()[0] == 0
    assert b'private-campus-test-token' not in path.read_bytes()


def test_expired_or_abandoned_slots_do_not_block_new_requests(tmp_path, monkeypatch):
    api, clock = fake_clock(monkeypatch)
    path = tmp_path / 'rate.sqlite'
    gate = api.CampusRequestCoordinator(path, max_concurrent=1, requests_per_minute=90)
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO leases VALUES (?,?,?,?)', ('expired', 'same', 1, clock.now - 1))
    with gate.slot('same', timeout=1): pass


def test_campus_rate_limit_waits_and_retries_until_success(tmp_path, monkeypatch):
    api, clock = fake_clock(monkeypatch)
    monkeypatch.setenv('SJTU_API_COORDINATOR_DB', str(tmp_path / 'retry.sqlite'))
    attempts = []
    def send(timeout):
        attempts.append((clock.now, timeout))
        if len(attempts) < 6:
            raise HTTPError('https://models.sjtu.edu.cn/api/v1', 429, 'busy', {'Retry-After': '2'}, None)
        return {'ok': True}
    value = api.campus_request('https://models.sjtu.edu.cn/api/v1/chat/completions', {}, 30, send)
    assert value == {'ok': True}
    assert len(attempts) == 6
    assert all(b[0] - a[0] >= 2 for a, b in zip(attempts, attempts[1:]))
    assert attempts[-1][1] < attempts[0][1]


def test_rate_limit_retries_keep_one_deadline_and_do_not_retry_auth_failures(tmp_path, monkeypatch):
    api, clock = fake_clock(monkeypatch)
    monkeypatch.setenv('SJTU_API_COORDINATOR_DB', str(tmp_path / 'deadline.sqlite'))
    def busy(timeout):
        raise HTTPError('https://models.sjtu.edu.cn/api/v1', 429, 'busy', {'Retry-After': '2'}, None)
    with pytest.raises(TimeoutError):
        api.campus_request('https://models.sjtu.edu.cn/api/v1/chat/completions', {}, 3, busy)
    assert clock.now < 1003.1
    calls = []
    def denied(timeout):
        calls.append(timeout)
        raise HTTPError('https://models.sjtu.edu.cn/api/v1', 401, 'denied', {}, None)
    with pytest.raises(HTTPError):
        api.campus_request('https://models.sjtu.edu.cn/api/v1/chat/completions', {}, 10, denied)
    assert len(calls) == 1
