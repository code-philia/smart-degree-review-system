from dataclasses import replace
from pathlib import Path
import pytest
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.logical_objects import shared_title_groups
from pdf_rules.caption_rules import detect_caption_rules


def scene(n=3,scale=1.,title='Figure 8.4 Examples from the sample dataset'):
    boxes=tuple((80+i*154,140,230+i*154,286) for i in range(n))
    def scaled(b):return tuple(v*scale for v in b)
    objects=[LayoutObject('figure',1,scaled(b),'',600*scale,840*scale,'image_body') for b in boxes]
    width=boxes[-1][2]-boxes[0][0];center=(boxes[0][0]+boxes[-1][2])/2
    cap=LayoutObject('figure_caption',1,scaled((center-72,293,center+72,308)),title,600*scale,840*scale)
    doc=PdfDocument(Path('unseen-compact-samples.pdf'),(PdfPage(1,600*scale,840*scale,(),images=tuple(scaled(b) for b in boxes)),))
    return doc,objects,cap


@pytest.mark.parametrize('n',[3,4])
@pytest.mark.parametrize('scale',[.75,1.,1.25])
@pytest.mark.parametrize('title',['图8.4 数据集中部分样本图像','Figure 8.4 Examples from the sample dataset'])
def test_physical_sample_row_with_short_collective_caption_is_one_object(n,scale,title):
    doc,objects,cap=scene(n,scale,title)
    out=shared_title_groups(objects,[cap],doc)
    assert len(out)==1
    assert not detect_caption_rules(out+[cap],[13],doc)['13']['findings']


def test_caption_for_only_the_middle_photo_is_not_borrowed_by_neighbors():
    doc,objects,cap=scene(title='Figure 8.4 A single specimen')
    assert len(shared_title_groups(objects,[cap],doc))==3


def test_removed_total_caption_does_not_erase_title_obligations():
    doc,objects,cap=scene()
    assert len(detect_caption_rules(shared_title_groups(objects,[],doc),[13],doc)['13']['findings'])==3


def test_missing_native_image_evidence_preserves_separate_observations():
    doc,objects,cap=scene();doc=replace(doc,pages=(replace(doc.pages[0],images=()),))
    assert len(shared_title_groups(objects,[cap],doc))==3


@pytest.mark.parametrize('covered',[1,2,3])
def test_independent_member_or_subgroup_caption_prevents_collective_merge(covered):
    doc,objects,cap=scene()
    own=replace(cap,bbox=(objects[0].bbox[0],117,objects[covered-1].bbox[2],132),text='Figure 8.3 Independent experiment')
    assert len(shared_title_groups(objects,[cap,own],doc))>1


def test_body_paragraph_between_row_and_caption_is_a_boundary():
    doc,objects,cap=scene();cap=replace(cap,bbox=(220,337,364,352))
    line=PdfLine(1,'A separate paragraph starts another experimental discussion.',(80,300,536,314),600,840)
    doc=replace(doc,pages=(replace(doc.pages[0],lines=(line,)),))
    assert len(shared_title_groups(objects,[cap],doc))==3


def test_a_restarted_panel_letter_keeps_independent_figures():
    doc,objects,cap=scene()
    lines=tuple(PdfLine(1,'(a)',(o.bbox[0]+45,270,o.bbox[0]+60,283),600,840) for o in objects)
    doc=replace(doc,pages=(replace(doc.pages[0],lines=lines),))
    assert len(shared_title_groups(objects,[cap],doc))==3
