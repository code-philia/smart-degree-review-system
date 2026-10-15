from pathlib import Path
from dataclasses import replace
from pdf_rules.model import PdfLine,PdfPage,PdfDocument
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules

def obj(box,kind='figure',text='',role='chart_body'):
 return LayoutObject(kind,1,box,text,600,840,role)
def line(text,box):return PdfLine(1,text,box,600,840)
def run(objects,lines=()):
 doc=PdfDocument(Path('independent-panels.pdf'),(PdfPage(1,600,840,tuple(lines)),))
 return detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)['13']['findings']

def test_multi_line_subtitles_extend_a_labelled_body_to_its_total_caption():
 bodies=[obj((60,100,260,215)),obj((300,100,500,215))]
 title=obj((170,305,390,330),'figure_caption','Figure 4.1 Results')
 lines=[line('(a) Left condition',(100,240,230,255)),line('(b) Right condition',(320,240,480,255))]
 assert run(bodies+[title],lines)==[]

def test_title_centred_across_two_equal_panels_can_be_short():
 bodies=[obj((70,100,265,240)),obj((290,100,485,240))]
 title=obj((180,254,375,274),'figure_caption','Figure 4.2 Comparison')
 assert run(bodies+[title])==[]

def test_short_title_over_only_one_panel_does_not_hide_untitled_neighbor():
 bodies=[obj((70,100,265,240)),obj((290,100,485,240))]
 title=obj((90,254,245,274),'figure_caption','Figure 4.2 One condition')
 assert len(run(bodies+[title]))==1

def test_restarted_letters_and_independent_title_keep_two_obligations():
 bodies=[obj((70,100,265,240)),obj((290,100,485,240))]
 title=obj((180,270,375,290),'figure_caption','Figure 4.2 One condition')
 lines=[line('(a) First',(100,242,230,257)),line('(a) Second',(320,242,460,257))]
 assert len(run(bodies+[title],lines))==1


def test_explicit_top_bottom_translations_are_two_rows_of_one_total_figure():
 bodies=[obj((100,100,500,330)),obj((100,352,500,582))]
 title=obj((110,602,490,632),'figure_caption','Figure 3.2 Chinese (Top) / English (Bottom) accuracy')
 assert run(bodies+[title])==[]

def test_top_bottom_caption_does_not_cross_another_figure_title():
 bodies=[obj((100,100,500,300)),obj((100,352,500,582))]
 title=obj((110,602,490,632),'figure_caption','Figure 3.2 Chinese (Top) / English (Bottom) accuracy')
 own=obj((180,313,420,330),'figure_caption','Figure 3.1 Earlier result')
 assert run(bodies+[title,own])==[]

def test_outside_panel_label_is_used_only_with_nearby_total_caption():
 bodies=[obj((110,100,270,220)),obj((330,100,490,220))]
 title=obj((230,286,390,301),'figure_caption','Figure 4.3 Rendering modes')
 lines=[line('(a) First condition',(115,264,270,277)),line('(b) Second condition',(335,264,490,277))]
 assert run(bodies+[title],lines)==[]

def test_repeated_numeric_metric_fields_define_regular_experiment_grid():
 bodies=[obj((x,y,x+190,y+130),'figure',role='image_body') for y in [100,285] for x in [80,295]]
 title=obj((160,469,440,484),'figure_caption','Figure 4.4 Rendering comparison')
 lines=[]
 for o in bodies:
  x,y,_,b=o.bbox
  lines += [line('PSNR=25.1 GS=100200',(x+20,b+14,x+175,b+27)),line('Train=20m40s',(x+40,b+29,x+155,b+42))]
 assert run(bodies+[title],lines)==[]
