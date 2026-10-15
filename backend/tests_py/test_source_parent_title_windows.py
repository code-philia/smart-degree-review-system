"""A native sliding window crossing a verified title is not another table.

Catches loss of source object ownership, while retaining nearby independent
untitled tables and rejecting unverified parser parent links.
"""
from dataclasses import replace
from pathlib import Path
import pytest
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.model import PdfDocument, PdfPage, PdfLine
from pdf_rules.object_identity import refine_targets
from pdf_rules.caption_rules import detect_caption_rules


def case(scale=1, *, native_title=True):
    def box(values):return tuple(v*scale for v in values)
    parent='layout:original-page:table:1'
    body=LayoutObject('table',1,box((80,120,520,410)),
                      'Method Value\nAlpha 12\nBeta 13',600*scale,800*scale,
                      role='table_body',source_id=parent+':body',parent_id=parent,
                      parent_bbox=box((80,120,520,410)),parent_kind='table')
    title=LayoutObject('table_caption',1,box((190,100,410,112)),
                       'Table 7.3 Parameter comparison',600*scale,800*scale,
                       role='table_caption',source_id=parent+':title',parent_id=parent,
                       parent_bbox=body.bbox,parent_kind='table')
    window=LayoutObject('table',1,box((80,88,520,183)),'',600*scale,800*scale,
                        role='native_table')
    texts=[PdfLine(1,'Table 7.3 Parameter comparison',box((192,100,408,112)),
                   600*scale,800*scale,bold=True)] if native_title else []
    texts.extend([PdfLine(1,t,box(b),600*scale,800*scale) for t,b in [
        ('Method Value',(90,128,400,140)),('Alpha 12',(90,170,400,182)),
        ('Beta 13',(90,208,400,220))]])
    doc=PdfDocument(Path('anonymous-table-source.pdf'),
                    (PdfPage(1,600*scale,800*scale,tuple(texts)),))
    return body,title,window,doc


def judged(objects,doc):
    layout=refine_targets(objects,doc)
    return layout,detect_caption_rules(layout,[14],doc)['14']['findings']


@pytest.mark.parametrize('scale',[.7,1,1.25])
@pytest.mark.parametrize('reverse',[False,True])
def test_verified_table_parent_consumes_the_native_window_crossing_its_title(scale,reverse):
    body,title,window,doc=case(scale)
    objects=[body,title,window]
    layout,findings=judged(list(reversed(objects)) if reverse else objects,doc)
    assert findings==[]
    assert [o.bbox for o in layout if o.kind=='table']==[body.bbox]


def test_nearby_independent_untitled_table_keeps_its_obligation():
    body,title,window,doc=case()
    independent=replace(window,bbox=(80,550,520,650))
    layout,findings=judged([body,title,window,independent],doc)
    assert [o.bbox for o in layout if o.kind=='table']==[body.bbox,independent.bbox]
    assert len(findings)==1
    assert findings[0]['location']['bounding_rect']['y1']==550


def test_parser_parent_alone_cannot_suppress_a_native_table():
    body,title,window,doc=case(native_title=False)
    _,findings=judged([body,title,window],doc)
    assert len(findings)==1
    assert findings[0]['location']['bounding_rect']['y1']==88


def test_unrelated_parser_namespaces_cannot_claim_a_native_window():
    body,title,window,doc=case()
    title=replace(title,parent_id='another-layout:table:1')
    _,findings=judged([body,title,window],doc)
    assert len(findings)==1


def test_an_independently_titled_upper_table_is_preserved():
    body,title,window,doc=case()
    independent_title=replace(title,bbox=(190,69,410,81),text='Table 7.2 Separate results',
                              parent_id='another-layout:table:2')
    layout,_=judged([body,title,window,independent_title],doc)
    assert window in layout


def test_missing_total_title_does_not_make_the_parser_body_clean():
    body,title,window,doc=case()
    _,findings=judged([body,window],doc)
    assert len(findings)==2


def test_data_outside_the_claimed_body_prevents_window_removal():
    body,title,window,doc=case()
    cell=PdfLine(1,'Separate header 36',(90,90,185,99),600,800)
    doc=replace(doc,pages=(replace(doc.pages[0],lines=(cell,)+doc.pages[0].lines),))
    layout,_=judged([body,title,window],doc)
    assert window in layout


def test_a_caption_shaped_internal_cell_does_not_prove_external_title_ownership():
    body,title,window,doc=case()
    body=replace(body,bbox=(80,88,520,410),parent_bbox=(80,88,520,410))
    title=replace(title,parent_bbox=body.bbox)
    layout,_=judged([body,title,window],doc)
    assert window in layout


def test_enlarging_a_parser_title_box_does_not_claim_a_separate_data_row():
    body,title,window,doc=case()
    title=replace(title,bbox=(80,90,520,115))
    cell=PdfLine(1,'Separate header 36',(90,90,185,99),600,800)
    doc=replace(doc,pages=(replace(doc.pages[0],lines=(cell,)+doc.pages[0].lines),))
    _,findings=judged([body,title,window],doc)
    assert len(findings)==1
    assert findings[0]['location']['bounding_rect']['y1']==88


def test_partial_frame_overlap_does_not_hide_a_separate_data_row():
    body,title,window,doc=case()
    cell=PdfLine(1,'Separate header 36',(450,90,550,99),600,800)
    doc=replace(doc,pages=(replace(doc.pages[0],lines=(cell,)+doc.pages[0].lines),))
    _,findings=judged([body,title,window],doc)
    assert len(findings)==1


def test_unrelated_neighbor_text_outside_the_frame_does_not_change_ownership():
    body,title,window,doc=case()
    neighbor=PdfLine(1,'Neighbor annotation',(530,90,590,99),600,800)
    doc=replace(doc,pages=(replace(doc.pages[0],lines=(neighbor,)+doc.pages[0].lines),))
    _,findings=judged([body,title,window],doc)
    assert findings==[]
