from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
import hashlib
import importlib
import json
import multiprocessing
import os
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


def test_short_database_write_lock_does_not_fail_coordinator_initialization(tmp_path):
    path = tmp_path / 'contended.sqlite'
    api = coordinator()
    api.CampusRequestCoordinator(path)
    with sqlite3.connect(path, isolation_level=None) as db, ThreadPoolExecutor(max_workers=1) as pool:
        db.execute('BEGIN EXCLUSIVE')
        future = pool.submit(api.CampusRequestCoordinator, path)
        try:
            time.sleep(1.3)
        finally:
            db.rollback()
        assert future.result(timeout=5).path == path


def test_short_database_write_lock_does_not_fail_slot_cleanup(tmp_path):
    from threading import Event
    path = tmp_path / 'cleanup.sqlite'
    gate = coordinator().CampusRequestCoordinator(path)
    entered, finish = Event(), Event()
    def request():
        with gate.slot('account', timeout=10):
            entered.set()
            assert finish.wait(5)
        return True
    with ThreadPoolExecutor(max_workers=1) as pool, sqlite3.connect(path, isolation_level=None) as db:
        future = pool.submit(request)
        assert entered.wait(3)
        db.execute('BEGIN EXCLUSIVE')
        finish.set()
        try:
            time.sleep(1.3)
        finally:
            db.rollback()
        assert future.result(timeout=5)
        assert db.execute('SELECT count(*) FROM leases').fetchone()[0] == 0


def test_qwen_and_detection_use_one_account_without_slowing_shared_request_pacing(tmp_path, monkeypatch):
    from pathlib import Path
    import importlib.util
    api, clock = fake_clock(monkeypatch)
    path = tmp_path / 'shared-model-rate.sqlite'
    monkeypatch.setenv('SJTU_API_COORDINATOR_DB', str(path))
    monkeypatch.setenv('SJTU_API_REQUESTS_PER_MINUTE', '90')
    monkeypatch.setenv('SJTU_API_MODEL', 'deepseek-chat')
    monkeypatch.delenv('REPORT_TRANSLATION_MODEL', raising=False)
    script = Path(__file__).parents[1] / 'scripts' / 'report_translation.py'
    spec = importlib.util.spec_from_file_location('shared_rate_translation', script)
    translation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(translation)
    starts = []
    def request():
        with api.campus_request_slot('https://models.sjtu.edu.cn/api/v1/chat/completions',
                                     {'Authorization': 'Bearer same-account'}, 10):
            starts.append(clock.now)
    request()
    with translation.translation_environment():
        request()
    request()
    assert starts == pytest.approx([1000.0, 1000.0 + 2/3, 1000.0 + 4/3])
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM accounts').fetchone()[0] == 1


def _paused_waiting_process(path, polled, resume, result):
    """Pause after a real denied SQLite attempt, outside its transaction."""
    gate = coordinator().CampusRequestCoordinator(path, max_concurrent=1, requests_per_minute=100)
    connection = gate._connection
    @contextmanager
    def observe(timeout=30):
        with connection(timeout=timeout) as db:
            yield db
        if not polled.is_set():
            polled.set()
            if not resume.wait(10):
                raise RuntimeError('test did not resume waiter')
    gate._connection = observe
    try:
        with gate.slot('same-account', timeout=10):
            result.put('admitted')
    except BaseException as error:
        result.put(type(error).__name__)


def test_new_process_cannot_overtake_registered_waiter(tmp_path):
    path = tmp_path / 'fifo.sqlite'
    gate = coordinator().CampusRequestCoordinator(path, max_concurrent=1, requests_per_minute=100)
    context = multiprocessing.get_context('spawn')
    polled, resume, result = context.Event(), context.Event(), context.Queue()
    process = context.Process(target=_paused_waiting_process, args=(path, polled, resume, result))
    try:
        with gate.slot('same-account', timeout=10):
            process.start()
            assert polled.wait(5)
            time.sleep(.65)  # The next RPM start is already due when capacity opens.
        newcomer = coordinator().CampusRequestCoordinator(path, max_concurrent=1, requests_per_minute=100)
        with newcomer.slot('other-account', timeout=1):
            pass  # An unrelated account must not queue behind this waiter.
        with pytest.raises(TimeoutError):
            with newcomer.slot('same-account', timeout=.15):
                pytest.fail('A new process overtook the already queued request')
    finally:
        resume.set()
        if process.pid is not None:
            process.join(5)
            if process.is_alive():
                process.terminate()
                process.join(5)
    assert process.exitcode == 0
    assert result.get(timeout=1) == 'admitted'

    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM waiters').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM leases').fetchone()[0] == 0


def test_dead_waiting_process_does_not_block_the_queue(tmp_path):
    path = tmp_path / 'dead-waiter.sqlite'
    gate = coordinator().CampusRequestCoordinator(path, max_concurrent=1, requests_per_minute=100)
    context = multiprocessing.get_context('spawn')
    polled, resume, result = context.Event(), context.Event(), context.Queue()
    process = context.Process(target=_paused_waiting_process, args=(path, polled, resume, result))
    try:
        with gate.slot('same-account', timeout=10):
            process.start()
            assert polled.wait(5)
            with sqlite3.connect(path) as db:
                assert db.execute('SELECT count(*) FROM waiters').fetchone()[0] == 1
            process.terminate()
            process.join(5)
        with gate.slot('same-account', timeout=2):
            pass
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT count(*) FROM waiters').fetchone()[0] == 0
    finally:
        # A terminated process can leave multiprocessing.Event's lock held.
        if process.pid is not None and process.is_alive():
            process.terminate()
            process.join(5)


def test_expired_waiter_is_removed_before_admission(tmp_path, monkeypatch):
    api, clock = fake_clock(monkeypatch)
    path = tmp_path / 'expired-waiter.sqlite'
    gate = api.CampusRequestCoordinator(path, max_concurrent=1, requests_per_minute=100)
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO waiters (id,account_id,pid,expires_at) VALUES (?,?,?,?)',
                   ('expired', 'same', os.getpid(), clock.now - 1))
    with gate.slot('same', timeout=.5):
        pass
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM waiters').fetchone()[0] == 0


def test_cancellation_while_queued_cleans_its_ticket(tmp_path, monkeypatch):
    api, clock = fake_clock(monkeypatch)
    path = tmp_path / 'cancelled-waiter.sqlite'
    gate = api.CampusRequestCoordinator(path, max_concurrent=1, requests_per_minute=100)
    def interrupt_sleep(value):
        raise KeyboardInterrupt()
    with gate.slot('same', timeout=10):
        monkeypatch.setattr(clock, 'sleep', interrupt_sleep)
        with pytest.raises(KeyboardInterrupt):
            with gate.slot('same', timeout=2):
                pytest.fail('A queued request cannot acquire an occupied slot')
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT count(*) FROM waiters').fetchone()[0] == 0
            assert db.execute('SELECT count(*) FROM leases').fetchone()[0] == 1


def test_legacy_database_upgrade_preserves_existing_pacing_and_active_lease(tmp_path, monkeypatch):
    api, clock = fake_clock(monkeypatch)
    path = tmp_path / 'legacy.sqlite'
    with sqlite3.connect(path) as db:
        db.executescript('CREATE TABLE accounts (id TEXT PRIMARY KEY, next_at REAL NOT NULL, blocked_until REAL NOT NULL); '
                         'CREATE TABLE leases (id TEXT PRIMARY KEY, account_id TEXT NOT NULL, pid INTEGER NOT NULL, expires_at REAL NOT NULL);')
        db.execute('INSERT INTO accounts VALUES (?,?,?)', ('same', clock.now + 2, clock.now + 1))
        db.execute('INSERT INTO leases VALUES (?,?,?,?)', ('legacy-active', 'same', os.getpid(), clock.now + 4))
        old_accounts = db.execute('SELECT * FROM accounts').fetchall()
        old_leases = db.execute('SELECT * FROM leases').fetchall()
    for _ in range(2):
        gate = api.CampusRequestCoordinator(path, max_concurrent=1, requests_per_minute=100)
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT * FROM accounts').fetchall() == old_accounts
            assert db.execute('SELECT * FROM leases').fetchall() == old_leases
    with pytest.raises(TimeoutError):
        with gate.slot('same', timeout=.5):
            pytest.fail('An active pre-upgrade lease still occupies capacity')
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM waiters').fetchone()[0] == 0
        assert db.execute('SELECT * FROM accounts').fetchall() == old_accounts
        assert db.execute('SELECT * FROM leases').fetchall() == old_leases
    clock.now += 4
    with gate.slot('same', timeout=1):
        pass


def test_database_lock_wait_cannot_start_request_after_deadline(tmp_path, monkeypatch):
    api, clock = fake_clock(monkeypatch)
    path = tmp_path / 'deadline-lock.sqlite'
    gate = api.CampusRequestCoordinator(path, max_concurrent=1, requests_per_minute=100)
    connection = gate._connection
    @contextmanager
    def delayed_connection(timeout=30):
        with connection(timeout=timeout) as db:
            clock.now += 1
            yield db
    monkeypatch.setattr(gate, '_connection', delayed_connection)
    with pytest.raises(TimeoutError):
        with gate.slot('same', timeout=.5):
            pytest.fail('Time spent acquiring the SQLite write lock exhausted this deadline')
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM waiters').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM leases').fetchone()[0] == 0


def test_maximum_capacity_still_allows_32_requests_and_keeps_rpm_bounded(tmp_path, monkeypatch):
    api, clock = fake_clock(monkeypatch)
    path = tmp_path / 'maximum-capacity.sqlite'
    gate = api.CampusRequestCoordinator(path, max_concurrent=32, requests_per_minute=100)
    starts = []
    with ExitStack() as slots:
        for _ in range(32):
            slots.enter_context(gate.slot('same', timeout=30))
            starts.append(clock.now)
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT count(*) FROM leases').fetchone()[0] == 32
        with pytest.raises(TimeoutError):
            with gate.slot('same', timeout=.2):
                pytest.fail('The 33rd request must remain queued while all slots are occupied')
    assert all(b - a >= .6 - .00001 for a, b in zip(starts, starts[1:]))
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM leases').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM waiters').fetchone()[0] == 0


def test_registered_follower_poll_cannot_hold_writer_ahead_of_ready_fifo_head(tmp_path, monkeypatch):
    from threading import Event, Thread, current_thread
    from types import SimpleNamespace
    path = tmp_path / 'head-write-contention.sqlite'
    api = coordinator()
    follower = api.CampusRequestCoordinator(path, max_concurrent=32, requests_per_minute=80)
    head = api.CampusRequestCoordinator(path, max_concurrent=32, requests_per_minute=80)
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO accounts VALUES (?,?,?)', ('same', time.time() - 1, 0))
        db.execute('INSERT INTO waiters (id,account_id,pid,expires_at) VALUES (?,?,?,?)',
                   ('older-head', 'same', os.getpid(), time.time() + 10))
    monkeypatch.setattr(api.uuid, 'uuid4', lambda: SimpleNamespace(
        hex='older-head' if current_thread().name == 'coordinator-head' else 'follower'))
    paused, resume, admitted = Event(), Event(), Event()
    observations, errors = [], []
    connection = follower._connection
    polls = 0

    class Cursor:
        def __init__(self, cursor, db):
            self.cursor, self.db = cursor, db

        def fetchone(self):
            nonlocal polls
            value = self.cursor.fetchone()
            self.cursor.close()  # End a SELECT read lock before the controlled pause.
            polls += 1
            if polls == 2:
                observations.append(self.db.in_transaction)
                paused.set()
                if not resume.wait(5):
                    raise RuntimeError('test did not resume registered follower')
            return value

    class Connection:
        def __init__(self, db):
            self.db = db

        def __getattr__(self, name):
            return getattr(self.db, name)

        def execute(self, sql, parameters=()):
            cursor = self.db.execute(sql, parameters)
            if sql.startswith('SELECT id') and 'FROM waiters WHERE account_id=' in sql:
                return Cursor(cursor, self.db)
            return cursor

    @contextmanager
    def observed_connection(timeout=30):
        with connection(timeout=timeout) as db:
            yield Connection(db)
    follower._connection = observed_connection

    def request(gate, entered=None):
        try:
            with gate.slot('same', timeout=3):
                if entered:
                    entered.set()
        except BaseException as error:
            errors.append(error)

    queued = Thread(target=request, args=(follower,), name='coordinator-follower')
    oldest = Thread(target=request, args=(head, admitted), name='coordinator-head')
    queued.start()
    try:
        assert paused.wait(2), 'The registered follower did not poll'
        oldest.start()
        assert admitted.wait(.4), 'A non-head poll kept the ready FIFO head from acquiring a free slot'
        assert observations == [False], 'A non-head poll must release all SQLite transaction locks'
    finally:
        resume.set()
        queued.join(5)
        if oldest.ident is not None:
            oldest.join(5)
    assert not queued.is_alive() and not oldest.is_alive()
    assert not errors
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM waiters').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM leases').fetchone()[0] == 0
