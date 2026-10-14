from pathlib import Path
from pdf_rules.model import PdfDocument,PdfPage
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules


def evaluate(title_box,with_physical=True,own_title=False,return_layout=False):
    boxes=[(90,120,300,280),(310,120,520,280)]
    bodies=[LayoutObject('figure',1,b,'',600,840,'image_body') for b in boxes]
    titles=[LayoutObject('figure_caption',1,title_box,'Figure 3.3 Method comparison',600,840)]
    if own_title:titles.append(LayoutObject('figure_caption',1,(100,285,285,302),'Figure 3.2 Independent result',600,840))
    doc=PdfDocument(Path('bitmap-pair-title.pdf'),(PdfPage(1,600,840,(),images=tuple(boxes) if with_physical else ()),))
    layout=prepare_caption_layout(bodies+titles,doc)
    if return_layout:return layout
    return detect_caption_rules(layout,[13],doc)['13']['findings']


def test_short_common_caption_owns_equal_height_original_bitmap_pair():
    assert evaluate((150,287,460,316))==[]


def test_localized_caption_preserves_uncaptioned_neighbor():
    assert len(evaluate((105,287,275,308)))==1


def test_short_caption_with_no_original_image_proof_does_not_merge_parser_guesses():
    assert evaluate((150,287,460,316),with_physical=False)


def test_independent_title_boundary_prevents_bitmap_pair_merge():
    layout=evaluate((150,316,460,338),own_title=True,return_layout=True)
    assert len([o for o in layout if o.kind=='figure'])==2
