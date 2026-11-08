"""Rule 38 distinguishes repeated running furniture from prior chapter prose."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from paper_compiler.local_checks import detect_ir
from test_fast_local_checks import sample_ir


class ChapterRunningHeaderEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.ir = sample_ir()
        for nid in ('intro-heading', 'main-heading', 'conclusion-heading'):
            span = next(node for node in self.ir['nodes'] if node['id'] == nid)['provenance'][0]
            span['bbox'] = [60, 124, span['bbox'][2], 142]

    def _add(self, nid, text, page, y=80, height=9, x=60):
        self.ir['nodes'].append({
            'id': nid, 'kind': 'Paragraph', 'text': text, 'attrs': {}, 'children': [],
            'provenance': [{
                'kind': 'source', 'source_id': 'pdf', 'page_index': page,
                'bbox': [x, y, x + len(text) * 5, y + height],
                'coordinate_system': 'unrotated_top_left_points',
                'node_text_start': 0, 'node_text_end': len(text),
            }],
        })
        self.ir['nodes'][0]['children'].append(nid)

    def _banner(self):
        # The 10% position is inside the band retained for true carry-over prose.
        for page in (4, 5, 6):
            self._add(f'banner-{page}', 'A recurring publication banner', page)

    def _tokens(self):
        return [finding['token'] for finding in detect_ir(self.ir, [38])['38']['findings']]

    def test_repeated_small_banner_above_chapter_is_ignored(self):
        self._banner()
        self.assertEqual(self._tokens(), [])

    def test_alternating_odd_even_headers_are_ignored(self):
        # Evidence need not occur on consecutive pages or on both page parities.
        for page in (4, 6):
            self._add(f'odd-{page}', 'Recurring left-page banner', page, x=70)
        for page in (5, 7):
            self._add(f'even-{page}', 'Recurring right-page banner', page, x=350)
        self.assertEqual(self._tokens(), [])

    def test_small_repeated_current_chapter_title_is_ignored(self):
        self._add('chapter-header', '第2章 方法', 5)
        self._add('chapter-header-peer', '第2章 方法', 7)
        self.assertEqual(self._tokens(), [])

    def test_genuine_prose_below_repeated_header_still_flags(self):
        self._banner()
        self._add('prior-prose', 'A preceding chapter continues on this line.', 5,
                  y=98, height=12)
        self.assertEqual(self._tokens(), ['第2章方法'])

    def test_unique_small_prior_text_still_flags(self):
        self._add('unique-prior', 'Unique small preceding text.', 5)
        self.assertEqual(self._tokens(), ['第2章方法'])

    def test_repeated_body_size_prior_text_still_flags(self):
        for page in (5, 6):
            self._add(f'body-{page}', 'The repeated body sentence continues.', page,
                      height=12)
        self.assertEqual(self._tokens(), ['第2章方法', '第3章总结与展望'])

    def test_repeated_text_at_other_height_is_not_header_evidence(self):
        self._add('prior-small', 'Repeated words at different heights.', 5)
        self._add('body-peer', 'Repeated words at different heights.', 6, y=300)
        self.assertEqual(self._tokens(), ['第2章方法'])

    def test_repeated_small_body_text_below_top_strip_still_flags(self):
        for nid in ('main-heading', 'conclusion-heading'):
            span = next(node for node in self.ir['nodes'] if node['id'] == nid)['provenance'][0]
            span['bbox'] = [60, 200, span['bbox'][2], 218]
        for page in (5, 6):
            self._add(f'body-small-{page}', 'Repeated small body text.', page, y=140)
        self.assertEqual(self._tokens(), ['第2章方法', '第3章总结与展望'])

    def test_same_page_duplicates_are_not_repeated_page_evidence(self):
        self._add('same-page-left', 'Repeated short words', 5, x=60)
        self._add('same-page-right', 'Repeated short words', 5, x=400)
        self.assertEqual(self._tokens(), ['第2章方法'])


if __name__ == '__main__':
    unittest.main()
