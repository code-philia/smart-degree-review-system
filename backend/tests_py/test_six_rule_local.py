import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "six_rule_detector.py"


def run_pdf(pages, rules):
    with tempfile.TemporaryDirectory() as directory:
        pdf_path = Path(directory) / "paper.pdf"
        document = pymupdf.open()
        for lines in pages:
            page = document.new_page()
            for index, line in enumerate(lines):
                page.insert_text((60, 90 + 35 * index), line, fontname="china-s", fontsize=12)
        document.save(pdf_path)
        document.close()
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        process = subprocess.run(
            [sys.executable, str(SCRIPT), "--pdf", str(pdf_path),
             *[part for rule in rules for part in ("--rule", str(rule))]],
            capture_output=True, text=True, encoding="utf-8", env=env,
        )
        return process


class SixRuleLocalTests(unittest.TestCase):
    def test_rule11_and_29_all_missing(self):
        process = run_pdf([
            ["第1章 绪论", "如图1.1所示。", "如图9.9所示。", "见附录A。", "详见附录Z。"],
            ["图1.1 系统架构"],
            ["附录A 实验设置"],
        ], [11, 29])
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)["rules"]
        for rule, token in ((11, "9.9"), (29, "Z")):
            findings = result[str(rule)]["findings"]
            self.assertEqual(result[str(rule)]["status"], "completed")
            self.assertEqual([item["token"] for item in findings], [token])
            box = findings[0]["location"]["bounding_rect"]
            self.assertEqual(findings[0]["location"]["page_number"], 1)
            self.assertLess(box["x1"], box["x2"])
            self.assertLess(box["y1"], box["y2"])

    def test_scope_and_self_reference(self):
        process = run_pdf([
            ["第1章 绪论", "正文见图1.1。", "图目录", "图2.2 未引用图 .... 10", "表3.1 未引用表 .... 11"],
            ["图2.2 未引用图", "表3.1 未引用表"],
            ["附录A 实验", "图1.1 附录中的同号图"],
        ], [11, 15, 16])
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)["rules"]
        self.assertEqual([f["token"] for f in result["11"]["findings"]], ["1.1"])
        self.assertEqual([f["token"] for f in result["15"]["findings"]], ["2.2", "1.1"])
        self.assertEqual([f["token"] for f in result["16"]["findings"]], ["3.1"])
        self.assertTrue(all(f["location"]["page_number"] > 1 for rule in (15, 16)
                            for f in result[str(rule)]["findings"]))

    def test_unreadable_page(self):
        process = run_pdf([[]], [11, 15, 16, 29])
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)["rules"]
        self.assertEqual([result[str(rule)]["status"] for rule in (11, 15, 16, 29)],
                         ["unsupported"] * 4)
        self.assertTrue(all(not result[str(rule)]["findings"] for rule in (11, 15, 16, 29)))

