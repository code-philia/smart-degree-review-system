"""Native adjacent image tiles share one independently matched outer caption."""
from dataclasses import replace
from pathlib import Path
import json
import unittest
from pdf_rules.layout_context import captioned_native_graphic,recover_document
from pdf_rules.model import PdfDocument,PdfLine,PdfPage
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.index import build_index

def actual():
    data=json.loads((Path(__file__).parent/'fixtures/hu73_adjacent_image_tiles_20261014.json').read_text())
    p=data['page'];p['lines']=tuple(PdfLine(**dict(l,direction=tuple(l['direction']),bbox=tuple(l['bbox']))) for l in p['lines'])
    p['images']=tuple(tuple(r) for r in p['images'])
    objects=[LayoutObject(**dict(o,bbox=tuple(o['bbox']),text_lines=tuple((t,tuple(b)) for t,b in o['text_lines']),panel_boxes=tuple(tuple(b) for b in o['panel_boxes']),parent_bbox=tuple(o['parent_bbox']) if o['parent_bbox'] is not None else None)) for o in data['objects']]
    return data,PdfPage(**p),objects

class AdjacentNativeImageTileRecoveryTests(unittest.TestCase):
    def test_actual73_shared_caption_resolves_both_tiles_without_discarding_text(self):
        data,page,objects=actual()
        self.assertTrue(page.unreadable);self.assertEqual(len(page.images),2)
        recovered=recover_document(PdfDocument(Path(data['source_pdf']),(page,)),objects).pages[0]
        self.assertFalse(recovered.unreadable)
        self.assertEqual(recovered.images,page.images)
        self.assertEqual([l for l in recovered.lines if l.source=='native'],sorted(page.lines,key=lambda l:(l.bbox[1],l.bbox[0])))
    def test_cloud_figure_without_native_caption_cannot_certify_scanned_prose(self):
        _,page,objects=actual();page=replace(page,lines=tuple(replace(l,source='mineru') for l in page.lines))
        self.assertFalse(captioned_native_graphic(page,objects,page.images))
    def test_native_caption_without_independent_matching_cloud_caption_is_insufficient(self):
        _,page,objects=actual();objects=[o for o in objects if o.kind!='figure_caption']
        self.assertFalse(captioned_native_graphic(page,objects,page.images))
    def test_separate_parsed_figures_do_not_share_one_caption(self):
        _,page,objects=actual()
        objects=[o for o in objects if o.kind!='figure']
        objects += [LayoutObject('figure',73,box,'',page.width,page.height,'image_body') for box in page.images]
        self.assertFalse(captioned_native_graphic(page,objects,page.images))
    def test_noncontiguous_native_images_do_not_share_one_caption(self):
        _,page,objects=actual();upper,lower=page.images
        upper=(upper[0],upper[1],upper[2],upper[3]-5)
        page=replace(page,images=(upper,lower))
        self.assertFalse(captioned_native_graphic(page,objects,page.images))
    def test_unaligned_native_images_do_not_share_one_caption(self):
        _,page,objects=actual();upper,lower=page.images
        page=replace(page,images=((upper[0]+5,upper[1],upper[2],upper[3]),lower))
        self.assertFalse(captioned_native_graphic(page,objects,page.images))
    def test_native_text_in_seam_prevents_shared_caption(self):
        _,page,objects=actual();upper,lower=page.images
        seam=PdfLine(73,'Fig9.9',(upper[0]+10,upper[3],upper[0]+70,lower[1]),page.width,page.height)
        page=replace(page,lines=page.lines+(seam,))
        self.assertFalse(captioned_native_graphic(page,objects,page.images))
    def test_independent_caption_inside_upper_tile_prevents_shared_caption(self):
        _,page,objects=actual();upper=page.images[0]
        line=PdfLine(73,'Figure 9.9 independent figure',(upper[0]+10,upper[1]+100,upper[0]+170,upper[1]+113),page.width,page.height)
        page=replace(page,lines=page.lines+(line,))
        self.assertFalse(captioned_native_graphic(page,objects,page.images))
    def test_each_tile_still_requires_figure_coverage(self):
        _,page,objects=actual();lower=page.images[1]
        objects=[replace(o,bbox=lower) if o.kind=='figure' else o for o in objects]
        self.assertFalse(captioned_native_graphic(page,objects,page.images))
    def test_native_reference_overlay_is_preserved_and_indexed(self):
        data,page,objects=actual();upper=page.images[0]
        line=PdfLine(73,'\u8be6\u89c1Fig9.9',(upper[0]+10,upper[1]+10,upper[0]+70,upper[1]+20),page.width,page.height)
        page=replace(page,lines=page.lines+(line,))
        document=recover_document(PdfDocument(Path(data['source_pdf']),(page,)),objects)
        self.assertFalse(document.pages[0].unreadable)
        self.assertIn(line,document.lines)
        self.assertIn('9.9',[r.number for r in build_index(document,objects).graphic_figure_refs+build_index(document,objects).figure_refs])
if __name__=='__main__':unittest.main()
