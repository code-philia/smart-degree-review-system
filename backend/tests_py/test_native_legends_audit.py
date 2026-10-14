from pathlib import Path
import io
import pymupdf
from PIL import Image,ImageDraw
from pdf_rules.pdf_extract import extract_pdf
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules

def test_native_series_legend_keys_belong_to_the_neighboring_chart():
 lines=tuple(PdfLine(1,name,(105,150+i*20,145,163+i*20),600,840) for i,name in enumerate(['Baseline','Method A','Method B','Ours']))
 boxes=tuple((85,152+i*20,95,162+i*20) for i in range(4))
 page=PdfPage(1,600,840,lines,images=boxes,graphics=((80,140,155,235),),legend_marks=boxes)
 doc=PdfDocument(Path('legend-layout.pdf'),(page,))
 objects=[LayoutObject('figure',1,(200,100,500,300),'',600,840,'chart_body'),LayoutObject('figure_caption',1,(200,320,450,335),'Figure 1.1 Measured results',600,840)]
 assert detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)['13']['findings']==[]

def test_raster_hatched_series_keys_are_legend_parts_and_not_missing_figures(tmp_path):
 path=tmp_path/'hatched-keys.pdf'
 with pymupdf.open() as pdf:
  p=pdf.new_page(width=600,height=840)
  p.draw_rect((200,100,500,300));p.draw_rect((80,130,160,245))
  for i,(name,color) in enumerate([('Baseline','yellow'),('Method A','skyblue'),('Ours','green')]):
   y=155+i*25
   im=Image.new('RGB',(20,20),'white');d=ImageDraw.Draw(im)
   for x in range(0,20,4):d.line((x,0,x,19),fill=color,width=2)
   stream=io.BytesIO();im.save(stream,format='PNG')
   p.insert_image((85,y-8,95,y+2),stream=stream.getvalue())
   p.insert_text((103,y),name,fontsize=10)
  p.insert_text((205,330),'Figure 1.1 Measured results',fontsize=10)
  p.insert_text((70,400),'Ordinary readable research body paragraph.',fontsize=12)
  pdf.save(path)
 doc=extract_pdf(path)
 objects=[LayoutObject('figure',1,(200,100,500,300),'',600,840,'chart_body')]
 assert detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)['13']['findings']==[]

def test_two_column_numeric_table_beside_chart_keeps_its_missing_table_title():
 lines=[]
 for i,name in enumerate(['A','B','C']):
  lines.extend([PdfLine(1,name,(100,150+i*20,120,163+i*20),600,840),PdfLine(1,str(i+10),(145,150+i*20,160,163+i*20),600,840)])
 page=PdfPage(1,600,840,tuple(lines),graphics=((80,140,180,225),),legend_marks=((85,152,95,162),(85,172,95,182),(85,192,95,202)))
 doc=PdfDocument(Path('real-table.pdf'),(page,))
 objects=[LayoutObject('figure',1,(200,100,500,300),'',600,840,'chart_body'),LayoutObject('table',1,(80,140,180,225),'',600,840,'table_body'),LayoutObject('figure_caption',1,(200,320,450,335),'Figure 1.1 Measured results',600,840)]
 assert len(detect_caption_rules(prepare_caption_layout(objects,doc),[14],doc)['14']['findings'])==1

def test_shared_wide_chart_caption_does_not_give_legend_an_independent_title():
 lines=tuple(PdfLine(1,name,(105,150+i*20,145,163+i*20),600,840) for i,name in enumerate(['Baseline','Method A','Method B','Ours']))
 boxes=tuple((85,152+i*20,95,162+i*20) for i in range(4))
 page=PdfPage(1,600,840,lines,images=boxes,graphics=((80,140,155,235),),legend_marks=boxes)
 doc=PdfDocument(Path('wide-title.pdf'),(page,))
 objects=[LayoutObject('figure',1,(200,100,500,250),'',600,840,'chart_body'),LayoutObject('figure_caption',1,(90,270,500,285),'Figure 1.1 Measured results',600,840)]
 assert detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)['13']['findings']==[]

def test_independently_captioned_legend_illustration_remains_a_separate_figure():
 from pdf_rules.logical_objects import attach_plot_legends
 lines=tuple(PdfLine(1,name,(105,150+i*20,145,163+i*20),600,840) for i,name in enumerate(['Baseline','Method A','Method B','Ours']))
 boxes=tuple((85,152+i*20,95,162+i*20) for i in range(4))
 page=PdfPage(1,600,840,lines,legend_marks=boxes)
 doc=PdfDocument(Path('two-titled-figures.pdf'),(page,))
 objects=[LayoutObject('figure',1,(80,140,155,235),'',600,840,'image_body'),LayoutObject('figure',1,(200,100,500,300),'',600,840,'chart_body'),LayoutObject('figure_caption',1,(65,250,175,265),'Figure 1.1 Color encoding',600,840),LayoutObject('figure_caption',1,(200,320,500,335),'Figure 1.2 Measured results',600,840)]
 assert len([o for o in attach_plot_legends(objects,doc) if o.kind=='figure'])==2


def test_top_legend_with_two_rows_belongs_to_verified_shared_axis_panels(tmp_path):
 from pdf_rules.logical_objects import attach_top_series_legends
 path=tmp_path/'two-row-legend.pdf'
 with pymupdf.open() as pdf:
  p=pdf.new_page(width=600,height=840)
  for i,(text,color) in enumerate([('Method A',(1,.4,.1)),('Method B',(.1,.5,1)),('Method C',(.1,.7,.1)),('Method D',(.7,.1,.7))]):
   x=150+(i%2)*160;y=170+(i//2)*17
   p.draw_rect((x,y,x+12,y+10),color=color,fill=color)
   p.insert_text((x+18,y+9),text,fontsize=9)
  pdf.save(path)
 parent=LayoutObject('figure',1,(90,212,510,575),'',600,840,'shared_axis_panels')
 legend=LayoutObject('figure',1,(145,166,440,202),'',600,840,'chart_body')
 title=LayoutObject('figure_caption',1,(130,586,480,600),'Figure 2.1 Comparison',600,840)
 doc=PdfDocument(path,(PdfPage(1,600,840,()),))
 assert len(attach_top_series_legends([parent,legend],[title],doc))==1
