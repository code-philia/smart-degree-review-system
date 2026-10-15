"""Caption direction conflicts must not move an alarm to a captioned neighbour."""
from pathlib import Path
import unittest

from pdf_rules.caption_rules import detect_caption_rules
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.model import PdfDocument, PdfLine, PdfPage


class CaptionAssociationTests(unittest.TestCase):
    def obj(self, kind, box, text='', page=1):
        return LayoutObject(kind, page, box, text, 600, 800)

    def detect(self, objects, rules=(13,)):
        # Exercise both layout preparation and association, including native titles.
        pages = tuple(PdfPage(number, 600, 800, tuple(
            PdfLine(number, obj.text, obj.bbox, 600, 800)
            for obj in objects if obj.page_number == number and obj.kind.endswith('_caption')))
            for number in sorted({obj.page_number for obj in objects}))
        document = PdfDocument(Path('paper.pdf'), pages)
        return detect_caption_rules(prepare_caption_layout(objects, document), rules, document)

    def boxes(self, result, rule=13):
        return [tuple(f['location']['bounding_rect'][k] for k in ('x1','y1','x2','y2'))
                for f in result[str(rule)]['findings']]

    def test_between_figures_caption_belongs_to_upper_figure_even_when_lower_is_closer(self):
        upper = self.obj('figure', (80, 100, 520, 270))
        lower = self.obj('figure', (180, 310, 420, 550))
        captions = [self.obj('figure_caption', (220, 280, 380, 292), '图2.7 视频样例'),
                    self.obj('figure_caption', (200, 294, 400, 306), 'Figure 2.7 Video examples')]
        # A separate unambiguous below-title pair establishes the paper's style.
        style = [self.obj('figure', (100, 150, 500, 350), page=2),
                 self.obj('figure_caption', (200, 360, 400, 380), '图2.9 其他实验', page=2)]
        # A caption-less lower figure must be reported in either extraction order.
        for objects in ([upper, lower, *captions, *style], [lower, *captions, upper, *style]):
            with self.subTest(order=[o.kind for o in objects]):
                self.assertEqual(self.boxes(self.detect(objects)), [(180, 310, 420, 550)])

    def test_two_captioned_figures_with_close_bilingual_titles_have_no_alarm(self):
        objects = [self.obj('figure', (80, 100, 520, 270)),
                   self.obj('figure', (180, 310, 420, 550)),
                   self.obj('figure_caption', (220, 280, 380, 292), '图2.7 视频样例'),
                   self.obj('figure_caption', (200, 294, 400, 306), 'Figure 2.7 Video examples'),
                   self.obj('figure_caption', (200, 560, 400, 572), '图2.8 第二项样例')]
        self.assertEqual(self.boxes(self.detect(objects)), [])

    def test_figure_caption_above_an_isolated_figure_is_still_supported(self):
        objects = [self.obj('figure', (100, 250, 500, 470)),
                   self.obj('figure_caption', (180, 220, 420, 235), '图3.1 上置图题')]
        self.assertEqual(self.boxes(self.detect(objects)), [])

    def test_two_above_figure_titles_are_not_lost_to_a_neighbour(self):
        objects = [self.obj('figure', (80, 100, 520, 250)),
                   self.obj('figure', (180, 290, 420, 550)),
                   self.obj('figure_caption', (200, 80, 400, 95), '图1.1 第一幅图'),
                   self.obj('figure_caption', (200, 270, 400, 285), '图1.2 第二幅图')]
        self.assertEqual(self.boxes(self.detect(objects)), [])

    def test_ambiguous_title_without_style_evidence_keeps_nearest_assignment(self):
        objects = [self.obj('figure', (80, 100, 520, 250)),
                   self.obj('figure', (180, 290, 420, 550)),
                   self.obj('figure_caption', (200, 270, 400, 285), '图1.2 第二幅图')]
        self.assertEqual(self.boxes(self.detect(objects)), [(80, 100, 520, 250)])

    def test_above_title_style_from_another_page_is_used_for_ambiguous_pair(self):
        objects = [self.obj('figure', (80, 100, 520, 270)),
                   self.obj('figure', (180, 310, 420, 550)),
                   self.obj('figure_caption', (200, 275, 400, 290), '图1.2 第二幅图'),
                   self.obj('figure', (100, 150, 500, 350), page=2),
                   self.obj('figure_caption', (200, 120, 400, 135), '图2.1 上置图题', page=2)]
        self.assertEqual(self.boxes(self.detect(objects)), [(80, 100, 520, 270)])

    def test_local_above_title_evidence_takes_precedence_over_other_pages(self):
        objects = [self.obj('figure', (80, 100, 520, 270)),
                   self.obj('figure', (180, 310, 420, 550)),
                   self.obj('figure_caption', (200, 275, 400, 290), '图1.2 第二幅图'),
                   self.obj('figure', (10, 650, 160, 730)),
                   self.obj('figure_caption', (10, 610, 160, 625), '图1.3 上置图题')]
        for page in (2,3):
            objects.extend([self.obj('figure', (100, 150, 500, 350), page=page),
                            self.obj('figure_caption', (200, 360, 400, 380), f'图{page}.1 下置图题', page=page)])
        self.assertEqual(self.boxes(self.detect(objects)), [(80, 100, 520, 270)])

    def test_valid_above_title_pairs_survive_a_dominant_below_title_style(self):
        objects = [self.obj('figure', (80, 100, 520, 250)),
                   self.obj('figure', (180, 290, 420, 550)),
                   self.obj('figure_caption', (200, 80, 400, 95), '图1.1 第一幅图'),
                   self.obj('figure_caption', (200, 270, 400, 285), '图1.2 第二幅图'),
                   self.obj('figure', (100, 650, 500, 710)),
                   self.obj('figure_caption', (200, 720, 400, 735), '图1.3 第三幅图'),
                   self.obj('figure', (100, 150, 500, 350), page=2),
                   self.obj('figure_caption', (200, 360, 400, 380), '图2.1 第四幅图', page=2)]
        self.assertEqual(self.boxes(self.detect(objects)), [])

    def test_missing_caption_on_both_figures_reports_both_objects(self):
        objects = [self.obj('figure', (80, 100, 520, 270)),
                   self.obj('figure', (180, 310, 420, 550))]
        self.assertCountEqual(self.boxes(self.detect(objects)),
                              [(80, 100, 520, 270), (180, 310, 420, 550)])

    def test_table_caption_between_tables_keeps_existing_nearest_assignment(self):
        objects = [self.obj('table', (80, 100, 520, 270)),
                   self.obj('table', (180, 310, 420, 550)),
                   self.obj('table_caption', (200, 284, 400, 305), '表4.3 实验结果')]
        self.assertEqual(self.boxes(self.detect(objects, (14,)), 14), [(80, 100, 520, 270)])


if __name__ == '__main__':
    unittest.main()
