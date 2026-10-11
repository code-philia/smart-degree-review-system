"""Conservative original-PDF evidence for flow diagrams misparsed as tables."""
from dataclasses import replace
from pathlib import Path
import pymupdf


def _diamond_nodes(mask):
    import cv2
    import numpy as np
    height, width = mask.shape
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    nodes = []
    ideal = np.asarray(((0, .5), (.5, 0), (1, .5), (.5, 1)))
    for contour in contours:
        poly = cv2.approxPolyDP(contour, .025*cv2.arcLength(contour, True), True)
        if len(poly) != 4 or not cv2.isContourConvex(poly):
            continue
        x, y, w, h = cv2.boundingRect(poly)
        if not (max(12, width*.025) <= w <= width*.35 and
                max(12, height*.025) <= h <= height*.35 and .65 <= w/h <= 1.55):
            continue
        points = (poly[:, 0, :]-np.asarray((x, y))) / np.asarray((w-1, h-1))
        distances = np.linalg.norm(points[:, None, :]-ideal[None, :, :], axis=2)
        if not ((distances.min(axis=0) <= .18).all() and
                len(set(distances.argmin(axis=1))) == 4):
            continue
        center = (x+(w-1)/2, y+(h-1)/2)
        if any(abs(center[0]-old[0]) < w*.35 and abs(center[1]-old[1]) < h*.35 for old in nodes):
            continue
        nodes.append((*center, (w-1)/2, (h-1)/2))
    return nodes


def connected_diamond_flow(rgb):
    """Require multiple hollow nodes AND links between their boundaries.

    Grid lines, isolated diamond bullets and letters alone cannot qualify.
    A drawing is inspected read-only; no rendered crop enters a mutant PDF.
    """
    import cv2
    import numpy as np
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    mask = cv2.threshold(gray, 160, 255, cv2.THRESH_BINARY_INV)[1]
    nodes = _diamond_nodes(mask)
    if len(nodes) < 3:
        return False
    # Look for substantial straight segments, then verify gap continuity.
    # Sampling ink occupancy alone confuses aligned numeric glyphs with links.
    segments = cv2.HoughLinesP(mask, 1, np.pi/180, threshold=16,
                               minLineLength=12, maxLineGap=2)
    if segments is None:
        return False
    segments = segments.reshape(-1, 2, 2)
    ink = cv2.dilate(mask, np.ones((3, 3), np.uint8))
    edges = []
    for i, a in enumerate(nodes):
        for j, b in enumerate(nodes[i+1:], i+1):
            dx, dy = b[0]-a[0], b[1]-a[1]
            # Intersect the center line with each diamond's L1 boundary.
            sa = 1/(abs(dx)/a[2]+abs(dy)/a[3])
            sb = 1/(abs(dx)/b[2]+abs(dy)/b[3])
            distance = (dx*dx+dy*dy)**.5
            if 1-sa-sb <= 0 or distance*(1-sa-sb) < min(a[2], a[3], b[2], b[3]):
                continue
            direction = np.asarray((dx, dy))/distance
            offset = segments-np.asarray(a[:2])
            projection = offset @ direction
            perpendicular = abs(offset[:, :, 0]*direction[1]-offset[:, :, 1]*direction[0])
            gap = distance*(1-sa-sb)
            # Hough may split a continuous line where a grid crosses it.
            # Require a substantial collinear segment AND uninterrupted ink
            # across the interior gap, not merely high average occupancy.
            links = ((perpendicular <= 3).all(axis=1)
                     & (abs(projection[:, 1]-projection[:, 0]) >= gap*.4)
                     & (projection.max(axis=1) >= sa*distance)
                     & (projection.min(axis=1) <= (1-sb)*distance))
            if not links.any():
                continue
            border_slack = max(3, min(a[2],a[3],b[2],b[3])*.15)
            t = np.linspace(sa+border_slack/distance, 1-sb-border_slack/distance,
                            max(20, int(gap)))
            if t[0] >= t[-1]:
                continue
            xs = np.rint(a[0]+dx*t).astype(int).clip(0, mask.shape[1]-1)
            ys = np.rint(a[1]+dy*t).astype(int).clip(0, mask.shape[0]-1)
            covered = ink[ys, xs] > 0
            holes = np.diff(np.flatnonzero(np.r_[True, covered, True]))-1
            if covered.mean() >= .95 and holes.max(initial=0) <= 2:
                edges.append((i, j))
    return len(edges) >= 2 and len({node for edge in edges for node in edge}) >= 3


def reclassify_flow_diagrams(objects, document):
    candidates = [obj for obj in objects if obj.kind == 'table'
                  and obj.bbox[2]-obj.bbox[0] >= 60 and obj.bbox[3]-obj.bbox[1] >= 45
                  and (obj.bbox[2]-obj.bbox[0])*(obj.bbox[3]-obj.bbox[1])
                      < obj.page_width*obj.page_height*.5]
    if not candidates or not Path(document.path).is_file():
        return list(objects)
    import numpy as np
    converted = set()
    with pymupdf.open(document.path) as pdf:
        for obj in candidates:
            if not 1 <= obj.page_number <= len(pdf):
                continue
            page = pdf[obj.page_number-1]
            page.set_rotation(0)
            clip = pymupdf.Rect(obj.bbox) & page.rect
            if clip.is_empty:
                continue
            scale = min(3, 1200/max(clip.width, clip.height))
            pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip,
                                 colorspace=pymupdf.csRGB, alpha=False)
            rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
            if connected_diamond_flow(rgb):
                converted.add(id(obj))
    return [replace(obj, kind='figure', role='native_flow_diagram') if id(obj) in converted else obj
            for obj in objects]


def coloured_series_keys(rgb):
    """Identify multiple compact colour keys followed by black label ink."""
    import cv2
    import numpy as np
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    coloured = ((hsv[:,:,1] >= 55) & (hsv[:,:,2] >= 70)).astype('uint8')*255
    black = (cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY) < 150) & (hsv[:,:,1] < 70)
    height, width = coloured.shape
    contours, _ = cv2.findContours(coloured, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    keys = []
    for contour in contours:
        x,y,w,h = cv2.boundingRect(contour)
        if not (4 <= w <= width*.16 and 4 <= h <= height*.9 and .55 <= w/h <= 6):
            continue
        if cv2.contourArea(contour) < w*h*.45:
            continue
        region = black[max(0,y-h//2):min(height,y+h+h//2), x+w+2:min(width,x+w+max(35,int(width*.32)))]
        ys,xs = np.nonzero(region)
        if len(xs) >= max(10,h*1.5) and xs.max(initial=0)-xs.min(initial=width) >= h*1.5:
            keys.append((x,y,w,h))
    return len(keys) >= 2
