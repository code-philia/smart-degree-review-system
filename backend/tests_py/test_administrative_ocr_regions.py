from dataclasses import replace
from pathlib import Path
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import recover_document,decision_form,prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules

FORM = "姓名 李甲 学号 123 所在学科 工学 指导教师 王乙 答辩日期 2026-01-01 答辩地点 教室 论文题目 研究方法 评语和决议 论文写作规范，经答辩委员会讨论和无记名投票，同意通过该同学的学位论文答辩，并建议授予其博士学位。"
ROSTER = "答辩委员会工作职务 姓名 职称 工作单位 签名 主席 委员 委员 委员 秘书"


def line(page,text,box,role="",source="native"):
    return PdfLine(page,text,box,600,840,role=role,source=source)


def fixture(native=False):
    first = PdfPage(1,600,840,(),unreadable=False)
    second = PdfPage(2,600,840,(),unreadable=False)
    if native:
        first=replace(first,lines=(line(1,FORM,(60,90,540,700),"table_body"),))
        second=replace(second,lines=(line(2,ROSTER,(60,60,540,310),"table_body"),))
    objects=[LayoutObject("text",1,(145,60,455,80),"大学博士学位论文答辩决议书",600,840,"table_caption"),
             LayoutObject("table",1,(60,90,540,700),FORM,600,840,"table_body"),
             LayoutObject("text",1,(60,90,540,700),FORM,600,840,"table_body"),
             LayoutObject("table",2,(60,60,540,310),ROSTER,600,840,"table_body"),
             LayoutObject("text",2,(60,60,540,310),ROSTER,600,840,"table_body")]
    return PdfDocument(Path("outlined-administrative.pdf"),(first,second)),objects


def test_outline_text_form_and_signature_schema_are_recovered_as_bounded_evidence():
    doc,objects=fixture()
    recovered=recover_document(doc,objects)
    assert decision_form(recovered.pages[0])
    assert any(l.role=="table_body" and "签名" in l.text for l in recovered.pages[1].lines)
    result=detect_caption_rules(prepare_caption_layout(objects,recovered),[14],recovered)
    assert result["14"]["findings"]==[]


def test_no_duplicate_native_administrative_reading_is_added():
    doc,objects=fixture(native=True)
    recovered=recover_document(doc,objects)
    assert sum(l.role=="table_body" for l in recovered.pages[0].lines)==1
    assert sum(l.role=="table_body" for l in recovered.pages[1].lines)==1


def test_research_reference_outside_form_prevents_whole_page_exclusion():
    doc,objects=fixture()
    reference=line(1,"See Figure 9.9.",(60,730,540,750))
    first=replace(doc.pages[0],lines=(reference,))
    recovered=recover_document(replace(doc,pages=(first,doc.pages[1])),objects)
    assert not decision_form(recovered.pages[0])
    assert reference in recovered.pages[0].lines


def test_graphic_below_signature_region_keeps_its_caption_obligation():
    doc,objects=fixture()
    outside=LayoutObject("figure",2,(100,500,400,700),"",600,840,"image_body")
    recovered=recover_document(doc,objects+[outside])
    result=detect_caption_rules(prepare_caption_layout(objects+[outside],recovered),[13],recovered)
    assert len(result["13"]["findings"])==1
    assert result["13"]["findings"][0]["location"]["bounding_rect"]["y1"]==500


def test_unread_content_outside_signature_region_stays_unread():
    doc,objects=fixture()
    second=replace(doc.pages[1],unreadable=True,images=((0,0,600,840),))
    recovered=recover_document(replace(doc,pages=(doc.pages[0],second)),objects)
    assert recovered.pages[1].unreadable


def test_arbitrary_research_table_is_not_projected_as_administrative_schema():
    page=PdfPage(1,600,840,())
    obj=LayoutObject("table",1,(60,100,540,300),"姓名 分类结果 工作单位 论文题目 数据分析",600,840,"table_body")
    recovered=recover_document(PdfDocument(Path("research.pdf"),(page,)),[obj])
    assert recovered.pages[0].lines==()


def test_research_chapter_prevents_whole_page_form_classification():
    doc,objects=fixture()
    heading=line(1,"第1章 实验结果",(60,40,540,60))
    first=replace(doc.pages[0],lines=(heading,))
    recovered=recover_document(replace(doc,pages=(first,doc.pages[1])),objects)
    assert not decision_form(recovered.pages[0])


def test_incomplete_decision_schema_does_not_enable_administrative_exclusion():
    page=PdfPage(1,600,840,(line(1,"姓名 论文题目 评语和决议 建议授予学位",(60,100,540,300),"table_body"),))
    assert not decision_form(page)
