"""Response receipt must not make asynchronously refunded TPM budget reusable."""
import os
import sqlite3

import pytest

from paper_compiler import campus_requests as api


class Clock:
    def __init__(self):self.now=1000.0
    def time(self):return self.now
    def monotonic(self):return self.now
    def sleep(self,seconds):self.now+=seconds


@pytest.fixture
def controlled(tmp_path,monkeypatch):
    clock=Clock();monkeypatch.setattr(api,'time',clock)
    return clock,tmp_path/'quota.sqlite'


def test_two_fresh_responses_do_not_recreate_the_observed_15230_token_gap(controlled):
    clock,path=controlled
    gate=api.CampusRequestCoordinator(path,tokens_per_minute=300000)
    with gate.token_slot('same',{'estimated':280705},timeout=300) as background:
        with gate.slot('same',timeout=300,token_reservation=background):
            for estimated,actual in [(8666,1012),(8668,1092)]:
                budget={'estimated':estimated}
                with gate.token_slot('same',budget,timeout=300) as identity:
                    with gate.slot('same',timeout=300,token_reservation=identity):budget['actual']=actual
            with pytest.raises(TimeoutError):
                with gate.token_slot('same',{'estimated':8663},timeout=.1):
                    pytest.fail('The gateway still has only 1961 tokens available')
            with sqlite3.connect(path) as db:
                assert db.execute('SELECT sum(tokens) FROM token_reservations').fetchone()[0]==298039
            clock.now+=61
            with gate.token_slot('same',{'estimated':8663},timeout=1):pass


def test_success_with_zero_usage_retains_the_reservation_for_the_full_window(controlled):
    clock,path=controlled;gate=api.CampusRequestCoordinator(path,tokens_per_minute=100)
    budget={'estimated':80}
    with gate.token_slot('same',budget,timeout=10) as identity:
        with gate.slot('same',timeout=10,token_reservation=identity):budget['actual']=0
    with pytest.raises(TimeoutError):
        with gate.token_slot('same',{'estimated':30},timeout=.1):pytest.fail('Success is not a confirmed refund')
    clock.now+=61
    with gate.token_slot('same',{'estimated':30},timeout=1):pass


def test_old_settled_balances_get_a_single_upgrade_hold(controlled):
    clock,path=controlled;api.CampusRequestCoordinator(path,tokens_per_minute=100)
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM quota_meta WHERE id='tpm-deferred-refund-v1'")
        db.execute('INSERT INTO token_reservations VALUES (?,?,?,?,2,?)',('old','same',5,os.getpid(),clock.now+60))
    gate=api.CampusRequestCoordinator(path,tokens_per_minute=100)
    with pytest.raises(TimeoutError):
        with gate.token_slot('same',{'estimated':30},timeout=.1):pytest.fail('Old balances may already be refunded too early')
    clock.now+=30
    gate=api.CampusRequestCoordinator(path,tokens_per_minute=100)
    clock.now+=31
    with gate.token_slot('same',{'estimated':30},timeout=1):pass
