from pathlib import Path
from pdf_rules.model import PdfDocument, PdfPage, PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.graphic_containers import recover_declared_vector_panels


def obj(box, kind="figure", text="", role="image_body"):
    return LayoutObject(kind, 1, box, text, 600, 840, role)


def fixture(frame=(100,100,500,320)):
    lines=tuple(PdfLine(1, f"node payload description {n}", (120,120+n*24,370,132+n*24),600,840) for n in range(4))
    page=PdfPage(1,600,840,lines,graphics=(frame,))
    doc=PdfDocument(Path("unplaced-vector.pdf"),(page,))
    fragments=[obj((110,170,130,185)),obj((210,170,230,185))]
    return fragments,doc


def test_valid_declared_vector_panel_is_still_recovered():
    fragments,doc=fixture()
    title=obj((140,330,460,344), "figure_caption", "Figure 4.1 Left: training. Right: inference.")
    result=recover_declared_vector_panels(fragments+[title],doc)
    assert len([o for o in result if o.role=="native_vector_panel"])==1


def test_frame_including_one_language_of_common_title_is_not_another_visual():
    fragments,doc=fixture((100,20,500,300))
    body=obj((100,100,500,270))
    chinese=obj((140,278,460,294),"figure_caption","图4.1 训练与推理流程。")
    english=obj((140,302,460,316),"figure_caption","Figure 4.1 Left: training. Right: inference.")
    existing=fragments+[body,chinese,english]
    result=recover_declared_vector_panels(existing,doc)
    assert not [o for o in result if o.role=="native_vector_panel"]
    assert body in result and chinese in result and english in result


def test_unrelated_internal_table_title_blocks_vector_parent_admission():
    fragments,doc=fixture()
    common=obj((140,330,460,344),"figure_caption","Figure 4.1 Left: training. Right: inference.")
    internal=obj((140,240,460,254),"table_caption","Table 7.2 Measurements")
    result=recover_declared_vector_panels(fragments+[common,internal],doc)
    assert not [o for o in result if o.role=="native_vector_panel"]
