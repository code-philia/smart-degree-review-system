"""Panel marks describe visual bodies, not extra graphic targets."""
from pathlib import Path
from dataclasses import replace
import pytest
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules
from pdf_rules.logical_objects import panel_label_lines


def fixture(mixed=False,with_title=True,with_independent_table_title=False,restart=False):
    boxes=((80,100,280,240),(320,100,520,240),(80,280,280,420),(320,280,520,420))
    bodies=[LayoutObject('table' if mixed and i==1 else 'figure',1,b,'',600,840,
                        'table_body' if mixed and i==1 else 'image_body') for i,b in enumerate(boxes)]
    tags=('a','b','a','b') if restart else ('a','b','c','d')
    lines=tuple(PdfLine(1,f'({t}) 不同条件结果',(b[0]+30,b[3]+6,b[2]-30,b[3]+18),600,840)
                for t,b in zip(tags,boxes))
    doc=PdfDocument(Path('unseen-labelled-composite.pdf'),(PdfPage(1,600,840,lines,images=boxes),))
    objects=list(bodies)
    if with_title:objects.append(LayoutObject('figure_caption',1,(100,450,500,470),'Figure 9.8 Independent experimental comparisons',600,840))
    if with_independent_table_title:objects.append(LayoutObject('table_caption',1,(335,78,505,94),'Table 9.4 Independent records',600,840))
    return doc,objects


def test_mixed_parser_types_follow_one_physical_panel_namespace_without_caption_letter_list():
    doc,objects=fixture(mixed=True)
    prepared=prepare_caption_layout(objects,doc)
    assert len([o for o in prepared if o.kind=='figure'])==1
    assert not any(o.kind=='table' for o in prepared)
    result=detect_caption_rules(prepared,[13,14],doc)
    assert result['13']['findings']==result['14']['findings']==[]


def test_own_table_title_preserves_independent_table_obligation():
    doc,objects=fixture(mixed=True,with_independent_table_title=True)
    assert any(o.kind=='table' for o in prepare_caption_layout(objects,doc))


def test_missing_common_title_does_not_change_table_identity():
    doc,objects=fixture(mixed=True,with_title=False)
    result=prepare_caption_layout(objects,doc)
    assert any(o.kind=='table' for o in result)
    findings=detect_caption_rules(result,[13,14],doc)
    assert findings['13']['findings'] and findings['14']['findings']


def test_restarted_namespaces_do_not_hide_an_independent_untitled_upper_row():
    doc,objects=fixture(mixed=True,restart=True)
    findings=detect_caption_rules(prepare_caption_layout(objects,doc),[13,14],doc)
    assert findings['13']['findings'] or findings['14']['findings']


def test_multi_panel_description_is_not_a_new_physical_panel_mark():
    doc,objects=fixture()
    explanation=PdfLine(1,'(a)(c) 第一种方法；(b)(d) 第二种方法。',(80,440,520,450),600,840)
    page=replace(doc.pages[0],lines=doc.pages[0].lines+(explanation,))
    assert len(panel_label_lines(page,objects))==4


def test_native_text_strip_cannot_steal_the_label_from_its_raster_body():
    boxes=((129,99,286,256),(345,99,502,258))
    bodies=[LayoutObject('figure',1,b,'',600,840,'image_body') for b in boxes]
    labels=(PdfLine(1,'(a) 第一种方法',(177,271,239,283),600,840),
            PdfLine(1,'(b) 第二种方法',(392,271,455,283),600,840))
    strips=[LayoutObject('figure',1,b,'',600,840,'native_figure')
            for b in ((170,264,247,284),(385,264,463,284))]
    title=LayoutObject('figure_caption',1,(100,296,515,321),'Figure 9.8 Experimental comparisons',600,840)
    doc=PdfDocument(Path('unseen-annotation-strip.pdf'),(PdfPage(1,600,840,labels,images=boxes),))
    layout=prepare_caption_layout(bodies+strips+[title],doc)
    assert len([o for o in layout if o.kind=='figure'])==1
    assert detect_caption_rules(layout,[13],doc)['13']['findings']==[]


def test_a_real_native_graphic_with_additional_content_is_not_discarded_as_a_label():
    doc,objects=fixture()
    extra=LayoutObject('figure',1,(105,240,255,279),'',600,840,'native_figure')
    diagram_line=PdfLine(1,'Independent measured axis',(110,265,250,277),600,840)
    doc=replace(doc,pages=(replace(doc.pages[0],lines=doc.pages[0].lines+(diagram_line,)),))
    layout=prepare_caption_layout(objects+[extra],doc)
    assert any(o.kind=='figure' and o.bbox[1]<=240 and o.bbox[3]>=277 for o in layout)


def test_bilingual_caption_rows_are_one_title_when_resolving_mixed_panel_types():
    doc,objects=fixture(mixed=True)
    objects.append(LayoutObject('figure_caption',1,(170,477,430,491),'图9.8 不同实验条件的比较',600,840))
    prepared=prepare_caption_layout(objects,doc)
    assert len([o for o in prepared if o.kind=='figure'])==1
    assert not any(o.kind=='table' for o in prepared)
    assert detect_caption_rules(prepared,[13,14],doc)['13']['findings']==[]



def description_block_fixture(include_title=True,unrelated=False):
    doc,objects=fixture()
    objects=[o for o in objects if not o.kind.endswith('_caption')]
    page=doc.pages[0]
    extra=(PdfLine(1,'(a)(c) 第一种方法；(b)(d) 第二种方法。',(80,445,520,457),600,840,font_size=10.5,bold=True),
           PdfLine(1,'(a)(c) First method; (b)(d) Second method.',(80,470,520,482),600,840,font_size=10.5,bold=True),
           PdfLine(1,'Original samples and their corresponding experimental results',(80,495,520,507),600,840,font_size=10.5,bold=True),
           PdfLine(1,'The comparison uses independent experimental conditions.',(80,517,520,529),600,840,font_size=10.5,bold=True))
    if unrelated:extra=(replace(extra[0],text='(a)(b) 无关说明；(x)(y) 另一种方法。'),)+extra[1:]
    title_line=PdfLine(1,'Figure 9.8 Experimental comparisons',(170,540,430,552),600,840,font_size=10.5,bold=True)
    if include_title:
        objects.append(LayoutObject('figure_caption',1,title_line.bbox,title_line.text,600,840))
        extra+=(title_line,)
    doc=replace(doc,pages=(replace(page,lines=page.lines+extra),))
    return doc,objects


def test_common_caption_includes_its_explicit_multi_panel_description_block():
    doc,objects=description_block_fixture()
    layout=prepare_caption_layout(objects,doc)
    assert detect_caption_rules(layout,[13],doc)['13']['findings']==[]


def test_panel_explanation_alone_does_not_replace_removed_total_caption():
    doc,objects=description_block_fixture(include_title=False)
    layout=prepare_caption_layout(objects,doc)
    assert detect_caption_rules(layout,[13],doc)['13']['findings']


def test_description_with_foreign_panel_letters_cannot_extend_the_title():
    doc,objects=description_block_fixture(unrelated=True)
    layout=prepare_caption_layout(objects,doc)
    assert detect_caption_rules(layout,[13],doc)['13']['findings']


def test_merged_native_marks_preserve_an_independent_restarted_panel_namespace():
    boxes=((30,100,155,240),(175,100,300,240),(320,100,445,240),(465,100,590,240))
    bodies=[LayoutObject('figure',1,b,'',600,840,'image_body') for b in boxes]
    merged=PdfLine(1,'(a)     (b)',(55,246,280,258),600,840,
                   text_regions=((0,3,(55,246,75,258)),(8,11,(260,246,280,258))))
    labels=(merged,PdfLine(1,'(a) second',(350,246,420,258),600,840),
            PdfLine(1,'(b) second',(490,246,560,258),600,840))
    doc=PdfDocument(Path('unseen-merged-panel-row.pdf'),(PdfPage(1,600,840,labels,images=boxes),))
    title=LayoutObject('figure_caption',1,(30,274,590,289),'Figure 9.8 Second experiment',600,840)
    lines=panel_label_lines(doc.pages[0],bodies+[title])
    assert [l.text[:3] for l in lines]==['(a)','(b)','(a)','(b)']
    assert lines[0].bbox==(55,246,75,258)
    assert detect_caption_rules(prepare_caption_layout(bodies+[title],doc),[13],doc)['13']['findings']


def mixed_column_fixture(interior=False):
    boxes=((40,100,140,220),(160,100,260,220),(40,270,140,390),(160,270,260,390))
    objects=[LayoutObject('table' if i==1 else 'figure',1,b,'',600,840,
                          'table_body' if i==1 else 'image_body') for i,b in enumerate(boxes)]
    lines=tuple(PdfLine(1,f'({t}) condition',(b[0]+15,b[3]+5,b[2]-15,b[3]+17),600,840)
                for b,t in zip(boxes,'abcd'))
    objects.append(LayoutObject('figure_caption',1,(40,410,260,426),'Figure 9.8 Comparisons',600,840))
    right=(350,80,570,205)
    objects.append(LayoutObject('figure',1,right,'',600,840,'image_body'))
    objects.append(LayoutObject('figure_caption',1,(100,230,220,245) if interior else (350,230,570,245),
                                'Figure 9.9 Independent experiment',600,840))
    doc=PdfDocument(Path('unseen-two-column-panels.pdf'),(PdfPage(1,600,840,lines,images=boxes+(right,)),))
    return doc,objects


def test_disjoint_column_title_cannot_block_mixed_panel_identity():
    doc,objects=mixed_column_fixture()
    findings=detect_caption_rules(prepare_caption_layout(objects,doc),[13,14],doc)
    assert not findings['13']['findings'] and not findings['14']['findings']


def test_intersecting_independent_title_still_blocks_mixed_panel_identity():
    doc,objects=mixed_column_fixture(interior=True)
    assert any(o.kind=='table' for o in prepare_caption_layout(objects,doc))


def test_description_title_extension_ignores_disjoint_column_objects_and_titles():
    doc,objects=description_block_fixture()
    def left(box):return (40+(box[0]-80)*.5,box[1],40+(box[2]-80)*.5,box[3])
    objects=[replace(o,bbox=left(o.bbox)) for o in objects]
    page=doc.pages[0]
    page=replace(page,lines=tuple(replace(l,bbox=left(l.bbox)) for l in page.lines),
                 images=tuple(left(b) for b in page.images))
    right=LayoutObject('figure',1,(350,465,570,490),'',600,840,'image_body')
    title=LayoutObject('figure_caption',1,(350,496,570,508),'Figure 9.9 Independent experiment',600,840)
    doc=replace(doc,pages=(replace(page,images=page.images+(right.bbox,)),))
    findings=detect_caption_rules(prepare_caption_layout(objects+[right,title],doc),[13],doc)
    assert not findings['13']['findings']


def test_merged_native_named_labels_keep_their_distinct_physical_owners():
    boxes=((30,100,155,240),(175,100,300,240),(320,100,445,240),(465,100,590,240))
    bodies=[LayoutObject('figure',1,b,'',600,840,'image_body') for b in boxes]
    text='(a) First;     (b) Second';second=text.index('(b)')
    regions=((0,3,(55,246,75,258)),(4,10,(80,246,120,258)),
             (second,second+3,(200,246,220,258)),(second+4,len(text),(225,246,280,258)))
    labels=(PdfLine(1,text,(55,246,280,258),600,840,text_regions=regions),
            PdfLine(1,'(a) second',(350,246,420,258),600,840),
            PdfLine(1,'(b) second',(490,246,560,258),600,840))
    doc=PdfDocument(Path('unseen-merged-named-labels.pdf'),(PdfPage(1,600,840,labels,images=boxes),))
    title=LayoutObject('figure_caption',1,(30,274,590,289),'Figure 9.8 Second experiment',600,840)
    assert len(panel_label_lines(doc.pages[0],bodies+[title]))==4
    assert detect_caption_rules(prepare_caption_layout(bodies+[title],doc),[13],doc)['13']['findings']


@pytest.mark.parametrize('start',[435,450])
def test_common_bilingual_title_does_not_block_itself_at_native_label_boundary(start):
    doc,objects=fixture(mixed=True,with_title=False)
    objects+=[LayoutObject('figure_caption',1,(100,start,500,start+12),'Figure 9.8 Comparisons',600,840),
              LayoutObject('figure_caption',1,(170,start+19,430,start+31),'图9.8 不同条件的比较',600,840)]
    result=detect_caption_rules(prepare_caption_layout(objects,doc),[13,14],doc)
    assert not result['13']['findings'] and not result['14']['findings']


@pytest.mark.parametrize('shift',[0,35])
def test_duplicate_native_observations_do_not_vote_as_independent_mixed_panels(shift):
    from pdf_rules.container_ownership import _mixed_panel_identity
    def box(x1,y1,x2,y2):return (x1+shift,y1,x2+shift,y2)
    boxes=(box(60,80,260,230),box(280,80,480,230),box(60,237,260,402),box(280,242,480,402))
    objects=[LayoutObject('table' if i==1 else 'figure',1,b,'',600,840,
                          'table_body' if i==1 else 'chart_body') for i,b in enumerate(boxes)]
    labels=tuple(PdfLine(1,f'({t}) Independent setting',box(x,237 if i<2 else 408,x+85,248 if i<2 else 419),600,840)
                 for i,(t,x) in enumerate(zip('abcd',(110,330,110,330))))
    title=LayoutObject('figure_caption',1,box(130,438,410,451),'Figure 9.8 Condition comparison',600,840)
    natives=[LayoutObject('figure',1,b,'',600,840,'native_figure') for b in
             (box(63,80,262,228),box(63,251,262,400),box(282,251,482,400))]
    doc=PdfDocument(Path('unseen-native-duplicate-votes.pdf'),(PdfPage(1,600,840,labels,images=boxes),))
    restored=_mixed_panel_identity(objects+natives+[title],doc)
    assert not any(o.kind=='table' for o in restored)


@pytest.mark.parametrize('gap',[21,25,31])
def test_only_native_label_carriers_cannot_own_the_panel_body_marks(gap):
    from pdf_rules.layout_context import _panel_group
    boxes=((129,99,286,256),(345,99,502,258))
    bodies=[LayoutObject('figure',1,b,'',600,840,'image_body') for b in boxes]
    labels=(PdfLine(1,'(a) First',(177,256+gap-6,239,256+gap+6),600,840),
            PdfLine(1,'(b) Second',(392,271,455,283),600,840))
    strips=[LayoutObject('figure',1,(l.bbox[0]-7,l.bbox[1]-7,l.bbox[2]+7,l.bbox[3]+1),'',600,840,'native_figure') for l in labels]
    title=LayoutObject('figure_caption',1,(100,315,515,331),'Figure 9.8 Conditions comparison',600,840)
    doc=PdfDocument(Path('unseen-native-marker-carriers.pdf'),(PdfPage(1,600,840,labels,images=boxes),))
    grouped=_panel_group(bodies+strips,doc,[title])
    assert any(set(boxes).issubset(set(o.panel_boxes)) for o in grouped)
    assert not any(o.role=='native_figure' for o in grouped)


def test_native_label_region_with_independent_content_keeps_its_obligation():
    from pdf_rules.layout_context import _panel_group
    doc,objects=fixture()
    labels=doc.pages[0].lines
    mark=labels[0]
    native=LayoutObject('figure',1,(mark.bbox[0]-5,mark.bbox[1]-3,mark.bbox[2]+5,mark.bbox[3]+20),'',600,840,'native_figure')
    independent=PdfLine(1,'Independent schematic measurement',(native.bbox[0]+2,mark.bbox[3]+3,native.bbox[2]-2,mark.bbox[3]+14),600,840)
    doc=replace(doc,pages=(replace(doc.pages[0],lines=labels+(independent,)),))
    assert any(o.role=='native_figure' for o in _panel_group([o for o in objects if o.kind=='figure']+[native],doc,[o for o in objects if o.kind.endswith('_caption')]))


@pytest.mark.parametrize('kind',['raster','vector'])
def test_small_independent_native_ink_is_not_discarded_by_an_area_threshold(kind):
    body=(100,100,300,240);small=(157,255,169,267)
    parent=LayoutObject('figure',1,body,'',600,840,'image_body')
    strip=LayoutObject('figure',1,(155,253,245,274),'',600,840,'native_figure')
    mark=PdfLine(1,'(a) Result',(175,260,235,272),600,840)
    title=LayoutObject('figure_caption',1,(100,75,300,89),'Figure 9.8 Independent parent',600,840)
    page=PdfPage(1,600,840,(mark,),images=(body,small) if kind=='raster' else (body,),
                 graphics=(small,) if kind=='vector' else ())
    doc=PdfDocument(Path('unseen-independent-small-ink.pdf'),(page,))
    assert detect_caption_rules(prepare_caption_layout([parent,strip,title],doc),[13],doc)['13']['findings']


def test_short_common_title_below_actual_panel_marks_preserves_mixed_identity():
    doc,objects=fixture(mixed=True)
    objects=[replace(o,bbox=(100,440,500,453)) if o.kind=='figure_caption' else o for o in objects]
    prepared=prepare_caption_layout(objects,doc)
    assert not any(o.kind=='table' for o in prepared)
    assert detect_caption_rules(prepared,[13,14],doc)['13']['findings']==[]
