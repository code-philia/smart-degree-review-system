"""A quoted native title remains the Chinese anchor of one bilingual visual."""
from pathlib import Path

import pytest

from pdf_rules.caption_context import contextual_caption
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules
from pdf_rules.model import PdfDocument, PdfLine, PdfPage


def title(text, bbox, *, block=3, size=10.56):
    return PdfLine(1, text, bbox, 595.32, 841.92, block_id=block, font_size=size)


@pytest.mark.parametrize("word,translation,rule", [
    ("图", "Fig.", 15), ("表", "Table", 16),
])
@pytest.mark.parametrize("opening,closing", [("“", "”"), ("‘", "’"), ("「", "」")])
def test_adjacent_quoted_nominal_title_keeps_both_language_rectangles(word, translation, rule, opening, closing):
    chinese = title(f"{word}1- 2{opening}试验曲线{closing}", (263.69, 676.97, 348.55, 688.66))
    english = title(f"{translation}1- 2 Experimental curve", (244.37, 689.81, 367.87, 701.50))
    visual = (140, 420, 470, 666)
    page = PdfPage(1, 595.32, 841.92, (chinese, english),
                   images=(visual,) if rule == 15 else (), tables=(visual,) if rule == 16 else ())
    doc = PdfDocument(Path("quoted-title.pdf"), (page,))
    findings = detect_rules(build_index(doc), {rule})[str(rule)]["findings"]
    assert len(findings) == 1
    rects = findings[0]["location"]["rects"]
    boxes = {(r["x1"], r["y1"], r["x2"], r["y2"]) for r in rects}
    assert boxes == {chinese.bbox, english.bbox}
    assert findings[0]["caption_count"] == 2


@pytest.mark.parametrize("word,kind", [("图", "figure"), ("表", "table")])
def test_quoted_object_name_at_body_paragraph_start_stays_prose(word, kind):
    first = title(f"{word}1-2“试验曲线”的峰值高度为十八米，其他参数仍需比较。", (117, 200, 515, 213), block=7, size=12)
    following = title("因此本文采用另一种计算方法进一步验证模型的精度。", (94, 217, 515, 230), block=7, size=12)
    sample = title("本节给出了不同方法计算结果之间的具体差异和误差分析。", (94, 170, 515, 183), block=8, size=12)
    page = PdfPage(1, 595.32, 841.92, (sample, first, following))
    assert contextual_caption(first, page, kind) is None
