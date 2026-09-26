import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from five_rule_detector import Line, detect_lines


def line(page, text, y=100, x0=60, height=12):
    return Line(page, text, (x0, y, 540, y + height), 600, 800)


class RealPaperRegressionTests(unittest.TestCase):
    def test_mixed_citation_lists_and_ranges_count_as_citations(self):
        body = ('第1章 绪论',
                '已有工作[20,80]、[4,85-92]、[25,58,98]、[93,109-111]和[4,119-120]。')
        lines = [line(1, body[0], 60), line(1, body[1], 120),
                 line(2, '参考文献', 40)]
        for index, number in enumerate((80, 87, 88, 90, 98, 110, 119, 120, 130)):
            lines.append(line(2, f'[{number}] 作者. 文献标题', 80 + index * 24))
        result = detect_lines(lines, [24])['24']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([item['token'] for item in result['findings']], ['130'])

    def test_formula_hyphen_and_dot_identify_the_same_target(self):
        lines = [line(1, '第2章 方法', 60),
                 line(1, '依据公式(2-1)计算，另见公式(2-9)。', 120),
                 line(1, '(2.1)', 200, 490)]
        result = detect_lines(lines, [18])['18']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([item['token'] for item in result['findings']], ['2-9'])

    def test_unicode_dash_formula_reference_is_still_checked(self):
        lines = [line(1, '第2章 方法', 60),
                 line(1, '依据公式(2–1)计算，另见公式(2—9)。', 120),
                 line(1, '(2.1)', 200, 490)]
        result = detect_lines(lines, [18])['18']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([item['token'] for item in result['findings']], ['2—9'])

    def test_malformed_numeric_bracket_does_not_crash_detection(self):
        lines = [line(1, '第1章 绪论', 60),
                 line(1, '范围[1-3-5]不是文献引用，已有研究[1]。', 100),
                 line(2, '参考文献', 40),
                 line(2, '[1] 作者. 文献', 80),
                 line(2, '[2] 作者. 文献', 110)]
        result = detect_lines(lines, [22])['22']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['findings'], [])

    def test_array_indexes_are_not_missing_bibliography_citations(self):
        lines = [line(1, '第1章 绪论', 60),
                 line(1, '已有研究[99]提出方法。', 100),
                 line(1, 'Root = Lh [0] (4.13)', 130),
                 line(1, 'a=[0]*n; i=0', 160),
                 line(2, '参考文献', 40),
                 line(2, '[1] 作者. 已引用文献', 80),
                 line(2, '[2] 作者. 另一文献', 110)]
        result = detect_lines(lines, [22])['22']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([item['token'] for item in result['findings']], ['99'])

    def test_code_index_does_not_count_as_reference_use(self):
        lines = [line(1, '第1章 绪论', 60),
                 line(1, '已有研究[2]提出方法。', 100),
                 line(1, 'a[1] = value', 130),
                 line(2, '参考文献', 40),
                 line(2, '[1] 作者. 未引用文献', 80),
                 line(2, '[2] 作者. 已引用文献', 110)]
        result = detect_lines(lines, [24])['24']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([item['token'] for item in result['findings']], ['1'])

    def test_prose_citations_after_model_names_percent_and_slash_are_kept(self):
        lines = [line(1, '第1章 绪论', 60),
                 line(1, 'Hibernus++[56]和Conformer[75]已有相关研究。', 100),
                 line(1, '性能提升40%[46]，另见I/O调度[69]。', 130),
                 line(2, '参考文献', 40)]
        for index, number in enumerate((46, 56, 69, 75)):
            lines.append(line(2, f'[{number}] 作者. 文献', 80 + index * 25))
        result = detect_lines(lines, [24])['24']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['findings'], [])

    def test_exact_chapter_heading_beats_earlier_prefix_description(self):
        lines = [line(1, '目录', 40)]
        for logical in range(1, 9):
            title = f'第{logical}章 章节{logical}'
            lines.append(line(1, f'{title}........{logical}', 75 + logical * 22))
            lines.append(line(logical + 2, title, 90, height=17))
        lines.append(line(4, '第3章 章节3：概览', 110, height=12))
        result = detect_lines(lines, [28])['28']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['findings'], [])

    def test_chapter_name_inside_overview_figure_is_not_heading(self):
        lines = [line(1, '目录', 40)]
        for logical in range(1, 9):
            title = f'第{logical}章 章节{logical}'
            lines.append(line(1, f'{title}........{logical}', 75 + logical * 22))
            lines.append(line(logical + 2, title, 90, height=17))
        lines.append(line(4, '第3章 章节3', 430, height=6))
        result = detect_lines(lines, [28])['28']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['findings'], [])


if __name__ == '__main__':
    unittest.main()
