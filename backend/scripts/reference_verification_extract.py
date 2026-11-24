"""Native bibliography adapter for database verification. No OCR, model or network."""
import argparse
import json
from pathlib import Path
import re
import sys
from collections import defaultdict
from statistics import median
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_compiler.frontend import _build_source_tree, _observe
from fast_local_detector import native_coverage


LABEL = re.compile(r'^\s*(?:\[\d{1,4}\]|\d{1,4}[.、])\s*')
TYPE = re.compile(r'\[([A-Za-z]{1,3})(?:/[A-Za-z]{1,2})?\]')
DOI = re.compile(r'(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)?(10\.\d{4,9}/[^\s"，；]+)', re.I)
YEAR = re.compile(r'(?<!\d)((?:19|20)\d{2})(?!\d)')
ARXIV = re.compile(r'(?:arxiv\s*:\s*|arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+/\d{7}(?:v\d+)?)', re.I)
INITIAL_NAME = r"(?:[A-Z](?:[.\-]*[A-Z])*\.\s*)+[A-Z\u00c0-\u00de][\w\u2019'\-]+(?:\s+[A-Z\u00c0-\u00de][\w\u2019'\-]+){0,3}"
INITIAL_AUTHORS = re.compile(rf'{INITIAL_NAME}(?:,\s*{INITIAL_NAME})*(?:,?\s+and\s+{INITIAL_NAME})?')


def _authors(value):
    value = re.sub(r'\bet\s+al\.?|等[.。]?', '', value, flags=re.I).strip(' ,.;，；。')
    parts = re.split(r'\s+(?:and|&)\s+|[,，;；]', value)
    # Join APA surname + initial fragments before exposing names to a resolver.
    names = []
    for part in parts:
        part = part.strip(' ,.;')
        if not part:
            continue
        if names and re.fullmatch(r'(?:[A-Z][. ]*){1,4}', part):
            names[-1] += ' ' + part
        else:
            names.append(part)
    return names[:60]


def _doi_values(source):
    # A PDF can wrap the explicit DOI even when the hyperlink has its complete
    # value. Join only identifier-shaped continuations, never a following title.
    value = re.sub(r'(10\.\d{4,9}/[^\s<>"，；]*[\w%\\/_-])\r?\n[ \t]*'
                   r'((?:\d|[-_/])[^\s<>"，；]{3,})',
                   lambda match: match.group(0) if YEAR.fullmatch(match.group(2).rstrip('.,'))
                   or re.fullmatch(r'\d{1,5}[-–:]\d{1,5}[.,]?', match.group(2))
                   else match.group(1) + match.group(2), source, flags=re.I)
    values = []
    for match in DOI.finditer(value):
        doi = unquote(match.group(1)).replace('\\_', '_').rstrip('.,;:。')
        for end, start in [(')', '('), (']', '['), ('}', '{'), ('>', '<')]:
            while doi.endswith(end) and doi.count(end) > doi.count(start):
                doi = doi[:-1]
        values.append(doi.lower())
    return list(dict.fromkeys(values))


def parse_entry(text):
    source = str(text)
    value = re.sub(r'\s+', ' ', LABEL.sub('', source)).strip()
    doi_values = _doi_values(source)
    doi = doi_values[0] if len(doi_values) == 1 else None
    arxiv_match = ARXIV.search(value)
    type_match = TYPE.search(value)
    year_scope = value[type_match.end():] if type_match else value
    title, authors, confidence = '', [], 'partial'
    quoted = re.search(r'["“]([^"”]{8,500})["”]', value)
    apa = re.search(r'\((?:19|20)\d{2}[a-z]?\)\s*[.．]?\s*', value)
    year_boundary = re.search(r'(?<!\d)(?:19|20)\d{2}[a-z]?\.\s+', value)
    if quoted:
        title = quoted.group(1).strip(' ,，.;')
        authors = _authors(value[:quoted.start()])
        confidence = 'high'
        year_scope = value[quoted.end():]
    elif type_match:
        prefix = value[:type_match.start()]
        # GB/T bibliography separates responsibility and title with a full stop.
        # An author's initial followed by another initial does not end that field.
        etal = re.search(r'\bet\s+al\.?(?:[,;:]\s*|\s+)', prefix, re.I)
        comma = next((candidate for candidate in re.finditer(r',\s+',prefix)
                      if INITIAL_AUTHORS.fullmatch(prefix[:candidate.start()].strip())
                      and not re.match(rf'(?:and\s+)?{INITIAL_NAME}',prefix[candidate.end():])), None)
        separators = list(re.finditer(r'(?:\bet\s+al\.|[.。．])\s+(?=[^\s])', prefix, re.I))
        separator = next((candidate for candidate in separators
                          if not re.search(r'(?:^|[,;]\s*)(?:[A-Za-z]\.\s*)*[A-Za-z]$', prefix[:candidate.start()])), None)
        # Initial-first names require a complete author-prefix parse, otherwise
        # a dot inside M.-T. Huang could be mistaken for the title boundary.
        if re.match(r'[A-Z]\.',prefix) and separator and not INITIAL_AUTHORS.fullmatch(prefix[:separator.start()].strip()):
            separator = None
        separator = etal or comma or separator
        if separator:
            # Initials inside a conventional IEEE author prefix are uncertain;
            # prefer an explicit et al boundary when one is present.
            title = prefix[separator.end():].strip(' ,，.。')
            authors = _authors(prefix[:separator.start()])
            confidence = 'high' if len(title) >= 4 and authors else 'partial'
    elif apa or year_boundary:
        boundary = apa or year_boundary
        tail = value[boundary.end():]
        title = re.split(r'(?<=[.?!])\s+(?=[A-Z])', tail, maxsplit=1)[0].strip(' .')
        authors = _authors(value[:boundary.start()])
        confidence = 'high' if len(title) >= 8 and authors else 'partial'
        year_scope = value[boundary.start():boundary.end()]
    # Do not invent a title from a whole unparsed entry. DOI/arXiv still provide
    # useful exact discovery keys while uncertain fields remain explicitly empty.
    if type_match and type_match.group(1).upper() == 'M' and not quoted:
        # A trailing GB/T book-volume field is not part of the work's title.
        title = re.sub(r'\s*:\s*vol(?:ume)?\.?\s*\d+(?:[-–]\d+)?$', '', title, flags=re.I)
    if len(title) > 500 or re.search(r'\[\d+\]', title):
        title, confidence = '', 'partial'
    if len(doi_values) > 1:
        confidence = 'partial'
    years = YEAR.findall(DOI.sub('', year_scope))
    arxiv_doi = re.fullmatch(r'10\.48550/arxiv\.(.+)', doi, re.I) if doi else None
    result = {
        'text': source, 'title': title, 'authors': authors,
        'year': int(years[0]) if years else None,
        'doi': doi,
        'arxiv_id': arxiv_match.group(1) if arxiv_match else arxiv_doi.group(1) if arxiv_doi else None,
        'type_code': type_match.group(1).upper() if type_match else None,
        'extraction_confidence': confidence,
    }
    folded_source = re.sub(r'(?<=[A-Za-z])-\r?\n[ \t]*(?=[a-z])', '', source)
    if folded_source != source and title:
        folded = parse_entry(folded_source)
        variant = folded['title']
        letters = lambda value: ''.join(char.casefold() for char in value if char.isalnum())
        if (variant and variant != title and letters(variant) == letters(title)
                and folded['authors'] == authors and folded['year'] == result['year']):
            result['title_search_variants'] = [variant]
    return result


def _reading_order(pages):
    """Order genuine separated columns before entry grouping, retaining all spans.

    This adapter is private to the new rule. It does not change other checks'
    shared PDF reading order.
    """
    for page in pages:
        width = page['width']
        left = [line for line in page['lines'] if line['bbox'][2] < width * .53]
        right = [line for line in page['lines'] if line['bbox'][0] > width * .47]
        if len(left) < 3 or len(right) < 3:
            continue
        if min(len(left),len(right)) < 8 and not (any(LABEL.match(line['text']) for line in left)
                                                  and any(LABEL.match(line['text']) for line in right)):
            continue
        gutter_left = max(line['bbox'][2] for line in left)
        gutter_right = min(line['bbox'][0] for line in right)
        overlap = min(max(x['bbox'][3] for x in left), max(x['bbox'][3] for x in right)) - max(min(x['bbox'][1] for x in left), min(x['bbox'][1] for x in right))
        if gutter_right - gutter_left < width * .015 or overlap < 20:
            continue
        sides = {line['id'] for line in left + right}
        others = [line for line in page['lines'] if line['id'] not in sides]
        top = min(line['bbox'][1] for line in left + right)
        # A full-width object crossing the columns makes reading order ambiguous.
        # Leave such pages unchanged rather than silently discarding source text.
        if any(top + 25 < line['bbox'][1] < page['height'] * .9 for line in others):
            continue
        before = [line for line in others if line['bbox'][1] <= top + 25]
        after = [line for line in others if line not in before]
        page['lines'] = sorted(before, key=lambda x:x['bbox'][1]) + sorted(left, key=lambda x:(x['bbox'][1],x['bbox'][0])) + sorted(right, key=lambda x:(x['bbox'][1],x['bbox'][0])) + sorted(after, key=lambda x:x['bbox'][1])
    return pages


def _without_running_margins(pages):
    """Remove corroborated running furniture only in this rule's private input.

    Repeated small text near the page edge is separate from a larger section
    heading. Body continuations near the top remain available for entry joining.
    """
    sizes = [line['font_size'] for page in pages for line in page['lines']
             if page['height'] * .12 < line['bbox'][1] < page['height'] * .88]
    normal = median(sizes) if sizes else 11
    seen = defaultdict(set)
    local_sizes = {page['page_index']: [line['font_size'] for line in page['lines']
                   if page['height'] * .12 < line['bbox'][1] < page['height'] * .88] for page in pages}
    local_normal = {index: min(normal, median(values)) if values else normal for index, values in local_sizes.items()}
    def signature(page, line):
        top = line['bbox'][3] <= page['height'] * .12
        bottom = line['bbox'][1] >= page['height'] * .88
        if (not top and not bottom) or line['font_size'] > local_normal[page['page_index']] * .95 or LABEL.match(line['text']):
            return None
        return ('top' if top else 'bottom', re.sub(r'\s+', '', line['text']).casefold())
    for page in pages:
        for line in page['lines']:
            key = signature(page, line)
            if key:
                seen[key].add(page['page_index'])
    for page in pages:
        def furniture(line):
            key = signature(page, line)
            if key and len(seen[key]) >= 2:
                return True
            box = line['bbox']
            centered = .4 * page['width'] <= (box[0] + box[2]) / 2 <= .6 * page['width']
            return (box[1] >= page['height'] * .88 and centered and line['font_size'] <= normal
                    and bool(re.fullmatch(r'\s*[-–—]?\s*(?:\d{1,5}|[ivxlcdmIVXLCDM]{1,10})\s*[-–—]?\s*', line['text'])))
        page['lines'] = [line for line in page['lines'] if not furniture(line)]
    return pages


def _split_author_year(node):
    text = node.get('text') or ''
    back = re.search(r'(?im)^(?:List\s+of\s+(?:Publications|Achievements)|Publications\s+and\s+(?:research\s+)?Achievements|学术论文[和与及]科研成果目录)\s*$',text)
    if back:
        end = back.start()
        text = text[:end].rstrip()
        node = {**node,'text':text,'provenance':[span for span in node.get('provenance',[]) if span.get('node_text_start',0)<end]}
    if LABEL.match(text):
        return [node]
    starts = [0]
    for match in re.finditer(r'(?m)^[A-Z][A-Za-z\u00c0-\u024f\u2019\x27-]+,\s*[A-Z][^\n]{0,200}\((?:19|20)\d{2}[a-z]?\)[.．]', text):
        if match.start() > 0:
            starts.append(match.start())
    if len(starts) == 1:
        return [node]
    result = []
    for index,start in enumerate(starts):
        end = starts[index+1] if index+1<len(starts) else len(text)
        spans = [span for span in node.get('provenance',[]) if start <= span.get('node_text_start',0) < end]
        result.append({**node,'id':f"{node['id']}-part-{index}",'text':text[start:end].strip(),'provenance':spans})
    return result


def extract(pdf):
    pages = _reading_order(_without_running_margins(_observe(Path(pdf))))
    ir = native_coverage(_build_source_tree(Path(pdf), include_citations=False, pages=pages))
    entries = []
    pages = {p['page_index']: p for p in ir['layout']['pages']}
    nodes = [piece for node in ir['nodes'] if node['kind']=='BibliographyEntry' for piece in _split_author_year(node)]
    for node in nodes:
        entry = parse_entry(node.get('text') or '')
        entry['id'] = node['id']
        rects = []
        for span in node.get('provenance', []):
            if span.get('kind') != 'source' or span.get('page_index') not in pages:
                continue
            page = pages[span['page_index']]
            box = span['bbox']
            rects.append({'x1': box[0], 'y1': box[1], 'x2': box[2], 'y2': box[3],
                          'width': page['width'], 'height': page['height'],
                          'page_number': span['page_index'] + 1})
        entry['location'] = ({'type': 'pdf_bbox', 'page_number': rects[0]['page_number'],
                              'bounding_rect': rects[0], 'rects': rects, 'text_excerpt': entry['text']}
                             if rects else None)
        entries.append(entry)
    complete = bool(entries) and ir.get('coverage', {}).get('pages', {}).get('status') == 'complete'
    return {'entries': entries, 'native_only': True, 'coverage_complete': complete,
            'page_count': len(pages), 'extraction_version': 'reference-native/1.0'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pdf', required=True, type=Path)
    args = parser.parse_args()
    import pymupdf
    pymupdf.TOOLS.mupdf_display_errors(False)
    pymupdf.TOOLS.mupdf_display_warnings(False)
    print(json.dumps(extract(args.pdf), ensure_ascii=True))
