from dataclasses import replace
from pathlib import Path
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules


def fixture(kind="figure",tags=(1,2,3),title=True):
    boxes=((100,100,260,220),(310,100,470,220),(205,270,365,390)) if kind=="figure" else ((100,130,500,210),(100,260,500,340),(100,390,500,470))
    textboxes=[(b[0],b[3]+5,b[2],b[3]+18) for b in boxes] if kind=="figure" else [(b[0],b[1]-18,b[2],b[1]-5) for b in boxes]
    lines=tuple(PdfLine(1,f"({tag}) Setting",box,600,840) for tag,box in zip(tags,textboxes))
    page=PdfPage(1,600,840,lines,images=boxes if kind=="figure" else (),tables=boxes if kind=="table" else ())
    objects=[LayoutObject(kind,1,b,"",600,840,"image_body" if kind=="figure" else "table_body") for b in boxes]
    if title:objects.append(LayoutObject(kind+"_caption",1,(160,420,410,440) if kind=="figure" else (120,90,480,110),"Figure 3.1 Results" if kind=="figure" else "Table 3.1 Results",600,840))
    return PdfDocument(Path("numbered-panels.pdf"),(page,)),objects


def test_numeric_figure_namespace_is_one_physical_common_title_group():
    doc,objects=fixture()
    result=detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)
    assert result["13"]["findings"]==[]


def test_stacked_numeric_table_namespace_shares_one_top_title():
    doc,objects=fixture("table")
    result=detect_caption_rules(prepare_caption_layout(objects,doc),[14],doc)
    assert result["14"]["findings"]==[]


def test_reset_numbering_cannot_absorb_untitled_figure():
    doc,objects=fixture(tags=(1,2,1))
    assert detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)["13"]["findings"]


def test_missing_numeric_panel_id_cannot_invent_complete_namespace():
    doc,objects=fixture(tags=(1,3,4))
    assert detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)["13"]["findings"]


def test_numeric_panels_without_common_caption_keep_title_obligations():
    doc,objects=fixture(title=False)
    assert len(detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)["13"]["findings"])==3


def test_unsupported_parser_rectangles_are_not_physical_panel_proof():
    doc,objects=fixture()
    doc=replace(doc,pages=(replace(doc.pages[0],images=(),tables=(),graphics=()),))
    assert detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)["13"]["findings"]


def test_an_intervening_caption_preserves_independent_figure():
    doc,objects=fixture()
    objects.append(LayoutObject("figure_caption",1,(110,240,270,255),"Figure 3.2 Independent",600,840))
    layout=prepare_caption_layout(objects,doc)
    assert len([o for o in layout if o.kind=="figure"])>=2


def test_prose_between_numeric_panels_prevents_merge():
    doc,objects=fixture("table")
    prose=PdfLine(1,"This separate experiment measures another population.",(100,222,500,242),600,840)
    doc=replace(doc,pages=(replace(doc.pages[0],lines=doc.pages[0].lines+(prose,)),))
    assert detect_caption_rules(prepare_caption_layout(objects,doc),[14],doc)["14"]["findings"]
