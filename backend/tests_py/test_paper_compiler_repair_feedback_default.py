
from copy import deepcopy
from paper_compiler.repair_feedback import prepare_feedback, restore_feedback

def population():
    rows = []
    for i in range(78):
        negative = i < 60
        rows.append({
            'id': 'example-' + str(i), 'parent_group': 'mother-' + str(i % 6),
            'expected': 'VIOLATION' if negative else 'PASS',
            'before': 'UNKNOWN', 'after': 'UNKNOWN' if negative else 'VIOLATION',
            'failure_types': ['false_negative' if negative else 'false_positive_mutant',
                              'insufficient_or_execution'],
            'original': {'node': {'id': 'node-' + str(i), 'kind': 'Paragraph',
                                  'text': 'Original complete text ' + str(i),
                                  'provenance': [{'page': i, 'range': [0, 99]}]}},
            'mutant': {'node': {'id': 'node-' + str(i), 'kind': 'Paragraph',
                                'text': 'Mutant complete text ' + str(i),
                                'provenance': [{'page': i, 'range': [0, 99]}]}},
            'analysis_original': {'facts': [{'state': 'observed', 'value': 'z' * 10000,
                                            'reason': 'Full original fact', 'source_range': [5, 15]}]},
            'analysis_mutant': {'facts': [{'state': 'unknown', 'reason': 'Full mutant reason'}]},
            'actual_original': [{'check_id': 'original-check', 'status': 'UNKNOWN'}],
            'actual_mutant': [{'check_id': 'missing-check' if negative else 'unexpected-check',
                               'status': 'UNKNOWN' if negative else 'VIOLATION'}],
            'label_evidence': {'source_quote': 'Full normative evidence ' + str(i)}
        })
    return rows

def test_default_four_full_examples_still_summarize_all_78():
    rows = population()
    saved = deepcopy(rows)
    packet = prepare_feedback(rows)
    summary = packet['feedback_summary']
    assert len(packet['feedback']) == 4
    assert summary['total_failures'] == 78
    assert summary['selected_examples'] == 4
    assert summary['omitted_examples'] == 74
    assert summary['failure_types'] == {
        'false_negative': 60, 'false_positive_mutant': 18, 'insufficient_or_execution': 78}
    assert summary['expected_statuses'] == {'PASS': 18, 'VIOLATION': 60}
    assert summary['before_statuses'] == {'UNKNOWN': 78}
    assert summary['after_statuses'] == {'UNKNOWN': 60, 'VIOLATION': 18}
    assert summary['diagnostic_counts'] == {
        'actual_original': [{'check_id': 'original-check', 'status': 'UNKNOWN', 'count': 78}],
        'actual_mutant': [{'check_id': 'missing-check', 'status': 'UNKNOWN', 'count': 60},
                          {'check_id': 'unexpected-check', 'status': 'VIOLATION', 'count': 18}]}
    source = {row['id']: row for row in saved}
    assert restore_feedback(packet) == [source[row['id']] for row in packet['feedback']]
    assert rows == saved
    assert packet['feedback_provenance_pool']

def test_explicit_twelve_remains_available_without_losing_facts():
    rows = population()
    packet = prepare_feedback(rows, limit=12)
    assert len(packet['feedback']) == 12
    assert packet['feedback_summary']['omitted_examples'] == 66
    assert packet['feedback_summary']['total_failures'] == 78
    source = {row['id']: row for row in rows}
    assert restore_feedback(packet) == [source[row['id']] for row in packet['feedback']]

def test_default_four_reserves_first_slot_for_latest_compile_error():
    rows = population()
    rows.insert(0, {'failure_types': ['compile_or_contract'], 'reason': 'older error'})
    latest = {'failure_types': ['compile_or_contract'], 'reason': 'current error',
              'failed_candidate': {'code': 'actual rejected candidate'}}
    rows.append(latest)
    packet = prepare_feedback(rows, attempt=3)
    assert len(packet['feedback']) == 4
    assert packet['feedback'][0] == latest
    assert packet['feedback_summary']['total_failures'] == 80
    assert packet['feedback_summary']['failure_types']['compile_or_contract'] == 2

def test_default_four_rotates_examples_while_preserving_failure_diversity():
    rows = population()
    first = prepare_feedback(rows, attempt=0)
    later = prepare_feedback(rows, attempt=1)
    assert len(first['feedback']) == len(later['feedback']) == 4
    assert first == prepare_feedback(rows, attempt=0)
    assert first['feedback_summary']['selected_ids'] != later['feedback_summary']['selected_ids']
    for packet in (first, later):
        assert {row['expected'] for row in packet['feedback']} == {'PASS', 'VIOLATION'}
        assert len({row['parent_group'] for row in packet['feedback']}) == 4
