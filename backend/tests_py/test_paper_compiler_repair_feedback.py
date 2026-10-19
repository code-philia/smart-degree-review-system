import copy
import json

from paper_compiler.repair_feedback import prepare_feedback, restore_feedback


def failure(index, *, expected='VIOLATION', before='PASS', after='PASS', kind='Paragraph', types=None):
    return {'id': str(index), 'expected': expected, 'before': before, 'after': after,
            'failure_types': types or ['false_negative'], 'parent_group': 'parent-' + str(index % 3),
            'original': {'node': {'id': 'source', 'kind': kind, 'text': 'Original source'}},
            'mutant': {'node': {'id': 'source', 'kind': kind, 'text': 'Changed source'}},
            'actual_mutant': [{'status': after, 'check_id': 'generic-check'}]}


def test_balanced_feedback_reaches_late_false_positives_and_kinds():
    rows = [failure(i) for i in range(30)]
    rows += [failure(30, expected='PASS', before='VIOLATION', after='VIOLATION',
                     kind='BibliographyEntry', types=['false_positive_original', 'false_positive_mutant'])]
    rows += [failure(31, before='UNKNOWN', after='UNKNOWN', kind='ReferenceUse',
                     types=['false_negative', 'insufficient_or_execution'])]
    packet = prepare_feedback(rows, limit=4)
    selected = packet['feedback']
    assert len(selected) == 4
    assert {'30', '31'} <= {row['id'] for row in selected}
    assert packet['feedback_summary']['total_failures'] == 32
    assert packet['feedback_summary']['omitted_examples'] == 28
    assert packet['feedback_summary']['failure_types']['false_positive_mutant'] == 1


def test_compile_error_kept_first_and_rotation_is_deterministic():
    rows = [failure(i) for i in range(20)]
    rows.append({'failure_types': ['compile_or_contract'], 'reason': 'Invalid capability',
                 'failed_candidate': {'code': 'actual rejected code'}})
    first = prepare_feedback(rows, attempt=1, limit=3)
    second = prepare_feedback(rows, attempt=2, limit=3)
    assert first['feedback'][0]['failed_candidate']['code'] == 'actual rejected code'
    assert second['feedback'][0]['failed_candidate']['code'] == 'actual rejected code'
    assert first == prepare_feedback(rows, attempt=1, limit=3)
    assert [r.get('id') for r in first['feedback']] != [r.get('id') for r in second['feedback']]


def test_provenance_is_losslessly_pooled_without_mutating_labels_or_text():
    provenance = [{'bbox': [1, 2, 3, 4], 'source_id': 'pdf', 'page_index': 4,
                   'ancestor_provenance': [{'kind': 'source', 'text_offsets': [1, 10]}],
                   'padding': 'coordinate record ' * 200}]
    rows = [failure(1), failure(2)]
    for row in rows:
        row['original']['node']['provenance'] = copy.deepcopy(provenance)
        row['mutant']['node']['provenance'] = copy.deepcopy(provenance)
        row['label_evidence'] = {'label': {'valid': True, 'quotes': ['Exact normative text']}}
        for diagnostic in row['actual_mutant']:
            diagnostic['provenance'] = copy.deepcopy(provenance)
    original = copy.deepcopy(rows)
    packet = prepare_feedback(rows, limit=2)
    assert restore_feedback(packet) == original
    assert rows == original
    assert len(packet['feedback_provenance_pool']) == 1
    assert len(json.dumps(packet)) < len(json.dumps(rows)) // 2
    assert packet['feedback'][0]['label_evidence'] == original[0]['label_evidence']


def test_empty_feedback_does_not_invent_failures():
    packet = prepare_feedback([])
    assert packet['feedback'] == []
    assert packet['feedback_summary']['total_failures'] == 0
    assert restore_feedback(packet) == []


def test_selected_examples_never_include_unprovided_validation_or_test_data():
    rows = [failure(i) for i in range(4)]
    packet = prepare_feedback(rows, limit=2)
    assert set(packet['feedback_summary']['selected_ids']) <= {'0', '1', '2', '3'}
    assert all('validation' not in k and 'test' not in k for k in packet)


def test_latest_compile_failure_precedes_older_rejected_candidates():
    rows = [failure(i) for i in range(18)]
    rows.insert(2, {'failure_types': ['compile_or_contract'], 'reason': 'old error',
                    'failed_candidate': {'code': 'obsolete candidate'}})
    rows.append({'failure_types': ['compile_or_contract'], 'reason': 'latest error',
                 'failed_candidate': {'code': 'current rejected candidate'}})
    packet = prepare_feedback(rows, attempt=3, limit=12)
    assert packet['feedback'][0]['reason'] == 'latest error'
    assert packet['feedback'][0]['failed_candidate']['code'] == 'current rejected candidate'
    assert packet['feedback_summary']['total_failures'] == 20
