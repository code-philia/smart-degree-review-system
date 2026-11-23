"""Native PDF controls; original-paper cases come from a private read-only manifest."""
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

fitz = pytest.importorskip('fitz')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import numeric_consistency as numeric

from numeric_native_tables import recover_native_tables
import numeric_native_tables as native


def _caption_context(table, model):
    return native.native_caption_context(table, model)


def _caption_block(source_id, text, bbox, *, page=3, section='experiment'):
    return {'block_id': source_id + ':p' + str(page), 'source_node_id': source_id,
            'section_id': section, 'page': page, 'text': text, 'block_type': 'Paragraph',
            'provenance': [{'page_index': page - 1, 'bbox': bbox}]}


def _caption_case(anchor_text='Table 1.2'):
    anchor = _caption_block('caption', anchor_text, [100, 100, 150, 112])
    table = {'page': 3, 'bbox': [90, 140, 460, 300],
             'source_node_ids': ['caption'], 'caption': anchor_text}
    return table, {'blocks': [anchor]}, anchor


def test_native_caption_context_recovers_only_adjacent_source_title():
    import copy
    table, model, anchor = _caption_case()
    title = _caption_block('title', 'Performance on cohort A', [162, 100.5, 350, 112.5])
    model['blocks'].append(title)
    before = copy.deepcopy((table, model))
    context = _caption_context(table, model)
    assert [block['text'] for block in context] == ['Table 1.2', 'Performance on cohort A']
    for actual, source in zip(context, [anchor, title]):
        assert all(actual[key] == source[key] for key in
                   ('text', 'block_id', 'source_node_id', 'page', 'provenance'))
    assert (table, model) == before
    context[0]['provenance'][0]['bbox'][0] = -100
    assert model['blocks'][0]['provenance'][0]['bbox'][0] == 100


def test_native_caption_context_keeps_full_caption_anchor_intact():
    table, model, anchor = _caption_case('Table 1.2 Performance on cohort A')
    anchor['provenance'] = [{'page_index': 2, 'bbox': [100, 100, 150, 112]},
                            {'page_index': 2, 'bbox': [162, 100, 350, 112]}]
    context = _caption_context(table, model)
    assert len(context) == 1
    assert context[0]['text'] == anchor['text']
    assert context[0]['provenance'] == anchor['provenance']


def test_native_caption_context_projects_caption_line_from_mixed_source_block():
    table, model, _ = _caption_case()
    title = 'Performance on cohort A'
    mixed = _caption_block('mixed-title', title + '\nUnrelated table header', [162, 100, 350, 112])
    mixed['provenance'] = [
        {'bbox': [162, 100, 350, 112], 'node_text_start': 0, 'node_text_end': len(title)},
        {'bbox': [162, 150, 350, 162], 'node_text_start': len(title) + 1,
         'node_text_end': len(mixed['text'])},
    ]
    model['blocks'].append(mixed)
    context = _caption_context(table, model)
    assert [b['text'] for b in context] == ['Table 1.2', title]
    assert context[1]['block_id'] == mixed['block_id']
    assert context[1]['source_node_id'] == mixed['source_node_id']
    assert context[1]['provenance'] == mixed['provenance'][:1]
    assert mixed['text'].endswith('Unrelated table header')


def test_native_caption_context_stops_at_another_table_label():
    table, model, _ = _caption_case()
    model['blocks'] += [_caption_block('other-caption', 'Table 7.8', [162, 100, 212, 112]),
                        _caption_block('other-title', 'Results on a different cohort', [224, 100, 450, 112])]
    assert [b['text'] for b in _caption_context(table, model)] == ['Table 1.2']


def test_native_caption_context_does_not_jump_a_foreign_caption_boundary():
    table, model, _ = _caption_case()
    model['blocks'] += [_caption_block('other-caption', '表2', [153, 100, 161, 112], section='other'),
                        _caption_block('other-title', 'Different cohort', [164, 100, 350, 112])]
    assert [b['text'] for b in _caption_context(table, model)] == ['Table 1.2']


@pytest.mark.parametrize('foreign', [
    _caption_block('parallel-title', 'Other column condition', [480, 100, 590, 112]),
    _caption_block('later-paragraph', 'The condition is different here.', [162, 145, 440, 157]),
    _caption_block('below-table', 'The condition is different here.', [162, 310, 440, 322]),
    _caption_block('other-section', 'Unrelated section condition', [162, 100, 440, 112], section='other'),
    _caption_block('other-page', 'Unrelated page condition', [162, 100, 440, 112], page=4),
])
def test_native_caption_context_excludes_nearby_foreign_source(foreign):
    table, model, _ = _caption_case()
    model['blocks'].append(foreign)
    assert [b['text'] for b in _caption_context(table, model)] == ['Table 1.2']


def test_native_caption_context_requires_the_existing_source_anchor():
    table, model, _ = _caption_case()
    table['source_node_ids'] = ['different-source']
    model['blocks'].append(_caption_block('title', 'Performance on cohort A', [162, 100, 350, 112]))
    assert _caption_context(table, model) == []


def test_native_caption_context_rejects_intervening_caption_for_another_table():
    table, model, _ = _caption_case()
    model['blocks'] += [_caption_block('title', 'Performance on cohort A', [162, 100, 350, 112]),
                        _caption_block('closer-caption', 'Table 7.8', [100, 120, 150, 132])]
    assert _caption_context(table, model) == []


def _rule(page, x0, x1, y):
    page.draw_line((x0, y), (x1, y), width=0.6)


def _text(page, x, y, text, size=10):
    page.insert_text((x, y), text, fontsize=size)


def _fixture(tmp_path, draw):
    doc = fitz.open()
    page = doc.new_page(width=600, height=800)
    draw(page)
    path = tmp_path / 'derived-native-control.pdf'
    doc.save(path)
    doc.close()
    with fitz.open(path) as original:
        blocks = []
        for bi, block in enumerate(original[0].get_text('dict')['blocks']):
            for li, line in enumerate(block.get('lines', [])):
                text = ''.join(span['text'] for span in line['spans'])
                blocks.append({'block_id': f'b{bi}l{li}:p1',
                    'source_node_id': f'b{bi}l{li}', 'section_id': 'experiment',
                    'page': 1, 'text': text,
                    'block_type': 'Caption' if text.startswith('Table ') else 'Paragraph',
                    'provenance': [{'page_index': 0, 'bbox': list(line['bbox'])}]})
    return path, {'blocks': blocks, 'sections': {'experiment': {'title': 'Results'}}}


def _recover(path, model):
    return recover_native_tables(path, model, numeric._table_structure, version='native-control/1')


def _simple_table(page, x0=50, x1=500, top=120, caption='Table 1 Results', suffix=''):
    _text(page, x0, top - 12, caption)
    for y in (top, top + 24, top + 94):
        _rule(page, x0, x1, y)
    for x, text in ((x0 + 8, 'Model'), (x0 + 200, 'MAE'), (x0 + 340, 'AUC')):
        _text(page, x, top + 16, text)
    for y, values in ((top + 42, ('Base' + suffix, '4.10', '0.70')),
                      (top + 62, ('Ours' + suffix, '3.20', '0.82')),
                      (top + 82, ('Other' + suffix, '3.90', '0.75'))):
        for x, text in zip((x0 + 8, x0 + 200, x0 + 340), values):
            _text(page, x, y, text)


def test_horizontal_rules_recover_complete_rows_without_vertical_borders(tmp_path):
    path, model = _fixture(tmp_path, _simple_table)
    tables, diagnostics = _recover(path, model)
    assert any(['Ours', '3.20', '0.82'] in t['matrix'] for t in tables)
    assert diagnostics['attempted_pages'] == 1
    assert diagnostics['successes'] == len(tables)


def test_weak_line_table_does_not_hide_native_text_result_rows(tmp_path):
    def draw(page):
        for x in (50, 160, 270):
            page.draw_line((x, 40), (x, 66))
        for y in (40, 66):
            _rule(page, 50, 270, y)
        _text(page, 58, 57, 'Header')
        _text(page, 168, 57, 'Only')
        _simple_table(page, top=170)
    path, model = _fixture(tmp_path, draw)
    tables, _ = _recover(path, model)
    assert any(['Ours', '3.20', '0.82'] in t['matrix'] for t in tables)
    assert any(t.get('strategy') == 'text' for t in tables)
    assert all(t['reliability'] == 'limited' for t in tables if t.get('strategy') == 'text')


def test_multilevel_headers_keep_native_spans_and_grounded_column_paths(tmp_path):
    def draw(page):
        _text(page, 50, 108, 'Table 2 Dataset comparison')
        for y in (120, 164, 224):
            _rule(page, 50, 500, y)
        _text(page, 58, 139, 'Model')
        _text(page, 257, 136, 'Dataset A')
        _text(page, 390, 136, 'Dataset B')
        for x, text in ((220, 'MAE'), (300, 'RMSE'), (380, 'MAE'), (450, 'RMSE')):
            _text(page, x, 157, text)
        for y, name in ((182, 'Base'), (202, 'Ours')):
            _text(page, 58, y, name)
            for x, value in zip((220, 300, 380, 450), ('2.40', '3.20', '4.10', '5.20')):
                _text(page, x, y, value)
    path, model = _fixture(tmp_path, draw)
    tables, _ = _recover(path, model)
    table = next(t for t in tables if ['Ours', '2.40', '3.20', '4.10', '5.20'] in t['matrix'])
    assert table['native_header_paths'][1] == ['Dataset A', 'MAE']
    assert table['native_header_paths'][2] == ['Dataset A', 'RMSE']
    assert table['native_header_paths'][3] == ['Dataset B', 'MAE']
    assert table['native_header_paths'][4] == ['Dataset B', 'RMSE']
    # Header hierarchy is additional evidence, never a reason to erase sparse-cell uncertainty.
    assert table['reliability'] == 'limited'
    assert 'merged_or_multilevel_header_cells' in table['limitations']


def test_nearby_captioned_tables_remain_separate(tmp_path):
    def draw(page):
        _simple_table(page, top=120, caption='Table 1 Left condition', suffix='Left')
        _simple_table(page, top=260, caption='Table 2 Right condition', suffix='Right')
    path, model = _fixture(tmp_path, draw)
    tables, _ = _recover(path, model)
    native = [t for t in tables if t.get('strategy') == 'native_rules']
    assert len(native) == 2
    assert {t['caption'] for t in native} == {'Table 1 Left condition', 'Table 2 Right condition'}
    assert all(not ('OursLeft' in str(t['matrix']) and 'OursRight' in str(t['matrix'])) for t in native)
    assert native[1]['table_id'] not in native[0]['same_source_alternatives']


def test_recovered_cells_are_exact_native_text_with_geometry(tmp_path):
    path, model = _fixture(tmp_path, _simple_table)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    tables, _ = _recover(path, model)
    table = next(t for t in tables if ['Ours', '3.20', '0.82'] in t['matrix'])
    with fitz.open(path) as doc:
        for row in table['rows']:
            for cell in row['cells']:
                if not cell.get('text'):
                    continue
                assert cell['bbox']
                assert cell['native_spans']
                for source in cell['native_spans']:
                    assert source['text'].strip()
                    assert source['char_start'] < source['char_end']
                    assert source['text'] in doc[0].get_text('text')
    assert table['raw_matrix']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_unbound_native_rule_region_cannot_become_reliable(tmp_path):
    path, _ = _fixture(tmp_path, _simple_table)
    tables, _ = _recover(path, {'blocks': [], 'sections': {}})
    assert tables
    assert all(t['reliability'] == 'limited' for t in tables)
    assert all('no_paper_model_source_binding' in t['limitations'] for t in tables)


def test_centered_group_label_uses_ruling_span_without_filling_source_cells(tmp_path):
    def draw(page):
        _text(page, 50, 108, 'Table 3 Grouped results')
        for y in (120, 144, 214):
            _rule(page, 50, 540, y)
        for x, value in ((58, 'Dataset'), (180, 'Model'), (320, 'MAE'), (450, 'AUC')):
            _text(page, x, 136, value)
        _text(page, 58, 182, 'Dataset-A')
        for y, name in ((162, 'Base'), (182, 'Ours'), (202, 'Other')):
            for x, value in zip((180, 320, 450), (name, '3.20', '0.82')):
                _text(page, x, y, value)
    path, model = _fixture(tmp_path, draw)
    tables, _ = _recover(path, model)
    table = next(t for t in tables if t.get('strategy') == 'native_rules')
    group = next(c for c in table['native_spanning_cells'] if c['text'] == 'Dataset-A')
    assert group['role'] == 'body'
    assert group['row_indices'] == [1, 2, 3]
    assert group['column_indices'] == [0]
    assert group['native_spans']
    assert all(row[0] is None for row in table['matrix'][1:])


def test_caption_from_neighboring_column_cannot_bind_the_table(tmp_path):
    def draw(page):
        _text(page, 40, 108, 'Table 1 Unrelated left')
        _text(page, 300, 108, 'Table 2 Right result')
        for y in (120, 144, 214):
            _rule(page, 300, 560, y)
        for x, value in ((310, 'Model'), (400, 'MAE'), (480, 'AUC')):
            _text(page, x, 136, value)
        for y, name in ((162, 'Base'), (182, 'Ours'), (202, 'Other')):
            for x, value in zip((310, 400, 480), (name, '3.20', '0.82')):
                _text(page, x, y, value)
    path, model = _fixture(tmp_path, draw)
    model['blocks'] = [b for b in model['blocks'] if b['text'] == 'Table 1 Unrelated left']
    tables, _ = _recover(path, model)
    table = next(t for t in tables if t.get('strategy') == 'native_rules')
    assert table['section_id'] is None
    assert table['source_node_ids'] == []
    assert table['reliability'] == 'limited'


def test_single_sparse_numeric_value_is_not_a_group_label(tmp_path):
    def draw(page):
        _text(page, 50, 108, 'Table 4 Sparse measurements')
        for y in (120, 144, 214):
            _rule(page, 50, 540, y)
        for x, value in ((58, 'Model'), (200, 'Optional'), (320, 'MAE'), (450, 'AUC')):
            _text(page, x, 136, value)
        _text(page, 200, 182, '8.40')
        for y, name in ((162, 'Base'), (182, 'Ours'), (202, 'Other')):
            for x, value in zip((58, 320, 450), (name, '3.20', '0.82')):
                _text(page, x, y, value)
    path, model = _fixture(tmp_path, draw)
    tables, _ = _recover(path, model)
    table = next(t for t in tables if t.get('strategy') == 'native_rules')
    assert table['matrix'][2][1] == '8.40'
    assert not any(c['text'] == '8.40' for c in table['native_spanning_cells'])
    assert table['reliability'] == 'limited'


def test_uncentered_sparse_text_remains_on_its_native_row(tmp_path):
    def draw(page):
        _text(page, 50, 108, 'Table 5 Sparse conditions')
        for y in (120, 144, 214):
            _rule(page, 50, 540, y)
        for x, value in ((58, 'Model'), (200, 'Condition'), (320, 'MAE'), (450, 'AUC')):
            _text(page, x, 136, value)
        _text(page, 200, 162, 'Rare')
        for y, name in ((162, 'Base'), (182, 'Ours'), (202, 'Other')):
            for x, value in zip((58, 320, 450), (name, '3.20', '0.82')):
                _text(page, x, y, value)
    path, model = _fixture(tmp_path, draw)
    tables, _ = _recover(path, model)
    table = next(t for t in tables if t.get('strategy') == 'native_rules')
    assert table['matrix'][1][1] == 'Rare'
    assert not any(c['text'] == 'Rare' for c in table['native_spanning_cells'])


@pytest.mark.parametrize('neighbor_vertical', [False, True])
def test_partial_native_header_rules_bind_uneven_groups_and_row_labels(tmp_path, neighbor_vertical):
    def draw(page):
        _text(page, 50, 108, 'Table 6 Grouped baseline comparison')
        for y in (120, 170, 244):
            _rule(page, 50, 540, y)
        _rule(page, 250, 365, 142)
        _rule(page, 390, 530, 142)
        if neighbor_vertical:
            for x in (20, 580):
                page.draw_line((x, 124), (x, 142), width=0.6)
        _text(page, 270, 137, 'Baseline')
        _text(page, 420, 137, 'Enhanced')
        _text(page, 58, 151, 'Dataset')
        _text(page, 160, 151, 'Model')
        for x, label in ((260, 'AUC'), (320, 'gAUC'), (400, 'AUC'), (460, 'gAUC')):
            _text(page, x, 164, label)
        for y, name in ((190, 'Base'), (210, 'Ours'), (230, 'Other')):
            for x, value in zip((58, 160, 260, 320, 400, 460), ('Set-A', name, '0.70', '0.72', '0.80', '0.82')):
                _text(page, x, y, value)
    path, model = _fixture(tmp_path, draw)
    tables, _ = _recover(path, model)
    table = next(t for t in tables if t.get('strategy') == 'native_rules')
    assert table['native_header_paths'][0] == ['Dataset']
    assert table['native_header_paths'][1] == ['Model']
    assert table['native_header_paths'][2] == ['Baseline', 'AUC']
    assert table['native_header_paths'][3] == ['Baseline', 'gAUC']
    assert table['native_header_paths'][4] == ['Enhanced', 'AUC']
    assert table['native_header_paths'][5] == ['Enhanced', 'gAUC']


def test_centered_parent_label_is_not_mistaken_for_the_middle_leaf_column(tmp_path):
    def draw(page):
        _text(page, 50, 108, 'Table 7 Three metrics')
        for y in (120, 164, 234):
            _rule(page, 50, 500, y)
        _text(page, 58, 136, 'Model')
        _text(page, 280, 136, 'Dataset-A')
        for x, label in ((220, 'MAE'), (300, 'RMSE'), (380, 'AUC')):
            _text(page, x, 157, label)
        for y, name in ((182, 'Base'), (202, 'Ours'), (222, 'Other')):
            for x, value in zip((58, 220, 300, 380), (name, '2.40', '3.20', '0.82')):
                _text(page, x, y, value)
    path, model = _fixture(tmp_path, draw)
    tables, _ = _recover(path, model)
    table = next(t for t in tables if t.get('strategy') == 'native_rules')
    assert table['native_header_paths'][1] == ['Dataset-A', 'MAE']
    assert table['native_header_paths'][2] == ['Dataset-A', 'RMSE']
    assert table['native_header_paths'][3] == ['Dataset-A', 'AUC']


def test_line_cells_containing_several_body_rows_remain_limited(tmp_path):
    def draw(page):
        _simple_table(page)
        for x in (50, 240, 380, 500):
            page.draw_line((x, 120), (x, 214))
    path, model = _fixture(tmp_path, draw)
    tables, _ = _recover(path, model)
    line = next(t for t in tables if t.get('strategy') == 'lines'
                and any('Base' in str(c) and 'Ours' in str(c) for r in t['raw_matrix'] for c in r))
    assert line['native_cells_grounded'] is True
    assert line['reliability'] == 'limited'
    assert 'multiline_cell_relationships_unresolved' in line['limitations']


def test_native_vertical_header_cells_override_broad_horizontal_separator(tmp_path):
    def draw(page):
        _text(page, 50, 108, 'Table 8 Direction-specific results')
        for y in (120, 164, 234):
            _rule(page, 50, 540, y)
        # This rule separates the two header levels, spanning both directions.
        # It does not merge the explicitly divided parent header cells.
        _rule(page, 185, 535, 144)
        for x in (180, 360):
            page.draw_line((x, 124), (x, 141), width=0.6)
        _text(page, 58, 137, 'Model')
        _text(page, 220, 137, 'Left to Right')
        _text(page, 400, 137, 'Right to Left')
        for x, label in ((220, 'MAE'), (300, 'RMSE'), (400, 'MAE'), (480, 'RMSE')):
            _text(page, x, 157, label)
        for y, name in ((182, 'Base'), (202, 'Ours'), (222, 'Other')):
            for x, value in zip((58, 220, 300, 400, 480), (name, '2.40', '3.20', '4.10', '5.20')):
                _text(page, x, y, value)
    path, model = _fixture(tmp_path, draw)
    tables, _ = _recover(path, model)
    table = next(t for t in tables if t.get('strategy') == 'native_rules')
    assert table['native_header_paths'][1] == ['Left to Right', 'MAE']
    assert table['native_header_paths'][2] == ['Left to Right', 'RMSE']
    assert table['native_header_paths'][3] == ['Right to Left', 'MAE']
    assert table['native_header_paths'][4] == ['Right to Left', 'RMSE']
    assert 'ambiguous_native_header_relationships' not in table['limitations']


def test_missing_pdf_returns_legacy_diagnostics(tmp_path):
    tables, diagnostics = _recover(tmp_path / 'absent.pdf', {})
    assert tables == []
    assert diagnostics == {'version': 'native-control/1', 'attempted_pages': 0,
                           'successes': 0, 'failures': [{'reason': 'pdf_source_unavailable'}]}


@pytest.mark.skipif(not os.environ.get('NUMERIC_NATIVE_TABLE_MANIFEST'),
                    reason='private original-PDF manifest is supplied only in offline evaluation')
def test_original_paper_native_tables_are_read_only_and_keep_target_relations():
    manifest = json.loads(Path(os.environ['NUMERIC_NATIVE_TABLE_MANIFEST']).read_text(encoding='utf-8'))
    for case in manifest:
        path = Path(case['pdf_path'])
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        assert before == case['sha256']
        tables, _ = _recover(path, case['model'])
        for target in case['targets']:
            candidates = [t for t in tables if t['page'] == target['page']]
            assert any(all(any(value in str(cell) for cell in row) for value in target['row'])
                       for t in candidates for row in t['matrix']), target
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before
