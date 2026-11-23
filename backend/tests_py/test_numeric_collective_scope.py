"""A framework evaluated across native model/dataset sets has collective roles."""
import copy

import pytest

from numeric_statistical_evidence import conservative_guard
from test_numeric_metric_evidence import block, model, MAPPING


def collective_case(metric='AUC'):
    caption = block('caption', 'experiment', 'Table 2.1', page=21, kind='Caption')
    caption['provenance'][0]['bbox'] = [80, 100, 510, 110]
    continuation = block('caption-text', 'experiment', 'Results on 2 public datasets.', page=21)
    continuation['provenance'][0]['bbox'] = [80, 112, 510, 125]
    comparison = block('comparison', 'experiment', '表2.1比较了本方法与各基准模型的实验结果。', page=21)
    source = model(caption, continuation, comparison)
    paths = [['Dataset'], ['Model'], ['基线', 'AUC'], ['本方法', 'RelaImpr (AUC)'], ['本方法', 'RelaImpr (gAUC)']]
    matrix = [[' / '.join(path) for path in paths],
              ['Alpha', 'HostA', '0.8', '2.1111%', '4.1111%'],
              ['Alpha', 'HostB', '0.8', '1.1111%', '3.1111%'],
              ['Beta', 'HostA', '0.8', '3.2111%', '5.2111%'],
              ['Beta', 'HostB', '0.8', '1.2111%', '2.2111%']]
    source['tables'] = [{'table_id': 't1', 'section_id': 'experiment', 'page': 21,
        'caption': 'Table 2.1', 'bbox': [80, 130, 510, 300],
        'source_node_ids': ['caption-node'], 'matrix': matrix, 'raw_matrix': copy.deepcopy(matrix),
        'column_headers': matrix[0], 'native_header_paths': paths, 'native_cells_grounded': True,
        'reliability': 'reliable', 'limitations': [], 'row_count': 5, 'column_count': 5}]
    context = '所提出的语义信息融合框架在两个公开数据集上取得改善。'
    source['pages'] = {7: {'lines': [{'id': 'native-abstract-line', 'text': context}]}}
    number = '3.21' if metric == 'AUC' else '5.21'
    row = {'declaration_id': 'd1', 'declaration': {'number': number, 'metric': metric + '相对提升',
        'unit': '%', 'comparison': 'relative', 'condition': '公开数据集', 'dataset': '两个公开数据集',
        'method': '语义信息融合框架', 'baseline': '多种主流推荐模型', 'source_context': context,
        'text': metric + '最高相对提升' + number + '%'}, 'status': 'consistent',
        'reason': '完整表格与声明一致', 'suggestion': '',
        'evidence': [{'block_id': 't1', 'page': 21, 'quote': str(matrix)}]}
    return row, source


@pytest.mark.parametrize('metric', ['AUC', 'gAUC'])
def test_native_collective_roles_cover_all_framework_comparisons(metric):
    row, source = collective_case(metric)
    before = copy.deepcopy(source)
    assert conservative_guard([row], model=source, mappings=[MAPPING]) == []
    assert row['status'] == 'consistent'
    proof = row['statistical_evidence'][0]
    assert proof['comparison_count'] == 4
    assert proof['tables'][0]['scope_sources']
    assert source == before


@pytest.mark.parametrize('change', ['count_mismatch', 'not_proposed', 'fake_context', 'no_caption',
                                   'named_baseline', 'missing_model', 'metadata_conflict', 'no_comparison'])
def test_unbound_collective_roles_preserve_the_maximum_warning(change):
    row, source = collective_case()
    table = source['tables'][0]
    if change == 'count_mismatch':
        row['declaration']['dataset'] = '三个公开数据集'
    elif change == 'not_proposed':
        table['native_header_paths'][3][0] = 'Other'
        table['native_header_paths'][4][0] = 'Other'
        table['matrix'][0][3:] = [' / '.join(path) for path in table['native_header_paths'][3:]]
        table['raw_matrix'] = copy.deepcopy(table['matrix'])
    elif change == 'fake_context':
        source['pages'][7]['lines'][0]['text'] = '原生摘要没有该框架描述。'
    elif change == 'no_caption':
        source['blocks'] = [b for b in source['blocks'] if b['block_id'] != 'caption-text']
    elif change == 'named_baseline':
        row['declaration']['baseline'] = 'WrongNet'
    elif change == 'missing_model':
        table['matrix'][2][1] = None
        table['raw_matrix'] = copy.deepcopy(table['matrix'])
    elif change == 'metadata_conflict':
        table['method'] = 'DifferentMethod'
    elif change == 'no_comparison':
        source['blocks'] = [b for b in source['blocks'] if b['block_id'] != 'comparison']
    conservative_guard([row], model=source, mappings=[MAPPING])
    assert row['status'] == 'inconclusive'


def test_collective_baseline_does_not_promote_ablation_to_overall_comparison():
    row, source = collective_case()
    source['sections']['experiment']['title'] = '5.3 消融实验'
    conservative_guard([row], model=source, mappings=[MAPPING])
    assert row['status'] == 'inconclusive'
