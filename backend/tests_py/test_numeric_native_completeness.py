"""Sparse native rows cannot disappear from a certified comparison set."""
import numeric_consistency as numeric
import pytest
from numeric_native_tables import _attach_native, _limit, _native_grid
from test_numeric_metric_evidence import MAPPING, model
from test_numeric_statistical_evidence import maximum_row


@pytest.mark.parametrize('orphan', ['9.5%', '9.5e0%', '9.5 ms', 'Dataset-C - -'])
def test_sparse_native_result_row_cannot_be_omitted_from_maximum_coverage(orphan):
    fragments = []

    def fragment(text, x, y):
        box = [x, y - 4, x + len(text) * 3, y + 4]
        fragments.append({
            'text': text, 'bbox': box,
            'native_spans': [{
                'block_index': len(fragments), 'line_index': 0,
                'span_index': 0, 'char_start': 0, 'char_end': len(text),
                'text': text, 'bbox': box,
            }],
        })

    for text, x in [('Dataset', 50), ('RelaImpr (AUC)', 200), ('gAUC', 350)]:
        fragment(text, x, 130)
    for y, dataset, auc, gauc in [
        (160, 'A', '3.9321%', '1.0%'),
        (180, 'B', '2.0%', '1.0%'),
    ]:
        for text, x in [(dataset, 50), (auc, 200), (gauc, 350)]:
            fragment(text, x, y)
    # This larger native result has an unreadable/absent dataset label and
    # second measurement. It must remain unknown, rather than disappear.
    fragment(orphan, 200, 210)
    rules = [[40, 120, 500], [40, 144, 500], [40, 230, 500]]
    grid = _native_grid([40, 120, 500, 230], rules, fragments, [], rules)
    if grid is None:
        return  # Refusing recovery is also conservative.
    proxy, cells, paths, spanning, uncertain = grid
    source = model()
    source['blocks'] = [{
        'block_id': 'caption:p21', 'text': 'Table 1 Results', 'block_type': 'Caption',
        'section_id': 'experiment', 'source_node_id': 'caption', 'page': 21,
        'provenance': [{'bbox': [40, 100, 400, 110]}],
    }]
    table, failure = numeric._table_structure(proxy, 21, 1, source, 800)
    assert failure is None
    table.update(raw_matrix=proxy.extract(), native_header_paths=paths,
                 native_spanning_cells=spanning)
    _attach_native(table, fragments, cells)
    if uncertain:
        _limit(table, 'ambiguous_native_header_relationships')
    source['tables'] = [table]
    row = maximum_row()
    row['evidence'][0]['block_id'] = table['table_id']
    numeric.conservative_evidence_guard([row], model=source, mappings=[MAPPING])
    assert row['status'] == 'inconclusive', (
        'A physically present, unresolved 9.5% result cannot certify 3.93% as '
        f'the complete maximum: {table["matrix"]!r}, {table["limitations"]!r}'
    )
