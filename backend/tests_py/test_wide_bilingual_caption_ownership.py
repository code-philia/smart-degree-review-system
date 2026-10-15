"""Long, styled bilingual titles can describe what a visual shows."""
from pathlib import Path
from dataclasses import replace
import pytest
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.index import build_index
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules
from pdf_rules.local_rules import detect_rules


def line(text,y,*,font=10.5,bold=True,block=1):
    return PdfLine(1,text,(80,y,520,y+12),600,800,font_size=font,bold=bold,block_id=block)


def document(kind="figure",*,bold=True,english_number="4.4",caption_font=10.5):
    zh,en=("图","Figure") if kind=="figure" else ("表","Table")
    body=(line("正文描述实验条件和评测安排，使用相同的参数进行评估。",110,font=12,bold=False,block=0),
          line("本文首先对不同方法的效果进行比较，然后讨论消融结果。",130,font=12,bold=False,block=0))
    cn=(line(f"{zh}4.4 展示不同任务的可视化结果，比较模型在各个场景中的表现。",420,bold=bold,font=caption_font),
        line("从左至右依次为输入、真实结果和所提方法，颜色表示不同类别。",436,bold=bold,font=caption_font))
    enline=line(f"{en} {english_number} Results across several conditions.",455,block=2)
    visual=(80,225,520,403)
    page=PdfPage(1,600,800,body+cn+(enline,),images=(visual,) if kind=="figure" else (),tables=(visual,) if kind=="table" else ())
    return PdfDocument(Path("fixture.pdf"),(page,))


@pytest.mark.parametrize("kind,rule",[("figure",13),("table",14)])
def test_full_width_bilingual_narrative_title_owns_its_actual_visual(kind,rule):
    d=document(kind);layout=prepare_caption_layout([],d)
    assert detect_caption_rules(layout,[rule])[str(rule)]["findings"]==[]
    found=detect_rules(build_index(d),[15 if kind=="figure" else 16])
    uncited=found["15" if kind=="figure" else "16"]["findings"]
    assert len(uncited)==1
    assert len(uncited[0]["location"]["rects"])==2


def test_styled_title_does_not_create_a_phantom_body_reference():
    idx=build_index(document())
    assert idx.figure_refs==[]


@pytest.mark.parametrize("bold,font,number",[(False,12,"4.4"),(True,10.5,"4.5")])
def test_body_prose_or_different_number_translation_does_not_create_a_caption_alias(bold,font,number):
    d=document(bold=bold,caption_font=font,english_number=number)
    idx=build_index(d)
    assert len(idx.figure_refs)==1
    assert len(idx.figures)==1


def test_body_reference_below_real_bilingual_title_remains_a_reference():
    d=document();p=d.pages[0]
    p=replace(p,lines=p.lines+(line("图4.4 展示了各场景的细粒度对比，可以看到本方法的优势。",510,font=12,bold=False,block=4),))
    idx=build_index(PdfDocument(d.path,(p,)))
    assert len(idx.figure_refs)==1
    assert detect_rules(idx,[15])["15"]["findings"]==[]


@pytest.mark.parametrize("kind,rule,uncited_rule",[("figure",13,15),("table",14,16)])
def test_both_languages_can_be_full_descriptive_sentences_without_self_citation(kind,rule,uncited_rule):
    d=document(kind);p=d.pages[0];word="Figure" if kind=="figure" else "Table"
    lines=p.lines[:-1]+(replace(p.lines[-1],text=f"{word} 4.4 shows the results across several conditions."),)
    d=PdfDocument(d.path,(replace(p,lines=lines),))
    assert detect_caption_rules(prepare_caption_layout([],d),[rule])[str(rule)]["findings"]==[]
    idx=build_index(d)
    assert (idx.figure_refs if kind=="figure" else idx.table_refs)==[]
    found=detect_rules(idx,[uncited_rule])[str(uncited_rule)]["findings"]
    assert len(found)==1 and len(found[0]["location"]["rects"])==2
