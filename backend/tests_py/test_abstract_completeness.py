"""Native abstract grammar: existence is different from structural completeness."""
import pytest
from paper_compiler.document_admission import assess_document_pages, assess_pdf
from paper_compiler.frontend import build_paper

ZH = '本文研究软件分析方法，并验证其有效性。'
EN = 'We evaluate a software analysis method.'


def page(*texts):
    return {'lines': [{'text': text} for text in texts]}


def paper(zh=None, en=None, article=False):
    if article:
        return [page('A Study of Software Analysis', 'Abstract', EN),
                page('1 Introduction', EN * 30), page('2 Methods', EN),
                page('3 Conclusion', EN), page('References')]
    return [page('博士学位论文', ZH * 20),
            *(zh if zh is not None else [page('摘要', ZH, '关键词：软件；分析')]),
            *(en if en is not None else [page('Abstract', EN, 'Keywords: software; analysis')]),
            page('目录'), page('第一章 绪论', ZH), page('第二章 方法研究', ZH),
            page('第三章 结论', ZH), page('参考文献')]


@pytest.mark.parametrize('part,kw,label', [('摘要', 'zh', '中文摘要'), ('英文摘要', 'en', '英文摘要（Abstract）')])
def test_partial_abstract_is_incomplete_not_missing(part, kw, label):
    result = assess_document_pages(paper(**{kw: [page('摘要' if kw == 'zh' else 'Abstract', ZH if kw == 'zh' else EN)]}))
    assert result['status'] == 'rejected'
    assert part in result['incomplete_sections']
    assert part not in result['missing_sections']
    assert label + '不完整' in result['reason']
    assert '缺少' + label not in result['reason']
    assert '关键词' in result['reason']


@pytest.mark.parametrize('part,kw,label', [('摘要', 'zh', '中文摘要'), ('英文摘要', 'en', '英文摘要（Abstract）')])
def test_absent_abstract_is_missing_not_incomplete(part, kw, label):
    result = assess_document_pages(paper(**{kw: []}))
    assert part in result['missing_sections']
    assert part not in result.get('incomplete_sections', [])
    assert '缺少' + label in result['reason']
    assert label + '不完整' not in result['reason']


def test_missing_conclusion_has_a_specific_failure_reason():
    pages = [item for item in paper() if item['lines'][0]['text'] != '第三章 结论']
    result = assess_document_pages(pages)
    assert result['status'] == 'rejected'
    assert result['missing_sections'] == ['结论']
    assert '缺少结论' in result['reason']


@pytest.mark.parametrize('texts', [('摘要',), ('摘要', '关键词：软件'), ('摘要', ZH, '关键词：')])
def test_heading_or_empty_keyword_list_cannot_compile(texts):
    result = assess_document_pages(paper(zh=[page(*texts)]))
    assert result['status'] == 'rejected'
    assert '摘要' in result['incomplete_sections']


@pytest.mark.parametrize('label', ['关键词：软件', '关 键 词 ： 软件', '关键字 软件', '关键词\n软件'])
def test_short_complete_abstract_and_keyword_variants_compile(label):
    result = assess_document_pages(paper(zh=[page('摘 要', ZH, *label.split('\n'))]))
    assert result['status'] == 'accepted'
    assert result['structure']['incomplete_sections'] == []


@pytest.mark.parametrize('label', ['Keywords: software', 'KEY WORDS software', 'Index Terms—software', 'Key words\nsoftware'])
def test_english_keywords_and_continuation_pages_compile(label):
    result = assess_document_pages(paper(en=[page('Abstract', EN), page(EN, *label.split('\n'))]))
    assert result['status'] == 'accepted'


def test_other_abstract_body_and_appendix_cannot_supply_a_keyword_closing():
    pages = paper(zh=[page('摘要', ZH)])
    pages.extend([page('附录', '关键词：软件')])
    result = assess_document_pages(pages)
    assert result['status'] == 'rejected'
    assert result['incomplete_sections'] == ['摘要']


def test_chinese_keyword_page_cannot_close_an_english_abstract():
    result = assess_document_pages(paper(en=[page('Abstract', EN), page('关键词：软件；分析')]))
    assert result['status'] == 'rejected'
    assert result['incomplete_sections'] == ['英文摘要']


def test_article_has_no_thesis_keyword_or_minimum_length_requirement():
    result = assess_document_pages(paper(article=True))
    assert result['status'] == 'accepted'


def test_article_heading_without_body_is_incomplete():
    pages = paper(article=True)
    pages[0] = page('A Study of Software Analysis', 'Abstract')
    result = assess_document_pages(pages)
    assert result['status'] == 'rejected'
    assert result['incomplete_sections'] == ['摘要']


def test_both_chinese_titles_short_bilingual_bodies_compile():
    result = assess_document_pages(paper(en=[page('摘要', EN, 'Keywords: software')]))
    assert result['status'] == 'accepted'


@pytest.mark.parametrize('kwargs', [
    {'en': [page('摘要', EN, '关键词：software; analysis')]},
    {'zh': [page('摘要', ZH, 'Keywords: 软件；分析')]},
])
def test_keyword_label_language_alone_does_not_reject_a_complete_abstract(kwargs):
    assert assess_document_pages(paper(**kwargs))['status'] == 'accepted'


def test_repeated_small_abstract_running_header_is_not_a_new_section():
    first = page('Abstract', EN)
    first['lines'][0].update(font_size=16, bbox=[100, 70, 200, 90])
    continued = page('Abstract', EN, 'Keywords: software', 'IV')
    continued['height'] = 842
    continued['lines'][0].update(font_size=9, bbox=[100, 30, 180, 40])
    result = assess_document_pages(paper(en=[first, continued]))
    assert result['status'] == 'accepted'


def test_equal_size_running_header_preserves_an_abstract_continuation():
    first = page('Abstract', EN)
    first['lines'][0].update(font_size=12, bbox=[100, 70, 200, 90])
    continued = page('Abstract', 'Keywords: software', 'IV')
    continued['height'] = 842
    continued['lines'][0].update(font_size=12, bbox=[100, 30, 180, 40])
    result = assess_document_pages(paper(en=[first, continued]))
    assert result['status'] == 'accepted'


def test_keyword_label_split_into_native_glyphs_is_readable():
    zh = page('摘要', ZH)
    for index, char in enumerate('关键词：软件'):
        zh['lines'].append({'text': char, 'bbox': [50 + index * 12, 300, 62 + index * 12, 312], 'font_size': 12})
    assert assess_document_pages(paper(zh=[zh]))['status'] == 'accepted'


def test_english_keyword_label_split_across_native_lines_is_readable():
    assert assess_document_pages(paper(en=[page('Abstract', EN, 'Key', 'words:', 'software')]))['status'] == 'accepted'


def test_inline_article_abstract_without_a_dash_or_colon_compiles():
    pages = paper(article=True)
    pages[0] = page('A Study of Software Analysis', 'Abstract ' + EN)
    assert assess_document_pages(pages)['status'] == 'accepted'


def test_chapter_organization_prose_inside_abstract_is_not_a_boundary():
    zh = page('摘要', ZH, '第二章介绍研究方法，第三章分析实验结果。', '关键词：软件；分析')
    assert assess_document_pages(paper(zh=[zh]))['status'] == 'accepted'


@pytest.mark.parametrize('text', ['Chapter 2 describes the proposed research method', '第二章 介绍本文提出的方法'])
def test_unpunctuated_chapter_description_remains_abstract_prose(text):
    en = page('Abstract', EN, text, 'Keywords: software; analysis')
    en['lines'][0]['font_size'] = 16
    for line in en['lines'][1:]:
        line['font_size'] = 11
    assert assess_document_pages(paper(en=[en]))['status'] == 'accepted'


def test_partially_split_keyword_label_joins_its_native_baseline():
    zh = page('摘要', ZH)
    for text, box in [('关', [50, 300, 62, 312]), ('键', [62, 300, 74, 312]),
                      ('词：软件；分析', [74, 300, 200, 312])]:
        zh['lines'].append({'text': text, 'bbox': box, 'font_size': 12})
    assert assess_document_pages(paper(zh=[zh]))['status'] == 'accepted'


def test_running_furniture_cannot_fill_an_empty_keyword_list():
    continuation = page('AI Research Group', 'IV')
    continuation['height'] = 842
    continuation['lines'][0].update(font_size=9, bbox=[50, 20, 300, 32])
    result = assess_document_pages(paper(en=[page('Abstract', EN, 'Keywords:'), continuation]))
    assert result['status'] == 'rejected'
    assert result['incomplete_sections'] == ['英文摘要']


def test_running_furniture_cannot_invent_an_absent_abstract_body():
    pages = paper(article=True)
    pages[0] = page('A Study of Software Analysis', 'Abstract')
    footer = {'text': 'AI Research Group', 'bbox': [50, 810, 300, 822], 'font_size': 9}
    pages[0].update(height=842)
    pages[0]['lines'].append(footer)
    result = assess_document_pages(pages)
    assert result['status'] == 'rejected'
    assert result['incomplete_sections'] == ['摘要']


def test_incomplete_native_pdf_never_constructs_a_paper(tmp_path, monkeypatch):
    import pymupdf
    import paper_compiler.frontend as frontend
    source = tmp_path / 'partial.pdf'
    with pymupdf.open() as doc:
        for item in paper(en=[page('Abstract', EN)]):
            native = doc.new_page()
            for index, line in enumerate(item['lines']):
                native.insert_text((50, 70 + index * 30), line['text'], fontname='china-s', fontsize=12)
        doc.save(source)
    called = []
    monkeypatch.setattr(frontend, '_build_source_tree', lambda *args, **kwargs: called.append(True))
    with pytest.raises(ValueError, match='英文摘要.*不完整|不完整.*英文摘要'):
        build_paper(source)
    assert called == []
    assert assess_pdf(source)['incomplete_sections'] == ['英文摘要']


def test_r6_checks_current_ir_and_distinguishes_incomplete_from_missing(tmp_path):
    from test_paper_structure_compilation import thesis
    from paper_compiler.local_checks import detect_ir
    ir = build_paper(thesis(tmp_path), include_citations=False)
    removed = {node['id'] for node in ir['nodes'] if 'Keywords:' in (node['text'] or '')}
    assert removed
    ir['nodes'] = [node for node in ir['nodes'] if node['id'] not in removed]
    for node in ir['nodes']:
        node['children'] = [child for child in node['children'] if child not in removed]
    finding = next(item for item in detect_ir(ir, [34])['34']['findings'] if item['token'] == '英文摘要')
    assert '英文摘要（Abstract）不完整' in finding['message']
    assert '关键词' in finding['message']
