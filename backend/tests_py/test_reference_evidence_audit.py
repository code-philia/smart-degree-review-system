from pathlib import Path
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules
from pdf_rules.text_fragments import merge_reference_fragments
from pdf_rules.mineru_layout import LayoutObject

def line(text,box):return PdfLine(1,text,box,600,840)
def run(lines,layout=()):
 doc=PdfDocument(Path('reference-evidence.pdf'),(PdfPage(1,600,840,tuple(lines)),))
 return detect_rules(build_index(doc,layout),[11,15,16])

def test_table_word_can_soft_wrap_between_its_two_chinese_characters():
 ls=[line('这是流程中计算量最小的环节。表',(70,100,520,113)),line('格3.1具体列出了各模块参数量。',(70,121,490,134)),line('表3.1 模块参数量',(190,260,410,273))]
 assert run(merge_reference_fragments(ls))['16']['findings']==[]

def test_quote_from_a_local_table_is_still_a_table_reference():
 ls=[line('使用提示词（摘自表3.3）：',(70,100,450,113)),line('表3.3 提示词内容',(190,260,410,273))]
 assert run(ls)['16']['findings']==[]

def test_external_paper_provenance_does_not_create_local_missing_target():
 ls=[line('示意图引自文献[12]中的图3.3。',(70,100,510,113))]
 assert run(ls)['11']['findings']==[]

def test_explicit_citation_inside_another_figure_counts_as_usage_but_not_rule11_body_alarm():
 layout=[LayoutObject('figure',1,(70,100,520,270),'',600,840,'image_body')]
 ls=[line('各分量关系同图3.1所述。',(100,180,390,193)),
     line('图3.2 理想函数',(190,290,410,303)),line('图3.1 域与重构',(190,450,410,463))]
 result=run(ls,layout)
 assert '3.1' not in [f['token'] for f in result['15']['findings']]
 assert result['11']['findings']==[]

def test_plain_diagram_label_is_not_usage_of_another_figure():
 layout=[LayoutObject('figure',1,(70,100,520,270),'',600,840,'image_body')]
 ls=[line('图3.1',(100,180,180,193)),line('图3.2 理想函数',(190,290,410,303)),line('图3.1 域与重构',(190,450,410,463))]
 assert '3.1' in [f['token'] for f in run(ls,layout)['15']['findings']]


def test_long_caption_explanation_is_not_rule11_body_text():
 from dataclasses import replace
 ls=[replace(line('图4.1 两阶段图形模型',(70,310,510,321)),font_size=10.5),replace(line('在训练阶段（图1(a)），测试阶段（图1(b)）。',(70,410,510,422)),font_size=10.5),replace(line('正文中的图8.8目标不存在。',(94,498,510,511)),font_size=12)]
 layout=[LayoutObject('figure_caption',1,(67,307,512,453),'图4.1 两阶段图形模型',600,840)]
 assert [f['token'] for f in run(ls,layout)['11']['findings']]==['8.8']

def test_oversized_cloud_caption_cannot_hide_body_with_different_font():
 from dataclasses import replace
 ls=[replace(line('图4.1 两阶段图形模型',(70,310,510,321)),font_size=10.5),replace(line('正文中的图8.8目标不存在。',(94,498,510,511)),font_size=12)]
 layout=[LayoutObject('figure_caption',1,(67,307,512,530),'图4.1 两阶段图形模型',600,840)]
 assert [f['token'] for f in run(ls,layout)['11']['findings']]==['8.8']

def test_other_object_referenced_in_long_caption_still_counts_as_usage():
 from dataclasses import replace
 ls=[replace(line('图4.1 两阶段图形模型',(70,310,510,321)),font_size=10.5),replace(line('可与图3.2所示方法进行对比。',(70,410,510,422)),font_size=10.5),line('图3.2 原有方法',(190,600,410,613))]
 layout=[LayoutObject('figure_caption',1,(67,307,512,453),'图4.1 两阶段图形模型',600,840)]
 assert '3.2' not in [f['token'] for f in run(ls,layout)['15']['findings']]


def test_sentence_ending_deictic_resolves_only_the_one_figure_in_the_same_section():
    from pathlib import Path
    from pdf_rules.model import PdfDocument,PdfPage,PdfLine
    from pdf_rules.index import build_index
    from pdf_rules.local_rules import detect_rules
    caption=PdfLine(1,'图2.4 融合结构',(160,300,440,315),600,840)
    prose=PdfLine(1,'本文的融合结构如图。',(80,400,500,415),600,840)
    doc=PdfDocument(Path('deictic.pdf'),(PdfPage(1,600,840,(caption,prose)),))
    assert detect_rules(build_index(doc),[15])['15']['findings']==[]


def test_the_word_image_is_not_a_sentence_ending_deictic():
    from pathlib import Path
    from pdf_rules.model import PdfDocument,PdfPage,PdfLine
    from pdf_rules.index import build_index
    from pdf_rules.local_rules import detect_rules
    caption=PdfLine(1,'图2.4 融合结构',(160,300,440,315),600,840)
    prose=PdfLine(1,'例如图像分类方法采用融合结构。',(80,400,500,415),600,840)
    doc=PdfDocument(Path('deictic.pdf'),(PdfPage(1,600,840,(caption,prose)),))
    assert detect_rules(build_index(doc),[15])['15']['findings']


def floated_software_table(duplicate=False):
    p1=PdfPage(1,600,840,(PdfLine(1,'服务器的操作系统与软件栈如下。',(80,650,520,664),600,840),
                         PdfLine(1,'后续实验使用相同的训练方案。',(80,700,520,714),600,840)))
    titles=[PdfLine(2,'表3.1 软件环境',(170,100,430,115),600,840)]
    objects=[LayoutObject('table',2,(80,130,520,260),'操作系统 语言版本 深度学习框架 Python PyTorch',600,840,'table_body')]
    if duplicate:
        titles.append(PdfLine(2,'表3.2 备用环境',(170,400,430,415),600,840))
        objects.append(LayoutObject('table',2,(80,430,520,560),'操作系统 语言版本 深度学习框架 Python PyTorch',600,840,'table_body'))
    return PdfDocument(Path('floated.pdf'),(p1,PdfPage(2,600,840,tuple(titles)))),objects


def test_cross_page_here_are_statement_requires_unique_matching_table_header():
    doc,objects=floated_software_table()
    assert detect_rules(build_index(doc,objects),[16])['16']['findings']==[]


def test_two_matching_floated_tables_cannot_be_silently_resolved_by_proximity():
    doc,objects=floated_software_table(True)
    assert len(detect_rules(build_index(doc,objects),[16])['16']['findings'])==2


def test_float_header_reference_cannot_take_the_next_tables_title():
    from dataclasses import replace
    doc,objects=floated_software_table()
    page=doc.pages[1]
    second_title=PdfLine(2,'表3.2 存储性能',(170,275,430,289),600,840)
    doc=replace(doc,pages=(doc.pages[0],replace(page,lines=page.lines+(second_title,))))
    objects.append(LayoutObject('table',2,(80,300,520,430),'存储设备 IOPS 随机读',600,840,'table_body'))
    found=detect_rules(build_index(doc,objects),[16])['16']['findings']
    assert [f['token'] for f in found]==['3.2']


def test_defined_graph_symbol_in_algorithm_input_is_not_a_figure_id():
    lines=[line('设初始攻击图为G0=(V0,E0)，其中V0为节点集合。',(70,70,530,85)),
           line('Input: 初始攻击图G0，日志数据库D。',(70,200,530,215))]
    assert run(lines)['11']['findings']==[]


def test_explicit_figure_citation_survives_a_graph_symbol_with_the_same_name():
    lines=[line('设初始攻击图为G0=(V0,E0)，其中V0为节点集合。',(70,70,530,85)),
           line('攻击图的实验结果如图G0所示。',(70,200,530,215))]
    assert [f['token'] for f in run(lines)['11']['findings']]==['G0']


def test_an_undefined_letter_prefixed_figure_reference_is_still_checked():
    assert [f['token'] for f in run([line('攻击图G0所示。',(70,200,530,215))])['11']['findings']]==['G0']


def test_nonbreaking_hyphen_keeps_the_full_chapter_object_number():
    lines=[line('正文如图4‑3所示。',(80,100,510,114)),line('图4-3 实验结果',(170,260,430,274))]
    result=run(lines)
    assert result['11']['findings']==[]
    assert result['15']['findings']==[]


def test_wrapped_graph_definition_retains_its_vertex_edge_tuple():
    lines=[line('本节设初始攻击图为G0 =',(70,70,530,85)),
           line('(V0,E0)，其中V0为节点集合。',(70,92,530,107)),
           line('Input: 初始攻击图G0，日志数据库D。',(70,200,530,215))]
    assert run(lines)['11']['findings']==[]
