"""A tiled original PDF image and its parser fragments are one physical object."""
from pathlib import Path
from pdf_rules.model import PdfDocument, PdfPage
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules
from pdf_rules.logical_objects import reconcile_physical_rasters


def figure(box, role='image_body', panels=()):
    return LayoutObject('figure', 1, box, '', 600, 840, role, panel_boxes=panels)


def caption(box=(220,355,380,375)):
    return LayoutObject('figure_caption', 1, box, 'Figure 3.1 Architecture', 600, 840)


def evaluate(objects, images):
    doc = PdfDocument(Path('physical-tiled-carrier.pdf'),
                      (PdfPage(1,600,840,(),images=tuple(images)),))
    layout = prepare_caption_layout(objects, doc)
    return layout, detect_caption_rules(layout, [13], doc)['13']['findings']


def test_abutting_physical_tiles_own_cloud_fragments_without_duplicate_alarms():
    tiles = [(100,100,500,220), (100,220,500,340)]
    objects = [figure((110,120,310,315)), figure((320,110,480,330)), caption()]
    layout, findings = evaluate(objects, tiles)
    assert findings == []
    assert len([o for o in layout if o.kind=='figure']) == 1


def reconciled(objects, images, titles=()):
    doc = PdfDocument(Path('physical-tiled-carrier.pdf'),
                      (PdfPage(1,600,840,(),images=tuple(images)),))
    return reconcile_physical_rasters(objects,list(titles),doc)


def test_an_independently_titled_figure_inside_tiled_export_retains_other_obligation():
    tiles = [(100,100,500,220), (100,220,500,340)]
    left, right = figure((110,110,280,270)), figure((310,110,490,330))
    carrier = figure((100,100,500,340),'continuous_chart_panels',tuple(tiles))
    result = reconciled([carrier,left,right],tiles,[caption((120,285,270,305))])
    assert left in result and right in result
    assert carrier not in result


def test_gapped_native_tiles_do_not_prove_one_uninterrupted_bitmap():
    tiles = [(100,100,500,200), (100,250,500,340)]
    carrier = figure((100,100,500,340),'continuous_chart_panels',tuple(tiles))
    child = figure((115,110,310,180))
    assert len(reconciled([carrier,child],tiles,[caption()])) == 2


def test_inferred_envelope_with_no_matching_original_tiles_does_not_hide_child():
    panels = ((100,100,500,220), (100,220,500,340))
    carrier = figure((100,100,500,340),'continuous_chart_panels',panels)
    child = figure((115,110,310,180))
    assert len(reconciled([carrier,child],[],[caption()])) == 2


def test_nearby_uncaptioned_image_outside_tiled_carrier_remains_reported():
    tiles = [(100,100,500,220), (100,220,500,340)]
    other = (100,450,250,600)
    objects = [figure((110,120,310,315)), figure((320,110,480,330)),
               figure(other), caption()]
    _, findings = evaluate(objects, tiles + [other])
    assert len(findings) == 1
    assert findings[0]['location']['bounding_rect']['y1'] >= 450
