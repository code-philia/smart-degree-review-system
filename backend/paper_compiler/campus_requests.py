"""Share separate campus TPM-budget and paced RPM-dispatch queues across workers."""
from contextlib import contextmanager
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
from urllib.parse import urlsplit
import uuid

_RESERVATION_HEARTBEAT_SECONDS = 5.0


def _setting(name, default, maximum):
    try:
        value = int(os.environ.get(name, str(default)))
        return value if 1 <= value <= maximum else default
    except (TypeError, ValueError):
        return default


def campus_requests_per_minute():
    """Versioned per-host default, independent of retired site allocations.

    Legacy SJTU_API_REQUESTS_PER_MINUTE values (such as20/80) must not keep
    upgraded deployments on the old allocation. Operators can deliberately
    select a different1..100 limit through the explicitly named override.
    """
    return _setting('SJTU_API_REQUESTS_PER_MINUTE_OVERRIDE', 100, 100)


def estimate_request_tokens(payload):
    """Match the text reservation used by the school's LiteLLM 1.87 gateway.

    The gateway admits estimated input characters / 4 plus the declared output
    ceiling, rather than waiting for actual usage to reach the TPM limit.
    """
    total_chars = 0
    messages = payload.get('messages')
    if messages:
        for message in messages:
            content = message.get('content')
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                total_chars += sum(len(part.get('text') or '') for part in content)
    elif payload.get('prompt'):
        prompt = payload['prompt']
        total_chars = sum(len(str(item)) for item in prompt) if isinstance(prompt, list) else len(prompt)
    elif payload.get('input'):
        value = payload['input']
        total_chars = sum(len(str(item)) for item in value) if isinstance(value, list) else len(value)
    estimated_input = max(1, total_chars // 4) if total_chars else 0
    for name in ('max_tokens', 'max_completion_tokens'):
        value = payload.get(name)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError('invalid campus output token budget')
    output = payload.get('max_tokens') or payload.get('max_completion_tokens')
    if output is None:
        output = 0 if payload.get('input') or not total_chars else max(estimated_input, 1024)
    return max(1, estimated_input + output)


def _actual_tokens(response):
    """Validate actual usage independently of answer parsing and quota reservation."""
    try:
        if isinstance(response, (str, bytes, bytearray)):
            response = json.loads(response)
        usage = response['usage']
        before, after = usage['prompt_tokens'], usage['completion_tokens']
        if any(type(value) is not int or value < 0 for value in (before, after)):
            return None
        total = before + after
        if total > 2**63 - 1:
            return None
        if 'total_tokens' in usage and (type(usage['total_tokens']) is not int or usage['total_tokens'] != total):
            return None
        return total
    except (TypeError, KeyError, ValueError, UnicodeError):
        return None


class CampusRequestCoordinator:
    def __init__(self, path, *, max_concurrent=16, requests_per_minute=100, tokens_per_minute=300000):
        if not 1 <= max_concurrent <= 32 or not 1 <= requests_per_minute <= 100:
            raise ValueError('invalid campus request concurrency or rate')
        if type(tokens_per_minute) is not int or not 1 <= tokens_per_minute <= 300000:
            raise ValueError('invalid campus token budget')
        self.path = Path(path)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.max_concurrent = max_concurrent
        self.interval = 60.0 / requests_per_minute
        self.tokens_per_minute = tokens_per_minute
        with self._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            legacy = 'accounts' in tables and 'quota_meta' not in tables
            schema = '''
                CREATE TABLE IF NOT EXISTS quota_meta (id TEXT PRIMARY KEY, ready_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY, next_at REAL NOT NULL, blocked_until REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS leases (
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL, pid INTEGER NOT NULL,
                    expires_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS leases_by_account ON leases(account_id);
                CREATE TABLE IF NOT EXISTS waiters (
                    ticket INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE,
                    account_id TEXT NOT NULL, pid INTEGER NOT NULL, expires_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS waiters_by_account ON waiters(account_id,ticket);
                CREATE TABLE IF NOT EXISTS token_waiters (
                    ticket INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE,
                    account_id TEXT NOT NULL, pid INTEGER NOT NULL, expires_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS token_waiters_by_account ON token_waiters(account_id,ticket);
                CREATE TABLE IF NOT EXISTS token_reservations (
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL, tokens INTEGER NOT NULL,
                    pid INTEGER NOT NULL, state INTEGER NOT NULL, expires_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS tokens_by_account ON token_reservations(account_id);
            '''
            for statement in schema.split(';'):
                if statement.strip():
                    db.execute(statement)
            # Existing usage is unknown at migration. After the old service's
            # control group is stopped, allow a full quiet provider window.
            db.execute('INSERT OR IGNORE INTO quota_meta VALUES (?,?)',
                       ('tpm', time.time() + 60 if legacy else 0))
            added = db.execute('INSERT OR IGNORE INTO quota_meta VALUES (?,?)',
                               ('tpm-deferred-refund-v1', 0)).rowcount
            if added and 'token_reservations' in tables:
                # Old settled rows may have already discarded output reservations.
                # After restart, cover those unknown balances for one full window.
                db.execute("UPDATE quota_meta SET ready_at=max(ready_at,?) WHERE id='tpm'", (time.time() + 60,))
            db.commit()
        os.chmod(self.path, 0o600)

    @contextmanager
    def _connection(self, timeout=30):
        # Initialization and lease cleanup must tolerate brief concurrent writes.
        db = sqlite3.connect(self.path, timeout=timeout, isolation_level=None)
        try:
            yield db
        finally:
            db.close()

    def _reap(self, db, now):
        # 0 = waiting for dispatch, 1 = admitted/in flight, 2 = settled or
        # uncertain. An expired transport lease is uncertain for one more minute.
        db.execute('UPDATE token_reservations SET state=2,expires_at=? WHERE state=1 AND expires_at<=?',
                   (now + 60, now))
        db.execute('DELETE FROM token_reservations WHERE state=2 AND expires_at<=?', (now,))
        db.execute('DELETE FROM token_reservations WHERE state=0 AND expires_at<=?', (now,))
        db.execute('DELETE FROM leases WHERE expires_at<=?', (now,))
        db.execute('DELETE FROM waiters WHERE expires_at<=?', (now,))
        db.execute('DELETE FROM token_waiters WHERE expires_at<=?', (now,))
        # Many queued threads share one process; inspect each PID only once.
        pids = db.execute('SELECT pid FROM leases UNION SELECT pid FROM waiters '
                          'UNION SELECT pid FROM token_waiters '
                          'UNION SELECT pid FROM token_reservations WHERE state<>2').fetchall()
        for (pid,) in pids:
            if not self._process_alive(pid):
                db.execute('DELETE FROM leases WHERE pid=?', (pid,))
                db.execute('DELETE FROM waiters WHERE pid=?', (pid,))
                db.execute('DELETE FROM token_waiters WHERE pid=?', (pid,))
                db.execute('DELETE FROM token_reservations WHERE pid=? AND state=0', (pid,))
                db.execute('UPDATE token_reservations SET state=2,expires_at=? WHERE pid=? AND state=1',
                           (now + 60, pid))

    @staticmethod
    def _process_alive(pid):
        if os.name != 'posix' or not Path('/proc').is_dir():
            return True
        try:
            state = Path('/proc', str(pid), 'stat').read_text().rsplit(') ', 1)[1].split()[0]
            return state != 'Z'
        except FileNotFoundError:
            return False
        except (OSError, IndexError):
            return True

    @contextmanager
    def _keep_reservation_alive(self, identity, lifetime):
        """Renew both leases while queued or receiving a long streamed response.

        Socket timeouts bound inactivity, not total response duration. A bounded
        heartbeat also recovers abandoned reservations without relying on PIDs.
        """
        stopped = threading.Event()
        def renew():
            while not stopped.wait(_RESERVATION_HEARTBEAT_SECONDS):
                try:
                    with self._connection(timeout=1) as db:
                        db.execute('BEGIN IMMEDIATE')
                        expiry = time.time() + lifetime
                        db.execute('UPDATE token_reservations SET expires_at=? WHERE id=? AND state<>2', (expiry, identity))
                        db.execute('UPDATE leases SET expires_at=? WHERE id=?', (expiry, identity))
                        db.commit()
                except sqlite3.OperationalError:
                    # A brief competing writer must not terminate renewal.
                    continue
        heartbeat = threading.Thread(target=renew, name='campus-budget-lease', daemon=True)
        heartbeat.start()
        try:
            yield
        finally:
            stopped.set()
            heartbeat.join(timeout=2)

    @contextmanager
    def token_slot(self, account, budget, *, timeout, wait_for_capacity=False, remaining_time=None):
        """FIFO budget admission, with no API lease or RPM ticket while waiting."""
        timeout = float(timeout)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('campus request timeout must be positive and finite')
        tokens = budget['estimated']
        if type(tokens) is not int or not 1 <= tokens <= self.tokens_per_minute:
            raise ValueError('request token budget exceeds the campus TPM limit')
        identity = uuid.uuid4().hex
        deadline = None if wait_for_capacity else time.monotonic() + timeout
        lifetime = max(30.0, timeout + 5)
        registered, renew_at = False, 0.0
        try:
            while True:
                if remaining_time is not None:
                    remaining_time()
                remaining = timeout if deadline is None else deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('campus API request timed out waiting for token budget')
                try:
                    with self._connection(timeout=min(1, remaining)) as db:
                        now = time.time()
                        if registered and deadline is None and now >= renew_at:
                            db.execute('UPDATE token_waiters SET expires_at=? WHERE id=?', (now + lifetime, identity))
                            renew_at = now + lifetime / 3
                        first = db.execute('SELECT id,pid,expires_at FROM token_waiters WHERE account_id=? ORDER BY ticket LIMIT 1',
                                           (account,)).fetchone() if registered else None
                        if not (first and first[0] != identity and first[2] > now and self._process_alive(first[1])):
                            db.execute('BEGIN IMMEDIATE')
                            now = time.time()
                            self._reap(db, now)
                            remaining = timeout if deadline is None else deadline - time.monotonic()
                            if remaining <= 0:
                                raise TimeoutError('campus API request timed out waiting for token budget')
                            db.execute('INSERT OR IGNORE INTO token_waiters (id,account_id,pid,expires_at) VALUES (?,?,?,?)',
                                       (identity, account, os.getpid(), now + (lifetime if deadline is None else remaining)))
                            if not registered:
                                renew_at = now + lifetime / 3
                            first = db.execute('SELECT id FROM token_waiters WHERE account_id=? ORDER BY ticket LIMIT 1', (account,)).fetchone()[0]
                            used = db.execute('SELECT coalesce(sum(tokens),0) FROM token_reservations WHERE account_id=?', (account,)).fetchone()[0]
                            ready_at = db.execute('SELECT ready_at FROM quota_meta WHERE id=?', ('tpm',)).fetchone()[0]
                            if first == identity and used + tokens <= self.tokens_per_minute and ready_at <= now:
                                db.execute('DELETE FROM token_waiters WHERE id=?', (identity,))
                                db.execute('INSERT INTO token_reservations VALUES (?,?,?,?,0,?)',
                                           (identity, account, tokens, os.getpid(), now + lifetime))
                                db.commit()
                                break
                            db.commit()
                            registered = True
                except sqlite3.OperationalError as error:
                    if 'locked' not in str(error).lower():
                        raise
                remaining = timeout if deadline is None else max(0, deadline - time.monotonic())
                time.sleep(min(.25, remaining))
            with self._keep_reservation_alive(identity, lifetime):
                yield identity
        finally:
            with self._connection() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('DELETE FROM token_waiters WHERE id=?', (identity,))
                row = db.execute('SELECT state FROM token_reservations WHERE id=?', (identity,)).fetchone()
                if row:
                    actual = budget.get('actual')
                    if row[0] == 0 or budget.get('rejected') is True:
                        db.execute('DELETE FROM token_reservations WHERE id=?', (identity,))
                    else:
                        # Receiving a response does not acknowledge the gateway's
                        # asynchronous refund. Keep at least the full estimate for
                        # one completion window; actual usage may increase it.
                        if type(actual) is int and 0 <= actual <= 2**63 - 1:
                            db.execute('UPDATE token_reservations SET tokens=? WHERE id=?', (min(max(tokens, actual), self.tokens_per_minute), identity))
                        db.execute('UPDATE token_reservations SET state=2,expires_at=? WHERE id=?', (time.time() + 60, identity))
                db.commit()

    @contextmanager
    def slot(self, account, *, timeout, wait_for_capacity=False, remaining_time=None, token_reservation=None):
        timeout = float(timeout)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('campus request timeout must be positive and finite')
        deadline = None if wait_for_capacity else time.monotonic() + timeout
        ticket_lifetime = max(30.0, timeout)
        renew_at = 0.0
        identity = token_reservation or uuid.uuid4().hex
        registered = False
        try:
            while True:
                if remaining_time is not None:
                    remaining_time()
                remaining = timeout if deadline is None else deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('campus API request timed out waiting for a shared slot')
                wait = .05
                try:
                    with self._connection(timeout=min(1, remaining)) as db:
                        now = time.time()
                        if registered and deadline is None and now >= renew_at:
                            # Keep the same FIFO ticket alive during a long wait.
                            # Renew infrequently so followers do not starve the head.
                            db.execute('UPDATE waiters SET expires_at=? WHERE id=?',
                                       (now + ticket_lifetime, identity))
                            renew_at = now + ticket_lifetime / 3
                        read_only_wait = False
                        if registered:
                            # Followers only observe a live head. Repeated writer
                            # transactions here can starve the one eligible caller.
                            now = time.time()
                            first = db.execute('SELECT id,pid,expires_at FROM waiters WHERE account_id=? ORDER BY ticket LIMIT 1',
                                               (account,)).fetchone()
                            if (first and first[0] != identity and first[2] > now
                                    and self._process_alive(first[1])):
                                pacing = db.execute('SELECT next_at,blocked_until FROM accounts WHERE id=?',
                                                    (account,)).fetchone()
                                if pacing:
                                    count = db.execute('SELECT count(*) FROM leases WHERE account_id=? AND expires_at>?',
                                                       (account, now)).fetchone()[0]
                                    if count < self.max_concurrent:
                                        wait = max(.05, max(pacing) - now)
                                    read_only_wait = True
                        if not read_only_wait:
                            db.execute('BEGIN IMMEDIATE')
                            remaining = timeout if deadline is None else deadline - time.monotonic()
                            if remaining <= 0:
                                raise TimeoutError('campus API request timed out waiting for a shared slot')
                            now = time.time()
                            self._reap(db, now)
                            db.execute('INSERT OR IGNORE INTO accounts VALUES (?,0,0)', (account,))
                            # Persist registration while waiting. Later chunks or workers
                            # cannot repeatedly steal capacity from an older request.
                            db.execute('INSERT OR IGNORE INTO waiters (id,account_id,pid,expires_at) VALUES (?,?,?,?)',
                                       (identity, account, os.getpid(), now + (ticket_lifetime if deadline is None else remaining)))
                            if deadline is None and not registered:
                                renew_at = now + ticket_lifetime / 3
                            first = db.execute('SELECT id FROM waiters WHERE account_id=? ORDER BY ticket LIMIT 1',
                                               (account,)).fetchone()[0]
                            next_at, blocked_until = db.execute('SELECT next_at,blocked_until FROM accounts WHERE id=?', (account,)).fetchone()
                            count = db.execute('SELECT count(*) FROM leases WHERE account_id=?', (account,)).fetchone()[0]
                            ready_at = max(next_at, blocked_until)
                            if first == identity and count < self.max_concurrent and ready_at <= now:
                                db.execute('DELETE FROM waiters WHERE id=?', (identity,))
                                lease_lifetime = max(30.0, remaining + 5) if token_reservation else remaining + 5
                                db.execute('INSERT INTO leases VALUES (?,?,?,?)', (identity, account, os.getpid(), now + lease_lifetime))
                                db.execute('UPDATE accounts SET next_at=? WHERE id=?', (now + self.interval, account))
                                db.commit()
                                break
                            if count < self.max_concurrent:
                                wait = max(.001 if first == identity else .05, ready_at - now)
                            db.commit()
                            registered = True
                except sqlite3.OperationalError as error:
                    if 'locked' not in str(error).lower():
                        raise
                remaining = timeout if deadline is None else max(0, deadline - time.monotonic())
                time.sleep(min(wait, .25, remaining))
            try:
                available = timeout if deadline is None else max(.001, deadline - time.monotonic())
                if remaining_time is not None:
                    available = min(available, remaining_time())
                if token_reservation:
                    with self._connection() as db:
                        changed = db.execute('UPDATE token_reservations SET state=1,expires_at=? WHERE id=? AND account_id=? AND state=0',
                                             (time.time() + max(30.0, available + 5), identity, account)).rowcount
                        if changed != 1:
                            raise RuntimeError('campus token reservation was lost before dispatch')
                yield available
            except Exception as error:
                if getattr(error, 'code', getattr(error, 'status', None)) == 429:
                    retry = getattr(error, 'retry_after', None)
                    if retry is None and getattr(error, 'headers', None):
                        retry = error.headers.get('Retry-After')
                    try:
                        retry = float(retry)
                        retry = min(60.0, max(1.0, retry)) if math.isfinite(retry) else 2.0
                    except (TypeError, ValueError):
                        retry = 2.0
                    with self._connection() as db:
                        db.execute('UPDATE accounts SET blocked_until=max(blocked_until,?) WHERE id=?', (time.time() + retry, account))
                raise
        finally:
            # Also release a queued ticket on timeout, exception or cancellation.
            with self._connection() as db:
                db.execute('DELETE FROM waiters WHERE id=?', (identity,))
                db.execute('DELETE FROM leases WHERE id=?', (identity,))


@lru_cache(maxsize=8)
def _coordinator(path, concurrency, rpm, tpm=300000):
    return CampusRequestCoordinator(path, max_concurrent=concurrency, requests_per_minute=rpm, tokens_per_minute=tpm)


@contextmanager
def campus_request_slot(url, headers, timeout, *, wait_for_capacity=False, remaining_time=None, token_budget=None):
    target = urlsplit(url)
    if target.scheme != 'https' or target.hostname != 'models.sjtu.edu.cn':
        yield timeout
        return
    configured = os.environ.get('SJTU_API_COORDINATOR_DB')
    root = Path(os.environ.get('PAPER_COMPILER_CACHE_ROOT') or Path(tempfile.gettempdir()) / 'smart-degree-sjtu')
    path = str(Path(configured) if configured else root / 'campus-requests.sqlite3')
    # No token or document text is stored in the coordination database.
    authorization = headers.get('Authorization', headers.get('authorization', ''))
    account = hashlib.sha256((target.netloc + '\0' + authorization).encode()).hexdigest()
    gate = _coordinator(path, _setting('SJTU_API_MAX_CONCURRENCY', 16, 32),
                        campus_requests_per_minute(), _setting('SJTU_API_TOKENS_PER_MINUTE', 300000, 300000))
    if token_budget is not None:
        with gate.token_slot(account, token_budget, timeout=timeout, wait_for_capacity=wait_for_capacity,
                             remaining_time=remaining_time) as identity:
            with gate.slot(account, timeout=timeout, wait_for_capacity=wait_for_capacity,
                           remaining_time=remaining_time, token_reservation=identity) as remaining:
                yield remaining
        return
    with gate.slot(account, timeout=timeout, wait_for_capacity=wait_for_capacity,
                   remaining_time=remaining_time) as remaining:
        yield remaining


def campus_request(url, headers, timeout, send, *, remaining_time=None, payload=None):
    """Queue campus limits and retry 429s; timeout bounds each real transport."""
    target = urlsplit(url)
    if target.scheme != 'https' or target.hostname != 'models.sjtu.edu.cn':
        return send(timeout)
    while True:
        budget = {'estimated': estimate_request_tokens(payload)} if payload is not None else None
        try:
            with campus_request_slot(url, headers, timeout, wait_for_capacity=True,
                                     remaining_time=remaining_time, token_budget=budget) as available:
                try:
                    response = send(available)
                except Exception as error:
                    if budget is not None and (getattr(error, 'code', getattr(error, 'status', None)) == 429
                                               or getattr(error, 'request_not_sent', False) is True):
                        budget['rejected'] = True  # Known rejection/preflight; inference never ran.
                    raise
                if budget is not None:
                    budget['actual'] = _actual_tokens(response)
                return response
        except Exception as error:
            if getattr(error, 'code', getattr(error, 'status', None)) != 429:
                raise
            # slot() records the shared Retry-After cooldown before releasing.
            # The next attempt queues there; a 429 never becomes a rule verdict.
