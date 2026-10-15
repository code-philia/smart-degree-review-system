from pathlib import Path
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules


def test_continued_table_label_after_number_is_a_title_even_without_space():
    line=PdfLine(1,'表6.1（续）软件依赖版本',(150,100,450,114),600,840,font_size=10.5,bold=True)
    page=PdfPage(1,600,840,(line,),tables=((80,120,520,700),))
    doc=PdfDocument(Path('continued.pdf'),(page,))
    obj=LayoutObject('table',1,(80,120,520,700),'软件名称 版本 功能',600,840,'table_body')
    assert detect_caption_rules(prepare_caption_layout([obj],doc),[14],doc)['14']['findings']==[]


def test_parser_caption_including_subpanel_row_cannot_overlap_the_real_table_body():
    lines=(PdfLine(1,'表4.1 多任务比较',(160,310,440,323),600,840,font_size=10.5,bold=True),
           PdfLine(1,'Table 4.1 Overall comparison',(130,330,470,343),600,840,font_size=10.5,bold=True),
           PdfLine(1,'((a)) 第一任务',(230,348,370,361),600,840,font_size=10.5,bold=False),
           PdfLine(1,'((b)) 第二任务',(230,530,370,543),600,840,font_size=10.5,bold=False))
    page=PdfPage(1,600,840,lines)
    doc=PdfDocument(Path('two-tasks.pdf'),(page,))
    objects=[LayoutObject('table',1,(80,348,520,705),'指标 准确率 F1',600,840,'table_body'),
             LayoutObject('table_caption',1,(130,310,470,362),'表4.1 多任务比较 Table 4.1 Overall comparison ((a)) 第一任务',600,840,'table_caption')]
    assert detect_caption_rules(prepare_caption_layout(objects,doc),[14],doc)['14']['findings']==[]


def test_an_untitled_independent_table_below_another_titled_table_stays_a_violation():
    lines=(PdfLine(1,'表4.1 第一任务',(160,310,440,323),600,840,font_size=10.5,bold=True),)
    page=PdfPage(1,600,840,lines)
    doc=PdfDocument(Path('separate-tables.pdf'),(page,))
    objects=[LayoutObject('table',1,(80,345,520,450),'第一任务',600,840,'table_body'),
             LayoutObject('table',1,(80,600,520,705),'第二任务',600,840,'table_body')]
    assert len(detect_caption_rules(prepare_caption_layout(objects,doc),[14],doc)['14']['findings'])==1
