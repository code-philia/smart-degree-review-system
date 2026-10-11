from pathlib import Path
import pytest
from pdf_rules.numbering import caption_match,FIGURE_REFERENCE,TABLE_REFERENCE,normalize_label
from pdf_rules.model import PdfLine,PdfPage,PdfDocument
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules

@pytest.mark.parametrize('kind,text,number',[('figure','图 B-1 系统结构','B.1'),('figure','Fig. C-12 System structure','C.12'),('table','表 A-3 参数列表','A.3')])
def test_hyphenated_appendix_title(kind,text,number):
 m=caption_match(text,kind)
 assert m is not None
 assert normalize_label(m.group('number'))==number

@pytest.mark.parametrize('pattern,text,number',[(FIGURE_REFERENCE,'见图 B-1。','B.1'),(TABLE_REFERENCE,'Table C-12 is referenced.','C.12')])
def test_hyphenated_appendix_reference(pattern,text,number):
 m=pattern.search(text)
 assert m is not None
 assert normalize_label(m.group('number'))==number

@pytest.mark.parametrize('text',['图 B-1 和图 B-2。','图 B-1和B-2展示结果。','图 B-1A invalid','Fig. F2D invalid'])
def test_prose_and_identifier_are_not_titles(text):
 assert caption_match(text,'figure') is None

def test_figure_title_and_deleted_title_obligation():
 box=(100,180,490,430)
 obj=LayoutObject('figure',1,box,'',600,840,role='image_body')
 line=PdfLine(1,'Figure C-12 System architecture',(190,450,450,464),600,840)
 for lines,expected in [((line,),0),((),1)]:
  doc=PdfDocument(Path('absent-appendix.pdf'),(PdfPage(1,600,840,lines,images=(box,)),))
  prepared=prepare_caption_layout([obj],doc)
  result=detect_caption_rules(prepared,[13],doc)['13']['findings']
  assert len(result)==expected

