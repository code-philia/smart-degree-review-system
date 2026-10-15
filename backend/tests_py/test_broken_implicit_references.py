"""Unresolved typesetting placeholders cannot establish a real target citation."""
from pathlib import Path
import pytest
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules


def run(text,kind="figure"):
    prefix="图" if kind=="figure" else "表"
    lines=(PdfLine(1,text,(80,100,520,115),600,840),
           PdfLine(1,prefix+"7.1 实验结果",(170,310,430,325),600,840,bold=True))
    doc=PdfDocument(Path("broken-ref.pdf"),(PdfPage(1,600,840,lines),))
    rule=15 if kind=="figure" else 16
    return detect_rules(build_index(doc),[rule])[str(rule)]["findings"]


@pytest.mark.parametrize("text",["如图??所示，本研究设计了框架。","如图 ? ? 所示，结果如下。","如图？？所示，结构如下。"])
def test_broken_figure_placeholder_is_not_an_implicit_reference(text):
    assert run(text)


def test_broken_table_placeholder_is_not_an_implicit_reference():
    assert run("如表??所示，参数如下。","table")


def test_valid_unnumbered_figure_reference_is_retained():
    assert run("如图所示，本研究设计了框架。") == []


def test_sentence_question_mark_is_not_a_broken_number():
    assert run("如图？这幅图的结果需要进一步讨论。") == []
