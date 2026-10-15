"""General layout regressions; mutation manifests never enter production code."""
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import pymupdf
from pdf_rules.engine import detect


class LayoutHttp:
    def __init__(self, pages):
        self.pages = pages
        self.uploaded_pages = []

    def request(self, method, url, **kwargs):
        if method == "POST":
            return {"code": 0, "data": {"batch_id": "fixture", "file_urls": ["https://fixture/upload"]}}
        if method == "PUT":
            with pymupdf.open(stream=kwargs["data"], filetype="pdf") as pdf:
                self.uploaded_pages.append(len(pdf))
            return {}
        if "/extract-results/" in url:
            return {"code": 0, "data": {"extract_result": [{"state": "done", "full_zip_url": "https://fixture/result"}]}}
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("layout.json", json.dumps({"pdf_info": self.pages}))
        return stream.getvalue()


def text_block(text, box=(60, 100, 550, 125)):
    return {"type": "text", "bbox": list(box), "lines": [{"bbox": list(box), "spans": [{"content": text}]}]}


def layout_page(number, blocks):
    return {"page_idx": number - 1, "page_size": [600, 800], "para_blocks": blocks}


def ocr_body():
    # A recovery fixture must represent body coverage, not a single recognized title.
    texts = ["正文如图1.1所示，另见图8.2。"] + [
        "本章介绍实验数据的采集方法和处理过程，并对不同实验条件下的结果开展分析。"
        for _ in range(4)]
    return [text_block(text, (60, 100 + i * 130, 540, 130 + i * 130))
            for i, text in enumerate(texts)]


class SixRuleLayoutRegressions(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "paper.pdf"

    def save(self, document):
        document.save(self.path)
        document.close()

    def image(self):
        source = pymupdf.open()
        page = source.new_page(width=240, height=160)
        page.draw_rect((0, 0, 240, 160), fill=(0.3, 0.5, 0.7))
        png = page.get_pixmap().tobytes("png")
        source.close()
        return png

    def line(self, page, text, y):
        page.insert_text((60, y), text, fontname="china-s", fontsize=12)

    def test_header_only_blank_page_does_not_block_readable_body(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "正文如图9.9所示，详见附录Z。", 100)
        doc.new_page(width=600, height=800).insert_image((415, 10, 510, 40), stream=self.image())
        self.save(doc)
        rules = detect(self.path, [11, 29])["rules"]
        self.assertEqual(rules["11"]["status"], "completed")
        self.assertEqual([f["token"] for f in rules["11"]["findings"]], ["9.9"])
        self.assertEqual([f["token"] for f in rules["29"]["findings"]], ["Z"])

    def test_scanned_body_without_ocr_remains_inconclusive(self):
        doc = pymupdf.open()
        self.line(doc.new_page(width=600, height=800), "正文如图1.1所示。", 100)
        doc.new_page(width=600, height=800).insert_image((30, 50, 570, 750), stream=self.image(), keep_proportion=False)
        self.save(doc)
        self.assertEqual(detect(self.path, [11], token="")["rules"]["11"]["status"], "unsupported")

    def test_ocr_recovers_scanned_reference_without_dropping_original_page(self):
        doc = pymupdf.open()
        doc.new_page(width=600, height=800).insert_image((30, 50, 570, 750), stream=self.image(), keep_proportion=False)
        self.line(doc.new_page(width=600, height=800), "图1.1 正常目标", 100)
        self.save(doc)
        http = LayoutHttp([layout_page(1, ocr_body())])
        rule = detect(self.path, [11], token="fixture-token", http_client=http)["rules"]["11"]
        self.assertEqual(rule["status"], "completed")
        self.assertEqual([(f["token"], f["page"]) for f in rule["findings"]], [("8.2", 1)])

    def test_administrative_form_is_not_a_research_table(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "学位论文答辩决议书", 90)
        self.line(page, "姓名 学号 导师 答辩日期", 140)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [text_block("学位论文答辩决议书"),
                           {"type": "table", "bbox": [60, 130, 540, 650]}])])
        rule = detect(self.path, [14], token="fixture-token", http_client=http)["rules"]["14"]
        self.assertEqual(rule["status"], "completed")
        self.assertEqual(rule["findings"], [])

    def test_title_page_logo_is_not_a_research_figure(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "某大学硕士学位论文", 120)
        self.line(page, "论文题目：机械系统的优化", 260)
        self.line(page, "作者 导师 专业", 400)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [{"type": "image", "bbox": [240, 140, 360, 250]}])])
        self.assertEqual(detect(self.path, [13], token="fixture-token", http_client=http)["rules"]["13"]["findings"], [])

    def test_native_caption_recovers_a_caption_omitted_by_mineru(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "第2章 实验结果", 80)
        self.line(page, "图2.1 实验结果对比", 350)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [{"type": "image", "bbox": [60, 150, 360, 330]}])])
        self.assertEqual(detect(self.path, [13], token="fixture-token", http_client=http)["rules"]["13"]["findings"], [])

    def test_subfigures_share_a_total_caption(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "第2章 实验结果", 80)
        self.line(page, "(a) 输入", 280)
        page.insert_text((320, 280), "(b) 输出", fontname="china-s", fontsize=12)
        self.line(page, "图2.1 对比结果", 320)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [
            {"type": "image", "bbox": [60, 150, 270, 260]},
            {"type": "image", "bbox": [300, 150, 510, 260]},
            text_block("图2.1 对比结果", (60, 305, 400, 325))])])
        self.assertEqual(detect(self.path, [13], token="fixture-token", http_client=http)["rules"]["13"]["findings"], [])

    def test_table_caption_can_be_below_the_table(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "第2章 实验结果", 80)
        self.line(page, "表2.1 结果对比", 350)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [{"type": "table", "bbox": [60, 150, 520, 330]},
                           text_block("表2.1 结果对比", (60, 335, 400, 355))])])
        self.assertEqual(detect(self.path, [14], token="fixture-token", http_client=http)["rules"]["14"]["findings"], [])

    def test_native_image_is_detected_when_mineru_misses_the_object(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "第2章 实验结果", 80)
        page.insert_image((100, 150, 450, 380), stream=self.image())
        self.save(doc)
        http = LayoutHttp([layout_page(1, [text_block("第2章 实验结果")])])
        findings = detect(self.path, [13], token="fixture-token", http_client=http)["rules"]["13"]["findings"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["page"], 1)
        self.assertGreater(findings[0]["location"]["bounding_rect"]["x2"], 400)

    def test_unicode_dash_and_caption_alias_are_not_false_missing_targets(self):
        from pdf_rules.index import build_index
        from pdf_rules.local_rules import detect_rules
        from pdf_rules.model import PdfDocument, PdfLine, PdfPage
        lines = tuple(PdfLine(1, text, (60, y, 500, y + 15), 600, 800) for text, y in [
            ("如图4–3所示。", 100), ("图4-3 结果", 400), ("Figure 4-3 Results", 420)])
        rules = detect_rules(build_index(PdfDocument(self.path, (PdfPage(1, 600, 800, lines),))), [11, 15])
        self.assertEqual(rules["11"]["findings"], [])
        self.assertEqual(rules["15"]["findings"], [])

    def test_native_three_line_table_is_recovered_when_mineru_omits_it(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "第2章 实验结果", 80)
        for y in (200, 225, 300):
            page.draw_line((100, y), (500, y))
        self.line(page, "方法 精度", 220)
        self.line(page, "算法甲 0.8", 255)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [text_block("第2章 实验结果")])])
        findings = detect(self.path, [14], token="fixture-token", http_client=http)["rules"]["14"]["findings"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["page"], 1)
        self.assertAlmostEqual(findings[0]["location"]["bounding_rect"]["y1"], 200, delta=3)

    def test_two_tables_do_not_create_a_third_table_across_the_prose_gap(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        for top in (200, 345):
            for y in range(top, top + 91, 30):
                page.draw_line((80, y), (480, y))
            for x in (80, 280, 480):
                page.draw_line((x, top), (x, top + 90))
            page.insert_text((100, top + 19), "Name", fontsize=10)
            page.insert_text((300, top + 19), "Value", fontsize=10)
            page.insert_text((100, top + 79), "Trial B", fontsize=10)
            page.insert_text((300, top + 79), "13.4", fontsize=10)
        page.insert_text((60, 325), "The next table has intentionally no caption.", fontsize=10)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [
            {"type": "table", "bbox": [80, 200, 480, 290]},
            {"type": "table", "bbox": [80, 345, 480, 435]},
            text_block("Table 1. Reference data", (60, 175, 400, 190))])])
        findings = detect(self.path, [14], token="fixture-token", http_client=http)["rules"]["14"]["findings"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["location"]["bounding_rect"]["y1"], 345)

    def test_barcode_only_ocr_does_not_claim_a_scanned_body_was_read(self):
        doc = pymupdf.open()
        self.line(doc.new_page(width=600, height=800), "正文如图1.1所示。", 100)
        doc.new_page(width=600, height=800).insert_image((30, 50, 570, 750), stream=self.image(), keep_proportion=False)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [text_block("12345678901234", (415, 10, 510, 40))])])
        self.assertEqual(detect(self.path, [11], token="fixture-token", http_client=http)["rules"]["11"]["status"], "unsupported")

    def test_discussion_of_administrative_forms_is_still_research_content(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "第2章 表单识别研究", 80)
        self.line(page, "学位论文答辩决议书的识别方法", 120)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [{"type": "table", "bbox": [60, 150, 520, 350]}])])
        self.assertEqual(len(detect(self.path, [14], token="fixture-token", http_client=http)["rules"]["14"]["findings"]), 1)

    def test_a_table_image_does_not_also_become_a_missing_caption_figure(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "第2章 实验结果", 80)
        self.line(page, "表2.1 对比结果", 140)
        page.insert_image((100, 160, 500, 380), stream=self.image())
        self.save(doc)
        http = LayoutHttp([layout_page(1, [{"type": "table", "bbox": [100, 160, 500, 380]}])])
        self.assertEqual(detect(self.path, [13, 14], token="fixture-token", http_client=http)["rules"]["13"]["findings"], [])

    def test_bilingual_caption_aliases_cannot_cover_two_independent_figures(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "第2章 实验结果", 80)
        page.insert_text((220, 280), "图2.1 结果对比说明", fontname="china-s", fontsize=12)
        page.insert_text((220, 305), "Figure 2.1 Comparison", fontsize=12)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [
            {"type": "image", "bbox": [60, 150, 270, 250]},
            {"type": "image", "bbox": [300, 150, 510, 250]}])])
        findings = detect(self.path, [13], token="fixture-token", http_client=http)["rules"]["13"]["findings"]
        self.assertEqual(len(findings), 1)

    def test_cross_page_subfigures_share_one_caption_with_continuation_evidence(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "第2章 实验结果", 80)
        self.line(page, "(a) 输入", 725)
        page = doc.new_page(width=600, height=800)
        self.line(page, "(b) 输出", 330)
        self.line(page, "图2.1 对比结果", 375)
        self.save(doc)
        http = LayoutHttp([
            layout_page(1, [{"type": "image", "bbox": [60, 460, 510, 705]}]),
            layout_page(2, [{"type": "image", "bbox": [60, 100, 510, 310]}])])
        self.assertEqual(detect(self.path, [13], token="fixture-token", http_client=http)["rules"]["13"]["findings"], [])

    def test_continued_table_requires_matching_column_headers(self):
        doc = pymupdf.open()
        for number, ys in [(1, (90, 320, 365)), (2, (80, 140, 180))]:
            page = doc.new_page(width=600, height=800)
            if number == 1:
                self.line(page, "第2章 实验结果", ys[0])
                self.line(page, "表2.1 对比结果", ys[1])
            page.insert_text((100, ys[2]), "Method", fontsize=12)
            page.insert_text((350, ys[2]), "Accuracy", fontsize=12)
        self.save(doc)
        http = LayoutHttp([
            layout_page(1, [{"type": "table", "bbox": [60, 340, 530, 720]}]),
            layout_page(2, [{"type": "table", "bbox": [60, 160, 530, 400]}])])
        self.assertEqual(detect(self.path, [14], token="fixture-token", http_client=http)["rules"]["14"]["findings"], [])

    def test_local_ocr_uploads_only_missing_pages_and_maps_back_original_page(self):
        doc = pymupdf.open()
        self.line(doc.new_page(width=600, height=800), "第1章 实验结果", 100)
        self.line(doc.new_page(width=600, height=800), "图1.1 正常目标", 100)
        doc.new_page(width=600, height=800).insert_image((30, 50, 570, 750), stream=self.image(), keep_proportion=False)
        self.save(doc)
        # The OCR input is a one-page subset of original PDF page 3.
        http = LayoutHttp([layout_page(1, ocr_body())])
        rule = detect(self.path, [11], token="fixture-token", http_client=http)["rules"]["11"]
        self.assertEqual(rule["status"], "completed")
        self.assertEqual([(f["token"], f["page"]) for f in rule["findings"]], [("8.2", 3)])
        self.assertEqual(http.uploaded_pages, [1])

    def test_narrative_reference_does_not_replace_a_deleted_caption(self):
        for kind, label, rule, sentence in [
                ("image", "图", 13, "图2.1展示了实验结果。"),
                ("table", "表", 14, "表2.1对上述方法进行了对比，说明结果。")]:
            with self.subTest(rule=rule):
                doc = pymupdf.open()
                page = doc.new_page(width=600, height=800)
                self.line(page, "第2章 实验结果", 80)
                self.line(page, sentence, 350)
                self.save(doc)
                http = LayoutHttp([layout_page(1, [{"type": kind, "bbox": [60, 150, 450, 300]}, text_block(sentence, (60, 335, 530, 355))])])
                self.assertEqual(len(detect(self.path, [rule], token="fixture-token", http_client=http)["rules"][str(rule)]["findings"]), 1)
                self.path.unlink()

    def test_compact_chinese_caption_keeps_the_complete_number(self):
        from pdf_rules.index import build_index
        from pdf_rules.model import PdfDocument, PdfLine, PdfPage
        line = PdfLine(1, "图2.1实验结果对比", (60, 320, 400, 340), 600, 800)
        index = build_index(PdfDocument(self.path, (PdfPage(1, 600, 800, (line,)),)))
        self.assertEqual([item.number for item in index.figures], ["2.1"])
        self.assertEqual(index.figure_refs, [])


    def test_native_page_number_does_not_make_scanned_body_readable(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        page.insert_image((30, 50, 570, 750), stream=self.image(), keep_proportion=False)
        page.insert_text((290, 780), "1", fontsize=12)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [text_block("Experimental Results")])])
        rules = detect(self.path, [11, 29], token="fixture-token", http_client=http)["rules"]
        self.assertEqual(rules["11"]["status"], "unsupported")
        self.assertEqual(rules["29"]["status"], "unsupported")
        self.assertEqual(http.uploaded_pages[0], 1)
        self.assertLessEqual(len(http.uploaded_pages), 3)

    def test_only_a_title_from_ocr_leaves_full_scan_inconclusive(self):
        doc = pymupdf.open()
        doc.new_page(width=600, height=800).insert_image((30, 50, 570, 750), stream=self.image(), keep_proportion=False)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [text_block("Experimental Results")])])
        self.assertEqual(detect(self.path, [11], token="fixture-token", http_client=http)["rules"]["11"]["status"], "unsupported")

    def test_large_untitled_figure_is_not_discarded_only_for_its_area(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "第2章 实验结果", 80)
        page.insert_image((30, 100, 570, 760), stream=self.image(), keep_proportion=False)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [text_block("第2章 实验结果", (60, 60, 400, 80))])])
        findings = detect(self.path, [13], token="fixture-token", http_client=http)["rules"]["13"]["findings"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["location"]["bounding_rect"]["y2"], 760)

    def test_restarted_panel_letters_begin_an_independent_figure(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "第2章 实验结果", 80)
        for x, label in [(95, "(a)"), (215, "(b)"), (345, "(a)"), (465, "(b)")]:
            page.insert_text((x, 270), label, fontsize=12)
        page.insert_text((60, 310), "Figure 2.1 First comparison", fontsize=12)
        self.save(doc)
        blocks = [{"type": "image", "bbox": [x, 150, x+110, 250]} for x in (60, 180, 310, 430)]
        http = LayoutHttp([layout_page(1, blocks)])
        findings = detect(self.path, [13], token="fixture-token", http_client=http)["rules"]["13"]["findings"]
        self.assertEqual(len(findings), 1)
        self.assertGreaterEqual(findings[0]["location"]["bounding_rect"]["x1"], 300)

    def test_repeated_table_headers_cannot_bridge_intervening_body_prose(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "表2.1 第一项实验", 580)
        page.insert_text((60, 630), "Method", fontsize=12)
        page.insert_text((350, 630), "Accuracy", fontsize=12)
        page.insert_text((60, 745), "End of first experiment.", fontsize=12)
        page = doc.new_page(width=600, height=800)
        page.insert_text((60, 80), "A separate experiment follows.", fontsize=12)
        page.insert_text((60, 140), "Method", fontsize=12)
        page.insert_text((350, 140), "Accuracy", fontsize=12)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [{"type": "table", "bbox": [60, 600, 530, 720]}]),
                           layout_page(2, [{"type": "table", "bbox": [60, 120, 530, 400]}])])
        findings = detect(self.path, [14], token="fixture-token", http_client=http)["rules"]["14"]["findings"]
        self.assertEqual([f["page"] for f in findings], [2])

    def test_administrative_keywords_in_a_body_sentence_do_not_exclude_page(self):
        doc = pymupdf.open()
        self.line(doc.new_page(width=600, height=800), "第2章 文档识别", 80)
        page = doc.new_page(width=600, height=800)
        self.line(page, "本节对学位论文原创性声明开展版面分析。", 100)
        self.line(page, "如图9.9所示，详见附录Z。", 150)
        self.save(doc)
        rules = detect(self.path, [11, 29])["rules"]
        self.assertEqual([f["token"] for f in rules["11"]["findings"]], ["9.9"])
        self.assertEqual([f["token"] for f in rules["29"]["findings"]], ["Z"])

    def test_a_narrative_table_reference_is_not_a_caption(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "第2章 实验结果", 80)
        self.line(page, "表2.1列出了各算法的实验结果。", 350)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [{"type": "table", "bbox": [60, 150, 450, 300]},
            text_block("表2.1列出了各算法的实验结果。", (60, 335, 530, 355))])])
        rules = detect(self.path, [14, 16], token="fixture-token", http_client=http)["rules"]
        self.assertEqual(len(rules["14"]["findings"]), 1)
        self.assertEqual(rules["16"]["findings"], [])


    def test_subfigure_caption_semicolons_are_preserved(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "第2章 实验结果", 80)
        page.insert_text((60, 345), "Figure 2.1 (a) Input; (b) Output", fontsize=12)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [{"type": "image", "bbox": [60, 150, 510, 300]}])])
        self.assertEqual(detect(self.path, [13], token="fixture-token", http_client=http)["rules"]["13"]["findings"], [])

    def test_two_scanned_strips_are_not_hidden_by_a_native_chapter_heading(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        page.insert_text((60, 90), "Chapter 2 Results", fontsize=12)
        for box in ((30, 140, 570, 420), (30, 440, 570, 720)):
            page.insert_image(box, stream=self.image(), keep_proportion=False)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [text_block("Chapter 2 Results")])])
        rules = detect(self.path, [11, 29], token="fixture-token", http_client=http)["rules"]
        self.assertEqual(rules["11"]["status"], "unsupported")
        self.assertEqual(rules["29"]["status"], "unsupported")
        self.assertEqual(http.uploaded_pages[0], 1)
        self.assertLessEqual(len(http.uploaded_pages), 3)

    def test_an_image_classification_does_not_prove_scanned_text_was_read(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        page.insert_image((30, 50, 570, 750), stream=self.image(), keep_proportion=False)
        page.insert_text((290, 780), "1", fontsize=12)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [{"type": "image", "bbox": [30, 50, 570, 750]}])])
        self.assertEqual(detect(self.path, [11], token="fixture-token", http_client=http)["rules"]["11"]["status"], "unsupported")

    def test_partial_ocr_with_a_large_unread_lower_region_stays_inconclusive(self):
        doc = pymupdf.open()
        doc.new_page(width=600, height=800).insert_image((30, 50, 570, 750), stream=self.image(), keep_proportion=False)
        self.save(doc)
        phrase = "This is a lengthy introductory sentence describing the experiment and its evaluation methods."
        http = LayoutHttp([layout_page(1, [text_block(phrase, (60, 80, 540, 100)),
                                               text_block(phrase, (60, 260, 540, 280))])])
        self.assertEqual(detect(self.path, [11], token="fixture-token", http_client=http)["rules"]["11"]["status"], "unsupported")

    def test_side_column_prose_does_not_break_a_vertical_subfigure_group(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        page.insert_text((95, 275), "(a)", fontsize=12)
        page.insert_text((95, 425), "(b)", fontsize=12)
        page.insert_text((350, 292), "This is a separate side column.", fontsize=12)
        page.insert_text((60, 465), "Figure 2.1 Comparison", fontsize=12)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [{"type": "image", "bbox": [60, 150, 270, 260]},
                                                  {"type": "image", "bbox": [60, 300, 270, 410]}])])
        self.assertEqual(detect(self.path, [13], token="fixture-token", http_client=http)["rules"]["13"]["findings"], [])


    def test_nested_ocr_administrative_title_preserves_its_separate_lines(self):
        doc = pymupdf.open()
        self.line(doc.new_page(width=600, height=800), "第1章 实验方法", 100)
        doc.new_page(width=600, height=800).insert_image((30, 50, 570, 750), stream=self.image(), keep_proportion=False)
        self.save(doc)
        title = "示例研究大学博士学位论文答辩决议书"
        nested = {"type": "image_caption", "bbox": [150, 30, 500, 85], "lines": [
            {"bbox": [420, 30, 490, 40], "spans": [{"type": "text", "content": "12345678901234"}]},
            {"bbox": [150, 60, 450, 84], "spans": [{"type": "text", "content": title}]}]}
        http = LayoutHttp([layout_page(1, [text_block("第1章 实验方法")]), layout_page(2, [
            {"type": "image", "bbox": [420, 10, 510, 40], "blocks": [nested]},
            {"type": "table", "bbox": [60, 100, 530, 720]}])])
        rules = detect(self.path, [11, 13, 14, 29], token="fixture-token", http_client=http)["rules"]
        for rule in rules.values():
            self.assertEqual(rule["status"], "completed")
            self.assertEqual(rule["findings"], [])

    def test_standalone_degree_administrative_title_is_not_a_research_table(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "示例研究大学硕士学位论文答辩决议书", 90)
        self.line(page, "姓名 学号 指导教师 答辩日期", 140)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [{"type": "table", "bbox": [60, 130, 540, 650]}])])
        self.assertEqual(detect(self.path, [14], token="fixture-token", http_client=http)["rules"]["14"]["findings"], [])


    def test_ocr_soft_wrap_within_one_paragraph_preserves_references(self):
        doc = pymupdf.open()
        doc.new_page(width=600, height=800).insert_image((30, 50, 570, 750), stream=self.image(), keep_proportion=False)
        self.save(doc)
        texts = [
            "本章介绍实验数据采集的设置和评估标准，并参考图",
            "9.9的异常数据。这里继续描述采集方法与实验过程。",
            "实验结果说明了各种因素对于最终性能的影响，需要独立核实。",
            "这里继续讨论实验条件下的数据处理与重建流程，详见附录",
            "Z。这里继续说明各项实验操作和最终评价的具体方法。"]
        lines = [{"bbox": [60, 100+i*130, 540, 130+i*130], "spans": [{"type": "text", "content": text}]}
                 for i, text in enumerate(texts)]
        block = {"type": "text", "bbox": [60, 100, 540, 650], "lines": lines}
        http = LayoutHttp([layout_page(1, [block])])
        rules = detect(self.path, [11, 29], token="fixture-token", http_client=http)["rules"]
        self.assertEqual(rules["11"]["status"], "completed")
        self.assertEqual([f["token"] for f in rules["11"]["findings"]], ["9.9"])
        self.assertEqual([f["token"] for f in rules["29"]["findings"]], ["Z"])


    def test_legitimate_caption_can_end_with_a_chinese_full_stop(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "如图2.1所示，见表2.1。", 100)
        self.line(page, "图2.1 模型架构。", 350)
        self.line(page, "表2.1 实验数据。", 450)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [
            {"type": "image", "bbox": [60, 150, 510, 330]},
            {"type": "table", "bbox": [60, 470, 510, 640]}])])
        rules = detect(self.path, [11, 13, 14, 15, 16], token="fixture-token", http_client=http)["rules"]
        for rule in rules.values():
            self.assertEqual(rule["status"], "completed")
            self.assertEqual(rule["findings"], [])


    def test_native_caption_label_and_title_in_separate_spans_form_one_caption(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        page.insert_text((60, 100), "See Figure 2.1 for the comparison.", fontsize=12)
        page.insert_text((200, 350), "Figure 2.1", fontname="helv", fontsize=12)
        page.insert_text((280, 350), "Comparison results.", fontname="tiro", fontsize=10.5)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [{"type": "image", "bbox": [60, 150, 510, 330]}])])
        rules = detect(self.path, [11, 13, 15], token="fixture-token", http_client=http)["rules"]
        for rule in rules.values():
            self.assertEqual(rule["status"], "completed")
            self.assertEqual(rule["findings"], [])


    def test_table_cell_label_is_not_merged_into_a_caption(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        for y in (200, 225, 300):
            page.draw_line((80, y), (500, y))
        page.insert_text((100, 220), "Table 2.1", fontname="helv", fontsize=12)
        page.insert_text((180, 220), "0.95", fontname="tiro", fontsize=10.5)
        page.insert_text((100, 255), "A numeric comparison cell", fontsize=12)
        self.save(doc)
        self.assertEqual(detect(self.path, [16])["rules"]["16"]["findings"], [])


    def test_paragraph_envelope_does_not_hide_a_large_gap_in_actual_ocr_lines(self):
        doc = pymupdf.open()
        doc.new_page(width=600, height=800).insert_image((30, 50, 570, 750), stream=self.image(), keep_proportion=False)
        self.save(doc)
        text = "这里介绍实验数据收集处理的方法和实验评价的设置，分析各个条件下的影响并详细说明结果。"
        block = {"type": "text", "bbox": [60, 100, 540, 650], "lines": [
            {"bbox": [60, 100, 540, 130], "spans": [{"type": "text", "content": text}]},
            {"bbox": [60, 620, 540, 650], "spans": [{"type": "text", "content": text}]}]}
        http = LayoutHttp([layout_page(1, [block])])
        rules = detect(self.path, [11, 29], token="fixture-token", http_client=http)["rules"]
        self.assertEqual(rules["11"]["status"], "unsupported")
        self.assertEqual(rules["29"]["status"], "unsupported")

    def test_captioned_native_composite_figure_is_not_unread_scanned_prose(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "第2章 实验结果", 70)
        page.insert_image((80, 100, 520, 700), stream=self.image(), keep_proportion=False)
        self.line(page, "图2.1 多组实验结果", 730)
        self.save(doc)
        blocks = [{"type": "image", "bbox": [x, 100, x+100, 695]} for x in (80, 190, 300, 410)]
        http = LayoutHttp([layout_page(1, blocks)])
        rule = detect(self.path, [11], token="fixture-token", http_client=http)["rules"]["11"]
        self.assertEqual(rule["status"], "completed")
        self.assertEqual(rule["findings"], [])

    def test_native_caption_does_not_resolve_a_full_page_scan_classified_as_image(self):
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        page.insert_image((10, 10, 590, 780), stream=self.image(), keep_proportion=False)
        self.line(page, "图2.1 实验结果", 795)
        self.save(doc)
        http = LayoutHttp([layout_page(1, [{"type": "image", "bbox": [10, 10, 590, 780]}])])
        self.assertEqual(detect(self.path, [11], token="fixture-token", http_client=http)["rules"]["11"]["status"], "unsupported")

    def test_images_outside_the_page_are_clipped_before_ocr_coverage(self):
        from pdf_rules.pdf_extract import extract_pdf
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "这是能够完整提取的原生正文，见附录Z。", 200)
        page.insert_image((80, -600, 520, 40), stream=self.image(), keep_proportion=False)
        self.save(doc)
        extracted = extract_pdf(self.path).pages[0]
        self.assertEqual(extracted.images, ((80.0, 0.0, 520.0, 40.0),))
        self.assertFalse(extracted.unreadable)

    def test_table_html_preserves_semantics_without_claiming_ocr_line_coverage(self):
        from pdf_rules.mineru_layout import normalize_layout
        body = {"type": "table_body", "bbox": [60, 100, 540, 650], "lines": [
            {"bbox": [60, 100, 540, 650], "spans": [{"type": "table", "html": "<table><tr><td>见附录Z</td><td>图9.9</td></tr></table>"}]}]}
        objects = normalize_layout([layout_page(1, [{"type": "table", "bbox": [60, 100, 540, 650], "blocks": [body]}])], 1, [(600, 800)])
        self.assertTrue(any("见附录Z" in obj.text for obj in objects))
        self.assertTrue(all(not obj.text_lines for obj in objects))

    def test_decision_form_with_a_truncated_title_is_excluded_by_its_structured_fields(self):
        doc = pymupdf.open()
        self.line(doc.new_page(width=600, height=800), "第1章 实验方法", 100)
        doc.new_page(width=600, height=800).insert_image((30, 50, 570, 750), stream=self.image(), keep_proportion=False)
        self.save(doc)
        html = "<table><tr><td>姓名</td><td>学号</td><td>论文题目</td></tr><tr><td>答辩日期</td><td>投票表决结果</td><td>答辩结论</td></tr><tr><td>答辩委员会工作职务</td><td>主席</td><td>委员</td></tr></table>"
        table = {"type": "table", "bbox": [60, 100, 540, 710], "blocks": [{"type": "table_body", "bbox": [60, 100, 540, 710], "lines": [{"bbox": [60, 100, 540, 710], "spans": [{"type": "table", "html": html}]}]}]}
        http = LayoutHttp([layout_page(1, [text_block("第1章 实验方法")]), layout_page(2, [text_block("示例大学硕士学位论文答辩", (80, 60, 520, 85)), table])])
        rules = detect(self.path, [11, 14, 29], token="fixture-token", http_client=http)["rules"]
        for rule in rules.values():
            self.assertEqual(rule["status"], "completed")
            self.assertEqual(rule["findings"], [])

    def test_a_research_table_mentioning_a_single_form_field_is_not_excluded(self):
        from pdf_rules.layout_context import nonresearch_page
        from pdf_rules.model import PdfPage, PdfLine
        page = PdfPage(1, 600, 800, (PdfLine(1, "调查统计: 答辩日期与学生表现的关系，见附录Z。", (60, 100, 540, 120), 600, 800),))
        self.assertFalse(nonresearch_page(page))

    def test_committee_signature_continuation_requires_the_preceding_decision_form(self):
        from pdf_rules.layout_context import research_document
        from pdf_rules.model import PdfPage, PdfLine, PdfDocument
        form = PdfPage(1, 600, 800, (PdfLine(1, "答辩日期 论文题目 答辩结论 答辩委员会工作职务 姓名 学号", (60, 80, 540, 600), 600, 800, role="table_body"),))
        continuation = PdfPage(2, 600, 800, (PdfLine(2, "主席 委员 委员 委员 委员 秘书", (60, 80, 540, 350), 600, 800),), unreadable=True, ink_bottom=350)
        recovered = research_document(PdfDocument(self.path, (form, continuation)))
        self.assertFalse(recovered.pages[1].unreadable)
        self.assertEqual(recovered.pages[1].lines, ())
        standalone = research_document(PdfDocument(self.path, (continuation,)))
        self.assertTrue(standalone.pages[0].unreadable)

    def test_a_large_image_clipped_to_a_small_panel_does_not_require_body_ocr(self):
        from pdf_rules.pdf_extract import extract_pdf
        source = pymupdf.open()
        source.new_page(width=600, height=800).insert_image((0, 0, 600, 800), stream=self.image(), keep_proportion=False)
        doc = pymupdf.open()
        page = doc.new_page(width=600, height=800)
        self.line(page, "第2章 实验结果，见附录Z。", 350)
        page.show_pdf_page(pymupdf.Rect(100, 100, 500, 200), source, 0, clip=pymupdf.Rect(0, 0, 600, 150))
        self.save(doc)
        source.close()
        extracted = extract_pdf(self.path).pages[0]
        self.assertFalse(extracted.unreadable)
        self.assertAlmostEqual(extracted.images[0][3], 200, delta=1)

    def test_one_secretary_signature_row_requires_a_verified_previous_decision_form(self):
        from pdf_rules.layout_context import research_document
        from pdf_rules.model import PdfPage, PdfLine, PdfDocument
        form = PdfPage(1, 600, 800, (PdfLine(1, "答辩日期 论文题目 答辩结论 答辩委员会工作职务 姓名", (60, 80, 540, 600), 600, 800, role="table_body"),))
        continuation = PdfPage(2, 600, 800, (PdfLine(2, "秘书 李同学 计算机学院", (60, 65, 540, 110), 600, 800),), unreadable=True, ink_bottom=110)
        self.assertFalse(research_document(PdfDocument(self.path, (form, continuation))).pages[1].unreadable)
        self.assertTrue(research_document(PdfDocument(self.path, (continuation,))).pages[0].unreadable)

    def test_incomplete_vlm_scan_is_recovered_using_forced_pipeline_ocr(self):
        class RecoveryHttp(LayoutHttp):
            def request(self, method, url, **kw):
                if method == "POST":
                    self.forced = json.loads(kw["data"])["model_version"] == "pipeline"
                self.pages = [layout_page(1, ocr_body() if getattr(self, "forced", False) else [text_block("Experimental Results")])]
                return super().request(method, url, **kw)
        doc = pymupdf.open()
        doc.new_page(width=600, height=800).insert_image((30, 50, 570, 750), stream=self.image(), keep_proportion=False)
        self.save(doc)
        rule = detect(self.path, [11], token="fixture-token", http_client=RecoveryHttp([]))["rules"]["11"]
        self.assertEqual(rule["status"], "completed")
        self.assertEqual([f["token"] for f in rule["findings"]], ["1.1", "8.2"])

    def test_ocr_subsets_of_identical_source_pages_have_stable_cache_bytes(self):
        from hashlib import sha256
        class HashHttp(LayoutHttp):
            def request(self, method, url, **kw):
                if method == "PUT":
                    self.hashes.append(sha256(kw["data"]).hexdigest())
                return super().request(method, url, **kw)
        doc = pymupdf.open()
        self.line(doc.new_page(width=600, height=800), "第1章 实验方法", 100)
        doc.new_page(width=600, height=800).insert_image((30, 50, 570, 750), stream=self.image(), keep_proportion=False)
        self.save(doc)
        http = HashHttp([layout_page(1, ocr_body())]); http.hashes = []
        detect(self.path, [11], token="fixture-token", http_client=http)
        detect(self.path, [11], token="fixture-token", http_client=http)
        self.assertEqual(http.hashes[0], http.hashes[1])

    def test_ocr_tiles_map_boxes_to_the_original_page_without_modifying_it(self):
        from pdf_rules.engine import _ocr_missing_pages
        from pdf_rules.pdf_extract import extract_pdf
        from hashlib import sha256
        doc = pymupdf.open()
        doc.new_page(width=600, height=800).insert_image((30, 50, 570, 750), stream=self.image(), keep_proportion=False)
        self.save(doc)
        before = sha256(self.path.read_bytes()).hexdigest()
        pages = [{"page_idx": i, "page_size": [600, h], "para_blocks": [text_block("见附录Z。", (60, 50, 540, 70))]}
                 for i, h in enumerate((360, 360, 320))]
        objects = _ocr_missing_pages(self.path, extract_pdf(self.path), "fixture-token", LayoutHttp(pages), force_ocr=True, tiled=True)
        self.assertEqual([obj.page_number for obj in objects], [1, 1, 1])
        self.assertEqual(objects[-1].bbox, (60.0, 530.0, 540.0, 550.0))
        self.assertEqual(objects[-1].page_height, 800)
        self.assertEqual(sha256(self.path.read_bytes()).hexdigest(), before)

    def test_all_ocr_recovery_passes_share_one_request_deadline(self):
        from unittest.mock import patch
        from pdf_rules.mineru_layout import LayoutObject
        doc = pymupdf.open()
        doc.new_page(width=600, height=800).insert_image((30, 50, 570, 750), stream=self.image(), keep_proportion=False)
        self.save(doc)
        title = LayoutObject("text", 1, (60, 70, 540, 90), "Experimental Results", 600, 800, "title")
        from pdf_rules.signature_ocr import recover_signature_pages
        with patch("pdf_rules.engine.monotonic", side_effect=[0, 1, 420, 840, 1005], create=True), patch("pdf_rules.engine.parse_layout", return_value=[title]) as parser, patch("pdf_rules.signature_ocr.recover_signature_pages", wraps=recover_signature_pages) as cpu:
            rule = detect(self.path, [11], token="fixture-token")["rules"]["11"]
        self.assertEqual(rule["status"], "unsupported")
        budgets = [call.kwargs.get("max_seconds", 1020) for call in parser.call_args_list]
        self.assertEqual(budgets, [419, 240])
        # At t=840 the remaining 180 seconds belong to CPU recovery;
        # another network pass cannot borrow that budget.
        self.assertEqual(cpu.call_args.kwargs["max_seconds"], 15)

    def test_rotated_pdf_keeps_native_geometry_and_ocr_crop_in_one_coordinate_frame(self):
        from pdf_rules.pdf_extract import extract_pdf
        from pdf_rules.engine import _ocr_missing_pages
        from hashlib import sha256
        doc = pymupdf.open()
        page = doc.new_page(width=800, height=600)
        page.insert_image((20, 50, 780, 550), stream=self.image(), keep_proportion=False)
        page.set_rotation(90)
        self.save(doc)
        before = sha256(self.path.read_bytes()).hexdigest()
        extracted = extract_pdf(self.path)
        self.assertEqual((extracted.pages[0].width, extracted.pages[0].height), (800, 600))
        self.assertEqual(extracted.pages[0].images, ((20, 50, 780, 550),))
        pages = [{"page_idx": i, "page_size": [800, h], "para_blocks": [text_block("实验结果。", (60, 50, 540, 70))]}
                 for i, h in enumerate((270, 270, 240))]
        objects = _ocr_missing_pages(self.path, extracted, "fixture-token", LayoutHttp(pages), force_ocr=True, tiled=True)
        self.assertEqual(objects[-1].bbox, (60, 410, 540, 430))
        self.assertEqual(sha256(self.path.read_bytes()).hexdigest(), before)

    def test_repeated_recovery_never_promotes_an_ocr_caption_to_native_evidence(self):
        from pdf_rules.model import PdfDocument, PdfPage
        from pdf_rules.mineru_layout import LayoutObject
        from pdf_rules.layout_context import recover_document
        doc = PdfDocument(self.path, (PdfPage(1, 600, 800, (), unreadable=True, images=((80, 100, 520, 700),)),))
        objects = [LayoutObject("figure", 1, (80, 100, 520, 700), "", 600, 800),
                   LayoutObject("figure_caption", 1, (80, 715, 520, 735), "图2.1 实验示例", 600, 800)]
        first = recover_document(doc, objects)
        self.assertTrue(first.pages[0].unreadable)
        self.assertTrue(recover_document(first, objects).pages[0].unreadable)

    def test_admin_form_field_names_in_a_research_table_do_not_exclude_the_page(self):
        from pdf_rules.model import PdfPage, PdfLine
        from pdf_rules.layout_context import nonresearch_page
        lines = [PdfLine(1, text, (60, y, 540, y+20), 600, 800) for text,y in [
            ("表2.1 表单识别字段与分类结果", 85),
            ("字段包括姓名、论文题目、答辩日期、答辩结论、答辩委员会工作职务。", 130),
            ("如图9.9所示，详见附录Z。", 200)]]
        self.assertFalse(nonresearch_page(PdfPage(1, 600, 800, tuple(lines))))

    def test_a_signature_row_cannot_hide_unread_scanned_body_below_it(self):
        from pdf_rules.model import PdfDocument, PdfPage, PdfLine
        from pdf_rules.layout_context import research_document
        form = PdfPage(1, 600, 800, (PdfLine(1, "答辩日期 论文题目 答辩结论 答辩委员会工作职务 姓名", (60, 80, 540, 600), 600, 800, role="table_body"),))
        page = PdfPage(2, 600, 800, (PdfLine(2, "秘书 李同学 计算机学院", (60, 65, 540, 110), 600, 800),), unreadable=True, images=((30, 200, 570, 750),))
        self.assertTrue(research_document(PdfDocument(self.path, (form, page))).pages[1].unreadable)

    def test_ocr_recovery_replaces_old_paragraphs_instead_of_duplicating_one_reference(self):
        class RecoveryHttp(LayoutHttp):
            def request(self, method, url, **kw):
                if method == "POST":
                    self.forced = json.loads(kw["data"])["model_version"] == "pipeline"
                blocks = [text_block("正文如图9.9所示。", (60, 100, 540, 130))]
                if getattr(self, "forced", False):
                    blocks = ocr_body()
                    blocks[0] = text_block("正文如图9.9所示，下面继续介绍实验过程。", (60, 100, 540, 130))
                self.pages = [layout_page(1, blocks)]
                return super().request(method, url, **kw)
        doc = pymupdf.open()
        doc.new_page(width=600, height=800).insert_image((30, 50, 570, 750), stream=self.image(), keep_proportion=False)
        self.save(doc)
        findings = detect(self.path, [11], token="fixture-token", http_client=RecoveryHttp([]))["rules"]["11"]["findings"]
        self.assertEqual([f["token"] for f in findings], ["9.9"])

    def test_rotated_pdf_findings_use_the_original_display_page_coordinates(self):
        doc = pymupdf.open()
        page = doc.new_page(width=800, height=600)
        page.insert_text((60, 100), "See Figure 9.9 for the experiment.", fontsize=12)
        page.set_rotation(90)
        self.save(doc)
        with pymupdf.open(self.path) as original:
            native = original[0].search_for("9.9")[0]
            expected = pymupdf.Rect(native) * original[0].rotation_matrix
        found = detect(self.path, [11])["rules"]["11"]["findings"][0]["location"]["bounding_rect"]
        self.assertEqual((found["width"], found["height"]), (600, 800))
        for key, value in zip(("x1", "y1", "x2", "y2"), expected):
            self.assertAlmostEqual(found[key], value, delta=.01)

    def test_faint_scanned_body_is_not_blank_below_a_signature_row(self):
        from dataclasses import replace
        from pdf_rules.pdf_extract import extract_pdf
        from pdf_rules.model import PdfDocument, PdfPage, PdfLine
        from pdf_rules.layout_context import recover_document, research_document
        from pdf_rules.mineru_layout import LayoutObject
        source = pymupdf.open()
        page = source.new_page(width=600, height=800)
        page.insert_text((60, 100), "Secretary signed here", fontsize=12)
        for y in range(430, 691, 30):
            page.insert_text((60, y), "Faint research body includes an unresolved reference to Figure 9.9.", fontsize=12, color=(.87, .87, .87))
        png = page.get_pixmap().tobytes("png")
        source.close()
        doc = pymupdf.open()
        doc.new_page(width=600, height=800).insert_image((0, 0, 600, 800), stream=png)
        self.save(doc)
        scanned = replace(extract_pdf(self.path).pages[0], number=2)
        self.assertGreater(scanned.ink_bottom, 400)
        form = PdfPage(1, 600, 800, (PdfLine(1, "答辩日期 论文题目 答辩结论 答辩委员会工作职务 姓名", (60, 80, 540, 600), 600, 800, role="table_body"),))
        evidence = [LayoutObject("text", 2, (60, 85, 300, 105), "秘书 李同学 计算机学院", 600, 800)]
        recovered = recover_document(PdfDocument(self.path, (form, scanned)), evidence)
        self.assertTrue(research_document(recovered).pages[1].unreadable)

    def test_sideways_originality_declaration_uses_title_and_legal_body(self):
        from pdf_rules.layout_context import nonresearch_page
        from pdf_rules.model import PdfPage, PdfLine
        lines = (
            PdfLine(1, "学位论文原创性声明", (110, 201, 138, 355), 842, 595, source="mineru", role="title"),
            PdfLine(1, "本人郑重声明：所呈交的学位论文，是本人在导师的指导下独立完成。本声明的法律结果由本人承担。", (151, 65, 253, 517), 842, 595, source="mineru", role="text"),
        )
        self.assertTrue(nonresearch_page(PdfPage(1, 842, 595, lines, unreadable=True)))

    def test_administrative_words_quoted_in_research_do_not_exclude_it(self):
        from pdf_rules.layout_context import nonresearch_page
        from pdf_rules.model import PdfPage, PdfLine
        title = PdfLine(1, "学位论文原创性声明", (110, 201, 138, 355), 842, 595, source="mineru", role="title")
        body = PdfLine(1, "调查比较不同原创性声明中的文字格式，见附录Z。", (151, 65, 253, 517), 842, 595)
        self.assertFalse(nonresearch_page(PdfPage(1, 842, 595, (title, body), unreadable=True)))

    def test_degree_approval_form_is_recognized_by_multiple_structured_fields(self):
        from pdf_rules.layout_context import nonresearch_page
        from pdf_rules.model import PdfPage, PdfLine
        table = PdfLine(1, "论文评审 选题与综述 总体评价 校抽检 院明审 答辩委员会成员 职务 姓名 工作单位 答辩审批意见 指导教师意见 学位评定分委员会意见", (60, 120, 540, 700), 600, 800, source="mineru", role="table_body")
        self.assertTrue(nonresearch_page(PdfPage(1, 600, 800, (table,), unreadable=True)))

    def test_research_table_with_approval_keywords_is_not_an_admin_form(self):
        from pdf_rules.layout_context import nonresearch_page
        from pdf_rules.model import PdfPage, PdfLine
        table = PdfLine(1, "论文评审 选题与综述 总体评价 校抽检 院明审 答辩委员会成员 职务 姓名 工作单位 答辩审批意见 指导教师意见 学位评定分委员会意见", (60, 120, 540, 700), 600, 800, source="mineru", role="table_body")
        caption = PdfLine(1, "表2.1 审批字段分类结果", (60, 90, 300, 110), 600, 800)
        self.assertFalse(nonresearch_page(PdfPage(1, 600, 800, (table, caption), unreadable=True)))

    def test_ocr_grid_tiles_map_both_column_and_row_offsets(self):
        from pdf_rules.engine import _ocr_missing_pages
        from pdf_rules.pdf_extract import extract_pdf
        from hashlib import sha256
        doc = pymupdf.open()
        doc.new_page(width=600, height=800).insert_image((30, 50, 570, 750), stream=self.image(), keep_proportion=False)
        self.save(doc)
        before = sha256(self.path.read_bytes()).hexdigest()
        pages = [{"page_idx": i, "page_size": [390, h], "para_blocks": [text_block("实验方法。", (20, 30, 100, 50))]}
                 for i, h in enumerate((360, 360, 360, 360, 320, 320))]
        objects = _ocr_missing_pages(self.path, extract_pdf(self.path), "fixture-token", LayoutHttp(pages), force_ocr=True, tiled="grid")
        self.assertEqual(objects[-1].bbox, (230, 510, 310, 530))
        self.assertEqual(objects[-1].page_number, 1)
        self.assertEqual((objects[-1].page_width, objects[-1].page_height), (600, 800))
        self.assertEqual(sha256(self.path.read_bytes()).hexdigest(), before)

    def test_full_legal_declaration_quoted_in_portrait_research_is_not_excluded(self):
        from pdf_rules.layout_context import nonresearch_page
        from pdf_rules.model import PdfPage, PdfLine
        texts = ["本节比较不同高校的声明格式，下面摘录一段样本文本。", "学位论文原创性声明",
                 "本人郑重声明：所呈交的学位论文，是本人独立完成。本声明的法律结果由本人承担。",
                 "上述措辞的分类结果如图9.9所示。"]
        lines = tuple(PdfLine(1, text, (60, y, 540, y+20), 600, 800) for text,y in zip(texts,(100,350,400,500)))
        self.assertFalse(nonresearch_page(PdfPage(1, 600, 800, lines)))

    def test_sideways_research_quoting_legal_statement_preserves_its_reference(self):
        from pdf_rules.layout_context import nonresearch_page
        from pdf_rules.model import PdfPage, PdfLine
        lines = (
            PdfLine(1, "学位论文原创性声明", (110, 201, 138, 355), 842, 595, source="mineru", role="title"),
            PdfLine(1, "本人郑重声明：所呈交的学位论文，本声明的法律結果由本人承担。", (151, 65, 253, 517), 842, 595),
            PdfLine(1, "上述分类结果如图9.9所示。", (310, 65, 330, 517), 842, 595),
        )
        self.assertFalse(nonresearch_page(PdfPage(1, 842, 595, lines, unreadable=True)))

    def test_overlapping_ocr_tiles_cannot_inflate_sparse_body_coverage(self):
        from pdf_rules.model import PdfDocument, PdfPage
        from pdf_rules.mineru_layout import LayoutObject
        from pdf_rules.layout_context import recover_document
        page = PdfPage(1, 600, 800, (), unreadable=True, images=((30, 50, 570, 750),))
        objects = []
        for y in (100, 270, 330, 510, 640):
            box = (250, y, 330, y+20)
            for _ in range(4):
                objects.append(LayoutObject("text", 1, box, "SPARSE.", 600, 800, "text", (("SPARSE.", box),)))
        recovered = recover_document(PdfDocument(self.path, (page,)), objects).pages[0]
        self.assertEqual(len(recovered.lines), 5)
        self.assertTrue(recovered.unreadable)
