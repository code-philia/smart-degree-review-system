import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from five_rule_detector import Line, detect_lines


def line(page, text, y=100, x0=60):
    return Line(page, text, (x0, y, 540, y + 12), 600, 800)


class FiveRuleDetectorTests(unittest.TestCase):
    def test_rule_6_finds_three_consecutive_copied_abstract_lines(self):
        copied = [
            '随着移动网络和云计算技术快速发展各种设备可以在移动网络下互联',
            '这些设备在运行过程中不断产生传感器数据和监控数据并传输',
            '远程服务器负责存储管理并为上层复杂应用提供决策分析支持',
        ]
        lines = [line(1, '摘要', 40)] + [line(1, t, 80 + i * 16) for i, t in enumerate(copied)]
        lines += [line(1, '关键词：网络', 200), line(2, '目录', 40), line(3, '第1章 绪论', 50)]
        lines += [line(3, t, 100 + i * 16) for i, t in enumerate(copied)]
        result = detect_lines(lines, [6])['6']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(result['findings']), 1)
        self.assertEqual(result['findings'][0]['page'], 1)
        self.assertEqual(result['findings'][0]['related_page'], 3)

    def test_rule_18_finds_reference_without_displayed_formula(self):
        lines = [line(1, '第1章 绪论'), line(1, '依据公式(9.9)进行计算', 140),
                 line(1, '(3.1)', 180, 480), line(1, '使用公式(3.1)验证', 230)]
        result = detect_lines(lines, [18])['18']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([f['token'] for f in result['findings']], ['9.9'])

    def test_rules_22_and_24_compare_body_citations_with_bibliography(self):
        lines = [line(1, '第1章 绪论'), line(1, '已有研究[1]提出方法，另见[0]', 140),
                 line(2, '参考文献', 40), line(2, '[1]', 100), line(2, '作者. 文献一', 115),
                 line(2, '[2]', 145), line(2, '作者. 文献二', 160)]
        result = detect_lines(lines, [22, 24])
        self.assertEqual([f['token'] for f in result['22']['findings']], ['0'])
        self.assertEqual([f['token'] for f in result['24']['findings']], ['2'])
        self.assertEqual(result['24']['findings'][0]['page'], 2)

    def test_rule_28_uses_consensus_offset_to_find_wrong_toc_page(self):
        lines = [line(1, '目录', 40)]
        for logical in range(1, 9):
            name = f'{logical} 测试章节{logical}'
            shown = 3 if logical == 1 else logical
            lines.append(line(1, f'{name}........................{shown}', 80 + logical * 20))
            lines.append(line(logical + 2, name, 90))
        result = detect_lines(lines, [28])['28']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(result['findings']), 1)
        self.assertEqual(result['findings'][0]['page'], 1)
        self.assertEqual(result['findings'][0]['actual_page'], 1)

    def test_missing_bibliography_is_unsupported_not_clean(self):
        result = detect_lines([line(1, '第1章 绪论'), line(1, '已有研究[1]')], [22, 24])
        self.assertEqual(result['22']['status'], 'unsupported')
        self.assertEqual(result['24']['status'], 'unsupported')


    def test_split_chinese_abstract_heading_is_supported(self):
        lines = [line(1, '摘', 40), line(1, '要', 40, 90),
                 line(1, '这是一段正常摘要，用于描述研究背景和实验设计。', 100),
                 line(1, '我们构建了实验平台并比较了不同方法的运行结果。', 116),
                 line(1, '实验结果说明该方法具有良好的稳定性和适应性。', 132),
                 line(1, '关键词：实验', 150), line(2, '第1章 绪论', 50),
                 line(2, '本文介绍研究背景和实验设计。', 100)]
        result = detect_lines(lines, [6])['6']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['findings'], [])

    def test_numeric_interval_is_not_a_bibliographic_citation(self):
        lines = [line(1, '第1章 绪论'), line(1, '取值范围为[0, 500]，已有研究[1]。', 140),
                 line(2, '参考文献', 40), line(2, '[1] Wang. First paper.', 100),
                 line(2, '[2] Li. Second paper.', 140)]
        result = detect_lines(lines, [22])['22']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['findings'], [])

    def test_toc_matches_split_heading_with_small_vertical_shift(self):
        lines = [line(1, '目录', 40), line(1, '第1章 绪论........3', 80),
                 line(3, '第1章 绪论', 90)]
        for index in range(1, 8):
            shown = index + 1
            lines.append(line(1, f'1.{index} 背景研究{index}........{shown}', 80 + index * 20))
            # PDF extraction order follows reading order; title glyphs can sit 2 pt higher.
            lines.append(line(index + 3, f'1.{index}', 102))
            lines.append(line(index + 3, f'背景研究{index}', 100, 120))
        result = detect_lines(lines, [28])['28']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(result['findings']), 1)
        self.assertEqual(result['findings'][0]['actual_page'], 1)

    def test_toc_entries_split_into_visual_fragments(self):
        lines = [line(1, '目录', 40)]
        for logical in range(1, 9):
            y = 80 + logical * 20
            lines.extend([line(1, f'{logical} 章节{logical}', y, 60),
                          line(1, '. . . . . . . . . .', y + 2, 300),
                          line(1, '3' if logical == 1 else str(logical), y + 1, 520),
                          line(logical + 2, f'{logical} 章节{logical}', 90)])
        result = detect_lines(lines, [28])['28']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(result['findings']), 1)

    def test_figure_list_citation_is_checked_but_not_treated_as_toc(self):
        lines = [line(1, '目录', 40), line(2, '插图目录', 40),
                 line(2, '图1.1 研究方法[99]........4', 80),
                 line(2, '图1.2 分析结果[1]........5', 100),
                 line(2, '图1.3 系统架构[1]........6', 120),
                 line(3, '第1章 绪论', 40),
                 line(4, '参考文献', 40), line(4, '[1] Wang. First paper.', 80),
                 line(4, '[2] Li. Second paper.', 100)]
        result = detect_lines(lines, [22])['22']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([f['token'] for f in result['findings']], ['99'])
        self.assertEqual(result['findings'][0]['page'], 2)


    def test_numbered_abstract_contributions_do_not_start_body_before_toc(self):
        copied = ['连续复制的正文第一行说明研究场景与总体方法具有明确意义',
                  '连续复制的正文第二行说明系统实现过程和关键技术的关系',
                  '连续复制的正文第三行说明实验结论和性能分析得到结果']
        lines = [line(1, '摘要', 40)]
        lines += [line(1, text, 80 + i * 16) for i, text in enumerate(copied)]
        lines += [line(1, '1. 本文首先提出一种实验方法。', 150),
                  line(1, '关键词：系统', 200), line(2, '目录', 40),
                  line(2, '第1章 绪论........1', 80),
                  line(2, '1.1 研究背景........1', 100),
                  line(2, '1.2 研究方法........2', 120),
                  line(3, '第1章 绪论', 40)]
        lines += [line(3, text, 90 + i * 16) for i, text in enumerate(copied)]
        result = detect_lines(lines, [6])['6']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(result['findings']), 1)


    def test_toc_continuation_page_and_back_matter_heading_are_checked(self):
        lines = [line(1, '目录', 40)]
        for logical in range(1, 6):
            lines.append(line(1, f'第{logical}章 章节{logical}........{logical}', 80 + logical * 20))
            lines.append(line(logical + 2, f'第{logical}章 章节{logical}', 90))
        lines += [line(2, '目录', 40), line(2, '致谢........11', 120),
                  line(8, '参考文献', 40), line(8, '[1]', 90), line(8, '[2]', 120),
                  line(12, '致谢', 90)]
        result = detect_lines(lines, [28])['28']
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(result['findings']), 1)
        self.assertEqual(result['findings'][0]['page'], 2)
        self.assertEqual(result['findings'][0]['actual_page'], 10)


if __name__ == '__main__':
    unittest.main()
