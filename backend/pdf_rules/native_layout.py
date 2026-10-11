"""Native PDF evidence used to supplement, never replace, MinerU layout."""
import re
from dataclasses import replace
from .numbering import LABEL, normalize_text, caption_match
from .model import PdfLine
from .native_graphics import visible_drawings
import pymupdf


def in_margin(box, width, height, display_rotation=0):
    """Recognize small header/footer carriers in the original display frame."""
    x1, y1, x2, y2 = box
    rotation=display_rotation%360
    if rotation==90:
        x1,y1,x2,y2=height-y2,x1,height-y1,x2
        width,height=height,width
    elif rotation==180:
        x1,y1,x2,y2=width-x2,height-y2,width-x1,height-y1
    elif rotation==270:
        x1,y1,x2,y2=y1,width-x2,y2,width-x1
        width,height=height,width
    return ((y2 <= height * 0.075 or y1 >= height * 0.95)
            and x2 - x1 <= width * 0.3 and y2 - y1 <= height * 0.065)



def text_covers_region(lines, box):
    """Conservative evidence of body OCR, never just a title or page number."""
    x1, y1, x2, y2 = box
    body = [line for line in lines
            if x1 <= (line.bbox[0] + line.bbox[2]) / 2 <= x2
            and y1 <= (line.bbox[1] + line.bbox[3]) / 2 <= y2
            and re.search(r"[A-Za-z\u4e00-\u9fff]", line.text)]
    if not body:
        return False
    letters = sum(len(re.findall(r"[A-Za-z\u4e00-\u9fff]", line.text)) for line in body)
    extent = max(line.bbox[3] for line in body) - min(line.bbox[1] for line in body)
    sentences = sum(len(re.findall(r"。|[.!?](?:\s|$)|[！？]", line.text)) for line in body)
    intervals = sorted((max(y1, line.bbox[1]), min(y2, line.bbox[3])) for line in body)
    cursor = y1
    largest_gap = 0
    for top, bottom in intervals:
        largest_gap = max(largest_gap, top - cursor)
        cursor = max(cursor, bottom)
    largest_gap = max(largest_gap, y2 - cursor)
    return (letters >= 80 and sentences >= 2 and extent >= (y2 - y1) * 0.7
            and intervals[0][0] <= y1 + (y2 - y1) * 0.2
            and cursor >= y2 - (y2 - y1) * 0.2
            and largest_gap <= (y2 - y1) * 0.25)


def raster_needs_ocr(lines, images, width, height):
    content = [box for box in images if not in_margin(box, width, height)]
    if not content:
        return False
    body = [line for line in lines
            if line.bbox[1] > height * 0.08 and line.bbox[3] < height * 0.95
            and re.search(r"[A-Za-z\u4e00-\u9fff]", line.text)]
    if not body:
        return True
    return (_union_area(content) >= width * height * 0.5
            and any(not text_covers_region(body, box) for box in content))


def _union_area(boxes):
    xs = sorted({x for box in boxes for x in (box[0], box[2])})
    total = 0
    for left, right in zip(xs, xs[1:]):
        intervals = sorted((box[1], box[3]) for box in boxes
                           if box[0] < right and box[2] > left)
        length = 0
        end = float('-inf')
        for top, bottom in intervals:
            length += max(0, bottom - max(top, end))
            end = max(end, bottom)
        total += (right - left) * length
    return total


def merge_caption_fragments(lines, tables=()):
    """Join title fragments along their actual text baseline, including rotation."""
    label = re.compile(rf"^\s*(?:图|表|Figure|Fig\.?|Table)\s*(?:{LABEL}|[.]\d+)[:：.]?\s*$", re.I)
    merged, consumed = {}, set()

    def projected(line, direction):
        dx, dy = direction
        x1, y1, x2, y2 = line.bbox
        points = [(x, y) for x in (x1,x2) for y in (y1,y2)]
        along = [x*dx+y*dy for x,y in points]
        across = [-x*dy+y*dx for x,y in points]
        return min(along), min(across), max(along), max(across)

    for index, left in enumerate(lines):
        if index in consumed or not label.fullmatch(normalize_text(left.text)):
            continue
        in_table = any(box[0] <= (left.bbox[0]+left.bbox[2])/2 <= box[2]
                       and box[1] <= (left.bbox[1]+left.bbox[3])/2 <= box[3] for box in tables)
        a = projected(left, left.direction)
        candidates = []
        for other, right in enumerate(lines):
            if (other == index or other in consumed or left.page_number != right.page_number
                    or left.source != right.source or left.direction != right.direction
                    or label.fullmatch(normalize_text(right.text))):
                continue
            # Native three-line windows can cross two plots. A title's original
            # text paragraph is stronger evidence than such a guessed table.
            same_paragraph = left.block_id is not None and left.block_id == right.block_id
            if in_table and (not same_paragraph or not re.search(r"[A-Za-z\u4e00-\u9fff]", right.text)):
                continue
            b = projected(right, left.direction)
            gap = b[0]-a[2]
            overlap = min(a[3],b[3])-max(a[1],b[1])
            height = min(a[3]-a[1],b[3]-b[1])
            if 0 <= gap <= max(30,height*3) and overlap >= height*.6:
                candidates.append((gap, other, right))
        if candidates:
            _, other, right = min(candidates,key=lambda item:item[0])
            start = len(normalize_text(left.text))+1
            merged[index] = replace(left, text=left.text+' '+right.text,
                bbox=(min(left.bbox[0],right.bbox[0]), min(left.bbox[1],right.bbox[1]),
                      max(left.bbox[2],right.bbox[2]), max(left.bbox[3],right.bbox[3])),
                text_regions=left.text_regions+tuple((a+start,b+start,box) for a,b,box in right.text_regions))
            consumed.add(other)
    return tuple(merged.get(index,line) for index,line in enumerate(lines) if index not in consumed)


def vertical_cell_borders(page, drawings=None):
    """Visible straight borders, including common PDF rectangle encoding."""
    borders = set()
    for drawing in visible_drawings(page) if drawings is None else drawings:
        for item in drawing['items']:
            segments = []
            if drawing.get('type') == 'f':
                # Filled slim rectangles are another common border encoding.
                if item[0] == 're':
                    rect = item[1]
                    fill = drawing.get('fill')
                    if (0 < rect.width <= 3 and rect.height >= rect.width*10
                            and drawing.get('fill_opacity',1) > 0
                            and fill is not None and min(fill) < .95):
                        x = (rect.x0+rect.x1)/2
                        borders.add((x,rect.y0,rect.y1))
                continue
            if item[0] == 'l':
                segments.append(item[1:3])
            elif item[0] == 're':
                rect = item[1]
                segments.extend(((rect.tl, rect.bl), (rect.tr, rect.br)))
            for a, b in segments:
                if abs(a.x-b.x) < 1.5 and abs(a.y-b.y) > 4:
                    borders.add(((a.x+b.x)/2, min(a.y,b.y), max(a.y,b.y)))
    return tuple(sorted(borders))


def three_line_tables(page, drawings=None):
    """Recover aligned top/header/bottom rules, with actual text between them."""
    drawings = visible_drawings(page) if drawings is None else drawings
    horizontal = []
    for drawing in visible_drawings(page) if drawings is None else drawings:
        for item in drawing["items"]:
            if item[0] != "l":
                continue
            a, b = item[1:3]
            if abs(a.y - b.y) < 1.5 and abs(a.x - b.x) >= page.rect.width * 0.18:
                x1, x2 = sorted((a.x, b.x))
                if page.rect.height * 0.08 < a.y < page.rect.height * 0.94:
                    horizontal.append((x1, x2, a.y))
    groups = []
    for line in sorted(set(horizontal), key=lambda line: line[2]):
        group = next((group for group in groups
                      if abs(group[0][0] - line[0]) < 3 and abs(group[0][1] - line[1]) < 3), None)
        if group is None:
            groups.append([line])
        else:
            group.append(line)
    boxes = []
    text_lines = [(*line["bbox"], "".join(span.get("text", "") for span in line.get("spans", [])))
                  for block in page.get_text("dict", flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)["blocks"] if block.get("type") == 0
                  for line in block.get("lines", [])]
    caption_rows = merge_caption_fragments(tuple(
        PdfLine(page.number + 1, line[4], tuple(line[:4]), page.rect.width, page.rect.height)
        for line in text_lines))
    captions = [line for line in caption_rows
                if caption_match(line.text, "figure") or caption_match(line.text, "table")]
    vertical = [(y1,y2,x) for x,y1,y2 in vertical_cell_borders(page, drawings)]
    def supported_span(lines, start, end):
        if end-start < 2:
            return False
        top, bottom = lines[start], lines[end]
        height = bottom[2]-top[2]
        if not (25 <= height <= page.rect.height*.6):
            return False
        # Internal row rules need not be the outer bottom of a table.
        if not any(4 <= header[2]-top[2] <= min(40,height*.4)
                   for header in lines[start+1:end]):
            return False
        return len(page.get_textbox(pymupdf.Rect(top[0],top[2],top[1],bottom[2])).strip()) >= 4

    for lines in groups:
        for index in range(len(lines) - 2):
            top, middle, bottom = lines[index:index + 3]
            height = bottom[2] - top[2]
            if not (25 <= height <= page.rect.height * 0.6
                    and 4 <= middle[2] - top[2] <= min(40, height * 0.4)):
                continue
            box = (top[0], top[2], top[1], bottom[2])
            # A header/body candidate needs content in both rule intervals.
            # A last row followed by an empty inter-table gap is not a new table.
            def occupied(upper, lower):
                return any(line[4].strip()
                           and line[0] < top[1] and line[2] > top[0]
                           and upper < (line[1] + line[3]) / 2 < lower
                           for line in text_lines)
            if not (occupied(top[2], middle[2]) and occupied(middle[2], bottom[2])):
                continue
            # A caption-shaped cell alone is not evidence of a table gap.
            # Require supported tables before and after this sliding window.
            gap_captions = [line for line in captions
                if middle[2] <= line.bbox[1] and line.bbox[3] <= bottom[2]
                and abs((line.bbox[0]+line.bbox[2])/2-(top[0]+top[1])/2) <= (top[1]-top[0])*.1
                and not any(top[0] <= x <= top[1] and y1 < (line.bbox[1]+line.bbox[3])/2 < y2
                            for y1, y2, x in vertical)]
            caption_gap = bool(gap_captions) and (
                any(supported_span(lines, start, end)
                    for end in (index,index+1) for start in range(index))
                and any(supported_span(lines,index+2,end)
                        for end in range(index+4,len(lines))))
            if caption_gap:
                continue
            # A sentence between two separate grids is not a table row.
            prose_gap = any(
                line[0] >= top[0] - 30 and line[2] <= top[1] + 30
                and line[1] >= middle[2] and line[3] <= bottom[2]
                and (line[2] - line[0] > (top[1] - top[0]) * 0.5 or len(line[4].strip()) > 30)
                and line[4].strip().endswith((".", "。", ";", "；"))
                for line in text_lines
            )
            if not prose_gap and len(page.get_textbox(pymupdf.Rect(box)).strip()) >= 4:
                boxes.append(box)
    return tuple(boxes)


def visible_ink_bottom(page):
    """Read-only raster evidence: a signature row cannot hide lower page content."""
    clip = pymupdf.Rect(page.rect.width*.03, page.rect.height*.08,
                        page.rect.width*.97, page.rect.height*.97)
    pix = page.get_pixmap(colorspace=pymupdf.csGRAY, alpha=False, clip=clip)
    mask = pix.samples.translate(bytes(1 if value < 255 else 0 for value in range(256)))
    for row in range(pix.height-1, -1, -1):
        if mask[row*pix.stride:row*pix.stride+pix.width].count(b"\x01") >= 3:
            return float(pix.y+row+1)
    return 0.0


def coloured_legend_marks(page, drawings=None):
    """Small coloured strokes/markers provide native evidence of plot legends."""
    marks=[]
    for drawing in visible_drawings(page) if drawings is None else drawings:
        rect=drawing['rect'];colours=(drawing.get('color'),drawing.get('fill'))
        if (0<rect.width<=40 and 0<=rect.height<=24
                and any(c is not None and len(c)==3 and max(c)-min(c)>.1 for c in colours)):
            marks.append((float(rect.x0),float(rect.y0)-.5,float(rect.x1),float(rect.y1)+.5))
    return tuple(marks)
