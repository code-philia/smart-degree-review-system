"""Native display-list evidence bounded by its actual PDF clipping scope.

Paths have already undergone Form/page transforms. Their raw coordinates can
extend far beyond visible ink, so consumers must use this bounded view.
Nonrectangular scissor bounds remain conservative: they do not prove an
academic figure's identity, and clipping edges are never invented as strokes.
"""
import pymupdf


def _clip_line(a, b, clip):
    """Intersect a painted segment with a rectangle, preserving its direction."""
    dx, dy = b.x - a.x, b.y - a.y
    start, end = 0.0, 1.0
    for delta, offset in ((-dx, a.x - clip.x0), (dx, clip.x1 - a.x),
                          (-dy, a.y - clip.y0), (dy, clip.y1 - a.y)):
        if delta == 0:
            if offset < 0:
                return None
            continue
        ratio = offset / delta
        if delta < 0:
            start = max(start, ratio)
        else:
            end = min(end, ratio)
        if start > end:
            return None
    if start == end:
        return None
    return (pymupdf.Point(a.x + start * dx, a.y + start * dy),
            pymupdf.Point(a.x + end * dx, a.y + end * dy))



def _visible_segment(a, b, clip, width=0.0):
    centre = _clip_line(a, b, clip)
    if centre is not None or width <= 0:
        return centre
    # A centre outside the clip may still paint a visible strip. Intersect
    # the actual stroke body, then take a representative parallel segment
    # INSIDE that strip. Enlarging the clip and returning its invisible
    # centre would create a false physical edge.
    from math import hypot
    length = hypot(b.x - a.x, b.y - a.y)
    if length == 0:
        return None
    ux, uy = (b.x - a.x) / length, (b.y - a.y) / length
    nx, ny = -uy, ux
    half = width / 2
    polygon = [(a.x + nx*half, a.y + ny*half),
               (a.x - nx*half, a.y - ny*half),
               (b.x - nx*half, b.y - ny*half),
               (b.x + nx*half, b.y + ny*half)]
    for axis, bound, sign in ((0, clip.x0, 1), (0, clip.x1, -1),
                              (1, clip.y0, 1), (1, clip.y1, -1)):
        output = []
        for previous, current in zip(polygon[-1:] + polygon[:-1], polygon):
            inside_p = sign * (previous[axis] - bound) >= 0
            inside_c = sign * (current[axis] - bound) >= 0
            if inside_p != inside_c:
                fraction = (bound - previous[axis]) / (current[axis] - previous[axis])
                output.append(tuple(previous[k] + fraction*(current[k]-previous[k]) for k in (0, 1)))
            if inside_c:
                output.append(current)
        polygon = output
        if len(polygon) < 3:
            return None
    along = [x*ux + y*uy for x, y in polygon]
    across = [x*nx + y*ny for x, y in polygon]
    offset = (min(across) + max(across)) / 2
    start, end = min(along), max(along)
    # Clip this representative line to the convex visible stroke polygon,
    # not just to the viewport. This also handles oblique clipped strokes.
    for p, q in zip(polygon, polygon[1:] + polygon[:1]):
        ex, ey = q[0]-p[0], q[1]-p[1]
        constant = ex*(ny*offset-p[1]) - ey*(nx*offset-p[0])
        slope = ex*uy - ey*ux
        if abs(slope) < 1e-12:
            if constant < -1e-9:
                return None
        elif slope > 0:
            start = max(start, -constant/slope)
        else:
            end = min(end, -constant/slope)
    if end <= start or max(across) <= min(across):
        return None
    return (pymupdf.Point(ux*start + nx*offset, uy*start + ny*offset),
            pymupdf.Point(ux*end + nx*offset, uy*end + ny*offset))


def _bounds(rect, clip):
    values = (max(rect.x0, clip.x0), max(rect.y0, clip.y0),
              min(rect.x1, clip.x1), min(rect.y1, clip.y1))
    # Straight lines have a zero-width or zero-height native rectangle.
    if values[0] > values[2] or values[1] > values[3]:
        return None
    return pymupdf.Rect(values)


def visible_drawings(page):
    """Retain path provenance while mapping every native consumer to visible ink.

    A clip applies only to following records at a strictly deeper level. MuPDF's
    scissor is already in page coordinates, including nested Form transforms.
    The source seqno/items remain in the original display list; this function
    creates a derived read-only view and does not rewrite PDF paths.
    """
    clips = {}
    result = []
    for raw in page.get_drawings(extended=True):
        level = raw.get("level", 0)
        clips = {depth: box for depth, box in clips.items() if depth < level}
        if raw["type"] == "clip":
            clips[level] = pymupdf.Rect(raw["scissor"])
            continue
        if raw["type"] == "group":
            continue
        clip = pymupdf.Rect(page.rect)
        for scope in clips.values():
            clip &= scope
        if clip.is_empty:
            continue
        visible = _bounds(raw["rect"], clip)
        width = float(raw.get("width") or 0) if "s" in raw["type"] else 0.0
        if visible is None and width > 0:
            rect = raw["rect"]
            support = pymupdf.Rect(rect.x0-width/2, rect.y0-width/2,
                                   rect.x1+width/2, rect.y1+width/2)
            visible = _bounds(support, clip)
        if visible is None:
            continue
        items = []
        for item in raw["items"]:
            if item[0] == "l":
                segment = _visible_segment(item[1], item[2], clip, width)
                if segment is not None:
                    items.append(("l", *segment))
            elif item[0] == "re":
                rect = item[1]
                if clip.contains(rect):
                    items.append(item)
                elif raw["type"] == "f":
                    fill = _bounds(rect, clip)
                    if fill is not None and not fill.is_empty:
                        items.append(("re", fill, item[2]))
                else:
                    # Stroked edges stop at the clip. A clip rectangle is not
                    # a painted border and must not create a new table column.
                    for a, b in ((rect.tl, rect.tr), (rect.tr, rect.br),
                                 (rect.br, rect.bl), (rect.bl, rect.tl)):
                        segment = _visible_segment(a, b, clip, width)
                        if segment is not None:
                            items.append(("l", *segment))
            else:
                # Curves/quads supply bounded graphic envelopes, not inferred
                # straight table borders. Preserve their original path items.
                items.append(item)
        if not items and not ("f" in raw["type"] and raw.get("fill") is not None
                              and not visible.is_empty):
            continue
        result.append({**raw, "items": items, "rect": visible,
                       "visible_clip": tuple(clip)})
    return tuple(result)
