"""Native PDF regressions for the three local rules added in PR #3."""
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_compiler.frontend import build_paper
from paper_compiler.local_checks import detect_ir


class NewLocalRulePdfRegressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def paper(self, abstract='本文提出一种论文检测方法，对文档结构进行建模与验证。',
              keywords=('关键词：检测；论文；规则',), continuation=None, chapter=None,
              keyword_indents=None):
        path = Path(self.temp.name) / 'paper.pdf'
        with pymupdf.open() as doc:
            def page(lines):
                p = doc.new_page(width=600, height=800)
                for x, y, text, size in lines:
                    p.insert_text((x, y), text, fontsize=size, fontname='china-s')
            page([(60, 90, '一种论文检测方法', 20)])
            page([(240, 100, '摘要', 18), (60, 150, abstract, 12)] +
                 [(keyword_indents[i] if keyword_indents else 60 if i == 0 else 112,
                   210 + i * 24, text, 12)
                  for i, text in enumerate(keywords if continuation is None else ())])
            if continuation is not None:
                page([(60, 150, continuation, 12), (60, 210, '关键词：检测；论文；规则', 12)])
            page([(60, 130, '第1章 绪论', 18),
                  (60, 180, '本文研究方法可以有效改进论文检测。', 12)])
            if chapter:
                page([(60, 130, '上一章的末段内容在该页继续，并得出了相应结论。', 12),
                      (60, 240, chapter, 18),
                      (60, 290, '本文研究方法可以有效改进论文检测。', 12)])
            doc.save(path)
        return build_paper(path, include_citations=False)

    def findings(self, ir, rule):
        return detect_ir(ir, [rule])[str(rule)]['findings']

    def test_valid_hanging_keyword_continuation_is_not_reported(self):
        ir = self.paper(keywords=('关键词：检测；论文；', '规则；方法'))
        self.assertEqual(self.findings(ir, 36), [])

    def test_too_few_wrapped_keywords_count_the_complete_list(self):
        found = self.findings(self.paper(keywords=('关键词：检测；', '论文')), 36)
        self.assertEqual(len(found), 1)
        self.assertIn('2 个', found[0]['message'])

    def test_keyword_continuations_follow_reading_order_across_indents(self):
        ir = self.paper(keywords=('关键词：检测；论文；', '规则；', '方法'),
                        keyword_indents=(60, 160, 100))
        self.assertEqual(self.findings(ir, 36), [])

    def test_internal_periods_in_wrapped_keywords_are_preserved(self):
        ir = self.paper(keywords=('关键词：检测；论文；', 'Node.js；方法'))
        self.assertEqual(self.findings(ir, 36), [])

    def test_too_many_wrapped_keywords_count_the_complete_list(self):
        found = self.findings(self.paper(keywords=('关键词：甲；乙；丙；丁；', '戊；己；庚；辛；壬')), 36)
        self.assertEqual(len(found), 1)
        self.assertIn('9 个', found[0]['message'])

    def test_abstract_continuation_is_checked_and_located(self):
        found = self.findings(self.paper(continuation='本文方法如图3-1所示，效果良好。'), 37)
        self.assertEqual([item['token'] for item in found], ['图3-1'])
        self.assertEqual(found[0]['location']['page_number'], 3)

    def test_body_references_after_abstract_are_excluded(self):
        ir = self.paper(continuation='本文方法有效，结果可靠。')
        body = next(n for n in ir['nodes'] if n['text'] == '本文研究方法可以有效改进论文检测。')
        body['text'] = '实验结果如图3-1所示。'
        self.assertEqual(self.findings(ir, 37), [])

    def test_one_chinese_equation_reference_has_one_alarm(self):
        found = self.findings(self.paper(abstract='本文利用公式(4)计算结果。'), 37)
        self.assertEqual([item['token'] for item in found], ['公式(4)'])

    def test_parenthesized_english_equation_references_are_detected(self):
        for token in ['Eq. (3)', 'Equation (3)', 'Eq. (3-1)', 'Eq. 3']:
            with self.subTest(token=token):
                found = self.findings(self.paper(abstract='The result follows ' + token + '.'), 37)
                self.assertEqual([item['token'] for item in found], [token])

    def test_numeric_intervals_are_not_bibliography_citations(self):
        for text in ['本文将特征值归一化到[0,1]区间，以提高方法稳定性。',
                     '本文在[1,2]区间内进行了稳定性验证。',
                     'We use the interval [1,2] to evaluate the result.']:
            with self.subTest(text=text):
                self.assertEqual(self.findings(self.paper(abstract=text), 37), [])

    def test_actual_citation_lists_remain_detected(self):
        found = self.findings(self.paper(abstract='已有研究[1,2]表明该方法有效。'), 37)
        self.assertEqual([item['token'] for item in found], ['[1,2]'])

    def test_chapter_without_space_after_label_still_requires_new_page(self):
        found = self.findings(self.paper(chapter='第2章方法研究'), 38)
        self.assertEqual([item['token'] for item in found], ['第2章方法研究'])
        self.assertEqual(found[0]['location']['page_number'], 4)


if __name__ == '__main__':
    unittest.main()
