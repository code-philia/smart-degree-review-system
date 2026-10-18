"""Read-only, resumable resource intervals over one existing cumulative ledger.

Ledger deltas include concurrent activity and any activity between resumed
sessions. They are interval totals, never precise attribution to one rule/task.
Elapsed time sums measured active sessions, excluding offline waiting.
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
from time import monotonic as _monotonic

from .storage import write_json_atomic

SCHEMA = 'paper-resource-interval/1.0'
_SCOPE = 'shared_ledger_interval'
_SUMMARY_KEYS = {'limit_cny', 'spent_cny', 'committed_cny', 'remaining_cny',
                 'requests', 'uncertain_requests', 'inflight_requests', 'blocked',
                 'prompt_tokens', 'completion_tokens', 'accounting'}


def budget_snapshot(client):
    """Read public summary values only; missing/unavailable accounting is unknown."""
    ledger = getattr(client, 'ledger', None)
    summary = getattr(ledger, 'summary', None)
    if not callable(summary):
        return None
    try:
        value = summary()
    except Exception:
        return None
    if not isinstance(value, dict) or not {'spent_cny', 'committed_cny', 'requests'} <= value.keys():
        return None
    return deepcopy({key: value[key] for key in _SUMMARY_KEYS if key in value})


def _ledger_path(client):
    value = getattr(getattr(client, 'ledger', None), 'path', None)
    return str(Path(value).resolve()) if isinstance(value, (str, Path)) else None


def _cost_delta(before, after, key):
    if before is None or after is None:
        return None
    try:
        left, right = Decimal(str(before[key])), Decimal(str(after[key]))
        if not left.is_finite() or not right.is_finite():
            return None
        return format(right - left, '.6f')
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None


def _counter_delta(before, after, key):
    if before is None or after is None:
        return None
    left, right = before.get(key), after.get(key)
    return right - left if type(left) is int and type(right) is int else None


def resource_usage(before, after, elapsed_seconds):
    return {'available': before is not None and after is not None,
            'accounting_scope': _SCOPE, 'elapsed_seconds': elapsed_seconds,
            'budget_before': deepcopy(before), 'budget_after': deepcopy(after),
            'spent_cny_delta': _cost_delta(before, after, 'spent_cny'),
            'committed_cny_delta': _cost_delta(before, after, 'committed_cny'),
            'requests_delta': _counter_delta(before, after, 'requests'),
            'prompt_tokens_delta': _counter_delta(before, after, 'prompt_tokens'),
            'completion_tokens_delta': _counter_delta(before, after, 'completion_tokens')}


class ResourceInterval:
    """Persist first-before and accumulated active time, then resume that interval.

    ``checkpoint`` captures in-flight progress without completing an evaluation.
    ``close`` is idempotent. Consumers decide when a true round record may exist.
    A completed round is read directly by its caller, without constructing a new
    interval or rewriting historical values.
    """
    def __init__(self, client, path, *, initial_record=None):
        self.client, self.path = client, Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path = _ledger_path(client)
        if self.path.is_file():
            state = json.loads(self.path.read_text())
            if state.get('schema_version') != SCHEMA:
                raise ValueError('invalid resource interval checkpoint')
            if state.get('ledger_path') is not None and ledger_path is not None and state['ledger_path'] != ledger_path:
                raise ValueError('resource accounting cannot switch to a different ledger')
            before = state['resource_usage']['budget_before']
            elapsed = state['resource_usage']['elapsed_seconds']
            started_at = state['started_at']
            sessions = state.get('sessions', 0)
        else:
            initial_record = initial_record or {}
            before = initial_record.get('budget_before', budget_snapshot(client))
            # Legacy unavailable summaries contain no measured cost values.
            if isinstance(before, dict) and before.get('available') is False:
                before = None
            elapsed = initial_record.get('elapsed_seconds', 0.0)
            started_at = initial_record.get('started_at') or datetime.now(timezone.utc).isoformat()
            sessions = 0
        if not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError('invalid accumulated active resource time')
        self.state = {'schema_version': SCHEMA, 'started_at': started_at,
                      'ledger_path': ledger_path, 'sessions': sessions + 1}
        self.started_at, self.budget_before = started_at, deepcopy(before)
        self._elapsed_before, self._started = elapsed, _monotonic()
        self._closed = False
        self.resource_usage = None
        self.checkpoint()

    def checkpoint(self, status='active'):
        if self._closed:
            return deepcopy(self.resource_usage)
        elapsed = self._elapsed_before + max(0.0, _monotonic() - self._started)
        self.resource_usage = resource_usage(self.budget_before, budget_snapshot(self.client), elapsed)
        self.state.update(status=status, resource_usage=deepcopy(self.resource_usage))
        write_json_atomic(self.path, self.state)
        return deepcopy(self.resource_usage)

    def close(self, status='completed'):
        result = self.checkpoint(status)
        self._closed = True
        return result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close('interrupted' if exc_type is not None else 'completed')
        return False
