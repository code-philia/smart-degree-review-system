"""Independent geometry, order and Unicode boundaries for parallel title repair."""
from pathlib import Path

from pdf_rules.index import build_index
from pdf_rules.model import PdfDocument, PdfLine, PdfPage
from pdf_rules.numbering import normalize_text
from pdf_rules.parallel_captions import recover_parallel_native_captions


def native_parallel_row(first='图8-7 实验装置', second='图8-8 测试装置', *, y=610):
    text=first+' '*20+second
    regions=[]
    offset=0
    for part,x0 in ((first,110),(' '*20,180),(second,320)):
        for j,char in enumerate(part):
            stop=offset+len(normalize_text(char))
            x=x0+j*5
            regions.append((offset,stop,(x,y,x+5,y+12)))
            offset=stop
    row=PdfLine(1,text,(110,y,regions[-1][2][2],y+12),600,840,
        font_size=10,text_regions=tuple(regions),block_id=1)
    return row


def document_with_row(row, *, images=((80,460,260,602),(300,460,510,602)), after=()):
    page=PdfPage(1,600,840,(row,*after),images=images)
    return PdfDocument(Path('synthetic-caption-review.pdf'),(page,))


def test_parallel_graphic_annotations_inside_images_are_not_new_main_titles():
    # These are native references printed inside two raster panels. Their
    # independently drawn main titles lie elsewhere; containment is not proof
    # that a label is a main title outside its owner.
    row=native_parallel_row(y=550)
    main=PdfLine(1,'图9-1 装置组成比较',(220,640,390,652),600,840,font_size=10)
    doc=document_with_row(row,after=(main,))
    assert recover_parallel_native_captions(doc)==doc


def test_second_title_keeps_the_original_scope_before_an_appendix_heading():
    row=native_parallel_row()
    appendix=PdfLine(1,'附录 A 补充推导',(80,710,220,725),600,840,font_size=16,bold=True)
    doc=document_with_row(row,after=(appendix,))
    index=build_index(recover_parallel_native_captions(doc))
    assert [(label.number,label.scope) for label in index.figures]==[('8.7','body'),('8.8','body')]
    assert index.appendices[0].scope=='A'


def test_second_title_ligature_offsets_keep_its_internal_citation_on_number_ink():
    row=native_parallel_row('Figure8-7 office rig','Figure8-8 ﬃ instrument (see Figure3-4)')
    # The inner reference remains ordinary title context, so it intentionally
    # prevents this narrower parallel split proof. Offsets may not create an
    # extra title out of the third reference, or suppress that inner citation.
    doc=document_with_row(row)
    recovered=recover_parallel_native_captions(doc)
    assert recovered==doc
    index=build_index(recovered)
    assert [label.number for label in index.figures]==['8.7']
    assert {label.number for label in index.graphic_figure_refs}=={'8.8','3.4'}


def test_second_title_unicode_normalization_preserves_exact_normalized_regions():
    row=native_parallel_row('Figure8-7 ﬃ rig','Figure8-8 ＦＦ instrument')
    doc=document_with_row(row)
    recovered=recover_parallel_native_captions(doc)
    second=recovered.pages[0].lines[-1]
    assert recovered.pages[0].lines[0]==row
    assert second.text=='Figure8-8 FF instrument'
    assert second.text_regions[0][0]==0
    assert second.text_regions[-1][1]==len(second.text)
    assert tuple(box for _,_,box in second.text_regions)==tuple(box for a,b,box in row.text_regions if a>=len(normalize_text('Figure8-7 ﬃ rig'))+20)
    assert second.bbox==(320,610,435,622)
    index=build_index(recovered)
    assert {label.number for label in index.figures}=={'8.7','8.8'}
    assert not index.graphic_figure_refs


def test_wide_comparison_title_keeps_the_other_figure_number_as_a_reference():
    # Two native image regions can be subpanels of one comparison figure.
    # A conjunction at the first fragment's end proves the title continues;
    # physical whitespace cannot convert its referenced Figure8-8 into a title.
    row=native_parallel_row('图8-7 原始模型与','图8-8 修正模型的结果比较')
    doc=document_with_row(row)
    recovered=recover_parallel_native_captions(doc)
    assert recovered==doc
    index=build_index(recovered)
    assert [label.number for label in index.figures]==['8.7']
    assert [label.number for label in index.graphic_figure_refs]==['8.8']
