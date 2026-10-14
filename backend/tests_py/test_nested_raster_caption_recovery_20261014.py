"""Real contained graphic layers share caption association, retain text/coverage."""
from dataclasses import replace
import json
from pathlib import Path
import unittest
from pdf_rules.layout_context import captioned_native_graphic,recover_document
from pdf_rules.model import PdfDocument,PdfLine,PdfPage
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.index import build_index

def actual():
 data=json.loads((Path(__file__).parent/'fixtures/liu121_nested_raster_recovery_20261014.json').read_text())
 p=data['page'];p['lines']=tuple(PdfLine(**dict(l,direction=tuple(l['direction']),bbox=tuple(l['bbox']))) for l in p['lines'])
 p['images']=tuple(tuple(r) for r in p['images'])
 return data,PdfPage(**p),[LayoutObject(**dict(o,bbox=tuple(o['bbox']),text_lines=tuple((t,tuple(b)) for t,b in o['text_lines']),panel_boxes=tuple(tuple(b) for b in o['panel_boxes']),parent_bbox=tuple(o['parent_bbox']) if o['parent_bbox'] is not None else None)) for o in data['objects']]

class NestedRasterCaptionRecoveryTests(unittest.TestCase):
 def test_actual121_initial_vlm_resolves_nested_native_label_carriers(self):
  data,page,objects=actual()
  self.assertTrue(page.unreadable);self.assertEqual(len(page.images),3)
  self.assertEqual([l.text for l in page.lines if len(l.text)==4 and abs(l.direction[1])>.8],['本章方法','本章方法'])
  recovered=recover_document(PdfDocument(Path(data['source_pdf']),(page,)),objects).pages[0]
  self.assertFalse(recovered.unreadable)
  self.assertEqual(recovered.images,page.images)
  self.assertEqual([l for l in recovered.lines if l.source=='native'],sorted(page.lines,key=lambda l:(l.bbox[1],l.bbox[0])))
 def test_tiny_layers_without_parent_remain_unreadable(self):
  _,page,objects=actual();page=replace(page,images=page.images[1:])
  self.assertFalse(captioned_native_graphic(page,objects,page.images))
 def test_separate_tiny_layer_does_not_inherit_main_caption(self):
  _,page,objects=actual()
  extra=(25,155,40,180);page=replace(page,images=page.images+(extra,))
  objects+=[LayoutObject('figure',121,extra,'',page.width,page.height,'image_body')]
  self.assertFalse(captioned_native_graphic(page,objects,page.images))
 def test_nested_layer_still_requires_its_own_figure_coverage(self):
  _,page,objects=actual()
  objects=[replace(o,bbox=(81,100,479,650)) if o.kind=='figure' else o for o in objects]
  self.assertFalse(captioned_native_graphic(page,objects,page.images))
 def test_parent_still_requires_independent_native_caption(self):
  _,page,objects=actual();page=replace(page,lines=tuple(replace(l,source='mineru') for l in page.lines))
  self.assertFalse(captioned_native_graphic(page,objects,page.images))
 def test_native_overlay_reference_is_retained_and_indexed(self):
  data,page,objects=actual();target=next(l for l in page.lines if l.text=='本章方法')
  page=replace(page,lines=tuple(replace(l,text='详见Fig9.9',text_regions=()) if l is target else l for l in page.lines))
  document=recover_document(PdfDocument(Path(data['source_pdf']),(page,)),objects)
  self.assertFalse(document.pages[0].unreadable)
  self.assertTrue(any(l.text=='详见Fig9.9' and l.source=='native' for l in document.lines))
  index=build_index(document,objects)
  self.assertIn('9.9',[r.number for r in index.graphic_figure_refs+index.figure_refs])

if __name__=='__main__':unittest.main()
