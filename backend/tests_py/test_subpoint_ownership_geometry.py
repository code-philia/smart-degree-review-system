"""Ownership percentages must not change when PDF geometry is sub-point sized.

A one-square-point denominator floor loses genuine primitive containment.
Literal fractions, empty shapes and the missing-title consumer guard both
sides of that bug; no parser output or labelled paper is hard-coded.
"""
from pathlib import Path
import pytest
from pdf_rules.layout_context import containment, prepare_caption_layout
from pdf_rules.object_identity import coverage
from pdf_rules.caption_rules import _horizontal_overlap, _matches, detect_caption_rules
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.model import PdfDocument, PdfPage


@pytest.mark.parametrize('scale',[.05,.5,2])
def test_containment_fraction_is_scale_invariant(scale):
    small=(0,0,scale,scale)
    assert containment(small,(-1,-1,3,3))==pytest.approx(1)
    assert containment(small,(0,0,scale*.5,scale))==pytest.approx(.5)
    assert containment(small,(2,2,3,3))==0


@pytest.mark.parametrize('scale',[.05,.5,2])
def test_union_coverage_uses_the_actual_positive_area(scale):
    box=(0,0,scale,scale)
    overlapping=((0,0,scale*.5,scale),(scale*.25,0,scale*.75,scale))
    assert coverage(box,overlapping)==pytest.approx(.75)
    assert coverage(box,(box,box))==pytest.approx(1)


@pytest.mark.parametrize('box',[(1,1,1,2),(1,1,2,1),(2,1,1,2)])
def test_empty_or_invalid_boxes_do_not_acquire_ownership(box):
    assert containment(box,(0,0,3,3))==0
    assert coverage(box,((0,0,3,3),))==0


def test_a_narrow_figure_keeps_its_actual_title_overlap_fraction():
    target=LayoutObject('figure',1,(100,100,100.2,140),'',600,800)
    title=LayoutObject('figure_caption',1,(95,144,220,155),'Figure 4.8 Detail',600,800)
    assert _horizontal_overlap(target,title)==pytest.approx(1)
    assert _matches(target,title)


def test_captioned_parent_owns_a_subpoint_bitmap_without_extra_obligation():
    body=LayoutObject('figure',1,(100,100,300,250),'',600,800,role='image_body')
    title=LayoutObject('figure_caption',1,(110,260,290,274),'Figure 4.8 Rendering',600,800)
    piece=(150,150,150.5,150.5)
    document=PdfDocument(Path('anonymous-primitives.pdf'),(PdfPage(1,600,800,(),images=(piece,)),))
    layout=prepare_caption_layout([body,title],document)
    assert detect_caption_rules(layout,[13],document)['13']['findings']==[]
    assert len([o for o in layout if o.kind=='figure'])==1


def test_an_unowned_subpoint_bitmap_remains_detectable():
    piece=(150,150,150.5,150.5)
    document=PdfDocument(Path('anonymous-small-figure.pdf'),(PdfPage(1,600,800,(),images=(piece,)),))
    layout=prepare_caption_layout([],document)
    findings=detect_caption_rules(layout,[13],document)['13']['findings']
    assert len(findings)==1
    assert findings[0]['location']['bounding_rect']['x1']==150


@pytest.mark.parametrize('scale',[.05,.5,2])
@pytest.mark.parametrize('inside_fraction',[.25,.5])
def test_small_bitmap_with_most_ink_outside_cannot_be_owned_by_nearby_title(scale,inside_fraction):
    body=LayoutObject('figure',1,(100,100,300,250),'',600,800,role='image_body')
    title=LayoutObject('figure_caption',1,(110,260,290,274),'Figure 4.8 Rendering',600,800)
    left=300-scale*inside_fraction
    piece=(left,150,left+scale,150+scale)
    document=PdfDocument(Path('independent-edge-bitmap.pdf'),(PdfPage(1,600,800,(),images=(piece,)),))
    layout=prepare_caption_layout([body,title],document)
    findings=detect_caption_rules(layout,[13],document)['13']['findings']
    assert len(findings)==1
    box=findings[0]['location']['bounding_rect']
    assert box['x1']==pytest.approx(left)
    assert box['x2']==pytest.approx(left+scale)
