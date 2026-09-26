"""Known-answer development PDFs; live MinerU test is opt-in."""
import os
import tempfile
import unittest
from pathlib import Path

import pymupdf

from pdf_rules.engine import detect


class SixRuleRealPdfTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def test_local_rules_have_positive_and_negative_examples(self):
        path = Path(self.directory.name) / "local.pdf"
        document = pymupdf.open()
        for lines in (
            ["第1章 绪论", "如图1.1所示，见表1.1，详见附录A。",
             "图1.1 已引用的图", "表1.1 已引用的表",
             "如图9.9所示，详见附录Z。"],
            ["图2.2 未引用的图", "表2.2 未引用的表", "附录A 实验材料"],
        ):
            page = document.new_page()
            for index, line in enumerate(lines):
                page.insert_text((60, 90 + 35 * index), line, fontname="china-s", fontsize=12)
        document.save(path)
        document.close()
        result = detect(path, [11, 15, 16, 29])["rules"]
        for number in (11, 15, 16, 29):
            self.assertEqual(result[str(number)]["status"], "completed")
            self.assertEqual(len(result[str(number)]["findings"]), 1, str(result[str(number)]))
            item = result[str(number)]["findings"][0]
            self.assertGreaterEqual(item["page"], 1)
            rect = item["location"]["bounding_rect"]
            self.assertLess(rect["x1"], rect["x2"])
            self.assertLess(rect["y1"], rect["y2"])

    @unittest.skipUnless(os.getenv("RUN_MINERU_API_TESTS") == "1" and os.getenv("MINERU_API_TOKEN"),
                         "Live MinerU test requires explicit environment opt-in")
    def test_live_mineru_figures_tables_and_original_bboxes(self):
        chart_doc = pymupdf.open()
        chart_page = chart_doc.new_page(width=360, height=160)
        chart_page.draw_rect(pymupdf.Rect(0, 0, 360, 160), fill=(0.95, 0.97, 1))
        for x, color, height in [(50, (0.1, 0.4, 0.9), 80), (120, (0.0, 0.6, 0.5), 110),
                                 (190, (0.9, 0.5, 0.1), 65), (260, (0.6, 0.2, 0.7), 125)]:
            chart_page.draw_rect(pymupdf.Rect(x, 145-height, x+35, 145), fill=color)
        chart_page.insert_text((15, 20), "Measured output", fontsize=11)
        png = chart_page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes("png")
        chart_doc.close()

        path = Path(self.directory.name) / "layout.pdf"
        document = pymupdf.open()
        page = document.new_page(width=595, height=842)
        page.insert_text((60, 60), "DEVELOPMENT FIXTURE: FIGURE AND TABLE CAPTIONS", fontsize=14)
        page.insert_text((60, 100), "The following chart is discussed in Figure 1.", fontsize=10)
        page.insert_text((60, 150), "Figure 1. Measured output with its caption.", fontsize=11)
        page.insert_image(pymupdf.Rect(80, 165, 440, 310), stream=png)
        page.insert_text((60, 335), "A second chart has intentionally no caption.", fontsize=10)
        page.insert_image(pymupdf.Rect(80, 345, 440, 490), stream=png)
        page.insert_text((60, 510), "Table 1. Reference measurements.", fontsize=11)
        for top in (525, 670):
            for y in range(top, top+91, 30):
                page.draw_line((80, y), (480, y), color=(0, 0, 0))
            for x in (80, 280, 480):
                page.draw_line((x, top), (x, top+90), color=(0, 0, 0))
            page.insert_text((100, top+19), "Name", fontsize=10)
            page.insert_text((300, top+19), "Value", fontsize=10)
            page.insert_text((100, top+49), "Trial A", fontsize=10)
            page.insert_text((300, top+49), "12.5", fontsize=10)
            page.insert_text((100, top+79), "Trial B", fontsize=10)
            page.insert_text((300, top+79), "13.4", fontsize=10)
        page.insert_text((60, 650), "The next table has intentionally no caption.", fontsize=10)
        document.save(path)
        document.close()

        result = detect(path, [13, 14])["rules"]
        self.assertEqual(result["13"]["status"], "completed")
        self.assertEqual(result["14"]["status"], "completed")
        self.assertEqual(len(result["13"]["findings"]), 1)
        self.assertEqual(len(result["14"]["findings"]), 1)
        self.assertEqual(result["13"]["findings"][0]["location"]["bounding_rect"]["page_number"], 1)
        self.assertGreater(result["13"]["findings"][0]["location"]["bounding_rect"]["y1"], 300)
        self.assertGreater(result["14"]["findings"][0]["location"]["bounding_rect"]["y1"], 600)

