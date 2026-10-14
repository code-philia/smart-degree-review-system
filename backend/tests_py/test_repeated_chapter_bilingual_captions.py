"""Bilingual physical identity does not create a phantom duplicate chapter ID."""
from pathlib import Path
from dataclasses import replace
import pytest
from pdf_rules.model import PdfDocument, PdfPage, PdfLine
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules


def doc(kind="figure", ref=None, english="2–2.3", chinese="2.3", EnglishPage=1, EnglishX=80):
    zh="图" if kind=="figure" else "表"
    en="Figure" if kind=="figure" else "Table"
    lines=[PdfLine(1,f"{zh}{chinese} 多条件实验结果",(100,300,500,312),600,800,font_size=10.5,bold=True),
           PdfLine(EnglishPage,f"{en} {english} Results across conditions",(EnglishX,319,EnglishX+400,331),600,800,font_size=10.5,bold=True)]
    if ref:lines.insert(0,PdfLine(1,ref,(80,100,520,115),600,800,font_size=12))
    pages=tuple(PdfPage(n,600,800,tuple(l for l in lines if l.page_number==n)) for n in sorted({l.page_number for l in lines}))
    return PdfDocument(Path("fixture.pdf"),pages)


@pytest.mark.parametrize("kind,rule,zh",[("figure",15,"图"),("table",16,"表")])
def test_reference_to_chinese_number_covers_its_adjacent_duplicate_chapter_translation(kind,rule,zh):
    result=detect_rules(build_index(doc(kind,ref=f"结果如{zh}2.3所示。")),[rule])
    assert result[str(rule)]["findings"]==[]


@pytest.mark.parametrize("kind,rule",[("figure",15),("table",16)])
def test_a_genuinely_unreferenced_bilingual_object_keeps_one_alarm_and_both_boxes(kind,rule):
    found=detect_rules(build_index(doc(kind)),[rule])[str(rule)]["findings"]
    assert len(found)==1
    assert found[0]["token"]=="2.3"
    assert len(found[0]["location"]["rects"])==2
    assert "2–2.3" in found[0]["text_excerpt"]


def test_reference_to_the_printed_english_alias_covers_same_physical_object():
    assert detect_rules(build_index(doc(ref="As shown in Figure 2-2.3, results improve.")),[15])["15"]["findings"]==[]


@pytest.mark.parametrize("english",["2.2.3","3-2.3","2-2.4","2-3.3"])
def test_a_legitimate_three_component_or_different_number_is_not_an_alias(english):
    found=detect_rules(build_index(doc(ref="结果如图2.3所示。",english=english)),[15])["15"]["findings"]
    assert len(found)==1
    assert found[0]["token"]==english.replace("-",".")


def test_different_pages_do_not_share_bilingual_identity():
    assert len(detect_rules(build_index(doc(ref="如图2.3所示。",EnglishPage=2)),[15])["15"]["findings"])==1


def test_parallel_distinct_objects_do_not_share_an_alias():
    d=doc(ref="如图2.3所示。")
    a,b,c=d.pages[0].lines
    d=PdfDocument(d.path,(replace(d.pages[0],lines=(a,replace(b,bbox=(50,300,240,312)),replace(c,bbox=(350,319,550,331)))),))
    assert len(detect_rules(build_index(d),[15])["15"]["findings"])==1


def test_unpaired_english_duplicate_chapter_number_keeps_its_original_identity():
    d=doc()
    d=PdfDocument(d.path,(replace(d.pages[0],lines=(d.pages[0].lines[1],)),))
    found=detect_rules(build_index(d),[15])["15"]["findings"]
    assert len(found)==1 and found[0]["token"]=="2.2.3"


def test_an_independent_native_visual_between_the_titles_is_a_hard_boundary():
    d=doc(ref="正文如图2.3所示。")
    p=d.pages[0];a,b,c=p.lines
    c=replace(c,text="Figure 2-2.3 Independent waveform",bbox=(100,331,500,343))
    p=replace(p,lines=(a,b,c),images=((80,210,520,290),(80,313,520,329)))
    found=detect_rules(build_index(PdfDocument(d.path,(p,))),[15])["15"]["findings"]
    assert len(found)==1 and found[0]["token"]=="2.2.3"


def test_parser_typography_alone_cannot_establish_a_different_number_alias():
    d=doc(ref="如图2.3所示。")
    p=replace(d.pages[0],lines=tuple(replace(l,source="mineru") for l in d.pages[0].lines))
    assert len(detect_rules(build_index(PdfDocument(d.path,(p,))),[15])["15"]["findings"])==1


def test_a_background_canvas_is_not_an_intervening_independent_visual():
    d=doc(ref="如图2.3所示。")
    p=replace(d.pages[0],images=((0,0,600,800),(80,220,520,290)))
    assert detect_rules(build_index(PdfDocument(d.path,(p,))),[15])["15"]["findings"]==[]
