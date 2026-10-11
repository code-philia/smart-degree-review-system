"""Native glyph bitmaps belonging to explicit inline mathematical spans."""


def remove_inline_equation_rasters(objects, document):
    from .layout_context import containment
    from .caption_rules import _matches
    from collections import defaultdict
    import math
    regions = defaultdict(list)
    for obj in objects:
        if obj.kind == 'equation' and obj.role == 'inline_equation':
            regions[obj.page_number].append(obj.bbox)
    candidates = []
    for obj in objects:
        if obj.kind != 'figure' or obj.role != 'native_figure':
            continue
        boxes = [box for box in regions[obj.page_number]
                 if containment(obj.bbox, box) >= .5]
        if not boxes:
            continue
        if any(other.page_number == obj.page_number and (
                other.kind == 'figure_caption' and _matches(obj, other)
                or other.kind == 'figure' and not other.role.startswith('native_')
                and containment(obj.bbox, other.bbox) >= .5) for other in objects):
            continue
        candidates.append((obj, boxes))
    if not candidates or not document.path.is_file():
        return objects
    import pymupdf
    import numpy as np
    removed = set()
    pages = {page.number: page for page in document.pages}
    # Only overflow needs pixel evidence: old equation bitmaps often contain
    # white padding beyond the actual formula. Render each affected page once.
    rendered = {}
    with pymupdf.open(document.path) as pdf:
        for obj, boxes in candidates:
            page = pages[obj.page_number]
            if page.display_rotation:
                continue
            if obj.page_number not in rendered:
                pix = pdf[obj.page_number-1].get_pixmap(matrix=pymupdf.Matrix(2,2),
                    colorspace=pymupdf.csGRAY, alpha=False, annots=False)
                rendered[obj.page_number] = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height,pix.width)
            pixels = rendered[obj.page_number]
            x1,y1 = (max(0,math.floor(v*2)) for v in obj.bbox[:2])
            x2,y2 = (math.ceil(v*2) for v in obj.bbox[2:])
            ink = pixels[y1:y2,x1:x2] < 245
            if not ink.any():
                continue
            explained = np.zeros(ink.shape,dtype=bool)
            for box in boxes:
                # Small glyph antialiasing / parser-coordinate tolerance only.
                a,b = (math.floor((v-2)*2) for v in box[:2])
                c,d = (math.ceil((v+2)*2) for v in box[2:])
                explained[max(0,b-y1):max(0,d-y1),max(0,a-x1):max(0,c-x1)] = True
            if not (ink & ~explained).any():
                removed.add(id(obj))
    return [obj for obj in objects if id(obj) not in removed]
