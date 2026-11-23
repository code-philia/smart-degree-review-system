"""A matching table never licenses dismissing source-explicit prose conflicts."""
import copy

import numeric_consistency as n
from test_numeric_metric_evidence import block, model
from test_numeric_statistical_evidence import maximum_row


def case():
    d = {'id': 'd1', 'number': '2.50', 'metric': 'MAE', 'method': 'ProposedModel',
         'dataset': 'DataA', 'unit': 'kcal/mol', 'comparison': 'absolute',
         'condition': 'rough coordinates', 'text': 'DataA上MAE为2.50 kcal/mol。'}
    source = model(block('prose', 'experiment', 'DataA中ProposedModel的MAE为3.56 kcal/mol。'))
    table = {'candidate_id': 'd1:t1', 'declaration_id': 'd1', 'block_type': 'StructuredTable',
             'section_id': 'experiment', 'page': 21, 'text': 'ProposedModel | MAE | 2.50',
             'source_node_id': 'table-node', 'block_id': 'table', 'provenance': [], 'is_primary': True}
    prose = {**source['blocks'][0], 'candidate_id': 'd1:e1', 'declaration_id': 'd1', 'is_primary': True}
    row = {'declaration_id': 'd1', 'declaration': d, 'status': 'consistent',
           'reason': '表格一致', 'suggestion': '', 'evidence': [{'candidate_id': 'd1:t1'}]}
    return d, source, [table, prose], row


def test_same_method_and_metric_competing_value_triggers_source_audit():
    d, source, candidates, row = case()
    assert n.conflict_audit_declarations([row], candidates, source) == [d]


def test_another_metric_or_named_dataset_does_not_trigger_target_conflict():
    for text in ('DataA中ProposedModel的RMSE为3.56 kcal/mol。',
                 'DataB中OtherModel的MAE为3.56 kcal/mol。'):
        d, source, candidates, row = case()
        candidates[1]['text'] = text
        assert n.conflict_audit_declarations([row], candidates, source) == []


def test_existing_warning_and_single_prose_support_are_not_rejudged():
    d, source, candidates, row = case()
    row['status'] = 'inconclusive'
    assert n.conflict_audit_declarations([row], candidates, source) == []
    row['status'] = 'consistent'; row['evidence'] = [{'candidate_id': 'd1:e1'}]
    assert n.conflict_audit_declarations([row], candidates, source) == []


def test_conflict_audit_requires_multiple_source_evidence_for_a_downgrade():
    d, source, candidates, row = case()
    structure = {'declarations': [d], 'mappings': []}
    def request(prompt):
        assert 'source_contradiction_audit' in prompt
        assert '表格一致' not in prompt  # do not anchor the auditor on the first verdict
        return {'results': [{'declaration_id': 'd1', 'status': 'inconclusive',
            'reason': '同一条件下表格MAE2.50与正文MAE3.56冲突，需核对。', 'suggestion': '',
            'evidence': [{'candidate_id': 'd1:t1'}, {'candidate_id': 'd1:e1'}]}]}
    rows = [row]
    diagnostics = n.audit_source_conflicts(rows, structure, candidates, source, request)
    assert not diagnostics
    assert row['status'] == 'inconclusive'
    assert len(row['evidence']) == 2
    assert row['source_conflict_audit']['previous_status'] == 'consistent'


def test_auditor_cannot_invent_a_source_or_silently_erase_a_supported_result():
    d, source, candidates, row = case(); before = copy.deepcopy(row)
    def request(prompt):
        return {'results': [{'declaration_id': 'd1', 'status': 'inconclusive', 'reason': '冲突',
            'suggestion': '', 'evidence': [{'candidate_id': 'invented'}]}]}
    errors = n.audit_source_conflicts([row], {'declarations': [d], 'mappings': []}, candidates, source, request)
    assert errors and row['status'] == 'execution_error'
    assert row['source_conflict_audit']['previous_status'] == before['status']


def test_native_soft_wrap_and_later_metric_mentions_do_not_hide_conflicts():
    for text in ('DataA ProposedModel MAE\n3.56 kcal/mol.',
                 'DataA ProposedModel MAE is 2.50 kcal/mol; ProposedModel MAE is 3.56 kcal/mol.'):
        d, source, candidates, row = case(); candidates[1]['text'] = text
        assert n.conflict_audit_declarations([row], candidates, source) == [d]


def test_two_definitions_cannot_replace_the_conflicting_measurement_sources():
    d, source, candidates, row = case()
    for index in (1, 2):
        candidates.append({**candidates[1], 'candidate_id': f'd1:m{index}',
            'block_type': 'MetricDefinition', 'evidence_role': 'metric_definition'})
    def request(prompt):
        return {'results': [{'declaration_id': 'd1', 'status': 'inconclusive', 'reason': '冲突',
            'suggestion': '', 'evidence': [{'candidate_id': 'd1:m1'}, {'candidate_id': 'd1:m2'}]}]}
    errors = n.audit_source_conflicts([row], {'declarations': [d], 'mappings': []}, candidates, source, request)
    assert errors and row['status'] == 'execution_error'


def test_native_parent_dataset_heading_is_kept_for_a_nested_result_paragraph():
    d, source, candidates, row = case()
    source['sections']['experiment']['parent_id'] = 'dataset-section'
    source['sections']['dataset-section'] = {'section_id': 'dataset-section',
        'parent_id': 'chapter', 'title': 'DataA evaluation'}
    candidates[1]['text'] = 'ProposedModel MAE 3.56 kcal/mol.'
    assert n.conflict_audit_declarations([row], candidates, source) == [d]
