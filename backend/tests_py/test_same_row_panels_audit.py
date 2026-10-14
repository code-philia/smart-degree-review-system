from pathlib import Path
from pdf_rules.model import PdfLine,PdfPage,PdfDocument
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.logical_objects import panel_label_lines
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules

def item(box,role='chart_body'):
 return LayoutObject('figure',1,box,'',600,840,role)
def line(text,box):return PdfLine(1,text,box,600,840)

def test_repeated_same_row_panel_labels_inside_one_chart_are_one_identity():
 parent=item((120,100,500,220))
 ls=(line('(a) TTFT',(220,225,300,240)),line('(a) TTFT',(360,225,440,240)))
 page=PdfPage(1,600,840,ls)
 assert len(panel_label_lines(page,[parent]))==1

def test_chinese_english_subpanel_titles_on_one_row_are_one_identity():
 parent=item((120,100,500,220))
 ls=(line('(c) 吞吐量',(220,225,315,240)),line('(c) Throughput',(350,225,480,240)))
 assert len(panel_label_lines(PdfPage(1,600,840,ls),[parent]))==1

def test_separate_neighboring_charts_keep_their_restarted_letters():
 parents=[item((80,100,270,220)),item((310,100,500,220))]
 ls=(line('(a) First',(120,225,210,240)),line('(a) Second',(350,225,450,240)))
 assert len(panel_label_lines(PdfPage(1,600,840,ls),parents))==2

def test_duplicate_translations_do_not_split_a_three_row_composite():
 bodies=[item((120,y,500,z)) for y,z in [(100,180),(235,325),(360,460)]]
 caption=LayoutObject('figure_caption',1,(160,500,460,520),'Figure 5.2 Composite results',600,840)
 ls=[]
 for tag,y in [('a',185),('b',330),('c',465)]:
  ls += [line(f'({tag}) Value',(220,y,300,y+15)),line(f'({tag}) Value',(360,y,440,y+15))]
 doc=PdfDocument(Path('independent-composite.pdf'),(PdfPage(1,600,840,tuple(ls)),))
 layout=prepare_caption_layout(bodies+[caption],doc)
 assert detect_caption_rules(layout,[13],doc)['13']['findings']==[]

def test_identical_translated_panel_acronym_on_two_lines_is_one_identity():
 parent=item((120,100,500,220))
 ls=(line('(a) TTFT',(270,224,315,235)),line('(a) TTFT',(271,238,316,249)))
 assert len(panel_label_lines(PdfPage(1,600,840,ls),[parent]))==1


def mixed_photo_plot_fixture(with_photo_label=True):
 # The two plots have an L-shaped envelope: its empty corner overlaps the
 # photo's label. Envelope containment must not steal the photo's identity.
 bodies=[item((150,430,230,535),'image_body'),
         item((290,430,490,535)),item((190,554,390,660))]
 caption=LayoutObject('figure_caption',1,(170,683,420,704),
                      'Figure 2.3 Device and experimental results',600,840)
 ls=[line('(b)',(380,542,402,557)),line('(c)',(280,666,302,679)),
     line('Time (s)',(365,516,420,530)),
     line('Time (s)',(265,641,320,656))]
 if with_photo_label:ls.append(line('(a)',(180,542,202,557)))
 doc=PdfDocument(Path('mixed-photo-plots.pdf'),(PdfPage(1,600,840,tuple(ls)),))
 return bodies+[caption],doc


def test_photo_and_l_shaped_plot_grid_share_their_declared_panel_caption():
 objects,doc=mixed_photo_plot_fixture()
 layout=prepare_caption_layout(objects,doc)
 assert detect_caption_rules(layout,[13],doc)['13']['findings']==[]


def test_unlabelled_neighbor_photo_is_not_absorbed_by_plot_envelope():
 objects,doc=mixed_photo_plot_fixture(with_photo_label=False)
 layout=prepare_caption_layout(objects,doc)
 findings=detect_caption_rules(layout,[13],doc)['13']['findings']
 assert len(findings)==1
 assert findings[0]['location']['bounding_rect']['x2'] < 250
