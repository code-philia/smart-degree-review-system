"""Numeric-only regressions from native thesis line geometry (no PDF outline)."""
import copy
import pytest
from numeric_navigation import attach_navigation, navigation_model


def native_ir(monkeypatch, rows):
    # Tuples: page, native text, x0, y0, font size, x1, font.
    import pymupdf
    class Doc:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get_toc(self, **kwargs): return []
    monkeypatch.setattr(pymupdf, 'open', lambda *args: Doc())
    pages, nodes = {}, [{'id': 'body', 'kind': 'Body', 'children': [], 'attrs': {}}]
    for i, (page, text, x, y, size, right, font) in enumerate(rows):
        lid, nid, sid = f'p{page}-l{i}', f'h{i}', f's{i}'
        box = [x, y, right, y+size]
        line = {'id': lid, 'text': text, 'bbox': box, 'font_size': size,
                'chars': [{'text': c, 'size': size, 'font': font} for c in text]}
        pages.setdefault(page, {'page_index': page-1, 'width': 595, 'height': 842, 'lines': []})['lines'].append(line)
        kind = 'Heading' if ('Bold' in font or size >= 14) else 'Paragraph'
        nodes.append({'id': nid, 'kind': kind, 'text': text, 'children': [], 'attrs': {},
                      'provenance': [{'line_id': lid, 'page_index': page-1, 'bbox': box,
                                      'node_text_start': 0, 'node_text_end': len(text)}]})
        if kind == 'Heading':
            nodes.append({'id': sid, 'kind': 'Section', 'children': [nid], 'attrs': {'level': 1}})
            nodes[0]['children'].append(sid)
        else: nodes[0]['children'].append(nid)
    return {'nodes': nodes, 'layout': {'pages': list(pages.values())}}


def row(page, text, x=85, y=125, size=16, right=350, font='FandolHei-Bold'):
    return (page, text, x, y, size, right, font)


def chapters():
    return [row(2, '第1 章', 230, right=278), row(2, '绪论', 294, right=326),
            row(2, '这是一段普通正文，用来说明所采用方法及其具体实验条件。', y=170, size=12, right=524, font='FandolSong-Regular'),
            row(3, '第2 章', 230, right=278), row(3, '融合模型', 294, right=358)]


def test_recovers_same_visual_row_number_and_experiment_title(monkeypatch):
    rows = chapters() + [row(3, '2.1', y=220, size=14, right=103),
                         row(3, '实验评估', 117, y=219, size=14, right=173),
                         row(3, '2.1.1', y=280, size=12, right=115),
                         row(3, 'WDNN 模型训练', 127, y=279, size=12, right=220),
                         row(3, '实验准确率为98.5%。', y=320, size=12, right=240, font='FandolSong-Regular')]
    ir = native_ir(monkeypatch, rows); before = copy.deepcopy(ir)
    attach_navigation('unused.pdf', ir)
    assert 'numeric_navigation' in ir
    sections = ir['numeric_navigation']['sections']
    root = next(s for s in sections if s['title'] == '第2 章 融合模型')
    experiment = next(s for s in sections if s['title'] == '2.1 实验评估')
    nested = next(s for s in sections if s['title'] == '2.1.1 WDNN 模型训练')
    assert experiment['parent_id'] == root['section_id']
    assert nested['parent_id'] == experiment['section_id']
    assert experiment['section_id'] == 's6'  # Preserve the semantic heading's original ID.
    assert ir['nodes'] == before['nodes'] and ir['layout'] == before['layout']
    model = navigation_model(ir)
    assert any('98.5%' in b['text'] and b['section_id'] == nested['section_id'] for b in model['blocks'])


def test_recovers_wrapped_chapter_title_without_absorbing_prose(monkeypatch):
    rows = chapters()[:3] + [row(3, '第2 章', 85, right=133),
                            row(3, '基于大语言模型的Kubernetes 误配置检测与修复方法', 149, right=524),
                            row(3, '设计', 280, y=149, right=312),
                            row(3, '本章对本文提出的方法及其原型实现进行实验评估。', y=195, size=12, right=524, font='FandolSong-Regular')]
    ir = native_ir(monkeypatch, rows); attach_navigation('unused.pdf', ir)
    assert 'numeric_navigation' in ir
    title = ir['numeric_navigation']['sections'][-1]['title']
    assert title.endswith('修复方法 设计') and '本章' not in title


@pytest.mark.parametrize('noise', [
    [row(1, '第1 章 绪论....................................1', y=160, size=16)],
    [row(2, '第1 章', 400, y=74, size=9, right=427, font='FandolSong-Regular'), row(2, '绪论', 436, y=74, size=9, right=454, font='FandolSong-Regular')],
    [row(3, '1515 (1x)', y=350, size=12, right=150), row(3, '547.35 (2.77x)', 220, y=350, size=12, right=310)],
    [row(3, '2.82 倍的性能提升', y=350, size=12, right=280)],
    [row(3, '1', 280, y=350, size=12, right=286), row(3, 'exp(x)', 300, y=350, size=12, right=340)],
    [row(3, '2.1', y=350, size=14, right=103), row(3, 'Accuracy', 117, y=350, size=14, right=180), row(3, '98.5', 300, y=350, size=14, right=330)],
])
def test_ignores_toc_headers_table_cells_formulas_and_decimals(monkeypatch, noise):
    ir = native_ir(monkeypatch, sorted(chapters() + noise, key=lambda r: (r[0], r[3], r[2])))
    attach_navigation('unused.pdf', ir)
    assert 'numeric_navigation' in ir
    assert len(ir['numeric_navigation']['sections']) == 2


def test_ambiguous_number_is_recorded_without_guessing_parent(monkeypatch):
    rows = chapters() + [row(3, '2.1 实验评估', y=220, size=14),
                         row(3, '2.1 另一实验', y=280, size=14),
                         row(3, '2.1.1 设置', y=340, size=12)]
    ir = native_ir(monkeypatch, rows); attach_navigation('unused.pdf', ir)
    assert 'numeric_navigation' in ir
    nav = ir['numeric_navigation']
    assert len(nav['sections']) == 2
    assert nav['unresolved']


def test_no_complete_numbered_chapter_chain_leaves_ir_unchanged(monkeypatch):
    ir = native_ir(monkeypatch, [row(1, '2.82 倍的性能提升', size=16), row(2, '第3章 实验', size=16)])
    original = copy.deepcopy(ir); attach_navigation('unused.pdf', ir)
    assert ir == original


def test_existing_verified_navigation_is_preserved(monkeypatch):
    ir = native_ir(monkeypatch, chapters())
    ir['numeric_navigation'] = {'version': 'verified', 'sections': [{'section_id': 'existing'}]}
    original = copy.deepcopy(ir); attach_navigation('unused.pdf', ir)
    assert ir == original


@pytest.mark.parametrize('number_size,title_size', [(14, 13.16), (12, 11.28)])
def test_native_mixed_latin_and_cjk_font_sizes_preserve_numbered_heading(monkeypatch, number_size, title_size):
    rows = chapters() + [row(3, '2.1', y=220, size=number_size, right=103),
                         row(3, 'Postman 协议概述', 117, y=219, size=title_size, right=240)]
    ir = native_ir(monkeypatch, rows)
    title = next(l for p in ir['layout']['pages'] for l in p['lines'] if l['text'] == 'Postman 协议概述')
    # Native line.font_size is the dominant Latin font, while the same line's
    # CJK characters and its number retain the nominal 12/14 pt heading size.
    title['chars'][-1]['size'] = number_size
    attach_navigation('unused.pdf', ir)
    assert any(s['title'] == '2.1 Postman 协议概述' for s in ir['numeric_navigation']['sections'])



def test_visible_toc_page_without_dot_leaders_cannot_supply_body_chapters(monkeypatch):
    ir = native_ir(monkeypatch, [row(1, '目录'), row(1, '第1章 绪论', y=180), row(1, '第2章 实验评估', y=240)])
    original = copy.deepcopy(ir); attach_navigation('unused.pdf', ir)
    assert ir == original


def test_compact_table_numeric_tail_is_not_a_numbered_subsection(monkeypatch):
    ir = native_ir(monkeypatch, chapters() + [row(3, '2.1', y=220, size=14, right=103),
                                             row(3, 'Accuracy', 117, y=220, size=14, right=180),
                                             row(3, '98.5', 190, y=220, size=14, right=230)])
    attach_navigation('unused.pdf', ir)
    assert len(ir['numeric_navigation']['sections']) == 2



@pytest.mark.parametrize('role', ['running_header', 'running_footer', 'page_number'])
def test_confirmed_page_furniture_cannot_supply_native_section(monkeypatch, role):
    ir = native_ir(monkeypatch, chapters() + [row(4, '2.1 实验评估', y=92, size=12)])
    node = next(n for n in ir['nodes'] if n.get('text') == '2.1 实验评估')
    node['kind'] = 'UnknownBlock'; node['attrs']['role'] = role
    attach_navigation('unused.pdf', ir)
    assert len(ir['numeric_navigation']['sections']) == 2



def test_same_page_back_matter_boundary_cannot_supply_numeric_evidence(monkeypatch):
    ir = native_ir(monkeypatch, chapters() + [row(3, '方法准确率为98.5%。', y=300, size=12, font='FandolSong-Regular'),
                                             row(3, '参考文献', y=350),
                                             row(3, '其他论文报告准确率为99.9%。', y=400, size=12, font='FandolSong-Regular')])
    attach_navigation('unused.pdf', ir)
    text = '\n'.join(b['text'] for b in navigation_model(ir)['blocks'])
    assert '98.5%' in text and '99.9%' not in text



def test_number_prefix_cannot_reopen_a_closed_native_chapter(monkeypatch):
    ir = native_ir(monkeypatch, chapters() + [row(2, '1.1 研究背景', y=220, size=14),
                                             row(3, '1.2 旧章编号示例', y=220, size=14)])
    attach_navigation('unused.pdf', ir)
    nav = ir['numeric_navigation']
    assert not any(s['title'].startswith('1.2') for s in nav['sections'])
    assert any(s['title'].startswith('1.2') for s in nav['unresolved'])
