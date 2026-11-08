"""Contents order cannot replace abstract evidence or close a missing tail."""
import pytest
from paper_compiler.document_admission import assess_document_pages
from paper_compiler.structure import abstract_sections, has_bilingual_abstract_bodies
from paper_compiler.local_checks import current_abstract_sections, core_parts
from test_abstract_completeness import paper, page, ZH, EN
from test_fast_local_checks import sample_ir


def contents_first(**kwargs):
    pages = paper(**kwargs)
    contents = next(item for item in pages if item['lines'][0]['text'] == '目录')
    pages.remove(contents)
    pages.insert(1, contents)
    return pages


def test_complete_bilingual_abstracts_after_contents_are_accepted():
    result = assess_document_pages(contents_first())
    assert result['status'] == 'accepted'
    assert result['structure']['missing_sections'] == []
    assert result['structure']['incomplete_sections'] == []


def test_complete_english_abstract_can_follow_contents_after_chinese_abstract():
    pages = paper()
    contents = pages.pop(3)
    pages.insert(2, contents)
    assert assess_document_pages(pages)['status'] == 'accepted'


def test_paired_language_recovery_can_follow_contents():
    pages = contents_first(zh=[page('摘要', ZH * 12, '关键词：软件；分析')],
                           en=[page('摘要', EN * 12, 'Keywords: software; analysis')])
    assert has_bilingual_abstract_bodies(pages) is True


@pytest.mark.parametrize('missing,expected', [('zh', ['摘要']), ('en', ['英文摘要'])])
def test_missing_language_after_contents_is_still_reported(missing, expected):
    result = assess_document_pages(contents_first(**{missing: []}))
    assert result['structure']['missing_sections'] == expected


def test_contents_keywords_cannot_close_a_truncated_abstract():
    pages = paper(zh=[page('摘要', ZH)])
    contents = pages.pop(3)
    pages.insert(2, contents)
    pages.insert(3, page('关键词：软件；分析'))
    sections = abstract_sections(pages, 'chinese-thesis')
    assert sections['摘要']['status'] == 'incomplete'
    assert sections['摘要']['has_keywords'] is False
    assert sections['英文摘要']['status'] == 'complete'


def test_contents_titles_do_not_supply_nonexistent_abstracts():
    pages = contents_first(zh=[], en=[])
    pages[1] = page('目录', '摘要 ........ 1', 'Abstract ........ 2', '第一章 绪论 ........ 3')
    sections = abstract_sections(pages, 'chinese-thesis')
    assert sections == {}


def test_abstract_in_body_or_appendix_cannot_replace_missing_front_matter():
    pages = contents_first(zh=[], en=[])
    pages.extend([page('附录', '摘要', ZH, '关键词：软件；分析'),
                  page('Abstract', EN, 'Keywords: software; analysis')])
    assert abstract_sections(pages, 'chinese-thesis') == {}


def test_current_ir_accepts_contents_before_bilingual_abstracts():
    ir = sample_ir()
    for node in ir['nodes']:
        for span in node['provenance']:
            if span['page_index'] in {2, 3}:
                span['page_index'] = 5 - span['page_index']
    sections = current_abstract_sections(ir)
    assert sections['摘要']['status'] == 'complete'
    assert sections['英文摘要']['status'] == 'complete'
    parts = core_parts(ir)
    assert parts['摘要'] is True
    assert parts['英文摘要'] is True


def test_contents_boundary_cannot_merge_an_earlier_body_with_a_later_empty_abstract():
    pages = [page('摘要', ZH), page('目录'),
             page('摘要', '关键词：软件；分析')]
    pages[2]['lines'][0].update(bbox=[100, 30, 180, 40], font_size=12)
    sections = abstract_sections(pages, 'chinese-thesis')
    assert sections['摘要']['status'] == 'incomplete'


def test_contents_intro_entry_cannot_hide_later_abstract_checks():
    from paper_compiler.local_checks import detect_ir, _body_start_page
    ir = sample_ir()
    for node in ir['nodes']:
        for span in node['provenance']:
            if span['page_index'] in {2, 3}:
                span['page_index'] = 5 - span['page_index']
    template = next(node for node in ir['nodes'] if node['id'] == 'toc')
    import copy
    entry = copy.deepcopy(template)
    entry.update(id='toc-intro-entry', text='第1章 绪论')
    entry['provenance'][0]['bbox'] = [60, 180, 160, 192]
    ir['nodes'].append(entry)
    ir['nodes'][0]['children'].append(entry['id'])
    next(node for node in ir['nodes'] if node['id'] == 'abstract-text')['text'] += '参见图2。'
    assert _body_start_page(ir) == 4
    assert detect_ir(ir, [36])['36']['status'] == 'completed'
    assert any('图2' in finding['message'] for finding in detect_ir(ir, [37])['37']['findings'])


@pytest.mark.parametrize('typed', [False, True])
def test_contents_abstract_entry_cannot_supply_abstract_object_prose(typed):
    import copy
    from paper_compiler.local_checks import detect_ir
    ir = sample_ir()
    toc = next(node for node in ir['nodes'] if node['id'] == 'toc')
    for nid, text, y in [('toc-abstract-entry', '摘要', 140),
                         ('toc-figure-entry', '图2 系统架构 ........ 10', 180)]:
        entry = copy.deepcopy(toc)
        entry.update(id=nid, text=text, kind='Abstract' if typed else 'Paragraph')
        entry['provenance'][0]['bbox'] = [60, y, 220, y + 12]
        ir['nodes'].append(entry)
        ir['nodes'][0]['children'].append(nid)
    assert detect_ir(ir, [37])['37']['findings'] == []
