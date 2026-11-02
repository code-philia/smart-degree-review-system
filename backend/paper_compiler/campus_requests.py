"""Share campus API request pacing and concurrent slots across worker processes."""
from contextlib import contextmanager
from functools import lru_cache
import hashlib
import math
import os
from pathlib import Path
import sqlite3
import tempfile
import time
from urllib.parse import urlsplit
import uuid


def _setting(name, default, maximum):
    try:
        value = int(os.environ.get(name, str(default)))
        return value if 1 <= value <= maximum else default
    except (TypeError, ValueError):
        return default


class CampusRequestCoordinator:
    def __init__(self, path, *, max_concurrent=16, requests_per_minute=90):
        if not 1 <= max_concurrent <= 32 or not 1 <= requests_per_minute <= 100:
            raise ValueError('invalid campus request concurrency or rate')
        self.path = Path(path)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.max_concurrent = max_concurrent
        self.interval = 60.0 / requests_per_minute
        with self._connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY, next_at REAL NOT NULL, blocked_until REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS leases (
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL, pid INTEGER NOT NULL,
                    expires_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS leases_by_account ON leases(account_id);
            ''')
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
        db.execute('DELETE FROM leases WHERE expires_at<=?', (now,))
        if os.name == 'posix' and Path('/proc').is_dir():
            for identity, pid in db.execute('SELECT id,pid FROM leases').fetchall():
                try:
                    state = Path('/proc', str(pid), 'stat').read_text().rsplit(') ', 1)[1].split()[0]
                    alive = state != 'Z'
                except FileNotFoundError:
                    alive = False
                except (OSError, IndexError):
                    alive = True
                if not alive:
                    db.execute('DELETE FROM leases WHERE id=?', (identity,))

    @contextmanager
    def slot(self, account, *, timeout):
        timeout = float(timeout)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('campus request timeout must be positive and finite')
        deadline = time.monotonic() + timeout
        identity = uuid.uuid4().hex
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('campus API request timed out waiting for a shared slot')
            wait = .05
            try:
                with self._connection(timeout=min(1, remaining)) as db:
                    db.execute('BEGIN IMMEDIATE')
                    now = time.time()
                    self._reap(db, now)
                    db.execute('INSERT OR IGNORE INTO accounts VALUES (?,0,0)', (account,))
                    next_at, blocked_until = db.execute('SELECT next_at,blocked_until FROM accounts WHERE id=?', (account,)).fetchone()
                    count = db.execute('SELECT count(*) FROM leases WHERE account_id=?', (account,)).fetchone()[0]
                    ready_at = max(next_at, blocked_until)
                    if count < self.max_concurrent and ready_at <= now:
                        db.execute('INSERT INTO leases VALUES (?,?,?,?)', (identity, account, os.getpid(), now + remaining + 5))
                        db.execute('UPDATE accounts SET next_at=? WHERE id=?', (now + self.interval, account))
                        db.commit()
                        break
                    wait = max(.001, ready_at - now) if count < self.max_concurrent else .05
                    db.rollback()
            except sqlite3.OperationalError as error:
                if 'locked' not in str(error).lower():
                    raise
            time.sleep(min(wait, .25, max(.001, remaining)))
        try:
            yield max(.001, deadline - time.monotonic())
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
            with self._connection() as db:
                db.execute('DELETE FROM leases WHERE id=?', (identity,))


@lru_cache(maxsize=8)
def _coordinator(path, concurrency, rpm):
    return CampusRequestCoordinator(path, max_concurrent=concurrency, requests_per_minute=rpm)


@contextmanager
def campus_request_slot(url, headers, timeout):
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
                        _setting('SJTU_API_REQUESTS_PER_MINUTE', 90, 100))
    with gate.slot(account, timeout=timeout) as remaining:
        yield remaining


def campus_request(url, headers, timeout, send):
    """Wait for campus capacity and retry 429s within one overall deadline."""
    target = urlsplit(url)
    if target.scheme != 'https' or target.hostname != 'models.sjtu.edu.cn':
        return send(timeout)
    deadline = time.monotonic() + float(timeout)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('campus API request timed out waiting for capacity')
        try:
            with campus_request_slot(url, headers, remaining) as available:
                return send(available)
        except Exception as error:
            if getattr(error, 'code', getattr(error, 'status', None)) != 429:
                raise
            # slot() records the shared Retry-After cooldown before releasing.
            # The next attempt queues there; a 429 never becomes a rule verdict.
