"""General number and directory evidence regressions with unseen identities."""
import unittest
from pathlib import Path

from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules
from pdf_rules.model import PdfDocument, PdfLine, PdfPage
from pdf_rules.numbering import caption_match, normalize_label, normalize_text, toc_line_keys
from pdf_rules.reference_identity_repair import repair_reference_identity


def row(text, y, x=70, right=520, page=1, size=12, **kwargs):
    regions = tuple((i, i + 1, (x + i * 5, y, x + (i + 1) * 5, y + 12))
                    for i in range(len(text)))
    return PdfLine(page, text, (x, y, right, y + 12), 600, 840,
                   font_size=size, text_regions=regions, **kwargs)


def document(*pages):
    return PdfDocument(Path("unseen-research.pdf"), tuple(pages))


def repaired(doc):
    return repair_reference_identity(build_index(doc))


class GeneralReferenceRepairTests(unittest.TestCase):
    def test_spaced_physical_caption_resolves_body_reference(self):
        text = "测量装置的结构如图8.6所示。"
        body = row(text, 110)
        title = row("图8- 6 激光测量装置", 380, x=180, right=420, size=10)
        doc = document(PdfPage(1, 600, 840, (body, title), images=((100, 220, 500, 360),)))
        index = repaired(doc)
        self.assertEqual(detect_rules(index, [11])["11"]["findings"], [])
        self.assertEqual([t.number for t in index.figures], ["8.6"])

    def test_spaced_caption_cannot_credit_itself_as_usage(self):
        title = row("表8- 6 温度测量值", 220, x=180, right=420, size=10)
        doc = document(PdfPage(1, 600, 840, (title,), tables=((90, 245, 510, 380),)))
        self.assertEqual([f["token"] for f in detect_rules(repaired(doc), [16])["16"]["findings"]], ["8.6"])

    def test_spaced_reference_retains_its_native_number_rectangle(self):
        body = row("正文先说明测量过程,详见图8 - 9。", 130)
        index = build_index(document(PdfPage(1, 600, 840, (body,))))
        self.assertEqual([r.number for r in index.figure_refs], ["8.9"])
        self.assertEqual(index.figure_refs[0].line.bbox, (135, 130, 160, 142))
        self.assertEqual(index.figure_refs[0].line.text, body.text)

    def test_normalization_does_not_rewrite_prose_offsets(self):
        self.assertEqual(normalize_text("图8 - 6 与样本1 2"), "图8 - 6 与样本1 2")
        self.assertEqual(normalize_label("B . 8 - 6"), "B.8.6")
        self.assertEqual(normalize_label("1 2"), "1 2")

    def test_period_after_table_word_is_an_actual_caption(self):
        title = row("Table.8-6 Temperature measurements", 220, x=170, right=440, size=10)
        doc = document(PdfPage(1, 600, 840, (title,), tables=((90, 245, 510, 380),)))
        self.assertEqual([t.number for t in repaired(doc).tables], ["8.6"])

    def test_spaced_range_still_reports_only_its_missing_middle_member(self):
        body = row("测量结果如图8 - 4 - 8 - 6所示。", 130)
        first = row("图8.4 校准结果", 300, x=180, right=420, size=10)
        last = row("图8.6 测量结果", 500, x=180, right=420, size=10)
        index = repaired(document(PdfPage(1, 600, 840, (body, first, last))))
        findings = detect_rules(index, [11])["11"]["findings"]
        self.assertEqual([f["token"] for f in findings], ["8.5"])
        self.assertEqual(findings[0]["location"]["bounding_rect"]["x1"], 100)
        self.assertEqual(findings[0]["location"]["bounding_rect"]["x2"], 165)

    def test_malformed_identifier_is_not_partially_a_caption(self):
        for text in ("图B8C 导出变量", "图8- 6x 变量名称", "Table.8- 6x variable"):
            with self.subTest(text=text):
                self.assertIsNone(caption_match(text, "table" if text.startswith("Table") else "figure"))

    def test_split_contents_appendix_and_bibliography_do_not_open_scopes(self):
        contents = (row("目", 96, x=490, right=502), row("录", 96, x=514, right=526),
                    row("第八章", 160, right=112), row("测量实验", 160, x=125, right=300), row("63", 161, x=512, right=526),
                    row("附录B 传感器程序", 195, right=265), row("81", 196, x=512, right=526),
                    row("参考文献", 230, right=120), row("85", 231, x=512, right=526),
                    row("致谢", 265, right=95), row("97", 266, x=512, right=526))
        body = row("独立测量结果如图8.9所示。", 300, page=2)
        index = repaired(document(PdfPage(1, 600, 840, contents), PdfPage(2, 600, 840, (body,))))
        self.assertEqual(index.appendices, [])
        self.assertEqual([(r.number, r.scope) for r in index.figure_refs], [("8.9", "body")])
        self.assertEqual([f["token"] for f in detect_rules(index, [11])["11"]["findings"]], ["8.9"])

    def test_split_acknowledgment_on_continued_directory_is_not_a_section(self):
        contents = (row("8.1 测量装置 ........ 63", 130),
                    row("8.2 校准试验 ........ 67", 165),
                    row("8.3 测量结果 ........ 73", 200),
                    row("致  谢", 235, right=110), row("........ 97", 235, x=125, right=526))
        body = row("校准结果如图8.9所示。", 300, page=2)
        index = repaired(document(PdfPage(1, 600, 840, contents), PdfPage(2, 600, 840, (body,))))
        self.assertEqual([f["token"] for f in detect_rules(index, [11])["11"]["findings"]], ["8.9"])

    def test_contents_title_is_separate_from_its_running_university_header(self):
        contents = (row("城北科技大学博士学位论文", 96, right=200, size=10.5),
                    row("目", 96, x=490, right=502, size=10.5), row("录", 96, x=514, right=526, size=10.5),
                    row("附录B 传感器程序", 165, right=265), row("81", 166, x=512, right=526),
                    row("参考文献", 200, right=120), row("85", 201, x=512, right=526),
                    row("科研成果", 235, right=120), row("97", 236, x=512, right=526))
        body = row("独立测量结果如图8.9所示。", 300, page=2)
        index = repaired(document(PdfPage(1, 600, 840, contents), PdfPage(2, 600, 840, (body,))))
        self.assertEqual([f["token"] for f in detect_rules(index, [11])["11"]["findings"]], ["8.9"])

    def test_actual_bibliography_still_excludes_its_figure_mention(self):
        lines = (row("参考文献", 200, x=250, right=350, size=16, bold=True),
                 row("[1] Wang. Experimental report. 2025.", 245), row("补充说明见图8.9。", 280))
        index = repaired(document(PdfPage(1, 600, 840, lines)))
        self.assertEqual(detect_rules(index, [11])["11"]["findings"], [])

    def test_numeric_table_cells_are_not_a_contents_directory(self):
        lines = (row("目录", 96, x=260, right=310, size=16),
                 row("参数类型", 180, right=135), row("63", 180, x=512, right=526),
                 row("参考文献", 215, right=135), row("85", 215, x=512, right=526),
                 row("测量参数", 250, right=135), row("97", 250, x=512, right=526))
        doc = document(PdfPage(1, 600, 840, lines, tables=((65, 160, 535, 300),)))
        self.assertFalse(toc_line_keys(doc))


if __name__ == "__main__":
    unittest.main()
