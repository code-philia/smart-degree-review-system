"""Native titled illustration pages must not be mistaken for unparsed prose."""
from pathlib import Path
import unittest
from pdf_rules.layout_context import captioned_native_graphic
from pdf_rules.model import PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject

class CaptionedResearchImageRecoveryTests(unittest.TestCase):
    box=(80,99,500,800)
    def page(self,caption):
        return PdfPage(1,595,842,(caption,),unreadable=True,images=(self.box,))
    def figure(self):return LayoutObject('figure',1,self.box,'',595,842,'image_body')

    def test_large_bottom_illustration_with_native_caption_is_resolved(self):
        cap=PdfLine(1,'图5.6 运动生成结果',(120,810,490,826),595,842)
        self.assertTrue(captioned_native_graphic(self.page(cap),[self.figure()],[self.box]))

    def test_sideways_native_caption_resolves_its_adjacent_illustration(self):
        cap=PdfLine(1,'图5-6 运动生成结果',(520,150,535,790),595,842,direction=(0,-1))
        self.assertTrue(captioned_native_graphic(self.page(cap),[self.figure()],[self.box]))

    def test_layout_label_alone_does_not_resolve_unread_body(self):
        cap=PdfLine(1,'图5.6 运动生成结果',(120,810,490,826),595,842,source='mineru')
        self.assertFalse(captioned_native_graphic(self.page(cap),[self.figure()],[self.box]))

    def test_partial_figure_layout_does_not_resolve_a_whole_scan(self):
        cap=PdfLine(1,'图5.6 运动生成结果',(120,810,490,826),595,842)
        partial=LayoutObject('figure',1,(80,650,500,800),'',595,842,'image_body')
        self.assertFalse(captioned_native_graphic(self.page(cap),[partial],[self.box]))

    def test_unrelated_side_caption_does_not_resolve_scan(self):
        cap=PdfLine(1,'图5-6 运动生成结果',(520,10,535,70),595,842,direction=(0,-1))
        self.assertFalse(captioned_native_graphic(self.page(cap),[self.figure()],[self.box]))
