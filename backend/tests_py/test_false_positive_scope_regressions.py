"""Native-source scope regressions for the 2026-10-29 false-positive review."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_compiler.frontend import build_paper
from paper_compiler.local_checks import detect_ir, _abstract_nodes, _node_page_index


class SourceScopeRegressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def paper(self, *, rotated=False, abstract_citation=False, back_title=None):
        path = Path(self.temp.name) / 'scope.pdf'
        with pymupdf.open() as doc:
            def page(lines):
                p = doc.new_page(width=600, height=800)
                for x, y, text, size, rotation in lines:
                    p.insert_text((x, y), text, fontsize=size,
                                  fontname='china-s' if any('\u4e00' <= c <= '\u9fff' for c in text) else 'helv',
                                  rotate=rotation)
                return p
            page([(60, 90, '一种论文检测方法', 20, 0)])
            page([(250, 100, '摘', 18, 0), (280, 100, '要', 18, 0),
                  (60, 150, '本文研究方法有效。' + ('已有研究[1]支持本文方法。' if abstract_citation else ''), 12, 0),
                  (60, 210, '关键词：检测；论文；规则', 12, 0)])
            page([(220, 100, 'Abstract', 18, 0),
                  (60, 150, 'The proposed method improves document analysis.', 12, 0),
                  (60, 210, 'Key words: document, analysis, method', 12, 0)])
            page([(250, 100, '目', 18, 0), (280, 100, '录', 18, 0),
                  (60, 150, '绪论及研究方法 1', 12, 0)])
            page([(250, 100, '插', 18, 0), (280, 100, '图', 18, 0),
                  (60, 150, '图 4.4 本文方法在不同配置下的比较', 12, 0)])
            page([(60, 100, '第1章 绪论', 18, 0),
                  (60, 150, '研究背景与相关工作的分析说明。', 12, 0),
                  (60, 185, '研究问题与主要目标的进一步说明。', 12, 0)])
            page([(60, 120, '上一章内容在此页继续，阐述相关工作和研究背景。', 12, 0),
                  (300 if rotated else 60, 420 if rotated else 250, '第二章', 18, 90 if rotated else 0),
                  (60, 470, '这里继续介绍研究内容以及具体的实验方法。', 12, 0)])
            page([(240, 100, '参考文献', 18, 0),
                  (60, 150, '[1] WANG A. Missing source type. Journal, 2024, 3: 1-9.', 12, 0),
                  (60, 200, '[2] WANG B. Correct source[J]. Journal, 2024, 3: 1-9.', 12, 0)])
            if back_title:
                page([(160, 100, back_title, 18, 0),
                      (60, 150, '[1] 2024 年中国软件大会软件自动修复竞赛，特等奖。', 12, 0),
                      (60, 210, '[2] 某项专利的作者和名称。专利号：ZL 2022 1 0374492.5', 12, 0)])
            doc.save(path)
        return build_paper(path, include_citations=False)

    def findings(self, ir, rule):
        return detect_ir(ir, [rule])[str(rule)]['findings']

    def test_abstract_ends_before_contents_and_figure_lists(self):
        ir = self.paper()
        self.assertEqual(self.findings(ir, 37), [])
        self.assertLess(max(_node_page_index(n) for n in _abstract_nodes(ir)), 3)

    def test_english_object_lists_end_an_abstract_without_keywords(self):
        for heading in ['List of Figures', 'List of Tables']:
            with self.subTest(heading=heading):
                path = Path(self.temp.name) / 'english-list.pdf'
                with pymupdf.open() as doc:
                    page = doc.new_page(width=600, height=800)
                    page.insert_text((240, 100), 'Abstract', fontsize=18)
                    page.insert_text((60, 150), 'Our method is shown in Figure 3.1.', fontsize=12)
                    page = doc.new_page(width=600, height=800)
                    page.insert_text((220, 100), heading, fontsize=18)
                    page.insert_text((60, 150),
                                     'Illustration of Figure 4.4 design alternatives .... 1', fontsize=12)
                    page = doc.new_page(width=600, height=800)
                    page.insert_text((60, 100), 'Chapter 1 Introduction', fontsize=18)
                    page.insert_text((60, 150), 'This section describes our method.', fontsize=12)
                    doc.save(path)
                ir = build_paper(path, include_citations=False)
                found = self.findings(ir, 37)
                self.assertEqual([f['token'] for f in found], ['Figure 3.1'])
                self.assertEqual(found[0]['location']['page_number'], 1)

    def test_real_abstract_citation_still_reports(self):
        found = self.findings(self.paper(abstract_citation=True), 37)
        self.assertEqual([f['token'] for f in found], ['[1]'])
        self.assertEqual(found[0]['location']['page_number'], 2)

    def test_rotated_table_cell_is_not_a_chapter_opening(self):
        self.assertEqual(self.findings(self.paper(rotated=True), 38), [])

    def test_horizontal_chapter_after_prior_content_still_reports(self):
        found = self.findings(self.paper(), 38)
        self.assertEqual([f['token'] for f in found], ['第二章'])
        self.assertEqual(found[0]['location']['page_number'], 7)

    def test_independent_achievements_heading_ends_main_bibliography(self):
        for title in ['发表论文和参加科研情况说明', '作者在学期间取得的学术成果']:
            with self.subTest(title=title):
                ir = self.paper(back_title=title)
                entries = [n for n in ir['nodes'] if n['kind'] == 'BibliographyEntry']
                self.assertEqual(len(entries), 2)
                found = self.findings(ir, 31)
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]['location']['page_number'], 8)
                self.assertEqual(ir['metadata']['bibliography_end']['page_index'], 8)


class ReviewedPdfScopeRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = Path(os.environ.get('FALSE_POSITIVE_FIXTURE_DIR', '/data/results/false-positive-20261029'))
        if not cls.fixtures.is_dir():
            raise unittest.SkipTest('reviewed PDFs are optional external regression fixtures')

    def test_reviewed_abstract_has_no_numbered_object_findings(self):
        ir = build_paper(self.fixtures / '268e5c06-321f-4b96-995c-81e7fd1630fb.pdf', include_citations=False)
        self.assertEqual(detect_ir(ir, [37])['37']['findings'], [])
        self.assertEqual(sorted({_node_page_index(n) for n in _abstract_nodes(ir)}), [3, 4])

    def test_reviewed_rotated_tables_have_no_chapter_findings(self):
        ir = build_paper(self.fixtures / 'c11fda55-2881-4e78-a2d7-015a46f2f9cb.pdf', include_citations=False)
        self.assertEqual(detect_ir(ir, [38])['38']['findings'], [])

    def test_reviewed_achievements_are_outside_reference_check(self):
        for uid, end_page in [('13ff9f1e-5e44-44bc-9708-98197a3790b3', 146),
                              ('e6f28752-f2a2-4ff0-9305-760915b09bad', 241)]:
            with self.subTest(uid=uid):
                ir = build_paper(self.fixtures / (uid + '.pdf'), include_citations=False)
                entries = [n for n in ir['nodes'] if n['kind'] == 'BibliographyEntry']
                self.assertTrue(entries)
                self.assertLess(max(_node_page_index(n) for n in entries), end_page)
                self.assertTrue(all(f['location']['page_number'] <= end_page
                                    for f in detect_ir(ir, [31])['31']['findings']))


if __name__ == '__main__':
    unittest.main()
