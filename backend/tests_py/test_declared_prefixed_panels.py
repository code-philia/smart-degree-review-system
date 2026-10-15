from pathlib import Path
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules
from pdf_rules.logical_objects import panel_label_lines


def example(shared=True):
    text='图5.5 时间线。图(a)顺序执行，图(b)并行执行。' if shared else '图5.5 并行执行时间线'
    lines=(PdfLine(1,'图(a) 顺序执行',(250,164,370,174),600,840),
           PdfLine(1,'图(b) 并行执行',(250,283,370,293),600,840))
    page=PdfPage(1,600,840,lines)
    bodies=[LayoutObject('figure',1,(89,178,518,281),'',600,840,'chart_body'),
            LayoutObject('figure',1,(88,297,518,412),'',600,840,'chart_body')]
    title=LayoutObject('figure_caption',1,(81,419,525,465),text,600,840)
    return PdfDocument(Path('declared-panels.pdf'),(page,)),bodies,title


def test_explicitly_declared_prefixed_panels_share_one_figure_title():
    doc,bodies,title=example()
    result=detect_caption_rules(prepare_caption_layout(bodies+[title],doc),[13],doc)
    assert result['13']['findings']==[]


def test_without_declared_panel_series_a_figure_word_is_not_a_subpanel_marker():
    doc,bodies,title=example(False)
    assert panel_label_lines(doc.pages[0],bodies,[title])==[]
    assert len(detect_caption_rules(prepare_caption_layout(bodies+[title],doc),[13],doc)['13']['findings'])==1


def test_independent_caption_between_declared_panels_keeps_their_ownership_separate():
    doc,bodies,title=example()
    other=LayoutObject('figure_caption',1,(150,281,450,295),'图5.4 独立的顺序执行图',600,840)
    prepared=prepare_caption_layout(bodies+[other,title],doc)
    figures=[x for x in prepared if x.kind=='figure']
    assert len(figures)==2


def test_fragmented_axis_word_and_letter_are_not_extra_subpanel_labels():
    from dataclasses import replace
    doc,bodies,title=example()
    lines=(PdfLine(1,'(a)',(291,164,311,175),600,840),
           PdfLine(1,'(b)',(291,283,311,294),600,840),
           PdfLine(1,'CPU',(91,199,110,208),600,840),
           PdfLine(1,'A',(127,199,137,208),600,840),
           PdfLine(1,'CPU',(91,336,110,345),600,840),
           PdfLine(1,'A',(127,336,137,345),600,840))
    page=replace(doc.pages[0],lines=lines)
    doc=replace(doc,pages=(page,))
    assert len(panel_label_lines(page,bodies,[title]))==2
    assert detect_caption_rules(prepare_caption_layout(bodies+[title],doc),[13],doc)['13']['findings']==[]
