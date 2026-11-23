"""Native caption rows may be wider than the ruled result table below them."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import numeric_native_tables as native


def _block(identity, text, box, kind='Paragraph'):
    return {'block_id': identity + ':p1', 'source_node_id': identity,
            'section_id': 'experiment', 'page': 1, 'text': text,
            'block_type': kind, 'provenance': [{'bbox': box}]}


def _case():
    label = _block('caption', 'Table 3.1', [110, 100, 150, 112], 'Caption')
    title = 'Protocol comparison (relative to baseline)'
    mixed = _block('title', title + '\nProtocol', [160, 100, 490, 112])
    mixed['provenance'] = [
        {'bbox': [160, 100, 490, 112], 'node_text_start': 0, 'node_text_end': len(title)},
        {'bbox': [195, 124, 235, 136], 'node_text_start': len(title) + 1,
         'node_text_end': len(mixed['text'])},
    ]
    fragments = [{'text': label['text'], 'bbox': [110, 100, 150, 112]},
                 {'text': title, 'bbox': [160, 100, 490, 112]},
                 {'text': 'Protocol', 'bbox': [195, 124, 235, 136]}]
    table = {'page': 1, 'bbox': [175, 120, 425, 175], 'limitations': [],
             'reliability': 'reliable'}
    return table, {'blocks': [label, mixed]}, fragments


def test_native_binding_accepts_centered_caption_row_wider_than_table():
    table, model, fragments = _case()
    before = deepcopy(model)
    native._bind_source(table, model, fragments)
    assert table['source_node_ids'] == ['caption']
    assert table['section_id'] == 'experiment'
    assert table['caption'] == 'Table 3.1'
    assert table['limitations'] == []
    assert model == before


def test_caption_context_projects_wide_title_without_table_header():
    table, model, _ = _case()
    table.update(source_node_ids=['caption'], caption='Table 3.1', section_id='experiment')
    before = deepcopy(model)
    context = native.native_caption_context(table, model)
    assert [b['text'] for b in context] == [
        'Table 3.1', 'Protocol comparison (relative to baseline)']
    assert context[1]['source_node_id'] == 'title'
    assert context[1]['provenance'] == model['blocks'][1]['provenance'][:1]
    assert model == before


@pytest.mark.parametrize('text,box', [
    ('Unrelated column', [190, 100, 490, 112]),
    ('Other table title', [160, 100, 230, 112]),
    ('Table 9.2', [160, 100, 490, 112]),
    ('Other paragraph', [160, 140, 490, 152]),
])
def test_native_binding_does_not_extend_caption_across_unrelated_geometry(text, box):
    table, model, fragments = _case()
    model['blocks'] = model['blocks'][:1]
    fragments[1:] = [{'text': text, 'bbox': box}]
    native._bind_source(table, model, fragments)
    assert table['source_node_ids'] == []
    assert table['section_id'] is None
    assert 'no_paper_model_source_binding' in table['limitations']


def test_native_binding_stops_at_nearer_wide_caption_missing_from_ir():
    table, model, fragments = _case()
    table['bbox'] = [175, 145, 425, 200]
    model['blocks'] = model['blocks'][:1]
    fragments = fragments[:2] + [
        {'text': 'Table 3.2', 'bbox': [110, 125, 150, 137]},
        {'text': 'A different comparison', 'bbox': [160, 125, 490, 137]},
    ]
    native._bind_source(table, model, fragments)
    assert table['source_node_ids'] == []
    assert table['section_id'] is None
    assert table['reliability'] == 'limited'
    assert 'no_paper_model_source_binding' in table['limitations']


@pytest.mark.parametrize('nearer_label,blocked', [('Table 3.2', True), ('Table 3.1', False)])
def test_caption_context_respects_intervening_wide_caption_identity(nearer_label, blocked):
    table, model, _ = _case()
    table.update(bbox=[175, 145, 425, 200], source_node_ids=['caption'],
                 caption='Table 3.1', section_id='experiment')
    model['blocks'] += [
        _block('nearer-caption', nearer_label, [110, 125, 150, 137], 'Caption'),
        _block('nearer-title', 'A different comparison', [160, 125, 490, 137]),
    ]
    context = native.native_caption_context(table, model)
    if blocked:
        assert context == []
    else:
        assert [b['source_node_id'] for b in context] == ['caption', 'title']


def _single_metric_case():
    box = [175, 120, 425, 240]
    rules = [[175, y, 425] for y in (120, 140, 240)]
    fragments = [{'text': 'Operation', 'bbox': [185, 125, 240, 137]},
                 {'text': 'Latency (ms)', 'bbox': [340, 125, 410, 137]}]
    for y, label, value in ((152, 'Derive', '3.84'), (172, 'Update', '4.17'),
                             (192, 'Seal', '3.73')):
        fragments += [{'text': label, 'bbox': [185, y, 235, y + 12]},
                      {'text': value, 'bbox': [355, y, 380, y + 12]}]
    return box, rules, fragments


def test_native_grid_recovers_two_column_single_metric_table():
    box, rules, fragments = _single_metric_case()
    grid = native._native_grid(box, rules, fragments, [], rules)
    assert grid is not None
    proxy, _, paths, spanning, uncertain = grid
    assert proxy.extract() == [['Operation', 'Latency (ms)'], ['Derive', '3.84'],
                               ['Update', '4.17'], ['Seal', '3.73']]
    assert paths == [['Operation'], ['Latency (ms)']]
    assert spanning == []
    assert uncertain is False


@pytest.mark.parametrize('malformation', ['one_row', 'reversed', 'misaligned'])
def test_single_metric_grid_requires_multiple_aligned_label_value_rows(malformation):
    box, rules, fragments = _single_metric_case()
    if malformation == 'one_row':
        fragments = fragments[:4]
    elif malformation == 'reversed':
        for index in (2, 4, 6):
            fragments[index]['text'], fragments[index + 1]['text'] = (
                fragments[index + 1]['text'], fragments[index]['text'])
    else:
        fragments[4]['bbox'] = [270, 172, 320, 184]
    assert native._native_grid(box, rules, fragments, [], rules) is None
