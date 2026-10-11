from pathlib import Path
from pdf_rules.model import PdfDocument,PdfPage
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.object_identity import refine_targets


def fixture(tagged=True,own_title=False,outside=False):
    equation=LayoutObject('text',1,(180,240,420,270),
        r'h_i = GRU(x_i,h_{i-1}) \tag{3.8}' if tagged else 'The following illustration explains the model.',
        600,840,'interline_equation' if tagged else 'text')
    fragments=[LayoutObject('figure',1,b,'',600,840,'native_figure') for b in
               [(190,246,204,263),(300,246,312,263),(390,246,401,263)]]
    objects=fragments+[equation]
    if own_title:objects.append(LayoutObject('figure_caption',1,(290,277,350,288),'Figure 2.5 Result',600,840))
    if outside:objects.append(LayoutObject('figure',1,(450,240,490,270),'',600,840,'native_figure'))
    return objects,PdfDocument(Path('equation-glyphs.pdf'),(PdfPage(1,600,840,()),))


def test_numbered_display_equation_owns_its_native_raster_glyph_fragments():
    objects,doc=fixture()
    assert not [o for o in refine_targets(objects,doc) if o.kind=='figure']


def test_normal_paragraph_cannot_suppress_nearby_untitled_figures():
    objects,doc=fixture(tagged=False)
    assert len([o for o in refine_targets(objects,doc) if o.kind=='figure'])==3


def test_separate_figure_caption_retains_its_title_identity_inside_a_formula_envelope():
    objects,doc=fixture(own_title=True)
    assert [o for o in refine_targets(objects,doc) if o.kind=='figure']


def test_graphic_outside_equation_extent_remains_an_independent_target():
    objects,doc=fixture(outside=True)
    assert len([o for o in refine_targets(objects,doc) if o.kind=='figure'])==1
