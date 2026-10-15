"""Header inventory codes must not make otherwise empty pages unextractable."""
from io import BytesIO

from PIL import Image, ImageDraw

from pdf_rules.pdf_extract import extract_pdf


def barcode_png():
    image = Image.new('RGB', (480, 280), 'white')
    draw = ImageDraw.Draw(image)
    x = 18
    for index in range(34):
        width = (3, 5, 2, 6, 3)[index % 5]
        draw.rectangle((x, 10, x + width - 1, 160), fill='black')
        x += width + (3, 2, 5)[index % 3]
    draw.text((40, 175), '20002658', fill='black')
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


def make_pdf(tmp_path, box, caption=None, rotation=0, image=None, prose=None):
    import pymupdf
    path = tmp_path / 'unseen-inventory-code.pdf'
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=600, height=840)
        page.insert_image(box, stream=image or barcode_png(), keep_proportion=False)
        if caption:
            page.insert_text((box[0], box[3] + 15), caption)
        if prose:
            page.insert_text((box[0], box[3] + 24), prose)
        page.set_rotation(rotation)
        pdf.save(path)
    return extract_pdf(path).pages[0]


def test_empty_page_with_native_header_barcode_remains_readable(tmp_path):
    page = make_pdf(tmp_path, (0, 0, 169, 60))
    assert page.unreadable is False
    assert page.images == ()
    assert page.margin_barcodes == ((0.0, 0.0, 169.0, 60.0),)


def test_research_barcode_in_body_keeps_image_and_ocr_obligation(tmp_path):
    page = make_pdf(tmp_path, (100, 180, 269, 240))
    assert page.unreadable is True
    assert len(page.images) == 1


def test_explicit_scientific_caption_keeps_header_graphic(tmp_path):
    page = make_pdf(tmp_path, (0, 0, 169, 60), 'Figure 1.1 Experimental barcode')
    assert len(page.images) == 1
    assert getattr(page, 'margin_barcodes', ()) == ()


def test_scientific_header_barcode_without_title_keeps_caption_obligation(tmp_path):
    page = make_pdf(tmp_path, (0, 0, 169, 60),
                    prose='The barcode above encodes our measured sample labels.')
    assert len(page.images) == 1
    assert page.margin_barcodes == ()
    from pathlib import Path
    from pdf_rules.caption_rules import detect_caption_rules
    from pdf_rules.layout_context import prepare_caption_layout
    from pdf_rules.mineru_layout import LayoutObject
    from pdf_rules.model import PdfDocument
    obj = LayoutObject('figure', 1, (0, 0, 169, 60), '', 600, 840, 'image_body')
    doc = PdfDocument(Path('new-scientific-barcode.pdf'), (page,))
    result = detect_caption_rules(prepare_caption_layout([obj], doc), [13], doc)
    assert len(result['13']['findings']) == 1


def test_nonbarcode_header_bitmap_remains_unresolved(tmp_path):
    image = Image.new('RGB', (480, 280), 'white')
    ImageDraw.Draw(image).ellipse((40, 20, 440, 250), outline='black', width=8)
    output = BytesIO()
    image.save(output, format='PNG')
    page = make_pdf(tmp_path, (0, 0, 169, 60), image=output.getvalue())
    assert page.unreadable is True
    assert len(page.images) == 1


def test_body_column_only_touching_inventory_code_edge_does_not_claim_it(tmp_path):
    import pymupdf
    path = tmp_path / 'independent-header-inventory.pdf'
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=600, height=840)
        page.insert_image((0, 0, 94, 60), stream=barcode_png(), keep_proportion=False)
        page.insert_text((72, 83), 'This independent paragraph explains the diffraction experiment.')
        pdf.save(path)
    page = extract_pdf(path).pages[0]
    assert len(page.margin_barcodes) == 1
    assert page.images == ()
