from pathlib import Path
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules


def table(box=(140,95,455,730)):
    return LayoutObject('table',1,box,'',600,840,'table_body')


def run(objects,lines):
    doc=PdfDocument(Path('panel-tables.pdf'),(PdfPage(1,600,840,tuple(lines)),))
    layout=prepare_caption_layout(objects,doc)
    return detect_caption_rules(layout,[14],doc)['14']['findings']


def test_sideways_table_has_a_named_panel_title_without_number_prefix():
    lines=[PdfLine(1,'(a) 算法在多模态评估任务上的性能指标',(443,300,455,520),600,840,direction=(0,-1),font_size=10.5)]
    lines += [PdfLine(1,str(i/10),(300+i,200,308+i,225),600,840,direction=(0,-1),font_size=8) for i in range(10)]
    assert run([table()],lines)==[]


def test_data_cell_panel_label_is_not_a_title():
    lines=[PdfLine(1,'(a) 算法在多模态评估任务上的性能指标',(300,200,312,430),600,840,direction=(0,-1),font_size=8)]
    lines += [PdfLine(1,str(i/10),(300+i,200,308+i,225),600,840,direction=(0,-1),font_size=8) for i in range(10)]
    assert len(run([table()],lines))==1


def test_caption_region_cannot_absorb_first_panel_heading():
    objects=[table((170,237,410,610)),LayoutObject('table_caption',1,(139,216,447,251),'表2.9 算法性能指标对比\n(a) 准确率指标',600,840,'table_caption')]
    lines=[PdfLine(1,'表2.9 算法性能指标对比',(141,217,446,229),600,840,font_size=10.5,bold=True,block_id=2),PdfLine(1,'(a) 准确率指标',(240,237,340,249),600,840,font_size=10.5,block_id=3)]
    assert run(objects,lines)==[]
