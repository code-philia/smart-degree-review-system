from pathlib import Path

import pymupdf

from .model import PdfDocument, PdfLine, PdfPage
from .numbering import normalize_text
from .visible_images import visible_images
from .native_graphics import visible_drawings
from .text_fragments import merge_reference_fragments
from .native_layout import raster_needs_ocr, three_line_tables, merge_caption_fragments, visible_ink_bottom, vertical_cell_borders, coloured_legend_marks


def extract_pdf(path: str | Path) -> PdfDocument:
    pdf_path = Path(path)
    pages = []
    with pymupdf.open(pdf_path) as document:
        for page_number, page in enumerate(document, 1):
            # Native text/image coordinates are unrotated. Normalize only this
            # in-memory document; never rewrite the input PDF.
            display_rotation=page.rotation
            page.set_rotation(0)
            lines = []
            for block_id, block in enumerate(page.get_text("rawdict", sort=True, flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)["blocks"]):
                if block.get("type") != 0:
                    continue
                for raw_line in block.get("lines", []):
                    chars = [char for span in raw_line.get("spans", []) for char in span.get("chars", [])]
                    while chars and chars[0]["c"].isspace():
                        chars.pop(0)
                    while chars and chars[-1]["c"].isspace():
                        chars.pop()
                    text = "".join(char["c"] for char in chars)
                    if not text:
                        continue
                    regions, offset = [], 0
                    for char in chars:
                        end = offset + len(normalize_text(char["c"]))
                        regions.append((offset, end, tuple(float(v) for v in char["bbox"])))
                        offset = end
                    measured = [(float(span.get("size",0)),len(span.get("chars",())),bool(span.get("flags",0)&16)) for span in raw_line.get("spans",())]
                    sizes = sorted(size for size,count,_ in measured for _ in range(count))
                    lines.append(PdfLine(
                        page_number, text, tuple(float(value) for value in raw_line["bbox"]),
                        float(page.rect.width), float(page.rect.height), text_regions=tuple(regions), block_id=block_id,
                        direction=tuple(raw_line.get("dir", (1.0, 0.0))),
                        font_size=sizes[len(sizes)//2] if sizes else None,
                        bold=sum(count for _,count,is_bold in measured if is_bold)>=max(1,len(sizes))*.7,
                    ))
            drawings = visible_drawings(page)
            tables = three_line_tables(page, drawings)
            lines = merge_caption_fragments(lines, tables)
            lines = merge_reference_fragments(lines, vertical_cell_borders(page, drawings))
            # Image transforms can extend outside the CropBox; invisible pixels
            # cannot be evidence that the visible page needs OCR.
            images = []
            for info in page.get_image_info():
                visible = pymupdf.Rect(info["bbox"]) & page.rect
                if not visible.is_empty:
                    images.append(tuple(float(v) for v in visible))
            images = visible_images(page, tuple(images))
            unreadable = raster_needs_ocr(lines, images, page.rect.width, page.rect.height)
            pages.append(PdfPage(
                page_number, float(page.rect.width), float(page.rect.height), tuple(lines),
                unreadable=unreadable,
                graphics=tuple(tuple(float(v) for v in d["rect"]) for d in drawings
                               if d["rect"].width>3 and d["rect"].height>3),
                images=images, tables=tables, legend_marks=coloured_legend_marks(page, drawings),display_rotation=display_rotation,
                ink_bottom=visible_ink_bottom(page) if unreadable else None,
            ))
    from .caption_raster_prefixes import recover_raster_caption_prefixes
    return recover_raster_caption_prefixes(PdfDocument(pdf_path, tuple(pages)))
