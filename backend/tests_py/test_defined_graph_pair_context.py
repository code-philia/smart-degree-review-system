from pathlib import Path
import pytest
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules


def check(definitions,uses):
    texts=definitions+uses
    lines=tuple(PdfLine(1,t,(80,100+i*25,520,115+i*25),600,840) for i,t in enumerate(texts))
    doc=PdfDocument(Path('graph-variables.pdf'),(PdfPage(1,600,840,lines),))
    return detect_rules(build_index(doc),[11])['11']['findings']


@pytest.mark.parametrize('use',[
    '对于图G1 中连接节点i与j的边c，计算边特征。',
    '同理，图G2 中连接节点p与q的边特征为。',
    '节点特征h1属于图G1 的节点i。',
    '图G1, G2 的节点和边特征作为模型输入。',
    '源图G1 与目标图G2 的节点一一对应。',
])
def test_paired_vertex_edge_definitions_establish_both_graph_variables(use):
    assert check(['给定两个图G1=(V1,E1)与G2=(V2,E2)，其中V表示节点，E表示边。'],[use])==[]


def test_wrapped_paired_graph_definition_preserves_second_variable():
    assert check(['形式化地，给定两个图G1 =','(V1,E1) 与G2 = (V2,E2)，其中V表示节点集合。'],['图G2 的边特征为向量。'])==[]


@pytest.mark.parametrize('use',['参见图G1。','如图G2所示。','图G1展示了节点匹配结果。'])
def test_explicit_illustration_use_is_kept_even_with_defined_graph_names(use):
    assert len(check(['给定两个图G1=(V1,E1)与G2=(V2,E2)。'],[use]))==1


def test_undefined_graph_variable_cannot_bypass_missing_figure_check():
    assert len(check([],['图G2中的节点表示实验结果。']))==1


def test_an_unrelated_tuple_does_not_declare_a_graph():
    assert len(check(['设置参数Q2=(A2,B2)。'],['图Q2中的节点表示实验结果。']))==1


def test_pair_membership_remains_a_mathematical_graph_use():
    assert check(['给定两个图G1=(V1,E1)与G2=(V2,E2)。'],['候选匹配对(i,a)，其中i属于图G1，a属于图G2。'])==[]
