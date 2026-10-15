from dataclasses import replace
from pathlib import Path
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.caption_rules import detect_caption_rules

def fixture(footer1='第 18 页',footer2='第 19 页',y=746,extra=()):
 def line(n,text,y,x=265,x2=325):return PdfLine(n,text,(x,y,x2,y+10),600,842,font_size=10)
 a=LayoutObject('figure',1,(110,97,470,616),'',600,842)
 b=LayoutObject('figure',2,(125,97,485,626),'',600,842)
 title=LayoutObject('figure_caption',2,(140,643,460,657),'图6.14 涡流演化',600,842)
 p1=PdfPage(1,600,842,(line(1,'(a)',338),line(1,'(b)',605),line(1,footer1,y),*extra))
 p2=PdfPage(2,600,842,(line(2,'(c)',348),line(2,'(d)',612),line(2,footer2,y)))
 return [a,b,title],PdfDocument(Path('missing.pdf'),(p1,p2))

def findings(**kwargs):
 objects,doc=fixture(**kwargs)
 return detect_caption_rules(objects,[13],doc)['13']['findings']

def test_repeated_bottom_page_numbers_do_not_break_panels():
 assert findings()==[]

def test_page_reference_inside_real_prose_still_blocks():
 assert [f['page'] for f in findings(footer1='参见第 18 页的实验结果。')]==[1]

def test_same_page_words_in_body_position_still_block():
 assert [f['page'] for f in findings(y=660)]==[1]

def test_unconfirmed_bottom_page_reference_still_blocks():
 assert [f['page'] for f in findings(footer2='另一段说明')]==[1]

def test_same_format_nonconsecutive_page_words_still_block():
 assert [f['page'] for f in findings(footer2='第 28 页')]==[1]

def test_real_intervening_body_survives_valid_footer():
 body=PdfLine(1,'下面讨论另一种独立实验条件。',(80,680,520,694),600,842,font_size=12)
 assert [f['page'] for f in findings(extra=(body,))]==[1]

def test_deleted_main_caption_keeps_both_halves_obligatory():
 objects,doc=fixture()
 assert [f['page'] for f in detect_caption_rules(objects[:2],[13],doc)['13']['findings']]==[1,2]
