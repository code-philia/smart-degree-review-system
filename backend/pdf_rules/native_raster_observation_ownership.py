"""Reconcile image-rectangle observations with a captioned original Form.

MuPDF image placement metadata includes images outside a Form's active clip.
A native coalesced envelope can therefore cross headers, prose and a title even
though its images paint only one already retained source graphic. This pass
binds the original image resources to that exact visible graphic; unknown
parser observations and independently painted images retain their obligations.
"""
from dataclasses import replace
from pathlib import Path

from .figure_identity_repair import _area, _inside, _union
from .caption_physical_ownership import _PageInk, _native_caption
from .caption_rules import detect_caption_rules
from .descriptive_caption_ownership import _declared_lines, _glyph_mask
from .mineru_layout import caption_identity
from .numbering import FIGURE_CAPTION, normalize_text


def _close(a, b):
    return max(abs(x-y) for x, y in zip(a, b)) < .05


def _identifying_characters_exist(line, required, ink):
    # Match every cached character to an actual filled/stroked source glyph.
    # A missing decimal point cannot borrow the paint of adjacent digits.
    from .native_text_paint import _filled_glyphs, _raw_boxes, _text
    glyphs = _filled_glyphs(ink.page)
    raw = _raw_boxes(ink.page)
    boxes = []
    for index in sorted(required):
        regions = [box for a, z, box in line.text_regions
                   if a == index and z-a == 1 and _area(box) > 0]
        if len(regions) != 1:
            return []
        region = regions[0]
        matches = [key for key in glyphs if key[2] == _text(line.text[index])
                   and any(_close(region, actual) for actual in [key[4]] + raw.get(key[:4], []))]
        # Tr=2 can fill and stroke one glyph, but two distinct source glyphs
        # at the declared rectangle are ambiguous and cannot prove identity.
        if len({key[:5] for key in matches}) != 1:
            return []
        boxes.append(region)
    return boxes


def _identifying_characters_painted(line, required, boxes, ink):
    # Suppress one actual identifying character at a time. Its own audited
    # glyph removal must reveal ink inside its exact native rectangle; a
    # neighbouring character's prefix mask cannot supply this evidence.
    for index, box in zip(sorted(required), boxes):
        character = replace(line, text=line.text[index], bbox=box,
                            text_regions=((0, 1, box),))
        mask = _glyph_mask(ink, [character])
        x0, y0, x1, y1 = [int(round(v*2)) for v in box]
        x0=max(x0,0);y0=max(y0,0);x1=min(x1,ink.width);y1=min(y1,ink.height)
        paint = ink.base[y0:y1, x0:x1] < 255
        if not int((paint & mask[y0:y1, x0:x1]).sum()):
            return False
    return bool(boxes)


def _printed_title(cap, page, ink):
    if not _native_caption(cap, page):
        return False
    lines = _declared_lines(cap, page)
    for line in lines:
        match = FIGURE_CAPTION.match(normalize_text(line.text))
        if match is None:
            continue
        required = {i for i, char in enumerate(line.text[:match.end('number')]) if char.strip()}
        boxes = _identifying_characters_exist(line, required, ink)
        if len(boxes) != len(required):
            continue
        if _identifying_characters_painted(line, required, boxes, ink):
            return True
    return False


def _image_roots(source_page):
    forms = source_page.get_xobjects()
    parents = {xref: parent for xref, name, parent, box in forms}
    names = {xref: name for xref, name, parent, box in forms if parent == 0}
    roots = {}
    for image in source_page.get_images(full=True):
        xref, parent = image[0], image[9]
        seen = set()
        while parent in parents and parent not in seen:
            seen.add(parent)
            if parents[parent] == 0:
                roots.setdefault(xref, set()).add(names[parent])
                break
            parent = parents[parent]
        if parent == 0:
            # A direct page image is independent of a neighbouring Form.
            roots.setdefault(xref, set()).add('page-image:' + image[7])
    return roots


def _native_contributors(obj, page):
    if obj.source_id or obj.role != 'native_figure' or obj.panel_boxes:
        return []
    boxes = [b for b in page.images if _inside(b, obj.bbox) > .999]
    return boxes if boxes and _close(_union(boxes), obj.bbox) else []


def _source_roots(boxes, info, roots, width, height):
    found = set()
    inline = []
    raster = []
    for box in boxes:
        placements = [record for record in info if _close(box, (
            max(0., record['bbox'][0]), max(0., record['bbox'][1]),
            min(width, record['bbox'][2]), min(height, record['bbox'][3])))]
        if not placements:
            return set(), []
        mapped = set().union(*(roots.get(record['xref'], set()) for record in placements))
        if mapped:
            found.update(mapped)
            raster.append(box)
        elif all(record['xref'] == 0 and max(record['width'], record['height']) <= 16
                 for record in placements) and _area(box) <= 100:
            # Inline stipple/glyph tiles are genuine source observations, and
            # cannot introduce a separate large graphic into the native union.
            inline.append(box)
        else:
            return set(), []
    if len(found) != 1 or not raster:
        return set(), []
    return found, inline


def _tiles_owned(boxes, ink, owner):
    # Inline tiles have no xref parent. Credit them only when every actual ink
    # pixel disappears with the independently proven Form. A white clipped
    # tile carries no additional graphic; an independent pixel fails closed.
    for box in boxes:
        x0, y0, x1, y1 = [int(round(v*2)) for v in box]
        x0=max(x0,0);y0=max(y0,0);x1=min(x1,ink.width);y1=min(y1,ink.height)
        paint = ink.base[y0:y1, x0:x1] < 255
        if int(paint.sum()) != int((paint & owner['mask'][y0:y1, x0:x1]).sum()):
            return False
    return True


def repair_native_raster_observation_ownership(objects, document):
    result = list(objects)
    if document is None or not Path(document.path).is_file():
        return result
    pending = {f['page'] for f in detect_caption_rules(result, [13], document)['13']['findings']}
    if not pending:
        return result
    import pymupdf
    from .source_native_caption_ownership import _OriginalPageInk
    with pymupdf.open(document.path) as source:
        for page in document.pages:
            if page.number not in pending or page.display_rotation or not 1 <= page.number <= len(source):
                continue
            native = [(o, _native_contributors(o, page)) for o in result
                      if o.kind == 'figure' and o.page_number == page.number]
            native = [(o, boxes) for o, boxes in native if boxes]
            anchors = [o for o in result if o.kind == 'figure' and o.page_number == page.number
                       and o.role == 'source_geometry_caption_owner' and o.caption_owner_id]
            if not native or not anchors:
                continue
            ink = _PageInk(source, page.number)
            try:
                if not ink.valid:
                    ink.close()
                    ink = _OriginalPageInk(source, page.number, document.path)
                if not ink.valid:
                    continue
                source_page = source[page.number-1]
                roots = _image_roots(source_page)
                info = source_page.get_image_info(hashes=True, xrefs=True)
                caps = [c for c in result if c.kind == 'figure_caption' and c.page_number == page.number]
                proven = {}
                for anchor in anchors:
                    cap = next((c for c in caps if caption_identity(c) == anchor.caption_owner_id), None)
                    if cap is None or not _printed_title(cap, page, ink):
                        continue
                    for xref, name, parent, box in source_page.get_xobjects():
                        if parent != 0:
                            continue
                        owner = ink.removal({name})
                        if (owner is None or not _close(owner['box'], anchor.bbox)
                                or not ink.owns(anchor, owner)):
                            continue
                        if any(c is not cap and _inside(c.bbox, owner['box']) > .5 for c in caps):
                            continue
                        proven.setdefault(name, []).append((anchor, owner))
                for obj, boxes in native:
                    linked, tiles = _source_roots(boxes, info, roots, page.width, page.height)
                    if len(linked) != 1:
                        continue
                    owners = proven.get(next(iter(linked)), [])
                    if len(owners) != 1:
                        continue
                    anchor, owner = owners[0]
                    if not _tiles_owned(tiles, ink, owner):
                        continue
                    # The visible source figure survives. Keep the raw native
                    # rectangle as a typed observation rather than a second
                    # academic figure whose clip was ignored by extraction.
                    typed = replace(obj, kind='text', role='source_clipped_raster_observation',
                                    caption_owner_id=anchor.caption_owner_id)
                    result = [typed if o is obj else o for o in result]
            except (ValueError, RuntimeError, IndexError):
                continue
            finally:
                ink.close()
    return result
