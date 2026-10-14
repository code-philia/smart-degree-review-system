from pathlib import Path
import pytest
from pdf_rules.model import PdfDocument, PdfPage, PdfLine
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules


def findings(text):
    line=PdfLine(1,text,(60,100,540,112),600,800)
    doc=PdfDocument(Path('unseen.pdf'),(PdfPage(1,600,800,(line,)),))
    return detect_rules(build_index(doc),[11])['11']['findings']


@pytest.mark.parametrize('text',[
    '在混合结构图（0.2-0.7）上比较不同模型的标准差。',
    '在同质图（0.85）上统计节点分类准确率。',
    '随机图（0.15）中每条边均以该概率独立采样。',
])
def test_graph_model_parenthesized_probability_is_not_figure_id(text):
    assert findings(text)==[]


def test_graph_parameter_does_not_hide_following_missing_figure():
    result=findings('在混合结构图（0.2-0.7）上比较结果，另见图8.9。')
    assert [f['token'] for f in result]==['8.9']


@pytest.mark.parametrize('text,expected',[
    ('如图（0.2-0.4）所示。',['0.2','0.3','0.4']),
    ('参见结构图（0.2-0.4）。',['0.2','0.3','0.4']),
    ('系统结构图（4.2）展示了完整处理流程。',['4.2']),
    ('请核对图0.3。',['0.3']),
])
def test_explicit_citation_and_chapter_number_still_report(text,expected):
    assert [f['token'] for f in findings(text)]==expected
