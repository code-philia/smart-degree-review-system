from pathlib import Path
from pdf_rules.model import PdfPage, PdfDocument
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout


def figure(box):
    return LayoutObject('figure', 1, box, '', 600, 840, 'image_body')


def caption(box, number='6.4'):
    return LayoutObject('figure_caption', 1, box, '图 '+number+' 推理能力的定性比较', 600, 840, 'image_caption')


def run(objects, graphics):
    doc=PdfDocument(Path('physical-frame.pdf'), (PdfPage(1,600,840,(),graphics=tuple(graphics)),))
    return [x for x in prepare_caption_layout(objects,doc) if x.kind=='figure']


def test_one_physical_graphic_frame_recovers_video_and_response_pieces():
    parts=[figure((88,119,520,169)),figure((88,174,520,584))]
    result=run(parts+[caption((216,591,391,605))],[(85,99,524,586)])
    assert len(result)==1
    assert result[0].bbox==(85,99,524,586)
    assert len(result[0].panel_boxes)==2


def test_nearby_pieces_without_physical_frame_are_not_merged():
    parts=[figure((88,119,520,169)),figure((88,174,520,584))]
    assert len(run(parts+[caption((216,591,391,605))],[]))==2


def test_independent_internal_caption_prevents_frame_merging():
    parts=[figure((88,119,520,169)),figure((88,210,520,584))]
    titles=[caption((216,175,391,189),'6.3'),caption((216,591,391,605))]
    assert len(run(parts+titles,[(85,99,524,586)]))==2


def test_page_background_does_not_group_independent_figures():
    parts=[figure((88,119,520,169)),figure((88,174,520,584))]
    assert len(run(parts+[caption((216,591,391,605))],[(0,0,600,840)]))==2


def test_badge_inside_one_original_bitmap_is_not_an_independent_picture():
    parts=[figure((85,145,545,300)),figure((88,118,113,143)),caption((207,306,401,335),'5.1')]
    doc=PdfDocument(Path('bitmap.pdf'),(PdfPage(1,600,840,(),images=((85,119,545,300),)),))
    result=[x for x in prepare_caption_layout(parts,doc) if x.kind=='figure']
    assert len(result)==1


def test_distinct_internal_numbered_caption_preserves_bitmap_child_identity():
    parts=[figure((85,145,545,300)),figure((88,118,140,160)),caption((90,165,160,179),'5.2'),caption((207,306,401,335),'5.1')]
    doc=PdfDocument(Path('bitmap.pdf'),(PdfPage(1,600,840,(),images=((85,119,545,300),)),))
    result=[x for x in prepare_caption_layout(parts,doc) if x.kind=='figure']
    assert len(result)>=2


def test_explicit_roman_subpanel_series_groups_stacked_heatmaps():
    from pdf_rules.model import PdfLine
    parts=[figure((105,99,502,392)),figure((105,401,502,546)),LayoutObject('figure_caption',1,(81,565,526,595),'图4.3 注意力模式：(i) 原始；(ii) 压缩。',600,840)]
    lines=[PdfLine(1,'(i)',(290,393,305,400),600,840),PdfLine(1,'(ii)',(288,548,307,558),600,840)]
    doc=PdfDocument(Path('roman.pdf'),(PdfPage(1,600,840,tuple(lines)),))
    assert len([x for x in prepare_caption_layout(parts,doc) if x.kind=='figure'])==1


def test_explicit_left_right_composite_recovers_vector_text_panel():
    from pdf_rules.model import PdfLine
    bars=[(75,y,149,y+7) for y in (129,141,160,179,198)]
    parts=[figure((384,96,512,248)),LayoutObject('figure_caption',1,(67,253,511,310),'图5.1 左图：思考过程；右图：模型冗余率。',600,840)]
    lines=[PdfLine(1,'This is a step in a reasoning process.',(80,y,370,y+10),600,840,font_size=8) for y in (129,150,175,200)]
    doc=PdfDocument(Path('reasoning.pdf'),(PdfPage(1,600,840,tuple(lines),images=tuple(bars),graphics=((73,124,383,233),)),))
    assert len([x for x in prepare_caption_layout(parts,doc) if x.kind=='figure'])==1
