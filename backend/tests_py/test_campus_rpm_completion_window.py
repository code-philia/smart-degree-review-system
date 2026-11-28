"""A delayed transport must not reuse an RPM grant before its real window ends."""
from types import SimpleNamespace
import sqlite3
from urllib.error import HTTPError
import pytest
import paper_compiler.campus_requests as c


@pytest.fixture
def clock(monkeypatch):
    state=SimpleNamespace(now=0.0)
    monkeypatch.setattr(c.time,'time',lambda:state.now)
    monkeypatch.setattr(c.time,'monotonic',lambda:state.now)
    monkeypatch.setattr(c.time,'sleep',lambda value:setattr(state,'now',state.now+value))
    return state


def finished_request(gate,clock,*,error=None):
    with gate.slot('key',timeout=1):
        clock.now=.5
        if error:raise error


def test_admission_aged_out_does_not_expire_delayed_request(clock,tmp_path):
    gate=c.CampusRequestCoordinator(tmp_path/'quota.sqlite',requests_per_minute=1)
    finished_request(gate,clock);clock.now=60.01
    with pytest.raises(TimeoutError):
        with gate.slot('key',timeout=.1):pass
    clock.now=60.51
    with gate.slot('key',timeout=.1):pass


def test_completion_history_survives_restart_without_resetting_the_window(clock,tmp_path):
    path=tmp_path/'quota.sqlite';gate=c.CampusRequestCoordinator(path,requests_per_minute=1)
    finished_request(gate,clock);clock.now=60.01
    again=c.CampusRequestCoordinator(path,requests_per_minute=1)
    with pytest.raises(TimeoutError):
        with again.slot('key',timeout=.1):pass
    clock.now=60.51
    with again.slot('key',timeout=.1):pass


def test_known_unsent_preflight_does_not_create_a_request_window(clock,tmp_path):
    gate=c.CampusRequestCoordinator(tmp_path/'quota.sqlite',requests_per_minute=1)
    error=RuntimeError('no HTTP was sent');error.request_not_sent=True
    with pytest.raises(RuntimeError):finished_request(gate,clock,error=error)
    clock.now=60.01
    with gate.slot('key',timeout=.1):pass


def test_rejected_http_request_still_consumes_rpm(clock,tmp_path):
    gate=c.CampusRequestCoordinator(tmp_path/'quota.sqlite',requests_per_minute=1)
    error=HTTPError('https://models.sjtu.edu.cn/api/v1',429,'limited',{'Retry-After':'1'},None)
    with pytest.raises(HTTPError):finished_request(gate,clock,error=error)
    clock.now=60.01
    with pytest.raises(TimeoutError):
        with gate.slot('key',timeout=.1):pass


def test_one_keys_completed_request_does_not_block_another_key(clock,tmp_path):
    gate=c.CampusRequestCoordinator(tmp_path/'quota.sqlite',requests_per_minute=1)
    finished_request(gate,clock);clock.now=60.01
    with gate.slot('other-key',timeout=.1):pass
    with pytest.raises(TimeoutError):
        with gate.slot('key',timeout=.1):pass


def test_expired_unknown_transport_keeps_one_safety_window(clock,tmp_path):
    gate=c.CampusRequestCoordinator(tmp_path/'quota.sqlite',requests_per_minute=1)
    with gate._connection() as db:
        db.execute('INSERT INTO leases VALUES (?,?,?,?)',('lost','key',123,-1))
    with pytest.raises(TimeoutError):
        with gate.slot('key',timeout=.1):pass


def test_old_database_has_one_migration_window_but_fresh_database_does_not(clock,tmp_path):
    path=tmp_path/'old.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE accounts (id TEXT PRIMARY KEY,next_at REAL NOT NULL,blocked_until REAL NOT NULL)')
        db.execute("INSERT INTO accounts VALUES ('key',0,0)")
    old=c.CampusRequestCoordinator(path)
    with pytest.raises(TimeoutError):
        with old.slot('key',timeout=.1):pass
    fresh=c.CampusRequestCoordinator(tmp_path/'fresh.sqlite')
    with fresh.slot('key',timeout=.1):pass
    clock.now=61
    again=c.CampusRequestCoordinator(path)
    with again.slot('key',timeout=.1):pass
