"""Native metric definitions are context, never numeric verdicts."""
from decimal import Decimal
import copy
import importlib

import pytest


def helper():
    # Keep the initial red run an assertion about the missing behavior.
    spec = importlib.util.find_spec('numeric_metric_evidence')
    assert spec is not None, 'native metric evidence/arithmetic helper is missing'
    return importlib.import_module('numeric_metric_evidence')


def section(sid, parent, title):
    return {'section_id': sid, 'parent_id': parent, 'title': title, 'block_ids': []}


def block(bid, sid, text, page=20, kind='Paragraph', **fields):
    return {'block_id': bid, 'source_node_id': bid + '-node', 'section_id': sid,
            'page': page, 'block_type': kind, 'table_id': None, 'text': text,
            'provenance': [{'line_id': bid + '-line', 'page_index': page - 1,
                            'node_text_start': 7, 'node_text_end': 7 + len(text),
                            'bbox': [80, 120, 510, 145]}], **fields}


def model(*blocks):
    return {'sections': {
        'chapter': section('chapter', None, '第五章 ProposedModel'),
        'metrics': section('metrics', 'chapter', '5.2 评价指标'),
        'experiment': section('experiment', 'chapter', '5.3 实验结果'),
        'other-method': section('other-method', 'chapter', '5.4 OtherModel 实验'),
        'other-chapter': section('other-chapter', None, '第四章 OtherModel'),
    }, 'blocks': list(blocks), 'pages': {}}


MAPPING = {'declaration_id': 'd1', 'chapter_id': 'chapter',
           'experiment_section_ids': ['experiment']}


def test_returns_pre_experiment_definition_with_exact_native_offsets():
    text = '平均绝对误差（Mean Absolute Error，MAE）定义为全部样本绝对误差的均值。'
    native = block('mae-definition', 'metrics', text)
    source = model(native, block('unrelated', 'other-chapter', text))
    before = copy.deepcopy(source)
    items = helper().metric_context({'id': 'd1', 'metric': '平均绝对误差'}, MAPPING, source)
    assert [i['block_id'] for i in items] == ['mae-definition']
    assert items[0]['quote'] == text == items[0]['text']
    assert items[0]['page'] == 20 and items[0]['section_id'] == 'metrics'
    assert items[0]['source_node_id'] == 'mae-definition-node'
    assert items[0]['block_text_start'] == 0 and items[0]['block_text_end'] == len(text)
    assert items[0]['provenance'][0]['node_text_start'] == 7
    assert items[0]['provenance'][0]['node_text_end'] == 7 + len(text)
    assert source == before


def test_metric_alias_finds_average_sse_header_without_keyword_in_abstract():
    source = model(block('header', 'experiment', 'Method | Average SSE | Standard deviation', kind='Table'))
    items = helper().metric_context({'id': 'd1', 'metric': '平方误差和'}, MAPPING, source)
    assert [i['block_id'] for i in items] == ['header']
    assert 'metric_header' in items[0]['evidence_kinds']


def test_does_not_infer_maximum_or_pass_from_matching_result_number():
    source = model(block('hit', 'experiment', 'ProposedModel AUC = 3.93，结果见表5.2。'))
    items = helper().metric_context({'id': 'd1', 'metric': 'AUC', 'number': '3.93',
                                      'comparison': 'maximum'}, MAPPING, source)
    assert items == []


def test_source_defined_formula_retrieves_cross_page_native_continuation():
    source = model(block('definition', 'metrics', 'gAUC 的相对提升（RelaImpr）定义如下：', page=20),
                   block('formula-a', 'metrics', 'RelaImpr = ((gAUC_enhanced - 0.5) /', page=20),
                   block('formula-b', 'metrics', '(gAUC_baseline - 0.5) - 1) × 100% (5.2)', page=21),
                   block('other', 'other-method', 'RelaImpr = OtherModel / 99', page=21))
    items = helper().metric_context({'id': 'd1', 'metric': 'gAUC相对提升'}, MAPPING, source)
    assert {i['block_id'] for i in items} == {'definition', 'formula-a', 'formula-b'}
    assert next(i for i in items if i['block_id'] == 'formula-b')['page'] == 21


def test_native_fraction_group_keeps_denominator_and_scale_with_eight_item_budget():
    source = model(block('general', 'metrics', 'gAUC 定义为按用户加权平均。'),
                   block('definition', 'metrics', '相对提升(RelaImpr) 的计算公式定义如下：'),
                   block('numerator', 'metrics', '((g)AUCEnhanced − 0.5'),
                   block('bracket', 'metrics', ')'),
                   block('denominator', 'metrics', '(g)AUCBaseline − 0.5 − 1'),
                   block('scale', 'metrics', '× 100%，'),
                   block('equation', 'metrics', '(5.2)'),
                   block('label', 'metrics', 'RelaImpr ='),
                   block('unrelated', 'metrics', 'RMSE 定义为另一项度量。'))
    items = helper().metric_context({'metric': 'gAUC相对提升'}, MAPPING, source)
    assert {'definition', 'numerator', 'bracket', 'denominator', 'scale', 'equation', 'label'} <= {i['block_id'] for i in items}
    assert 'unrelated' not in {i['block_id'] for i in items}
    assert len(items) <= 8


def test_preceding_metric_formula_does_not_crowd_out_requested_relative_formula():
    source = model(block('general', 'metrics', 'gAUC 定义为按用户加权平均。'),
                   block('previous-equation', 'metrics', '(5.1)'),
                   block('previous-label', 'metrics', 'gAUC ='),
                   block('previous-symbol', 'metrics', 'u w'),
                   block('definition', 'metrics', '相对提升(RelaImpr) 的计算公式定义如下：'),
                   block('numerator', 'metrics', '((g)AUCEnhanced − 0.5'),
                   block('bracket', 'metrics', ')'),
                   block('denominator', 'metrics', '(g)AUCBaseline − 0.5 − 1'),
                   block('scale', 'metrics', '× 100%，'),
                   block('equation', 'metrics', '(5.2)'),
                   block('label', 'metrics', 'RelaImpr ='))
    items = helper().metric_context({'metric': 'gAUC相对提升'}, MAPPING, source)
    assert {'definition', 'numerator', 'denominator', 'scale', 'equation', 'label'} <= {i['block_id'] for i in items}
    assert 'previous-equation' not in {i['block_id'] for i in items}


def test_base_metric_does_not_retrieve_distinct_compound_metric_definition():
    source = model(block('mae', 'metrics', '平均绝对误差(MAE): 反映预测误差的平均水平。'),
                   block('dmae', 'metrics', '距离矩阵平均绝对误差(D-MAE): 定义为距离矩阵之差。'),
                   block('dmae-formula', 'metrics', 'D-MAE ='))
    items = helper().metric_context({'metric': 'MAE'}, MAPPING, source)
    assert [i['block_id'] for i in items] == ['mae']


def test_metric_label_is_paired_with_immediately_following_anaphoric_definition():
    source = model(block('label', 'metrics', '平均误差平方和（Average Sum of Squared Errors, Avg-SSE）'),
                   block('definition', 'metrics', '该指标的计算方式为全部子集误差平方和的算术平均值。形式化定义如下：'))
    items = helper().metric_context({'metric': '平均SSE'}, MAPPING, source)
    assert {i['block_id'] for i in items} == {'label', 'definition'}


def test_formula_continuation_cannot_cross_unmapped_method_or_page_gap():
    source = model(block('definition', 'metrics', 'MAE 定义如下：'),
                   block('other', 'other-method', 'MAE = 123'),
                   block('far', 'metrics', 'sum(abs(errors)) / n', page=24))
    items = helper().metric_context({'id': 'd1', 'metric': 'MAE'}, MAPPING, source)
    assert [i['block_id'] for i in items] == ['definition']


@pytest.mark.parametrize('field,value', [('dataset', 'Dataset-B'), ('method', 'OtherModel'),
                                        ('baseline', 'OtherBaseline'), ('condition', 'test split')])
def test_explicit_conflicting_scope_metadata_is_excluded(field, value):
    source = model(block('wrong', 'metrics', 'MAE 定义为平均绝对误差。', **{field: value}),
                   block('right', 'metrics', 'MAE 定义为平均绝对误差。'))
    declaration = {'id': 'd1', 'metric': 'MAE', 'dataset': 'Dataset-A',
                   'method': 'ProposedModel', 'baseline': 'Baseline', 'condition': 'validation split'}
    items = helper().metric_context(declaration, MAPPING, source)
    assert [i['block_id'] for i in items] == ['right']


def test_dataset_specific_sibling_definitions_do_not_leak():
    source = model(block('wrong', 'wrong-dataset', 'MAE 定义为平均绝对误差。'),
                   block('right', 'metrics', 'MAE 定义为平均绝对误差。'))
    source['sections']['wrong-dataset'] = section('wrong-dataset', 'chapter', 'Dataset-B 评价指标')
    items = helper().metric_context({'id': 'd1', 'metric': 'MAE', 'dataset': 'Dataset-A'}, MAPPING, source)
    assert [i['block_id'] for i in items] == ['right']


def test_same_chapter_other_method_definition_without_experiment_label_is_excluded():
    source = model(block('other-loss', 'other-loss', 'MAE 定义为 OtherModel 的损失函数：x / n。'),
                   block('right', 'metrics', 'MAE 定义为平均绝对误差。'))
    source['sections']['other-loss'] = section('other-loss', 'chapter', '5.4 OtherModel 模型定义')
    items = helper().metric_context({'metric': 'MAE', 'method': 'ProposedModel'}, MAPPING, source)
    assert [i['block_id'] for i in items] == ['right']


def test_missing_or_unknown_mapping_fails_closed():
    source = model(block('definition', 'metrics', 'MAE 定义为平均绝对误差。'))
    for mapping in ({}, {'chapter_id': 'missing', 'experiment_section_ids': ['experiment']}):
        assert helper().metric_context({'metric': 'MAE'}, mapping, source) == []


def test_retrieves_shared_preliminary_definition_but_not_other_method_chapter():
    source = model(block('shared', 'shared-metrics', '平均绝对误差(MAE): 反映预测误差的平均水平，MAE = 1 / n。', page=12),
                   block('other-definition', 'other-metrics', '平均绝对误差(MAE) 定义为1 / k。', page=15))
    source['sections'].update({
        'prelim': section('prelim', None, '第二章 相关概念与工作概述'),
        'shared-metrics': section('shared-metrics', 'prelim', '2.1.4 能垒预测的评估指标体系'),
        'other-metrics': section('other-metrics', 'other-chapter', '4.1 评估指标体系'),
    })
    items = helper().metric_context({'metric': 'MAE'}, MAPPING, source)
    assert [i['block_id'] for i in items] == ['shared']
    assert items[0]['scope_kind'] == 'shared_metric_definition'


def test_bounded_exact_excerpt_preserves_clipped_source_offsets():
    text = ('irrelevant prose ' * 80) + 'MAE 定义为平均绝对误差。' + (' trailing prose' * 80)
    source = model(block('long', 'metrics', text), block('second', 'metrics', 'MAE 定义为平均绝对误差。'))
    source['blocks'][0]['provenance'][0]['text_offsets'] = [0, len(text)]
    items = helper().metric_context({'metric': 'MAE'}, MAPPING, source, max_items=1, max_chars=90)
    assert len(items) == 1 and len(items[0]['quote']) <= 90
    item = items[0]
    assert 'MAE' in item['quote']
    assert item['quote'] == text[item['block_text_start']:item['block_text_end']]
    assert item['provenance'][0]['node_text_start'] == 7 + item['block_text_start']
    assert item['provenance'][0]['node_text_end'] == 7 + item['block_text_end']
    assert item['provenance'][0]['text_offsets'] == [item['block_text_start'], item['block_text_end']]


def test_multiline_source_quote_keeps_native_gaps_in_offsets():
    native = block('lines', 'metrics', 'MAE 定义如下：\n绝对误差的均值。')
    native['provenance'] = [
        {'line_id': 'l1', 'page_index': 19, 'node_text_start': 11, 'node_text_end': 20, 'bbox': [80, 120, 300, 140]},
        {'line_id': 'l2', 'page_index': 19, 'node_text_start': 28, 'node_text_end': 36, 'bbox': [80, 150, 300, 170]},
    ]
    item = helper().metric_context({'metric': 'MAE'}, MAPPING, model(native))[0]
    assert [(p['node_text_start'], p['node_text_end']) for p in item['provenance']] == [(11, 20), (28, 36)]
    assert item['quote'] == native['text']


@pytest.mark.parametrize('expression,variables,want', [
    ('(enhanced / baseline - 1) * 100', {'enhanced': '0.8210', 'baseline': '0.8000'}, Decimal('2.62500')),
    ('((enhanced - 0.5) / (baseline - 0.5) - 1) * 100', {'enhanced': '0.8210', 'baseline': '0.8000'}, Decimal('7.00')),
    ('0.10000000000000000001 + delta', {'delta': '0.00000000000000000001'}, Decimal('0.10000000000000000002')),
    ('-(x - 2) ** 2 + +y', {'x': Decimal('5'), 'y': 10}, Decimal('1')),
    ('1e-4 * n / 2', {'n': '20'}, Decimal('0.001')),
])
def test_decimal_arithmetic_uses_only_expression_and_supplied_values(expression, variables, want):
    value = helper().evaluate_expression(expression, variables)
    assert isinstance(value, Decimal) and value == want


def test_rounding_stays_with_caller_at_declared_precision():
    value = helper().evaluate_expression('(enhanced / baseline - 1) * 100',
                                         {'enhanced': '1.055251', 'baseline': '1'})
    assert value == Decimal('5.525100')
    assert value.quantize(Decimal('.01')) == Decimal('5.53')


@pytest.mark.parametrize('expression,variables', [
    ('missing + 1', {}), ('x / 0', {'x': '1'}), ('1 / (x - 1)', {'x': '1'}),
    ('x + 1', {'x': 'NaN'}), ('x', {'x': 'Infinity'}), ('x', {'x': float('inf')}),
    ('x', {'x': True}), ('float("nan")', {}), ('__import__("os").system("echo unsafe")', {}),
    ('x.real', {'x': '1'}), ('x[0]', {'x': '1'}), ('[x for x in ()]', {}),
    ('1 if x else 2', {'x': '1'}), ('1 < 2', {}), ('True', {}), ('"1"', {}),
    ('2 ** 100000000', {}), ('2 ** 0.5', {}), ('1e999999', {}),
    ('1 // 2', {}), ('3 % 2', {}), ('(x := 1)', {}), ('0x10 + 1', {}),
])
def test_unsafe_unknown_or_invalid_arithmetic_fails_closed(expression, variables):
    with pytest.raises(ValueError):
        helper().evaluate_expression(expression, variables)
