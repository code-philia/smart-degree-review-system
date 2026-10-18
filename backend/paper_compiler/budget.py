"""Cross-process accounting reserves worst-case charges before sending requests."""
from contextlib import contextmanager
from decimal import Decimal, ROUND_CEILING
import json
import math
import os
import sqlite3
import time
from pathlib import Path


class BudgetExceeded(RuntimeError):
    pass


def micros(value):
    value = Decimal(str(value))
    if not value.is_finite() or value < 0:
        raise ValueError('cost/limit must be finite and nonnegative')
    return int((value * 1_000_000).to_integral_value(rounding=ROUND_CEILING))


def money(value):
    return f'{Decimal(value) / Decimal(1_000_000):.6f}'


class BudgetLedger:
    def __init__(self, path: Path, limit_cny: Decimal):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        limit = micros(limit_cny)
        if limit <= 0:
            raise ValueError('limit must be positive')
        with self._connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS phases (name TEXT PRIMARY KEY, limit_micro INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS requests (
                  id TEXT PRIMARY KEY, phase TEXT NOT NULL, reserved_micro INTEGER NOT NULL,
                  charged_micro INTEGER, status TEXT NOT NULL, created_at REAL NOT NULL,
                  updated_at REAL NOT NULL, usage_json TEXT, reason TEXT);
                CREATE TABLE IF NOT EXISTS request_scopes (
                  request_id TEXT PRIMARY KEY, scope_id TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS request_scopes_by_scope ON request_scopes(scope_id);
                CREATE TABLE IF NOT EXISTS scopes (
                  id TEXT PRIMARY KEY, limit_micro INTEGER NOT NULL,
                  timeout_seconds REAL NOT NULL, created_at REAL NOT NULL, deadline_at REAL NOT NULL);
            """)
            conn.execute('BEGIN IMMEDIATE')
            previous = conn.execute("SELECT value FROM settings WHERE key='limit_micro'").fetchone()
            if previous and int(previous[0]) != limit:
                raise ValueError('existing budget limit cannot be changed by a new client')
            conn.execute("INSERT OR IGNORE INTO settings VALUES ('limit_micro', ?)", (str(limit),))
            conn.commit()
        os.chmod(self.path, 0o600)

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            conn.execute('PRAGMA busy_timeout=30000')
            yield conn
        finally:
            conn.close()

    def ensure_scope(self, scope_id, max_cost_cny, timeout_seconds):
        """Create an additional task cap once; resuming never resets cost or deadline."""
        if not isinstance(scope_id, str) or not scope_id.strip() or len(scope_id) > 200:
            raise ValueError('scope id must be a nonempty string of at most 200 characters')
        limit = micros(max_cost_cny)
        if isinstance(timeout_seconds, bool):
            raise ValueError('scope timeout must be positive and finite')
        timeout = float(timeout_seconds)
        if limit <= 0 or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('scope cost and timeout must be positive and finite')
        with self._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            old = conn.execute('SELECT limit_micro,timeout_seconds FROM scopes WHERE id=?', (scope_id,)).fetchone()
            if old and (old[0] != limit or old[1] != timeout):
                raise ValueError('existing scope limit or timeout cannot be changed')
            if not old:
                now = time.time()
                conn.execute('INSERT INTO scopes VALUES (?,?,?,?,?)',
                             (scope_id, limit, timeout, now, now + timeout))
            conn.commit()
        return self.scope_summary(scope_id)

    def scope_summary(self, scope_id):
        with self._connection() as conn:
            scope = conn.execute('SELECT limit_micro,timeout_seconds,created_at,deadline_at FROM scopes WHERE id=?',
                                 (scope_id,)).fetchone()
            if not scope:
                raise ValueError('unknown scope')
            rows = conn.execute("""SELECT r.reserved_micro,r.charged_micro,r.status FROM requests r
                JOIN request_scopes s ON r.id=s.request_id WHERE s.scope_id=?""", (scope_id,)).fetchall()
        committed = sum(r[1] if r[1] is not None else r[0] for r in rows)
        return {'scope_id': scope_id, 'limit_cny': money(scope[0]),
                'spent_cny': money(sum(r[1] or 0 for r in rows)), 'committed_cny': money(committed),
                'remaining_cny': money(max(0, scope[0] - committed)), 'requests': len(rows),
                'uncertain_requests': sum(r[2] == 'uncertain' for r in rows),
                'inflight_requests': sum(r[2] == 'reserved' for r in rows),
                'timeout_seconds': scope[1], 'created_at': scope[2], 'deadline_at': scope[3],
                'remaining_seconds': max(0, scope[3] - time.time()),
                'cost_accounting': 'same_cumulative_ledger'}

    def reserve(self, request_id, max_cost_cny, phase, phase_limit_cny, *, scope_id=None):
        reserve, phase_limit = micros(max_cost_cny), micros(phase_limit_cny)
        if not request_id or not phase or reserve <= 0 or phase_limit <= 0:
            raise ValueError('request, phase and positive reservation/limit required')
        with self._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if conn.execute("SELECT 1 FROM settings WHERE key='blocked'").fetchone():
                raise BudgetExceeded('accounting anomaly: further paid calls blocked')
            if conn.execute('SELECT 1 FROM requests WHERE id=?', (request_id,)).fetchone():
                raise ValueError('duplicate request reservation')
            old_phase = conn.execute('SELECT limit_micro FROM phases WHERE name=?', (phase,)).fetchone()
            if old_phase and old_phase[0] != phase_limit:
                raise ValueError('existing phase limit cannot be changed')
            now = time.time()
            if scope_id is not None:
                scope = conn.execute('SELECT limit_micro,deadline_at FROM scopes WHERE id=?', (scope_id,)).fetchone()
                if not scope:
                    raise ValueError('scope must be registered before reservation')
                if now >= scope[1]:
                    raise BudgetExceeded('scope deadline exhausted')
                used_scope = conn.execute("""SELECT COALESCE(SUM(COALESCE(r.charged_micro,r.reserved_micro)),0)
                    FROM requests r JOIN request_scopes s ON r.id=s.request_id WHERE s.scope_id=?""",
                    (scope_id,)).fetchone()[0]
                if used_scope + reserve > scope[0]:
                    raise BudgetExceeded('authorized scope budget exhausted')
            total = conn.execute('SELECT COALESCE(SUM(COALESCE(charged_micro, reserved_micro)),0) FROM requests').fetchone()[0]
            used_phase = conn.execute('SELECT COALESCE(SUM(COALESCE(charged_micro,reserved_micro)),0) FROM requests WHERE phase=?', (phase,)).fetchone()[0]
            limit = int(conn.execute("SELECT value FROM settings WHERE key='limit_micro'").fetchone()[0])
            if total + reserve > limit or used_phase + reserve > phase_limit:
                raise BudgetExceeded('authorized cumulative or phase budget exhausted')
            conn.execute('INSERT OR IGNORE INTO phases VALUES (?,?)', (phase, phase_limit))
            conn.execute('INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?)',
                         (request_id, phase, reserve, None, 'reserved', now, now, None, None))
            if scope_id is not None:
                conn.execute('INSERT INTO request_scopes VALUES (?,?)', (request_id, scope_id))
            conn.commit()
        return request_id

    def settle(self, request_id, usage, charged_cny):
        charged = micros(charged_cny)
        exceeded = False
        with self._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT reserved_micro,status FROM requests WHERE id=?', (request_id,)).fetchone()
            if not row or row[1] == 'settled':
                raise ValueError('missing or already settled request')
            conn.execute('UPDATE requests SET charged_micro=?, status=?,usage_json=?,updated_at=? WHERE id=?',
                         (charged, 'settled', json.dumps(usage, sort_keys=True), time.time(), request_id))
            if charged > row[0]:
                exceeded = True
                conn.execute("INSERT OR REPLACE INTO settings VALUES ('blocked','charge exceeded reserved bound')")
            conn.commit()
        if exceeded:
            raise BudgetExceeded('observed charge exceeded reserved bound; all further calls blocked')

    def mark_uncertain(self, request_id, reason):
        # Do not release a reservation on a timeout: the provider may have completed it.
        if reason not in {'timeout', 'transport', 'missing_usage', 'invalid_usage'}:
            reason = 'transport'
        with self._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT status FROM requests WHERE id=?', (request_id,)).fetchone()
            if not row or row[0] == 'settled':
                raise ValueError('missing or settled reservation')
            conn.execute("UPDATE requests SET status='uncertain',reason=?,updated_at=? WHERE id=?", (reason, time.time(), request_id))
            conn.commit()

    def summary(self):
        with self._connection() as conn:
            rows = conn.execute('SELECT phase,reserved_micro,charged_micro,status,usage_json FROM requests').fetchall()
            limit = int(conn.execute("SELECT value FROM settings WHERE key='limit_micro'").fetchone()[0])
            blocked = bool(conn.execute("SELECT 1 FROM settings WHERE key='blocked'").fetchone())
        committed = sum(r[2] if r[2] is not None else r[1] for r in rows)
        prompt = completion = 0
        for row in rows:
            usage = json.loads(row[4]) if row[4] else {}
            prompt += usage.get('prompt_tokens', 0)
            completion += usage.get('completion_tokens', 0)
        return {'limit_cny': money(limit), 'spent_cny': money(sum(r[2] or 0 for r in rows)),
                'committed_cny': money(committed), 'remaining_cny': money(max(0, limit-committed)),
                'requests': len(rows), 'uncertain_requests': sum(r[3]=='uncertain' for r in rows),
                'inflight_requests': sum(r[3]=='reserved' for r in rows), 'blocked': blocked,
                'prompt_tokens': prompt, 'completion_tokens': completion,
                'accounting': 'conservative_daytime_rates_without_cache_or_coupon_discounts'}
