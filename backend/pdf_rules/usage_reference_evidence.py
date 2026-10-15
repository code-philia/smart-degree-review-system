"""Independent source-native evidence view for unused figures and tables.

The shared index is immutable input.  Existing direct uses retain their exact
identity; newly recovered uses are attached to a unique physical caption group.
This prevents a duplicated manuscript or repeated number from gaining usage
merely because another physical object has the same label.  No file, cache,
paper identity, or previous finding is read here.
"""
import copy
import re
from bisect import bisect_right
from collections import Counter
from dataclasses import replace
from statistics import median

from .model import DocumentIndex, Label
from .numbering import normalize_label, toc_line_keys, DOT_LEADER, FIGURE_REFERENCE, TABLE_REFERENCE, APPENDIX_QUALIFIER, caption_match
from .usage_text_cache import normalize_text
from .caption_context import body_font
from .caption_identity import caption_groups
from .reference_identity_repair import _scope_map, _label, _text, _external, _TYPED
from .reference_context import defined_graph_symbols, local_reference, graph_variable_use
from .reference_groups import reference_matches
from .bibliography_scope_resume import _native_glyphs
from .local_rules import indirect_reference_key, physical_target_key
from .usage_paragraphs import usage_paragraphs

_CHAPTER = re.compile(r'^(?:第\s*[零〇一二三四五六七八九十百0-9]+\s*章|Chapter\s+[0-9IVX]+)(?:\s|$)', re.I)
_NONBODY = re.compile(r'^(?:参考文献|致\s*谢|References|Acknowledg(?:e)?ments)$', re.I)
_DIRECTORY = re.compile(r'^(?:插图(?:目录)?|图目录|表目录|图录|表录|附表|ListofFigures|ListofTables)', re.I)


def _key(line):
    return line.page_number, line.bbox


def _clone(value):
    # Labels, lines and documents are frozen.  Hidden container bindings may
    # hold mutable sets/lists, so copy those recursively without cloning ink.
    if isinstance(value, list):
        return [_clone(v) for v in value]
    if isinstance(value, dict):
        return {k: _clone(v) for k, v in value.items()}
    if isinstance(value, set):
        return {_clone(v) for v in value}
    if isinstance(value, tuple):
        return tuple(_clone(v) for v in value)
    return value


def _inside(a, b, tolerance=.5):
    return b[0]-tolerance <= a[0] and b[1]-tolerance <= a[1] and a[2] <= b[2]+tolerance and a[3] <= b[3]+tolerance


def _overlap(a, b):
    return max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))


def _letters(text):
    return len(re.findall(r'[A-Za-z\u4e00-\u9fff]', text))


def _foreign_usage_owner(text,match):
    """Reject an explicit foreign owner of this recovered literal reference.

    A foreign paper mentioned elsewhere in a comparison is insufficient.
    Ownership must directly precede the type word or point to it with its/their.
    Shared parser references and numbering remain unchanged.
    """
    prefix=re.split(r'[。；;!?]|(?<!\d)\.(?!\d)',text[:match.start()])[-1]
    foreign=r'\b(?:another|other|a\s+different)\s+(?:papers?|works?|study|studies|thesis|theses)\b'
    direct=re.search(r'\b(?:in|from|of)\s+'+foreign+r'\s*(?:[\u2019\x27]s\s*)?[\[(（\s]*$',prefix,re.I)
    denial=direct and re.search(r'\b(?:not|never)(?:\s+(?:directly|originally|copied|taken|borrowed))?\s*$',prefix[:direct.start()],re.I)
    if direct and not denial:
        return True
    # Provenance can be negated while the named foreign table still has
    # its explicit possessive owner: "not from another paper's Table".
    if re.search(foreign+r'[\u2019\x27]s\s*[\[(（\s]*$',prefix,re.I):
        return True
    if re.search(r'(?:另一|其他|其它)(?:一)?(?:篇)?(?:论文|研究|文献)(?:中|里)?(?:的|所示|中的)?[\[(（\s]*$',prefix):
        return True
    owners=list(re.finditer(foreign,prefix,re.I))
    if owners:
        tail=prefix[owners[-1].end():]
        if (not re.search(r'\b(?:our|this)\s+(?:paper|work|study|thesis|actions?|figures?|tables?)\b',tail,re.I)
                and re.search(r'\b(?:its|their)\s*[\[(（\s]*$',tail,re.I)):
            return True
    return False


def _uses(line, kind, scope, symbols=None):
    # The ordinary parser includes subpanel suffixes (7.3a/7.3b), grouped
    # numbers and ranges.  Recovery must retain that shared literal meaning.
    text = re.sub(r'(?<=[0-9])\s*([.\-])\s*(?=[0-9])', r'\1', _text(line.text))
    pattern = FIGURE_REFERENCE if kind == 'figure' else TABLE_REFERENCE
    for match in reference_matches(pattern, text):
        if not local_reference(text, match):
            continue
        if kind == 'figure' and symbols is not None and graph_variable_use(text, match, symbols, line=line):
            continue
        reference = _label(match.group('number'), line, scope)
        if _external(text, kind, reference.number) or _foreign_usage_owner(text,match):
            continue
        qualifier = APPENDIX_QUALIFIER.search(text[max(0, match.start()-16):match.start()])
        if qualifier:
            reference = replace(reference, target_scope=normalize_label(qualifier.group('number')))
        yield reference


def _font(page, fallback):
    font = body_font(page) or fallback
    # On a page consisting mostly of a long smaller caption, full-width
    # caption/code rows can dominate the shared font sample.  Native numbered
    # section ink and two independently printed paragraph rows prove the body
    # size without promoting a plot's small internal labels.
    for heading in page.lines:
        if (heading.source == 'native' and heading.bold and heading.font_size
                and re.fullmatch(r'(?:[A-Z]\.)?\d+(?:\.\d+)+', normalize_text(heading.text).strip())
                and font < heading.font_size <= font*1.20):
            count = sum(l.source == 'native' and not l.bold and l.font_size
                        and abs(l.font_size-heading.font_size) <= .2
                        and _letters(l.text) >= 15 for l in page.lines)
            if count >= 2:
                font = heading.font_size
    return font


def _directory_regions(document):
    keys = set(toc_line_keys(document))
    for page in document.pages:
        ordered = sorted(page.lines, key=lambda l: (l.bbox[1], l.bbox[0]))
        rows = []
        for line in ordered:
            if line.source != 'native' or line.bbox[1] > page.height*.22:
                continue
            row = next((r for r in rows if abs(r[0].bbox[1]-line.bbox[1]) <= 3), None)
            if row is None:
                rows.append([line])
            else:
                row.append(line)
        heading = [r for r in rows if _DIRECTORY.match(''.join(normalize_text(l.text).replace(' ', '') for l in sorted(r, key=lambda l: l.bbox[0])))]
        # PDF extraction may put the right-aligned page number in its own row.
        leaders = [l for l in ordered if re.search(r'(?:[.·…]\s*){3,}', normalize_text(l.text))]
        numbered = [l for l in ordered if any(p.match(normalize_text(l.text)) for p in _TYPED.values())]
        if not heading or len(leaders) < 3 or len(numbered) < 3:
            continue
        # Native heading plus several right-hand page-number leaders proves
        # the directory region, including an entry whose final page number is
        # glued to a full stop and consequently misses the single-row grammar.
        start = min(l.bbox[1] for r in heading for l in r)
        for line in ordered:
            if line.bbox[1] < start:
                continue
            if _CHAPTER.match(normalize_text(line.text).strip()) and line.font_size and line.font_size >= 14:
                break
            keys.add(_key(line))
    return keys


def _chapter(line, page, font, ordered):
    text = normalize_text(line.text).strip()
    if (not _native_glyphs(line) or not font or line.font_size < font*1.15
            or line.bbox[1] >= page.height*.30 or line.bbox[1] <= page.height*.10
            or not _CHAPTER.match(text) or len(text) >= 100
            or re.search(r'[，,。；;!?！？]', text)):
        return False
    # A chapter number can be in a separate native line from its title; large
    # ink suffices even if the PDF does not encode that font as bold.
    if any(0 < abs(other.page_number-line.page_number) <= 2
           and normalize_text(other.text).strip() == text
           and other.font_size and abs(other.font_size-line.font_size) <= .5
           and abs(other.bbox[1]-line.bbox[1]) <= 3
           and abs(other.bbox[0]-line.bbox[0]) <= 5 for other in ordered):
        return False
    return not any(_inside(line.bbox, b) for b in (*page.images, *page.tables))


def _zones(document, directories, fonts):
    # The existing scope recognizer already carries conservative appendix and
    # supplementary-hierarchy evidence.  Add only a native chapter boundary;
    # target labels retain their original scope for physical identity.
    base, _ = _scope_map(document, directories)
    from .usage_scope import usage_scope_map
    usage_scopes = usage_scope_map(document, directories)
    pages = {p.number: p for p in document.pages}
    ordered = sorted(document.lines, key=lambda l: (l.page_number, l.bbox[1], l.bbox[0]))
    zones = {}; positions = []; states = []
    scope = 'body'; epoch = 0; resumed = False; previous_base = 'body'
    for line in ordered:
        key = _key(line); page = pages[line.page_number]; font = fonts[page.number]
        bscope = base.get(key, previous_base)
        if key not in directories:
            text = normalize_text(line.text).strip()
            formal = (_NONBODY.fullmatch(text) and _native_glyphs(line)
                      and line.bbox[1] > page.height*.10
                      and line.font_size >= font*.85
                      and not any(_inside(line.bbox, b) for b in (*page.images, *page.tables)))
            if formal or (bscope == '_nonbody' and previous_base != '_nonbody'):
                scope = '_nonbody'; resumed = False
            if _chapter(line, page, font, ordered):
                if scope == '_nonbody':
                    epoch += 1
                scope = 'body'; resumed = True
            elif bscope != '_nonbody':
                if bscope != previous_base or not resumed:
                    scope = bscope
            previous_base = bscope
        zones[key] = scope, epoch
        if usage_scopes.get(key, ('body', 0))[1]:
            # A complete independently printed manuscript has a proven
            # identity even when the frozen parser still calls it nonbody.
            zones[key] = usage_scopes[key]
        positions.append((line.page_number, line.bbox[1], line.bbox[0]))
        states.append(zones[key])

    def zone(line):
        if _key(line) in zones:
            return zones[_key(line)]
        i = bisect_right(positions, (line.page_number, line.bbox[1], line.bbox[0]))-1
        return states[i] if i >= 0 else ('body', 0)
    return zone


def _body_style(line, font):
    return (line.source == 'native' and _native_glyphs(line) and not line.bold
            and font*.94 <= line.font_size <= font*1.06 and abs(line.direction[1]) < .05)


def _short_reference_tail(line, page, font):
    """A short typed citation can finish an independently proven body row."""
    from .usage_paragraphs import _intervening_content
    text = normalize_text(line.text).strip()
    match = next((pattern.match(text) for pattern in (FIGURE_REFERENCE, TABLE_REFERENCE)
                  if pattern.match(text)), None)
    if match is None or not re.fullmatch(r'\s*(?:当中|中|内|里|所示)?\s*[。.!?！？]', text[match.end():]):
        return False
    for previous in page.lines:
        if (not _body_style(previous, font) or _letters(previous.text) < 15
                or previous.bbox[2]-previous.bbox[0] < page.width*.6
                or previous.role in {'figure_caption','table_caption','header','footer','equation'}):
            continue
        prefix = normalize_text(previous.text).strip()
        cue = re.search(r'(?:如|参见|详见|展示在|显示在|列于|示于)\s*$', prefix)
        # The conjunction must follow a real typed reference, not arbitrary
        # prose. Paragraph reconstruction supplies adjacency and alignment.
        grouped = bool(re.search(r'(?:和|与|及|、|and)\s*$', prefix, re.I)
                       and any(tuple(_uses(previous, kind, 'body')) for kind in ('figure','table')))
        if ((cue or grouped) and not _intervening_content(previous, line, page)
                and len(usage_paragraphs([(previous,'body'),(line,'body')])) == 1):
            return True
    return False


def _prose_shape(line, page, font):
    """Independent paragraph layout, including short wrapped final rows."""
    if not _body_style(line, font):
        return False
    short_tail = _letters(line.text) < 4 and _short_reference_tail(line, page, font)
    # Inline mathematics splits one physical body row into several native
    # text runs. Its short typed first run still belongs to that full row.
    same_row = [l for l in page.lines if l != line and _body_style(l, font)
                and l.role not in {'header','footer','figure_caption','table_caption','equation'}
                and abs(l.bbox[1]-line.bbox[1]) <= font*.35
                and 0 <= l.bbox[0]-line.bbox[2] <= font*3]
    split_body = any(_letters(l.text) >= 15 and l.bbox[2]-line.bbox[0] >= page.width*.6
                     and re.search(r'[，,。；;!?！？]$', l.text.strip()) for l in same_row)
    if _letters(line.text) < 4 and not short_tail and not split_body:
        return False
    if line.role in {'header', 'footer', 'equation'} or not page.height*.10 < line.bbox[1] < page.height*.94:
        return False
    h = max(font, line.bbox[3]-line.bbox[1])
    ordinary = [l for l in page.lines if l != line and _body_style(l, font)
                and l.role not in {'header', 'footer', 'figure_caption', 'table_caption', 'equation'}
                and l.bbox[2]-l.bbox[0] >= page.width*.35 and _letters(l.text) >= 15
                and not any(pattern.match(normalize_text(l.text)) for pattern in _TYPED.values())]
    width = line.bbox[2]-line.bbox[0]
    wide = width >= page.width*.55 and _letters(line.text) >= 15
    peer = False
    for other in ordinary:
        gap = min(abs(line.bbox[1]-other.bbox[3]), abs(other.bbox[1]-line.bbox[3]))
        if gap <= h*1.5 and abs(line.bbox[0]-other.bbox[0]) <= h*2.5:
            peer = True
            break
    # Mathematical inline fragments sometimes split the preceding prose row.
    # Require its native body ink to span the paragraph, not a lone plot label.
    previous = [l for l in page.lines if l != line and _body_style(l, font)
                and 0 <= line.bbox[1]-l.bbox[3] <= h*1.3]
    if previous:
        row_y = max(l.bbox[1] for l in previous)
        row = [l for l in previous if abs(l.bbox[1]-row_y) <= h*.6]
        if row and max(l.bbox[2] for l in row)-min(l.bbox[0] for l in row) >= page.width*.6:
            peer = True
    margin = min((l.bbox[0] for l in ordinary), default=None)
    first = (margin is not None and font*.8 <= line.bbox[0]-margin <= font*3.5
             and width >= page.width*.35 and _letters(line.text) >= 15)
    inside = any(_inside(line.bbox, b) for b in (*page.images, *page.tables, *page.graphics)
                 if b[2]-b[0] >= 30 and b[3]-b[1] >= 15)
    # Oversized visual carriers can enclose genuine prose.  In that case a
    # second native paragraph row must establish the independent body block.
    return bool((wide or peer or first) and (not inside or (peer and (wide or first or short_tail or split_body))))


def _footnote(line, page, font):
    if (line.source != 'native' or not line.font_size or line.font_size >= font*.83
            or line.bbox[1] <= page.height*.65):
        return False
    small = [l for l in page.lines if l.source == 'native' and l.font_size
             and abs(l.font_size-line.font_size) <= .5 and l.bbox[1] >= page.height*.65]
    block = [l for l in small if l == line or line.block_id is not None and l.block_id == line.block_id]
    return any(_letters(l.text) >= 4 and re.search(r'(?:出自|来源|摘自|引自|source|adapted|reproduced|copyright)', l.text, re.I)
               for l in block)


def _own_visual(target, kind, page):
    """Native visual adjacency can prove a title despite unusual typography.

    The caption must be outside and aligned with its own physical object.
    Intervening body or section ink breaks adjacency, so a paragraph beneath
    a table or enclosed in an oversized carrier is not promoted to a title.
    """
    line = target.line; a = line.bbox
    boxes = (*page.images, *page.graphics) if kind == 'figure' else page.tables
    for b in boxes:
        if b[2]-b[0] < 30 or b[3]-b[1] < 15 or _inside(a, b):
            continue
        overlap = min(a[2], b[2])-max(a[0], b[0])
        if overlap < min(a[2]-a[0], b[2]-b[0])*.4:
            continue
        if abs((a[0]+a[2]-b[0]-b[2])/2) > max((line.font_size or 12)*3, (b[2]-b[0])*.15):
            continue
        if 0 <= a[1]-b[3] <= 65:
            low, high = b[3], a[1]
        elif 0 <= b[1]-a[3] <= 65:
            low, high = a[3], b[1]
        else:
            continue
        intervening = [row for row in page.lines if row != line
                       and low+.5 < (row.bbox[1]+row.bbox[3])/2 < high-.5
                       and _letters(row.text) >= 3
                       and min(row.bbox[2], max(a[2], b[2])) > max(row.bbox[0], min(a[0], b[0]))
                       and not (line.block_id is not None and row.block_id == line.block_id)]
        if not intervening:
            return True
    return False


def _body_target(target, kind, peers, pages, fonts):
    line = target.line; page = pages.get(line.page_number)
    if page is None or _own_visual(target, kind, page) or not _prose_shape(line, page, fonts[page.number]):
        return False
    # A separate, normally styled caption for the same number establishes that
    # this body-sized native paragraph cannot itself be that object's title.
    for other in peers:
        if other == target or other.number != target.number or _key(other.line) == _key(line):
            continue
        row = other.line
        if (row.source not in {'native','local_caption_prefix_ocr'} or not row.font_size
                or not (row.bold or row.font_size < line.font_size*.94)):
            continue
        if abs(row.page_number-line.page_number) > 1:
            continue
        # The opposite-language line of a bilingual caption remains a title.
        if row.page_number == line.page_number and abs(row.bbox[1]-line.bbox[1]) <= 70:
            chinese = normalize_text(line.text).lstrip().startswith(('图', '表'))
            if normalize_text(row.text).lstrip().startswith(('图', '表')) != chinese:
                continue
        return True
    return False


def _caption_regions(targets, pages):
    protected = set()
    for target in targets:
        line = target.line; page = pages.get(line.page_number)
        protected.add(_key(line))
        if page is None:
            continue
        anchors = [l for l in page.lines if _inside(l.bbox, line.bbox, 1)]
        if not anchors:
            anchors = [line]
        for anchor in anchors:
            protected.add(_key(anchor))
            # Native caption continuations retain the same font and block.
            # Do not extend into an independently indented body paragraph.
            for row in page.lines:
                if (anchor.block_id is not None and row.block_id == anchor.block_id
                        and row.source == 'native' and row.font_size and anchor.font_size
                        and abs(row.font_size-anchor.font_size) <= anchor.font_size*.06
                        and row.bold == anchor.bold):
                    protected.add(_key(row))
        for row in page.lines:
            if (row.source == 'native' and row.font_size and line.font_size
                    and abs(row.font_size-line.font_size) <= line.font_size*.06
                    and abs(row.bbox[1]-line.bbox[1]) <= 70
                    and any(any(r.number == target.number for r in _uses(row, k, target.scope))
                            for k in ('figure', 'table'))
                    and any(pattern.match(normalize_text(row.text)) for pattern in _TYPED.values())):
                protected.add(_key(row))
    return protected


def _inline_heading_wrapped_document(document,protected,directories,zone):
    """Join actual same-row body spans only before a broken English type word.

    A short emphasized inline heading can make the frozen parser split a
    full-width native row. Retain all actual glyph rectangles; the existing
    wrapped-reference parser still proves the next row and literal number.
    """
    from .usage_wrapped_references import _complete_native_ink
    excluded={'figure','table','figure_caption','table_caption','header','footer','equation'}
    words=('figure','figures','table','tables');replacements={}
    for page in document.pages:
        for line in page.lines:
            prefix=re.search(r'(?<![A-Za-z0-9_./\\])([A-Za-z]+)-\s*$',normalize_text(line.text))
            if (prefix is None or not any(word.startswith(prefix[1].casefold()) and
                    0<len(prefix[1])<len(word) for word in words)
                    or line.source!='native' or line.bold or not line.font_size
                    or line.role in excluded or _key(line) in protected|directories
                    or zone(line)[0]=='_nonbody'):continue
            peers=[p for p in page.lines if p is not line and p.source=='native' and p.bold
                   and p.font_size and abs(p.font_size-line.font_size)<=.2
                   and p.direction==line.direction==(1.0,0.0)
                   and p.role not in excluded and _key(p) not in protected|directories
                   and zone(p)==zone(line)
                   and 0<=line.bbox[0]-p.bbox[2]<=line.font_size*1.5
                   and abs(line.bbox[1]-p.bbox[1])<=line.font_size*.15
                   and abs(line.bbox[3]-p.bbox[3])<=line.font_size*.15
                   and 4<=_letters(p.text)<=45 and re.search(r'[.:：]\s*$',p.text)
                   and not any(pattern.match(normalize_text(p.text)) for pattern in _TYPED.values())]
            if len(peers)!=1:continue
            peer=peers[0]
            if any(_inside(p.bbox,b) for p in (peer,line) for b in (*page.images,*page.tables,*page.graphics)):continue
            first=_complete_native_ink(peer,document);second=_complete_native_ink(line,document)
            if first is None or second is None:continue
            head=normalize_text(first.text);tail=normalize_text(second.text);shift=len(head)+1
            joined=replace(second,text=head+' '+tail,bold=False,
                bbox=(first.bbox[0],min(first.bbox[1],second.bbox[1]),second.bbox[2],max(first.bbox[3],second.bbox[3])),
                text_regions=first.text_regions+tuple((a+shift,b+shift,bbox) for a,b,bbox in second.text_regions),reference_regions=())
            if not _native_glyphs(joined):continue
            if _key(peer) in replacements or _key(line) in replacements:continue
            replacements[_key(peer)]=None;replacements[_key(line)]=joined
    if not replacements:return None
    return replace(document,pages=tuple(replace(page,lines=tuple(replacements.get(_key(line),line)
        for line in page.lines if replacements.get(_key(line),line) is not None)) for page in document.pages))


def _literal_caption_identity(target, kind):
    text = re.sub(r'(?<=[0-9])\s*([.\-])\s*(?=[0-9])', r'\1', normalize_text(target.line.text))
    match = caption_match(text, kind)
    return replace(target, number=normalize_label(match.group('number'))) if match else target


def _restore_bilingual_captions(targets, kind, document):
    """Recover an adjacent translation dropped after a spaced-number mismatch."""
    from .caption_identity import _pair_distance
    targets = [_literal_caption_identity(t, kind) for t in targets]
    lines = document.lines
    by_page = {}
    for target in targets:
        by_page.setdefault(target.line.page_number, []).append(target)
    known = {_key(t.line) for t in targets}
    additions = []
    for line in lines:
        if _key(line) in known or line.source != 'native':
            continue
        for anchor in by_page.get(line.page_number, ()):
            if abs(line.bbox[1] - anchor.line.bbox[1]) > 150:
                continue
            if (line.font_size and anchor.line.font_size
                    and abs(line.font_size-anchor.line.font_size) > anchor.line.font_size*.12):
                continue
            candidate = _literal_caption_identity(Label('', line, anchor.scope), kind)
            if candidate.number and _pair_distance(anchor, candidate, lines, document) is not None:
                additions.append(candidate); known.add(_key(line)); break
    return targets + additions


def _explicit_usage_refs(result, directories, protected):
    """Only literal type-and-number ink outside captions/directories is usage."""
    blocked = protected | directories
    by_page = {}
    for page, box in blocked:
        by_page.setdefault(page, []).append(box)
    wrapped = {}
    for evidence in getattr(result, 'usage_recovered_refs', ()):
        if evidence.get('criterion') != 'independent native wrapped type; unique physical caption group':
            continue
        first = evidence['preceding_row']['text']
        # The recovery already proved contiguous native body rows and a real
        # hyphenated type word; retain that literal text while the highlight
        # stays on the number's ink in the second row.
        literal = re.sub(r'-\s*$', '', first) + evidence['text']
        wrapped[(evidence['kind'], evidence['number'], evidence['page'], evidence['bbox'])] = literal
    for kind, names in (('figure', ('figure_refs','graphic_figure_refs')),
                        ('table', ('table_refs','graphic_table_refs'))):
        for name in names:
            kept = []
            for ref in getattr(result, name):
                if _key(ref.line) in directories or _key(ref.line) in protected:
                    continue
                # Reference bbox can be narrowed to its number by the parser.
                if any(_inside(ref.line.bbox, box) for box in by_page.get(ref.line.page_number, ())):
                    continue
                text = wrapped.get((kind, ref.number, ref.line.page_number, ref.line.bbox), ref.line.text)
                if any(literal.number == ref.number for literal in _uses(replace(ref.line, text=text), kind, ref.scope)):
                    kept.append(ref)
            setattr(result, name, kept)


def recover_usage_index(index: DocumentIndex, *, explicit_only=False) -> DocumentIndex:
    """Return a physically bound 15/16-only view; never mutate ``index``."""
    result = copy.copy(index)
    for name, value in index.__dict__.items():
        if isinstance(value, (list, dict, set)):
            setattr(result, name, _clone(value))
    pages = {p.number: p for p in index.document.pages}
    sizes = [l.font_size for l in index.lines if l.source == 'native' and not l.bold
             and l.font_size and _letters(l.text) >= 15]
    fallback = median(sizes) if sizes else 12
    fonts = {p.number: _font(p, fallback) for p in index.document.pages}
    directories = _directory_regions(index.document)
    zone = _zones(index.document, directories, fonts)
    discarded = set()
    for kind, name in (('figure', 'figures'), ('table', 'tables')):
        targets = _restore_bilingual_captions(getattr(result, name), kind, index.document)
        keep = []
        for target in targets:
            line = target.line; page = pages.get(line.page_number)
            footnote_target = (page is not None and _footnote(line, page, fonts[page.number])
                               and not _own_visual(target, kind, page)
                               and any(other != target and other.number == target.number
                                       and other.line.page_number == line.page_number
                                       and other.line.bbox[3]+30 < line.bbox[1]
                                       and not _footnote(other.line, page, fonts[page.number])
                                       for other in targets))
            remove = (_key(line) in directories or footnote_target
                      or _body_target(target, kind, targets, pages, fonts))
            if remove:
                discarded.add(_key(line))
            else:
                keep.append(target)
        setattr(result, name, keep)
    protected = _caption_regions(result.figures + result.tables, pages)
    eligible = []
    for page in index.document.pages:
        for line in sorted(page.lines, key=lambda l: (l.bbox[1], l.bbox[0])):
            if (_key(line) in directories or _key(line) in protected
                    or _footnote(line, page, fonts[page.number]) or not _prose_shape(line, page, fonts[page.number])):
                continue
            scope, epoch = zone(line)
            if scope == '_nonbody':
                continue
            eligible.append((line, (scope, epoch)))
    from .usage_formal_aliases import inline_alias_fragments
    eligible.extend(inline_alias_fragments(result,eligible,pages,fonts,protected,directories,zone))
    eligible.sort(key=lambda item:(item[0].page_number,item[0].bbox[1],item[0].bbox[0]))
    paragraphs = usage_paragraphs(eligible, index.document)
    graph_symbols = defined_graph_symbols(index.document)
    bindings = getattr(result, 'indirect_reference_targets', {})
    result.indirect_reference_targets = _clone(bindings)
    result.usage_recovered_refs = []
    for kind, target_name, ref_name in (('figure', 'figures', 'graphic_figure_refs'), ('table', 'tables', 'graphic_table_refs')):
        targets = getattr(result, target_name)
        groups = caption_groups(targets, index.lines, index.document)
        by_number = {}
        for group in groups:
            for number in {t.number for t in group}:
                by_number.setdefault(number, []).append(group)
        refs = getattr(result, ref_name)
        known = {indirect_reference_key(kind, r) for r in refs}
        for line, (scope, epoch) in paragraphs:
            for reference in _uses(line, kind, scope, graph_symbols if kind == 'figure' else None):
                candidates = [g for g in by_number.get(reference.number, [])
                              if any(zone(t.line) == (scope, epoch) for t in g)]
                if reference.target_scope is not None:
                    candidates = [g for g in candidates if any(t.scope == reference.target_scope for t in g)]
                if len(candidates) != 1:
                    continue
                group = candidates[0]
                target = next(t for t in group if t.number == reference.number)
                # Preserve the target's original scope; renumbering the scope
                # of a second manuscript would let first-copy direct refs
                # credit that second, separately printed physical object.
                bound = replace(reference, scope=target.scope, target_scope=target.target_scope)
                key = indirect_reference_key(kind, bound)
                if key not in known:
                    refs.append(bound); known.add(key)
                result.indirect_reference_targets.setdefault(key, set()).update(physical_target_key(kind, t) for t in group)
                result.usage_recovered_refs.append(dict(kind=kind, number=bound.number,
                    page=line.page_number, bbox=line.bbox, text=line.text,
                    target_page=target.line.page_number, target_bbox=target.line.bbox,
                    criterion='independent native paragraph; unique physical caption group'))
    from .usage_formal_aliases import formal_alias_references,formal_symbol_references
    from .usage_wrapped_references import wrapped_native_references
    wrapped=wrapped_native_references(index.document,pages,fonts,protected,directories,zone,_prose_shape,_uses,graph_symbols)
    inline_document=_inline_heading_wrapped_document(index.document,protected,directories,zone)
    if inline_document is not None:
        inline_pages={p.number:p for p in inline_document.pages}
        wrapped.extend(wrapped_native_references(inline_document,inline_pages,fonts,protected,directories,zone,_prose_shape,_uses,graph_symbols))
    for kind,target_name,ref_name in (('figure','figures','graphic_figure_refs'),('table','tables','graphic_table_refs')):
        targets=getattr(result,target_name)
        groups=list(caption_groups(targets,index.lines,index.document))
        references=getattr(result,ref_name)
        known={indirect_reference_key(kind,r) for r in references}
        for actual_kind,reference,owner,first in wrapped:
            if actual_kind!=kind:continue
            candidates=[g for g in groups if any(t.number==reference.number and zone(t.line)==owner for t in g)]
            if len(candidates)!=1:continue
            group=candidates[0];target=next(t for t in group if t.number==reference.number)
            bound=replace(reference,scope=target.scope,target_scope=target.target_scope)
            key=indirect_reference_key(kind,bound)
            if key not in known:references.append(bound);known.add(key)
            result.indirect_reference_targets.setdefault(key,set()).update(physical_target_key(kind,t) for t in group)
            result.usage_recovered_refs.append(dict(kind=kind,number=bound.number,
                page=reference.line.page_number,bbox=reference.line.bbox,text=reference.line.text,
                preceding_row=dict(page=first.page_number,bbox=first.bbox,text=first.text),
                target_page=target.line.page_number,target_bbox=target.line.bbox,
                criterion='independent native wrapped type; unique physical caption group'))
    groups=list(caption_groups(result.figures,index.lines,index.document))
    known={indirect_reference_key('figure',r) for r in result.graphic_figure_refs}
    for criterion,references in (
        ('independent native typed reference; unique physical formal figure',formal_alias_references(result,groups,paragraphs,zone)),
        ('independent native formal symbol; unique physical formal definition',formal_symbol_references(result,groups,paragraphs,zone))):
        for reference,group in references:
            target=next(t for t in group if t.number==reference.number)
            bound=replace(reference,scope=target.scope,target_scope=target.target_scope)
            key=indirect_reference_key('figure',bound)
            if key not in known:
                result.graphic_figure_refs.append(bound);known.add(key)
            result.indirect_reference_targets.setdefault(key,set()).update(physical_target_key('figure',t) for t in group)
            result.usage_recovered_refs.append(dict(kind='figure',number=bound.number,
                page=reference.line.page_number,bbox=reference.line.bbox,text=reference.line.text,
                target_page=target.line.page_number,target_bbox=target.line.bbox,
                criterion=criterion))
    from .usage_display_references import display_references
    for reference,group,criterion in display_references(result,groups,paragraphs,zone):
        target=next(t for t in group if t.number==reference.number)
        bound=replace(reference,scope=target.scope,target_scope=target.target_scope)
        key=indirect_reference_key('figure',bound)
        if key not in known:
            result.graphic_figure_refs.append(bound);known.add(key)
        result.indirect_reference_targets.setdefault(key,set()).update(physical_target_key('figure',t) for t in group)
        result.usage_recovered_refs.append(dict(kind='figure',number=bound.number,
            page=reference.line.page_number,bbox=reference.line.bbox,text=reference.line.text,
            target_page=target.line.page_number,target_bbox=target.line.bbox,criterion=criterion))
    if explicit_only:
        _explicit_usage_refs(result, directories, protected)
    return result


def usage_resolved_target(reference, target, targets, scopes):
    """The ordinary literal resolver confined to one usage manuscript epoch."""
    from .usage_scope import usage_epoch, usage_reference_epoch
    from .local_rules import resolved_target
    epoch = usage_reference_epoch(scopes, reference)
    return (epoch >= 0 and epoch == usage_epoch(scopes, target)
            and resolved_target(reference, target, targets))


def usage_inferred_target(reference, target, kind, index, groups, targets, scopes):
    """Preserve physical bindings and unbound uniqueness within one epoch."""
    from .usage_scope import usage_epoch, usage_reference_epoch
    from .local_rules import inferred_target
    epoch = usage_reference_epoch(scopes, reference)
    if epoch < 0 or epoch != usage_epoch(scopes, target):
        return False
    local_targets = [t for t in targets if usage_epoch(scopes, t) == epoch]
    local_groups = [g for g in groups if g and all(usage_epoch(scopes, t) == epoch for t in g)]
    return inferred_target(reference, target, kind, index, local_groups, local_targets)
