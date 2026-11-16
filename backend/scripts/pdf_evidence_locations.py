"""Recover exact source glyph rectangles without changing saved report evidence."""
from __future__ import annotations

from contextlib import contextmanager
import json
import sys
import unicodedata


@contextmanager
def evidence_document(source):
    """Geometry is optional: preserve semantic findings if a PDF cannot open."""
    doc = None
    try:
        if source:
            import pymupdf
            doc = pymupdf.open(source)
    except Exception:
        pass
    try:
        yield doc
    finally:
        if doc:
            try:
                doc.close()
            except Exception:
                pass


def _normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text).casefold()
                   if not c.isspace() and c not in '-\u00ad\u2010\u2011')


def quote_rects(doc, start, quote, page_count=3):
    """Match one complete quote in a bounded page window, in visual line order."""
    target = _normalize(quote)
    if not target or start < 0:
        return []
    chars, positions = [], []
    for page_index in range(start, min(start + page_count, len(doc))):
        page = doc[page_index]
        lines = [(block_index, line_index, line)
                 for block_index, block in enumerate(page.get_text('rawdict')['blocks'])
                 for line_index, line in enumerate(block.get('lines', []))]
        # Edited PDFs can append a replacement line after the page footer in
        # content-stream order. Only physical order reconstructs its sentence.
        lines.sort(key=lambda row: (round(row[2]['bbox'][1], 1), row[2]['bbox'][0]))
        for block_index, line_index, line in lines:
            for span in line.get('spans', []):
                for char in span.get('chars', []):
                    for value in _normalize(char['c']):
                        chars.append(value)
                        positions.append((page_index, block_index, line_index, char['bbox']))
    text = ''.join(chars)
    offset = text.find(target)
    if offset < 0 or text.find(target, offset + 1) >= 0:
        return []  # Absent or ambiguous evidence gets no fabricated coordinates.
    groups = {}
    for page_index, block_index, line_index, box in positions[offset:offset + len(target)]:
        key = (page_index, block_index, line_index)
        if key not in groups:
            groups[key] = list(box)
        else:
            b = groups[key]
            b[:] = [min(b[0], box[0]), min(b[1], box[1]), max(b[2], box[2]), max(b[3], box[3])]
    return [dict(x1=b[0], y1=b[1], x2=b[2], y2=b[3],
                 width=doc[key[0]].rect.width, height=doc[key[0]].rect.height,
                 page_number=key[0] + 1) for key, b in groups.items()]


def quote_location(doc, page_number, quote, page_count=3):
    try:
        rects = quote_rects(doc, page_number - 1, quote, page_count)
    except Exception:
        return None  # Optional extraction failure must not discard a finding.
    if not rects:
        return None
    first_page = rects[0]['page_number']
    first = [r for r in rects if r['page_number'] == first_page]
    return dict(type='pdf_bbox', page_number=first_page, text_excerpt=quote,
                rects=rects, bounding_rect={**first[0],
                    'x1': min(r['x1'] for r in first), 'y1': min(r['y1'] for r in first),
                    'x2': max(r['x2'] for r in first), 'y2': max(r['y2'] for r in first)})


def main():
    import pymupdf
    queries = json.load(sys.stdin)['queries']
    with pymupdf.open(sys.argv[1]) as doc:
        locations = [quote_location(doc, query['page_number'], query['quote'],
                                    min(3, max(1, query.get('page_count', 3))))
                     for query in queries]
    print(json.dumps({'locations': locations}, ensure_ascii=True))


if __name__ == '__main__':
    main()
