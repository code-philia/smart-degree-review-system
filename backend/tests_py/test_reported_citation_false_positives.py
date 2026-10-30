"""Regressions for reported funding, output-list and native citation markers."""
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from five_rule_detector import Line, detect_lines, detect_pdf


def line(page, text, y=100):
    return Line(page, text, (70, y, 530, y + 12), 600, 800)


def bibliography():
    return [line(2, '参考文献', 50), line(2, '[1] Author. First work.', 100),
            line(2, '[2] Author. Unused work.', 130)]


def test_funding_identifiers_do_not_hide_genuine_missing_citations():
    lines = [line(1, '第1章 绪论', 50),
             line(1, '已有研究[1]，另见文献[99]。', 100),
             line(1, '本研究由国家自然科学基金项目[62192731]资助。', 140)]
    result = detect_lines(lines + bibliography(), [22, 24])
    assert [f['token'] for f in result['22']['findings']] == ['99']
    assert [f['token'] for f in result['24']['findings']] == ['2']


def test_bulleted_project_ids_in_academic_outputs_are_not_citations():
    lines = [line(1, '第1章 绪论'), line(1, '已有工作[1]。', 130)]
    lines += bibliography()
    lines += [line(3, '个人简历以及在校期间成果', 50),
              line(3, '研究课题', 100),
              line(3, '• [62192731] 国家自然科学基金重大项目。', 140),
              line(3, '• [62192733] 自然科学基金重大项目子课题。', 170)]
    result = detect_lines(lines, [22, 24])
    assert result['22']['findings'] == []
    assert [f['token'] for f in result['24']['findings']] == ['2']


def test_awards_and_patents_do_not_extend_bibliography_or_count_as_use():
    lines = [line(1, '第1章 绪论'), line(1, '已有研究[1]，另见[99]。', 130)]
    lines += bibliography()
    lines += [line(3, '作者在学期间取得的学术成果', 50),
              line(3, '发表的学术论文', 80), line(3, '[2] Author. Own paper.', 110),
              line(4, '竞赛获奖', 50), line(4, '[1] 2024年竞赛一等奖。', 100),
              line(4, '[3] 2025年竞赛二等奖。', 130),
              line(4, '授权专利', 170), line(4, '[4] 一种专利。', 210)]
    result = detect_lines(lines, [22, 24])
    assert [f['token'] for f in result['22']['findings']] == ['99']
    assert [f['token'] for f in result['24']['findings']] == ['2']


def test_fullwidth_bibliography_labels_and_citations_are_supported():
    lines = [line(1, '第1章 绪论'), line(1, '已有研究［1］，另见［99］。', 130),
             line(2, '参考文献', 50), line(2, '［1］Author. First work.', 100),
             line(2, '［2］Author. Unused work.', 130),
             line(3, '攻读博士学位期间取得创新性成果', 50),
             line(3, '［3］Author. Own paper.', 100)]
    result = detect_lines(lines, [22, 24])
    assert result['22']['status'] == result['24']['status'] == 'completed'
    assert [f['token'] for f in result['22']['findings']] == ['99']
    assert [f['token'] for f in result['24']['findings']] == ['2']


def test_native_citation_destination_recovers_bare_number_only(tmp_path):
    path = tmp_path / 'linked-citation.pdf'
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((70, 90), 'Introduction', fontsize=16)
    page.insert_text((70, 140), 'GPT-Neo 126 initializes the model. Plain experiment 127.', fontsize=12)
    rect = page.search_for('126')[0]
    page = pdf.new_page()
    page.insert_text((70, 90), 'References', fontsize=16)
    page.insert_text((70, 140), '[126] Author. Model paper.', fontsize=12)
    page.insert_text((70, 170), '[127] Author. Unused paper.', fontsize=12)
    target_xref = pdf.page_xref(1)
    pdf.xref_set_key(pdf.pdf_catalog(), 'Names',
                     '<</Dests <</Names [(cite.0@GPT-Neo) [%d 0 R /XYZ 70 700 null]]>>>>' % target_xref)
    pdf[0].insert_link({'kind': pymupdf.LINK_GOTO, 'from': rect, 'page': 1, 'to': pymupdf.Point(70, 140)})
    pdf.reload_page(pdf[0])
    links = pdf[0].get_links()
    pdf.xref_set_key(links[0]['xref'], 'A', '<</S /GoTo /D (cite.0@GPT-Neo)>>')
    pdf.save(path)
    pdf.close()
    result = detect_pdf(path, [22, 24])['rules']
    assert result['22']['findings'] == []
    assert [f['token'] for f in result['24']['findings']] == ['127']

import pytest


@pytest.mark.parametrize('left,right', [('[', ']'), ('［', '］')])
@pytest.mark.parametrize('data', ['X{left}999{right}', 'F1-score 0.56{left}99{right}',
                                  '{left}2,2{right}', 'THIS{left}0{right}, THIS{left}1{right}'])
def test_bracket_width_does_not_change_numeric_data_classification(left, right, data):
    text = data.format(left=left, right=right)
    lines = [line(1, '第1章 绪论', 50), line(1, '已有研究[1]。', 80),
             line(1, text, 110)] + bibliography()
    result = detect_lines(lines, [22, 24])
    assert result['22']['findings'] == []
    assert [f['token'] for f in result['24']['findings']] == ['2']


@pytest.mark.parametrize('left,right', [('[', ']'), ('［', '］')])
def test_wrapped_citations_use_both_bracket_widths_and_stop_at_closer(left, right):
    lines = [line(1, '第1章 绪论', 50),
             line(1, f'已有研究{left}1,', 100),
             line(1, f'99{right}，另见{left}100{right}。', 120),
             line(1, f'继续引用{left}2{right}。', 140)] + bibliography()
    result = detect_lines(lines, [22, 24])
    assert sorted(f['token'] for f in result['22']['findings']) == ['100', '99']
    assert result['24']['findings'] == []


@pytest.mark.parametrize('left,right', [('[', ']'), ('［', '］')])
def test_genuine_missing_citation_preserves_marker_and_original_offsets(left, right):
    marker = f'{left}99{right}'
    text = f'已有研究[1]，另见文献{marker}。'
    result = detect_lines([line(1, '第1章 绪论', 50), line(1, text, 100)]
                          + bibliography(), [22, 24])
    finding, = result['22']['findings']
    assert finding['token'] == '99'
    assert finding['text_range'] == [text.index(marker), text.index(marker) + len(marker)]
    assert marker in finding['message']
    assert [f['token'] for f in result['24']['findings']] == ['2']
