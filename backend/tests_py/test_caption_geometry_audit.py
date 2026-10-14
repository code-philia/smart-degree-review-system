from pathlib import Path
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules

def test_one_oversized_math_glyph_does_not_move_caption_into_plot():
 regions=tuple((i,i+1,(120+i*6,325,126+i*6,339)) for i in range(28))+((28,29,(288,280,294,370)),)
 title=PdfLine(1,'Figure 2.8 Comparison at k',(120,280,320,370),600,840,text_regions=regions)
 doc=PdfDocument(Path('math-title.pdf'),(PdfPage(1,600,840,(title,)),))
 image=LayoutObject('figure',1,(80,100,520,310),'',600,840,'chart_body')
 assert detect_caption_rules(prepare_caption_layout([image],doc),[13],doc)['13']['findings']==[]

def test_a_caption_without_character_evidence_keeps_its_original_box():
 title=PdfLine(1,'Figure 2.8 Comparison',(120,280,320,370),600,840)
 doc=PdfDocument(Path('math-title.pdf'),(PdfPage(1,600,840,(title,)),))
 image=LayoutObject('figure',1,(80,100,520,310),'',600,840,'chart_body')
 assert len(detect_caption_rules(prepare_caption_layout([image],doc),[13],doc)['13']['findings'])==1



def test_centered_smaller_bold_nominal_table_title_may_end_with_period():
 from pdf_rules.caption_context import contextual_caption
 for text in ['表8.2 为计算矩阵乘积准备随机数所需的通信开销对比。','表8.2 为计算矩阵乘积准备随机数的性能基准（8线程）。']:
  title=PdfLine(1,text,(150,325,450,337),600,840,font_size=10.5,bold=True)
  prose=PdfLine(1,'本文分析多个通信协议在不同矩阵规模下的实验结果。',(80,420,520,434),600,840,font_size=12)
  page=PdfPage(1,600,840,(title,prose),tables=((120,120,480,310),))
  assert contextual_caption(title,page,'table') is not None
  doc=PdfDocument(Path('nominal-title.pdf'),(page,))
  table=LayoutObject('table',1,(120,120,480,310),'',600,840,'table_body')
  assert detect_caption_rules(prepare_caption_layout([table],doc),[14],doc)['14']['findings']==[]



def test_bold_body_font_statement_is_not_recovered_as_a_smaller_table_title():
 from pdf_rules.caption_context import contextual_caption
 text=PdfLine(1,'表8.2为本文方法的配置提供了依据。',(104,325,520,339),600,840,font_size=12,bold=True)
 prose=PdfLine(1,'本文分析多个通信协议在不同矩阵规模下的实验结果。',(80,420,520,434),600,840,font_size=12)
 page=PdfPage(1,600,840,(text,prose),tables=((120,120,480,310),))
 assert contextual_caption(text,page,'table') is None



def test_parser_table_geometry_supports_native_nominal_title_when_native_grid_missing():
 title=PdfLine(1,'表8.2 为矩阵乘法准备随机数的性能基准。',(150,325,450,337),600,840,font_size=10.5,bold=True)
 prose=PdfLine(1,'本文分析多个通信协议在不同矩阵规模下的实验结果。',(80,420,520,434),600,840,font_size=12)
 page=PdfPage(1,600,840,(title,prose))
 table=LayoutObject('table',1,(120,120,480,310),'',600,840,'table_body')
 doc=PdfDocument(Path('thin-grid.pdf'),(page,))
 layout=prepare_caption_layout([table],doc)
 assert detect_caption_rules(layout,[14],doc)['14']['findings']==[]
 from pdf_rules.index import build_index
 assert any(t.number=='8.2' for t in build_index(doc,layout).tables)
