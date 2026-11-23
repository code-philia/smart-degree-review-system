"""Integration guards retain native source identities and complete claim scope."""
import copy
import json
import pytest

import numeric_consistency as n
from test_numeric_contribution_scope import case
from test_numeric_statistical_evidence import average_row, maximum_row, table
from test_numeric_metric_evidence import block, model, section, MAPPING


def test_maximum_guard_checks_both_grounded_child_method_chapters():
    structure, context, source = case()
    expanded = n.expand_contribution_scope(structure, context, source)
    source['tables'] = [table('t1', [('A', '2.0%')], sid='e4'),
                        table('t2', [('A', '17.61%')], sid='e5')]
    row = maximum_row('17.61')
    row['evidence'][0]['block_id'] = 't2'
    n.conservative_evidence_guard([row], model=source, mappings=expanded['mappings'])
    assert row['status'] == 'consistent'
    row = maximum_row('2.0')
    n.conservative_evidence_guard([row], model=source, mappings=expanded['mappings'])
    assert row['status'] == 'inconclusive'


def test_sampled_table_rows_keep_original_indices_and_truncation_flags():
    item = table('t1', [(str(i), str(i) + '%') for i in range(60)])
    item.update(bbox=[0, 0, 500, 500], source_node_ids=['source'])
    item['native_spanning_cells'] = [{'role': 'body', 'text': 'Late group',
        'row_indices': [56, 57], 'column_indices': [0], 'grounding': 'native_ruling_boundaries'}]
    d = maximum_row('56')['declaration']
    source = model(); source['tables'] = [item]
    candidates, _ = n.retrieve_candidates([d], [MAPPING], source)
    task = json.loads(n.verifier_prompt({'declarations': [d], 'mappings': [MAPPING]}, candidates).split('\n输入：\n')[1])['tasks'][0]
    view = next(c['table'] for c in task['candidates'] if c['block_type'] == 'StructuredTable')
    assert view['original_row_indices'] == [0, 1, 2, 57]
    assert view['original_row_count'] == 61 and view['rows_truncated'] is True
    assert view['matrix'][3] == item['matrix'][57]
    assert view['native_spanning_cells'][0]['row_indices'] == [56, 57]
    assert view['cells_truncated'] is False


def test_internal_group_metadata_is_never_copied_into_public_source_quotes():
    item = table('t1', [('A', '3.93%')])
    item['native_spanning_cells'] = [{'role': 'body', 'text': 'Dataset-A',
        'row_indices': [1], 'column_indices': [0], 'grounding': 'native_ruling_boundaries'}]
    quote = n._table_quote(item)
    assert all(key not in quote for key in ('source_row_group', 'row_indices', 'column_indices'))
    assert '3.93%' in quote


def test_complete_source_reading_supersedes_only_covered_weak_alternative():
    item = table('t1', [('A', '3.9321%'), ('B', '2.0%')])
    item.update(source_node_ids=['source'], bbox=[0, 0, 500, 500], same_source_alternatives=['weak'])
    weak = copy.deepcopy(item)
    weak.update(table_id='weak', reliability='limited', limitations=['unconfirmed_text_table_relationships'])
    source = model(); source['tables'] = [item, weak]
    row = maximum_row()
    n.conservative_evidence_guard([row], model=source, mappings=[MAPPING])
    assert row['status'] == 'consistent'
    weak['matrix'].append(['C', '9.5%']); weak['row_count'] += 1
    row = maximum_row()
    n.conservative_evidence_guard([row], model=source, mappings=[MAPPING])
    assert row['status'] == 'inconclusive'


def test_partial_native_character_overlap_does_not_suppress_extra_measurement():
    from numeric_native_tables import preferred_table_alternatives
    item = table('t1', [('A', '3.9321%')])
    item.update(source_node_ids=['source'], bbox=[0, 0, 500, 500], same_source_alternatives=['weak'],
                rows=[{'cells': [{'native_spans': [{'block_index': 0, 'line_index': 0,
                    'span_index': 0, 'char_start': 0, 'char_end': 5}]}]}])
    weak = copy.deepcopy(item)
    weak.update(table_id='weak', reliability='limited', limitations=['unconfirmed_text_table_relationships'])
    weak['rows'][0]['cells'][0]['native_spans'][0]['char_end'] = 6
    assert preferred_table_alternatives([item, weak]) == [item, weak]
    weak['rows'][0]['cells'][0]['native_spans'][0]['char_end'] = 4
    assert preferred_table_alternatives([item, weak]) == [item]


def test_named_condition_without_digits_is_not_silently_treated_as_global():
    source = model(); item = table('t1', [('A', '3.9321%'), ('B', '2.0%')])
    item['caption'] = 'Table 1 Results under bright light'; source['tables'] = [item]
    row = maximum_row(); row['declaration']['condition'] = 'low light'
    n.conservative_evidence_guard([row], model=source, mappings=[MAPPING])
    assert row['status'] == 'inconclusive'


def test_named_other_method_definition_cannot_establish_target_average():
    source = model(block('other-definition', 'other-metrics', 'OtherModel 的平均SSE定义为样本SSE的均值。'))
    source['sections']['other-metrics'] = section('other-metrics', 'chapter', '5.4 OtherModel 评价指标')
    row = average_row(metric='平均SSE')
    row['declaration'].update(text='ProposedModel 平均SSE为5.3934。', method='ProposedModel')
    row['evidence'][0]['quote'] = 'ProposedModel SSE 5.3934'
    n.conservative_evidence_guard([row], model=source, mappings=[MAPPING])
    assert row['status'] == 'inconclusive'


@pytest.mark.parametrize('name', ['BERT', 'ResNet-50', 'Model_2'])
def test_other_named_method_title_is_scope_even_without_optional_metadata(name):
    source = model(block('other-definition', 'other-metrics', f'{name}: average SSE is defined as mean SSE.'))
    source['sections']['other-metrics'] = section('other-metrics', 'chapter', f'5.4 {name} evaluation metrics')
    row = average_row(metric='平均SSE')
    row['declaration'].update(text='ProposedModel 平均SSE为5.3934。', method='ProposedModel')
    row['evidence'][0]['quote'] = 'ProposedModel SSE 5.3934'
    n.conservative_evidence_guard([row], model=source, mappings=[MAPPING])
    assert row['status'] == 'inconclusive'


def test_source_grounded_dataset_name_is_not_misclassified_as_another_method():
    source = model(block('definition', 'metrics', 'Average SSE is defined as mean SSE for all samples.'))
    source['sections']['metrics']['title'] = '5.2 CIFAR-10 数据集评价指标'
    row = average_row(metric='平均SSE')
    row['declaration'].update(text='ProposedModel平均SSE为5.3934。', method='ProposedModel', dataset='CIFAR-10')
    row['evidence'][0]['quote'] = 'ProposedModel SSE 5.3934'
    n.conservative_evidence_guard([row], model=source, mappings=[MAPPING])
    assert row['status'] == 'consistent'


def test_digit_prefixed_target_method_is_not_split_into_a_different_name():
    source = model(block('definition', 'metrics', 'Average SSE is defined as mean SSE for all samples.'))
    source['sections']['metrics']['title'] = '5.2 3D-UniReaction 评价指标'
    row = average_row(metric='平均SSE')
    row['declaration'].update(text='3D-UniReaction平均SSE为5.3934。', method='3D-UniReaction')
    row['evidence'][0]['quote'] = '3D-UniReaction SSE 5.3934'
    n.conservative_evidence_guard([row], model=source, mappings=[MAPPING])
    assert row['status'] == 'consistent'


def test_statistics_of_neighboring_target_do_not_veto_current_target():
    for context in ('模型平均误差为3.57米且准确率为90%。', '模型最高误差为3.57米；准确率为90%。'):
        row = average_row(metric='准确率')
        row['declaration'].update(text=context, number='90', unit='%', condition='', comparison='absolute')
        row['evidence'][0]['quote'] = '模型 Accuracy 90%'
        n.conservative_evidence_guard([row], model=model(), mappings=[MAPPING])
        assert row['status'] == 'consistent'


def test_native_table_reference_recovers_a_float_past_a_subsection_heading():
    source = model(block('reference', 'experiment', '完整对比结果如表5.4所示。'))
    source['sections']['comparison'] = section('comparison', 'chapter', '5.4 方案对比')
    target = table('float', [('A', '3.9321%'), ('B', '2.0%')], sid='comparison')
    target.update(caption='表5.4 数据集对比', bbox=[0, 0, 500, 500], source_node_ids=['native-table'])
    unrelated = copy.deepcopy(target)
    unrelated.update(table_id='unrelated', section_id='other-chapter')
    source['tables'] = [target, unrelated]
    structure = {'declarations': [maximum_row()['declaration']], 'mappings': [MAPPING]}
    expanded = n.expand_referenced_table_scope(structure, source)
    references = expanded['mappings'][0]['table_reference_scope']
    assert [ref['table_id'] for ref in references] == ['float']
    assert references[0]['quote'] == '表5.4'
    candidates, _ = n.retrieve_candidates(expanded['declarations'], expanded['mappings'], source)
    assert [c['block_id'] for c in candidates if c['block_type'] == 'StructuredTable'] == ['float']
    row = maximum_row(); row['evidence'][0]['block_id'] = 'float'
    n.conservative_evidence_guard([row], model=source, mappings=expanded['mappings'])
    assert row['status'] == 'consistent'
