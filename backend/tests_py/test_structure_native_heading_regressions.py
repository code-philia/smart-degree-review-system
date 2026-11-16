"""Native heading style and running-header regressions, without model calls."""
import pytest

from paper_compiler.document_admission import assess_document_pages
from paper_compiler.structure import has_bilingual_abstract_bodies


def line(text, *, y=132, size=16, bold=True, x=180):
    return {"text": text, "bbox": [x, y, x + 210, y + size],
            "font_size": size, "is_bold": bold}


def native_thesis(*, body_bold=True, running_intro=False):
    zh = "本文研究软件分析方法，并通过真实实验验证所提出方法的有效性。" * 12
    en = "We propose a software analysis method and evaluate the effectiveness of its experimental results. " * 12
    headings = ["博士学位论文", "摘要", "Abstract", "目录", "第一章 绪论",
                "第二章 方法研究", "第三章 结论", "参考文献"]
    pages = []
    for index, heading in enumerate(headings):
        rows = [line(heading, bold=body_bold if index == 5 else True),
                line(en if index == 2 else zh, y=180, size=12, bold=False, x=90),
                line(en if index == 2 else zh, y=210, size=12, bold=False, x=90),
                line(en if index == 2 else zh, y=240, size=12, bold=False, x=90)]
        if index in {1, 2}:
            rows.append(line("Keywords: software; analysis" if index == 2 else "关键词：软件；分析",
                             y=690, size=12, bold=False, x=90))
        if running_intro:
            rows.insert(0, line("第一章 绪论", y=92, size=12, bold=False, x=420))
        pages.append({"page_index": index, "height": 842, "width": 595, "lines": rows})
    return pages


def test_prominent_peer_chapter_does_not_require_intro_bold_style():
    result = assess_document_pages(native_thesis(body_bold=False))
    assert result["status"] == "accepted"
    assert result["structure"]["observed_sections"]["主体"] is True


def test_repeated_low_running_intro_header_does_not_hide_bilingual_abstracts():
    pages = native_thesis(running_intro=True)
    result = assess_document_pages(pages)
    assert result["status"] == "accepted"
    assert result["structure"]["abstract_sections"]["摘要"]["page_number"] == 2
    assert result["structure"]["abstract_sections"]["英文摘要"]["page_number"] == 3
    assert has_bilingual_abstract_bodies(pages) is True


def test_running_intro_header_cannot_supply_removed_actual_intro():
    pages = native_thesis(running_intro=True)
    pages[4]["lines"] = [row for row in pages[4]["lines"] if row["bbox"][1] != 132]
    result = assess_document_pages(pages)
    assert "引言" in result["missing_sections"]


def test_peer_chapter_body_still_requires_actual_heading():
    pages = native_thesis(body_bold=False)
    pages[5]["lines"] = [row for row in pages[5]["lines"] if row["bbox"][1] != 132]
    assert "主体" in assess_document_pages(pages)["missing_sections"]


@pytest.mark.parametrize("page_index, missing", [(1, "摘要"), (2, "英文摘要")])
def test_running_header_does_not_restore_removed_abstract_heading(page_index, missing):
    pages = native_thesis(running_intro=True)
    pages[page_index]["lines"] = [row for row in pages[page_index]["lines"] if row["bbox"][1] != 132]
    assert missing in assess_document_pages(pages)["missing_sections"]


def test_normal_size_numbered_chapter_mention_is_not_a_prominent_body_heading():
    pages = native_thesis(body_bold=False)
    pages[5]["lines"][0] = line("第二章 方法研究", size=12, bold=False)
    assert "主体" in assess_document_pages(pages)["missing_sections"]


def test_split_native_chapter_title_tolerates_font_bbox_ascent_difference():
    pages = native_thesis(body_bold=False, running_intro=True)
    for page_index, number, title in [(4, "第1 章", "绪论"), (5, "第2 章", "方法研究"),
                                      (6, "第3 章", "结论")]:
        page = pages[page_index]
        page["lines"][1:2] = [line(number, x=210),
                              line(title, x=280, y=136, bold=page_index != 5)]
        page["lines"][1]["bbox"][2] = 260
    assert assess_document_pages(pages)["status"] == "accepted"
