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
    add('abstract-text', 'Paragraph', '本文提出一种论文检测方法，对文档结构进行建模与验证。', 2, 120, parent='abstract')
    add('english-abstract-heading', 'Heading', 'Abstract', 2, 220, parent='abstract')
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
        node['text']='甲,乙,丙,丁。'  # Complete prose sentence, rather than an ambiguous diagram label.
        self.assertEqual(len(self.check(self.ir,[35])['35']['findings']),3)

    def test_punctuation_location_uses_the_line_containing_the_error(self):
        node = next(n for n in self.ir['nodes'] if n['id']=='body-text')
        node['text']='正常的第一行。\n这里,需要修订。'
        first=dict(node['provenance'][0]);first.update(node_text_start=0,node_text_end=8)
        second=dict(first);second.update(node_text_start=9,node_text_end=len(node['text']),bbox=[60,190,300,202])
        node['provenance']=[first,second]
        found=self.check(self.ir,[35])['35']['findings'][0]
        self.assertEqual(found['location']['bounding_rect']['y1'],190)

    def test_punctuation_highlights_only_the_misused_character(self):
        node = next(n for n in self.ir['nodes'] if n['id'] == 'body-text')
        node['text'] = '正常中文。\n这里,需要修订。'
        first = dict(node['provenance'][0], node_text_start=0, node_text_end=5)
        second = dict(first, node_text_start=6, node_text_end=len(node['text']),
                      line_id='second-line', bbox=[60,190,300,202])
        node['provenance'] = [first, second]
        self.ir['layout']['pages'][5]['lines'] = [{
            'id':'second-line', 'text':'这里,需要修订。', 'bbox':[60,190,300,202],
            'chars':[{'text':',', 'start':2, 'end':3, 'bbox':[84,190,87,202]}],
        }]
        found = self.check(self.ir, [35])['35']['findings'][0]
        rect = found['location']['bounding_rect']
        self.assertEqual([rect[k] for k in ['x1','y1','x2','y2']], [84,190,87,202])
        self.assertEqual(found['location']['rects'], [rect])

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

    # --- Rule 36: keyword count 3-8 ---

    def _keyword_node(self, ir=None):
        return next(n for n in (ir or self.ir)['nodes'] if n['id'] == 'keywords')

    def test_three_keywords_pass(self):
        self.assertEqual(self.check(self.ir, [36])['36']['findings'], [])

    def test_eight_keywords_pass(self):
        self._keyword_node()['text'] = '关键词：a；b；c；d；e；f；g；h'
        self.assertEqual(self.check(self.ir, [36])['36']['findings'], [])

    def test_two_keywords_fail(self):
        self._keyword_node()['text'] = '关键词：a；b'
        findings = self.check(self.ir, [36])['36']['findings']
        self.assertEqual(len(findings), 1)
        self.assertIn('2 个', findings[0]['message'])

    def test_nine_keywords_fail(self):
        self._keyword_node()['text'] = '关键词：a；b；c；d；e；f；g；h；i'
        findings = self.check(self.ir, [36])['36']['findings']
        self.assertEqual(len(findings), 1)
        self.assertIn('9 个', findings[0]['message'])

    def test_wrapped_keyword_line_is_joined(self):
        # A wrapped line split mid-term must not split "规则检测" into two terms.
        self._keyword_node()['text'] = '关键词：规则检测\n论文；方法'
        findings = self.check(self.ir, [36])['36']['findings']
        self.assertEqual(len(findings), 1)
        self.assertIn('2 个', findings[0]['message'])

    def test_no_keyword_block_is_not_a_finding(self):
        self._keyword_node()['text'] = None
        self.assertEqual(self.check(self.ir, [36])['36']['findings'], [])

    def test_body_text_keyword_label_is_ignored(self):
        # A colon-label mention in the body/appendix must not become a keyword
        # count violation; only front-matter keyword blocks are checked.
        ir = copy.deepcopy(self.ir)
        ir['nodes'] = [n for n in ir['nodes'] if n['id'] != 'keywords']
        main = next(n for n in ir['nodes'] if n['id'] == 'main')
        ir['nodes'].append({'id': 'fake-kw', 'kind': 'Paragraph',
                            'text': '关键词：测试；数据', 'attrs': {},
                            'children': [], 'provenance': main['provenance'][:1]})
        main['children'].append('fake-kw')
        self.assertEqual(self.check(ir, [36])['36']['findings'], [])

    def test_partial_coverage_does_not_false_flag_absence(self):
        self.ir['coverage']['pages']['status'] = 'partial'
        self._keyword_node()['text'] = None
        self.assertEqual(self.check(self.ir, [36])['36']['findings'], [])

    # --- Rule 37: no figure/table/equation/reference numbers in the abstract ---

    def _abstract_node(self, ir=None):
        return next(n for n in (ir or self.ir)['nodes'] if n['id'] == 'abstract-text')

    def test_clean_abstract_passes_object_number_check(self):
        self.assertEqual(self.check(self.ir, [37])['37']['findings'], [])

    def test_figure_number_in_abstract_fails(self):
        self._abstract_node()['text'] = '本文方法如图3-1所示，效果良好。'
        findings = self.check(self.ir, [37])['37']['findings']
        self.assertEqual([f['token'] for f in findings], ['图3-1'])

    def test_table_number_in_abstract_fails(self):
        self._abstract_node()['text'] = '检测结果见表2-1。'
        findings = self.check(self.ir, [37])['37']['findings']
        self.assertEqual([f['token'] for f in findings], ['表2-1'])

    def test_equation_number_in_abstract_fails(self):
        self._abstract_node()['text'] = '由式(4)可得检测阈值。'
        findings = self.check(self.ir, [37])['37']['findings']
        self.assertEqual([f['token'] for f in findings], ['式(4)'])

    def test_citation_number_in_abstract_fails(self):
        self._abstract_node()['text'] = '已有研究[3-5]表明该方法有效。'
        findings = self.check(self.ir, [37])['37']['findings']
        self.assertEqual([f['token'] for f in findings], ['[3-5]'])

    def test_english_abstract_figure_number_fails(self):
        self._abstract_node()['text'] = '本方法流程Fig. 2展示了检测过程。'
        findings = self.check(self.ir, [37])['37']['findings']
        self.assertEqual([f['token'] for f in findings], ['Fig. 2'])

    def test_abstract_prose_words_without_numbers_are_not_findings(self):
        self._abstract_node()['text'] = '本文表明该表达方式有效，并试图改进形式。'
        self.assertEqual(self.check(self.ir, [37])['37']['findings'], [])

    def test_body_object_number_is_ignored(self):
        # Body references are legitimate; only front-matter abstract prose is checked.
        node = next(n for n in self.ir['nodes'] if n['id'] == 'body-text')
        node['text'] = '实验装置如图3所示，结果见表2-1。'
        self.assertEqual(self.check(self.ir, [37])['37']['findings'], [])

    def test_abstract_page_prose_without_heading_node_is_checked(self):
        # A 摘要 heading split across glyph runs leaves abstract prose as plain text.
        ir = copy.deepcopy(self.ir)
        ir['nodes'] = [n for n in ir['nodes'] if n['id'] not in {'abstract', 'abstract-heading'}]
        def span(x, y=100):
            return [{'kind': 'source', 'source_id': 'pdf', 'page_index': 2,
                     'bbox': [x, y, x + 12, y + 12],
                     'coordinate_system': 'unrotated_top_left_points'}]
        ir['nodes'].append({'id': 'split-heading-1', 'kind': 'Heading', 'text': '摘',
                            'attrs': {}, 'children': [], 'provenance': span(60)})
        ir['nodes'].append({'id': 'split-heading-2', 'kind': 'Heading', 'text': '要',
                            'attrs': {}, 'children': [], 'provenance': span(74)})
        ir['nodes'].append({'id': 'orphan-abstract', 'kind': 'Paragraph', 'text': '如图3所示，方法有效。',
                            'attrs': {}, 'children': [], 'provenance': span(60, 200)})
        self.assertEqual([f['node_id'] for f in self.check(ir, [37])['37']['findings']], ['orphan-abstract'])

    def test_partial_coverage_abstract_number_is_still_reported(self):
        self.ir['coverage']['pages']['status'] = 'partial'
        self._abstract_node()['text'] = '如图3所示，方法有效。'
        self.assertEqual(len(self.check(self.ir, [37])['37']['findings']), 1)


class ChapterNewPageRuleTests(unittest.TestCase):
    """Rule 38: every body chapter label must sit at the top of its own page."""

    def setUp(self):
        self.check = importlib.import_module('paper_compiler.local_checks').detect_ir
        self.ir = sample_ir()
        # Chapter headings are typeset larger than the 12 pt body text.
        for nid in ['intro-heading', 'main-heading', 'conclusion-heading']:
            span = next(n for n in self.ir['nodes'] if n['id'] == nid)['provenance'][0]
            span['bbox'] = [span['bbox'][0], span['bbox'][1], span['bbox'][2], span['bbox'][1] + 18]

    def _add(self, nid, kind, text, page, y=100, x=60, parent='paper', height=12):
        span = {'kind': 'source', 'source_id': 'pdf', 'page_index': page,
                'bbox': [x, y, x + max(12, len(text) * 5), y + height],
                'coordinate_system': 'unrotated_top_left_points',
                'node_text_start': 0, 'node_text_end': len(text)}
        self.ir['nodes'].append({'id': nid, 'kind': kind, 'text': text, 'attrs': {},
                                 'children': [], 'provenance': [span]})
        next(n for n in self.ir['nodes'] if n['id'] == parent)['children'].append(nid)

    def _move(self, nid, page, y):
        span = next(n for n in self.ir['nodes'] if n['id'] == nid)['provenance'][0]
        height = span['bbox'][3] - span['bbox'][1]
        span['page_index'] = page
        span['bbox'] = [span['bbox'][0], y, span['bbox'][2], y + height]

    def _tokens(self):
        return [f['token'] for f in self.check(self.ir, [38])['38']['findings']]

    def test_chapters_at_page_top_pass(self):
        self.assertEqual(self._tokens(), [])

    def test_previous_chapter_text_above_chapter_heading_fails(self):
        self._move('main-heading', 5, 200)
        self._add('prior-text', 'Paragraph', '上一章末段的延续文字。', 5, 120)
        self.assertEqual(self._tokens(), ['第2章方法'])

    def test_same_baseline_title_fragment_is_not_prior_content(self):
        # Real theses centre 第4 章 and the title on one baseline; the title glyph
        # group can start a few points higher and must not count as prior content.
        self._add('title-fragment', 'Heading', '方法研究', 5, 103, x=200, height=18)
        self.assertEqual(self._tokens(), [])

    def test_running_header_above_heading_is_ignored(self):
        # Even-page headers carry the thesis name and the current chapter; they sit
        # above the top margin and are 12.6 pt tall in the archive, so rows() keeps them.
        self._add('running-header', 'Paragraph', '上海交通大学硕士学位论文', 5, 60, height=13)
        self._add('running-header-chapter', 'Paragraph', '第2章 方法', 5, 60, x=400, height=13)
        self.assertEqual(self._tokens(), [])

    def test_chapter_outline_line_in_body_type_is_not_a_chapter_opening(self):
        # 论文组织结构 sections list each chapter as a body-size line: "第3章 主要内容安排".
        self._move('main-heading', 5, 200)
        self._add('prior-text', 'Paragraph', '上一章末段的延续文字。', 5, 120)
        self._add('outline-prose', 'Paragraph', '第3章 主要内容安排', 5, 230)
        self.assertEqual(self._tokens(), ['第2章方法'])

    def test_chapter_outline_page_is_not_a_chapter_opening(self):
        for offset, text in enumerate(['第一章 绪论', '第二章 方法', '第三章 总结']):
            self._add(f'outline-{offset}', 'Heading', text, 5, 150 + offset * 30, height=18)
        self.assertEqual(self._tokens(), [])

    def test_toc_dot_leader_is_not_a_chapter_label(self):
        self._add('toc-entry', 'Paragraph', '第2章 方法................12', 5, 150, height=18)
        self.assertEqual(self._tokens(), [])

    def test_front_matter_chapter_label_is_excluded(self):
        self._add('front-label', 'Paragraph', '第2章 方法', 2, 150, height=18)
        self._add('front-body', 'Paragraph', '摘要正文。', 2, 120)
        self.assertEqual(self._tokens(), [])

    def test_subsection_heading_is_not_a_chapter_label(self):
        self._add('subsection', 'Paragraph', '2.1 方法', 5, 150, height=18)
        self.assertEqual(self._tokens(), [])

    def test_long_chapter_title_is_still_a_chapter_label(self):
        self._move('conclusion-heading', 6, 200)
        self._add('prior-text', 'Paragraph', '上一章末段的延续文字。', 6, 120)
        node = next(n for n in self.ir['nodes'] if n['id'] == 'conclusion-heading')
        node['text'] = '第3章 基于深度学习的文档结构建模与验证方法研究'
        self.assertEqual(self._tokens(), ['第3章基于深度学习的文档结构建模与验证方法研究'])

    def test_two_chapters_on_one_page_flag_the_lower_one(self):
        self._add('next-heading', 'Paragraph', '第3章 总结', 5, 200, height=18)
        self._add('prior-text', 'Paragraph', '上一章末段的延续文字。', 5, 120)
        self.assertEqual(self._tokens(), ['第3章总结'])

    def test_partial_coverage_reports_visible_violation(self):
        self.ir['coverage']['pages']['status'] = 'partial'
        self._move('main-heading', 5, 200)
        self._add('prior-text', 'Paragraph', '上一章末段的延续文字。', 5, 120)
        result = self.check(self.ir, [38])['38']
        self.assertEqual(len(result['findings']), 1)
        self.assertIn('仅检查可读取文字', result['reason'])

    def test_synthetic_mutation_still_resolves_location(self):
        self._move('main-heading', 5, 200)
        self._add('prior-text', 'Paragraph', '上一章末段的延续文字。', 5, 120)
        node = next(n for n in self.ir['nodes'] if n['id'] == 'main-heading')
        node['provenance'] = [{'kind': 'synthetic', 'operation_id': 'case-1',
                               'ancestor_provenance': node['provenance']}]
        finding = self.check(self.ir, [38])['38']['findings'][0]
        self.assertEqual(finding['node_id'], 'main-heading')
        self.assertEqual(finding['location']['page_number'], 6)


if __name__ == '__main__':
    unittest.main()
