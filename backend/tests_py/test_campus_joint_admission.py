"""Queued calls occupy neither quota until joint dispatch admission."""
import sqlite3
import os
import pytest
from paper_compiler import campus_requests as api
from test_campus_token_budget import controlled, payload, usage, counts

URL = 'https://models.sjtu.edu.cn/api/v1/chat/completions'


def test_rpm_wait_never_reserves_tokens(controlled, monkeypatch):
    clock, path = controlled
    api.campus_request(URL, {}, 1, lambda _: usage(), payload=payload())
    observed = []
    original_sleep = clock.sleep
    def inspect(seconds):
        with sqlite3.connect(path) as db:
            observed.append(db.execute('SELECT sum(tokens) FROM token_reservations').fetchone()[0])
        original_sleep(seconds)
    monkeypatch.setattr(clock, 'sleep', inspect)
    api.campus_request(URL, {}, 1, lambda _: usage(), payload=payload())
    assert observed and set(observed) == {10}


def test_both_unavailable_waits_for_rpm_first(controlled, monkeypatch):
    clock, path = controlled
    api.campus_request(URL, {}, 1, lambda _: usage(90, 0), payload=payload(89))
    def inspect(_):
        assert counts(path) == dict(waiters=1, leases=0, token_waiters=0, token_reservations=1)
        raise KeyboardInterrupt()
    monkeypatch.setattr(clock, 'sleep', inspect)
    with pytest.raises(KeyboardInterrupt):
        api.campus_request(URL, {}, 1, lambda _: pytest.fail('must wait'), payload=payload(79))
    assert counts(path) == dict(waiters=0, leases=0, token_waiters=0, token_reservations=1)


def test_tpm_wait_does_not_consume_rpm_and_rechecks_before_send(controlled, monkeypatch):
    clock, path = controlled
    gate = api.CampusRequestCoordinator(path, tokens_per_minute=100)
    with gate.slot('same', timeout=1):
        pass
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO token_reservations VALUES (?,?,?,?,2,?)', ('used', 'same', 90, 1, clock.now+2))
    clock.now += .6
    sleeps = []
    original_sleep = clock.sleep
    def inspect(seconds):
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT next_at FROM accounts WHERE id=?', ('same',)).fetchone()[0] == 1000.6
            assert db.execute('SELECT count(*) FROM leases').fetchone()[0] == 0
        sleeps.append(clock.now)
        original_sleep(seconds)
    monkeypatch.setattr(clock, 'sleep', inspect)
    with gate.slot('same', timeout=4, token_budget={'estimated':80, 'actual':0}):
        assert clock.now >= 1002
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT count(*) FROM token_reservations').fetchone()[0] == 1
            assert db.execute('SELECT next_at FROM accounts WHERE id=?', ('same',)).fetchone()[0] == pytest.approx(clock.now+.6)
    assert sleeps


def test_tpm_to_rpm_transfer_keeps_age_and_no_reservation(controlled, monkeypatch):
    clock, path = controlled
    gate = api.CampusRequestCoordinator(path, tokens_per_minute=100)
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO accounts VALUES (?,?,0)', ('same', 1001))
        db.execute('INSERT INTO token_waiters VALUES (?,?,?,?,?)', (1, 'older', 'same', os.getpid(), 1100))
    snapshots = []
    def inspect(seconds):
        with sqlite3.connect(path) as db:
            rows = db.execute('SELECT ticket,id FROM waiters UNION ALL SELECT ticket,id FROM token_waiters ORDER BY ticket').fetchall()
            own = next(row[0] for row in rows if row[1] != 'older')
            snapshots.append(own)
            assert db.execute('SELECT count(*) FROM token_reservations').fetchone()[0] == 0
            assert db.execute('SELECT next_at FROM accounts').fetchone()[0] in (1001, 1002)
            if clock.now >= 1001:
                # Our caller has reached TPM behind the older waiter. Make RPM
                # unavailable again; the next transfer must retain ticket 2.
                db.execute('UPDATE accounts SET next_at=1002')
                db.execute('DELETE FROM token_waiters WHERE id=?', ('older',))
        clock.now += seconds
    monkeypatch.setattr(clock, 'sleep', inspect)
    with gate.slot('same', timeout=4, token_budget={'estimated':80, 'actual':0}):
        assert clock.now >= 1002
    assert snapshots and set(snapshots) == {2}


def test_scope_cancelling_at_joint_admission_consumes_neither_quota(controlled):
    _, path = controlled
    gate = api.CampusRequestCoordinator(path, tokens_per_minute=100)
    checks = []
    def remaining():
        checks.append(1)
        if len(checks) == 2:
            raise TimeoutError('scope expired')
        return 1
    with pytest.raises(TimeoutError, match='scope expired'):
        with gate.slot('same', timeout=1, token_budget={'estimated':80}, remaining_time=remaining):
            pytest.fail('cancelled before dispatch')
    assert all(value == 0 for value in counts(path).values())
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT next_at FROM accounts').fetchone() is None


def test_legacy_token_waiter_uses_the_shared_ticket_sequence(controlled, monkeypatch):
    clock, path = controlled
    gate = api.CampusRequestCoordinator(path, tokens_per_minute=100)
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO waiters VALUES (?,?,?,?,?)', (1, 'joint', 'same', os.getpid(), 1100))
        db.execute('INSERT INTO token_reservations VALUES (?,?,?,?,2,?)', ('used', 'other', 90, os.getpid(), 1100))
    def inspect(_):
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT ticket FROM token_waiters').fetchone()[0] == 2
        raise KeyboardInterrupt()
    monkeypatch.setattr(clock, 'sleep', inspect)
    with pytest.raises(KeyboardInterrupt):
        with gate.token_slot('other', {'estimated':30}, timeout=1):
            pytest.fail('insufficient tokens')


def test_upgrade_normalizes_overlapping_live_queue_tickets(controlled):
    _, path = controlled
    api.CampusRequestCoordinator(path, tokens_per_minute=100)
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO waiters VALUES (?,?,?,?,?)', (1, 'joint', 'same', os.getpid(), 1100))
        db.execute('INSERT INTO token_waiters VALUES (?,?,?,?,?)', (1, 'legacy', 'other', os.getpid(), 1100))
    api.CampusRequestCoordinator(path, tokens_per_minute=100)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM (SELECT ticket FROM waiters UNION SELECT ticket FROM token_waiters)').fetchone()[0] == 2


def test_final_slow_callback_keeps_the_full_rpm_interval(controlled):
    clock, path = controlled
    gate = api.CampusRequestCoordinator(path, tokens_per_minute=100)
    def remaining():
        clock.now += 1
        return 10
    with gate.slot('same', timeout=10, token_budget={'estimated':80, 'actual':0}, remaining_time=remaining):
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT next_at FROM accounts').fetchone()[0] == pytest.approx(clock.now+.6)


def test_final_callback_cannot_exceed_local_deadline(controlled):
    clock, path = controlled
    gate = api.CampusRequestCoordinator(path, tokens_per_minute=100)
    checks = []
    def remaining():
        checks.append(1)
        if len(checks) == 2:
            clock.now += 2
        return 10
    with pytest.raises(TimeoutError):
        with gate.slot('same', timeout=1, token_budget={'estimated':80}, remaining_time=remaining):
            pytest.fail('local deadline expired')
    assert all(value == 0 for value in counts(path).values())
