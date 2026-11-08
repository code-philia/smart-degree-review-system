"""Declaration titles need source geometry and whole-title evidence, not prose mentions."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from paper_compiler.local_checks import core_parts


def paper_ir():
    return {
        'nodes': [{'id': 'paper', 'kind': 'Paper', 'text': None, 'attrs': {},
                   'children': [], 'provenance': []}],
        'layout': {'pages': [{'page_index': index, 'width': 600, 'height': 800}
                             for index in range(3)]},
        'metadata': {},
        'coverage': {'pages': {'status': 'complete'}},
    }


def add_node(ir, text, *, kind='Paragraph', page=0, box=None, parent='paper'):
    node_id = 'node-' + str(len(ir['nodes']))
    box = box or [120, 140, 120 + len(text or '') * 12, 155]
    node = {'id': node_id, 'kind': kind, 'text': text, 'attrs': {}, 'children': [],
            'provenance': [] if text is None else [{
                'kind': 'source', 'source_id': 'pdf', 'page_index': page,
                'bbox': box, 'coordinate_system': 'unrotated_top_left_points',
                'node_text_start': 0, 'node_text_end': len(text),
            }]}
    ir['nodes'].append(node)
    next(node for node in ir['nodes'] if node['id'] == parent)['children'].append(node_id)
    return node_id


def declaration_parts(ir):
    parts = core_parts(ir, abstracts={})
    return {name: parts[name] for name in ('原创性声明', '使用授权说明')}


@pytest.mark.parametrize('title', [
    '原创性声明', '独 创 性 声 明', '学位论文原创性声明',
    '博士学位论文独创性声明', '硕士学位论文原创声明', '学术诚信声明',
])
def test_standalone_originality_titles_in_bare_paragraphs_remain_supported(title):
    ir = paper_ir()
    add_node(ir, title)
    assert declaration_parts(ir) == {'原创性声明': True, '使用授权说明': False}


@pytest.mark.parametrize('title', [
    '使用授权书', '学位论文使用授权说明', '版权授权声明',
    '学位论文版权使用授权书', '学位论文授权使用声明',
    '学位论文使用权限', '博士学位论文使用权限说明', '硕士学位论文使用许可声明',
])
def test_equivalent_standalone_authorization_titles_are_present(title):
    ir = paper_ir()
    add_node(ir, title)
    assert declaration_parts(ir) == {'原创性声明': False, '使用授权说明': True}


def test_combined_originality_and_usage_rights_title_supplies_both_parts():
    ir = paper_ir()
    add_node(ir, '学位论文原创性声明和使用权限', kind='Heading')
    assert declaration_parts(ir) == {'原创性声明': True, '使用授权说明': True}


def add_skewed_originality_title(ir, *, kind='Heading'):
    # The PDF can report rightmost glyphs before middle glyphs in reading order.
    # Different glyph boxes still overlap vertically and form one horizontal title.
    for text, box in [
        ('独', [213, 79, 230, 98]), ('创', [249, 79, 265, 99]),
        ('明', [358, 90, 375, 105]), ('声', [321, 93, 338, 110]),
        ('性', [285, 93.5, 302, 110.5]),
    ]:
        add_node(ir, text, kind=kind, box=box)


@pytest.mark.parametrize('kind', ['Heading', 'Paragraph'])
def test_skewed_split_title_uses_horizontal_glyph_order(kind):
    ir = paper_ir()
    add_skewed_originality_title(ir, kind=kind)
    assert declaration_parts(ir)['原创性声明'] is True


@pytest.mark.parametrize('title', ['学位论文原创性声明', '学位论文版权使用授权书'])
def test_dot_leader_contents_mentions_do_not_supply_a_declaration(title):
    ir = paper_ir()
    add_node(ir, title + ' ............... 154')
    assert declaration_parts(ir) == {'原创性声明': False, '使用授权说明': False}


@pytest.mark.parametrize('kind', ['ToCEntry', 'Paragraph', 'Heading'])
def test_contents_descendants_do_not_supply_declarations_even_without_leaders(kind):
    ir = paper_ir()
    toc_id = add_node(ir, None, kind='ToC')
    add_node(ir, '学位论文原创性声明', kind=kind, parent=toc_id)
    add_node(ir, '学位论文版权使用授权书', kind=kind, parent=toc_id,
             box=[120, 180, 420, 195])
    assert declaration_parts(ir) == {'原创性声明': False, '使用授权说明': False}


@pytest.mark.parametrize('text', [
    '详见学位论文原创性声明和使用授权说明',
    '本章讨论原创性声明与版权授权声明的法律含义',
    '学位论文使用授权书应由作者签署',
    '本人知悉学位论文的使用权限，并将遵守有关规定。',
    '未提供原创性声明',
])
def test_prose_mentions_do_not_supply_declarations(text):
    ir = paper_ir()
    add_node(ir, text)
    assert declaration_parts(ir) == {'原创性声明': False, '使用授权说明': False}


@pytest.mark.parametrize('kind', ['Figure', 'Table', 'Bibliography'])
def test_object_and_bibliography_labels_do_not_supply_a_declaration(kind):
    ir = paper_ir()
    parent_id = add_node(ir, None, kind=kind)
    add_node(ir, '原创性声明', kind='Paragraph', parent=parent_id)
    add_node(ir, '版权使用授权书', kind='Paragraph', parent=parent_id,
             box=[120, 180, 360, 195])
    assert declaration_parts(ir) == {'原创性声明': False, '使用授权说明': False}


@pytest.mark.parametrize('title', ['', '学位论文承诺', '学位论文使用说明', '原创性研究'])
def test_absent_or_unrecognized_titles_remain_missing(title):
    ir = paper_ir()
    if title:
        add_node(ir, title, kind='Heading')
    assert declaration_parts(ir) == {'原创性声明': False, '使用授权说明': False}


def test_vertically_separate_glyphs_do_not_form_a_declaration():
    ir = paper_ir()
    for index, char in enumerate('独创性声明'):
        add_node(ir, char, kind='Heading', box=[120 + index * 35, 140 + index * 24,
                                               136 + index * 35, 156 + index * 24])
    assert declaration_parts(ir)['原创性声明'] is False


def test_distant_columns_do_not_form_a_declaration():
    ir = paper_ir()
    add_node(ir, '独创性', kind='Heading', box=[50, 140, 98, 156])
    add_node(ir, '声明', kind='Heading', box=[400, 140, 432, 156])
    assert declaration_parts(ir)['原创性声明'] is False


def test_glyphs_on_different_pages_do_not_form_a_declaration():
    ir = paper_ir()
    add_node(ir, '独创性', kind='Heading', box=[120, 140, 168, 156])
    add_node(ir, '声明', kind='Heading', page=1, box=[180, 140, 212, 156])
    assert declaration_parts(ir)['原创性声明'] is False


def test_incompatible_glyph_sizes_do_not_form_a_declaration():
    ir = paper_ir()
    add_node(ir, '独创性', kind='Heading', box=[120, 140, 168, 156])
    add_node(ir, '声明', kind='Heading', box=[185, 145, 225, 185])
    assert declaration_parts(ir)['原创性声明'] is False


def test_split_prose_prefix_cannot_be_discarded_to_create_a_title():
    ir = paper_ir()
    add_node(ir, '详见', box=[80, 140, 112, 157])
    add_node(ir, '原创性声明', box=[130, 148, 210, 165])
    assert declaration_parts(ir)['原创性声明'] is False


@pytest.mark.parametrize('skewed', [False, True])
def test_declaration_first_page_is_not_a_title_page(skewed):
    ir = paper_ir()
    if skewed:
        add_skewed_originality_title(ir)
    else:
        add_node(ir, '学位论文使用权限', kind='Heading')
    add_node(ir, '作者签名：', box=[120, 300, 200, 315])
    add_node(ir, '导师签名：', box=[120, 340, 200, 355])
    add_node(ir, '摘要', kind='Heading', page=1)
    assert core_parts(ir, abstracts={})['题名页'] is False


@pytest.mark.parametrize('title,expected', [
    ('独创性说明', {'原创性声明': True, '使用授权说明': False}),
    ('学位论文原创性说明', {'原创性声明': True, '使用授权说明': False}),
    ('研究生学位论文原创性声明', {'原创性声明': True, '使用授权说明': False}),
    ('博士研究生学位论文使用权限', {'原创性声明': False, '使用授权说明': True}),
])
def test_equivalent_statement_and_graduate_degree_titles(title, expected):
    ir = paper_ir()
    add_node(ir, title, kind='Heading')
    assert declaration_parts(ir) == expected


@pytest.mark.parametrize('kind', ['Heading', 'Paragraph'])
@pytest.mark.parametrize('prefix', ['示例大学', '甲地研究院'])
def test_institution_prefixed_display_title_needs_no_subheadings(kind, prefix):
    ir = paper_ir()
    add_node(ir, prefix + '学位论文原创性声明和使用授权说明', kind=kind,
             box=[70, 140, 530, 160])
    assert declaration_parts(ir) == {'原创性声明': True, '使用授权说明': True}


@pytest.mark.parametrize('title', [
    '详见示例大学学位论文原创性声明',
    '未提供示例大学学位论文原创性声明',
    '示例大学学位论文原创性声明应由作者签署',
    '示例大学学位论文原创性声明（未提供）',
])
def test_displayed_institution_prose_or_absence_notice_is_not_a_declaration(title):
    ir = paper_ir()
    add_node(ir, title, kind='Heading', box=[70, 140, 530, 160])
    assert declaration_parts(ir) == {'原创性声明': False, '使用授权说明': False}


def test_left_aligned_body_mention_of_institution_title_is_not_a_declaration():
    ir = paper_ir()
    add_node(ir, '示例大学学位论文原创性声明', box=[20, 140, 220, 152])
    assert declaration_parts(ir) == {'原创性声明': False, '使用授权说明': False}


@pytest.mark.parametrize('title,expected', [
    ('论文原创性声明', {'原创性声明': True, '使用授权说明': False}),
    ('博士论文独创性声明', {'原创性声明': True, '使用授权说明': False}),
    ('硕士毕业论文原创性声明书', {'原创性声明': True, '使用授权说明': False}),
    ('学位论文使用授权声明书', {'原创性声明': False, '使用授权说明': True}),
    ('原创性声明、使用授权书', {'原创性声明': True, '使用授权说明': True}),
    ('论文独创性声明暨论文使用授权书', {'原创性声明': True, '使用授权说明': True}),
    ('学位论文原创性声明以及使用权限', {'原创性声明': True, '使用授权说明': True}),
    ('示例大学博士论文独创性声明', {'原创性声明': True, '使用授权说明': False}),
])
def test_complete_declaration_title_variants_preserve_existing_aliases(title, expected):
    ir = paper_ir()
    add_node(ir, title, kind='Heading')
    assert declaration_parts(ir) == expected


@pytest.mark.parametrize('kind', ['Heading', 'Paragraph'])
def test_interleaved_native_glyph_baselines_keep_horizontal_title_order(kind):
    ir = paper_ir()
    for index, char in enumerate('独创性声明'):
        x = 120 + index * 35
        y = 140 + (8 if index % 2 else 0)
        add_node(ir, char, kind=kind, box=[x, y, x + 17, y + 17])
    assert declaration_parts(ir)['原创性声明'] is True


@pytest.mark.parametrize('title', [
    '博士论文独创性声明应当由作者签署',
    '未签署论文原创性声明',
    '学位论文使用授权声明书（未提供）',
    '关于论文原创性声明与使用授权书',
])
def test_new_title_variants_do_not_promote_displayed_prose(title):
    ir = paper_ir()
    add_node(ir, title, kind='Heading')
    assert declaration_parts(ir) == {'原创性声明': False, '使用授权说明': False}


def test_declaration_pieces_use_live_ir_text_offsets():
    ir = paper_ir()
    node_id = add_node(ir, '独创性声明\n普通的后续正文。', kind='Heading')
    node = next(node for node in ir['nodes'] if node['id'] == node_id)
    first = dict(node['provenance'][0], node_text_end=5, bbox=[120, 140, 200, 157])
    second = dict(first, node_text_start=6, node_text_end=len(node['text']),
                  bbox=[120, 190, 320, 207])
    node['provenance'] = [first, second]
    assert declaration_parts(ir)['原创性声明'] is True
    ir['layout']['pages'][0]['lines'] = [
        {'id': 'immutable-title', 'text': '独创性声明', 'bbox': [120, 140, 200, 157]},
    ]
    node['text'] = '研究说明。\n普通的后续正文。'
    assert declaration_parts(ir)['原创性声明'] is False


@pytest.mark.parametrize('kind', ['ToC', 'Figure', 'Table', 'Bibliography'])
def test_interleaved_title_glyphs_in_excluded_containers_remain_missing(kind):
    ir = paper_ir()
    parent_id = add_node(ir, None, kind=kind)
    for index, char in enumerate('独创性声明'):
        x = 120 + index * 35
        y = 140 + (8 if index % 2 else 0)
        add_node(ir, char, kind='Heading', parent=parent_id,
                 box=[x, y, x + 17, y + 17])
    assert declaration_parts(ir)['原创性声明'] is False
