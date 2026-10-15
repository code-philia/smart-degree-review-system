"""Unrelated PDF pages must not enter a local physical-panel comparison."""
from pathlib import Path
import pytest
from pdf_rules.model import PdfDocument, PdfPage, PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.logical_objects import panel_label_conflict


class ReadCountingLines(tuple):
    def __new__(cls, values):
        value = super().__new__(cls, values)
        value.reads = 0
        return value

    def __iter__(self):
        for line in super().__iter__():
            self.reads += 1
            yield line


@pytest.mark.parametrize("target_page", [2, 9])
@pytest.mark.parametrize("restarted", [False, True])
def test_panel_conflict_reads_only_pages_with_comparison_regions(target_page, restarted):
    pages = []
    for number in range(1, 13):
        tags = ("(a) first", "(a) second" if restarted else "(b) second")
        lines = ReadCountingLines(tuple(
            PdfLine(number, text, (100, 150+i*120, 220, 164+i*120), 600, 800)
            for i, text in enumerate(tags)))
        pages.append(PdfPage(number, 600, 800, lines))
    document = PdfDocument(Path("panel-scope.pdf"), tuple(pages))
    observations = [LayoutObject("figure", target_page, box, "", 600, 800, "image_body")
                    for box in ((80, 80, 260, 145), (80, 200, 260, 265))]
    # Real panel behavior still distinguishes shared(a,b) from restarted(a,a).
    assert panel_label_conflict(observations, document) is restarted
    assert pages[target_page-1].lines.reads > 0
    # Counts instrument real source reads; no caption/label function is mocked.
    assert sum(page.lines.reads for page in pages if page.number != target_page) == 0


@pytest.mark.parametrize("reverse", [False, True])
def test_horizontally_unaligned_panels_do_not_scan_text_for_a_merge(reverse):
    from pdf_rules.logical_objects import continuous_chart_rows
    lines=ReadCountingLines((PdfLine(1,"(a) experimental label",(100,150,220,164),600,800),))
    doc=PdfDocument(Path("unaligned-components.pdf"),(PdfPage(1,600,800,lines),))
    parts=[LayoutObject("figure",1,box,"",600,800,"native_figure")
           for box in ((80,100,180,200),(320,200,420,300))]
    sequence=list(reversed(parts)) if reverse else parts
    result=continuous_chart_rows(sequence,[],doc)
    assert result==sequence
    assert lines.reads==0
