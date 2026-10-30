"""Numeric-rule-only navigation view, grounded in PDF outline destinations and native lines.

The shared Paper Model is not rewritten. Every derived range retains native line/node IDs.
"""
from __future__ import annotations

from collections import defaultdict
import re


VERSION = 'numeric-navigation/1.1'


def title_key(text):
    text = re.sub(r'\s+', '', text).casefold()
    text = re.sub(r'^(?:第[一二三四五六七八九十百\d]+章|chapter\d+|\d+(?:\.\d+)*[.:：]?)', '', text)
    return text.strip(':：.、')


def attach_navigation(pdf, ir):
    import pymupdf
    with pymupdf.open(pdf) as doc:
        raw = doc.get_toc(simple=False)
    if not raw:
        return ir
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
    boundaries = sorted(nav['sections'], key=lambda s: (s['page'], s['y'], s['level']))
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
            grouped[(owner, page+1)].append((source, text[start:stop]))
        for (sid, page), spans in grouped.items():
            block_id = f'{node["id"]}:p{page}:{sid}'
            blocks.append({'block_id': block_id, 'source_node_id': node['id'], 'section_id': sid,
                           'page': page, 'block_type': node['kind'], 'table_id': None,
                           'text': '\n'.join(t for _, t in spans), 'provenance': [s for s, _ in spans]})
            sections[sid]['block_ids'].append(block_id)
    blocks.sort(key=lambda b: (b['page'], b['provenance'][0]['bbox'][1], b['provenance'][0]['bbox'][0]))
    toc = nav['toc_lines']
    if nav['toc_visible_page'] is not None and not toc:
        toc = [{'node_id': s['heading_node_id'], 'text': s['outline_title'], 'source': 'visible_toc_and_body_verified_outline', 'target_page': s['page']} for s in nav['sections']]
    return {'sections': sections, 'blocks': blocks, 'pages': pages, 'toc': toc,
            'limitations': ['native_text_only', 'table_cells_not_reliably_reconstructed'],
            'navigation': {'version': VERSION, 'unresolved': nav['unresolved'], 'toc_visible_page': nav['toc_visible_page']}}
