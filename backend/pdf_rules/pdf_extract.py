from pathlib import Path

import pymupdf

from .model import PdfDocument, PdfLine, PdfPage


def extract_pdf(path: str | Path) -> PdfDocument:
    pdf_path = Path(path)
    pages = []
    with pymupdf.open(pdf_path) as document:
        for page_number, page in enumerate(document, 1):
            lines = []
            for block in page.get_text("dict", sort=True)["blocks"]:
                if block.get("type") != 0:
                    continue
                for raw_line in block.get("lines", []):
                    text = "".join(span.get("text", "") for span in raw_line.get("spans", [])).strip()
                    if not text:
                        continue
                    lines.append(PdfLine(
                        page_number, text, tuple(float(value) for value in raw_line["bbox"]),
                        float(page.rect.width), float(page.rect.height),
                    ))
            pages.append(PdfPage(
                page_number, float(page.rect.width), float(page.rect.height), tuple(lines),
                unreadable=not lines and bool(page.get_images(full=True)),
            ))
    return PdfDocument(pdf_path, tuple(pages))
