"""Resume supplementary research proved by native hierarchy and equation ink.

This pure scope repair does not read paths, paper identities, or PDF/cache files.
A numbered title alone cannot end a bibliography. Its original native glyphs,
hierarchical consecutive subheadings, ordinary paragraphs and an aligned numbered
display equation must agree; bibliographic entries veto that interpretation.
"""
import re
from statistics import median
from .numbering import normalize_text, is_toc_line

_SECTION = re.compile(r'^(?P<number>\.?[1-9][0-9]*(?:\.[0-9]+)*)\s+(?P<title>\S.{0,79})$')
_ENTRY = re.compile(r'^\s*(?:\[[0-9]{1,4}\]|[0-9]{1,4}[.)]\s)')
_EQUATION_NUMBER = re.compile(r'^\(\s*\.?[0-9]+(?:\.[0-9]+)*\s*\)$')
_NONBODY_TITLE = re.compile(r'^(?:参考文献|致\s*谢|References|Acknowledg(?:e)?ments)$', re.I)
_PUBLICATION = re.compile(r'\[(?:J|C|M|D|R|S|N|P|EB)(?:/OL)?\]|\bDOI\b|https?://|\b(?:18|19|20)[0-9]{2}\b', re.I)


def _key(line):
    return line.page_number, line.bbox


def _native_glyphs(line):
    if (line.source != 'native' or line.font_size is None or line.font_size <= 0
            or line.direction[0] < .9 or abs(line.direction[1]) > .05):
        return False
    covered = set()
    for start, end, box in line.text_regions:
        if box[2] > box[0] and box[3] > box[1]:
            covered.update(range(start, end))
    return all(i in covered for i, c in enumerate(line.text) if not c.isspace())


def _inside_visual(line, page):
    a = line.bbox
    return any(b[0]-.5 <= a[0] and b[1]-.5 <= a[1]
               and a[2] <= b[2]+.5 and a[3] <= b[3]+.5
               for b in (*page.tables, *page.images))


def _headings(document, directories, body_size):
    result = []
    for p in document.pages:
        eligible = [l for l in p.lines if l.bold and _native_glyphs(l)
                    and l.font_size >= body_size*.98
                    and p.height*.10 < l.bbox[1] < p.height*.88
                    and _key(l) not in directories and not _inside_visual(l, p)]
        used = set()
        for line in sorted(eligible, key=lambda l: (l.bbox[1], l.bbox[0])):
            if _key(line) in used:
                continue
            peers = [line] if line.block_id is None else [l for l in eligible
                    if l.block_id == line.block_id
                    and abs(l.bbox[1]-line.bbox[1]) <= line.font_size*.3
                    and abs(l.font_size-line.font_size) <= .5]
            peers.sort(key=lambda l: l.bbox[0])
            used.update(_key(l) for l in peers)
            text = ' '.join(normalize_text(l.text).strip() for l in peers)
            match = _SECTION.fullmatch(text)
            if not match or is_toc_line(text) or re.search(r'[，,。；;!?！？]', match['title']):
                continue
            result.append(dict(lines=peers, page=p.number, y=min(l.bbox[1] for l in peers),
                               x=peers[0].bbox[0], size=peers[0].font_size, text=text,
                               dotted=match['number'].startswith('.'),
                               number=tuple(map(int, match['number'].lstrip('.').split('.')))))
    # Repeated title ink in the same page band is a running heading.
    return [h for h in result if not any(q['page'] != h['page'] and q['text'] == h['text']
            and abs(q['y']-h['y']) <= 3 and abs(q['x']-h['x']) <= 5
            and abs(q['size']-h['size']) <= .5 for q in result)]


def _formal_nonbody_title(line, body_size, ordered=(), pages=None):
    if (not _native_glyphs(line) or not _NONBODY_TITLE.fullmatch(normalize_text(line.text).strip())
            or line.bbox[1] <= line.page_height*.10):
        return False
    page = pages.get(line.page_number) if pages else None
    if page and _inside_visual(line, page):
        return False
    if line.bold or line.font_size >= body_size*1.12:
        return True
    if not body_size*.90 <= line.font_size <= body_size*1.10:
        return False
    # A same-size title must stand alone and introduce actual publication
    # entries. A field label beside another native cell cannot stop research.
    if any(l.page_number == line.page_number and l.bbox != line.bbox
           and abs(l.bbox[1]-line.bbox[1]) <= body_size*.3 and l.text.strip()
           and (l.bbox[0] > line.bbox[2]+2 or l.bbox[2] < line.bbox[0]-2)
           for l in ordered):
        return False
    following = [l for l in ordered if l.page_number == line.page_number
                 and line.bbox[3] < l.bbox[1] <= line.bbox[3]+body_size*9
                 and _native_glyphs(l) and (not page or not _inside_visual(l, page))]
    return any(_ENTRY.match(normalize_text(l.text))
               and _PUBLICATION.search(' '.join(q.text for q in following[i:i+3]))
               for i, l in enumerate(following))


def _proof(root, headings, ordered, pages, directories, body_size):
    start = root['page'], root['y']
    later = [h for h in headings if start < (h['page'], h['y'])
             and h['page'] <= root['page']+1]
    limit = next(((h['page'], h['y']) for h in later
                 if len(h['number']) <= len(root['number'])), (root['page']+2, 0))
    formal_ends = [(l.page_number, l.bbox[1]) for l in ordered
                   if start < (l.page_number, l.bbox[1]) < limit
                   and _formal_nonbody_title(l, body_size, ordered, pages)]
    if formal_ends:
        limit = min(formal_ends)
    children = [h for h in later if (h['page'], h['y']) < limit
                and h['dotted'] == root['dotted']
                and len(h['number']) == len(root['number'])+1
                and h['number'][:-1] == root['number']
                and root['x']-3 <= h['x'] <= root['x']+body_size*2]
    if not any(b['number'][-1] == a['number'][-1]+1
               for a, b in zip(children, children[1:])):
        return False
    region = [l for l in ordered if start <= (l.page_number, l.bbox[1]) < limit
              and _key(l) not in directories]
    if any((_ENTRY.match(normalize_text(l.text)) and not _inside_visual(l, pages[l.page_number]))
           or _formal_nonbody_title(l, body_size, ordered, pages)
           for l in region):
        return False
    prose = [l for l in region if _native_glyphs(l) and not l.bold
             and body_size*.90 <= l.font_size <= body_size*1.10
             and len(normalize_text(l.text).strip()) >= 28
             and l.bbox[2]-l.bbox[0] >= l.page_width*.45
             and re.search(r'[，,。.;；:：]', l.text)
             and not _inside_visual(l, pages[l.page_number])]
    if len(prose) < 3:
        return False
    for l in region:
        if (not _native_glyphs(l) or l.bold or _inside_visual(l, pages[l.page_number])
                or not re.search(r'[=≤≥≈≡]', l.text)
                or not l.page_width*.25 <= l.bbox[0] < l.bbox[2] <= l.page_width*.80):
            continue
        math_letters = sum(0x1d400 <= ord(c) <= 0x1d7ff or 0x370 <= ord(c) <= 0x3ff for c in l.text)
        if math_letters < 2:
            continue
        if any(n.page_number == l.page_number and _native_glyphs(n)
               and _EQUATION_NUMBER.fullmatch(normalize_text(n.text).strip())
               and n.bbox[0] > n.page_width*.75
               and abs(n.bbox[1]-l.bbox[1]) <= body_size*1.5 for n in region):
            return True
    return False


def resume_bibliography_scopes(document, scopes, nonbody, *, directories=()):
    """Return copied scope maps, reopening only proved supplementary research."""
    updated, remaining = dict(scopes), set(nonbody)
    if not nonbody:
        return updated, remaining
    directories = set(directories)
    ordered = sorted(document.lines, key=lambda l: (l.page_number, l.bbox[1], l.bbox[0]))
    sizes = [l.font_size for l in ordered if l.source == 'native' and not l.bold
             and l.font_size and len(l.text.strip()) >= 28 and l.bbox[1] > l.page_height*.12]
    body_size = median(sizes) if sizes else 12
    pages = {p.number: p for p in document.pages}
    headings = _headings(document, directories, body_size)
    starts = {(_key(h['lines'][0])) for h in headings
              if h['size'] >= body_size*1.12
              and scopes.get(_key(h['lines'][0])) == '_nonbody'
              and _proof(h, headings, ordered, pages, directories, body_size)}
    active = False
    for l in ordered:
        key = _key(l)
        if key in directories:
            continue
        if _formal_nonbody_title(l, body_size, ordered, pages) or scopes.get(key) not in {'_nonbody', 'body'}:
            active = False
        if key in starts:
            active = True
        if active and scopes.get(key) == '_nonbody':
            updated[key] = 'body'
            remaining.discard(key)
    return updated, remaining
