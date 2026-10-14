"""Invisible path extents must not become native table/figure evidence."""
import pymupdf
import pytest
from pdf_rules.native_layout import three_line_tables, vertical_cell_borders, coloured_legend_marks
from pdf_rules.pdf_extract import extract_pdf
from pdf_rules.container_ownership import _horizontal_rules


def page_with_commands(commands, text_rows=()):
    pdf = pymupdf.open()
    page = pdf.new_page(width=600, height=800)
    for text, x, y in text_rows:
        page.insert_text((x, y), text, fontsize=10)
    text = b"\n".join(pdf.xref_stream(xref) for xref in page.get_contents())
    xref = pdf.get_new_xref()
    pdf.update_object(xref, "<<>>")
    pdf.update_stream(xref, commands.encode("ascii") + b"\n" + text)
    page.set_contents(xref)
    return pdf, page


def clipped_long_rules():
    # Original paths reach x=14000. Only x=100..150 is displayed.
    return "q 100 600 50 120 re W n 0 G 1 w " + " ".join(
        f"80 {800-y} m 14000 {800-y} l S" for y in (100, 120, 180)
    ) + " Q"


def test_clipped_long_chart_edges_are_not_a_full_width_table():
    pdf, page = page_with_commands(clipped_long_rules(),
        [("Header", 105, 115), ("Values", 105, 155)])
    try:
        assert three_line_tables(page) == ()
    finally:
        pdf.close()


def test_visible_border_endpoints_follow_the_clip_instead_of_hidden_paths():
    pdf, page = page_with_commands(
        "q 100 600 50 120 re W n 0 G 1 w "
        "125 790 m 125 100 l S 14000 790 m 14000 100 l S Q")
    try:
        assert vertical_cell_borders(page) == ((125.0, 80.0, 200.0),)
    finally:
        pdf.close()


def test_native_graphic_envelopes_and_container_rules_use_visible_geometry(tmp_path):
    pdf, page = page_with_commands(
        "q 100 600 50 120 re W n 0 G 1 w "
        "80 700 m 14000 700 l 14000 620 l 80 620 l h S Q")
    path = tmp_path / "clipped-original.pdf"
    try:
        assert _horizontal_rules(page) == []
        pdf.save(path)
    finally:
        pdf.close()
    extracted = extract_pdf(path)
    # True visible extent is narrow. No multi-panel container may span hidden ink.
    assert extracted.pages[0].graphics == ((100.0, 100.0, 150.0, 180.0),)
    assert extracted.pages[0].tables == ()


def test_clip_boundary_does_not_invent_a_stroked_vertical_table_border():
    pdf, page = page_with_commands(
        "q 100 600 50 120 re W n 0 G 1 w -1000 620 15000 80 re S Q")
    try:
        assert vertical_cell_borders(page) == ()
    finally:
        pdf.close()


def test_clip_scope_ends_before_a_real_untitled_table():
    commands = clipped_long_rules() + " 0 G " + " ".join(
        f"60 {800-y} m 520 {800-y} l S" for y in (280, 300, 380))
    pdf, page = page_with_commands(commands,
        [("Chart", 105, 115), ("Values", 105, 155),
         ("Header", 70, 295), ("7", 70, 340)])
    try:
        boxes = three_line_tables(page)
        assert boxes == ((60.0, 280.0, 520.0, 380.0),)
    finally:
        pdf.close()


def test_ordinary_visible_table_and_its_vertical_cells_are_preserved():
    pdf, page = page_with_commands("0 G 1 w " + " ".join(
        f"60 {800-y} m 520 {800-y} l S" for y in (150, 170, 260)) +
        " 200 650 m 200 540 l S",
        [("Header", 70, 165), ("7", 70, 220)])
    try:
        assert three_line_tables(page) == ((60.0, 150.0, 520.0, 260.0),)
        assert vertical_cell_borders(page) == ((200.0, 150.0, 260.0),)
    finally:
        pdf.close()


def test_clipped_filled_slim_cell_border_retains_its_visible_span():
    pdf, page = page_with_commands(
        "q 100 600 50 120 re W n 0 g 124 100 2 690 re f Q")
    try:
        assert vertical_cell_borders(page) == ((125.0, 80.0, 200.0),)
    finally:
        pdf.close()


def test_container_boundary_rules_do_not_use_hidden_line_extensions():
    pdf, page = page_with_commands(clipped_long_rules())
    try:
        assert _horizontal_rules(page) == []
    finally:
        pdf.close()


def test_colour_key_uses_its_visible_filled_extent():
    pdf, page = page_with_commands(
        "q 100 690 20 10 re W n 1 0 0 rg 50 680 500 50 re f Q")
    try:
        assert coloured_legend_marks(page) == ((100.0, 99.5, 120.0, 110.5),)
    finally:
        pdf.close()


def test_visible_stroke_support_survives_when_its_centre_is_just_outside_clip():
    commands = "q 60 540 460 110 re W n 0 G 4 w " + " ".join(
        f"60 {800-y} m 520 {800-y} l S" for y in (149, 170, 261)) + " Q"
    pdf, page = page_with_commands(commands,
        [("Header", 70, 165), ("7", 70, 220)])
    try:
        # Top and bottom strokes have one point of real visible ink. Their
        # visible strip centres are 150.5 and 259.5, not the invisible149/261.
        assert three_line_tables(page) == ((60.0, 150.5, 520.0, 259.5),)
    finally:
        pdf.close()


def test_visible_vertical_stroke_support_is_not_lost_at_clip_edge():
    pdf, page = page_with_commands(
        "q 60 540 460 110 re W n 0 G 4 w 59 660 m 59 530 l S Q")
    try:
        assert vertical_cell_borders(page) == ((60.5, 150.0, 260.0),)
    finally:
        pdf.close()


def test_fully_hidden_stroke_is_not_resurrected_by_its_width():
    pdf, page = page_with_commands(
        "q 60 540 460 110 re W n 0 G 4 w 55 660 m 55 530 l S Q")
    try:
        assert vertical_cell_borders(page) == ()
    finally:
        pdf.close()
