"""Typed algorithm headings own numbered instructions in any body language."""
from pathlib import Path
from dataclasses import replace
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.object_identity import refine_targets


def fixture(numbers=(1,2,3,4,5),separate=False,bold=True,heading=True,numeric=False,peers=False):
    lines=[]
    if heading:lines.append(PdfLine(1,'算法 2.4 多尺度状态更新',(80,82,480,98),600,840,bold=bold))
    for row,n in enumerate(numbers):
        y=118+row*24
        text=('64 128 0.91' if numeric else ['施加外力','预测粒子位置','搜索邻域粒子','更新位置与速度','计算边界状态'][row%5])
        if separate:
            lines.extend([PdfLine(1,f'{n}:',(90,y,104,y+14),600,840),PdfLine(1,text,(124,y,420,y+14),600,840)])
        else:lines.append(PdfLine(1,f'{n}: {text}',(90,y,420,y+14),600,840))
        if peers:lines.append(PdfLine(1,'0.91',(455,y,493,y+14),600,840))
    obj=LayoutObject('table',1,(80,100,520,260),'',600,840,'table_body')
    doc=PdfDocument(Path('numbered-language-algorithm.pdf'),(PdfPage(1,600,840,tuple(lines)),))
    return [obj],doc


def tables(objects,document):return [o for o in refine_targets(objects,document) if o.kind=='table']


def test_natural_language_numbered_instructions_under_bold_algorithm_title_are_not_a_table():
    objects,doc=fixture()
    assert tables(objects,doc)==[]


def test_separate_number_column_preserves_the_same_instruction_namespace():
    objects,doc=fixture(separate=True)
    assert tables(objects,doc)==[]


def test_ordinary_numbered_prose_without_algorithm_title_retains_its_table_obligation():
    objects,doc=fixture(heading=False)
    assert len(tables(objects,doc))==1


def test_plain_algorithm_mention_cannot_replace_a_typed_heading():
    objects,doc=fixture(bold=False)
    assert len(tables(objects,doc))==1


def test_numeric_measurement_rows_are_not_instruction_steps():
    objects,doc=fixture(numeric=True)
    assert len(tables(objects,doc))==1


def test_restart_of_row_numbers_is_not_one_algorithm_namespace():
    objects,doc=fixture(numbers=(1,2,1,2))
    assert len(tables(objects,doc))==1


def test_gapped_data_indices_cannot_prove_a_complete_instruction_namespace():
    objects,doc=fixture(numbers=(1,2,4,5))
    assert len(tables(objects,doc))==1


def test_parameter_cells_beside_the_rows_retain_a_research_table():
    objects,doc=fixture(peers=True)
    assert len(tables(objects,doc))==1


def test_a_table_with_its_own_numbered_title_retains_its_table_identity():
    objects,doc=fixture()
    objects.append(LayoutObject('table_caption',1,(180,84,500,98),'表 3.1 测量结果',600,840,'table_caption'))
    assert len(tables(objects,doc))==1


def configuration_fixture(separate=False, instructions=False):
    lines=[PdfLine(1,'Algorithm 2.4 Parameter configuration',(80,82,480,98),600,840,bold=True)]
    names=['learning_rate 0.01','batch_size 64','optimizer Adam']
    if instructions:names=['Set learning_rate to 0.01','Initialize a batch of 64 samples','Train with the Adam optimizer']
    for i,text in enumerate(names):
        y=118+i*24
        if separate:
            lines.extend([PdfLine(1,f'{i+1}:',(90,y,104,y+14),600,840),PdfLine(1,text,(124,y,420,y+14),600,840)])
        else:lines.append(PdfLine(1,f'{i+1}: {text}',(90,y,420,y+14),600,840))
    obj=LayoutObject('table',1,(80,100,520,220),'',600,840,'table_body')
    return [obj],PdfDocument(Path('ordered-parameter-frame.pdf'),(PdfPage(1,600,840,tuple(lines)),))


def test_flattened_parameter_name_value_rows_are_not_instructions():
    objects,doc=configuration_fixture()
    assert len(tables(objects,doc))==1


def test_parameter_names_values_with_separate_index_column_remain_a_table():
    objects,doc=configuration_fixture(separate=True)
    assert len(tables(objects,doc))==1


def test_real_parameter_setting_actions_still_form_an_algorithm():
    objects,doc=configuration_fixture(instructions=True)
    assert tables(objects,doc)==[]


def test_human_readable_parameter_names_remain_data_not_steps():
    objects,doc=configuration_fixture()
    names=['1: Learning rate 0.01','2: Batch size 64','3: Optimizer Adam']
    page=doc.pages[0]
    lines=[page.lines[0]]+[replace(line,text=text) for line,text in zip(page.lines[1:],names)]
    doc=replace(doc,pages=(replace(page,lines=tuple(lines)),))
    assert len(tables(objects,doc))==1


def test_joined_numeric_result_fields_remain_a_research_table():
    objects,doc=configuration_fixture()
    names=['1: Dataset A 64 0.91','2: Dataset B 128 0.93','3: Dataset C 256 0.95']
    page=doc.pages[0]
    lines=[page.lines[0]]+[replace(line,text=text) for line,text in zip(page.lines[1:],names)]
    doc=replace(doc,pages=(replace(page,lines=tuple(lines)),))
    assert len(tables(objects,doc))==1


def test_short_literal_setting_actions_are_not_static_data_records():
    objects,doc=configuration_fixture()
    names=['1: Initialize counter 0','2: Set learning_rate 0.01','3: Select optimizer Adam']
    page=doc.pages[0]
    lines=[page.lines[0]]+[replace(line,text=text) for line,text in zip(page.lines[1:],names)]
    doc=replace(doc,pages=(replace(page,lines=tuple(lines)),))
    assert tables(objects,doc)==[]
