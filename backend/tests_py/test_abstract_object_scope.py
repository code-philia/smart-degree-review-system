"""Abstract numbering checks must never consume adjacent article body columns."""
import copy

import pymupdf
import pytest

from paper_compiler.frontend import _build_source_tree
from paper_compiler.local_checks import detect_ir


def findings(ir):
    return detect_ir(ir, [37])["37"]["findings"]


def article(tmp_path, *, abstract_tokens=False, continuation=False, single_column=False):
    path = tmp_path / "article.pdf"
    with pymupdf.open() as doc:
        p = doc.new_page(width=600, height=800)
        p.insert_text((60, 110), "Abstract", fontsize=14)
        for y in (140, 160, 180, 200):
            p.insert_text((60, y), "Our method improves reliable document analysis.", fontsize=10)
        if abstract_tokens:
            p.insert_text((60, 240), "Our evaluation uses Figure 3 and Table 2.", fontsize=10)
            p.insert_text((60, 260), "We compare Equation (4) with earlier work [5].", fontsize=10)
        if continuation:
            for y in (110, 130, 150):
                p.insert_text((320, y), "The analysis continues with additional evidence.", fontsize=10)
            p.insert_text((320, 180), "We retain genuine references to Figure 6.", fontsize=10)
        intro_x, intro_y = (60, 310) if single_column else (320, 250 if continuation else 110)
        p.insert_text((intro_x, intro_y), "1 Introduction", fontsize=14)
        for y in (intro_y + 30, intro_y + 50, intro_y + 70):
            p.insert_text((intro_x, y), "Prior work [16] is compared with Figure 9.", fontsize=10)
        p = doc.new_page(width=600, height=800)
        p.insert_text((60, 110), "2 Methods", fontsize=14)
        p.insert_text((60, 140), "The body cites Table 8 and Equation (9).", fontsize=10)
        doc.save(path)
    ir = _build_source_tree(path, include_citations=False)
    ir['metadata']['document_admission'] = {'structure': {'profile': 'research-article'}}
    return ir


@pytest.mark.parametrize("single_column", [False, True])
def test_first_page_introduction_closes_abstract(tmp_path, single_column):
    assert findings(article(tmp_path, single_column=single_column)) == []


def test_genuine_late_left_column_abstract_references_are_retained(tmp_path):
    found = findings(article(tmp_path, abstract_tokens=True))
    assert {f["token"] for f in found} == {"Figure 3", "Table 2", "Equation (4)", "[5]"}
    assert all(f["location"]["page_number"] == 1 for f in found)
    assert all(f["location"]["bounding_rect"]["x1"] < 300 for f in found)


def test_abstract_can_continue_in_right_column_before_introduction(tmp_path):
    found = findings(article(tmp_path, abstract_tokens=True, continuation=True))
    assert {f["token"] for f in found} == {"Figure 3", "Table 2", "Equation (4)", "[5]", "Figure 6"}
    figure = next(f for f in found if f["token"] == "Figure 6")
    assert figure["location"]["bounding_rect"]["x1"] == pytest.approx(320)


@pytest.mark.parametrize("boundary", ["CCS Concepts", "Keywords", "Index Terms", "Keywords: analysis"])
def test_article_metadata_is_not_abstract_prose(tmp_path, boundary):
    ir = article(tmp_path)
    template = next(n for n in ir["nodes"] if n["kind"] == "Heading" and n["text"] == "Abstract")
    for nid, text, y, kind in [("metadata", boundary, 280, "Heading"),
                               ("metadata-text", "Subject classification [99] uses Table 7.", 310, "Paragraph")]:
        n = copy.deepcopy(template)
        n.update(id=nid, text=text, kind=kind)
        n["provenance"][0].update(bbox=[60,y,280,y+12], node_text_end=len(text))
        ir["nodes"].append(n)
    assert findings(ir) == []


def test_partial_paragraph_cannot_reintroduce_excluded_middle_spans(tmp_path):
    ir = article(tmp_path, abstract_tokens=True)
    node = next(n for n in ir["nodes"] if n["text"] and "Our evaluation" in n["text"])
    selected = copy.deepcopy(node["provenance"][0])
    fragments = [("The abstract refers to Figure 3.", 60, 240),
                 ("The body refers to Figure 9.", 320, 300),
                 ("The abstract refers to Table 2.", 60, 260)]
    node["text"] = "\n".join(text for text, _, _ in fragments)
    node["provenance"] = []
    offset = 0
    for text, x, y in fragments:
        span = copy.deepcopy(selected)
        span.update(bbox=[x,y,x+220,y+12], node_text_start=offset, node_text_end=offset+len(text))
        node["provenance"].append(span)
        offset += len(text)+1
    found = findings(ir)
    assert "Figure 9" not in {f["token"] for f in found}
    assert {"Figure 3", "Table 2"} <= {f["token"] for f in found}


def test_numeric_first_level_chapter_in_body_column_is_checked(tmp_path):
    ir = article(tmp_path)
    found = detect_ir(ir, [38])["38"]["findings"]
    assert len(found) == 1
    assert found[0]["token"] == "1introduction"
    assert found[0]["location"]["page_number"] == 1


@pytest.mark.parametrize("heading,expected", [
    ("Chapter 2 Methods", True), ("2 Methods", True),
    ("2.1 Methods", False), ("2 Methods are described in this paragraph.", False)])
def test_chapter_number_forms_do_not_include_subsections_or_prose(tmp_path, heading, expected):
    path = tmp_path / "chapter.pdf"
    with pymupdf.open() as doc:
        p = doc.new_page(width=600, height=800)
        p.insert_text((60, 110), "Chapter 1 Introduction", fontsize=18)
        for y in (150, 180, 210):
            p.insert_text((60, y), "The previous chapter continues on this page.", fontsize=12)
        p.insert_text((60, 300), heading, fontsize=18 if not heading.endswith(".") else 12)
        p.insert_text((60, 340), "The following chapter discusses the methods.", fontsize=12)
        doc.save(path)
    ir = _build_source_tree(path, include_citations=False)
    ir['metadata']['document_admission'] = {'structure': {'profile': 'research-article'}}
    found = detect_ir(ir, [38])["38"]["findings"]
    assert bool(found) is expected
    if expected:
        assert len(found) == 1
        assert found[0]["location"]["bounding_rect"]["y1"] > 250


def test_bare_numeric_labels_do_not_change_thesis_chapter_policy(tmp_path):
    ir = article(tmp_path)
    ir['metadata']['document_admission']['structure']['profile'] = 'chinese-thesis'
    assert detect_ir(ir, [38])['38']['findings'] == []


@pytest.mark.parametrize('title', ['1 Introduction', '1 Introduction and Contextualization'])
def test_two_column_abstract_before_full_width_body_retains_both_columns(tmp_path, title):
    path = tmp_path / 'full-width-body.pdf'
    with pymupdf.open() as doc:
        p = doc.new_page(width=600, height=800)
        p.insert_text((60, 110), 'Abstract', fontsize=14)
        for x in (60, 320):
            for y in (140, 160, 180, 200):
                p.insert_text((x, y), 'Our method improves reliable document analysis.', fontsize=10)
        p.insert_text((320, 240), 'Our abstract cites Figure 6.', fontsize=10)
        p.insert_text((60, 400), title, fontsize=18)
        p.insert_text((60, 440), 'The full width body cites Table 7 and documents the complete experimental evaluation procedure.', fontsize=10)
        doc.save(path)
    found = findings(_build_source_tree(path, include_citations=False))
    assert [f['token'] for f in found] == ['Figure 6']
    assert found[0]['location']['bounding_rect']['x1'] == pytest.approx(320)


def test_short_final_abstract_line_stays_in_left_column(tmp_path):
    path = tmp_path / 'short-final-line.pdf'
    with pymupdf.open() as doc:
        p = doc.new_page(width=600, height=800)
        p.insert_text((60, 110), 'Abstract', fontsize=14)
        for y in (140, 160, 180, 200):
            p.insert_text((60, y), 'Our method improves reliable document analysis.', fontsize=10)
        p.insert_text((60, 240), 'See Figure 6.', fontsize=10)
        p.insert_text((320, 110), '1 Introduction', fontsize=14)
        for y in (140, 160, 180):
            p.insert_text((320, y), 'Prior work [16] motivates the current analysis.', fontsize=10)
        doc.save(path)
    found = findings(_build_source_tree(path, include_citations=False))
    assert [f['token'] for f in found] == ['Figure 6']
    assert found[0]['location']['bounding_rect']['x1'] == pytest.approx(60)
