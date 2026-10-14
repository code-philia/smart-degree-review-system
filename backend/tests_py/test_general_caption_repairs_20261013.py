from dataclasses import replace
from pathlib import Path

from pdf_rules.caption_rules import detect_caption_rules
from pdf_rules.layout_context import _panel_group, prepare_caption_layout
from pdf_rules.logical_objects import panel_label_lines, shared_axis_groups
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.model import PdfDocument, PdfLine, PdfPage


def body(box, page=1, role='image_body'):
    return LayoutObject('figure', page, box, '', 600, 840, role)


def title(box, text='Figure 4.3 Measurements', page=1):
    return LayoutObject('figure_caption', page, box, text, 600, 840)


def document(pages):
    return PdfDocument(Path('unseen-caption-ownership.pdf'), tuple(pages))


def test_same_page_prose_keeps_cross_page_caption_with_its_original_figure():
    previous = body((100, 600, 450, 730), page=1)
    missing = body((160, 185, 430, 380), page=2)
    retained = title((170, 100, 440, 125), page=2)
    prose = PdfLine(2, 'An independent description introduces a different object.',
                    (90, 140, 510, 157), 600, 840)
    doc = document((PdfPage(1, 600, 840, ()), PdfPage(2, 600, 840, (prose,))))
    findings = detect_caption_rules([previous, missing, retained], [13], doc)['13']['findings']
    assert [f['page'] for f in findings] == [2]
    assert findings[0]['location']['bounding_rect']['y1'] == 185


def test_legitimate_above_figure_title_and_translated_row_remain_valid():
    graphic = body((100, 180, 450, 380))
    cap = title((170, 100, 420, 115))
    translated = PdfLine(1, '图4.3 实验结果', (210, 120, 380, 135), 600, 840)
    doc = document((PdfPage(1, 600, 840, (translated,)),))
    assert detect_caption_rules([graphic, cap], [13], doc)['13']['findings'] == []


def test_parser_envelope_cannot_hide_separate_native_raster_above_captioned_raster():
    native = ((180, 100, 440, 280), (175, 340, 450, 545))
    parsed = body((175, 98, 451, 545))
    cap = title((210, 550, 410, 575))
    doc = document((PdfPage(1, 600, 840, (), images=native),))
    prepared = prepare_caption_layout([parsed, cap], doc)
    findings = detect_caption_rules(prepared, [13], doc)['13']['findings']
    assert len(findings) == 1
    assert findings[0]['location']['bounding_rect']['y2'] == 280


def test_explicit_lettered_composite_survives_native_raster_partition_recovery():
    native = ((180, 100, 440, 280), (175, 340, 450, 545))
    parsed = body((175, 98, 451, 545))
    labels = (PdfLine(1, '(a) First condition', (220, 285, 370, 300), 600, 840),
              PdfLine(1, '(b) Second condition', (220, 548, 380, 563), 600, 840))
    cap = title((175, 570, 450, 590), 'Figure 4.3 (a) First condition; (b) Second condition')
    doc = document((PdfPage(1, 600, 840, labels, images=native),))
    assert detect_caption_rules(prepare_caption_layout([parsed, cap], doc), [13], doc)['13']['findings'] == []


def axis_fixture(distinct):
    upper = body((100, 100, 400, 280), role='chart_body')
    lower = body((100, 300, 400, 480), role='chart_body')
    cap = title((175, 485, 325, 500), 'Figure 8.2 Second experiment')
    lines = [PdfLine(1, 'Time (s)', box, 600, 840, source='local_graphic_ocr')
             for box in ((200, 265, 280, 275), (200, 465, 280, 475))]
    if distinct:
        lines.insert(0, PdfLine(1, 'Figures 8.1 and 8.2 respectively show two conditions.',
                               (80, 65, 520, 80), 600, 840))
    page = PdfPage(1, 600, 840, tuple(lines), images=(upper.bbox, lower.bbox))
    return [upper, lower], [cap], document((page,))


def test_explicit_distinct_figure_ids_prevent_shared_axes_from_erasing_missing_title():
    targets, captions, doc = axis_fixture(True)
    grouped = shared_axis_groups(targets, captions, doc)
    assert len(grouped) == 2
    assert len(detect_caption_rules(grouped + captions, [13], doc)['13']['findings']) == 1


def test_shared_axes_without_distinct_source_figure_declaration_keep_existing_grouping():
    targets, captions, doc = axis_fixture(False)
    assert len(shared_axis_groups(targets, captions, doc)) == 1


def merged_marker_fixture():
    boxes = ((100, 200, 280, 300), (300, 200, 480, 300),
             (190, 317, 400, 425), (110, 445, 480, 550))
    targets = [body(b, role='chart_body' if i == 3 else 'image_body') for i, b in enumerate(boxes)]
    # The labels sit a little closer to the wide next-row image. Their original
    # glyph bounds and distinct same-row source bodies still prove (a) and (b).
    text = 'a)                     b)'
    b_start = text.index('b)')
    regions = ((0, 1, (180, 304, 185, 315)), (1, 2, (185, 304, 190, 315)),
               (b_start, b_start + 1, (370, 304, 375, 315)),
               (b_start + 1, b_start + 2, (375, 304, 380, 315)))
    labels = (PdfLine(1, text, (80, 304, 380, 315), 600, 840, text_regions=regions),
              PdfLine(1, 'c)', (285, 430, 300, 442), 600, 840),
              PdfLine(1, 'd)', (285, 555, 300, 567), 600, 840),
              PdfLine(1, 'c) Third condition, d) Fourth condition', (180, 591, 410, 604), 600, 840))
    cap = title((100, 575, 480, 620),
                'Figure 4.3 a) First, b) Second; c) Third, d) Fourth')
    doc = document((PdfPage(1, 600, 840, labels, images=boxes),))
    return targets, [cap], doc


def test_caption_continuation_is_not_a_duplicate_physical_panel_marker():
    targets, caps, doc = merged_marker_fixture()
    labels = panel_label_lines(doc.pages[0], targets, caps)
    assert [line.text for line in labels] == ['a)', 'b)', 'c)', 'd)']


def test_native_merged_label_row_rejoins_mixed_height_composite_with_one_total_title():
    targets, caps, doc = merged_marker_fixture()
    grouped = _panel_group(targets, doc, caps)
    assert len(grouped) == 1
    assert detect_caption_rules(grouped + caps, [13], doc)['13']['findings'] == []


def cross_page_fixture(with_body=False, wrong_namespace=False, missing_caption=False):
    first = body((130, 340, 470, 680), page=1)
    second = body((180, 175, 435, 335), page=2)
    labels1 = (PdfLine(1, 'a) First method', (240, 490, 380, 506), 600, 840),
               PdfLine(1, 'b) Second method', (240, 655, 380, 677), 600, 840))
    labels2 = (PdfLine(2, 'a) Restarted method' if wrong_namespace else 'c) Third method',
                       (240, 339, 385, 356), 600, 840),)
    if with_body:
        intro = PdfLine(1, 'There are three methods, as Figure 6.4 illustrates.', (90, 230, 510, 245), 600, 840)
        labels1 = (intro,) + labels1 + (PdfLine(1, 'Following prose describes further details of the method.',
                                               (90, 698, 510, 714), 600, 840),)
        labels2 = (PdfLine(2, 'This paragraph continues the explanation across the page.',
                           (90, 105, 510, 125), 600, 840),) + labels2
    caps = [] if missing_caption else [title((240, 365, 380, 390), 'Figure 6.4 Methods', page=2)]
    pages = (PdfPage(1, 600, 840, labels1, images=((140, 340, 470, 480), (130, 530, 470, 650))),
             PdfPage(2, 600, 840, labels2, images=(second.bbox,)))
    return [first, second] + caps, document(pages)


def test_bare_closing_parenthesis_panel_namespace_continues_across_page():
    objects, doc = cross_page_fixture()
    assert detect_caption_rules(objects, [13], doc)['13']['findings'] == []


def test_explicit_counted_cross_page_panel_namespace_can_span_explanatory_prose():
    objects, doc = cross_page_fixture(with_body=True)
    assert detect_caption_rules(objects, [13], doc)['13']['findings'] == []


def test_cross_page_restarted_namespace_cannot_borrow_another_main_title():
    objects, doc = cross_page_fixture(with_body=True, wrong_namespace=True)
    findings = detect_caption_rules(objects, [13], doc)['13']['findings']
    assert [f['page'] for f in findings] == [1]


def test_cross_page_panel_count_without_retained_main_title_keeps_both_obligations():
    objects, doc = cross_page_fixture(with_body=True, missing_caption=True)
    assert len(detect_caption_rules(objects, [13], doc)['13']['findings']) == 2


def test_nearby_bilingual_table_title_cannot_supply_two_independent_tables():
    upper = LayoutObject('table', 1, (100, 125, 500, 268), '', 600, 840, 'table_body')
    lower = LayoutObject('table', 1, (115, 311, 495, 485), '', 600, 840, 'table_body')
    labels = (PdfLine(1, 'Table 5 - 3', (205, 281, 270, 294), 600, 840, block_id=2),
              PdfLine(1, 'Mechanical properties', (280, 281, 390, 294), 600, 840, block_id=2),
              PdfLine(1, '表5-3 力学属性表', (215, 297, 365, 310), 600, 840, block_id=2))
    from pdf_rules.native_layout import merge_caption_fragments
    lines = merge_caption_fragments(labels)
    doc = document((PdfPage(1, 600, 840, lines),))
    caps = [LayoutObject('table_caption', 1, l.bbox, l.text, 600, 840) for l in lines]
    from pdf_rules.layout_context import _caption_aliases
    findings = detect_caption_rules([upper, lower] + _caption_aliases(caps), [14], doc)['14']['findings']
    assert len(findings) == 1
    assert findings[0]['location']['bounding_rect']['y1'] == 125


def test_source_proved_margin_barcode_removes_only_contained_parser_observations():
    barcode = (510, 0, 590, 60)
    page = PdfPage(1, 600, 840, ())
    # Source geometry metadata is supplied by the pixel classifier. It is not
    # inferred from a parser role, a corner rectangle, or a paper identifier.
    object.__setattr__(page, 'margin_barcodes', (barcode,))
    observations = [LayoutObject(kind, 1, barcode, 'Bars', 600, 840)
                    for kind in ('figure', 'table', 'text', 'figure_caption', 'table_caption')]
    research = body((100, 180, 400, 350))
    prepared = prepare_caption_layout(observations + [research], document((page,)))
    assert not any(o.bbox == barcode for o in prepared)
    assert any(o.bbox == research.bbox and o.kind == 'figure' for o in prepared)


def test_partial_overlap_or_unproved_body_barcode_retains_figure_obligation():
    barcode = (510, 0, 590, 60)
    page = PdfPage(1, 600, 840, ())
    object.__setattr__(page, 'margin_barcodes', (barcode,))
    wider = body((505, 0, 595, 98))
    body_code = body((100, 180, 400, 260))
    prepared = prepare_caption_layout([wider, body_code], document((page,)))
    assert {o.bbox for o in prepared if o.kind == 'figure'} == {wider.bbox, body_code.bbox}
