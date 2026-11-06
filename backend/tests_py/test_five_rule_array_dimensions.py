"""Issue #7: native code/tensor evidence must not erase genuine citations."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from five_rule_detector import Line, detect_lines


def row(text, y=100, x=60, width=470, page=1):
    return Line(page, text, (x, y, x + width, y + 12), 600, 840)


def findings(body, rule=22, labels=(1, 2)):
    lines = [row('第1章 方法', 45), *body, row('参考文献', 40, page=3)]
    lines += [row(f'[{number}] Author. Research paper.', 80 + i * 22, page=3)
              for i, number in enumerate(labels)]
    return detect_lines(lines, [rule])[str(rule)]['findings']


def diagram(y=150, page=1, x=120):
    return [row('W1 (HBM)', y, x, 50, page),
            row('[1024,4096]', y + 12, x - 2, 54, page),
            row('W2 (HBM)', y + 32, x, 50, page),
            row('[4096]', y + 44, x + 8, 30, page)]


class ArrayDimensionCitationTests(unittest.TestCase):
    def test_function_parameter_declarations_do_not_create_six_false_references(self):
        code = ['float\u00a0A[4096][4096],', 'float s[4096],', 'float r[4096],',
                'float q[4096],', 'float p[4096]']
        body = [row(text, 100 + i * 18) for i, text in enumerate(code)]
        body += [row('已有研究[188]、[199]和[177]提供依据。', 250)]
        self.assertEqual([f['token'] for f in findings(body)], ['188', '199', '177'])

    def test_inline_unicode_bias_tensor_is_not_a_citation(self):
        text = 'GELU 随后读取4 bit 偏置𝑊2[4096]并进行逐元素激活，参见文献[188]。'
        result = findings([row(text)])
        self.assertEqual([f['token'] for f in result], ['188'])
        self.assertEqual(result[0]['text_range'], [text.index('[188]'), text.index('[188]') + 5])

    def test_split_diagram_dimension_is_not_a_citation(self):
        self.assertEqual(findings(diagram()), [])

    def test_array_and_tensor_numbers_do_not_count_as_bibliography_uses(self):
        body = [row('float A[188][199],'), row('偏置𝑊2[177]用于计算。', 125),
                *diagram(), row('已有研究[1]。', 240)]
        self.assertEqual([f['token'] for f in findings(body, 24, (1, 177, 188, 199, 4096))],
                         ['177', '188', '199', '4096'])

    def test_standalone_and_model_name_citations_remain_eligible(self):
        body = [row('已有工作[4096]提出该算法。'), row('BERT[188]和MAD-X[199]提供方法。', 125),
                row('[177]', 150)]
        self.assertEqual([f['token'] for f in findings(body)], ['4096', '188', '199', '177'])

    def test_code_context_does_not_hide_a_later_citation_on_the_same_line(self):
        text = 'float A[4096][4096]; 相关研究[199]验证算法。'
        result = findings([row(text)])
        self.assertEqual([f['token'] for f in result], ['199'])
        self.assertEqual(result[0]['text_range'], [text.index('[199]'), text.index('[199]') + 5])

    def test_superscript_citation_after_tensor_name_is_preserved(self):
        text = '偏置W2[188]的研究结果。'
        start = text.index('[188]')
        styled = Line(1, text, (60, 100, 530, 112), 600, 840,
                      ((0, start, 12), (start, start + 5, 8), (start + 5, len(text), 12)))
        self.assertEqual([f['token'] for f in findings([styled])], ['188'])

    def test_unlabelled_shape_does_not_hide_an_unrelated_standalone_citation(self):
        self.assertEqual([f['token'] for f in findings([
            row('[1024,4096]', 150, 118, 54), row('[188]', 194, 128, 30)])], ['188'])

    def test_distant_label_does_not_turn_a_standalone_citation_into_a_dimension(self):
        body = diagram()
        body[-1] = row('[188]', 310, 128, 30)
        self.assertEqual([f['token'] for f in findings(body)], ['188'])

    def test_other_column_or_page_cannot_supply_a_dimension_label(self):
        for replacement in [row('[188]', 194, 430, 30), row('[188]', 194, 128, 30, page=2)]:
            with self.subTest(replacement=replacement):
                body = diagram()
                body[-1] = replacement
                self.assertEqual([f['token'] for f in findings(body)], ['188'])

    def test_bare_citation_below_a_prose_model_name_is_not_suppressed(self):
        body = [row('BERT', 150, 120, 50), row('[188]', 162, 128, 30),
                row('[1024,4096]', 195, 118, 54)]
        self.assertEqual([f['token'] for f in findings(body)], ['188'])

    def test_declaration_with_in_range_numbers_still_does_not_count_as_citation(self):
        self.assertEqual([f['token'] for f in findings([row('int buf[1][2],')], 24)], ['1', '2'])

    def test_comma_declarators_and_pointer_parameters_share_the_declared_type(self):
        body = [row('const float *A[188][199], B[177];'), row('unsigned int *buf[4096])', 125)]
        self.assertEqual(findings(body), [])

    def test_adjacent_references_after_a_model_name_remain_citations(self):
        self.assertEqual([f['token'] for f in findings([row('采用BERT[188][199]作为基线。')])], ['188', '199'])

    def test_explicit_citing_verb_after_a_tensor_name_remains_a_citation(self):
        self.assertEqual([f['token'] for f in findings([row('偏置W2[188]提出了另一种方法。')])], ['188'])

    def test_smaller_citation_marker_below_a_diagram_label_is_not_a_dimension(self):
        body = diagram()
        body[0] = Line(1, body[0].text, body[0].bbox, 600, 840, ((0, len(body[0].text), 12),))
        body[2] = Line(1, body[2].text, body[2].bbox, 600, 840, ((0, len(body[2].text), 12),))
        body[-1] = Line(1, '[188]', body[-1].bbox, 600, 840, ((0, 5, 8),))
        self.assertEqual([f['token'] for f in findings(body)], ['188'])

    def test_all_inline_tensor_dimensions_are_data_even_when_numbers_exist_as_references(self):
        body = [row('权重矩阵W1[188][199]用于计算。')]
        self.assertEqual(findings(body), [])
        self.assertEqual([f['token'] for f in findings(body, 24, (1, 188, 199))], ['1', '188', '199'])

    def test_tensor_noun_alone_does_not_hide_a_reference_or_invent_an_uncited_entry(self):
        for text in ['The matrix A[188] was introduced by Smith.', '偏置W2[188]由Smith等人提出。',
                     'The matrix A[188][199] was introduced by Smith.']:
            with self.subTest(text=text):
                expected = ['188', '199'] if '[199]' in text else ['188']
                self.assertEqual([f['token'] for f in findings([row(text)])], expected)
                uncited = ['1'] if '[199]' in text else ['1', '199']
                self.assertEqual([f['token'] for f in findings([row(text)], 24, (1, 188, 199))], uncited)


if __name__ == '__main__':
    unittest.main()
