import copy
import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def sample_ir():
    nodes = [{'id': 'paper', 'kind': 'Paper', 'text': None, 'attrs': {}, 'children': [], 'provenance': []}]
    def add(nid, kind, text, page, y=100, x=60, parent='paper', attrs=None):
        span = {'kind': 'source', 'source_id': 'pdf', 'page_index': page,
                'bbox': [x, y, x + max(12, len(text or '') * 5), y + 12],
                'coordinate_system': 'unrotated_top_left_points',
                'node_text_start': 0, 'node_text_end': len(text or '')}
        nodes.append({'id': nid, 'kind': kind, 'text': text, 'attrs': attrs or {},
                      'children': [], 'provenance': [span] if text is not None else []})
        next(n for n in nodes if n['id'] == parent)['children'].append(nid)
    add('title', 'TitlePage', '一种论文检测方法', 0)
    add('originality', 'Paragraph', '学位论文原创性声明', 1)
    add('authorization', 'Paragraph', '学位论文使用授权书', 1, 140)
    add('abstract', 'Abstract', None, 2)
    add('abstract-heading', 'Heading', '摘要', 2, parent='abstract')
    add('keywords', 'Paragraph', '关键词：检测；论文；规则', 2, 160, parent='abstract')
    add('toc', 'Paragraph', '目', 3, x=250)
    add('toc-fragment', 'Paragraph', '录', 3, x=280)
    for nid, title, page in [('intro', '第1章 绪论', 4), ('main', '第2章 方法', 5), ('conclusion', '第3章 总结与展望', 6)]:
        add(nid, 'Section', None, page, attrs={'level': 1, 'number': str(page - 3)})
        add(nid+'-heading', 'Heading', title, page, parent=nid)
    add('body-text', 'Paragraph', '实验结果可靠，因此可以完成检测。', 5, 160, parent='main')
    add('bibliography', 'Bibliography', None, 7)
    add('bib-heading', 'Heading', '参考文献', 7, parent='bibliography')
    add('ref1', 'BibliographyEntry', '[1] WANG A. A useful paper[J]. Journal of Tests, 2020, 3: 1-9.', 7, 140, parent='bibliography')
    return {'nodes': nodes, 'layout': {'pages': [{'page_index': i, 'width': 600, 'height': 800} for i in range(8)]},
            'coverage': {'pages': {'status': 'complete'}}, 'metadata': {}}


class FastLocalChecksTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((Path(__file__).resolve().parents[1] / 'paper_compiler/local_checks.py').exists(),
                        'Three local Paper IR checks have not been implemented')
        self.check = importlib.import_module('paper_compiler.local_checks').detect_ir
        self.ir = sample_ir()

    def test_declaration_first_line_is_not_a_title_page(self):
        from paper_compiler.local_checks import core_parts
        node = next(n for n in self.ir['nodes'] if n['id'] == 'title')
        node['kind'] = 'Title'
        node['text'] = '学位论文原创性声明'
        self.assertIs(core_parts(self.ir)['题名页'], False)

    def test_scanned_page_with_native_page_number_is_not_complete(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
        from fast_local_detector import native_coverage
        ir = self.ir
        ir['root_id'] = 'paper'
        ir['layout']['pages'][0].update(images=[[0,0,600,800]],lines=[{'text':'1','bbox':[290,780,300,790]}])
        self.assertEqual(native_coverage(ir)['coverage']['pages']['status'], 'partial')

    def test_literal_punctuation_in_a_technical_explanation_is_not_misuse(self):
        node = next(n for n in self.ir['nodes'] if n['id'] == 'body-text')
        node['text'] = '将语句终止符; 等特殊符号作为单独的词元。'
        self.assertEqual(self.check(self.ir, [35])['35']['findings'], [])

    def test_running_header_does_not_replace_missing_conclusion(self):
        node = next(n for n in self.ir['nodes'] if n['id'] == 'conclusion-heading')
        node['text'] = '第3章 实验分析'
        self.ir['nodes'].append({'id':'header','kind':'Paragraph','text':'总结与展望','children':[], 'attrs':{},
          'provenance':[{'kind':'source','source_id':'pdf','page_index':7,'bbox':[400,60,470,69], 'coordinate_system':'unrotated_top_left_points'}]})
        self.assertIn('结论', [f['token'] for f in self.check(self.ir,[34])['34']['findings']])

    def test_conclusion_accepts_topic_summary_and_future_outlook(self):
        node = next(n for n in self.ir['nodes'] if n['id'] == 'conclusion-heading')
        node['text'] = '第3章 课题总结与未来展望'
        self.assertEqual(self.check(self.ir,[34])['34']['findings'], [])

    def test_dense_remaining_body_text_is_not_a_possible_title_page(self):
        from paper_compiler.local_checks import core_parts
        node = next(n for n in self.ir['nodes'] if n['id'] == 'title')
        node['kind'] = 'Paragraph'
        node['text'] = '这是摘要的研究背景和方法说明。'*30
        self.assertIs(core_parts(self.ir)['题名页'], False)

    def test_toc_continuation_is_not_an_unconfirmed_title_page(self):
        from paper_compiler.local_checks import core_parts
        node=next(n for n in self.ir['nodes'] if n['id']=='title')
        node.update(kind='Paragraph',text='第二章 方法 ............... 10')
        self.assertIs(core_parts(self.ir)['题名页'],False)

    def test_keywords_continuation_cannot_be_a_title_page(self):
        from paper_compiler.local_checks import core_parts
        node=next(n for n in self.ir['nodes'] if n['id']=='title')
        node.update(kind='Paragraph',text='关键词：检测；论文；规则')
        self.assertIs(core_parts(self.ir)['题名页'],False)

    def test_adjacent_mixed_punctuation_is_not_lost(self):
        node = next(n for n in self.ir['nodes'] if n['id']=='body-text')
        node['text']='甲,乙,丙,丁'
        self.assertEqual(len(self.check(self.ir,[35])['35']['findings']),3)

    def test_punctuation_location_uses_the_line_containing_the_error(self):
        node = next(n for n in self.ir['nodes'] if n['id']=='body-text')
        node['text']='正常的第一行。\n这里,需要修订。'
        first=dict(node['provenance'][0]);first.update(node_text_start=0,node_text_end=8)
        second=dict(first);second.update(node_text_start=9,node_text_end=len(node['text']),bbox=[60,190,300,202])
        node['provenance']=[first,second]
        found=self.check(self.ir,[35])['35']['findings'][0]
        self.assertEqual(found['location']['bounding_rect']['y1'],190)

    def test_spaced_toc_glyphs_are_present(self):
        self.assertEqual(self.check(self.ir, [34])['34']['findings'], [])

    def test_required_conclusion_is_not_optional(self):
        for n in self.ir['nodes']:
            if n['id'] == 'conclusion-heading': n['text'] = '第3章 实验分析'
        findings = self.check(self.ir, [34])['34']['findings']
        self.assertEqual([f['token'] for f in findings], ['结论'])

    def test_optional_english_title_and_appendix_are_not_required(self):
        self.assertEqual(self.check(self.ir, [34])['34']['findings'], [])

    def test_punctuation_is_local_and_ignores_normal_mixed_content(self):
        node = next(n for n in self.ir['nodes'] if n['id'] == 'body-text')
        node['text'] = '实验结果可靠, 因此可以完成检测。'
        self.assertEqual(len(self.check(self.ir, [35])['35']['findings']), 1)
        node['text'] = '采用 Python 3.12，网址为 https://example.org/a,b。'
        self.assertEqual(self.check(self.ir, [35])['35']['findings'], [])
        node['text'] = '代码示例：print("可靠,因此")'
        self.assertEqual(self.check(self.ir, [35])['35']['findings'], [])

    def test_reference_marker_is_checked_from_ir_without_a_model(self):
        self.assertEqual(self.check(self.ir, [31])['31']['findings'], [])
        node = next(n for n in self.ir['nodes'] if n['id'] == 'ref1')
        node['text'] = node['text'].replace('[J]', '')
        self.assertEqual(len(self.check(self.ir, [31])['31']['findings']), 1)

    def test_author_publication_list_is_not_chinese_prose(self):
        node = next(n for n in self.ir['nodes'] if n['id'] == 'body-text')
        node['text'] = '张三,李四. 学术论文成果[J]. 测试期刊, 2020.'
        next(n for n in self.ir['nodes'] if n['id'] == 'main')['children'].remove(node['id'])
        self.ir['nodes'][0]['children'].append('back')
        self.ir['nodes'].append({'id': 'back', 'kind': 'BackMatter', 'text': None, 'children': [node['id']], 'attrs': {}, 'provenance': []})
        self.assertEqual(self.check(self.ir, [35])['35']['findings'], [])

    def test_bracketed_term_in_title_is_not_a_resource_type(self):
        node = next(n for n in self.ir['nodes'] if n['id'] == 'ref1')
        node['text'] = '[1] WANG A. Advances in [AI] systems[J]. Journal of Tests, 2020.'
        self.assertEqual(self.check(self.ir, [31])['31']['findings'], [])

    def test_doi_and_access_date_are_not_unconditionally_required(self):
        node = next(n for n in self.ir['nodes'] if n['id'] == 'ref1')
        for marker in ['[J]', '[J/OL]', '[PP]', '[C/OL]']:
            node['text'] = f'[1] WANG A. A useful paper{marker}. arXiv preprint, 2020.'
            self.assertEqual(self.check(self.ir, [31])['31']['findings'], [])

    def test_unreadable_pages_do_not_become_missing_section_alarms(self):
        self.ir['coverage']['pages']['status'] = 'partial'
        self.ir['nodes'] = [n for n in self.ir['nodes'] if n['id'] != 'originality']
        self.assertEqual(self.check(self.ir, [34])['34']['findings'], [])


if __name__ == '__main__':
    unittest.main()
