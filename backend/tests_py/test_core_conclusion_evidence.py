"""Real final chapters survive running contents labels; genuine absence does not."""
import copy
import unittest

from paper_compiler.structure import assess_structure


def line(text, y=130, size=18, x=180):
    return {'text': text, 'bbox': [x, y, x + min(450, max(10, len(text) * size)), y + size],
            'font_size': size, 'is_bold': size >= 16, 'chars': []}


def thesis(*, ending='全文总结与研究展望', header='目录', chapter=7,
           subsection=False, header_only=False, contents_only=False):
    prose = '本文提出一种方法，并通过实验对方法进行评估和分析。'
    def page(lines):
        return {'height': 842, 'width': 595, 'lines': lines}
    pages = [page([line('目录', x=250), line('第1章 绪论 ............ 1', 190, 12, 85),
                  line('第2章 方法 ............ 2', 220, 12, 85),
                  line(f'第{chapter}章 {ending} ............ 3', 250, 12, 85)])]
    for number, title in [(1, '绪论'), (2, '方法'), (chapter, ending)]:
        lines = [line(header, 60, 9, 490)] if header else []
        if header_only:
            lines.append(line(f'第{chapter}章 {ending}', 60, 9, 340))
        if number != chapter or not (subsection or header_only or contents_only):
            lines.append(line(f'第{number}章 {title}'))
        if number == chapter and subsection:
            lines.append(line(f'{chapter}.1 全文总结'))
        lines += [line(prose, 200 + k * 25, 12, 85) for k in range(5)]
        pages.append(page(lines))
    pages.append(page([line('参考文献'), line('[1] A book [M]. 2020.', 190, 12, 85)]))
    return pages


def sections(pages):
    return assess_structure(pages, {'signals': {'academic_cover': True}})['observed_sections']


class CoreConclusionEvidenceTests(unittest.TestCase):
    def test_full_summary_and_research_outlook_is_a_final_chapter(self):
        self.assertTrue(sections(thesis(header=None))['结论'])

    def test_repeated_contents_header_does_not_hide_real_body_conclusion(self):
        self.assertTrue(sections(thesis(ending='总结与展望'))['结论'])

    def test_chapter_number_is_not_document_specific(self):
        for number in (3, 7, 9):
            with self.subTest(chapter=number):
                self.assertTrue(sections(thesis(chapter=number))['结论'])

    def test_contents_running_label_aliases_do_not_hide_real_chapter(self):
        for header in ('目录', '目 录', '目次', 'Contents', 'Table of Contents'):
            with self.subTest(header=header):
                self.assertTrue(sections(thesis(header=header))['结论'])

    def test_actual_contents_page_remains_observed(self):
        self.assertTrue(sections(thesis())['目录'])

    def test_short_true_contents_with_repeated_label_remains_observed(self):
        pages = thesis(ending='总结与展望')
        pages[0]['lines'][0] = line('目录', 60, 9, 490)
        self.assertTrue(sections(pages)['目录'])

    def test_small_body_size_conclusion_under_stale_label_is_not_evidence(self):
        pages = thesis(ending='总结与展望')
        pages[3]['lines'][1] = line('第7章 总结与展望', 130, 12)
        self.assertFalse(sections(pages)['结论'])

    def test_leaderless_annotated_contents_is_not_final_chapter(self):
        pages = thesis(ending='总结与展望', contents_only=True)
        pages[0]['lines'] = [line('目录', 60, 9, 490),
                             line('第7章 总结与展望', 130, 18, 100), line('3', 130, 12, 490)]
        pages[0]['lines'] += [line('本章总结了全文的研究内容并介绍了将来的工作方向。',
                                  200 + k * 25, 12, 85) for k in range(5)]
        self.assertFalse(sections(pages)['结论'])

    def test_only_contents_entry_cannot_supply_missing_conclusion(self):
        self.assertFalse(sections(thesis(contents_only=True))['结论'])

    def test_only_summary_subsection_cannot_supply_missing_final_chapter(self):
        self.assertFalse(sections(thesis(subsection=True))['结论'])

    def test_only_running_conclusion_header_cannot_supply_missing_final_chapter(self):
        self.assertFalse(sections(thesis(header_only=True))['结论'])

    def test_alias_substring_in_prose_is_not_a_conclusion_heading(self):
        self.assertFalse(sections(thesis(ending='全文总结与研究展望的方法介绍'))['结论'])

    def test_observation_does_not_modify_input_pages(self):
        pages = thesis()
        before = copy.deepcopy(pages)
        sections(pages)
        self.assertEqual(pages, before)


if __name__ == '__main__':
    unittest.main()
