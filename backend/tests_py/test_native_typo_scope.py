"""Native PDF provenance gates typo input; these fixtures never perform OCR."""
from copy import deepcopy
import socket
import subprocess
import urllib.request

import pymupdf
import pytest

from native_typo_scope import filter_native_typo_ir
from paper_compiler.frontend import _build_source_tree, _observe
from run_bilingual_semantic_lint import _body_chunks


def raster():
    with pymupdf.open() as image:
        page = image.new_page(width=600, height=800)
        page.insert_text((60, 100), "Scanned source, not editable body text.")
        page.draw_rect((70, 150, 500, 680), color=(0, 0, 0))
        return page.get_pixmap().tobytes("png")


def body_page(document):
    page = document.new_page(width=600, height=800)
    page.insert_text((60, 80), "Chapter 1 Introduction", fontsize=18)
    return page


def text(page, value, y=130, **kwargs):
    page.insert_text((60, y), value, fontname="china-s", fontsize=12, **kwargs)


def run_scope(document, tmp_path):
    path = tmp_path / "native-provenance.pdf"
    document.save(path)
    ir = _build_source_tree(path, include_citations=False)
    before = deepcopy(ir)
    filtered, audit = filter_native_typo_ir(path, ir)
    assert ir == before, "scope selection must not alter the compiler IR"
    return "\n\n".join(chunk["model_text"] for chunk in _body_chunks(filtered)), audit


@pytest.mark.parametrize("render_mode", [0, 3])
def test_full_page_scan_overlay_cannot_enter_typo_input(tmp_path, render_mode):
    with pymupdf.open() as document:
        page = body_page(document)
        page.insert_image(page.rect, stream=raster())
        text(page, "扫描文字误识成多轮对活场景。", render_mode=render_mode)
        result, audit = run_scope(document, tmp_path)
    assert result == ""
    assert audit["scanned_pages"] == [1]
    assert audit["coverage"] == "none"


def test_image_only_scan_is_explicitly_reported_as_skipped(tmp_path):
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        page.insert_image(page.rect, stream=raster())
        result, audit = run_scope(document, tmp_path)
    assert result == ""
    assert audit["page_decisions"][0]["reasons"] == ["page_raster_scan"]


def test_tiled_full_page_scan_is_not_mistaken_for_native_body(tmp_path):
    with pymupdf.open() as document:
        page = body_page(document)
        for box in [(0, 0, 300, 800), (300, 0, 600, 800)]:
            page.insert_image(box, stream=raster(), keep_proportion=False)
        text(page, "拼接扫描图里的隐藏文字。", render_mode=3)
        result, audit = run_scope(document, tmp_path)
    assert result == ""
    assert audit["scanned_pages"] == [1]


def test_native_body_with_a_large_diagram_retains_its_real_typo(tmp_path):
    with pymupdf.open() as document:
        page = body_page(document)
        text(page, "系统尚未完成布署，因此暂不发布。")
        page.insert_image((80, 220, 520, 650), stream=raster())
        result, audit = run_scope(document, tmp_path)
    assert "系统尚未完成布署" in result
    assert audit["eligible_pages"] == [1]
    assert audit["scanned_pages"] == []


def test_adjacent_native_superscript_does_not_remove_a_body_line(tmp_path):
    with pymupdf.open() as document:
        page = body_page(document)
        text(page, "这是包含公式的原生正文錯字。")
        # A formula's superscript can lie inside another rawdict line's taller
        # font-metric bbox, while the compiler correctly gives it its own source.
        page.insert_text((195, 124), "2", fontsize=7)
        result, _ = run_scope(document, tmp_path)
    assert "这是包含公式的原生正文錯字" in result


def test_pdf_image_clip_keeps_native_text_beyond_the_visible_diagram(tmp_path):
    with pymupdf.open() as document:
        page = body_page(document)
        page.insert_image(page.rect, stream=raster(), keep_proportion=False)
        image_stream = page.get_contents()[-1]
        document.update_stream(image_stream, b"q 0 400 600 400 re W n\n" + document.xref_stream(image_stream) + b"\nQ")
        text(page, "原生正文在图片实际裁剪区域之外。", y=550)
        text(page, "实际图片内的文字仍须跳过。", y=300)
        result, audit = run_scope(document, tmp_path)
    assert "原生正文在图片实际裁剪区域之外" in result
    assert "实际图片内" not in result
    assert audit["scanned_pages"] == []
    assert audit["page_decisions"][0]["raster_coverage"] == .5


@pytest.mark.parametrize("render_mode", [0, 3])
def test_partial_scan_keeps_only_independent_native_body(tmp_path, render_mode):
    with pymupdf.open() as document:
        page = body_page(document)
        text(page, "这是保留的原生正文錯字。")
        page.insert_image((40, 260, 550, 650), stream=raster(), keep_proportion=False)
        text(page, "图片内的隐藏文字不应检测。", y=330, render_mode=render_mode)
        text(page, "这是图下的原生正文。", y=710)
        result, audit = run_scope(document, tmp_path)
    assert "原生正文錯字" in result
    assert "图下的原生正文" in result
    assert "图片内" not in result
    assert audit["coverage"] == "partial"
    assert audit["page_decisions"][0]["status"] == "partial"


@pytest.mark.parametrize("options", [{"render_mode": 3}, {"fill_opacity": 0}])
def test_nonvisible_text_is_excluded_even_without_a_raster(tmp_path, options):
    with pymupdf.open() as document:
        page = body_page(document)
        text(page, "可见的原生正文。")
        text(page, "没有扫描图也不能检测隐藏文字。", y=200, **options)
        result, _ = run_scope(document, tmp_path)
    assert "可见的原生正文" in result
    assert "隐藏文字" not in result


def test_text_painted_under_an_image_is_excluded(tmp_path):
    with pymupdf.open() as document:
        page = body_page(document)
        text(page, "正常正文仍需检查。")
        text(page, "图后不可见文字。", y=330)
        page.insert_image((40, 260, 550, 650), stream=raster(), keep_proportion=False)
        result, _ = run_scope(document, tmp_path)
    assert "正常正文" in result
    assert "图后不可见" not in result


def test_native_administrative_back_matter_is_excluded(tmp_path):
    with pymupdf.open() as document:
        page = body_page(document)
        text(page, "正文中的錯字仍然需要检查。")
        page = document.new_page(width=600, height=800)
        page.insert_text((100, 90), "学位论文答辩决议书", fontname="china-s", fontsize=18)
        text(page, "姓名：某同学    学号：123456")
        text(page, "答辩日期：某日期", y=170)
        text(page, "行政附页中的錯字不在正文检测范围。", y=220)
        page = document.new_page(width=600, height=800)
        text(page, "答辩决议续页中的錯字也不属于正文。")
        result, audit = run_scope(document, tmp_path)
    assert "正文中的錯字仍然" in result
    assert "行政附页" not in result
    assert "答辩决议续页" not in result
    assert audit["administrative_pages"] == [2, 3]


def test_body_mention_of_administrative_form_does_not_end_scope(tmp_path):
    with pymupdf.open() as document:
        page = body_page(document)
        text(page, "系统支持答辩决议书管理，正文錯字仍需检测。")
        result, audit = run_scope(document, tmp_path)
    assert "正文錯字仍需检测" in result
    assert audit["administrative_pages"] == []


def test_early_declaration_cannot_hide_later_native_chapter(tmp_path):
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        page.insert_text((100, 90), "学位论文原创性声明", fontname="china-s", fontsize=18)
        text(page, "本人郑重声明此论文为本人研究成果。")
        page = body_page(document)
        text(page, "进入正文后，系统布署有待完成。")
        result, audit = run_scope(document, tmp_path)
    assert "系统布署有待完成" in result
    assert audit["eligible_pages"] == [2]


def test_native_and_scan_pages_do_not_share_a_paragraph(tmp_path):
    with pymupdf.open() as document:
        page = body_page(document)
        text(page, "原生段落的前半部。")
        page = document.new_page(width=600, height=800)
        page.insert_image(page.rect, stream=raster())
        text(page, "扫描段落不可进入模型。", render_mode=3)
        page = document.new_page(width=600, height=800)
        text(page, "原生段落的后半部含有錯字。")
        path = tmp_path / "merged-native-scan.pdf"
        document.save(path)
    observations = _observe(path)
    lines = [(p, line) for p in observations for line in p["lines"] if "Chapter" not in line["text"]]
    value = "\n".join(line["text"] for _, line in lines)
    sources, start = [], 0
    for p, line in lines:
        sources.append({"kind": "source", "source_id": "pdf", "page_index": p["page_index"],
                        "bbox": line["bbox"], "node_text_start": start,
                        "node_text_end": start + len(line["text"])})
        start += len(line["text"]) + 1
    ir = {"nodes": [{"id": "body", "kind": "Body", "children": ["p"]},
                    {"id": "p", "kind": "Paragraph", "text": value, "provenance": sources}]}
    filtered, audit = filter_native_typo_ir(path, ir)
    result = "\n\n".join(c["model_text"] for c in _body_chunks(filtered))
    assert "扫描段落" not in result
    assert "原生段落的前半部。\n\n原生段落的后半部" in result
    assert audit["eligible_pages"] == [1, 3]


def test_scope_must_not_fall_back_to_native_front_matter(tmp_path):
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        text(page, "封面的姓名不是正文的錯字检测范围。")
        result, audit = run_scope(document, tmp_path)
    assert result == ""
    assert audit["coverage"] == "none"


def test_missing_provenance_is_not_assumed_to_be_native(tmp_path):
    with pymupdf.open() as document:
        page = body_page(document)
        text(page, "这是真实原生文字。")
        path = tmp_path / "source.pdf"
        document.save(path)
    ir = {"nodes": [{"id": "body", "kind": "Body", "children": ["p"]},
                    {"id": "p", "kind": "Paragraph", "text": "无来源的錯字。"}]}
    filtered, audit = filter_native_typo_ir(path, ir)
    assert _body_chunks(filtered) == []
    assert audit["coverage"] == "none"


def test_unavailable_pdf_is_an_explicitly_empty_scope(tmp_path):
    ir = {"nodes": [{"id": "body", "kind": "Body", "children": ["p"]},
                    {"id": "p", "kind": "Paragraph", "text": "不能把来源不可用当作通过。"}]}
    filtered, audit = filter_native_typo_ir(tmp_path / "missing.pdf", ir)
    assert _body_chunks(filtered) == []
    assert audit["source_status"] == "unavailable"
    assert audit["coverage"] == "none"


@pytest.mark.parametrize("change", ["text", "source_id", "same_characters_reordered"])
def test_unproven_source_text_is_not_accepted_from_a_native_bbox(tmp_path, change):
    with pymupdf.open() as document:
        page = body_page(document)
        text(page, "这是真实原生正文。")
        path = tmp_path / "untrusted-source.pdf"
        document.save(path)
    ir = _build_source_tree(path, include_citations=False)
    paragraph = next(node for node in ir["nodes"] if node.get("kind") == "Paragraph" and "原生正文" in node.get("text", ""))
    if change == "text":
        paragraph["text"] = paragraph["text"].replace("正文", "错字")
    elif change == "source_id":
        for source in paragraph["provenance"]:
            source["source_id"] = "ocr"
    else:
        paragraph["text"] = paragraph["text"].replace("正文", "文正")
    filtered, audit = filter_native_typo_ir(path, ir)
    assert "原生正文" not in "".join(c["model_text"] for c in _body_chunks(filtered))
    assert "错字" not in "".join(c["model_text"] for c in _body_chunks(filtered))
    assert "文正" not in "".join(c["model_text"] for c in _body_chunks(filtered))
    assert audit["coverage"] == "none"


def test_native_columns_and_glyph_paint_order_keep_their_source_line_order(tmp_path):
    with pymupdf.open() as document:
        page = body_page(document)
        # Right column is painted first. Each line also contains separately
        # painted Chinese glyphs; source identity must follow native PDF lines,
        # without imposing a page-wide or left-to-right trace ordering.
        for x, value in [(360, "右列正文有錯字。"), (60, "左列正文仍须检测。")]:
            for index, char in enumerate(value):
                page.insert_text((x + index * 12, 130), char, fontname="china-s", fontsize=12)
        result, audit = run_scope(document, tmp_path)
    assert "右列正文有錯字" in result
    assert "左列正文仍须检测" in result
    assert audit["skip_reasons"] == {}


def test_native_extraction_and_scope_work_with_ocr_network_and_processes_forbidden(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Native typo scope must never invoke OCR, a subprocess, or a network fallback")

    with pymupdf.open() as document:
        page = body_page(document)
        text(page, "原生正文有錯字，仍然属于检测范围。")
        page = document.new_page(width=600, height=800)
        page.insert_image(page.rect, stream=raster())
        text(page, "已有隐藏文字层也不能用于错字检测。", render_mode=3)
        monkeypatch.setattr(pymupdf.Page, "get_textpage_ocr", forbidden)
        monkeypatch.setattr(socket, "create_connection", forbidden)
        monkeypatch.setattr(urllib.request, "urlopen", forbidden)
        monkeypatch.setattr(subprocess, "Popen", forbidden)
        result, audit = run_scope(document, tmp_path)
    assert "原生正文有錯字" in result
    assert "隐藏文字层" not in result
    assert audit["scanned_pages"] == [2]
