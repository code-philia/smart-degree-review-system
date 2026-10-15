from pathlib import Path
from pdf_rules.caption_rules import detect_caption_rules
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.model import PdfDocument, PdfLine, PdfPage

def obj(kind,box,text='',role='image_body'): return LayoutObject(kind,1,box,text,600,840,role)
def check(objects, lines=()):
 doc=PdfDocument(Path('code-fragment.pdf'),(PdfPage(1,600,840,tuple(PdfLine(1,t,(85,310+i*16,450,322+i*16),600,840) for i,t in enumerate(lines))),))
 return detect_caption_rules(prepare_caption_layout(objects,doc),[13,14],doc)

def test_unnumbered_cpp_fragment_is_not_a_missing_figure():
 lines=['auto value = client.acquire(key);','if (!value) { return; }','auto [snap, deltas] = client.snapshot(key);','for (auto &d : deltas) client.apply(d);','client.release(*value);']
 assert check([obj('figure',(70,300,520,430))],lines)['13']['findings']==[]

def test_neighboring_diagram_title_does_not_turn_code_into_a_figure():
 lines=['auto value = client.acquire(key);','if (!value) { return; }','client.apply(*value);','client.release(*value);']
 objects=[obj('figure',(70,100,520,250)),obj('figure_caption',(140,260,480,280),'Figure 2.1 Data model','image_caption'),obj('figure',(70,300,520,430))]
 assert check(objects,lines)['13']['findings']==[]

def test_braced_type_definitions_are_code_not_uml_diagrams():
 text='Class Record {name: String count: Integer} Enum Role {LOCAL REMOTE} Class Config {enabled: boolean ratio: Double}'
 assert check([obj('table',(70,300,520,430),text,'table_body')])['13']['findings']==[]
 assert check([obj('table',(70,300,520,430),text,'table_body')])['14']['findings']==[]

def test_real_uml_diagram_with_typed_properties_still_requires_figure_title():
 text='Class Record {name: String count: Integer} Class Config {enabled: boolean ratio: Double} Record -> Config'
 assert len(check([obj('table',(70,300,520,430),text,'table_body')])['13']['findings'])==1

def test_comparison_table_containing_a_code_cell_still_requires_table_title():
 text='Method Time Description Class Record {name: String count: Integer} baseline 10 optimized 4'
 assert len(check([obj('table',(70,300,520,430),text,'table_body')])['14']['findings'])==1

def test_plot_with_one_code_annotation_still_requires_title():
 assert len(check([obj('figure',(70,300,520,430))],['Latency','Throughput','client.run(x);'])['13']['findings'])==1

def test_deliberately_captioned_code_screenshot_stays_a_figure():
 objects=[obj('figure',(70,300,520,430)),obj('figure_caption',(130,440,480,460),'Figure 2.2 API screenshot','image_caption')]
 from pdf_rules.object_identity import code_listing
 page=PdfPage(1,600,840,tuple(PdfLine(1,t,(85,310+i*16,450,322+i*16),600,840) for i,t in enumerate(['auto value = client.acquire(key);','client.apply(*value);','client.release(*value);'])))
 assert not code_listing(objects[0],page,objects,[objects[1]])


def test_native_raster_copy_inherits_full_region_code_identity():
 text='Class Record {name: String count: Integer} Class Config {enabled: boolean ratio: Double}'
 objects=[obj('table',(70,300,520,430),text,'table_body'),obj('figure',(70,300,520,430),'','native_figure')]
 assert check(objects)['13']['findings']==[]



def test_continued_algorithm_with_separate_number_cells_is_not_a_table():
 from pdf_rules.object_identity import algorithm_frame
 ls=[PdfLine(1,'续算法 7.1',(70,280,220,294),600,840)]
 for i,text in enumerate(['end for','v ← E(q)','for each table entry t in T do','score ← similarity(q,t)','end for','return score']):
  y=310+i*18
  ls.extend([PdfLine(1,str(20+i),(74,y,88,y+12),600,840),PdfLine(1,text,(110,y,490,y+12),600,840)])
 page=PdfPage(1,600,840,tuple(ls))
 target=obj('table',(70,300,520,425),role='table_body')
 assert algorithm_frame(target,page)
 doc=PdfDocument(Path('continued-algorithm.pdf'),(page,))
 assert detect_caption_rules(prepare_caption_layout([target],doc),[14],doc)['14']['findings']==[]



def test_formal_protocol_and_functionality_frames_are_programs_not_tables():
 from pdf_rules.object_identity import code_listing
 for heading in ['Protocol 8: 验证协议 Verify','Functionality 8: Ideal functionality FCommit','Procedure 8: 子例程 Verify']:
  ls=[PdfLine(1,heading,(90,90,360,104),600,840)]
  body=['Input: receive X = input value.','Set state = X and compute Y = state + 1.','Check the condition and send Output: Y to every party.']
  ls += [PdfLine(1,t,(90,120+i*25,500,134+i*25),600,840) for i,t in enumerate(body)]
  page=PdfPage(1,600,840,tuple(ls),graphics=((80,100,520,240),))
  target=obj('table',(80,100,520,240),'','table_body')
  assert code_listing(target,page,[target],[])



def test_protocol_column_header_does_not_turn_comparison_data_into_program():
 from pdf_rules.object_identity import code_listing
 ls=[PdfLine(1,t,(90,110+i*20,490,124+i*20),600,840) for i,t in enumerate(['Protocol 8: Performance comparison','Method Input Output','Receive 128 256','Check 64 32','Send 16 8'])]
 page=PdfPage(1,600,840,tuple(ls),graphics=((80,100,520,240),))
 target=obj('table',(80,100,520,240),'','table_body')
 assert not code_listing(target,page,[target],[])



def test_deliberately_captioned_formal_protocol_stays_a_table():
 from pdf_rules.object_identity import code_listing
 lines=[PdfLine(1,t,(90,110+i*20,490,124+i*20),600,840) for i,t in enumerate(['Protocol 8: Verify','Input: receive X = value','Set state = X; compute Y = X+1','Check condition; send Output: Y'])]
 page=PdfPage(1,600,840,tuple(lines),graphics=((80,100,520,240),))
 target=obj('table',(80,100,520,240),'','table_body')
 title=obj('table_caption',(180,250,420,265),'Table 8.2 Protocol definition','table_caption')
 assert not code_listing(target,page,[target,title],[title])



def continuation_example(name='FCommit',first_bottom=760,title=False):
 from dataclasses import replace
 first=obj('table',(70,100,510,first_bottom),'','table_body')
 tail=replace(obj('table',(85,100,525,150),'','table_body'),page_number=2)
 ls=[PdfLine(1,'Functionality 8: FCommit',(80,90,320,104),600,840)]
 ls += [PdfLine(1,t,(90,120+i*25,490,134+i*25),600,840) for i,t in enumerate(['Input: receive X = input value.','Set state = X and compute Y = state+1.','Check condition and send Output: Y.'])]
 page1=PdfPage(1,600,840,tuple(ls),graphics=(first.bbox,))
 page2=PdfPage(2,600,840,(PdfLine(2,f'{name} distributes a final zero sharing to every output participant.',(100,115,510,128),600,840),),graphics=(tail.bbox,))
 objects=[first,tail]
 if title:objects.append(replace(obj('table_caption',(190,162,420,176),'Table 9.2 Independent comparison','table_caption'),page_number=2))
 return objects,PdfDocument(Path('definition-continuation.pdf'),(page1,page2))



def test_formal_definition_tail_retains_previous_page_identity():
 objects,doc=continuation_example()
 result=detect_caption_rules(prepare_caption_layout(objects,doc),[14],doc)
 assert result['14']['findings']==[]



def test_unrelated_name_on_next_page_does_not_inherit_formal_frame():
 objects,doc=continuation_example('FCompare')
 result=detect_caption_rules(prepare_caption_layout(objects,doc),[14],doc)
 assert len(result['14']['findings'])==1



def test_formal_frame_cannot_jump_from_middle_of_previous_page():
 objects,doc=continuation_example(first_bottom=400)
 result=detect_caption_rules(prepare_caption_layout(objects,doc),[14],doc)
 assert len(result['14']['findings'])==1



def test_titled_tail_keeps_independent_table_identity():
 objects,doc=continuation_example(title=True)
 layout=prepare_caption_layout(objects,doc)
 assert any(o.kind=='table' and o.page_number==2 for o in layout)



def test_code_parsed_definition_can_own_its_next_page_tail():
 from dataclasses import replace
 objects,doc=continuation_example()
 objects[0]=replace(objects[0],kind='text',role='code_body')
 result=detect_caption_rules(prepare_caption_layout(objects,doc),[14],doc)
 assert result['14']['findings']==[]
