"""Issue #12: real sentence punctuation versus native technical notation."""
import unittest
from paper_compiler.local_checks import detect_ir
from test_fast_punctuation_scope import paper


def findings(text):
    return detect_ir(paper(text), [35])['35']['findings']


class PunctuationPeriodTests(unittest.TestCase):
    def test_chinese_periods_are_detected_between_sentences_and_at_line_end(self):
        for text in ['缓冲容量.对从零开始的二维循环进行分块。', '后两个分量确定块内顺序.边界块需限制。',
                     '本文提出一种新的方法.', '实验结果可靠.\n因此可以完成检测。']:
            with self.subTest(text=text):
                result = findings(text)
                self.assertEqual([f['token'] for f in result], ['.'])
                self.assertIn('英文句号', result[0]['message'])
                self.assertIn('中文句号', result[0]['suggestion'])

    def test_periods_and_existing_commas_and_semicolons_are_all_checked(self):
        result = findings('实验结果可靠,因此可以采用;该方法性能稳定.后续工作仍将继续.')
        self.assertCountEqual([f['token'] for f in result], [',', ';', '.', '.'])

    def test_ordinary_english_words_do_not_turn_prose_into_pseudocode(self):
        for text in ['The tasks require joint scheduling of tiled computation。',
                     'The input data are processed by the proposed method。',
                     'The output values ensure stable and reproducible results。',
                     'The functions return accurate results on the test data。',
                     'The functions\nreturn accurate results on the test data。',
                     'Return values are used to evaluate the performance。']:
            with self.subTest(text=text):
                self.assertEqual([f['token'] for f in findings(text)], ['。'])

    def test_multiple_english_period_errors_in_one_paragraph_are_preserved(self):
        text = ('The tasks require joint scheduling. The work consists of three parts。\n'
                'We reduce manual restructuring and repeated parameter tuning。')
        result = findings(text)
        self.assertEqual([f['token'] for f in result], ['。', '。'])
        self.assertTrue(all('英文句号' in f['suggestion'] for f in result))

    def test_correct_chinese_and_english_sentences_remain_clean(self):
        for text in ['本方法计算可靠，因此能够完成验证。',
                     'The tasks require joint scheduling. We return the computed values.',
                     '本方法采用版本v1.2.3，误差为0.05，参见图1.2及第2.3节。',
                     '实验使用e.g.给出的形式，并采用U.S.标准进行测试。',
                     '我们采用.NET平台，并使用数据.json及论文.pdf作为输入。',
                     '实验仍在继续...因此暂不讨论最终结论。',
                     '实验仍在继续. . .因此暂不讨论最终结论。',
                     '第一章. . . . . 1',
                     '一.研究背景', '本方法的示例为“实验结束.”，仅作为输入数据。']:
            with self.subTest(text=text):
                self.assertEqual(findings(text), [])

    def test_real_english_algorithm_labels_and_instructions_are_excluded(self):
        for text in ['Input: The original data are passed into the model。',
                     'Require: The input data must contain at least four values。',
                     'Ensure: The output contains a valid sorted sequence。',
                     'Input: The original data.\nreturn the computed value and stop execution。',
                     '1: return the computed value and stop execution。',
                     'foreach value in the data compute its representation。']:
            with self.subTest(text=text):
                self.assertEqual(findings(text), [])

    def test_inline_math_does_not_hide_a_later_prose_sentence(self):
        text = ('常见仿射调度可写为𝜃(𝒊) = 𝑇𝒊，变换为(𝑖, 𝑗) ↦→(𝑗, 𝑖)。\n'
                '循环分块便于复用片上数据并控制缓冲容量.对从零开始的循环进行分块。')
        self.assertEqual([f['token'] for f in findings(text)], ['.'])
        self.assertEqual(findings('调度为𝜃 = 迭代,序号。'), [])


if __name__ == '__main__':
    unittest.main()
