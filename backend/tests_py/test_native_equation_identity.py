from pathlib import Path
from dataclasses import replace
import pymupdf
import pytest
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.object_identity import refine_targets


def fixture(tmp_path,extra=False):
    path=tmp_path/'unseen-numbered-equation.pdf'
    pdf=pymupdf.open();p=pdf.new_page(width=600,height=840)
    for y,text in [(150,'x = a + b'),(175,'y = c / d'),(200,'z = x * y')]:p.insert_text((180,y),text,fontsize=12)
    p.insert_text((500,175),'(8.7)',fontsize=12)
    if extra:p.draw_rect(pymupdf.Rect(260,155,275,166),color=(1,0,0),fill=(1,0,0))
    pdf.save(path);pdf.close()
    pdf=pymupdf.open(path);p=pdf[0];lines=[]
    for block in p.get_text('rawdict')['blocks']:
        for row in block.get('lines',[]):
            chars=[c for s in row['spans'] for c in s['chars']];text=''.join(c['c'] for c in chars)
            lines.append(PdfLine(1,text,tuple(row['bbox']),600,840,font_size=12,text_regions=tuple((i,i+1,tuple(c['bbox'])) for i,c in enumerate(chars))))
    pdf.close()
    body=LayoutObject('figure',1,(175,134,330,205),'',600,840,'image_body')
    doc=PdfDocument(path,(PdfPage(1,600,840,tuple(lines)),))
    return doc,body


def test_native_numbered_display_formula_has_no_figure_title_obligation(tmp_path):
    doc,body=fixture(tmp_path)
    assert body not in refine_targets([body],doc)


def test_graphic_ink_in_a_math_region_preserves_the_figure(tmp_path):
    doc,body=fixture(tmp_path,extra=True)
    assert body in refine_targets([body],doc)


def test_an_actual_figure_caption_preserves_math_figure_identity(tmp_path):
    doc,body=fixture(tmp_path)
    title=LayoutObject('figure_caption',1,(180,213,320,226),'Figure8.6 Mathematical diagram',600,840)
    assert body in refine_targets([body,title],doc)


def test_equation_without_external_number_is_not_inferred_from_symbols(tmp_path):
    doc,body=fixture(tmp_path);page=doc.pages[0]
    doc=replace(doc,pages=(replace(page,lines=tuple(l for l in page.lines if not l.text.startswith('('))),))
    assert body in refine_targets([body],doc)


def test_missing_original_preserves_unverified_parser_observation(tmp_path):
    doc,body=fixture(tmp_path);doc=replace(doc,path=Path('missing-native-equation.pdf'))
    assert body in refine_targets([body],doc)


def test_prose_with_a_number_is_not_a_display_equation(tmp_path):
    doc,body=fixture(tmp_path);page=doc.pages[0]
    doc=replace(doc,pages=(replace(page,lines=tuple(replace(l,text='Experiments yield x = a + b.') if not l.text.startswith('(') else l for l in page.lines)),))
    assert body in refine_targets([body],doc)

@pytest.mark.parametrize('extra',[None,'diagonal','axis'])
def test_numbered_system_can_own_proved_fraction_rules_but_keeps_diagram_strokes(tmp_path,extra):
 from pdf_rules.pdf_extract import extract_pdf
 path=tmp_path/'fraction-system.pdf'
 with pymupdf.open() as pdf:
  p=pdf.new_page(width=600,height=840)
  for y,text in [(150,'x = a + b'),(175,'y = c / d'),(200,'z = x * y')]:p.insert_text((180,y),text,fontsize=12)
  p.insert_text((290,150),'n',fontsize=10)
  p.insert_text((290,170),'2',fontsize=10)
  p.draw_line((285,157),(305,157),width=.6,color=(0,0,0))
  p.insert_text((500,175),'(8.7)',fontsize=12)
  if extra=='diagonal':p.draw_line((275,183),(325,160),width=.6,color=(0,0,0))
  if extra=='axis':p.draw_line((177,205),(335,205),width=.6,color=(0,0,0))
  pdf.save(path)
 doc=extract_pdf(path)
 body=LayoutObject('figure',1,(175,134,340,208),'',600,840,'image_body')
 assert (body in refine_targets([body],doc))==bool(extra)
