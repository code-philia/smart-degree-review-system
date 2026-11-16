"""Numeric-rule-only navigation view, grounded in PDF outline destinations and native lines.

The shared Paper Model is not rewritten. Every derived range retains native line/node IDs.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import re


VERSION = 'numeric-navigation/1.2'


def title_key(text):
    text = re.sub(r'\s+', '', text).casefold()
    text = re.sub(r'^(?:第[一二三四五六七八九十百\d]+章|chapter\d+|\d+(?:\.\d+)*[.:：]?)', '', text)
    return text.strip(':：.、')



_CHAPTER = re.compile(r'^(?:第\s*([一二三四五六七八九十百\d]+)\s*章|chapter\s+(\d+))\s*[:：.、]?\s*(.*)$', re.I)
_SUBSECTION = re.compile(r'^(\d+(?:\.\d+){1,3})(?:\s+|(?=[\u3400-\u9fff]))(.*)$')
_LEADER = re.compile(r'(?:\.\s*){3,}|…{2,}|⋯')
_END_TITLE = re.compile(r'^(?:参考文献|致谢|附录(?:\s*[A-Z一二三四五六七八九十\d])?|Bibliography|References|Acknowledg(?:e)?ments|Appendix(?:\s+[A-Z])?)$', re.I)


def _chapter_number(value):
    if value.isdecimal():
        return int(value)
    digits = dict(zip('一二三四五六七八九', range(1, 10)))
    if value == '十':
        return 10
    if '十' in value and len(value) <= 3:
        tens, units = value.split('十')
        return (digits.get(tens, 1) * 10) + digits.get(units, 0)
    return digits.get(value)


def _numbered(text):
    chapter = _CHAPTER.fullmatch(text.strip())
    if chapter:
        number = _chapter_number(chapter[1] or chapter[2])
        return ((number,), chapter[3]) if number and number < 100 else None
    subsection = _SUBSECTION.fullmatch(text.strip())
    if subsection:
        numbers = tuple(int(n) for n in subsection[1].split('.'))
        if all(0 < n < 100 for n in numbers):
            return numbers, subsection[2]
    return None


def _line_size(line):
    # A line's representative size can be the Latin font (e.g. 11.28 pt)
    # while its CJK glyphs and section number use the nominal 12 pt style.
    return max([float(line.get('font_size') or 0)] + [float(c.get('size') or 0) for c in line.get('chars', [])])


def _native_rows(page):
    """Join separate PDF text lines only when they share a visual baseline."""
    rows = []
    lines = [l for l in page.get('lines', []) if l.get('bbox') and l.get('text', '').strip()]
    for line in sorted(lines, key=lambda l: (l['bbox'][1], l['bbox'][0])):
        center = (line['bbox'][1] + line['bbox'][3]) / 2
        size = _line_size(line) or line['bbox'][3] - line['bbox'][1]
        if rows and abs(center - rows[-1]['center']) <= max(2, min(size, rows[-1]['size']) * .28):
            rows[-1]['lines'].append(line)
            rows[-1]['size'] = max(rows[-1]['size'], size)
        else:
            rows.append({'lines': [line], 'center': center, 'size': size})
    for row in rows:
        row['lines'].sort(key=lambda l: l['bbox'][0])
        row['text'] = ' '.join(l['text'].strip() for l in row['lines'])
        row['y'] = min(l['bbox'][1] for l in row['lines'])
    return rows


def _heading_row(row, body_size):
    lines, size = row['lines'], row['size']
    # A heading is one compact typographic run. Multiple table columns cannot
    # become a title simply because the left cell resembles a section number.
    if any(abs((_line_size(l) or size) - size) > .7 for l in lines):
        return False
    if any(re.fullmatch(r'[+\-−]?\d+(?:[.,]\d+)*(?:[eE][+\-]?\d+)?', l['text'].strip()) for l in lines[1:]):
        return False
    if any(not -1 <= b['bbox'][0] - a['bbox'][2] <= size * 2.2 for a, b in zip(lines, lines[1:])):
        return False
    fonts = [c.get('font', '') for l in lines for c in l.get('chars', []) if c.get('text', '').strip()]
    bold = bool(fonts) and sum(bool(re.search('bold|black|heavy', f, re.I)) for f in fonts) >= len(fonts) * .8
    return size >= body_size + .8 or (size >= body_size - .3 and bold)


def _title_text(text):
    return (2 <= len(text.strip()) <= 120 and bool(re.search(r'[A-Za-z\u3400-\u9fff]', text))
            and not _LEADER.search(text) and not re.search(r'[。；;!?！？=<>±×%]|\d\s*[（(]', text)
            and not re.match(r'^\d+(?:\.\d+)?(?:\s|$)', text.strip()))


def _attach_native_navigation(ir):
    """Conservative numeric-only fallback for PDFs without outline destinations.

    Chapter numbers, native geometry and typography must agree. A numbered
    subsection is admitted only beneath its unique, preceding number prefix.
    No generic Heading/Section classification is trusted as geometric evidence.
    """
    pages = {p['page_index'] + 1: p for p in ir.get('layout', {}).get('pages', [])}
    sizes = Counter()
    for page in pages.values():
        for line in page.get('lines', []):
            box = line.get('bbox')
            if (box and page.get('height', 0) * .105 < box[1] < page.get('height', 0) * .9
                    and len(line.get('text', '')) >= 25 and not _LEADER.search(line['text'])
                    and not _numbered(line['text'])
                    and not any(re.search('bold|black|heavy', c.get('font', ''), re.I) for c in line.get('chars', []))):
                sizes[round(_line_size(line), 1)] += len(line['text'])
    body_size = sizes.most_common(1)[0][0] if sizes else 12
    if body_size <= 0:
        return ir
    nodes = {n['id']: n for n in ir.get('nodes', [])}
    parents = {c: n['id'] for n in nodes.values() for c in n.get('children', [])}
    owners = {}
    for node in nodes.values():
        for src in node.get('provenance') or []:
            lid = src.get('line_id')
            if lid and (lid not in owners or node.get('kind') == 'Heading'):
                owners[lid] = node['id']
    candidates, ends, toc_lines, toc_pages = [], [], [], []
    for pnum, page in sorted(pages.items()):
        rows = [row for row in _native_rows(page)
                if not any(nodes.get(owners.get(l['id']), {}).get('attrs', {}).get('role')
                           in {'running_header', 'running_footer', 'page_number'} for l in row['lines'])]
        visible_toc = any(re.sub(r'\s+', '', row['text']).casefold() in {'目录', '目次', 'contents', 'tableofcontents'}
                          and row['size'] >= body_size + .8 and row['y'] < page.get('height', 0) * .4 for row in rows)
        if visible_toc:
            toc_pages.append(pnum)
        for i, row in enumerate(rows):
            text, y, size = row['text'], row['y'], row['size']
            if _LEADER.search(text):
                toc_lines.extend({'node_id': owners.get(l['id']), 'line_id': l['id'], 'page': pnum, 'text': l['text']} for l in row['lines'])
                continue
            if visible_toc or not page.get('height', 0) * .105 <= y <= page.get('height', 0) * .9 or not _heading_row(row, body_size):
                continue
            if _END_TITLE.fullmatch(text.strip()) and size >= body_size + .8:
                ends.append({'page': pnum, 'y': y})
            numbered = _numbered(text)
            if numbered is None:
                continue
            number, title = numbered
            group = list(row['lines'])
            # Native lines can split a long heading onto the next visual row.
            for next_row in rows[i+1:i+3]:
                gap = next_row['y'] - max(l['bbox'][1] for l in group)
                if not (size * .7 <= gap <= size * 1.9 and abs(next_row['size'] - size) <= .7
                        and _heading_row(next_row, body_size) and _numbered(next_row['text']) is None
                        and _title_text(next_row['text'])):
                    break
                title += (' ' if title else '') + next_row['text']
                text += ' ' + next_row['text']
                group.extend(next_row['lines'])
            if not _title_text(title):
                continue
            if len(number) == 1 and (size < body_size + 1 or y > page['height'] * .35):
                continue
            heading_owners = list(dict.fromkeys(owners[l['id']] for l in group if l['id'] in owners))
            # Preserve the original semantic title Section ID where possible;
            # a separate number line is frequently only a Paragraph node.
            semantic = next((owners.get(l['id']) for l in group if _title_text(l['text']) and _numbered(l['text']) is None), None)
            semantic = semantic or next((o for o in heading_owners if nodes[o].get('kind') == 'Heading'), None)
            sid = parents.get(semantic)
            if nodes.get(semantic, {}).get('kind') != 'Heading' or nodes.get(sid, {}).get('kind') != 'Section':
                sid = 'nav-section-' + group[0]['id']
            candidates.append({'section_id': sid, 'level': len(number), 'number': number,
                               'title': text, 'outline_title': text, 'parent_id': None,
                               'page': pnum, 'y': y, 'heading_node_id': semantic,
                               'heading_node_ids': heading_owners, 'heading_line_ids': [l['id'] for l in group]})
    by_number = defaultdict(list)
    for item in candidates:
        by_number[item['number']].append(item)
    roots = [c for c in candidates if c['level'] == 1]
    # An incomplete or ambiguous chapter chain does not justify replacing the
    # existing view. Never turn a decimal, cover or isolated label into a root.
    if len(roots) < 2 or [r['number'][0] for r in roots] != list(range(1, len(roots)+1)):
        return ir
    admitted, unresolved, known, last_sibling, active_prefixes = [], [], {}, {}, set()
    for item in candidates:
        number = item['number']
        parent_number = number[:-1]
        reason = None
        if len(by_number[number]) != 1:
            reason = 'ambiguous_native_number'
        elif len(number) > 1 and parent_number not in known:
            reason = 'unverified_native_parent'
        elif parent_number and parent_number not in active_prefixes:
            reason = 'outside_native_parent_range'
        elif number[-1] != last_sibling.get(parent_number, 0) + 1:
            reason = 'nonsequential_native_number'
        elif len(number) > 1 and item['page'] < known[parent_number]['page']:
            reason = 'nonpreceding_native_parent'
        if reason:
            unresolved.append({k: item[k] for k in ('title', 'page', 'y', 'level') } | {'reason': reason})
            continue
        item['parent_id'] = known[parent_number]['section_id'] if parent_number else None
        admitted.append({k: v for k, v in item.items() if k != 'number'})
        known[number] = item
        last_sibling[parent_number] = number[-1]
        active_prefixes = {number[:depth] for depth in range(1, len(number)+1)}
    first, last = roots[0]['page'], roots[-1]['page']
    ir['numeric_navigation'] = {'version': VERSION, 'source': 'native_numbered_headings', 'sections': admitted,
                                'toc_visible_page': next((p for p in toc_pages if p < first), None),
                                'toc_lines': [l for l in toc_lines if l['page'] < first and not re.match(r'^[图表]', l['text'])],
                                'unresolved': unresolved, 'end_boundaries': [e for e in ends if (e['page'], e['y']) > (last, roots[-1]['y'])]}
    return ir

def attach_navigation(pdf, ir):
    if ir.get('numeric_navigation'):
        return ir
    import pymupdf
    with pymupdf.open(pdf) as doc:
        raw = doc.get_toc(simple=False)
    if not raw:
        return _attach_native_navigation(ir)
    pages = {p['page_index'] + 1: p for p in ir.get('layout', {}).get('pages', [])}
    line_pages = {line['id']: pnum for pnum, p in pages.items() for line in p.get('lines', [])}
    owners = {}
    parent = {child: n['id'] for n in ir['nodes'] for child in n.get('children', [])}
    nodes = {n['id']: n for n in ir['nodes']}
    for node in ir['nodes']:
        for source in node.get('provenance') or []:
            line_id = source.get('line_id')
            if line_id and (line_id not in owners or node.get('kind') == 'Heading'):
                owners[line_id] = node['id']
    resolved, unresolved = [], []
    stack = []
    for index, entry in enumerate(raw):
        level, title, page = entry[:3]
        while stack and stack[-1]['level'] >= level:
            stack.pop()
        outline_parent = stack[-1] if stack else None
        lines = pages.get(page, {}).get('lines') or []
        point = entry[3].get('to') if len(entry) > 3 and isinstance(entry[3], dict) else None
        target_y = float(point.y) if point is not None else None
        # Named destinations in some PDFs expose bottom-origin coordinates.
        target_positions = [target_y, float(pages.get(page, {}).get('height', 0)) - target_y] if target_y is not None else []
        wanted = title_key(title)
        options = []
        for i, line in enumerate(lines):
            for count in (1, 2, 3):
                group = lines[i:i+count]
                if len(group) != count or not wanted:
                    continue
                box = group[0].get('bbox')
                if not box or any(not g.get('bbox') for g in group):
                    continue
                if any(abs(g['bbox'][1] - box[1]) > 80 for g in group):
                    continue
                text = ' '.join(g.get('text', '') for g in group)
                if title_key(text) != wanted:
                    continue
                y = min(g['bbox'][1] for g in group)
                distance = min((abs(y - ty) for ty in target_positions), default=0)
                if target_y is not None and distance > 100:
                    continue
                font = max(g.get('font_size', 0) for g in group)
                # Prefer a full numbered heading over a separated title on the same baseline.
                numbered = bool(re.match(r'^(?:第[一二三四五六七八九十百\d]+章|\d+(?:\.\d+)*\s|chapter\s+\d+)', text, re.I))
                options.append((-round(font, 1), round(distance, 1), not numbered, -count, y, group, text))
        if not options:
            # A destination can be off by one PDF page. Only admit an exact numbered
            # title on an adjacent page; never guess from a generic subsection label.
            expected_number = re.match(r'^(\d+(?:\.\d+)*)\s', title)
            if expected_number:
                for adjacent in (page-1, page+1):
                    adjacent_lines = pages.get(adjacent, {}).get('lines') or []
                    for i in range(len(adjacent_lines)):
                        for count in (1, 2, 3):
                            group = adjacent_lines[i:i+count]
                            if len(group) != count or any(not g.get('bbox') for g in group):
                                continue
                            text = ' '.join(g.get('text', '') for g in group)
                            number = re.match(r'^(\d+(?:\.\d+)*)(?:\s|$)', text)
                            if not number or number[1] != expected_number[1] or title_key(text) != wanted:
                                continue
                            y = min(g['bbox'][1] for g in group)
                            if any(abs(g['bbox'][1]-y) > 80 for g in group):
                                continue
                            font = max(g.get('font_size', 0) for g in group)
                            options.append((-round(font, 1), 100.0, False, -count, y, group, text))
        if not options:
            unresolved.append({'outline_index': index, 'level': level, 'title': title, 'page': page})
            stack.append({'level': level, 'section_id': None})
            continue
        _, _, _, _, y, group, text = min(options, key=lambda x: x[:5])
        line_id = group[0]['id']
        source_page = line_pages[line_id]
        owner = owners.get(line_id)
        heading_owners = list(dict.fromkeys(owners.get(g['id']) for g in group if owners.get(g['id'])))
        semantic_owner = next((owners.get(g['id']) for g in reversed(group) if title_key(g.get('text', ''))), owner)
        original_section = parent.get(owner)
        sid = original_section if nodes.get(owner, {}).get('kind') == 'Heading' and nodes.get(original_section, {}).get('kind') == 'Section' else 'nav-section-' + line_id
        if sid in {x['section_id'] for x in resolved} or (level > 1 and (not outline_parent or outline_parent['section_id'] is None)):
            unresolved.append({'outline_index': index, 'level': level, 'title': title, 'page': page, 'reason': 'duplicate_anchor_or_unverified_parent'})
            stack.append({'level': level, 'section_id': None})
            continue
        item = {'section_id': sid, 'level': level, 'title': text, 'outline_title': title,
                'parent_id': outline_parent['section_id'] if outline_parent else None, 'page': source_page,
                'outline_target_page': page,
                'y': y, 'heading_node_id': semantic_owner, 'heading_node_ids': heading_owners, 'heading_line_ids': [g['id'] for g in group],
                'outline_index': index}
        resolved.append(item)
        stack.append(item)
    # Admit only body chapters, not covers, abstracts, tables-of-contents or bibliography.
    admitted, active_root = [], None
    for item in resolved:
        if item['level'] == 1:
            has_number = bool(re.match(r'^(?:第[一二三四五六七八九十百\d]+章|\d+\s|chapter\s+\d+)', item['title'], re.I))
            is_body = has_number or bool(re.fullmatch(r'Introduction|Conclusions?', item['outline_title'], re.I))
            active_root = item['section_id'] if is_body else None
        if active_root:
            admitted.append(item)
    if not admitted:
        return ir
    # Preserve every resolved top-level boundary, including bibliography/end matter.
    end_boundaries = [{'page': x['page'], 'y': x['y']} for x in resolved if x['level'] == 1 and x['section_id'] not in {a['section_id'] for a in admitted} and x['page'] >= admitted[0]['page']]
    toc_lines = []
    toc_page = None
    first_body = min(x['page'] for x in admitted)
    for pnum, page in sorted(pages.items()):
        if pnum >= first_body:
            break
        lines = page.get('lines') or []
        labels = {'目录', '目次', 'contents', 'tableofcontents'}
        has_toc = False
        observed_labels = set()
        for i, line in enumerate(lines):
            for count in (1, 2, 3):
                group = lines[i:i+count]
                text = re.sub(r'\s+', '', ''.join(l.get('text', '') for l in group)).casefold()
                same_row = all(l.get('bbox') and line.get('bbox') and abs(l['bbox'][1] - line['bbox'][1]) < 4 for l in group)
                if same_row:
                    observed_labels.add(text)
                if text in labels and same_row:
                    has_toc = True
        if toc_page is not None and pnum > toc_page and observed_labels & {'表目录', '图目录', '表目次', '图目次', '摘要', 'abstract', 'listoftables', 'listoffigures'}:
            break
        if has_toc:
            toc_page = pnum if toc_page is None else toc_page
        if toc_page is not None:
            toc_lines.extend({'node_id': owners.get(l['id']), 'line_id': l['id'], 'page': pnum, 'text': l.get('text', '')}
                             for l in lines if re.search(r'(?:\.\s*){3,}|…{2,}|⋯', l.get('text', '')))
    ir['numeric_navigation'] = {'version': VERSION, 'sections': admitted, 'toc_visible_page': toc_page,
                                'toc_lines': toc_lines, 'unresolved': unresolved, 'end_boundaries': end_boundaries}
    return ir


def navigation_model(ir):
    nav = ir['numeric_navigation']
    sections = {s['section_id']: {**s, 'block_ids': []} for s in nav['sections']}
    pages = {p['page_index'] + 1: p for p in ir['layout']['pages']}
    uncertain = [dict(s, section_id=None) for s in nav.get('unresolved', []) if 'y' in s]
    boundaries = sorted(nav['sections'] + uncertain, key=lambda s: (s['page'], s['y'], s['level']))
    real_heading_lines = {lid for s in nav['sections'] for lid in s['heading_line_ids']}
    end = min(((b['page'], b['y']) for b in nav['end_boundaries']), default=(10**9, 0))
    excluded_roles = {'running_header', 'running_footer', 'page_number'}
    blocks = []
    for node in ir['nodes']:
        if node.get('attrs', {}).get('role') in excluded_roles or not isinstance(node.get('text'), str):
            continue
        text = node['text']
        grouped = defaultdict(list)
        for source in node.get('provenance') or []:
            page = source.get('page_index')
            start, stop, box = source.get('node_text_start'), source.get('node_text_end'), source.get('bbox')
            if type(page) is not int or type(start) is not int or type(stop) is not int or not box or not 0 <= start < stop <= len(text):
                continue
            position = (page+1, float(box[1]))
            if position >= end:
                continue
            eligible = [s for s in boundaries if (s['page'], s['y']-.5) <= position]
            if not eligible:
                continue
            owner = eligible[-1]['section_id']
            if owner is None:
                continue
            grouped[(owner, page+1)].append((source, text[start:stop]))
        for (sid, page), spans in grouped.items():
            block_id = f'{node["id"]}:p{page}:{sid}'
            kind = node['kind']
            # The generic parser can mistake bold table cells for headings. In this
            # verified view, only outline-grounded heading lines receive that role.
            if kind == 'Heading' and not any(s.get('line_id') in real_heading_lines for s, _ in spans):
                kind = 'Paragraph'
            blocks.append({'block_id': block_id, 'source_node_id': node['id'], 'section_id': sid,
                           'page': page, 'block_type': kind, 'paper_model_kind': node['kind'], 'table_id': None,
                           'text': '\n'.join(t for _, t in spans), 'provenance': [s for s, _ in spans]})
            sections[sid]['block_ids'].append(block_id)
    blocks.sort(key=lambda b: (b['page'], b['provenance'][0]['bbox'][1], b['provenance'][0]['bbox'][0]))
    toc = nav['toc_lines']
    if nav['toc_visible_page'] is not None and not toc:
        toc = [{'node_id': s['heading_node_id'], 'text': s['outline_title'], 'source': 'visible_toc_and_body_verified_outline', 'target_page': s['page']} for s in nav['sections']]
    return {'sections': sections, 'blocks': blocks, 'pages': pages, 'toc': toc,
            'limitations': ['native_text_only', 'table_cells_not_reliably_reconstructed'],
            'navigation': {'version': VERSION, 'unresolved': nav['unresolved'], 'toc_visible_page': nav['toc_visible_page']}}
