from pathlib import Path
import pytest
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules


def line(text,y):return PdfLine(1,text,(60 if y==100 else 180,y,540 if y==100 else 420,y+13),600,840)


def run(text,numbers=(2,),kind='figure'):
    titles=[line(f'{"Figure" if kind=="figure" else "Table"} 7.{n} Experimental result',300+n*40) for n in numbers]
    doc=PdfDocument(Path('subpanel-range.pdf'),(PdfPage(1,600,840,tuple([line(text,100)]+titles)),))
    index=build_index(doc)
    return index,detect_rules(index,[11,15,16])


@pytest.mark.parametrize('text',['Fig. 7.2a-7.2b show the results.','As shown in Figures 7–2c–7–2d, performance improves.','如图7.2a-7.2b所示。'])
def test_numeric_subpanel_range_resolves_parent_figure(text):
    index,result=run(text)
    assert index.figure_refs
    assert result['11']['findings']==[] and result['15']['findings']==[]


def test_cross_parent_subpanel_range_resolves_all_parent_figures():
    _,result=run('As shown in Figs. 7.2a-7.4b, performance improves.',numbers=(2,3,4))
    assert result['11']['findings']==[] and result['15']['findings']==[]


def test_missing_parent_inside_subpanel_range_remains_reported():
    _,result=run('See Figures 7.2a-7.4b for comparisons.',numbers=(2,4))
    assert [f['token'] for f in result['11']['findings']]==['7.3']


def test_parent_table_is_cited_by_lettered_panel_range():
    _,result=run('As shown in Table 7.2a-7.2b, the scores differ.',kind='table')
    assert result['16']['findings']==[]


@pytest.mark.parametrize('text',['Feature graph F2D contains four vertices.','The value is stored in object_Fig7.2a.','Figure 7.2alpha is an identifier.'])
def test_identifiers_are_not_partial_numeric_subpanel_citations(text):
    _,result=run(text)
    assert result['11']['findings']==[]
    assert result['15']['findings']
