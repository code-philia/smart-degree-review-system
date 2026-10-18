from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import pytest

from paper_compiler.budget import BudgetLedger, BudgetExceeded


def test_atomic_reservations_cannot_overcommit_across_clients(tmp_path):
    path = tmp_path / 'budget.db'
    BudgetLedger(path, Decimal('0.5'))
    def attempt(i):
        ledger = BudgetLedger(path, Decimal('0.5'))
        try:
            ledger.reserve(str(i), Decimal('0.1'), 'pilot', Decimal('0.5'))
            return True
        except BudgetExceeded:
            return False
    with ThreadPoolExecutor(max_workers=10) as pool:
        assert sum(pool.map(attempt, range(20))) == 5
    assert BudgetLedger(path, Decimal('0.5')).summary()['committed_cny'] == '0.500000'


def test_phase_cap_and_total_cap_survive_restarts(tmp_path):
    path = tmp_path / 'budget.db'
    ledger = BudgetLedger(path, Decimal('10'))
    ledger.reserve('first', Decimal('5'), 'pilot', Decimal('5'))
    ledger.settle('first', {'prompt_tokens': 100}, Decimal('4'))
    restarted = BudgetLedger(path, Decimal('10'))
    with pytest.raises(BudgetExceeded):
        restarted.reserve('more-pilot', Decimal('2'), 'pilot', Decimal('5'))
    restarted.reserve('batch', Decimal('6'), 'batch', Decimal('10'))
    with pytest.raises(BudgetExceeded):
        restarted.reserve('too-much', Decimal('.01'), 'batch', Decimal('10'))
    with pytest.raises(ValueError, match='limit'):
        BudgetLedger(path, Decimal('1000'))


def test_timeout_reservation_is_retained_and_cannot_be_double_settled(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.db', Decimal('1'))
    ledger.reserve('lost-response', Decimal('.8'), 'pilot', Decimal('1'))
    ledger.mark_uncertain('lost-response', 'timeout')
    assert ledger.summary()['committed_cny'] == '0.800000'
    with pytest.raises(BudgetExceeded):
        ledger.reserve('retry', Decimal('.3'), 'pilot', Decimal('1'))
    ledger.settle('lost-response', {'prompt_tokens': 10}, Decimal('.2'))
    with pytest.raises(ValueError):
        ledger.settle('lost-response', {}, Decimal('0'))
    assert ledger.summary()['spent_cny'] == '0.200000'


def test_invalid_or_duplicate_reservations_cannot_change_ledger(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.db', Decimal('1'))
    for value in ['-1', 'NaN', 'Infinity']:
        with pytest.raises(ValueError):
            ledger.reserve('bad', Decimal(value), 'pilot', Decimal('1'))
    ledger.reserve('same', Decimal('.2'), 'pilot', Decimal('1'))
    with pytest.raises(ValueError):
        ledger.reserve('same', Decimal('.2'), 'pilot', Decimal('1'))
    assert ledger.summary()['requests'] == 1


def test_charge_above_reservation_is_recorded_and_blocks_new_calls(tmp_path):
    ledger = BudgetLedger(tmp_path / 'budget.db', Decimal('1'))
    ledger.reserve('unexpected', Decimal('.1'), 'pilot', Decimal('1'))
    with pytest.raises(BudgetExceeded):
        ledger.settle('unexpected', {}, Decimal('.2'))
    assert ledger.summary()['spent_cny'] == '0.200000'
    with pytest.raises(BudgetExceeded):
        ledger.reserve('next', Decimal('.1'), 'pilot', Decimal('1'))
