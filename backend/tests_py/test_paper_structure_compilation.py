import pymupdf
import pytest
from paper_compiler.frontend import build_paper
from paper_compiler.document_admission import assess_pdf

PROSE = '本文提出软件分析方法，比较相关研究并通过实验验证算法的有效性。' * 12
HEADINGS = ['博士学位论文', '摘要', 'Abstract', '关键词：软件；分析；检测', '目录',
            '第一章 绪论', '第二章 方法研究', '第三章 实验评估', '第四章 结论', '参考文献']


def thesis(tmp_path, missing=None, appendix=None):
    path = tmp_path / 'paper.pdf'
    with pymupdf.open() as doc:
        for heading in HEADINGS:
            if heading == missing:
                continue
            page = doc.new_page()
            page.insert_text((50, 70), heading, fontname='china-s', fontsize=16)
            page.insert_textbox((50, 110, 550, 750), PROSE, fontname='china-s', fontsize=11)
        if appendix:
            page = doc.new_page()
            page.insert_text((50, 70), appendix, fontname='china-s')
        doc.save(path)
    return path


@pytest.mark.parametrize('heading', ['摘要', 'Abstract', '关键词：软件；分析；检测', '目录',
                                     '第一章 绪论', '第四章 结论', '参考文献'])
def test_missing_core_section_is_a_compilation_failure_not_a_non_paper(tmp_path, heading):
    path = thesis(tmp_path, missing=heading)
    assessment = assess_pdf(path)
    assert assessment['status'] == 'rejected'
    assert assessment['reason_code'] == 'paper_structure_incomplete'
    assert assessment['missing_sections']
    with pytest.raises(ValueError, match='编译|结构'):
        build_paper(path)


def test_missing_core_section_can_build_only_with_explicit_partial_opt_in(tmp_path):
    path = thesis(tmp_path, missing='参考文献')
    ir = build_paper(path, include_citations=False, allow_incomplete_structure=True)
    admission = ir['metadata']['document_admission']
    assert admission['status'] == 'accepted'
    assert admission['stage'] == 'partial'
    assert admission['reason_code'] == 'paper_structure_incomplete'
    assert admission['structure']['missing_sections'] == ['参考文献']


def test_full_core_without_declarations_authorization_or_standard_cover_compiles(tmp_path):
    path = thesis(tmp_path, missing='博士学位论文')
    assert assess_pdf(path)['status'] == 'accepted'
    assert build_paper(path)['nodes'][0]['kind'] == 'Paper'


def test_omitted_body_chapters_fail_compilation(tmp_path):
    path = tmp_path / 'no-body.pdf'
    with pymupdf.open(thesis(tmp_path)) as doc:
        doc.delete_pages([6, 7])
        doc.save(path)
    assert '主体' in assess_pdf(path)['missing_sections']


def test_contents_entries_do_not_supply_missing_actual_chapters(tmp_path):
    path = thesis(tmp_path, missing='第四章 结论')
    with pymupdf.open(path) as doc:
        # A ToC reference to a chapter is not the actual chapter.
        doc[4].insert_text((50, 700), '第四章 结论 .......... 40', fontname='china-s')
        doc.save(tmp_path / 'toc-only.pdf')
    assert '结论' in assess_pdf(tmp_path / 'toc-only.pdf')['missing_sections']


def test_numbered_bibliography_cannot_supply_a_missing_body(tmp_path):
    path = tmp_path / 'references-only.pdf'
    with pymupdf.open(thesis(tmp_path)) as doc:
        doc.delete_pages([6, 7])
        doc[-1].insert_text((50, 650), '1. Smith, A practical study of software analysis, 2025.')
        doc.save(path)
    assert '主体' in assess_pdf(path)['missing_sections']


def test_abstract_names_in_contents_do_not_supply_missing_abstracts(tmp_path):
    path = tmp_path / 'contents-abstracts.pdf'
    with pymupdf.open(thesis(tmp_path)) as doc:
        doc[4].insert_text((50, 650), '摘要', fontname='china-s')
        doc[4].insert_text((50, 700), 'Abstract')
        doc.delete_pages([1, 2])
        doc.save(path)
    assessment = assess_pdf(path)
    assert set(assessment['missing_sections']) >= {'摘要', '英文摘要'}


def test_missing_cover_and_contents_cannot_downgrade_a_thesis_to_article(tmp_path):
    path = tmp_path / 'no-cover-or-contents.pdf'
    with pymupdf.open(thesis(tmp_path)) as doc:
        doc.delete_pages([0, 2, 4])
        doc.save(path)
    assessment = assess_pdf(path)
    assert assessment['profile'] == 'chinese-thesis'
    assert set(assessment['missing_sections']) >= {'目录', '英文摘要'}


def test_article_contents_does_not_make_it_a_thesis():
    from paper_compiler.document_admission import assess_document_pages
    pages = [{'lines': [{'text': text} for text in rows]} for rows in [
        ['A Study of Software Analysis', 'Abstract', 'We propose and evaluate an analysis method. ' * 80],
        ['Contents'], ['1 Introduction'], ['2 Methods'], ['3 Conclusion'], ['References']]]
    assessment = assess_document_pages(pages)
    assert assessment['status'] == 'accepted'
    assert assessment['structure']['profile'] == 'research-article'


@pytest.mark.parametrize('label', ['1.1 研究背景', '2. 本文主要贡献'])
def test_intro_subsections_and_lists_do_not_supply_main_body(tmp_path, label):
    path = tmp_path / 'intro-only.pdf'
    with pymupdf.open(thesis(tmp_path)) as doc:
        doc[5].insert_text((50, 650), label, fontname='china-s', fontsize=11)
        doc.delete_pages([6, 7])
        doc.save(path)
    assert '主体' in assess_pdf(path)['missing_sections']


@pytest.mark.parametrize('label', ['2. We release an open source dataset for future research.', '2. Contributions'])
def test_article_intro_list_is_not_a_peer_body_heading(tmp_path, label):
    path = tmp_path / 'article-intro-list.pdf'
    with pymupdf.open() as doc:
        for heading in ['Abstract', '1 Introduction', '3 Conclusion', 'References']:
            page = doc.new_page()
            page.insert_text((50, 70), heading, fontsize=16)
            page.insert_textbox((50, 110, 550, 600), 'We propose a software analysis algorithm and discuss prior research. ' * 30, fontsize=10)
            if heading == '1 Introduction':
                page.insert_text((50, 650), label, fontsize=10)
        doc.save(path)
    assert '主体' in assess_pdf(path)['missing_sections']


def test_mixed_font_heading_agrees_with_public_builder(tmp_path):
    path = tmp_path / 'mixed-font.pdf'
    with pymupdf.open() as doc:
        for heading in ['Abstract', 'Introduction', '2 Methods', '3 Conclusion', 'References']:
            page = doc.new_page()
            if heading == 'Introduction':
                page.insert_text((50, 70), '1 ', fontsize=20)
                page.insert_text((70, 70), heading, fontsize=16)
            else:
                page.insert_text((50, 70), heading, fontsize=16)
            page.insert_textbox((50, 110, 550, 750), 'We evaluate a software analysis method and compare the experimental results. ' * 30, fontsize=10)
        doc.save(path)
    assert assess_pdf(path)['status'] == 'accepted'
    assert build_paper(path)['nodes'][0]['kind'] == 'Paper'


def test_dispatch_proof_requires_completed_ir_construction(tmp_path, monkeypatch):
    from scripts.check_paper_document import check_document
    import paper_compiler.frontend as frontend
    path = thesis(tmp_path)
    assert check_document(path)['compiled'] is True
    def broken_ir(*args, **kwargs):
        raise ValueError('contract validation failed')
    monkeypatch.setattr(frontend, '_build_source_tree', broken_ir)
    failure = check_document(path)
    assert failure['status'] == 'rejected'
    assert failure['compiled'] is False
    assert failure['reason_code'] == 'paper_model_compile_failed'


def test_missing_core_section_never_constructs_a_typed_paper(tmp_path, monkeypatch):
    import paper_compiler.frontend as frontend
    called = []
    monkeypatch.setattr(frontend, '_build_source_tree', lambda *args, **kwargs: called.append(True))
    with pytest.raises(ValueError, match='编译'):
        frontend.build_paper(thesis(tmp_path, missing='第四章 结论'))
    assert called == []


def mislabeled_abstract_thesis(tmp_path):
    # The reported PDF has two separate abstract pages both titled 摘要.
    # Chapter existence depends on its bounded prose, not the title language.
    path = tmp_path / 'mislabeled-english-abstract.pdf'
    with pymupdf.open(thesis(tmp_path)) as doc:
        doc.delete_page(2)
        page = doc.new_page(pno=2)
        page.insert_text((50, 70), '摘 要', fontname='china-s', fontsize=16)
        page.insert_textbox((50, 110, 550, 600),
                            'We propose a collaborative software analysis method and evaluate its effectiveness. ' * 12,
                            fontsize=11)
        page.insert_text((50, 650), 'Keywords: software; analysis; detection', fontsize=11)
        doc[1].insert_text((50, 650), '关键词：软件；分析；检测', fontname='china-s', fontsize=11)
        doc.save(path)
    return path


def test_english_abstract_with_chinese_title_still_compiles(tmp_path):
    path = mislabeled_abstract_thesis(tmp_path)
    assert assess_pdf(path)['status'] == 'accepted'
    ir = build_paper(path, include_citations=False)
    from paper_compiler.local_checks import core_parts
    assert core_parts(ir)['英文摘要'] is True
    from scripts.paper_model_bilingual_rules import extract_bilingual_facts
    facts = extract_bilingual_facts(ir)
    assert 'We propose a collaborative software analysis method' in facts['english_abstract']
    assert facts['locations']['english_abstract']['page_number'] == 3
    assert facts['english_keywords']['values'] == ['software', 'analysis', 'detection']
    from scripts.check_paper_document import check_document
    assert check_document(path)['compiled'] is True


def test_deleted_english_abstract_is_not_restored_from_original_layout(tmp_path):
    from paper_compiler.local_checks import core_parts, detect_ir
    ir = build_paper(mislabeled_abstract_thesis(tmp_path), include_citations=False)
    removed = {node['id'] for node in ir['nodes']
               if any(span.get('page_index') == 2 for span in node['provenance'])}
    ir['nodes'] = [node for node in ir['nodes'] if node['id'] not in removed]
    for node in ir['nodes']:
        node['children'] = [child for child in node['children'] if child not in removed]
    assert core_parts(ir)['英文摘要'] is False
    assert '英文摘要' in [finding['token'] for finding in detect_ir(ir, [34])['34']['findings']]


@pytest.mark.parametrize('marker_y', [620, 700])
def test_preface_prose_before_abstract_marker_is_not_an_abstract(tmp_path, marker_y):
    path = tmp_path / 'preface-is-not-abstract.pdf'
    with pymupdf.open(thesis(tmp_path)) as doc:
        doc.delete_page(2)
        page = doc.new_page(pno=2)
        page.insert_text((50, 70), 'Dedication', fontsize=16)
        page.insert_textbox((50, 110, 550, 550),
                            'We thank our colleagues for their collaboration and helpful discussions about this project. ' * 10,
                            fontsize=11)
        page.insert_text((50, marker_y), '摘要', fontname='china-s', fontsize=16)
        page.insert_text((50, 650), 'Keywords: software; project', fontsize=11)
        doc[1].insert_text((50, 650), '关键词：软件；分析', fontname='china-s')
        doc.save(path)
    assert '英文摘要' in assess_pdf(path)['missing_sections']


@pytest.mark.parametrize('placement', ['body', 'contents', 'cover'])
def test_english_text_outside_abstract_cannot_supply_missing_english_abstract(tmp_path, placement):
    path = tmp_path / 'english-outside-abstract.pdf'
    with pymupdf.open(thesis(tmp_path, missing='Abstract')) as doc:
        page = doc[{'body': 4, 'contents': 3, 'cover': 0}[placement]]
        if placement != 'cover':
            page.insert_text((50, 500), '摘 要', fontname='china-s')
        page.insert_textbox((50, 520, 550, 700),
                            'We propose and evaluate a software analysis method using experimental data. ' * 8,
                            fontsize=9)
        page.insert_text((50, 730), 'Keywords: software; analysis', fontsize=9)
        doc[1].insert_text((50, 650), '关键词：软件；分析；检测', fontname='china-s')
        doc.save(path)
    assert '英文摘要' in assess_pdf(path)['missing_sections']


def test_intro_diagram_conclusion_label_does_not_end_body_scope(tmp_path):
    path = tmp_path / 'diagram-label-before-body.pdf'
    with pymupdf.open(thesis(tmp_path)) as doc:
        doc[5].insert_text((100, 400), '研究结论', fontname='china-s', fontsize=9)
        doc.save(path)
    assert assess_pdf(path)['status'] == 'accepted'
    assert build_paper(path, include_citations=False)['nodes'][0]['kind'] == 'Paper'


def test_intro_diagram_label_cannot_supply_missing_real_conclusion(tmp_path):
    path = tmp_path / 'diagram-only-conclusion.pdf'
    with pymupdf.open(thesis(tmp_path, missing='第四章 结论')) as doc:
        doc[5].insert_text((100, 400), '研究结论', fontname='china-s', fontsize=9)
        doc.save(path)
    assessment = assess_pdf(path)
    assert assessment['status'] == 'rejected'
    assert '结论' in assessment['missing_sections']
    assert '主体' not in assessment['missing_sections']


def test_intro_summary_subsection_cannot_replace_final_conclusion(tmp_path):
    path = tmp_path / 'intro-summary-subsection.pdf'
    with pymupdf.open(thesis(tmp_path, missing='第四章 结论')) as doc:
        doc[5].insert_text((50, 400), '1.5 总结', fontname='china-s', fontsize=16)
        doc.save(path)
    assert '结论' in assess_pdf(path)['missing_sections']
