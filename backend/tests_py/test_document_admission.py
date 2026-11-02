"""Document identity must be established before constructing a Paper."""
import pymupdf
import pytest

from paper_compiler.frontend import build_paper
from paper_compiler.document_admission import assess_pdf


def pdf_with_text(tmp_path, text, name='upload.pdf', scanned_back=False):
    path = tmp_path / name
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_textbox((45, 40, 550, 780), text, fontsize=10, fontname='china-s')
        if scanned_back:
            pix = page.get_pixmap()
            scan = doc.new_page()
            scan.insert_image(scan.rect, pixmap=pix)
        doc.save(path)
    return path


@pytest.mark.parametrize('title', [
    'CCF博士学位论文激励计划推荐表（单位）',
    '学位论文撰写规范与格式指南',
    '软件系统用户手册',
    '个人简历',
    '增值税电子普通发票',
    '教学课件：软件工程',
])
def test_non_paper_never_becomes_a_paper(tmp_path, title):
    path = pdf_with_text(tmp_path, title + '\n作者姓名\n培养单位\n博士学位论文题目\n填写日期\n推荐意见\n说明材料。' * 2,
                         name='博士学位论文.pdf', scanned_back=True)
    with pytest.raises(ValueError, match='(?i)paper|论文'):
        build_paper(path)


def test_rejection_precedes_optional_model_calls(tmp_path):
    class NoModel:
        def __getattr__(self, name):
            raise AssertionError('A non-paper must not reach model calls')
    path = pdf_with_text(tmp_path, '博士学位论文推荐表\n摘要\n研究成果简介\n参考文献\n[1] A real academic reference, 2024.')
    with pytest.raises(ValueError, match='(?i)paper|论文'):
        build_paper(path, client=NoModel())


@pytest.mark.parametrize('missing', ['摘要', '目录', '参考文献'])
def test_real_thesis_missing_a_required_section_fails_structure_compilation(tmp_path, missing):
    prose = '本文研究软件系统的检测方法，分析已有方法的不足，提出改进算法，并通过实验验证有效性。' * 8
    sections = ['博士学位论文', '摘要', 'Abstract', '关键词：软件；检测；研究', prose, '目录', '第一章 绪论', prose,
                '第二章 方法研究', prose, '第三章 实验评估', prose, '第四章 结论', prose,
                '参考文献', '[1] Research on software testing, 2024.']
    path = pdf_with_text(tmp_path, '\n'.join(row for row in sections if row != missing))
    assessment = assess_pdf(path)
    assert assessment['reason_code'] == 'paper_structure_incomplete'
    assert missing in assessment['missing_sections']
    with pytest.raises(ValueError, match='编译'):
        build_paper(path)


@pytest.mark.parametrize('abstract', [True, False])
def test_english_research_article_without_thesis_cover(tmp_path, abstract):
    prose = 'We study a method for document analysis and evaluate the proposed algorithm against a baseline. ' * 22
    text = '\n'.join(['A Study of Document Analysis', 'Journal of Software, doi:10.1234/test',
                      'Abstract' if abstract else '', prose, '1 Introduction', prose,
                      '2 Methods', prose, '3 Results', prose, '4 Conclusion', prose,
                      'References', '[1] Author. Previous research, 2024.'])
    # Separate pages keep this a readable miniature article, not an overflowing text box.
    path = tmp_path / 'article.pdf'
    with pymupdf.open() as doc:
        for part in text.split(prose):
            page = doc.new_page()
            page.insert_textbox((45, 40, 550, 780), part + '\n' + prose, fontsize=10)
        doc.save(path)
    if abstract:
        assert assess_pdf(path)['status'] == 'accepted'
        assert build_paper(path)['nodes'][0]['kind'] == 'Paper'
    else:
        assert assess_pdf(path)['reason_code'] == 'paper_structure_incomplete'


def test_appendix_form_does_not_reclassify_a_real_thesis(tmp_path):
    prose = '本文研究软件检测方法，提出新算法并对实验结果进行分析。' * 12
    from test_paper_structure_compilation import thesis
    path = thesis(tmp_path)
    with pymupdf.open(path) as doc:
        page = doc.new_page()
        page.insert_text((45, 50), '论文推荐表', fontname='china-s')
        doc.save(tmp_path / 'with-appendix.pdf')
    assert build_paper(tmp_path / 'with-appendix.pdf')['nodes'][0]['kind'] == 'Paper'


@pytest.mark.parametrize('kind', ['blank', 'scan', 'corrupt'])
def test_unconfirmed_or_unreadable_documents_fail_closed(tmp_path, kind):
    path = pdf_with_text(tmp_path, '' if kind == 'blank' else 'Recommendation form', scanned_back=kind == 'scan')
    if kind == 'scan':
        with pymupdf.open(path) as doc:
            doc.delete_page(0)
            doc.save(tmp_path / 'scan.pdf')
        path = tmp_path / 'scan.pdf'
    if kind == 'corrupt':
        path.write_bytes(b'%PDF-corrupted')
    assert assess_pdf(path)['status'] == 'rejected'


def test_ieee_article_roman_headings_and_abstract_dash_are_admitted(tmp_path):
    prose = 'We propose and evaluate a new software analysis method with experimental evidence. ' * 25
    path = tmp_path / 'ieee.pdf'
    with pymupdf.open() as doc:
        for heading in ['A Study of Analysis\nAbstract—This paper studies analysis.', 'I. INTRODUCTION',
                        'II. METHOD', 'III. RESULTS', 'IV. CONCLUSION', 'REFERENCES']:
            page = doc.new_page()
            assert page.insert_textbox((45, 40, 550, 780), heading + '\n' + prose, fontsize=10, fontname='china-s') >= 0
        doc.save(path)
    assert assess_pdf(path)['status'] == 'accepted'


def test_research_about_invoices_is_not_an_invoice(tmp_path):
    from paper_compiler.document_admission import assess_pages
    rows = ['Information Extraction from Scanned Invoice Images', 'Abstract',
            'We propose a learning algorithm to extract information from invoices. ' * 80,
            '1 Introduction', '2 Methods', '3 Results', '4 Conclusion', 'References']
    assert assess_pages([{'lines': [{'text': row} for row in rows]}])['status'] == 'accepted'


def test_two_column_article_keeps_source_headings_and_keywords_without_colon(tmp_path):
    path = tmp_path / 'two-column.pdf'
    with pymupdf.open() as doc:
        page = doc.new_page()
        prose = 'We propose an algorithm to analyze documents and evaluate the experimental results. ' * 12
        page.insert_text((45, 50), 'Information Extraction from Invoice Images')
        page.insert_text((45, 100), 'Abstract')
        assert page.insert_textbox((45, 120, 280, 680), prose, fontsize=10) >= 0
        assert page.insert_textbox((310, 90, 550, 680), prose, fontsize=10) >= 0
        page.insert_text((45, 710), 'Keywords OCR, information extraction')
        page.insert_text((45, 740), 'References')
        for heading in ['1 Introduction', '2 Methods', '3 Conclusion']:
            page = doc.new_page()
            page.insert_text((45, 70), heading)
            assert page.insert_textbox((45, 100, 550, 750), prose, fontsize=10) >= 0
        doc.save(path)
    assessment = assess_pdf(path)
    assert assessment['status'] == 'accepted'
    assert assessment['signals']['keywords']
    assert build_paper(path)['nodes'][0]['kind'] == 'Paper'
