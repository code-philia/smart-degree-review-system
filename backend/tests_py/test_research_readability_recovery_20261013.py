"""Recover bounded research images while retaining incomplete prose scans."""
from dataclasses import replace
import json
from pathlib import Path
import unittest

from pdf_rules.layout_context import _native_caption_carrier, captioned_native_graphic, recover_document
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.model import PdfDocument, PdfLine, PdfPage
from pdf_rules.pdf_extract import extract_pdf


def physical_cases():
    path = Path(__file__).parent / 'fixtures/research_image_readability_20261013.json'
    for case in json.loads(path.read_text()):
        page_data = case['page']
        page_data['lines'] = tuple(PdfLine(**line) for line in page_data['lines'])
        page_data['images'] = tuple(tuple(box) for box in page_data['images'])
        yield case, PdfPage(**page_data), [LayoutObject(**obj) for obj in case['objects']]


class ResearchReadabilityRecoveryTests(unittest.TestCase):
    def test_real_left_native_caption_does_not_hide_unread_raster_column(self):
        path = Path(__file__).parent / 'fixtures/native_caption_left_unread_scanned_right.pdf'
        document = extract_pdf(path)
        page = document.pages[0]
        self.assertTrue(page.unreadable)
        self.assertNotIn('Unextracted method', '\n'.join(line.text for line in page.lines))
        image, scan = (80, 60, 520, 520), (80, 530, 520, 650)
        caption = '\n'.join(line.text for line in page.lines)
        # Cover both a correctly bounded left caption and an overwide parser
        # envelope: neither can establish the unread right raster column.
        for cloud_box in ((80, 530, 200, 650), scan):
            with self.subTest(cloud_box=cloud_box):
                objects = [LayoutObject('figure', 1, image, '', 600, 800, 'image_body'),
                           LayoutObject('figure_caption', 1, cloud_box, caption, 600, 800, 'image_caption')]
                self.assertFalse(_native_caption_carrier(page, objects, scan))
                self.assertFalse(captioned_native_graphic(page, objects, page.images))
                self.assertTrue(recover_document(document, objects).pages[0].unreadable)

    def test_real_consecutive_native_panel_explanations_resolve_eight_images(self):
        case, page, objects = next(physical_cases())
        recovered = recover_document(PdfDocument(Path(case['source_pdf']), (page,)), objects)
        self.assertFalse(recovered.pages[0].unreadable)
        self.assertEqual(len(page.images), 8)
        self.assertEqual(recovered.pages[0].images, page.images)
        self.assertEqual([obj.bbox for obj in objects if obj.kind == 'figure'][0],
                         [52.02796702665441, 98.10720371604675, 277.1489781996783, 232.25378838900863])

    def test_real_native_caption_raster_copies_do_not_hide_matching_scientific_images(self):
        for case, page, objects in list(physical_cases())[1:]:
            with self.subTest(page=page.number):
                recovered = recover_document(PdfDocument(Path(case['source_pdf']), (page,)), objects)
                self.assertFalse(recovered.pages[0].unreadable)
                self.assertEqual(recovered.pages[0].images, page.images)
                native = [line for line in recovered.pages[0].lines if line.source == 'native']
                self.assertEqual(native, sorted(page.lines, key=lambda line: (line.bbox[1], line.bbox[0])))

    def test_cloud_panel_labels_without_native_explanations_do_not_resolve(self):
        _, page, objects = next(physical_cases())
        page = replace(page, lines=tuple(replace(line, source='mineru') for line in page.lines))
        self.assertFalse(captioned_native_graphic(page, objects, page.images))

    def test_nonconsecutive_panel_explanations_do_not_prove_whole_image_page(self):
        _, page, objects = next(physical_cases())
        page = replace(page, lines=tuple(replace(line, text=line.text.replace('(b)', '(z)'))
                                         for line in page.lines))
        self.assertFalse(captioned_native_graphic(page, objects, page.images))

    def test_partial_graphic_layout_does_not_resolve_unrecognized_image_area(self):
        _, page, objects = next(physical_cases())
        objects = [obj for obj in objects if not (obj.kind == 'figure' and obj.bbox[1] > 550)]
        self.assertFalse(captioned_native_graphic(page, objects, page.images))

    def test_native_caption_start_does_not_resolve_unread_lower_prose(self):
        image = (80, 120, 520, 560)
        scan = (80, 570, 520, 740)
        line = PdfLine(1, '图1.1 这是科研图片的原生图注，后面的扫描正文仍未识别。',
                       (80, 572, 520, 584), 600, 800)
        page = PdfPage(1, 600, 800, (line,), True, (image, scan))
        objects = [LayoutObject('figure', 1, image, '', 600, 800, 'image_body'),
                   LayoutObject('figure_caption', 1, scan, line.text, 600, 800, 'image_caption')]
        self.assertFalse(captioned_native_graphic(page, objects, page.images))

    def test_full_page_scan_with_native_caption_keeps_unreadable(self):
        image = (0, 0, 600, 800)
        line = PdfLine(1, '图1.1 扫描页中的一个图注', (80, 740, 520, 755), 600, 800)
        page = PdfPage(1, 600, 800, (line,), True, (image,))
        objects = [LayoutObject('figure', 1, image, '', 600, 800, 'image_body')]
        self.assertFalse(captioned_native_graphic(page, objects, page.images))


if __name__ == '__main__':
    unittest.main()
