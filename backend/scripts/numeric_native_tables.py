"""Read-only, page-local table alternatives grounded in native PDF geometry."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
from statistics import median
from types import SimpleNamespace


_CAPTION = re.compile(r'^(?:表\s*\d|Table\s+\d)', re.I)
_TABLE_LABEL = re.compile(r'^(?:表\s*|Table\s*)\d+(?:\s*[.\-]\s*\d+)*\s*[:：.]?$', re.I)
_ANY_CAPTION = re.compile(r'^(?:(?:表|图)\s*\d|(?:Table|Figure|Fig[.]?)\s*\d)', re.I)
_NUMBER = re.compile(r'^[\d\s.,%+\-−±×*<>=≤≥~()]+$')


def _rect(box):
    try:
        values = [float(v) for v in box]
        return values if len(values) == 4 and values[0] <= values[2] and values[1] <= values[3] else None
    except (TypeError, ValueError):
        return None


def _union(boxes):
    boxes = [b for b in boxes if b]
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)] if boxes else None


def _clean(text):
    return re.sub(r'\s+', ' ', str(text or '')).strip()


def _inside(inner, outer, tolerance=1.5):
    return (outer[0] - tolerance <= (inner[0] + inner[2]) / 2 <= outer[2] + tolerance
            and outer[1] - tolerance <= (inner[1] + inner[3]) / 2 <= outer[3] + tolerance)


def _overlap_x(left, right):
    width = min(left[2], right[2]) - max(left[0], right[0])
    return max(0, width) / max(1, min(left[2] - left[0], right[2] - right[0]))


def _wide_caption_box(text, box, fragments, table_box):
    """A contiguous, centred title row may extend beyond a narrow ruled table."""
    if not _TABLE_LABEL.fullmatch(text.strip()):
        return None
    height, baseline = max(1, box[3] - box[1]), (box[1] + box[3]) / 2
    if not -1.5 <= table_box[1] - box[3] <= max(36, min(80, height * 6)):
        return None
    adjacent = [f for f in fragments if f['bbox'][0] >= box[2] - 1
                and abs((f['bbox'][1] + f['bbox'][3]) / 2 - baseline) <= max(
                    2, min(height, f['bbox'][3] - f['bbox'][1]) * .25)
                and min(box[3], f['bbox'][3]) - max(box[1], f['bbox'][1]) >= min(
                    height, f['bbox'][3] - f['bbox'][1]) * .6]
    boxes, right = [box], box[2]
    for fragment in sorted(adjacent, key=lambda f: (f['bbox'][0], f['bbox'][2])):
        if (not -1 <= fragment['bbox'][0] - right <= max(12, height * 1.6)
                or _ANY_CAPTION.match(fragment['text'].strip())):
            break
        boxes.append(fragment['bbox'])
        right = fragment['bbox'][2]
    extent = _union(boxes)
    if (len(boxes) > 1 and _overlap_x(extent, table_box) >= .3
            and abs((extent[0] + extent[2] - table_box[0] - table_box[2]) / 2)
                <= max(12, (table_box[2] - table_box[0]) * .15)):
        return extent
    return None


def _fragments(page):
    """Keep exact native span character offsets; split only visible wide gutters."""
    fragments = []
    for bi, block in enumerate(page.get_text('rawdict').get('blocks', [])):
        for li, line in enumerate(block.get('lines', [])):
            if tuple(line.get('dir', (1, 0))) != (1, 0):
                continue
            chars = []
            for si, span in enumerate(line.get('spans', [])):
                for ci, char in enumerate(span.get('chars', [])):
                    if _rect(char.get('bbox')):
                        chars.append((char, si, ci, float(span.get('size', 10))))
            if not chars:
                continue
            groups, current = [], []
            for item in chars:
                if current and item[0]['bbox'][0] - current[-1][0]['bbox'][2] > max(3, item[3] * .7):
                    groups.append(current)
                    current = []
                current.append(item)
            if current:
                groups.append(current)
            for group in groups:
                while group and group[0][0]['c'].isspace():
                    group.pop(0)
                while group and group[-1][0]['c'].isspace():
                    group.pop()
                if not group:
                    continue
                sources = []
                for char, si, ci, _ in group:
                    if sources and sources[-1]['span_index'] == si and sources[-1]['char_end'] == ci:
                        source = sources[-1]
                        source['text'] += char['c']
                        source['char_end'] = ci + 1
                        source['bbox'] = _union([source['bbox'], _rect(char['bbox'])])
                    else:
                        sources.append({'block_index': bi, 'line_index': li, 'span_index': si,
                                        'char_start': ci, 'char_end': ci + 1,
                                        'text': char['c'], 'bbox': _rect(char['bbox'])})
                fragments.append({'text': ''.join(c[0]['c'] for c in group),
                                  'bbox': _union([_rect(c[0]['bbox']) for c in group]),
                                  'native_spans': sources})
    return fragments


def _rules(page):
    horizontal, vertical = [], []
    for drawing in page.get_drawings():
        for item in drawing.get('items', []):
            if item[0] == 'l':
                x0, y0, x1, y1 = item[1].x, item[1].y, item[2].x, item[2].y
                if abs(y1 - y0) <= 1 and abs(x1 - x0) >= 40:
                    horizontal.append([min(x0, x1), (y0 + y1) / 2, max(x0, x1)])
                elif abs(x1 - x0) <= 1 and abs(y1 - y0) >= 4:
                    vertical.append([(x0 + x1) / 2, min(y0, y1), max(y0, y1)])
            elif item[0] == 're':
                box = _rect(item[1])
                if box and box[2] - box[0] >= 40 and box[3] - box[1] <= 2:
                    horizontal.append([box[0], (box[1] + box[3]) / 2, box[2]])
    return horizontal, vertical


def _regions(horizontal, fragments):
    """Three aligned rulings establish a region; intervening captions split it."""
    groups = []
    for rule in sorted(horizontal, key=lambda r: (r[0], r[2], r[1])):
        if rule[2] - rule[0] < 100:
            continue
        group = next((g for g in groups if abs(g[0][0] - rule[0]) <= 2
                      and abs(g[0][2] - rule[2]) <= 2), None)
        if group is None:
            groups.append([rule])
        elif all(abs(old[1] - rule[1]) > 1.5 for old in group):
            group.append(rule)
    regions = []
    for rules in groups:
        ordered = sorted(rules, key=lambda r: r[1])
        parts, part = [], []
        for rule in ordered:
            split = part and (rule[1] - part[-1][1] > 260 or any(
                _CAPTION.search(f['text']) and part[-1][1] < f['bbox'][1] < rule[1]
                and _overlap_x(f['bbox'], [rule[0], 0, rule[2], 1]) >= .3 for f in fragments))
            if split:
                parts.append(part)
                part = []
            part.append(rule)
        parts.append(part)
        for part in parts:
            if len(part) >= 3 and part[-1][1] - part[0][1] >= 25:
                regions.append(([part[0][0], part[0][1], part[0][2], part[-1][1]], part))
    return sorted(regions, key=lambda r: (r[0][1], r[0][0]))


def _physical_rows(fragments):
    rows = []
    for fragment in sorted(fragments, key=lambda f: ((f['bbox'][1] + f['bbox'][3]) / 2, f['bbox'][0])):
        center = (fragment['bbox'][1] + fragment['bbox'][3]) / 2
        tolerance = max(2.5, (fragment['bbox'][3] - fragment['bbox'][1]) * .3)
        row = next((r for r in reversed(rows) if abs(r['center'] - center) <= tolerance), None)
        if row is None:
            row = {'center': center, 'fragments': []}
            rows.append(row)
        row['fragments'].append(fragment)
        row['center'] = median((f['bbox'][1] + f['bbox'][3]) / 2 for f in row['fragments'])
    for row in rows:
        row['fragments'].sort(key=lambda f: f['bbox'][0])
    return rows


def _numeric(fragment):
    text = fragment['text'].strip()
    return bool(re.search(r'\d', text) and _NUMBER.fullmatch(text))


def _columns(fragments):
    intervals = []
    for fragment in sorted(fragments, key=lambda f: f['bbox'][0]):
        left, right = fragment['bbox'][0], fragment['bbox'][2]
        if intervals and left <= intervals[-1][1] + 1:
            intervals[-1][1] = max(intervals[-1][1], right)
        else:
            intervals.append([left, right])
    return intervals


def _column_coverage(fragment, columns, siblings, bbox, vertical, horizontal):
    center = (fragment['bbox'][0] + fragment['bbox'][2]) / 2
    ycenter = (fragment['bbox'][1] + fragment['bbox'][3]) / 2
    leaf_matches = [i for i, (x0, x1) in enumerate(columns) if x0 - 2 <= center <= x1 + 2]
    if len(siblings) >= len(columns) - 1 and len(leaf_matches) == 1:
        return leaf_matches
    boundaries = [bbox[0], bbox[2]] + list({x for x, y0, y1 in vertical
        if bbox[0] + 1 < x < bbox[2] - 1 and y0 - 3 <= ycenter <= y1 + 3})
    if len(boundaries) > 2:
        # Enclosing native cell boundaries are stronger than a separator spanning
        # several sibling header cells on the same baseline.
        left = max((x for x in boundaries if x < center), default=bbox[0])
        right = min((x for x in boundaries if x > center), default=bbox[2])
        return [i for i, (x0, x1) in enumerate(columns) if left <= (x0 + x1) / 2 <= right]
    below = [rule for rule in horizontal if rule[0] <= center <= rule[2]
             and -.5 <= rule[1] - fragment['bbox'][3] <= 8
             and rule[2] - rule[0] < bbox[2] - bbox[0] - 3
             and bbox[0] - 2 <= rule[0] < rule[2] <= bbox[2] + 2]
    if below:
        rule = min(below, key=lambda r: (abs(r[1] - fragment['bbox'][3]), r[2] - r[0]))
        coverage = [i for i, (x0, x1) in enumerate(columns) if rule[0] <= (x0 + x1) / 2 <= rule[2]]
        if coverage:
            return coverage
    if len(boundaries) == 2 and len(leaf_matches) == 1:
        sibling_matches = []
        for sibling in sorted(siblings, key=lambda f: f['bbox'][0]):
            sibling_center = (sibling['bbox'][0] + sibling['bbox'][2]) / 2
            matches = [i for i, (x0, x1) in enumerate(columns) if x0 - 2 <= sibling_center <= x1 + 2]
            if len(matches) != 1:
                break
            sibling_matches.append(matches[0])
        # Row-label or leaf cells can sit between parent/leaf header levels.
        # A group centred over the middle numeric column is still a parent label.
        if (len(sibling_matches) == len(siblings) and sibling_matches
                and (len(siblings) > 1 or sibling_matches[0] == 0)
                and sibling_matches == list(range(sibling_matches[0], sibling_matches[0] + len(siblings)))):
            return leaf_matches
    left = max((x for x in boundaries if x < center), default=bbox[0])
    right = min((x for x in boundaries if x > center), default=bbox[2])
    if len(boundaries) == 2:
        centers = sorted((f['bbox'][0] + f['bbox'][2]) / 2 for f in siblings)
        pos = centers.index(center)
        left = (centers[pos - 1] + center) / 2 if pos else bbox[0]
        right = (centers[pos + 1] + center) / 2 if pos < len(centers) - 1 else bbox[2]
    coverage = [i for i, (x0, x1) in enumerate(columns) if left <= (x0 + x1) / 2 <= right]
    if len(coverage) > 1 and len(boundaries) == 2:
        child_centers = [(columns[i][0] + columns[i][1]) / 2 for i in coverage]
        gap = median(b - a for a, b in zip(child_centers, child_centers[1:]))
        # Midpoint grouping alone cannot justify a visibly off-centre group label.
        if abs(center - (child_centers[0] + child_centers[-1]) / 2) > max(12, gap * .4):
            return []
    return coverage


def _native_grid(bbox, full_rules, fragments, vertical, horizontal):
    inside = [f for f in fragments if _inside(f['bbox'], bbox)]
    physical = _physical_rows(inside)
    data = [r for r in physical if sum(_numeric(f) for f in r['fragments']) >= 2]
    single_metric = len(data) < 2
    if single_metric:
        data = [r for r in physical if len(r['fragments']) == 2
                and not _numeric(r['fragments'][0]) and _numeric(r['fragments'][1])]
    if len(data) < 2:
        return None
    first_data = data[0]['center']
    header_end = max((r[1] for r in full_rules if r[1] < first_data - 2), default=bbox[1])
    header_rows = [r for r in physical if r['center'] < header_end]
    body = [f for f in inside if (f['bbox'][1] + f['bbox'][3]) / 2 > header_end]
    columns = _columns(body)
    if not 2 <= len(columns) <= 40 or (single_metric and len(columns) != 2):
        return None
    # Rows require aligned native result cells. Isolated group labels remain spans.
    body_rows = [r for r in physical if r['center'] > header_end
                 and any(_numeric(f) for f in r['fragments'])]
    if len(body_rows) < 2:
        return None
    rows = header_rows + body_rows
    matrix = [[None for _ in columns] for _ in rows]
    cells = [[None for _ in columns] for _ in rows]
    paths = [[] for _ in columns]
    spanning, uncertain_headers = [], False
    for ri, row in enumerate(rows):
        for fragment in row['fragments']:
            is_header = ri < len(header_rows)
            if is_header:
                coverage = _column_coverage(fragment, columns, row['fragments'], bbox, vertical, horizontal)
                if not coverage:
                    uncertain_headers = True
                    coverage = [min(range(len(columns)), key=lambda i: abs(
                        (columns[i][0] + columns[i][1] - fragment['bbox'][0] - fragment['bbox'][2]) / 2))]
                else:
                    for ci in coverage:
                        paths[ci].append(fragment['text'])
            else:
                coverage = [ci for ci, (x0, x1) in enumerate(columns)
                            if x0 - 1 <= (fragment['bbox'][0] + fragment['bbox'][2]) / 2 <= x1 + 1]
            if len(coverage) != 1 and not is_header:
                uncertain_headers = True
                continue
            if not coverage:
                continue
            ci = coverage[0]
            if cells[ri][ci] is not None:
                uncertain_headers = True
            matrix[ri][ci] = _clean(fragment['text'])
            cells[ri][ci] = fragment
            if is_header and len(coverage) > 1:
                spanning.append(dict(deepcopy(fragment), role='header', row_indices=[ri], column_indices=coverage,
                                     grounding='native_header_geometry'))
    # Group labels have an explicit native ruling interval covering several rows.
    # Do not forward-fill their text into unrelated physical source cells.
    for ci, (x0, x1) in enumerate(columns):
        for top_rule, bottom_rule in zip(full_rules, full_rules[1:]):
            top, bottom = top_rule[1], bottom_rule[1]
            if top < header_end - 1:
                continue
            indices = [ri for ri, row in enumerate(rows) if top < row['center'] < bottom and ri >= len(header_rows)]
            column_fragments = [f for f in body if top < (f['bbox'][1] + f['bbox'][3]) / 2 < bottom
                                and x0 - 1 <= (f['bbox'][0] + f['bbox'][2]) / 2 <= x1 + 1]
            if len(indices) > 1 and len(column_fragments) == 1:
                fragment = column_fragments[0]
                # A solitary number is never inferred to cover multiple rows.
                if _numeric(fragment):
                    continue
                center = (fragment['bbox'][1] + fragment['bbox'][3]) / 2
                if abs(center - (top + bottom) / 2) > max(4, (fragment['bbox'][3] - fragment['bbox'][1]) * .5):
                    continue
                spanning.append(dict(deepcopy(fragment), role='body', row_indices=indices,
                                     column_indices=[ci], grounding='native_ruling_boundaries'))
                for ri in indices:
                    if cells[ri][ci] is fragment:
                        cells[ri][ci], matrix[ri][ci] = None, None
    proxy_rows = []
    for row_cells in cells:
        boxes = [f['bbox'] if f else None for f in row_cells]
        proxy_rows.append(SimpleNamespace(bbox=_union(boxes), cells=boxes))
    proxy = SimpleNamespace(bbox=bbox, rows=proxy_rows,
                            header=SimpleNamespace(names=[' / '.join(p) for p in paths]),
                            extract=lambda: deepcopy(matrix))
    represented = {(f['text'], tuple(f['bbox'])) for row in cells for f in row if f}
    represented.update((f['text'], tuple(f['bbox'])) for f in spanning)
    missing_source = any((f['text'], tuple(f['bbox'])) not in represented for f in inside)
    return proxy, cells, paths, spanning, (uncertain_headers or missing_source
                                          or not header_rows or any(not path for path in paths))


def _bind_source(structure, model, fragments):
    bbox, page = structure['bbox'], structure['page']
    candidates = []
    for block in model.get('blocks', []):
        if block.get('page') != page:
            continue
        text = str(block.get('text') or '').strip()
        for provenance in block.get('provenance') or []:
            box = _rect(provenance.get('bbox'))
            if not box or not -8 <= bbox[1] - box[3] <= 180:
                continue
            if _overlap_x(box, bbox) < .3 and not _wide_caption_box(text, box, fragments, bbox):
                continue
            native = ' '.join(f['text'] for f in fragments if _inside(f['bbox'], box))
            if re.sub(r'\s+', '', text) not in re.sub(r'\s+', '', native):
                continue
            is_caption = bool(_CAPTION.search(text)) or block.get('block_type') == 'Caption'
            # A nearer native caption is an identity boundary, even if the IR lacks it.
            if any(_CAPTION.search(f['text']) and box[3] + 2 < f['bbox'][1] < bbox[1]
                   and (_overlap_x(f['bbox'], bbox) >= .3
                        or _wide_caption_box(f['text'], f['bbox'], fragments, bbox))
                   for f in fragments):
                continue
            candidates.append((not is_caption, abs(bbox[1] - box[3]), block))
    if candidates:
        _, _, selected = min(candidates, key=lambda x: x[:2])
        structure['caption'] = str(selected.get('text') or '')
        structure['section_id'] = selected.get('section_id')
        structure['source_node_ids'] = [selected['source_node_id']] if selected.get('source_node_id') else []
    else:
        structure.update(caption='', section_id=None, source_node_ids=[])
    if not structure.get('section_id') or not structure.get('source_node_ids'):
        _limit(structure, 'no_paper_model_source_binding')


def _limit(structure, reason):
    structure['reliability'] = 'limited'
    if reason not in structure.setdefault('limitations', []):
        structure['limitations'].append(reason)


def _attach_native(structure, fragments, native_cells=None):
    grounded = True
    for ri, row in enumerate(structure.get('rows', [])):
        for ci, cell in enumerate(row.get('cells', [])):
            if native_cells is not None:
                fragment = native_cells[ri][ci]
                sources = deepcopy(fragment['native_spans']) if fragment else []
            else:
                box = _rect(cell.get('bbox'))
                sources = [deepcopy(s) for f in fragments if box and _inside(f['bbox'], box)
                           for s in f['native_spans']]
            cell['native_spans'] = sources
            if cell.get('text') and re.sub(r'\s+', '', str(cell['text'])) != re.sub(
                    r'\s+', '', ''.join(s['text'] for s in sources)):
                grounded = False
    structure['native_cells_grounded'] = grounded
    if not grounded:
        _limit(structure, 'native_cell_text_not_grounded')


def compact_table_context(table):
    """Small source-context payload; exact character provenance stays in the trace."""
    return {'native_header_paths': deepcopy(table.get('native_header_paths', [])),
            'native_spanning_cells': [{key: deepcopy(cell[key]) for key in
                ('role', 'text', 'row_indices', 'column_indices', 'grounding') if key in cell}
                for cell in table.get('native_spanning_cells', [])],
            'native_cells_grounded': bool(table.get('native_cells_grounded'))}


def native_caption_context(table, model):
    """Return exact caption/title blocks joined only by their native row geometry."""
    table_box = _rect(table.get('bbox'))
    page = table.get('page')
    identities = set(table.get('source_node_ids') or [])
    if not table_box or type(page) is not int or not identities:
        return []
    number = r'\d+(?:\s*[.\-]\s*\d+)*'
    table_prefix = re.compile(r'^(?:表\s*|Table\s*)(' + number + r')', re.I)
    label_only = re.compile(r'^(?:表\s*|Table\s*)' + number + r'\s*[:：.]?$', re.I)
    any_caption = re.compile(r'^(?:(表|图)\s*|(?:Table|Figure|Fig[.]?)\s*)(' + number + r')', re.I)
    fields = ('text', 'source_node_id', 'block_id', 'page', 'provenance', 'section_id')
    blocks, native_blocks = [], []
    for block in model.get('blocks') or []:
        if (block.get('page') != page or not isinstance(block.get('text'), str)
                or not block['text'].strip() or not block.get('block_id')
                or not block.get('source_node_id')):
            continue
        boxes = [_rect(p.get('bbox')) for p in block.get('provenance') or []]
        if boxes and all(boxes):
            native_blocks.append((block, _union(boxes), boxes))
            multirow = any(abs((b[1] + b[3] - boxes[0][1] - boxes[0][3]) / 2) > 2 for b in boxes)
            full_anchor = (block['source_node_id'] in identities
                           and table_prefix.match(block['text'].strip())
                           and all(b[3] <= table_box[1] + 1 for b in boxes))
            if not multirow or full_anchor:
                blocks.append((block, _union(boxes), boxes))
                continue
            parts = block['text'].split('\n')
            provenance = block['provenance']
            if len(parts) != len(provenance) or not all(
                    type(p.get('node_text_start')) is int and type(p.get('node_text_end')) is int
                    and p['node_text_end'] - p['node_text_start'] == len(part)
                    for part, p in zip(parts, provenance)):
                continue
            for part, source, source_box in zip(parts, provenance, boxes):
                projected = dict(block, text=part, provenance=[source])
                blocks.append((projected, source_box, [source_box]))
    anchors = [(block, box, boxes) for block, box, boxes in blocks
               if block['source_node_id'] in identities and table_prefix.match(block['text'].strip())]
    caption_fragments = [{'text': block['text'], 'bbox': box} for block, box, _ in blocks]
    result, seen = [], set()

    def emit(block):
        if block['block_id'] not in seen:
            seen.add(block['block_id'])
            result.append(deepcopy({key: block[key] for key in fields if key in block}))

    for anchor, box, _ in sorted(anchors, key=lambda entry: (entry[1][1], entry[1][0])):
        height = max(1, box[3] - box[1])
        caption_box = box
        if _overlap_x(box, table_box) < .3:
            caption_box = _wide_caption_box(anchor['text'], box,
                [{'text': other['text'], 'bbox': other_box} for other, other_box, _ in blocks
                 if other.get('section_id') == anchor.get('section_id')], table_box)
        if (not -1.5 <= table_box[1] - box[3] <= max(36, min(80, height * 6))
                or not caption_box):
            continue
        identity = re.sub(r'\s+', '', table_prefix.match(anchor['text'].strip())[1]).replace('-', '.')
        # A different intervening caption is an identity boundary. The same
        # table's bilingual label may lie below the selected native label.
        blocked = False
        for other, other_box, _ in native_blocks:
            caption = any_caption.match(other['text'].strip())
            if (other['block_id'] == anchor['block_id'] or not caption
                    or not box[3] + 2 < other_box[1] < table_box[1]
                    or (_overlap_x(other_box, table_box) < .3
                        and not _wide_caption_box(other['text'], other_box, caption_fragments, table_box))):
                continue
            same_table = table_prefix.match(other['text'].strip())
            if (not same_table or re.sub(r'\s+', '', same_table[1]).replace('-', '.') != identity):
                blocked = True
                break
        if blocked:
            continue
        emit(anchor)
        if not label_only.fullmatch(anchor['text'].strip()):
            continue
        baseline = (box[1] + box[3]) / 2
        padding, max_gap = max(12, height * 2), max(12, height * 1.6)
        adjacent = []
        for other, other_box, other_boxes in blocks:
            if (other['block_id'] == anchor['block_id']
                    or (other.get('section_id') != anchor.get('section_id')
                        and not any_caption.match(other['text'].strip()))
                    or other_box[0] < box[2] - 1
                    or other_box[0] < min(table_box[0], caption_box[0]) - padding
                    or other_box[2] > max(table_box[2], caption_box[2]) + padding
                    or other_box[3] > table_box[1] + 1):
                continue
            if all(abs((b[1] + b[3]) / 2 - baseline) <= max(2, min(height, b[3] - b[1]) * .25)
                   and min(box[3], b[3]) - max(box[1], b[1]) >= min(height, b[3] - b[1]) * .6
                   for b in other_boxes):
                adjacent.append((other, other_box))
        right = box[2]
        for other, other_box in sorted(adjacent, key=lambda entry: (entry[1][0], entry[1][2])):
            if other_box[0] - right > max_gap or other_box[0] < right - 1:
                break
            if any_caption.match(other['text'].strip()):
                break
            emit(other)
            right = other_box[2]
    return result


def preferred_table_alternatives(tables):
    """Suppress only fully covered, explicitly bound inferior source readings."""
    def safe(table):
        matrix = table.get('matrix') or []
        return (table.get('native_cells_grounded') is True and not table.get('cross_page')
                and not (set(table.get('limitations') or []) - {'merged_or_multilevel_header_cells'})
                and table.get('row_count') == len(matrix) and bool(matrix)
                and all(len(row) == table.get('column_count') for row in matrix)
                and any(table.get('native_header_paths') or table.get('column_headers') or []))

    def characters(table):
        cells = [cell for row in table.get('rows') or [] for cell in row.get('cells') or []]
        cells += table.get('native_spanning_cells') or []
        return {(s.get('block_index'), s.get('line_index'), s.get('span_index'), position)
                for cell in cells
                for s in cell.get('native_spans') or []
                for position in range(s.get('char_start', 0), s.get('char_end', 0))}

    rank = lambda table: ({'native_rules': 0, 'lines': 1, 'text': 2}.get(table.get('strategy'), 3),
                          tables.index(table))
    grounded = [table for table in tables if safe(table)]
    keys = {id(table): characters(table) for table in tables}
    kept = []
    for table in tables:
        covered = False
        for other in grounded:
            if other is table or (safe(table) and rank(other) >= rank(table)):
                continue
            if (table.get('page') != other.get('page')
                    or table.get('section_id') != other.get('section_id')
                    or not table.get('source_node_ids')
                    or table['source_node_ids'] != other.get('source_node_ids')
                    or table.get('table_id') not in (other.get('same_source_alternatives') or [])):
                continue
            source, complete = keys[id(table)], keys[id(other)]
            # A partial overlap is not full coverage: it might hide a larger row.
            if source and source <= complete:
                covered = True
            elif (not source and not complete and table.get('bbox') == other.get('bbox')
                    and table.get('raw_matrix', table.get('matrix')) == other.get('raw_matrix', other.get('matrix'))):
                covered = True
            if covered:
                break
        if not covered:
            kept.append(table)
    return kept


def recover_native_tables(pdf_path, model, structure_builder, *, version):
    """Keep line/text alternatives and recover grids only inside native ruling bounds."""
    diagnostics = {'version': version, 'attempted_pages': 0, 'successes': 0, 'failures': []}
    tables = []
    if not pdf_path or not Path(pdf_path).is_file():
        diagnostics['failures'].append({'reason': 'pdf_source_unavailable'})
        return tables, diagnostics
    try:
        import fitz
        document = fitz.open(str(pdf_path))
    except Exception as exc:
        diagnostics['failures'].append({'reason': 'pdf_open_failed', 'error': type(exc).__name__})
        return tables, diagnostics
    try:
        for page_index, page in enumerate(document):
            diagnostics['attempted_pages'] += 1
            page_number, page_tables = page_index + 1, []
            try:
                fragments = _fragments(page)
                horizontal, vertical = _rules(page)
                for bbox, rules in _regions(horizontal, fragments):
                    grid = _native_grid(bbox, rules, fragments, vertical, horizontal)
                    if not grid:
                        continue
                    proxy, cells, paths, spanning, uncertain = grid
                    structure, failure = structure_builder(proxy, page_number, len(page_tables) + 1,
                        model, float(page.rect.height), page=page)
                    if failure or not structure:
                        continue
                    structure.update(strategy='native_rules', detection='native_ruling_geometry',
                        raw_matrix=proxy.extract(), native_header_paths=paths, native_spanning_cells=spanning,
                        native_rulings=[list(rule) for rule in rules])
                    _attach_native(structure, fragments, cells)
                    _bind_source(structure, model, fragments)
                    if uncertain:
                        _limit(structure, 'ambiguous_native_header_relationships')
                    page_tables.append(structure)
            except Exception as exc:
                diagnostics['failures'].append({'page': page_number, 'strategy': 'native_rules',
                                                'reason': type(exc).__name__})
                fragments = []
            # Consume each finder immediately: PyMuPDF table extraction uses finder-local state.
            for strategy in ('lines', 'text'):
                try:
                    found = list(page.find_tables(strategy=strategy).tables)
                    diagnostics.setdefault('strategy_counts', {}).setdefault(strategy, 0)
                    diagnostics['strategy_counts'][strategy] += len(found)
                    for table in found:
                        raw = deepcopy(table.extract() or [])
                        structure, failure = structure_builder(table, page_number, len(page_tables) + 1,
                            model, float(page.rect.height), page=page)
                        if failure or not structure:
                            diagnostics['failures'].append({'page': page_number, 'strategy': strategy,
                                                            'reason': failure or 'empty_table'})
                            continue
                        structure.update(strategy=strategy, raw_matrix=raw,
                            detection='default_lines' if strategy == 'lines' else 'text_mode')
                        _attach_native(structure, fragments)
                        _bind_source(structure, model, fragments)
                        if strategy == 'lines' and any('\n' in str(cell or '') for row in raw[1:] for cell in row):
                            _limit(structure, 'multiline_cell_relationships_unresolved')
                        if strategy == 'text':
                            _limit(structure, 'unconfirmed_text_table_relationships')
                        page_tables.append(structure)
                except Exception as exc:
                    diagnostics['failures'].append({'page': page_number, 'strategy': strategy,
                                                    'reason': type(exc).__name__})
            # Alternative identities require both the same geometry and native source characters.
            for table in page_tables:
                source_keys = {(s['block_index'], s['line_index'], s['span_index'], s['char_start'], s['char_end'])
                               for row in table['rows'] for cell in row['cells'] for s in cell.get('native_spans', [])}
                alternatives = []
                for other in page_tables:
                    if other is table or table['source_node_ids'] != other['source_node_ids']:
                        continue
                    a, b = table['bbox'], other['bbox']
                    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
                    area = max(1, (a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
                    other_keys = {(s['block_index'], s['line_index'], s['span_index'], s['char_start'], s['char_end'])
                                  for row in other['rows'] for cell in row['cells'] for s in cell.get('native_spans', [])}
                    if intersection / area >= .7 and source_keys and len(source_keys & other_keys) / max(len(source_keys), len(other_keys)) >= .7:
                        alternatives.append(other['table_id'])
                table['same_source_alternatives'] = alternatives
            tables.extend(page_tables)
            diagnostics['successes'] += len(page_tables)
    finally:
        document.close()
    return tables, diagnostics
