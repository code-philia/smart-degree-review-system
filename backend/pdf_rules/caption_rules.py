from .mineru_layout import LayoutObject
from .numbering import normalize_text
import re


def _horizontal_overlap(left: LayoutObject, right: LayoutObject) -> float:
    x1 = max(left.bbox[0], right.bbox[0])
    x2 = min(left.bbox[2], right.bbox[2])
    width=min(left.bbox[2]-left.bbox[0],right.bbox[2]-right.bbox[0])
    return max(0.0,x2-x1)/width if width>0 else 0.0


def _matches(target: LayoutObject, caption: LayoutObject) -> bool:
    if target.page_number == caption.page_number and getattr(target,"caption_owner_id",""):
        from .mineru_layout import caption_identity
        if target.caption_owner_id == caption_identity(caption):return True
    if caption.role=='unnumbered_panel_title' and target.kind=='table' and caption.page_number==target.page_number:
        from .layout_context import containment
        if containment(caption.bbox,target.bbox)>=.8:
            return True
    if (target.page_number == caption.page_number
            and caption.bbox[3]-caption.bbox[1] > 3*(caption.bbox[2]-caption.bbox[0])):
        # Sideways captions have a vertical baseline beside the graphic.
        overlap = min(target.bbox[3],caption.bbox[3])-max(target.bbox[1],caption.bbox[1])
        height = min(target.bbox[3]-target.bbox[1],caption.bbox[3]-caption.bbox[1])
        gap = max(caption.bbox[0]-target.bbox[2],target.bbox[0]-caption.bbox[2])
        if overlap >= height*.5 and -2 <= gap <= 80:
            return True
        width=caption.bbox[2]-caption.bbox[0]
        crossing=(caption.bbox[0]<target.bbox[0]<caption.bbox[2]
                  or caption.bbox[0]<target.bbox[2]<caption.bbox[2])
        if (crossing and target.bbox[1]<=caption.bbox[1]<caption.bbox[3]<=target.bbox[3]
                and width<=min(36,(target.bbox[2]-target.bbox[0])*.25)
                and gap>=-min(18,width*.6)):
            return True
        return (target.bbox[0]<=caption.bbox[0]<caption.bbox[2]<=target.bbox[2]
                and target.bbox[1]<=caption.bbox[1]<caption.bbox[3]<=target.bbox[3]
                and width<=min(36,(target.bbox[2]-target.bbox[0])*.15)
                and min(caption.bbox[0]-target.bbox[0],target.bbox[2]-caption.bbox[2])<=max(5,width*.5))
    if (caption.role == 'unnumbered_heading' and target.kind == 'table'
            and caption.page_number == target.page_number
            and caption.bbox[3] <= min(target.bbox[1], caption.page_height*.18)):
        return True
    tolerance = max(2, min(5, (caption.bbox[3]-caption.bbox[1])*.25))
    if _horizontal_overlap(target, caption) < 0.25:
        return False
    if target.page_number == caption.page_number:
        # Layout crops sometimes include their complete title. A short title
        # at the outer edge may belong to that crop; an internal caption for
        # another object cannot supply a title for the surrounding container.
        height=caption.bbox[3]-caption.bbox[1]
        crossing=(caption.bbox[1]<target.bbox[1]<caption.bbox[3]
                  or caption.bbox[1]<target.bbox[3]<caption.bbox[3])
        overlap=min(caption.bbox[3],target.bbox[3])-max(caption.bbox[1],target.bbox[1])
        if (crossing and height<=min(36,(target.bbox[3]-target.bbox[1])*.25)
                and overlap<=min(18,height*.6)):
            return True
        if (target.bbox[0]<=caption.bbox[0]<caption.bbox[2]<=target.bbox[2]
                and target.bbox[1]<=caption.bbox[1]<caption.bbox[3]<=target.bbox[3]
                and height<=min(36,(target.bbox[3]-target.bbox[1])*.15)
                and min(caption.bbox[1]-target.bbox[1],target.bbox[3]-caption.bbox[3])<=max(5,height*.5)):
            return True
        if target.kind == "figure":
            return (-tolerance <= caption.bbox[1] - target.bbox[3] <= 80 or
                    -tolerance <= target.bbox[1] - caption.bbox[3] <= 80)
        return (-tolerance <= target.bbox[1] - caption.bbox[3] <= 80 or
                -tolerance <= caption.bbox[1] - target.bbox[3] <= 80)
    if caption.page_number == target.page_number + 1 and target.kind == "figure":
        return target.bbox[3] >= target.page_height * 0.75 and caption.bbox[1] <= caption.page_height * 0.15
    if caption.page_number == target.page_number - 1 and target.kind == "table":
        return caption.bbox[3] >= caption.page_height * 0.75 and target.bbox[1] <= target.page_height * 0.15
    return False


def _location(obj: LayoutObject) -> dict:
    x1, y1, x2, y2 = obj.bbox
    rect = {"x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "width": obj.page_width, "height": obj.page_height,
            "page_number": obj.page_number}
    return {"type": "pdf_bbox", "page_number": obj.page_number,
            "bounding_rect": rect, "rects": [rect], "text_excerpt": obj.text}


def _rank_figure_candidates(candidates, targets):
    """Infer title side from unambiguous pairs, never from evaluation labels.

    Prefer the current page's observed style, then the document's. If neither
    has a dominant side, keep distance ordering rather than assume a style.
    """
    by_caption = {}
    for candidate in candidates:
        if candidate[0] == 0:
            by_caption.setdefault(candidate[-1], []).append(candidate)
    page_votes, votes = {}, [0, 0]
    for options in by_caption.values():
        if len(options) != 1:
            continue
        candidate = options[0]
        page = targets[candidate[-2]].page_number
        side = candidate[1]
        page_votes.setdefault(page, [0, 0])[side] += 1
        votes[side] += 1

    def preferred(counts):
        if counts[0] == counts[1]:
            return None
        return int(counts[1] > counts[0])

    ranked = []
    for candidate in candidates:
        page = targets[candidate[-2]].page_number
        side = preferred(page_votes.get(page, [0, 0]))
        if side is None:
            side = preferred(votes)
        penalty = int(candidate[0] == 0 and side is not None and candidate[1] != side)
        ranked.append((candidate[0], penalty, *candidate[2:]))
    return ranked


def _figure_matches(candidates):
    """Keep preferred associations, then recover unused valid title pairings.

    A one-pass greedy match can strand an above-figure title when its figure
    takes a neighbour's title. An augmenting path increases coverage without
    letting an untitled figure steal the only title of a captioned figure.
    """
    owners, adjacency = {}, {}
    matched = set()
    for *_, target, caption in sorted(candidates):
        adjacency.setdefault(target, []).append(caption)
        if target not in matched and caption not in owners:
            owners[caption] = target
            matched.add(target)
    for start in adjacency:
        if start in matched:
            continue
        parents = {start: None}
        queue = [start]
        seen_captions = set()
        free = None
        for target in queue:
            for caption in adjacency[target]:
                if caption in seen_captions:
                    continue
                seen_captions.add(caption)
                if caption not in owners:
                    free = (target, caption)
                    break
                owner = owners[caption]
                if owner not in parents:
                    parents[owner] = (target, caption)
                    queue.append(owner)
            if free is not None:
                break
        if free is not None:
            target, caption = free
            while True:
                owners[caption] = target
                parent = parents[target]
                if parent is None:
                    break
                target, caption = parent
            matched.add(start)
    return matched


def detect_caption_rules(objects: list[LayoutObject], selected_rule_numbers, document=None) -> dict:
    result = {}
    selected = set(selected_rule_numbers)
    for rule, target_kind, caption_kind, label in (
        (13, "figure", "figure_caption", "图"),
        (14, "table", "table_caption", "表"),
    ):
        if rule not in selected:
            continue
        if not objects:
            result[str(rule)] = {"status": "unsupported", "reason": "MinerU 未返回可核查版面", "findings": []}
            continue
        targets = [obj for obj in objects if obj.kind == target_kind]
        captions = [obj for obj in objects if obj.kind == caption_kind]
        by_page = {}
        for caption_index, caption in enumerate(captions):
            by_page.setdefault(caption.page_number, []).append((caption_index, caption))
        candidates = []
        for target_index, target in enumerate(targets):
            # _matches accepts same-page titles, next-page figure titles and
            # previous-page table titles only. Preserve original caption order.
            adjacent = target.page_number + (1 if target_kind == 'figure' else -1)
            local = by_page.get(target.page_number, []) + by_page.get(adjacent, [])
            for caption_index, caption in sorted(local):
                if not _matches(target, caption):
                    continue
                if document is not None and _body_between(target, caption, document, objects):
                    continue
                if target.page_number == caption.page_number:
                    gap = max(caption.bbox[1] - target.bbox[3],
                              target.bbox[1] - caption.bbox[3], 0)
                elif target.page_number < caption.page_number:
                    gap = target.page_height - target.bbox[3] + caption.bbox[1]
                else:
                    gap = caption.page_height - caption.bbox[3] + target.bbox[1]
                horizontal = abs((target.bbox[0] + target.bbox[2]) -
                                 (caption.bbox[0] + caption.bbox[2]))
                above_figure = int(target_kind == "figure"
                                   and target.page_number == caption.page_number
                                   and caption.bbox[3] <= target.bbox[1] + 2)
                candidates.append((abs(target.page_number - caption.page_number),
                                   above_figure, gap, horizontal, target_index, caption_index))
        matched_targets, matched_captions = set(), set()
        if target_kind == "figure":
            matched_targets = _figure_matches(_rank_figure_candidates(candidates, targets))
        else:
            # A table can also take the next table's closer title. Reassign
            # that title when an alternate valid title preserves both owners.
            matched_targets = _figure_matches(candidates)
        if document is not None:
            # Continue a physically split object only with evidence beyond distance.
            progress = True
            while progress:
                progress = False
                for index, target in enumerate(targets):
                    if index in matched_targets:
                        continue
                    if any(_continuation(target, targets[other], document, captions)
                           for other in matched_targets):
                        matched_targets.add(index)
                        progress = True
        findings = []
        for target_index, target in enumerate(targets):
            if target_index in matched_targets:
                continue
            findings.append({
                "rule_id": str(rule), "page": target.page_number,
                "message": f"{label}对象附近缺少{label}题",
                "text_excerpt": target.text,
                "location": _location(target),
            })
        result[str(rule)] = {"status": "completed", "findings": findings}
    return result


def _continuation(target, matched, document, captions=()):
    if target.kind != matched.kind or abs(target.page_number - matched.page_number) != 1:
        return False
    first, second = sorted((target, matched), key=lambda obj: obj.page_number)
    # A float can leave normal whitespace after a subpanel. Its identity is
    # established by consecutive panel labels and absence of intervening body,
    # rather than how far down the physical page that panel happens to reach.
    # Headerless table continuation still requires the original page-end gate.
    if ((first.kind == "table" and first.bbox[3] + 2 < first.page_height * 0.83)
            or second.bbox[1] > second.page_height * 0.25
            or _horizontal_overlap(first, second) < 0.8):
        return False
    pages = {page.number: page for page in document.pages}
    if first.kind == "figure":
        from .layout_context import _panel_match
        from .logical_objects import panel_label_lines
        def tags(obj, *, native=False):
            return {match.group(1).lower()
                    for line in panel_label_lines(pages[obj.page_number], [first, second], captions)
                    if not native or line.source == 'native'
                    if obj.bbox[1] <= line.bbox[1] <= obj.bbox[3] + 40
                    and obj.bbox[0] - 15 <= line.bbox[0] <= obj.bbox[2] + 15
                    if (match := _panel_match(line.text))}
        a, b = tags(first), tags(second)
        if not (a and b and ord(min(b)) == ord(max(a)) + 1):
            return False
        if not _body_between(first, second, document):
            return True
        return _counted_panel_continuation(first, second, tags(first, native=True),
                                           tags(second, native=True), captions, pages)
    if _body_between(first, second, document):
        return False
    def header(obj):
        lines = [line for line in pages[obj.page_number].lines
                 if obj.bbox[0] <= line.bbox[0] <= obj.bbox[2]
                 and obj.bbox[1] - 2 <= line.bbox[1] <= obj.bbox[1] + 45]
        if not lines:
            return ()
        top = min(line.bbox[1] for line in lines)
        return tuple(normalize_text(line.text).strip().lower() for line in sorted(lines, key=lambda line: line.bbox[0])
                     if abs(line.bbox[1] - top) < 8)
    a, b = header(first), header(second)
    if len(a) >= 2 and a == b and any(re.search(r'[A-Za-z\u4e00-\u9fff]', text) for text in a):
        return True
    if _source_table_continuation(first, second, pages):
        return True
    # The numeric fallback is specifically for a page beginning with data.
    # A different semantic header starts a different table, even if row keys
    # happen to continue the previous table's sequence.
    if any(not re.fullmatch(r'[+\-−]?\d+(?:\.\d+)?', text) for text in b):
        return False
    return _numeric_table_continuation(first, second, pages)


def _counted_panel_continuation(first, second, before, after, captions, pages):
    """An explicitly counted figure namespace can wrap around explanatory prose.

    Require the original introduction to cite the retained main title, every
    consecutive panel letter, and a separately observed physical body on each
    page. A nearby next-page title or a restarted (a) is insufficient.
    """
    from .numbering import FIGURE_REFERENCE, caption_match, normalize_label
    letters = sorted(before | after)
    if (len(letters) < 3 or before & after
            or letters != [chr(ord('a') + i) for i in range(len(letters))]):
        return False
    if not all(any(min(b[2], obj.bbox[2]) > max(b[0], obj.bbox[0])
                   and min(b[3], obj.bbox[3]) > max(b[1], obj.bbox[1])
                   for b in pages[obj.page_number].images + pages[obj.page_number].graphics)
               for obj in (first, second)):
        return False
    titles = [c for c in captions if c.kind == 'figure_caption'
              and c.page_number == second.page_number
              and 0 <= c.bbox[1] - second.bbox[3] <= 80
              and _matches(second, c)]
    if len(titles) != 1:
        return False
    title = caption_match(titles[0].text, 'figure')
    if title is None:
        return False
    number = normalize_label(title.group('number'))
    counts = {'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
              'seven': 7, 'eight': 8, 'nine': 9,
              '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6,
              '七': 7, '八': 8, '九': 9}
    for line in pages[first.page_number].lines:
        if (line.source != 'native' or line.bbox[3] > first.bbox[1]
                or first.bbox[1] - line.bbox[3] > 180):
            continue
        text = normalize_text(line.text)
        count = re.search(r'([二两三四五六七八九2-9])\s*(?:种|幅|个|组)|'
                          r'\b(two|three|four|five|six|seven|eight|nine|[2-9])\s+'
                          r'(?:methods|techniques|conditions|panels|cases)\b', text, re.I)
        if count is None:
            continue
        raw = count.group(1) or count.group(2)
        value = int(raw) if raw.isdigit() else counts[raw.lower()]
        if value == len(letters) and any(normalize_label(m.group('number')) == number
                                       for m in FIGURE_REFERENCE.finditer(text)):
            return True
    return False


def _source_table_continuation(first, second, pages):
    """A parser's spanning table must be corroborated by native next-page cells.

    Some parsers place the whole multi-page table text on its first body and
    leave the following body empty. Require several distinct cells absent
    from the first physical page, not just similar columns or common values.
    """
    if not first.text or second.text.strip():
        return False
    from .table_identity_repair import _semantic_column_header
    new_header = _semantic_column_header(second, pages[second.page_number])
    if new_header and new_header != _semantic_column_header(first, pages[first.page_number]):
        return False
    widths = [o.bbox[2]-o.bbox[0] for o in (first, second)]
    if min(widths)/max(widths) < .9:
        return False
    def clean(text):
        return re.sub(r'[\s_{}]', '', normalize_text(text)).casefold()
    def cells(obj):
        return {clean(line.text) for line in pages[obj.page_number].lines
                if obj.bbox[0] <= (line.bbox[0]+line.bbox[2])/2 <= obj.bbox[2]
                and obj.bbox[1] <= (line.bbox[1]+line.bbox[3])/2 <= obj.bbox[3]
                and len(clean(line.text)) >= 3}
    before, after = cells(first), cells(second)
    novel = after-before
    source = clean(first.text)
    supported = {cell for cell in novel if cell in source}
    return len(supported) >= 3 and len(supported) >= len(novel)*.8



def _numeric_table_continuation(first, second, pages):
    """A headerless continuation preserves columns and its ordered row key."""
    def rows(obj):
        result = []
        for line in sorted(pages[obj.page_number].lines, key=lambda l:(l.bbox[1],l.bbox[0])):
            cx = (line.bbox[0]+line.bbox[2])/2
            cy = (line.bbox[1]+line.bbox[3])/2
            if not (obj.bbox[0] <= cx <= obj.bbox[2] and obj.bbox[1] <= cy <= obj.bbox[3]):
                continue
            text = normalize_text(line.text).strip()
            if not re.fullmatch(r'[+\-−]?\d+(?:\.\d+)?', text):
                continue
            row = next((row for y,row in result if abs(cy-y) <= 5), None)
            if row is None:
                row=[]
                result.append((cy,row))
            row.append((cx, float(text.replace('−','-'))))
        return [sorted(row) for _,row in result if len(row) >= 3]
    before, after = rows(first), rows(second)
    if not before or len(after) < 2:
        return False
    a,b,c = before[-1],after[0],after[1]
    if len(a) != len(b) or len(b) != len(c):
        return False
    widths = [o.bbox[2]-o.bbox[0] for o in (first,second)]
    if min(widths)/max(widths) < .9:
        return False
    if any(abs((x-first.bbox[0])/widths[0]-(y-second.bbox[0])/widths[1]) > .035
           for (x,_),(y,_) in zip(a,b)):
        return False
    step = c[0][1]-b[0][1]
    return step > 0 and abs(b[0][1]-a[0][1]-step) < 1e-7

def _running_page_footer(line, page, document):
    if line.role in {'footer', 'page_number'}:
        return True
    # Native extraction has no footer role. Require a compact bottom page label
    # corroborated by the same printed format and advancing number next door.
    def printed_number(row, sheet):
        if (row.bbox[1] < sheet.height*.85 or row.bbox[2]-row.bbox[0] > sheet.width*.2
                or row.bbox[3]-row.bbox[1] > sheet.height*.025):
            return None
        text = re.sub(r'\s+', '', normalize_text(row.text))
        match = re.fullmatch(r'(第)([0-9]+)(页)|(Page)([0-9]+)', text, re.I)
        if not match:
            return None
        return (re.sub(r'[0-9]+', '#', text).lower(), int(match.group(2) or match.group(5)))
    current = printed_number(line, page)
    return bool(current and any(
        abs(other.bbox[1]-line.bbox[1]) <= 3
        and (value := printed_number(other, other_page))
        and value[0] == current[0] and value[1]-current[1] == other_page.number-page.number
        for other_page in document.pages if abs(other_page.number-page.number) == 1
        for other in other_page.lines))


def _caption_annotation(line, target, caption, page, observations=()):
    """A compact native legend/title continuation is not intervening body prose."""
    from .caption_context import body_font
    from .numbering import FIGURE_CAPTION, TABLE_CAPTION, normalize_label
    if target.kind.endswith('_caption'):
        target, caption = caption, target
    if target.kind not in {'figure', 'table'} or caption.kind != target.kind+'_caption':
        return False
    pattern = FIGURE_CAPTION if target.kind == 'figure' else TABLE_CAPTION
    printed = pattern.match(normalize_text(caption.text))
    if not printed or line.source != 'native' or not line.font_size:
        return False
    for anchor in page.lines:
        match = pattern.match(normalize_text(anchor.text))
        if (anchor.source != 'native' or not anchor.bold or not anchor.font_size
                or not match or not anchor.text_regions
                or normalize_label(match.group('number')) != normalize_label(printed.group('number'))):
            continue
        covered = {a for a, z, box in anchor.text_regions
                   if z-a == 1 and box[2] > box[0] and box[3] > box[1]}
        required = {i for i, char in enumerate(anchor.text[:match.end('number')]) if char.strip()}
        overlap = max(0, min(anchor.bbox[3], caption.bbox[3])-max(anchor.bbox[1], caption.bbox[1]))
        if not required <= covered or overlap < (anchor.bbox[3]-anchor.bbox[1])*.65:
            continue
        font = anchor.font_size
        if line.font_size > font*1.05:
            continue
        continued = line.bold and abs(line.font_size-font) <= font*.05
        typical = body_font(page)
        if not (continued or line.font_size < font*.92
                or (typical and line.font_size < typical*.92)):
            continue
        same_block = anchor.block_id is not None and line.block_id == anchor.block_id
        def compact(text):
            from unicodedata import normalize
            return re.sub(r'\s+', '', re.sub(r'<[^>]*>', '', normalize('NFKC', normalize_text(text)))).casefold()
        owned_note = any(
            o.kind == 'text' and o.page_number == page.number
            and o.role in {'table_caption', 'table_footnote', 'image_caption', 'image_footnote'}
            and target.parent_id and o.parent_id
            and (o.parent_id == target.parent_id or o.parent_id.startswith(target.parent_id+':'))
            and (compact(line.text) in compact(o.text)
                 or (len(re.sub(r'[^\u4e00-\u9fff]', '', line.text)) >= 12
                     and re.sub(r'[^\u4e00-\u9fff]', '', line.text)
                     in re.sub(r'[^\u4e00-\u9fff]', '', o.text)))
            and min(o.bbox[3],line.bbox[3])-max(o.bbox[1],line.bbox[1]) >= (line.bbox[3]-line.bbox[1])*.5
            for o in observations)
        columns = compact(target.text)
        descriptions = [line.text]
        descriptions.extend(o.text for o in observations
            if o.kind == 'text' and o.role == 'text' and o.page_number == page.number
            and compact(line.text) in compact(o.text)
            and min(o.bbox[3],line.bbox[3])-max(o.bbox[1],line.bbox[1]) >= (line.bbox[3]-line.bbox[1])*.5)
        definition = False
        if target.kind == 'table':
            for description in descriptions:
                terms = re.findall(r'[“"‘]([^”"’]{3,})[”"’]|\b([A-Za-z][A-Za-z0-9._/-]{2,})\b', description)
                defines = re.search(r'表示|代表|意为|\b(?:denotes?|means?|represents?|indicates?)\b', description, re.I)
                formatting = re.search(r'(?:加粗|下划线).{0,12}(?:数值|结果|表示)', description)
                if formatting or (defines and any(compact(a or b).strip('.') in columns for a,b in terms)):
                    definition = True
                    break
        if not (continued or same_block or owned_note or definition):
            continue
        centre = (line.bbox[0]+line.bbox[2])/2
        visual_centre = (target.bbox[0]+target.bbox[2])/2
        if abs(centre-visual_centre) > max(font*2.5, (target.bbox[2]-target.bbox[0])*.08):
            continue
        title_gap = max(line.bbox[1]-caption.bbox[3], caption.bbox[1]-line.bbox[3], 0)
        visual_gap = max(line.bbox[1]-target.bbox[3], target.bbox[1]-line.bbox[3], 0)
        if min(title_gap, visual_gap) <= font*3:
            return True
    return False


def _body_between(left, right, document, observations=()):
    if left.page_number == right.page_number:
        # Source-proved ownership can include internal explanatory text.
        from .mineru_layout import caption_identity
        if ((getattr(left, 'caption_owner_id', '')
             and left.caption_owner_id == caption_identity(right))
                or (getattr(right, 'caption_owner_id', '')
                    and right.caption_owner_id == caption_identity(left))):
            return False
        upper, lower = sorted((left, right), key=lambda obj: obj.bbox[1])
        if upper.bbox[3] > lower.bbox[1]:
            return False
        from .layout_context import _panel_match
        from .mineru_layout import _caption_kind
        page = next(p for p in document.pages if p.number == left.page_number)
        return any(line.source == 'native'
                   and upper.bbox[3] <= line.bbox[1] < line.bbox[3] <= lower.bbox[1]
                   and line.bbox[2] - line.bbox[0] >= page.width * .45
                   and len(re.findall(r'[A-Za-z\u4e00-\u9fff]', line.text)) >= 12
                   and not _caption_kind(line.text) and not _panel_match(line.text)
                   and not _running_page_footer(line, page, document)
                   and not _caption_annotation(line, left, right, page, observations)
                   for line in page.lines)
    first, second = sorted((left, right), key=lambda obj: obj.page_number)
    for page in document.pages:
        if page.number not in {first.page_number, second.page_number}:
            continue
        for line in page.lines:
            if _running_page_footer(line, page, document):
                continue
            if line.bbox[1] <= page.height * 0.08 or line.bbox[3] >= page.height * 0.95:
                continue  # Running headers and page numbers do not separate an object.
            # A mirrored running header may sit below the fixed 8% margin.
            # Confirm it repeats on the other page at the same vertical level.
            running = line.bbox[1] < page.height*.11 and any(
                other_page.number != page.number and other_page.number in {first.page_number, second.page_number}
                and any(normalize_text(other.text).strip() == normalize_text(line.text).strip()
                        and abs(other.bbox[1]-line.bbox[1]) <= 12 for other in other_page.lines)
                for other_page in document.pages)
            if running:
                continue
            in_gap = (page.number == first.page_number and line.bbox[1] >= first.bbox[3]
                      or page.number == second.page_number and line.bbox[3] <= second.bbox[1])
            text = normalize_text(line.text).strip()
            if (in_gap and re.search(r"[A-Za-z\u4e00-\u9fff]", text)
                    and not re.match(r"^(?:续表|续图|(?:Table|Figure)\s+.+[Cc]ontinued|[（(][a-z][）)])", text, re.I)):
                return True
    return False
