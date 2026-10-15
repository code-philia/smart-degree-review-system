from pathlib import Path
import pytest
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules


def fixture(role='image_body', restart=False, barrier=False, internal_title=False):
    boxes=[(85,100,225,240),(235,100,375,240),(385,100,525,240),
           (160,275,300,415),(310,275,450,415)]
    bodies=[LayoutObject('figure',1,b,'',600,840,role) for b in boxes]
    letters=['a','b','c','d','e'] if not restart else ['a','b','c','a','b']
    lines=[PdfLine(1,f'({tag}) condition',((b[0]+b[2])/2-25,b[3]+8,(b[0]+b[2])/2+25,b[3]+20),600,840)
           for tag,b in zip(letters,boxes)]
    title=LayoutObject('figure_caption',1,(215,443,395,461),'Figure 3.1 Comparison',600,840)
    objects=bodies+[title]
    if barrier:lines.append(PdfLine(1,'The following experiment is a separate comparison.',(90,260,520,273),600,840))
    if internal_title:objects.append(LayoutObject('figure_caption',1,(210,257,400,273),'Figure 3.0 Earlier experiment',600,840))
    doc=PdfDocument(Path('five-panel-final-row.pdf'),(PdfPage(1,600,840,tuple(lines),images=tuple(boxes)),))
    return objects,doc


def findings(objects,doc):
    layout=prepare_caption_layout(objects,doc)
    return detect_caption_rules(layout,[13],doc)['13']['findings']


@pytest.mark.parametrize('role',['image_body','chart_body'])
def test_contiguous_panel_namespace_owns_centred_incomplete_last_row(role):
    objects,doc=fixture(role)
    assert findings(objects,doc)==[]


def test_restarted_letters_keep_earlier_untitled_composite_independent():
    objects,doc=fixture(restart=True)
    assert findings(objects,doc)


def test_body_paragraph_separates_two_labelled_grids():
    objects,doc=fixture(barrier=True)
    assert findings(objects,doc)


def test_intervening_independent_caption_is_a_boundary():
    objects,doc=fixture(internal_title=True)
    layout=prepare_caption_layout(objects,doc)
    assert len([o for o in layout if o.kind=='figure'])==2
