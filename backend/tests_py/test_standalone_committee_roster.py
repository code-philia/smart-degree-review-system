from pathlib import Path
from dataclasses import replace
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules


SCHEMA='答辩委员会工作职务 姓名 职称 工作单位 签名 主席 委员 委员 秘书'


def fixture(preceding_form=True,own_caption=False,outside=False,partial=False):
    first=PdfPage(1,600,840,(PdfLine(1,'答辩日期 论文题目 答辩结论 答辩委员会工作职务 姓名',(60,80,540,700),600,840,source='mineru',role='table_body'),))
    if not preceding_form:first=replace(first,lines=(PdfLine(1,'第一章 实验结果',(60,80,540,100),600,840),))
    line=PdfLine(2,SCHEMA,(60,80,540,250),600,840,source='mineru',role='table_body')
    second=PdfPage(2,600,840,(line,),unreadable=True,images=((0,0,600,840),),ink_bottom=650)
    box=(420,135,490,160)
    if outside:box=(100,500,300,610)
    if partial:box=(420,225,490,300)
    objects=[LayoutObject('table',2,line.bbox,SCHEMA,600,840,'table_body'),LayoutObject('figure',2,box,'',600,840,'image_body')]
    if own_caption:objects.append(LayoutObject('figure_caption',2,(400,170,520,185),'Figure 2.3 Example',600,840))
    return PdfDocument(Path('signature-object.pdf'),(first,second)),objects


def findings(**kwargs):
    document,objects=fixture(**kwargs)
    return detect_caption_rules(prepare_caption_layout(objects,document),[13,14],document)


def test_signature_image_fragment_in_verified_administrative_table_has_no_figure_title_obligation():
    result=findings()
    assert result['13']['findings']==[] and result['14']['findings']==[]


def test_standalone_schema_cannot_replace_preceding_administrative_form_evidence():
    assert findings(preceding_form=False)['13']['findings']


def test_independent_figure_outside_signature_region_is_not_masked():
    assert findings(outside=True)['13']['findings']


def test_partial_overlap_cannot_mask_a_visible_neighbor_figure():
    assert findings(partial=True)['13']['findings']


def test_a_title_inside_signature_bounds_keeps_an_independent_figure_target():
    document,objects=fixture(own_caption=True)
    assert [o for o in prepare_caption_layout(objects,document) if o.kind=='figure' and o.role=='image_body']
