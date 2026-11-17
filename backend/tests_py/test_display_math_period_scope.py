"""Display equations do not exempt ordinary source prose punctuation."""
import copy
import unittest
from paper_compiler.local_checks import detect_ir


def native_ir(lines, merge_groups=()):
    """lines = (text, bbox, block_id); real source offsets retain physical rows."""
    page = {'page_index': 0, 'width': 595.28, 'height': 841.89, 'images': [], 'lines': []}
    nodes = []
    for i, (text, box, block_id) in enumerate(lines):
        lid = f'p0-b{block_id}-l{i}'
        page['lines'].append({'id': lid, 'text': text, 'bbox': list(box), 'block_id': block_id,
                              'chars': [], 'font_size': 12, 'direction': [1, 0]})
        nodes.append({'id': f'n{i}', 'kind': 'Paragraph', 'text': text, 'children': [], 'attrs': {},
                      'provenance': [{'kind': 'source', 'page_index': 0, 'line_id': lid,
                                      'bbox': list(box), 'text_offsets': [0, len(text)],
                                      'node_text_start': 0, 'node_text_end': len(text)}]})
    for group in merge_groups:
        target = nodes[group[0]]
        text, sources = '', []
        for idx in group:
            part = nodes[idx]
            if text:
                text += '\n'
            source = copy.deepcopy(part['provenance'][0])
            source['node_text_start'] = len(text)
            source['node_text_end'] = len(text) + len(part['text'])
            sources.append(source)
            text += part['text']
        target['text'], target['provenance'] = text, sources
    removed = {idx for g in merge_groups for idx in g[1:]}
    return {'nodes': [n for i, n in enumerate(nodes) if i not in removed], 'layout': {'pages': [page]}, 'coverage': {'pages': {'status': 'complete'}}}


def unnumbered(annotation='𝑞∼p𝑄为当前样本的取值.'):
    return native_ir([
        ('𝑄∼p𝑄,', [189, 200, 230, 213], 8),
        (annotation, [255, 199, 392, 213], 8),
    ])


def findings(ir):
    return detect_ir(ir, [35])['35']['findings']


class DisplayMathPeriodScopeTests(unittest.TestCase):
    def test_centered_full_prose_without_comma_is_not_an_infix_expression(self):
        ir = native_ir([
            ('采用x−y计算本轮结果并执行下一轮更新.', [190, 200, 405, 213], 2),
            ('x≈y', [70, 200, 110, 213], 1),
            ('(1)', [487, 200, 510, 213], 2),
        ])
        self.assertEqual([f['token'] for f in findings(ir)], ['.'])

    def test_prose_list_cannot_borrow_distant_other_column_relation(self):
        ir = native_ir([
            ('x≈y', [70, 200, 130, 213], 1),
            ('1,', [340, 200, 350, 213], 2),
            ('本文继续使用该方法.', [360, 200, 480, 213], 2),
            ('(1)', [500, 200, 525, 213], 2),
        ])
        self.assertEqual([f['token'] for f in findings(ir)], ['.'])

    def test_independent_right_column_formula_cannot_exempt_left_prose(self):
        ir = native_ir([
            ('α为学习率，本实验中保持不变.', [70, 200, 267, 213], 1),
            ('x≈y', [350, 200, 420, 213], 2),
            ('(1)', [500, 200, 525, 213], 2),
        ])
        self.assertEqual([f['token'] for f in findings(ir)], ['.'])

    def test_minus_inside_full_chinese_statement_remains_prose(self):
        ir = native_ir([
            ('该差值采用x−y计算，下一轮使用相同参数.', [70, 200, 440, 213], 1),
            ('x≈y', [70, 199, 110, 212], 2),
            ('(1)', [500, 200, 525, 213], 2),
        ])
        self.assertEqual([f['token'] for f in findings(ir)], ['.'])

    def test_unrelated_tag_cannot_establish_infix_display(self):
        ir = native_ir([
            ('输入状态≡系统状态.', [184, 200, 396, 213], 2),
            ('(7.4)', [487, 200, 510, 213], 3),
        ])
        self.assertEqual([f['token'] for f in findings(ir)], ['.'])

    def test_numbered_equivalence_terminal_dot_is_formula(self):
        ir = native_ir([
            ('输入状态≡系统状态≡可观测状态.', [184, 200, 396, 213], 2),
            ('(7.4)', [487, 200, 510, 213], 2),
        ])
        self.assertEqual(findings(ir), [])

    def test_numbered_piecewise_branch_terminal_dot_is_formula(self):
        ir = native_ir([
            ('𝑣∼p', [166, 200, 205, 213], 2),
            ('1,', [216, 191, 225, 204], 3),
            ('若类别为甲,', [237, 191, 414, 204], 3),
            ('0,', [216, 209, 225, 222], 3),
            ('其他情况.', [237, 209, 285, 222], 3),
            ('(7.4)', [487, 200, 510, 213], 3),
        ])
        self.assertEqual(findings(ir), [])

    def test_piecewise_condition_column_can_be_more_than_four_em_from_value(self):
        ir = native_ir([
            ('𝑣∼p', [201, 200, 235, 213], 2),
            ('0,', [246, 210, 255, 223], 3),
            ('其他情况.', [309, 210, 357, 222], 3),
            ('(7.4)', [487, 200, 510, 213], 4),
        ])
        self.assertEqual(findings(ir), [])

    def test_numbered_fraction_denominator_terminal_dot_is_formula(self):
        ir = native_ir([
            ('归一化量= 数据值−下界', [214, 194, 362, 214], 4),
            ('上界−下界.', [277, 202, 366, 222], 5),
            ('(7.4)', [481, 202, 510, 214], 5),
        ])
        self.assertEqual(findings(ir), [])

    def test_unnumbered_centered_two_math_fragments_terminal_dot_is_formula(self):
        self.assertEqual(findings(unnumbered()), [])

    def test_inline_relation_in_ordinary_prose_remains_reported(self):
        ir = native_ir([('观测变量𝑞∼p𝑄是本段定义.', [70, 200, 400, 213], 8)])
        self.assertEqual([f['token'] for f in findings(ir)], ['.'])

    def test_centered_ordinary_prose_with_relation_remains_reported(self):
        ir = native_ir([('我们令𝑞∼p𝑄来计算当前样本.', [184, 200, 410, 213], 8)])
        self.assertEqual([f['token'] for f in findings(ir)], ['.'])

    def test_left_aligned_two_fragments_do_not_establish_display_math(self):
        ir = unnumbered()
        ir['layout']['pages'][0]['lines'][0]['bbox'] = [70, 200, 111, 213]
        ir['layout']['pages'][0]['lines'][1]['bbox'] = [136, 199, 510, 213]
        for n, l in zip(ir['nodes'], ir['layout']['pages'][0]['lines']):
            n['provenance'][0]['bbox'] = l['bbox']
        self.assertEqual([f['token'] for f in findings(ir)], ['.'])

    def test_formula_and_following_prose_in_same_paragraph_keep_prose_dot(self):
        ir = native_ir([
            ('𝑄∼p𝑄,', [189, 200, 230, 213], 8),
            ('𝑞∼p𝑄为当前样本的取值.', [255, 199, 392, 213], 8),
            ('随后是真正的中文说明.', [70, 240, 510, 253], 9),
        ], merge_groups=[(1, 2)])
        got = findings(ir)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]['location']['bounding_rect']['y1'], 240)

    def test_formula_and_prose_in_same_source_line_keep_later_dot(self):
        got = findings(unnumbered('𝑞∼p𝑄为当前样本。随后是真正的中文说明.'))
        self.assertEqual([f['token'] for f in got], ['.'])

    def test_ascii_sentence_boundary_in_source_line_is_not_whole_line_exemption(self):
        got = findings(unnumbered('𝑞∼p𝑄为当前样本.随后是真正的中文说明.'))
        self.assertEqual(len(got), 2)

    def test_true_halfwidth_comma_inside_display_annotation_is_still_reported(self):
        got = findings(unnumbered('𝑞∼p𝑄为当前样本,取值保持稳定。'))
        self.assertEqual([f['token'] for f in got], [','])

    def test_math_unicode_alone_does_not_prove_formula(self):
        ir = native_ir([('当前𝑞是本次采样的变量.', [184, 200, 410, 213], 8)])
        self.assertEqual([f['token'] for f in findings(ir)], ['.'])

    def test_numbered_math_neighbor_does_not_exempt_plain_chinese_sentence(self):
        ir = native_ir([
            ('𝑄∼p𝑄,', [189, 200, 230, 213], 8),
            ('这里是真正的中文说明.', [255, 199, 410, 213], 8),
            ('(7.4)', [487, 200, 510, 213], 8),
        ])
        self.assertEqual([f['token'] for f in findings(ir)], ['.'])

    def test_missing_layout_line_cannot_exempt_source(self):
        ir = unnumbered()
        ir['layout']['pages'][0]['lines'] = []
        self.assertEqual([f['token'] for f in findings(ir)], ['.'])

    def test_missing_math_partner_cannot_exempt_source(self):
        ir = unnumbered()
        ir['nodes'] = ir['nodes'][1:]
        ir['layout']['pages'][0]['lines'] = ir['layout']['pages'][0]['lines'][1:]
        self.assertEqual([f['token'] for f in findings(ir)], ['.'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
