"""Read native image clipping from MuPDF's SVG display list; never edit PDF pixels."""
import re
import base64
import io
import xml.etree.ElementTree as ET
import pymupdf

NUMBER = r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?"


def _matrix(value):
    if not value:
        return pymupdf.Matrix(1, 1)
    match = re.fullmatch(r"matrix\(([^)]+)\)", value)
    if not match:
        raise ValueError("Unsupported display transform")
    values = re.findall(NUMBER, match.group(1))
    if len(values) != 6:
        raise ValueError("Invalid display transform")
    return pymupdf.Matrix(*(float(v) for v in values))


def _rectangular_path(value):
    # MuPDF emits M/L/H/V rectangles for PDF Form BBox and clipping rectangles.
    # Curved/nonrectangular paths keep the original conservative envelope.
    tokens = re.findall(r"[A-Za-z]|" + NUMBER, value)
    points, cursor, origin = [], [0.0, 0.0], [0.0, 0.0]
    command, index = None, 0
    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index]
            index += 1
        if command is None or command.upper() not in {"M", "L", "H", "V", "Z"}:
            raise ValueError("Nonrectangular clipping path")
        if command.upper() == "Z":
            cursor = origin[:]
            command = None
            continue
        count = 2 if command.upper() in {"M", "L"} else 1
        numbers = [float(v) for v in tokens[index:index+count]]
        if len(numbers) != count:
            raise ValueError("Incomplete clipping path")
        index += count
        relative = command.islower()
        if count == 2:
            cursor = [numbers[i] + (cursor[i] if relative else 0) for i in range(2)]
        else:
            axis = 0 if command.upper() == "H" else 1
            cursor[axis] = numbers[0] + (cursor[axis] if relative else 0)
        points.append(tuple(cursor))
        if command.upper() == "M":
            origin = cursor[:]
            command = "l" if relative else "L"
    if len(points) < 3:
        raise ValueError("Empty clipping path")
    return pymupdf.Rect(min(p[0] for p in points), min(p[1] for p in points),
                        max(p[0] for p in points), max(p[1] for p in points))


def _blank_bitmap(payload):
    from PIL import Image
    with Image.open(io.BytesIO(payload)) as source:
        # Inspect exact decoded pixels. Even a faint line remains real content.
        if source.width * source.height > 4_000_000:
            return False
        if 'A' in source.getbands() and source.getchannel('A').getextrema() != (255,255):
            return False  # Opacity itself can encode a visible drawing.
        rgb = Image.new('RGB', source.size, 'white')
        rgba = source.convert('RGBA')
        rgb.paste(rgba, mask=rgba.getchannel('A'))
        return all(low == high == 255 for low, high in rgb.getextrema())


def visible_images(page, fallback):
    if page.rotation or not fallback:
        return fallback
    try:
        infos = page.get_image_info(xrefs=True)
        if not any(d['type'] == 'clip' for d in page.get_cdrawings(extended=True)):
            visible = [info for info in infos if not (pymupdf.Rect(info['bbox']) & page.rect).is_empty]
            # The cheap path also checks ordinary background tiles, which need
            # no clipping and may have hundreds of pixels in both dimensions.
            if len(visible) == len(fallback) and all(info['xref'] for info in visible):
                blank = {}
                for info in visible:
                    key = info['xref']
                    if key not in blank:
                        resource = page.parent.extract_image(key)
                        blank[key] = not resource.get('smask') and _blank_bitmap(resource['image'])
                return tuple(box for box, info in zip(fallback, visible) if not blank[info['xref']])
        root = ET.fromstring(page.get_svg_image(text_as_path=False))
        ids = {e.get("id"): e for e in root.iter() if e.get("id")}
        images = []
        blank = {}
        def blank_primitive(image):
            key = image.get('id')
            if key not in blank:
                blank[key] = False
                # One-pixel edge fills often surround embedded raster panels.
                # They are painting primitives, not independent figures.
                if float(image.get('width')) * float(image.get('height')) <= 4_000_000:
                    href = image.get('{http://www.w3.org/1999/xlink}href',image.get('href',''))
                    if href.startswith('data:image/') and ';base64,' in href:
                        blank[key] = _blank_bitmap(base64.b64decode(href.split(';base64,', 1)[1]))
            return blank[key]
        def walk(element, matrix, clip, masked=False, pattern_box=None):
            tag = element.tag.rsplit("}", 1)[-1]
            if tag in {"defs", "clipPath"}:
                return
            matrix = _matrix(element.get("transform")) * matrix
            reference = re.fullmatch(r"url\(#([^)]+)\)", element.get("clip-path", ""))
            if reference:
                definition = ids.get(reference.group(1))
                if definition is not None:
                    bounds = []
                    for path in definition:
                        try:
                            bounds.append(_rectangular_path(path.get("d", "")) * _matrix(path.get("transform")) * matrix)
                        except ValueError:
                            bounds.append(page.rect)
                    if bounds:
                        envelope = pymupdf.Rect(bounds[0])
                        for box in bounds[1:]:
                            envelope |= box
                        clip = clip & envelope
            mask = re.fullmatch(r"url\(#([^)]+)\)", element.get("mask", ""))
            masked = masked or bool(mask)
            if mask:
                definition = ids.get(mask.group(1))
                if definition is not None and definition.get('mask-type') is not None:
                    # MuPDF emits mask-type for an external PDF soft-mask
                    # group. A bare SVG mask is an image's alpha channel and
                    # is not an extra PDF image instance.
                    # A PDF soft mask may contain a page-sized image even when
                    # the painted object is clipped to a tiny visible region.
                    # Follow its actual use with the consumer's clipping state.
                    walk(definition, matrix, clip, masked, pattern_box)
            paint = re.fullmatch(r"url\(#([^)]+)\)", element.get("fill", ""))
            if paint:
                definition = ids.get(paint.group(1))
                if definition is None:
                    raise ValueError("Unknown SVG paint resource")
                if definition.tag.rsplit("}", 1)[-1] == "pattern":
                    # PDF image-info counts the pattern's resource invocation,
                    # while SVG paints it through a shape instead of <use>.
                    # Count those image resources too, retaining the CONSUMER
                    # region: its texture can repeat beyond the first tile.
                    if definition.get("patternUnits") != "userSpaceOnUse" or definition.get("patternContentUnits", "userSpaceOnUse") != "userSpaceOnUse":
                        raise ValueError("Unsupported pattern coordinate units")
                    if tag == "rect":
                        x, y = float(element.get("x", 0)), float(element.get("y", 0))
                        bounds = pymupdf.Rect(x, y, x+float(element.get("width")), y+float(element.get("height")))
                    elif tag == "path":
                        bounds = _rectangular_path(element.get("d", ""))
                    else:
                        raise ValueError("Unsupported pattern consumer")
                    painted = (bounds * matrix) & clip
                    # Repeating a patterned pattern is outside this reader's
                    # supported subset. Preserve fallback instead of hiding it.
                    if pattern_box is not None:
                        raise ValueError("Nested pattern paint")
                    pattern_matrix = _matrix(definition.get("patternTransform")) * matrix
                    walk(definition, pattern_matrix, clip, masked, painted)
            image = element if tag == "image" else None
            if tag == "use":
                ref = element.get("{http://www.w3.org/1999/xlink}href", element.get("href", ""))
                image = ids.get(ref.lstrip("#"))
                if image is not None and image.tag.rsplit("}", 1)[-1] != "image":
                    walk(image, matrix, clip, masked, pattern_box)
                    image = None
            if image is not None:
                x, y = float(element.get("x", 0)), float(element.get("y", 0))
                w, h = float(image.get("width")), float(image.get("height"))
                visible = pattern_box if pattern_box is not None else (pymupdf.Rect(x, y, x+w, y+h) * matrix) & clip
                images.append(tuple(visible) if not visible.is_empty and visible.width >= .1
                              and visible.height >= .1 and (masked or not blank_primitive(image)) else None)
            for child in element:
                walk(child, matrix, clip, masked, pattern_box)
        walk(root, pymupdf.Matrix(1, 1), page.rect)
        # Count direct images, soft-mask consumers and image-filled patterns.
        # Retain the guard: genuinely unparsed images must never disappear.
        # Off-canvas and completely clipped instances still count as understood
        # source invocations, but their visible boxes are not academic objects.
        if len(images) != len(infos):
            return fallback
        return tuple(box for box in images if box is not None)
    except Exception:
        return fallback
