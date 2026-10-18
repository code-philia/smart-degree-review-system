"""Additional task limits without replacing or resetting the cumulative ledger.

Wrap the client before PDF extraction or any semantic/audit/refinement calls. A
scope id identifies one task across processes and restarts. Use that same id and
limits to resume it. MaasClient clones keep the original cache and transport;
cache hits do not reserve money. Unmetered test doubles get a time guard only.
"""
from copy import copy
import math
import time

from .budget import BudgetExceeded, BudgetLedger, micros, money


class RequestDeadlineExceeded(BudgetExceeded):
    """No further model request may be started for this task."""


class _Scope:
    def __init__(self, scope_id, max_cost_cny, timeout_seconds, ledger):
        if not isinstance(scope_id, str) or not scope_id.strip() or len(scope_id) > 200:
            raise ValueError('scope id must be a nonempty string of at most 200 characters')
        self.limit_micro = micros(max_cost_cny)
        if isinstance(timeout_seconds, bool):
            raise ValueError('scope timeout must be positive and finite')
        self.timeout_seconds = float(timeout_seconds)
        if self.limit_micro <= 0 or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError('scope cost and timeout must be positive and finite')
        self.scope_id = scope_id
        self.ledger = ledger
        if ledger is not None:
            if not isinstance(ledger, BudgetLedger):
                raise TypeError('metered client must use the existing BudgetLedger')
            state = ledger.ensure_scope(scope_id, max_cost_cny, self.timeout_seconds)
            self.created_at, self.deadline_at = state['created_at'], state['deadline_at']
        else:
            self.created_at = time.time()
            self.deadline_at = self.created_at + self.timeout_seconds
        # Persist wall time for other processes; also prevent a wall-clock rollback
        # from extending the current process's allowance.
        self.monotonic_deadline = time.monotonic() + max(0, self.deadline_at - time.time())

    def remaining(self):
        value = min(self.deadline_at - time.time(), self.monotonic_deadline - time.monotonic())
        if value <= 0:
            raise RequestDeadlineExceeded('task scope deadline exhausted')
        return value

    def summary(self):
        if self.ledger is not None:
            result = self.ledger.scope_summary(self.scope_id)
        else:
            result = {'scope_id': self.scope_id, 'limit_cny': money(self.limit_micro),
                      'spent_cny': None, 'committed_cny': None, 'remaining_cny': None,
                      'created_at': self.created_at, 'deadline_at': self.deadline_at,
                      'timeout_seconds': self.timeout_seconds, 'cost_accounting': 'unavailable'}
        result['remaining_seconds'] = max(0, min(self.deadline_at - time.time(),
                                                self.monotonic_deadline - time.monotonic()))
        return result


class _ScopedLedger:
    """Route clone reservations to the same ledger transaction, adding its scope."""
    def __init__(self, ledger, scope):
        self._ledger, self._scope = ledger, scope

    def reserve(self, request_id, max_cost_cny, phase, phase_limit_cny, *, scope_id=None):
        if scope_id is not None and scope_id != self._scope.scope_id:
            raise ValueError('client reservation cannot change its scope')
        self._scope.remaining()
        return self._ledger.reserve(request_id, max_cost_cny, phase, phase_limit_cny,
                                    scope_id=self._scope.scope_id)

    def __getattr__(self, name):
        return getattr(self._ledger, name)


class _BoundedClient:
    def __init__(self, client, scope):
        self._scope = scope
        self.ledger = scope.ledger
        self._client = copy(client)
        if hasattr(client, 'config'):
            self._client.config = dict(client.config)
        if hasattr(client, 'max_attempts'):
            self._client.max_attempts = 1
        if scope.ledger is not None:
            self._client.ledger = _ScopedLedger(scope.ledger, scope)
        self._client._request_limits = scope

    def complete_json(self, task, instructions, data, max_tokens):
        self._scope.remaining()
        return self._client.complete_json(task, instructions, data, max_tokens)

    def scope_summary(self):
        return self._scope.summary()

    def __getattr__(self, name):
        return getattr(self._client, name)

    def __repr__(self):
        return '<BoundedClient>'


def bounded_client(client, scope_id, max_cost_cny='5', timeout_seconds=1200):
    """Clone with one attempt and a persistent additional cost/deadline cap.

    The original client remains unchanged. ``result.ledger`` is the original
    BudgetLedger; ``scope_summary()`` reports the additional task cap. A timeout
    is a BudgetExceeded subclass, so budget-stop handling also stops expired
    tasks. Wrap once at task entry and pass the result to every pipeline stage.
    Fake clients without a ledger are supported, with explicit unmetered status.
    """
    if not callable(getattr(client, 'complete_json', None)):
        raise TypeError('client must implement complete_json')
    if isinstance(client, _BoundedClient):
        scope = client._scope
        if (scope_id != scope.scope_id or micros(max_cost_cny) != scope.limit_micro
                or isinstance(timeout_seconds, bool) or float(timeout_seconds) != scope.timeout_seconds):
            raise ValueError('already bounded client cannot change scope limits')
        return client
    scope = _Scope(scope_id, max_cost_cny, timeout_seconds, getattr(client, 'ledger', None))
    return _BoundedClient(client, scope)
