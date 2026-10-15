"""Academic text tables are sized by their physical frame, not page width."""
from dataclasses import replace
import pytest
import pymupdf
from pdf_rules.pdf_extract import extract_pdf
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.container_ownership import _recover_captioned_text_frames
from pdf_rules.caption_rules import detect_caption_rules


def original_frame(tmp_path,width=180,scale=1,side='below',with_title=True,with_rules=True,inner_title=False):
    path=tmp_path/'unseen-narrow-response-table.pdf'
    box=tuple(v*scale for v in (150,150,150+width,245))
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600*scale,height=840*scale)
        if with_rules:
            for y in (150,165,245):
                page.draw_line((150*scale,y*scale),((150+width)*scale,y*scale),width=.7*scale)
        for i in range(3):
            page.insert_text((155*scale,(180+i*20)*scale),'Independent response data with explained results.',fontsize=6*scale)
        if with_title:
            page.insert_text(((150+width/2-65)*scale,(139 if side=='above' else 262)*scale),'Table 9.8 Independent responses',fontsize=8*scale)
        if inner_title:
            page.insert_text((155*scale,205*scale),'Figure 9.7 Independent diagram',fontsize=6*scale)
        pdf.save(path)
    document=extract_pdf(path)
    objects=[LayoutObject('figure',1,box,'',600*scale,840*scale,'image_body')]
    for line in document.lines:
        if line.text.startswith('Table 9.8'):
            objects.append(LayoutObject('table_caption',1,line.bbox,line.text,600*scale,840*scale))
        if line.text.startswith('Figure 9.7'):
            objects.append(LayoutObject('figure_caption',1,line.bbox,line.text,600*scale,840*scale))
    return document,objects


@pytest.mark.parametrize('scale',[.5,1,1.5])
@pytest.mark.parametrize('width',[180,360])
@pytest.mark.parametrize('side',['above','below'])
def test_actual_ruled_table_title_owns_its_frame_at_different_page_ratios(tmp_path,scale,width,side):
    document,objects=original_frame(tmp_path,width,scale,side)
    prepared=_recover_captioned_text_frames(objects,document)
    assert len([o for o in prepared if o.kind=='table'])==1
    assert not detect_caption_rules(prepared,[13,14],document)['13']['findings']
    assert not detect_caption_rules(prepared,[13,14],document)['14']['findings']


@pytest.mark.parametrize('with_title,with_rules',[(False,True),(True,False)])
def test_proximity_or_native_rules_alone_cannot_create_caption_ownership(tmp_path,with_title,with_rules):
    document,objects=original_frame(tmp_path,with_title=with_title,with_rules=with_rules)
    prepared=_recover_captioned_text_frames(objects,document)
    assert any(o.kind=='figure' for o in prepared)
    assert detect_caption_rules(prepared,[13],document)['13']['findings']


def test_an_independent_inner_figure_title_prevents_the_outer_table_from_absorbing_it(tmp_path):
    document,objects=original_frame(tmp_path,inner_title=True)
    assert any(o.kind=='figure' for o in _recover_captioned_text_frames(objects,document))
