"""Regression cases for native-text punctuation evidence, with no service calls."""
import importlib.util
import os
from pathlib import Path
import unittest

source = Path(os.environ.get('LOCAL_CHECKS_PATH', str(Path(__file__).resolve().parents[1] / 'paper_compiler/local_checks.py')))
spec = importlib.util.spec_from_file_location('punctuation_under_test', source)
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


def paper(text, images=None, container='Section'):
    return {
        'root_id': 'paper', 'coverage': {'pages': {'status': 'complete'}},
        'nodes': [
            {'id': 'paper', 'kind': 'Paper', 'text': None, 'attrs': {}, 'children': ['section'], 'provenance': []},
            {'id': 'section', 'kind': container, 'text': None, 'attrs': {}, 'children': ['paragraph'], 'provenance': []},
            {'id': 'paragraph', 'kind': 'Paragraph', 'text': text, 'attrs': {}, 'children': [],
             'provenance': [{'kind': 'source', 'source_id': 'pdf', 'page_index': 0,
                             'bbox': [60, 120, 520, 180], 'line_id': 'line',
                             'node_text_start': 0, 'node_text_end': len(text)}]},
        ],
        'layout': {'pages': [{'page_index': 0, 'width': 600, 'height': 800,
                              'images': images or [], 'lines': [{'id': 'line', 'text': text, 'bbox': [60, 120, 520, 180]}]}]},
    }


class PunctuationScopeTests(unittest.TestCase):
    def findings(self, text, **kwargs):
        result = checks.detect_ir(paper(text, **kwargs), [35])['35']
        self.assertEqual(result['status'], 'completed')
        return result['findings']

    def test_plain_chinese_prose_still_reports_misused_comma(self):
        self.assertEqual(len(self.findings('实验结果可靠,因此可以完成检测。')), 1)

    def test_correct_chinese_prose_is_clean(self):
        self.assertEqual(self.findings('实验结果可靠，因此可以完成检测。'), [])

    def test_chinese_prose_with_an_english_period_still_checks_commas(self):
        self.assertEqual(len(self.findings('实验结果可靠,因此可以完成检测.')), 1)

    def test_front_matter_labels_and_split_declarations_remain_checked(self):
        for text in ['姓    名:张三', '导师:李四教授', '学科/专业名称:计算机技术',
                     '本人郑重声明:所呈交的学位论文，是本人在导师指导下独立进行研究工作',
                     '本人同意学校保留学位论文的复印件和电子版,允许查阅论文']:
            with self.subTest(text=text):
                self.assertEqual(len(self.findings(text)), 1)

    def test_literal_formats_and_quoted_examples_are_not_prose_errors(self):
        for text in ['标识符的格式遵循命名空间:语义域-时间戳-序列号。',
                     '输入采用特定格式，即”指令,示例,问题”，用于测试。',
                     '表格对象的人口统计学信息错误!未定义书签。',
                     '原告卢某诉称:被告应当返还借款。本案已经审理终结。',
                     'Case 3: 角色沉浸感。角色设定:傲慢且看不起平民的贵族反派。',
                     '系统指令:在保证语义与逻辑一致的前提下，执行改写任务。']:
            with self.subTest(text=text):
                self.assertEqual(self.findings(text), [])

    def test_pseudocode_input_and_comment_are_not_body_prose(self):
        for text in ['输入:原始序列,输出特征。', '// 偏移量较大,执行标准过程。',
                     '⊲ 最终层隐状态,形状为序列长度。', '初始化:采样随机向量,输出密钥。']:
            with self.subTest(text=text):
                self.assertEqual(self.findings(text), [])

    def test_tuple_delimiter_inside_prose_is_not_chinese_punctuation(self):
        self.assertEqual(self.findings('我们将(状态,动作,奖励)定义为一个训练样本，用于学习策略。'), [])
        self.assertEqual(self.findings('对于每一对⟨基准版本,更新版本⟩，分别运行测试并汇总结果。'), [])

    def test_research_publication_entry_is_not_body_prose(self):
        self.assertEqual(self.findings('[1] 张三,李四. 一种可复现的测试方法[J]. 测试期刊, 2020.'), [])
        self.assertEqual(self.findings('[2] 张三,李四. 测试软件著作权证书,已授权.'), [])

    def test_boolean_configuration_keeps_existing_exclusion(self):
        self.assertEqual(self.findings('文本配置项 enabled: true 运行,能够正常完成检测。'), [])

    def test_multiline_quoted_data_is_preserved(self):
        self.assertEqual(self.findings('引用示例为“第一行的测试输入\n初始问题:请分析样本，并返回结果。”'), [])

    def test_operator_definition_and_diagram_fragments_are_not_sentences(self):
        for text in ['其中:表示', '控制中心:输出解析', '速度?\n刹车?', '第2簇,西北方']:
            with self.subTest(text=text):
                self.assertEqual(self.findings(text), [])

    def test_scanned_image_text_layer_is_not_punctuation_evidence(self):
        self.assertEqual(self.findings('论文结构清晰,具有一定创新性。', images=[[0, 0, 600, 800]]), [])

    def test_table_or_figure_descendant_is_not_body_prose(self):
        for container in ['Table', 'Figure']:
            self.assertEqual(self.findings('实验结果可靠,因此可以完成检测。', container=container), [])

    def test_prose_outside_parentheses_remains_checked(self):
        self.assertEqual(len(self.findings('我们将(状态,动作)作为输入,因此可以学习策略。')), 1)


if __name__ == '__main__':
    unittest.main()
