from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import json
import pytest
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.figure_identity_repair import repair_figure_identity
from pdf_rules.caption_rules import detect_caption_rules
CASES=json.loads((Path(__file__).parent/'fixtures/figure_caption_repair_physical_cases.json').read_text(encoding='utf-8'))
def load(case):
 path=Path(case['path'])
 if not path.is_file():pytest.skip('Original immutable PDF needed for pixel evidence')
 assert sha256(path.read_bytes()).hexdigest()==case['sha']
 pages=[]
 for p in case['pages']:
  kw=dict(p);kw['lines']=tuple(PdfLine(**l) for l in p['lines']);pages.append(PdfPage(**kw))
 return [LayoutObject(**o) for o in case['objects']],PdfDocument(path,tuple(pages))
@pytest.mark.parametrize('case',CASES,ids=lambda c:c['case'])
def test_original_declared_figures_text_and_carriers_have_no_false_missing_title(case):
 objects,document=load(case)
 fixed=repair_figure_identity(objects,document)
 assert detect_caption_rules(fixed,[13],document)['13']['findings']==[]
 assert repair_figure_identity(fixed,document)==fixed
@pytest.mark.parametrize('case',CASES,ids=lambda c:c['case'])
def test_deleting_real_total_title_still_reports_a_figure(case):
 objects,document=load(case)
 objects=[o for o in objects if o.kind!='figure_caption']
 pages=tuple(replace(p,lines=tuple(l for l in p.lines if not l.text.lstrip().startswith(('图','Figure','Fig.')))) for p in document.pages)
 document=replace(document,pages=pages)
 fixed=repair_figure_identity(objects,document)
 assert detect_caption_rules(fixed,[13],document)['13']['findings']

def test_unproven_panel_crops_must_not_use_an_internal_caption():
 figure=LayoutObject('figure',1,(70,100,530,350),'',600,840,role='chart_body',panel_boxes=((70,100,280,200),(320,100,530,200)))
 cap=LayoutObject('figure_caption',1,(100,280,500,300),'Figure 2.1 Inner object',600,840)
 page=PdfPage(1,600,840,(),graphics=((70,100,530,350),))
 doc=PdfDocument(Path('layout-only.pdf'),(page,))
 fixed=repair_figure_identity([figure,cap],doc)
 assert detect_caption_rules(fixed,[13],doc)['13']['findings']

def test_explicit_unresolved_figure_reference_keeps_a_prompt_screenshot_as_figure():
 texts=['Prompt for prediction','You are provided with the following data.','Your task is to generate a response.','Please return the requested output format.']
 lines=[PdfLine(1,'提示模板如图 2.9 所示',(70,80,530,95),600,840)]+[PdfLine(1,t,(90,120+i*15,450,132+i*15),600,840) for i,t in enumerate(texts)]
 page=PdfPage(1,600,840,tuple(lines));doc=PdfDocument(Path('layout-only.pdf'),(page,));o=LayoutObject('figure',1,(80,110,520,195),'',600,840)
 assert detect_caption_rules(repair_figure_identity([o],doc),[13],doc)['13']['findings']

@pytest.mark.parametrize('shape,expected',[('arrow',True),('line_plot',False),('axis_plot',False),('rectangle',False)])
def test_only_a_solid_directional_arrow_gets_pixel_proof(tmp_path,shape,expected):
 import pymupdf
 from pdf_rules.figure_identity_repair import _directional_arrow
 path=tmp_path/'shape.pdf'
 with pymupdf.open() as pdf:
  p=pdf.new_page(width=600,height=840)
  if shape=='arrow':p.draw_polyline([(80,218),(490,218),(490,210),(520,222),(490,234),(490,226),(80,226),(80,218)],closePath=True,color=(0,0,0),fill=(0,0,0))
  elif shape=='line_plot':p.draw_polyline([(80,230),(190,219),(250,224),(380,211),(520,225)],color=(0,0,0),width=2)
  elif shape=='axis_plot':
   p.draw_polyline([(80,210),(80,233),(520,233)],color=(0,0,0),width=1)
   p.draw_polyline([(90,228),(240,214),(420,219),(510,211)],color=(0,0,0),width=2)
  else:p.draw_rect((80,218,520,226),color=(0,0,0),fill=(0,0,0))
  pdf.save(path)
 with pymupdf.open(path) as pdf:
  o=LayoutObject('figure',1,(80,210,521,235),'',600,840,role='native_figure')
  assert _directional_arrow(o,pdf)==expected
  if shape=='arrow':
   doc=PdfDocument(path,(PdfPage(1,600,840,(),images=(o.bbox,)),))
   assert detect_caption_rules(repair_figure_identity([o],doc),[13],doc)['13']['findings']

@pytest.mark.parametrize('graphic_stroke',[False,True])
def test_original_glyph_coverage_includes_short_heading_but_preserves_diagram_ink(tmp_path,graphic_stroke):
 import pymupdf
 from pdf_rules.pdf_extract import extract_pdf
 path=tmp_path/'body-carrier.pdf'
 with pymupdf.open() as pdf:
  p=pdf.new_page(width=600,height=840)
  p.insert_text((80,110),'Section heading',fontsize=12)
  for y in (140,160,180):p.insert_text((80,y),'The long original body paragraph continues outside the bitmap carrier and describes the experiment in full detail.',fontsize=9)
  if graphic_stroke:p.draw_line((100,118),(270,125),color=(0,0,0),width=2)
  pdf.save(path)
 doc=extract_pdf(path);o=LayoutObject('figure',1,(90,98,280,173),'',600,840,role='native_figure')
 fixed=repair_figure_identity([o],doc)
 assert bool(detect_caption_rules(fixed,[13],doc)['13']['findings'])==graphic_stroke
