"""Representative counterexamples and lossless pooling for repair prompts.

This module never reads a benchmark, oracle file, detector, or evidence gateway.
Its input is the feedback already admitted by the caller's split policy.
"""
from collections import Counter
from copy import deepcopy
import hashlib

from .storage import json_bytes

VERSION = 'representative-repair-feedback/1.0'


def _features(row):
    features = {('failure', str(value)) for value in row.get('failure_types', [])}
    for key in ('expected', 'before', 'after'):
        if key in row:
            features.add((key, str(row[key])))
    node = row.get('mutant', {}).get('node', {})
    if isinstance(node, dict) and node.get('kind'):
        features.add(('kind', node['kind']))
    for key in ('actual_original', 'actual_mutant'):
        for diagnostic in row.get(key, []):
            if diagnostic.get('status') in {'VIOLATION', 'UNKNOWN', 'ERROR'}:
                features.add(('diagnostic', diagnostic.get('check_id'), diagnostic.get('status')))
    return features


def _select(rows, limit, attempt):
    if len(rows) <= limit:
        return list(range(len(rows)))
    offset = attempt % len(rows)
    candidates = list(range(offset, len(rows))) + list(range(offset))
    # The latest real compile failure must remain visible before semantic cases.
    selected = [i for i in range(len(rows)-1, -1, -1)
                if 'compile_or_contract' in rows[i].get('failure_types', [])][:1]
    uncovered, parents = set(), Counter()
    for index in selected:
        uncovered.update(_features(rows[index]))
        parents[rows[index].get('parent_group')] += 1
    while len(selected) < min(limit, len(rows)):
        remaining = [i for i in candidates if i not in selected]
        chosen = max(remaining, key=lambda i: (
            len(_features(rows[i]) - uncovered),
            -parents[rows[i].get('parent_group')]))
        selected.append(chosen)
        uncovered.update(_features(rows[chosen]))
        parents[rows[chosen].get('parent_group')] += 1
    return selected


def prepare_feedback(feedback, *, attempt=0, limit=12):
    """Return a bounded diverse example list, full counts, and exact provenance.

    Repeated coordinates/ancestor records are stored once and referenced. Source
    text, attributes, facts, diagnostics, and label evidence are not abbreviated.
    Rotation changes examples within repeated failure classes across attempts.
    """
    if type(limit) is not int or limit < 1:
        raise ValueError('feedback example limit must be a positive integer')
    if type(attempt) is not int or attempt < 0:
        raise ValueError('repair attempt must be a nonnegative integer')
    rows = list(feedback)
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError('feedback examples must be dictionaries')
    selected = _select(rows, limit, attempt)
    pool = {}

    def project(value):
        if isinstance(value, list):
            return [project(item) for item in value]
        if not isinstance(value, dict):
            return deepcopy(value)
        result = {}
        for key, item in value.items():
            if key in {'provenance', 'ancestor_provenance'} and isinstance(item, list) and item:
                identifier = 'provenance-' + hashlib.sha256(json_bytes(item)).hexdigest()
                pool.setdefault(identifier, deepcopy(item))
                result[key] = {'$provenance_ref': identifier}
            else:
                result[key] = project(item)
        return result

    return {'feedback': [project(rows[i]) for i in selected],
            'feedback_provenance_pool': pool,
            'feedback_summary': {
                'policy': VERSION, 'attempt': attempt, 'total_failures': len(rows),
                'selected_examples': len(selected), 'omitted_examples': len(rows) - len(selected),
                'selected_ids': [rows[i]['id'] for i in selected if 'id' in rows[i]],
                'failure_types': dict(sorted(Counter(t for row in rows for t in row.get('failure_types', [])).items())),
                'expected_statuses': dict(sorted(Counter(str(row['expected']) for row in rows if 'expected' in row).items()))}}


def restore_feedback(packet):
    """Expand the exact selected input examples, for audit and roundtrip tests."""
    pool = packet['feedback_provenance_pool']

    def expand(value):
        if isinstance(value, list):
            return [expand(item) for item in value]
        if not isinstance(value, dict):
            return deepcopy(value)
        result = {}
        for key, item in value.items():
            if key in {'provenance', 'ancestor_provenance'} and isinstance(item, dict) and set(item) == {'$provenance_ref'}:
                result[key] = deepcopy(pool[item['$provenance_ref']])
            else:
                result[key] = expand(item)
        return result

    return [expand(row) for row in packet['feedback']]
