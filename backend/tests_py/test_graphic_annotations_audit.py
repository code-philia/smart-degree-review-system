from pathlib import Path
from unittest.mock import patch
from pdf_rules.model import PdfPage,PdfDocument,PdfLine
from pdf_rules.local_ocr import OcrText
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.graphic_annotations import recover_graphic_annotations

def body(y):return LayoutObject('figure',1,(80,y,500,y+100),'',600,840,'chart_body')
def doc(lines=()):return PdfDocument(Path(__file__),(PdfPage(1,600,840,tuple(lines)),))

def test_ocr_only_supplies_high_confidence_graphic_annotations():
 items=[OcrText('(a)',.99,(95,100,115,113)),OcrText('(b)',.99,(95,215,115,228)),
        OcrText('(c)',.45,(95,330,115,343)),OcrText('Figure 7.9 Bad OCR',.99,(80,100,300,113))]
 with patch('pdf_rules.graphic_annotations._read_region',return_value=items):
  recovered=recover_graphic_annotations(doc(),[body(100),body(215)])
 assert [l.text for l in recovered.lines]==['(a)','(b)']
 assert all(l.role=='graphic_annotation' for l in recovered.lines)

def test_existing_native_graphic_labels_do_not_call_ocr():
 def native_marker(tag,y):
  # Real native extraction supplies each printed character's rectangle.
  return PdfLine(1,f'({tag})',(95,y,115,y+13),600,840,text_regions=(
   (0,1,(95,y,101,y+13)),(1,2,(101,y,109,y+13)),(2,3,(109,y,115,y+13))))
 source=doc([native_marker('a',100),native_marker('b',215)])
 with patch('pdf_rules.graphic_annotations._read_region',side_effect=AssertionError('unnecessary OCR')):
  assert recover_graphic_annotations(source,[body(100),body(215)])==source

def test_single_missing_figure_is_not_given_ocr_title():
 with patch('pdf_rules.graphic_annotations._read_region',side_effect=AssertionError('single image')):
  assert recover_graphic_annotations(doc(),[body(100)])==doc()

def test_ocr_failure_preserves_native_evidence():
 source=doc()
 with patch('pdf_rules.graphic_annotations._read_region',side_effect=RuntimeError('model unavailable')):
  assert recover_graphic_annotations(source,[body(100),body(215)])==source


def test_consecutive_numbers_in_confirmed_badges_are_panel_labels():
 hits=[OcrText('1',.99,(85,103,93,114)),OcrText('2',.99,(85,218,93,229))]
 with patch('pdf_rules.graphic_annotations._read_region',return_value=hits),patch('pdf_rules.graphic_annotations._dark_badge',return_value=True):
  recovered=recover_graphic_annotations(doc(),[body(100),body(215)])
 assert [l.text for l in recovered.lines]==['(a)','(b)']

def test_plain_axis_tick_numbers_are_never_converted_to_panel_labels():
 hits=[OcrText('1',.99,(85,103,93,114)),OcrText('2',.99,(85,218,93,229))]
 with patch('pdf_rules.graphic_annotations._read_region',return_value=hits),patch('pdf_rules.graphic_annotations._dark_badge',return_value=False):
  assert recover_graphic_annotations(doc(),[body(100),body(215)])==doc()


def test_physical_badges_retain_full_box_darkness_evidence():
 from dataclasses import replace
 source=replace(doc(),pages=(replace(doc().pages[0],images=((85,103,97,115),(85,218,97,230))),))
 hits=[OcrText('1',.87,(85,103,97,115)),OcrText('2',.99,(85,218,97,230))]
 def dark(document,number,box,*,padding=2):return padding==0
 with patch('pdf_rules.graphic_annotations._read_region',return_value=[]),patch('pdf_rules.graphic_annotations._read_number_badges',return_value=hits),patch('pdf_rules.graphic_annotations._dark_badge',side_effect=dark):
  recovered=recover_graphic_annotations(source,[body(100),body(215)])
 assert [l.text for l in recovered.lines]==['(a)','(b)']

def test_number_badge_ocr_failure_preserves_region_annotations():
 hits=[OcrText('(a)',.99,(95,100,115,113)),OcrText('(b)',.99,(95,215,115,228))]
 with patch('pdf_rules.graphic_annotations._read_region',return_value=hits),patch('pdf_rules.graphic_annotations._read_number_badges',side_effect=RuntimeError('unavailable')):
  assert [l.text for l in recover_graphic_annotations(doc(),[body(100),body(215)]).lines]==['(a)','(b)']


def test_numbered_diagram_panels_need_not_have_sparse_native_text():
 source=doc([PdfLine(1,'Diagram label '+str(i),(110,y+i*15,250,y+12+i*15),600,840) for y in (100,215) for i in range(4)])
 hits=[OcrText('1',.99,(85,103,93,114)),OcrText('2',.99,(85,218,93,229))]
 with patch('pdf_rules.graphic_annotations._read_region',side_effect=AssertionError('do not OCR dense native diagram')),patch('pdf_rules.graphic_annotations._read_number_badges',return_value=hits),patch('pdf_rules.graphic_annotations._dark_badge',return_value=True):
  recovered=recover_graphic_annotations(source,[body(100),body(215)])
 assert [l.text for l in recovered.lines if l.role=='graphic_annotation']==['(a)','(b)']


def test_native_markers_without_character_bounds_keep_the_existing_region_recovery():
 source=doc([PdfLine(1,'(a)',(95,100,115,113),600,840),PdfLine(1,'(b)',(95,215,115,228),600,840)])
 with patch('pdf_rules.graphic_annotations._read_region',return_value=[]) as reader:
  assert recover_graphic_annotations(source,[body(100),body(215)])==source
 assert reader.call_count==1
