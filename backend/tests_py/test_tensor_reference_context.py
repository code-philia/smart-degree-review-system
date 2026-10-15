from pathlib import Path
import pytest
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules


def check(text):
    line=PdfLine(1,text,(85,180,525,194),600,840)
    return detect_rules(build_index(PdfDocument(Path('tensor.pdf'),(PdfPage(1,600,840,(line,)),))),[11])['11']['findings']


@pytest.mark.parametrize('text',['卷积层的输入为初始特征图𝑓1与卷积核φ1。','通过加权得到响应图R2，并继续执行卷积。','多头注意力图A3用于特征聚合。'])
def test_named_tensor_maps_are_not_numbered_illustration_references(text):
    assert check(text)==[]


@pytest.mark.parametrize('text',['结果如特征图F1所示。','参见图F1。','响应图R2所示的模块仍需核查。','输出结果如图3.1所示。'])
def test_explicit_reference_words_preserve_real_missing_figure_detection(text):
    assert len(check(text))==1
