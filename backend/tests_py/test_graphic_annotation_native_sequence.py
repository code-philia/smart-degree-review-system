from pathlib import Path
from dataclasses import replace
import pytest
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules import graphic_annotations as g

@pytest.mark.parametrize('variant,expected',[('complete',0),('complete_inside',0),('missing_glyphs',2),('gap',2),('repeated_namespace',2)])
def test_proved_native_panel_sequence_avoids_ocr_aliases_but_missing_evidence_still_reads(tmp_path,monkeypatch,variant,expected):
 path=tmp_path/'original.pdf';path.write_bytes(b'original-exists')
 def label(tag,y):
  text=f'({tag}) Native panel description'
  return PdfLine(1,text,(130,y,330,y+12),600,840,source='native',text_regions=((0,1,(130,y,134,y+12)),(1,2,(134,y,139,y+12)),(2,3,(139,y,143,y+12))) if variant!='missing_glyphs' else ())
 shift=-20 if variant=='complete_inside' else 0
 lines=[label('a',210+shift),label('c' if variant=='gap' else 'b',410+shift)]
 if variant=='repeated_namespace':lines.append(label('a',380))
 page=PdfPage(1,600,840,tuple(lines));doc=PdfDocument(path,(page,))
 targets=[LayoutObject('figure',1,(100,100,400,200),'',600,840,'chart_body'),LayoutObject('figure',1,(100,300,400,400),'',600,840,'chart_body')]
 calls=[]
 monkeypatch.setattr(g,'_read_number_badges',lambda *a:calls.append('badges') or [])
 monkeypatch.setattr(g,'_read_region',lambda *a:calls.append('region') or [])
 assert g.recover_graphic_annotations(doc,targets)==doc
 assert len(calls)==expected


@pytest.mark.parametrize('right_x',[340,235])
@pytest.mark.parametrize('native_inside',[False,True])
@pytest.mark.parametrize('contextual_title',[False,True])
def test_native_labels_on_one_group_do_not_skip_another_raster_group(tmp_path,monkeypatch,right_x,native_inside,contextual_title):
 path=tmp_path/'original.pdf';path.write_bytes(b'original-exists')
 def label(tag,y):
  return PdfLine(1,f'({tag}) Native panel',(95,y,220,y+12),600,840,source='native',
   text_regions=((0,1,(95,y,99,y+12)),(1,2,(99,y,104,y+12)),(2,3,(104,y,108,y+12))))
 shift=-16 if native_inside else 0
 page=PdfPage(1,600,840,(label('a',184+shift),label('b',284+shift),
  PdfLine(1,'Figure 1 Native panels',(70,310,220,322),600,840,source='native'),
  PdfLine(1,'图2可见/在用卫星数量对比' if contextual_title else 'Figure 2 Raster panels',
   (right_x,310,right_x+150,322),600,840,source='native',bold=contextual_title,font_size=9 if contextual_title else None)))
 doc=PdfDocument(path,(page,))
 targets=[LayoutObject('figure',1,(x,y,x+150,y+80),'',600,840,'chart_body')
          for x in (70,right_x) for y in (100,200)]
 doc=replace(doc,pages=(replace(page,images=tuple(o.bbox for o in targets)),))
 calls=[]
 monkeypatch.setattr(g,'_read_number_badges',lambda *a:calls.append('badges') or [])
 monkeypatch.setattr(g,'_read_region',lambda *a:calls.append('region') or [])
 g.recover_graphic_annotations(doc,targets)
 assert calls==['badges','region']


@pytest.mark.parametrize('raster_number',[1,2])
def test_prepared_raster_titles_keep_independent_physical_panel_namespaces(tmp_path,monkeypatch,raster_number):
 path=tmp_path/'original.pdf';path.write_bytes(b'original-exists')
 def marker(tag,y):
  return PdfLine(1,f'({tag})',(95,y,108,y+12),600,840,source='native',
   text_regions=((0,1,(95,y,99,y+12)),(1,2,(99,y,104,y+12)),(2,3,(104,y,108,y+12))))
 boxes=tuple((x,y,x+150,y+80) for x in (70,235) for y in (100,200))
 page=PdfPage(1,600,840,(marker('a',184),marker('b',284),
  PdfLine(1,'Figure 1 Native panels',(70,310,220,322),600,840)),images=boxes)
 doc=PdfDocument(path,(page,))
 targets=[LayoutObject('figure',1,b,'',600,840,'chart_body') for b in boxes]
 # The raw parser already read this printed raster title; it has no native line.
 targets.append(LayoutObject('figure_caption',1,(235,310,385,322),
  f'Figure {raster_number} Raster panels',600,840))
 calls=[]
 monkeypatch.setattr(g,'_read_number_badges',lambda *a:calls.append('badges') or [])
 monkeypatch.setattr(g,'_read_region',lambda *a:calls.append('region') or [])
 g.recover_graphic_annotations(doc,targets)
 assert calls==['badges','region']
