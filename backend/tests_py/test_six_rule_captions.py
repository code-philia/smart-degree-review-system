import unittest

from pdf_rules.caption_rules import detect_caption_rules
from pdf_rules.mineru_layout import LayoutObject, normalize_layout


def obj(kind, page, bbox, text=""):
    return LayoutObject(kind, page, bbox, text, 600.0, 800.0)


class CaptionRuleTests(unittest.TestCase):
    def test_missing_captions(self):
        objects = [
            obj("figure", 2, (50, 100, 250, 260)),
            obj("figure", 2, (320, 100, 520, 260)),
            obj("table", 3, (50, 100, 550, 300)),
        ]
        result = detect_caption_rules(objects, [13, 14])
        self.assertEqual(len(result["13"]["findings"]), 2)
        self.assertEqual(len(result["14"]["findings"]), 1)
        self.assertNotEqual(result["13"]["findings"][0]["location"]["bounding_rect"]["x1"],
                            result["13"]["findings"][1]["location"]["bounding_rect"]["x1"])
        self.assertEqual(result["14"]["findings"][0]["page"], 3)

    def test_cross_page_continuation_and_decoration(self):
        objects = [
            obj("figure", 1, (80, 650, 500, 790)),
            obj("figure_caption", 2, (80, 15, 500, 35), "图 2 跨页示例"),
            obj("table_caption", 2, (70, 300, 400, 320), "续表 3"),
            obj("table", 2, (70, 330, 520, 620)),
            obj("decoration", 2, (10, 10, 30, 30)),
        ]
        result = detect_caption_rules(objects, [13, 14])
        self.assertEqual(result["13"]["findings"], [])
        self.assertEqual(result["14"]["findings"], [])

    def test_real_mineru_nested_chart_and_misclassified_captions(self):
        def caption(kind, box, text):
            return {"type": kind, "bbox": box, "lines": [{"spans": [{"content": text}]}]}
        pages = [{"page_idx": 0, "page_size": [595, 842], "para_blocks": [
            {"type": "chart", "bbox": [95, 162, 423, 310], "blocks": [
                caption("chart_caption", [57, 138, 268, 154], "Figure 1. Measured output"),
                {"type": "chart_body", "bbox": [95, 162, 423, 310]}]},
            {"type": "chart", "bbox": [95, 343, 423, 490], "blocks": [
                {"type": "chart_body", "bbox": [95, 343, 423, 490]},
                caption("chart_caption", [57, 499, 233, 513], "Table 1. Measurements")]},
            {"type": "table", "bbox": [78, 522, 480, 614], "blocks": [
                {"type": "table_body", "bbox": [78, 522, 480, 614]}]},
            {"type": "table", "bbox": [78, 667, 480, 759], "blocks": [
                caption("table_caption", [57, 639, 251, 654], "The next table has no caption"),
                {"type": "table_body", "bbox": [78, 667, 480, 759]}]},
        ]}]
        objects = normalize_layout(pages, 1, [(595.0, 842.0)])
        result = detect_caption_rules(objects, [13, 14])
        self.assertEqual([f["location"]["bounding_rect"]["y1"] for f in result["13"]["findings"]], [343.0])
        self.assertEqual([f["location"]["bounding_rect"]["y1"] for f in result["14"]["findings"]], [667.0])
    def test_missing_layout_is_inconclusive(self):
        result = detect_caption_rules([], [13, 14])
        self.assertEqual(result["13"]["status"], "unsupported")
        self.assertEqual(result["14"]["status"], "unsupported")


    def test_one_caption_cannot_cover_two_figures(self):
        objects = [
            obj("figure", 1, (50, 100, 300, 250)),
            obj("figure", 1, (260, 100, 510, 250)),
            obj("figure_caption", 1, (250, 260, 310, 280), "图 1 并排示例"),
        ]
        result = detect_caption_rules(objects, [13])
        self.assertEqual(len(result["13"]["findings"]), 1)
