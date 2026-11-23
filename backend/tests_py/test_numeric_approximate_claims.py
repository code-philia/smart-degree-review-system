"""Rounded derived claims need native operands, roles, and measurement context."""
import copy

import pytest

from numeric_statistical_evidence import conservative_guard
from test_numeric_metric_evidence import model, MAPPING


def ratio_case():
    matrix = [['Seq', 'Lens', 'Dense'], ['8k', '0.14', '0.56'], ['32k', '0.22', '1.20']]
    table = {'table_id': 'timings', 'section_id': 'experiment', 'page': 21,
             'caption': 'Table 1 Attention latency (ms)', 'matrix': matrix,
             'raw_matrix': copy.deepcopy(matrix), 'column_headers': matrix[0],
             'native_header_paths': [[header] for header in matrix[0]],
             'native_cells_grounded': True, 'reliability': 'reliable',
             'limitations': [], 'row_count': 3, 'column_count': 3}
    source = model()
    source['tables'] = [table]
    row = {'declaration_id': 'd1', 'declaration': {
        'number': '5', 'metric': '注意力加速', 'unit': '倍', 'method': 'Lens',
        'baseline': '', 'condition': '32K decoding', 'text': '32K注意力加速约5倍'},
        'status': 'consistent', 'reason': '计算得Dense/Lens=1.20/0.22≈5.45，可按声明精度舍入。',
        'suggestion': '', 'evidence': [{'block_id': 'timings', 'page': 21,
            'quote': 'Table 1\nSeq | Lens | Dense\n8k | 0.14 | 0.56\n32k | 0.22 | 1.20'}]}
    return row, source


def test_native_same_row_ratio_prevents_false_rounding_veto():
    row, source = ratio_case()
    before = copy.deepcopy(source)
    assert conservative_guard([row], model=source, mappings=[MAPPING]) == []
    assert row['status'] == 'consistent'
    proof = row['statistical_evidence'][0]
    assert proof['table_id'] == 'timings'
    assert proof['numerator'] == {'row': 2, 'column': 2, 'header': 'Dense', 'value': '1.20'}
    assert proof['denominator'] == {'row': 2, 'column': 1, 'header': 'Lens', 'value': '0.22'}
    assert proof['derived_value'].startswith('5.4545')
    assert source == before


@pytest.mark.parametrize('mutation', [
    'cross_row', 'wrong_method', 'wrong_baseline', 'wrong_metric', 'wrong_caption',
    'other_phase', 'fake_operand', 'fake_quotient', 'fake_intermediate',
    'incomplete_table', 'outside_scope', 'uncited_table',
])
def test_unproven_ratio_preserves_rounding_warning(mutation):
    row, source = ratio_case()
    if mutation == 'cross_row':
        row['declaration'].update(number='9', text='注意力加速约9倍')
        row['reason'] = 'Dense/Lens=1.20/0.14≈8.57，可舍入到9。'
    elif mutation == 'wrong_method':
        row['declaration']['method'] = 'Other'
    elif mutation == 'wrong_baseline':
        row['declaration']['baseline'] = 'Other'
    elif mutation == 'wrong_metric':
        row['declaration'].update(metric='准确率', unit='%')
    elif mutation == 'wrong_caption':
        source['tables'][0]['caption'] = 'Table 1 Attention memory (MB)'
    elif mutation == 'other_phase':
        source['tables'][0]['caption'] = 'Table 1 Query latency (ms)'
    elif mutation == 'fake_operand':
        row['reason'] = 'Dense/Lens=1.15/0.22≈5.23，可舍入到5。'
    elif mutation == 'fake_quotient':
        row['declaration'].update(number='6', text='注意力加速约6倍')
        row['reason'] = 'Dense/Lens=1.20/0.22≈6，可舍入到6。'
    elif mutation == 'fake_intermediate':
        row['reason'] = 'Dense/Lens=1.20/0.22≈5.40，可舍入到5。'
    elif mutation == 'incomplete_table':
        source['tables'][0]['native_cells_grounded'] = False
    elif mutation == 'outside_scope':
        source['tables'][0]['section_id'] = 'other-chapter'
    elif mutation == 'uncited_table':
        row['evidence'][0]['block_id'] = 'other-table'
    conservative_guard([row], model=source, mappings=[MAPPING])
    assert row['status'] == 'inconclusive'
    assert not row.get('statistical_evidence')


def test_literal_nonrounding_value_is_not_excused_by_speedup_language():
    row, source = ratio_case()
    row['reason'] = '注意力加速为5.57倍，按概数舍入为5倍。'
    row['evidence'][0]['quote'] = '32K注意力加速5.57倍。'
    conservative_guard([row], model=source, mappings=[MAPPING])
    assert row['status'] == 'inconclusive'
