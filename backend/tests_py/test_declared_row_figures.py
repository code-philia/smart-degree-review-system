from dataclasses import replace
from pathlib import Path
import pytest
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules


def scene(n=4,title_text='图9.8 不同场景的结果。上排为原始结果，下排为独立对照结果。',own_title=False):
    width=440;part=(width-(n-1)*12)/n
    boxes=tuple((80+i*(part+12),y,80+i*(part+12)+part,y+104) for y in (140,274) for i in range(n))
    objects=[LayoutObject('figure',1,b,'',600,840,'image_body') for b in boxes]
    lines=[]
    if title_text:
        title=PdfLine(1,title_text,(80,405,520,428),600,840,font_size=10.5,bold=True)
        objects.append(LayoutObject('figure_caption',1,title.bbox,title.text,600,840))
        lines.append(title)
    if own_title:
        title=PdfLine(1,'Figure 9.7 Independent upper experiment',(80,253,520,266),600,840,font_size=10.5,bold=True)
        objects.append(LayoutObject('figure_caption',1,title.bbox,title.text,600,840));lines.append(title)
    doc=PdfDocument(Path('unseen-declared-row-grid.pdf'),(PdfPage(1,600,840,tuple(lines),images=boxes),))
    return doc,objects


@pytest.mark.parametrize('n',[2,4])
@pytest.mark.parametrize('declaration',['上排为原始结果，下排为对照结果。','Upper row: original. Lower row: independent comparisons.'])
def test_explicit_two_row_total_caption_owns_the_aligned_physical_grid(n,declaration):
    doc,objects=scene(n,'Figure 9.8 Conditions comparison. '+declaration)
    prepared=prepare_caption_layout(objects,doc)
    assert len([o for o in prepared if o.kind=='figure'])==1
    assert not detect_caption_rules(prepared,[13],doc)['13']['findings']


def test_proximity_without_explicit_row_declaration_keeps_independent_upper_objects():
    doc,objects=scene(title_text='Figure 9.8 Independent lower results')
    assert detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)['13']['findings']


def test_removed_total_title_cannot_be_replaced_by_grid_geometry():
    doc,objects=scene(title_text='')
    assert detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)['13']['findings']


def test_independent_intervening_title_is_a_row_ownership_boundary():
    doc,objects=scene(own_title=True)
    assert len([o for o in prepare_caption_layout(objects,doc) if o.kind=='figure'])>=2


def test_a_member_title_above_the_grid_keeps_other_members_independent():
    doc,objects=scene(n=2)
    own=LayoutObject('figure_caption',1,(80,113,294,128),'Figure 9.7 Separate top-left result',600,840)
    prepared=prepare_caption_layout(objects+[own],doc)
    assert len([o for o in prepared if o.kind=='figure'])>1
    assert detect_caption_rules(prepared,[13],doc)['13']['findings']


@pytest.mark.parametrize('gap',[1,3])
def test_body_prose_is_a_barrier_even_close_to_the_upper_row(gap):
    doc,objects=scene(n=2)
    text=PdfLine(1,'This independent paragraph explains the first experiment.',(80,244+gap,520,258+gap),600,840,font_size=10.5)
    doc=replace(doc,pages=(replace(doc.pages[0],lines=doc.pages[0].lines+(text,)),))
    assert detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)['13']['findings']


@pytest.mark.parametrize('title',['图9.8 上行链路和下行链路的质量对比。','图9.8 上行信道和下行信道的结果。'])
def test_domain_uplink_downlink_terms_do_not_declare_two_physical_rows(title):
    doc,objects=scene(n=2,title_text=title)
    assert detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)['13']['findings']


@pytest.mark.parametrize('subtitle',['Baseline','Original unmodified results'])
def test_a_centered_bold_row_subtitle_does_not_become_an_independent_body_paragraph(subtitle):
    doc,objects=scene(n=2)
    text=PdfLine(1,subtitle,(190,250,410,263),600,840,font_size=10.5,bold=True)
    doc=replace(doc,pages=(replace(doc.pages[0],lines=doc.pages[0].lines+(text,)),))
    assert not detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)['13']['findings']


@pytest.mark.parametrize('covered',[1,2,3,4])
def test_an_upper_subgroup_title_preserves_its_physical_row_boundary(covered):
    doc,objects=scene(n=4)
    members=sorted([o for o in objects if o.kind=='figure' and o.bbox[1]==140],key=lambda o:o.bbox[0])
    box=(members[0].bbox[0],113,members[covered-1].bbox[2],128)
    own=LayoutObject('figure_caption',1,box,'Figure 9.7 Independent upper-row result',600,840)
    prepared=prepare_caption_layout(objects+[own],doc)
    assert len([o for o in prepared if o.kind=='figure'])>1


@pytest.mark.parametrize('physical',[False,True])
def test_a_closer_preceding_observation_needs_native_physical_evidence(physical):
    doc,objects=scene(n=4)
    top=sorted([o for o in objects if o.kind=='figure' and o.bbox[1]==140],key=lambda o:o.bbox[0])
    own=LayoutObject('figure_caption',1,(top[0].bbox[0],113,top[1].bbox[2],128),'Figure9.7 Independent upper subgroup',600,840)
    prev=replace(top[0],bbox=(80,40,294,110))
    if physical:doc=replace(doc,pages=(replace(doc.pages[0],images=doc.pages[0].images+(prev.bbox,)),))
    prepared=prepare_caption_layout(objects+[own,prev],doc)
    grids=[o for o in prepared if o.role=='declared_row_panels']
    assert bool(grids)==physical
