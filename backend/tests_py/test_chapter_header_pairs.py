"""Corroborated chapter/header pairs may use the same font size as prose."""
import unittest

from paper_compiler.local_checks import detect_ir
from test_fast_local_checks import sample_ir


class ChapterHeaderPairTests(unittest.TestCase):
    def setUp(self):
        self.ir = sample_ir()
        for name in ('intro-heading', 'main-heading', 'conclusion-heading'):
            node = next(n for n in self.ir['nodes'] if n['id'] == name)
            node['provenance'][0]['bbox'][1] = 124
            node['provenance'][0]['bbox'][3] = 142

    def add(self, name, text, page, x, y=80, height=12):
        self.ir['nodes'].append({'id': name, 'kind': 'Paragraph', 'text': text,
            'attrs': {}, 'children': [], 'provenance': [{'kind': 'source', 'source_id': 'pdf',
                'page_index': page, 'bbox': [x, y, x + len(text) * 5, y + height],
                'coordinate_system': 'unrotated_top_left_points',
                'node_text_start': 0, 'node_text_end': len(text)}]})
        self.ir['nodes'][0]['children'].append(name)

    def pair(self, page, *, title='第2章 方法', height=12, swap=False):
        self.add(f'banner-{page}', 'A recurring journal', page, 430 if swap else 60, height=height)
        self.add(f'current-{page}', title, page, 60 if swap else 430, height=height)

    def tokens(self):
        return [f['token'] for f in detect_ir(self.ir, [38])['38']['findings']]

    def test_body_size_paired_running_header_is_not_previous_chapter_prose(self):
        self.pair(5)
        self.pair(7)
        self.assertEqual(self.tokens(), [])

    def test_mirrored_body_size_header_pair_is_also_ignored(self):
        self.pair(5, swap=True)
        self.pair(7, swap=True)
        self.assertEqual(self.tokens(), [])

    def test_distinct_recurring_fields_with_moderate_gap_are_headers(self):
        width = self.ir['layout']['pages'][0]['width']
        for page in (5, 7):
            self.add(f'banner-{page}', 'A recurring journal', page, 60)
            self.add(f'current-{page}', '第2章 方法', page,
                     60 + len('A recurring journal') * 5 + width * .11)
        self.assertEqual(self.tokens(), [])

    def test_repeated_header_plus_true_prior_body_line_still_flags(self):
        self.pair(5)
        self.pair(7)
        self.add('carry', 'The previous chapter continues.', 5, 60, y=107)
        self.assertEqual(self.tokens(), ['第2章方法'])

    def test_single_page_pair_is_not_enough_evidence(self):
        self.pair(5)
        self.assertEqual(self.tokens(), ['第2章方法'])

    def test_repeated_pair_without_a_corresponding_chapter_heading_still_flags(self):
        self.pair(5, title='A different body fragment')
        self.pair(7, title='A different body fragment')
        self.assertEqual(self.tokens(), ['第2章方法'])

    def test_repeated_body_sentence_alone_is_not_a_header_pair(self):
        for page in (5, 7):
            self.add(f'body-{page}', 'The previous chapter continues.', page, 60)
        self.assertEqual(self.tokens(), ['第2章方法'])

    def test_repeated_header_text_below_top_band_still_flags(self):
        for page in (5, 7):
            self.add(f'banner-{page}', 'A recurring journal', page, 60, y=104)
            self.add(f'current-{page}', '第2章 方法', page, 430, y=104)
        self.assertEqual(self.tokens(), ['第2章方法'])

    def test_pair_with_sentence_punctuation_remains_prose(self):
        for page in (5, 7):
            self.add(f'banner-{page}', 'The old chapter ends.', page, 60)
            self.add(f'current-{page}', '第2章 方法', page, 430)
        self.assertEqual(self.tokens(), ['第2章方法'])

    def test_subsection_cannot_corroborate_removing_real_prior_body(self):
        self.add('subsection', '2.1 实验设置', 4, 180, y=150, height=18)
        self.ir['nodes'][-1]['kind'] = 'Heading'
        self.ir['nodes'][-1]['attrs'] = {'level': 2}
        for page in (5, 7):
            self.add(f'subsection-header-{page}', '2.1 实验设置', page, 430)
            self.add(f'real-short-tail-{page}', '继续使用上一节的实验设置', page, 60)
        self.assertEqual(self.tokens(), ['第2章方法'])

    def test_joined_fields_require_independent_recurring_prefix(self):
        for page in (5, 7):
            self.add(f'combined-{page}', 'A recurring journal 第2章 方法', page, 60)
        self.assertEqual(self.tokens(), ['第2章方法'])
        for page in (0, 1):
            self.add(f'prefix-{page}', 'A recurring journal', page, 60)
        self.assertEqual(self.tokens(), [])



if __name__ == '__main__':
    unittest.main()
