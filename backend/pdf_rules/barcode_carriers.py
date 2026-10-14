"""Recognize small inventory barcodes from visible pixels in the page margin."""
import numpy as np
import pymupdf
import re

from .numbering import caption_match


def _display_box(box, width, height, rotation):
    x1, y1, x2, y2 = box
    if rotation == 90:
        return (height-y2, x1, height-y1, x2), height, width
    if rotation == 180:
        return (width-x2, height-y2, width-x1, height-y1), width, height
    if rotation == 270:
        return (y1, width-x2, y2, width-x1), height, width
    return box, width, height


def _one_dimensional_bars(gray):
    """Require many long, parallel black/white runs, not a dark image or a logo."""
    dark = gray < 128
    if min(dark.shape) < 20:
        return False
    changes = np.count_nonzero(dark[:, 1:] != dark[:, :-1], axis=1)
    density = dark.mean(axis=1)
    rows = (changes >= 24) & (density >= .12) & (density <= .65)
    boundaries = np.flatnonzero(np.diff(np.r_[False, rows, False]))
    if not len(boundaries):
        return False
    start, end = max(zip(boundaries[::2], boundaries[1::2]), key=lambda p:p[1]-p[0])
    if end-start < dark.shape[0]*.28:
        return False
    band = dark[start:end]
    columns = band.mean(axis=0)
    if np.mean((columns <= .05) | (columns >= .95)) < .97:
        return False
    template = columns >= .5
    if np.mean(band == template[None, :]) < .98:
        return False
    occupied = np.flatnonzero(template)
    if not len(occupied) or occupied[-1]-occupied[0] < dark.shape[1]*.2:
        return False
    # An inventory code also has a compact human-readable line beneath its bars.
    lower = dark[end:]
    return bool(lower.size and np.count_nonzero(lower) >= 10
                and np.count_nonzero(lower) < lower.size*.25)


def margin_barcode_boxes(page, images, lines, display_rotation=0):
    """A research caption vetoes exclusion even when the pixels are a barcode."""
    proven = []
    for box in images:
        shown, width, height = _display_box(box, page.rect.width, page.rect.height,
                                           display_rotation % 360)
        x1, y1, x2, y2 = shown
        if not ((y1 <= height*.04 and y2 <= height*.12
                 or y1 >= height*.90 and y2 >= height*.96)
                and 0 < x2-x1 <= width*.35 and 0 < y2-y1 <= height*.12):
            continue
        if any((caption_match(line.text, 'figure') or caption_match(line.text, 'table')
                or (line.source == 'native' and abs(line.direction[1]) < .1
                    and line.bbox[2]-line.bbox[0] >= page.rect.width*.3
                    and len(re.findall(r'[A-Za-z\u4e00-\u9fff]', line.text)) >= 12
                    and min(line.bbox[2], box[2])-max(line.bbox[0], box[0])
                        >= .6*min(line.bbox[2]-line.bbox[0], box[2]-box[0])))
               and max(line.bbox[0], box[0]) < min(line.bbox[2], box[2])
               and min(abs(line.bbox[1]-box[3]), abs(box[1]-line.bbox[3])) <= 80
               for line in lines):
            continue
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(3, 3), clip=pymupdf.Rect(box),
                                 colorspace=pymupdf.csGRAY, alpha=False, annots=False)
        gray = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width)
        if display_rotation % 360:
            gray = np.rot90(gray, -(display_rotation % 360)//90)
        if _one_dimensional_bars(gray):
            proven.append(box)
    return tuple(proven)
