"""Native rectangular Form clipping owns its graphic parts, never nearby objects."""
from pathlib import Path
from dataclasses import replace
import pymupdf
from pdf_rules.model import PdfDocument, PdfPage
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.graphic_containers import merge_physical_graphic_containers
from pdf_rules.layout_context import prepare_caption_layout


def object_(box,kind="figure",role="chart_body",text=""):
    return LayoutObject(kind,1,box,text,600,840,role)


def source_pdf(tmp_path,frames=((100,100,500,320),)):
    with pymupdf.open() as source,pymupdf.open() as output:
        panel=source.new_page(width=400,height=220)
        for box in ((10,70,190,210),(210,70,390,210),(20,0,380,45)):
            panel.draw_rect(box,color=(0,0,0))
        page=output.new_page(width=600,height=840)
        for frame in frames:page.show_pdf_page(pymupdf.Rect(frame),source,0,keep_proportion=False)
        path=tmp_path/"physical-forms.pdf";output.save(path)
    return PdfDocument(path,(PdfPage(1,600,840,()),))


def members():
    return [object_((110,170,290,310)),object_((310,170,490,310)),
            object_((120,101,480,145),"table","table_body","Model A Model B Model C")]


def title(box=(170,331,430,345),kind="figure_caption",text="Figure 7.1 Comparison"):
    return object_(box,kind,kind,text)


def test_original_form_unifies_chart_and_table_shaped_legend(tmp_path):
    doc=source_pdf(tmp_path)
    result=merge_physical_graphic_containers(members(),[title()],doc)
    assert len(result)==1
    assert result[0].kind=="figure"
    assert len(result[0].panel_boxes)==3


def test_prepared_layout_retains_no_separate_legend_table(tmp_path):
    doc=source_pdf(tmp_path)
    result=prepare_caption_layout(members()+[title()],doc)
    assert not [x for x in result if x.kind=="table"]
    assert len([x for x in result if x.kind=="figure"])==1


def test_proximity_without_source_clipping_cannot_absorb_table():
    doc=PdfDocument(Path("unplaced.pdf"),(PdfPage(1,600,840,()),))
    result=merge_physical_graphic_containers(members(),[title()],doc)
    assert any(x.kind=="table" for x in result)


def test_internal_numbered_table_title_preserves_independent_identity(tmp_path):
    doc=source_pdf(tmp_path)
    titles=[title(),title((150,149,440,163),"table_caption","Table 7.2 Data")]
    result=merge_physical_graphic_containers(members(),titles,doc)
    assert any(x.kind=="table" for x in result)


def test_untitled_form_does_not_arbitrarily_reclassify_legend(tmp_path):
    doc=source_pdf(tmp_path)
    result=merge_physical_graphic_containers(members(),[],doc)
    assert any(x.kind=="table" for x in result)


def test_unrelated_outside_picture_is_preserved(tmp_path):
    doc=source_pdf(tmp_path)
    outside=object_((20,400,150,480))
    result=merge_physical_graphic_containers(members()+[outside],[title()],doc)
    assert outside in result
    assert len(result)==2


def test_original_forms_with_separate_titles_do_not_merge_across_invocations(tmp_path):
    doc=source_pdf(tmp_path,((100,100,500,320),(100,420,500,640)))
    lower=[replace(x,bbox=(x.bbox[0],x.bbox[1]+320,x.bbox[2],x.bbox[3]+320)) for x in members()]
    result=merge_physical_graphic_containers(members()+lower,
        [title(),title((170,651,430,665),text="Figure 7.2 Another comparison")],doc)
    assert len(result)==2
    assert all(x.kind=="figure" for x in result)


def test_page_canvas_cannot_absorb_independent_graphics(tmp_path):
    doc=source_pdf(tmp_path,((0,0,600,840),))
    result=merge_physical_graphic_containers(members(),[title()],doc)
    assert any(x.kind=="table" for x in result)
