"""Recover numbered article headings without treating diagram labels as chapters."""
import pymupdf
import pytest

from paper_compiler.frontend import _build_source_tree
from paper_compiler.local_checks import detect_ir


def article(tmp_path, *, profile='research-article', clean=False, colon=False):
    path = tmp_path / 'split-numbered-sections.pdf'
    with pymupdf.open() as doc:
        p = doc.new_page(width=600, height=800)
        for x in (60, 320):
            for y in (140, 160, 180):
                p.insert_text((x, y), 'Earlier research describes our document analysis.', fontsize=10, fontname='tiro')
        p.insert_text((130, 250), '1', fontsize=12, fontname='tibo')
        p.insert_text((155, 250), 'Introduction', fontsize=12, fontname='tibo')
        for y in (280, 300, 320):
            p.insert_text((60, y), 'Our study compares several reliable approaches.', fontsize=10, fontname='tiro')
        # Neither a smaller subsection nor a large figure label is a chapter.
        p.insert_text((60, 350), '1.1 Implementation Details', fontsize=11, fontname='tibo')
        p.insert_text((155, 380), 'Reasoning Agent', fontsize=12, fontname='tibo')
        p.insert_text((155, 410), 'Figure 2 Overview', fontsize=12, fontname='tibo')
        if clean:
            p = doc.new_page(width=600, height=800)
        p.insert_text((105 if colon else 130, 450 if not clean else 130), '2', fontsize=12, fontname='tibo')
        p.insert_text((130 if colon else 155, 450 if not clean else 130), 'Evaluation: Tests' if colon else 'Evaluation', fontsize=12, fontname='tibo')
        p.insert_text((60, 500), 'The results establish the performance of the system.', fontsize=10, fontname='tiro')
        p = doc.new_page(width=600, height=800)
        p.insert_text((130, 130), '3', fontsize=12, fontname='tibo')
        p.insert_text((155, 130), 'Conclusion', fontsize=12, fontname='tibo')
        p.insert_text((60, 170), 'We summarize the findings and future research.', fontsize=10, fontname='tiro')
        doc.save(path)
    ir = _build_source_tree(path, include_citations=False)
    ir['metadata']['document_admission'] = {'structure': {'profile': profile}}
    assert not any(n['kind'] == 'Heading' and n['text'] and 'Introduction' in n['text'] for n in ir['nodes'])
    return ir


def test_numbered_article_titles_inside_paragraphs_are_checked(tmp_path):
    found = detect_ir(article(tmp_path), [38])['38']['findings']
    assert [f['token'] for f in found] == ['1introduction', '2evaluation']
    assert found[1]['location']['bounding_rect']['y1'] > 430


def test_fresh_page_heading_does_not_alarm(tmp_path):
    found = detect_ir(article(tmp_path, clean=True), [38])['38']['findings']
    assert [f['token'] for f in found] == ['1introduction']


@pytest.mark.parametrize('profile', ['chinese-thesis', 'english-thesis'])
def test_article_style_fallback_does_not_expand_thesis_checks(tmp_path, profile):
    assert detect_ir(article(tmp_path, profile=profile), [38])['38']['findings'] == []


def test_numbered_body_prose_does_not_supply_chapter_style(tmp_path):
    ir = article(tmp_path)
    for node in ir['nodes']:
        if node['text']:
            node['text'] = node['text'].replace('Introduction', 'Background sentence.').replace('Conclusion', 'Closing sentence.')
    assert detect_ir(ir, [38])['38']['findings'] == []


def test_colon_in_a_real_first_level_title_is_retained(tmp_path):
    found = detect_ir(article(tmp_path, colon=True), [38])['38']['findings']
    assert [f['token'] for f in found] == ['1introduction', '2evaluation:tests']
