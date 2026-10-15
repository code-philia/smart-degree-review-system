"""Academic object ownership must survive parser fragmentation and input order."""
from pathlib import Path
from dataclasses import replace
import pymupdf
import pytest
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.model import PdfDocument, PdfPage, PdfLine


def object_(kind, box, text='', role=''):
    return LayoutObject(kind, 1, box, text, 600, 800, role)


def line(text, box):
    return PdfLine(1, text, box, 600, 800)


def evaluate(objects, document):
    layout=prepare_caption_layout(objects,document)
    return layout,detect_caption_rules(layout,[13,14],document)


def test_explicit_common_figure_title_owns_a_chart_and_statistical_table():
    objects=[object_('figure',(80,100,280,290),role='image_body'),
             object_('table',(320,100,520,290),role='table_body'),
             object_('figure_caption',(65,318,535,348),'Figure 4.2 Statistics: (a) Topics; (b) Numeric summary')]
    lines=[line('(a) Topics',(110,295,250,310)),line('(b) Numeric summary',(330,295,510,310))]
    doc=PdfDocument(Path('mixed-panels.pdf'),(PdfPage(1,600,800,tuple(lines)),))
    layout,result=evaluate(objects,doc)
    assert result['13']['findings']==[]
    assert result['14']['findings']==[]
    assert len([o for o in layout if o.kind in {'figure','table'}])==1


def test_independent_table_title_prevents_absorption_by_a_figure_title():
    objects=[object_('figure',(80,100,280,290),role='image_body'),
             object_('table',(320,100,520,290),role='table_body'),
             object_('figure_caption',(65,345,535,375),'Figure 4.2 Statistics: (a) Topics; (b) Numeric summary'),
             object_('table_caption',(335,70,510,90),'Table 4.1 Separate measurements')]
    lines=[line('(a) Topics',(110,295,250,310)),line('(b) Numeric summary',(330,295,510,310))]
    doc=PdfDocument(Path('mixed-panels.pdf'),(PdfPage(1,600,800,tuple(lines)),))
    layout,_=evaluate(objects,doc)
    assert len([o for o in layout if o.kind in {'figure','table'}])==2


@pytest.mark.parametrize('factor',[.7,1,1.25])
def test_regular_plot_grid_uses_relative_gutter_size(factor):
    def scaled(box):return tuple(v*factor for v in box)
    objects=[object_('figure',scaled((x,y,x+180,y+120)),role='chart_body')
             for x in (80,300) for y in (100,240)]
    objects.append(object_('figure_caption',scaled((70,378,515,400)),
                           'Figure 3.1 Distributions'))
    objects=[replace(o,page_width=600*factor,page_height=800*factor) for o in objects]
    doc=PdfDocument(Path('grid.pdf'),(PdfPage(1,600*factor,800*factor,()),))
    layout,result=evaluate(objects,doc)
    assert result['13']['findings']==[]
    assert len([o for o in layout if o.kind=='figure'])==1


def ruled_case_table(tmp_path,*,include_title=True,independent=False):
    path=tmp_path/'case-table.pdf'
    pdf=pymupdf.open();p=pdf.new_page(width=600,height=800)
    rules=[120,170,195,220,270,295,320,370,395,420]
    for y in rules:p.draw_line((80,y),(520,y),width=.8)
    pdf.save(path);pdf.close()
    objects=[];lines=[]
    if include_title:objects.append(object_('table_caption',(160,95,440,110),
                                            'Table 5.1 Qualitative examples','image_caption'))
    for i,y in enumerate((120,220,320)):
        objects.append(object_('figure',(85,y+10,515,y+47),role='image_body'))
        lines.extend([line('Input: a video example',(85,y+2,400,y+9)),
                      line('Output: model response',(85,y+55,490,y+68)),
                      line('Human: reference response',(85,y+78,490,y+91))])
    if independent:objects.append(object_('figure',(80,560,520,700),role='image_body'))
    return objects,PdfDocument(path,(PdfPage(1,600,800,tuple(lines)),))


def test_graphics_inside_a_ruled_case_table_inherit_the_table_title(tmp_path):
    objects,doc=ruled_case_table(tmp_path)
    layout,result=evaluate(objects,doc)
    assert result['13']['findings']==[]
    assert result['14']['findings']==[]
    assert len([o for o in layout if o.kind=='table'])==1
    assert not [o for o in layout if o.kind=='figure']


def test_fragmenting_and_reordering_table_cell_images_preserves_one_obligation(tmp_path):
    objects,doc=ruled_case_table(tmp_path)
    fragmented=[]
    for o in objects:
        if o.kind!='figure':fragmented.append(o);continue
        a,b,c,d=o.bbox;m=(a+c)/2
        fragmented.extend([replace(o,bbox=(a,b,m,d)),replace(o,bbox=(m,b,c,d))])
    for sequence in (fragmented,list(reversed(fragmented))):
        layout,result=evaluate(sequence,doc)
        assert result['13']['findings']==[]
        assert result['14']['findings']==[]
        assert len([o for o in layout if o.kind in {'table','figure'}])==1


def test_an_untitled_figure_outside_the_table_remains_an_alarm(tmp_path):
    objects,doc=ruled_case_table(tmp_path,independent=True)
    _,result=evaluate(objects,doc)
    assert len(result['13']['findings'])==1
    assert result['13']['findings'][0]['page']==1
    assert result['13']['findings'][0]['location']['bounding_rect']['y1']==560


def test_ruling_lines_without_repeated_record_fields_do_not_merge_figures(tmp_path):
    objects,doc=ruled_case_table(tmp_path)
    doc=PdfDocument(doc.path,(replace(doc.pages[0],lines=()),))
    layout,_=evaluate(objects,doc)
    assert len([o for o in layout if o.kind in {'figure','table'}])==3


def test_removing_a_total_title_cannot_turn_unowned_objects_into_a_clean_page(tmp_path):
    objects,doc=ruled_case_table(tmp_path,include_title=False)
    _,result=evaluate(objects,doc)
    assert result['13']['findings'] or result['14']['findings']


@pytest.mark.parametrize('factor',[.7,1,1.25])
def test_stacked_bilingual_subplots_keep_one_outer_title(factor):
 def scale(box):return tuple(v*factor for v in box)
 objs=[object_('figure',scale((100,100,500,300)),role='chart_body'),
       object_('figure',scale((100,366,500,566)),role='chart_body'),
       object_('figure_caption',scale((65,609,535,638)),'Figure 5.5 Performance and efficiency')]
 texts=[('(a) 性能对比',(160,312,440,326)),('(a) Performance comparison',(125,330,475,344)),
        ('(b) 效率分析',(160,577,440,591)),('(b) Efficiency analysis',(125,594,475,606))]
 ls=[replace(line(t,scale(b)),page_width=600*factor,page_height=800*factor) for t,b in texts]
 objs=[replace(o,page_width=600*factor,page_height=800*factor) for o in objs]
 doc=PdfDocument(Path('vertical-panels.pdf'),(PdfPage(1,600*factor,800*factor,tuple(ls)),))
 layout,result=evaluate(objs,doc)
 assert result['13']['findings']==[]
 assert len([o for o in layout if o.kind=='figure'])==1


def numeric_code_like_table(*,title=True,numeric=True):
    objects=[object_('text',(80,150,520,590),'Method Structure A B C\n[(stage -> stage)] -> result','code_body')]
    if title:objects.append(object_('table_caption',(85,105,515,140),'Table 7.1 Pipeline performance','code_caption'))
    objects += [object_('table',(80,150,520,210),role='native_table'),object_('table',(80,495,520,590),role='native_table')]
    ls=[]
    for row,y in enumerate((180,260,340,420,520)):
        ls.append(line('[(stage -> stage)] -> result',(90,y-8,280,y+10)))
        for col,x in enumerate((320,385,455)):
            ls.append(line(f'{70+row+col}.50' if numeric else f'return value{col};',(x,y,x+35,y+11)))
    return objects,PdfDocument(Path('code-like-result-table.pdf'),(PdfPage(1,600,800,tuple(ls)),))


def test_code_classification_does_not_fragment_a_captioned_numeric_result_table():
    objects,doc=numeric_code_like_table()
    for sequence in (objects,list(reversed(objects))):
        layout,result=evaluate(sequence,doc)
        assert result['14']['findings']==[]
        assert len([o for o in layout if o.kind=='table'])==1
        assert [o for o in layout if o.kind=='table'][0].bbox[3]>=590


def test_code_body_without_table_title_is_not_automatically_a_result_table():
    from pdf_rules.container_ownership import recover_code_like_result_tables
    objects,doc=numeric_code_like_table(title=False)
    result=recover_code_like_result_tables(objects,doc)
    assert not any(o.kind=='table' and o.role=='table_body' for o in result)


def test_table_title_does_not_convert_executable_code_without_numeric_columns():
    from pdf_rules.container_ownership import recover_code_like_result_tables
    objects,doc=numeric_code_like_table(numeric=False)
    result=recover_code_like_result_tables(objects,doc)
    assert not any(o.kind=='table' and o.role=='table_body' for o in result)


def test_ocr_short_panel_label_does_not_duplicate_the_same_native_label(tmp_path,monkeypatch):
    from pdf_rules import graphic_annotations
    from pdf_rules.local_ocr import OcrText
    path=tmp_path/'panel-label.pdf'
    with pymupdf.open() as pdf:
        pdf.new_page(width=600,height=800);pdf.save(path)
    ls=[line('(c) Method C',(160,632,220,643))]
    doc=PdfDocument(path,(PdfPage(1,600,800,tuple(ls)),))
    bodies=[object_('figure',(80,150,290,375),role='image_body'),object_('figure',(80,400,290,625),role='image_body')]
    monkeypatch.setattr(graphic_annotations,'_read_region',lambda *args:[OcrText('(c)',.99,(160,632,175,643))])
    result=graphic_annotations.recover_graphic_annotations(doc,bodies)
    assert len(result.pages[0].lines)==1


def test_ocr_restarted_panel_label_at_a_different_position_is_preserved(tmp_path,monkeypatch):
    from pdf_rules import graphic_annotations
    from pdf_rules.local_ocr import OcrText
    path=tmp_path/'restarted-label.pdf'
    with pymupdf.open() as pdf:
        pdf.new_page(width=600,height=800);pdf.save(path)
    ls=[line('(a) First figure',(160,384,220,395))]
    doc=PdfDocument(path,(PdfPage(1,600,800,tuple(ls)),))
    bodies=[object_('figure',(80,150,290,375),role='image_body'),object_('figure',(80,400,290,625),role='image_body')]
    monkeypatch.setattr(graphic_annotations,'_read_region',lambda *args:[OcrText('(a)',.99,(160,632,175,643))])
    result=graphic_annotations.recover_graphic_annotations(doc,bodies)
    assert len(result.pages[0].lines)==2


@pytest.mark.parametrize('scale',[.7,1,1.3])
def test_physical_figure_frame_owns_plots_legend_and_panel_name_rows(scale):
    def box(b):return tuple(x*scale for x in b)
    plots=[object_('figure',box((x,120,x+75,180)),role='chart_body') for x in (80,156,232,308,384)]
    plots=[replace(o,page_width=600*scale,page_height=800*scale) for o in plots]
    title=replace(object_('figure_caption',box((175,215,365,230)),'Figure 8.3 Method comparison'),page_width=600*scale,page_height=800*scale)
    texts=[line('Clean data | Poisoned data',box((285,102,450,112)))]+[
        line(f'Method {i}',box((x,185,x+70,195))) for i,x in enumerate((80,156,232,308,384))]
    texts=[replace(l,page_width=600*scale,page_height=800*scale) for l in texts]
    doc=PdfDocument(Path('framed-row.pdf'),(PdfPage(1,600*scale,800*scale,tuple(texts),graphics=(box((70,95,470,200)),)),))
    from pdf_rules.graphic_containers import merge_physical_graphic_containers
    result=merge_physical_graphic_containers(plots,[title],doc)
    assert len(result)==1
    assert len(result[0].panel_boxes)==5


def test_sparse_icons_do_not_fill_a_large_graphic_frame():
    from pdf_rules.graphic_containers import merge_physical_graphic_containers
    plots=[object_('figure',(160,200,180,220),role='image_body'),object_('figure',(300,200,320,220),role='image_body')]
    title=object_('figure_caption',(175,410,365,425),'Figure 8.3 Icons')
    doc=PdfDocument(Path('sparse.pdf'),(PdfPage(1,600,800,(),graphics=((70,95,470,400),)),))
    assert len(merge_physical_graphic_containers(plots,[title],doc))==2



def prompt_box(title='Reviewer core prompt',table_title=False):
    body=(80,100,520,330)
    texts=[line(title,(95,110,270,123)),
           line('You are a document auditor. Your task is to check the supplied evidence.',(95,140,505,153)),
           line('Please verify every claim and report uncertainties in your response.',(95,165,505,178)),
           line('Check that the cited evidence matches the original source material.',(95,190,505,203)),
           line('Explain why a reported error is supported by its context and source.',(95,215,505,228))]
    text='\n'.join(l.text for l in texts)
    objs=[object_('table',body,text,'table_body')]
    if table_title:objs.append(object_('table_caption',(180,70,420,85),'Table 8.2 Auditor prompt'))
    doc=PdfDocument(Path('prompt.pdf'),(PdfPage(1,600,800,tuple(texts),graphics=(body,)),))
    return objs,doc


def test_plain_instruction_prompt_frame_is_not_a_statistical_table():
    objs,doc=prompt_box()
    layout,result=evaluate(objs,doc)
    assert result['14']['findings']==[]
    assert not any(o.kind=='table' for o in layout)


def test_deliberately_captioned_prompt_table_keeps_its_table_identity():
    objs,doc=prompt_box(table_title=True)
    layout,result=evaluate(objs,doc)
    assert any(o.kind=='table' for o in layout)


def test_single_column_ordinary_prose_is_not_assumed_to_be_a_prompt():
    objs,doc=prompt_box('Audit result explanation')
    layout,result=evaluate(objs,doc)
    assert len(result['14']['findings'])==1


def test_prompt_heading_does_not_remove_a_multicolumn_table():
    objs,doc=prompt_box()
    cells=[line(f'Model {i}',(95,140+i*30,160,153+i*30)) for i in range(4)]
    cells += [line('Prompt instruction',(280,140+i*30,390,153+i*30)) for i in range(4)]
    doc=replace(doc,pages=(replace(doc.pages[0],lines=(doc.pages[0].lines[0],*cells)),))
    layout,result=evaluate(objs,doc)
    assert len(result['14']['findings'])==1
