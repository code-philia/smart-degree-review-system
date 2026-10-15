from dataclasses import replace
from pathlib import Path
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules


def run(text="下表列出了各模型的参数规模。",kind="table",extra=False,heading=False,layout=True):
    prefix="表" if kind=="table" else "图"
    one=PdfPage(1,600,840,(PdfLine(1,text,(80,350,520,365),600,840),))
    lines=[PdfLine(2,prefix+"5.1 模型参数规模",(170,100,430,115),600,840)]
    objects=[LayoutObject(kind,2,(80,130,520,330),"",600,840,kind+"_body")]
    if extra:
        lines.append(PdfLine(2,prefix+"5.2 第二组模型参数规模",(170,400,430,415),600,840))
        objects.append(LayoutObject(kind,2,(80,430,520,600),"",600,840,kind+"_body"))
    if heading:lines.append(PdfLine(2,"第5章 另一项研究",(80,80,520,95),600,840,bold=True))
    doc=PdfDocument(Path("deictic.pdf"),(one,PdfPage(2,600,840,tuple(lines))))
    return detect_rules(build_index(doc,objects if layout else []),[15 if kind=="figure" else 16])


def test_next_table_subject_verb_is_an_explicit_cross_page_reference():
    assert run()["16"]["findings"]==[]


def test_next_figure_subject_verb_is_an_explicit_cross_page_reference():
    assert run("下图展示了模型结构。","figure")["15"]["findings"]==[]


def test_surface_term_is_not_a_table_deictic():
    assert run("下表面显示了涂层的厚度。")["16"]["findings"]


def test_image_layer_term_is_not_a_figure_deictic():
    assert run("下图层展示了不同类型的特征。","figure")["15"]["findings"]


def test_two_nearby_tables_are_not_arbitrarily_selected():
    assert len(run(extra=True)["16"]["findings"])==2


def test_a_real_section_boundary_prevents_borrowing_the_next_table():
    assert run(heading=True)["16"]["findings"]


def test_long_cross_page_distance_without_physical_body_cannot_resolve_reference():
    assert run(layout=False)["16"]["findings"]
