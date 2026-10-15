"""An immutable appendix view used only by the full-text usage rules (15/16).

The caller keeps the original reference index: this view defines eligible
target positions and readable pages, not which explicit references may count.
"""
from collections import Counter
from bisect import bisect_right
from dataclasses import replace
import re

from .model import PdfDocument
from .numbering import normalize_text, is_toc_line, toc_line_keys, caption_match


_APPENDIX = re.compile(r'^(?:附\s*录|appendix\b|appendices\b)\s*(.*)$', re.I)
_SUFFIX_APPENDIX = re.compile(
    r'^(.{1,80}?)\s*[（(]\s*(?:附\s*录\s*(?:[A-Z]|\d+(?:\.\d+)?|[一二三四五六七八九十]+)?|'
    r'appendix\b\s*(?:[A-Z]|\d+(?:\.\d+)?|[IVXLCDM]+)?)\s*[）)]$', re.I)
_CHAPTER = re.compile(r'^(?:第\s*[一二三四五六七八九十百〇零0-9]+\s*章|chapter\s+[0-9IVXLCDM]+\b)', re.I)
_NARRATIVE = re.compile(
    r'^(?:中|内|里|所|介绍|展示|讨论|描述|给出|包含|列举|列出|参见|详见|可见|'
    r'提供|说明|使用|分析|是|有|将|为|见(?:图|表)|'
    r'(?:reports?|provides?|contains?|shows?|presents?|describes?|illustrates?|'
    r'discusses?|lists?|is|are|was|were|has|have|in|of)\b)', re.I)


def _marginal(line, page):
    role = line.role.lower().replace('_', ' ')
    return (any(word in role for word in ('header', 'footer', 'page number'))
            or line.bbox[1] >= page.height * .92
            or (line.bbox[3] <= page.height * .105
                and (line.font_size or line.bbox[3] - line.bbox[1]) <= 12))


def _body_size(page):
    sizes = [round(l.font_size or l.bbox[3] - l.bbox[1], 1) for l in page.lines
             if not _marginal(l, page) and l.bbox[2] - l.bbox[0] >= page.width * .6
             and len(l.text.strip()) >= 12]
    return Counter(sizes).most_common(1)[0][0] if sizes else 12.0


def _heading_style(line, page):
    if _marginal(line, page):
        return False
    role = line.role.lower()
    size = line.font_size or line.bbox[3] - line.bbox[1]
    if any(word in role for word in ('heading', 'section title', 'chapter title')):
        return True
    # Large, compact standalone type separates a section title from prose.
    body_size = _body_size(page)
    centered_bold = (line.bold and size >= body_size * .95
                     and abs((line.bbox[0] + line.bbox[2]) / 2 - page.width / 2) < page.width * .08
                     and line.bbox[2] - line.bbox[0] < page.width * .7)
    return ((size >= max(13.5, body_size * 1.18) or centered_bold)
            and line.bbox[2] - line.bbox[0] < page.width * .85
            and len(normalize_text(line.text).strip()) <= 80)


def _running_header_keys(document):
    repeated = {}
    for page in document.pages:
        for line in page.lines:
            if line.bbox[3] > page.height * .105 or 'heading' in line.role.lower():
                continue
            signature = (normalize_text(line.text).strip(),
                         round(line.bbox[0] / page.width, 2),
                         round(line.bbox[1] / page.height, 2),
                         round(line.font_size or line.bbox[3] - line.bbox[1], 1))
            repeated.setdefault(signature, []).append((page.number, line.bbox))
    return {key for values in repeated.values() if len({p for p, _ in values}) >= 2
            for key in values}


def _directory_page(page):
    rows = [normalize_text(l.text).strip() for l in page.lines]
    has_title = any(re.fullmatch(r'(?:目\s*录|contents|table\s+of\s+contents)'
                                r'\s*(?:(?:[（(]\s*(?:续|continued)\s*[）)])|(?:[-—:]\s*)?(?:续|continued))?', t, re.I)
                    for t in rows)
    return has_title and sum(bool(re.search(r'(?:\s|[.·…])\d+\s*$', t)) for t in rows) >= 2


def _directory_pages(document):
    result = set()
    previous = False
    for page in document.pages:
        rows = [normalize_text(line.text).strip() for line in page.lines
                if not _marginal(line, page)]
        entries = [text for text in rows
                   if re.match(r'^(?:chapter\s+[0-9IVXLCDM]+|第\s*[一二三四五六七八九十百0-9]+\s*章|'
                               r'appendix\s+[A-Z0-9]|附\s*录\s*[A-Z0-9])', text, re.I)
                   and re.search(r'(?:\s|[.·…])\d+\s*$', text)]
        current = (_directory_page(page) or
                   (previous and len(entries) >= 2 and len(entries)*2 >= len(rows)))
        if current:
            result.add(page.number)
        previous = current
    return result


def _appendix_heading(line, page, directory):
    text = normalize_text(line.text).strip()
    match = _APPENDIX.match(text)
    suffix = _SUFFIX_APPENDIX.fullmatch(text)
    if not match and not suffix:
        return False
    if ((page.number, line.bbox) in directory or is_toc_line(text)
            or _directory_page(page) or not _heading_style(line, page)):
        return False
    if not match:
        # The appendix identifier is an actual part of a standalone title,
        # not a prose reference such as '(see Appendix A)' or a TOC row.
        return (not any(caption_match(text, kind) for kind in ('figure', 'table'))
                and not re.search(r'[。；;，,!?！？]', suffix[1]))
    tail = match[1].strip()
    # A heading may have a letter/number and a title, including no identifier.
    tail = re.sub(r'^(?:[A-Z]|\d+)(?=\s|[:：]|$)\s*', '', tail, flags=re.I)
    tail = tail.lstrip(':：- ').strip()
    return not (re.search(r'[。；;，,!?！？]', tail) or _NARRATIVE.match(tail)
                or (tail.endswith('.') and len(tail.split()) > 2))


def _body_heading(line, page):
    text = normalize_text(line.text).strip()
    return bool(_CHAPTER.match(text) and _heading_style(line, page)
                and not is_toc_line(text) and not re.search(r'[。；;，,!?！？]', text))


def _appendix_title_fragments(page, directory):
    """Identify adjacent chapter text in the same physical appendix title.

    Native extraction can split a title at its large inter-word gap.  A
    chapter phrase on that baseline is title content, so it cannot restart
    the main body.  Block identity alone never joins separate title rows.
    """
    markers = [line for line in page.lines
               if _appendix_heading(line, page, directory)]
    fragments = set()
    for line in page.lines:
        if not _body_heading(line, page):
            continue
        for marker in markers:
            if line.source != marker.source:
                continue
            if (line.block_id is not None and marker.block_id is not None
                    and line.block_id != marker.block_id):
                continue
            if any(abs(l.direction[0] - 1) > .05 or abs(l.direction[1]) > .05
                   for l in (line, marker)):
                continue
            a, b = marker.bbox, line.bbox
            heights = (a[3] - a[1], b[3] - b[1])
            sizes = (marker.font_size or heights[0], line.font_size or heights[1])
            size = min(sizes)
            if size <= 0 or max(sizes) > size * 1.15:
                continue
            overlap = min(a[3], b[3]) - max(a[1], b[1])
            gap = b[0] - a[2]
            if (abs(a[1] - b[1]) <= max(2, min(heights) * .2)
                    and overlap >= min(heights) * .7
                    and -.15 * size <= gap <= 2 * size):
                fragments.add(id(line))
                break
    return fragments


def _new_cover(page):
    rows = [normalize_text(l.text).strip() for l in page.lines if not _marginal(l, page)]
    text = '\n'.join(rows)
    institutional = bool(re.search(r'大学|\bUniversity\b|\bInstitute\b', text, re.I))
    thesis = [l for l in page.lines if re.search(r'学位论文|\b(?:thesis|dissertation)\b', l.text, re.I)]
    metadata = sum(bool(re.search(pattern, text, re.I)) for pattern in
                   (r'作者|姓名|\b(?:author|candidate|student)\s*:',
                    r'导师|指导教师|\b(?:advisor|supervisor)\s*:'))
    return institutional and metadata == 2 and any(_heading_style(l, page) for l in thesis)


def usage_document(document: PdfDocument) -> PdfDocument:
    """Clear verified appendix intervals without mutating PDF geometry or refs.

    A genuine chapter or new thesis cover can restore the main-body interval.
    An unreadable mixed page stays unreadable when body content precedes its
    appendix title; a wholly excluded appendix page cannot block rules 15/16.
    """
    directory_pages = _directory_pages(document)
    directory = (toc_line_keys(document) | _running_header_keys(document)
                 | {(page.number, line.bbox) for page in document.pages
                    if page.number in directory_pages for line in page.lines})
    active = False
    result = []
    for page in document.pages:
        title_fragments = _appendix_title_fragments(page, directory)
        started_active = active
        restored = active and page.number not in directory_pages and _new_cover(page)
        if restored:
            active = False
        kept = []
        excluded = started_active and not restored
        for line in sorted(page.lines, key=lambda l: (l.bbox[1], l.bbox[0])):
            if (_appendix_heading(line, page, directory)
                    or id(line) in title_fragments):
                active = True
                excluded = True
            elif (active and _body_heading(line, page) and page.number not in directory_pages
                  and (page.number, line.bbox) not in directory):
                active = False
                kept.append(line)
            elif not active:
                kept.append(line)
        if excluded and not any(not _marginal(l, page) for l in kept):
            kept = []
        retained = set(id(l) for l in kept)
        lines = tuple(l for l in page.lines if id(l) in retained)
        # Preserve the original input tuple and each line's identity/order.
        result.append(replace(page, lines=lines,
                              unreadable=False if excluded and not lines else page.unreadable))
    return replace(document, pages=tuple(result))


def _native_rows(page):
    """Join only neighboring native title fragments on their physical row."""
    from .bibliography_scope_resume import _native_glyphs
    rows = []
    for line in sorted(page.lines, key=lambda l: (l.bbox[1], l.bbox[0])):
        if not _native_glyphs(line) or _marginal(line, page):
            continue
        row = next((r for r in rows
                    if abs(r[0].bbox[1]-line.bbox[1]) <= min(r[0].font_size, line.font_size)*.2
                    and abs(r[0].font_size-line.font_size) <= .5
                    and r[0].bold == line.bold
                    and (r[0].block_id == line.block_id or
                         r[0].block_id is None or line.block_id is None)
                    and -.5 <= line.bbox[0]-r[-1].bbox[2] <= line.font_size*2.5), None)
        if row is None:
            rows.append([line])
        else:
            row.append(line)
    return rows


def _usage_directory_pages(document):
    # TOC headings may be separate '目'/'录' native runs.  Font/baseline and
    # actual page-number leaders prove a physical directory, not a prose word.
    result = set(_directory_pages(document))
    previous = False
    for page in document.pages:
        title = any(re.fullmatch(r'(?:目\s*录|contents|table\s+of\s+contents)',
                    ' '.join(normalize_text(l.text).strip() for l in row), re.I)
                    and any(_heading_style(l, page) for l in row)
                    for row in _native_rows(page))
        entries = [l for l in page.lines if is_toc_line(normalize_text(l.text))]
        relevant = [l for l in page.lines if not _marginal(l, page)]
        current = (page.number in result or (title and len(entries) >= 3)
                   or (previous and len(entries) >= 3 and len(entries)*2 >= len(relevant)))
        if current:
            result.add(page.number)
        previous = current
    return result


def _usage_thesis_cover(page):
    """Native thesis title and separated author/advisor metadata prove a cover."""
    from .bibliography_scope_resume import _native_glyphs
    rows = [l for l in page.lines if _native_glyphs(l) and not _marginal(l, page)]
    text = '\n'.join(normalize_text(l.text).strip() for l in rows)
    if (re.search(r'签名|签字|声明|答辩|决议|\bsignature\b|\bdeclaration\b', text, re.I)
            or not re.search(r'大学|\bUniversity\b|\bInstitute\b', text, re.I)):
        return False
    thesis = [l for l in rows if re.search(r'学位论文|\b(?:thesis|dissertation)\b', l.text, re.I)
              and l.font_size >= 13.5 and l.bbox[1] < page.height*.5
              and not any(caption_match(l.text, k) for k in ('figure', 'table'))]
    authors = [l for l in rows if re.match(r'^(?:作者|姓名|\b(?:author|candidate|student))\s*[:：]',
                normalize_text(l.text).strip(), re.I)]
    advisors = [l for l in rows if re.match(r'^(?:导师|指导教师|\b(?:advisor|supervisor))\s*[:：]',
                 normalize_text(l.text).strip(), re.I)]
    if not thesis or not authors or not advisors:
        return False
    return any(a != b and a.font_size >= 10 and b.font_size >= 10
               and abs(a.bbox[1]-b.bbox[1]) >= min(a.font_size, b.font_size)*.8
               and a.bbox[1] > min(l.bbox[1] for l in thesis)
               and b.bbox[1] > min(l.bbox[1] for l in thesis)
               for a in authors for b in advisors)


def _usage_first_chapter(line, page, directory, fragments):
    from .bibliography_scope_resume import _native_glyphs
    return bool((page.number, line.bbox) not in directory
                and id(line) not in fragments and _native_glyphs(line)
                and page.height*.10 < line.bbox[1] < page.height*.30
                and _body_heading(line, page)
                and re.match(r'^(?:第\s*(?:一|1)\s*章|chapter\s+(?:1|I)\b)',
                             normalize_text(line.text).strip(), re.I))


def _usage_chapter_prose(document, chapter, directory):
    from .bibliography_scope_resume import _native_glyphs
    rows = []
    for page in document.pages:
        if not chapter.page_number <= page.number <= chapter.page_number+1:
            continue
        size = _body_size(page)
        for line in page.lines:
            if ((page.number, line.bbox) in directory or _marginal(line, page)
                    or not _native_glyphs(line) or line.bold
                    or not size*.90 <= line.font_size <= size*1.10
                    or len(normalize_text(line.text).strip()) < 20
                    or line.bbox[2]-line.bbox[0] < page.width*.5
                    or not re.search(r'[，,。.;；:：]', line.text)
                    or (page.number == chapter.page_number and line.bbox[1] <= chapter.bbox[3])):
                continue
            if any(b[0]-.5 <= line.bbox[0] and b[1]-.5 <= line.bbox[1]
                   and line.bbox[2] <= b[2]+.5 and line.bbox[3] <= b[3]+.5
                   for b in (*page.images, *page.tables)):
                continue
            rows.append(line)
    return len(rows) >= 3


class _UsageScopeFacts(dict):
    """Ordinary scope facts with derived native-ink and position indexes.

    These indexes contain only the mapping's original geometry and identities,
    never a reference decision or a mutable document/index object. Normal dict
    mutations invalidate the derived facts; a subsequent query rebuilds them.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._facts_dirty = True
        self._ensure_facts()

    def _ensure_facts(self):
        if not self._facts_dirty:
            return
        by_page = {}
        positions = []
        for (page, box), identity in self.items():
            by_page.setdefault(page, []).append((box, identity))
            positions.append((page, box[1], box[0], identity[1]))
        positions.sort()
        self._ink_by_page = {page: tuple(rows) for page, rows in by_page.items()}
        self._positions = tuple(positions)
        self._position_keys = tuple(position[:3] for position in positions)
        self._facts_dirty = False

    def ink_on_page(self, page):
        self._ensure_facts()
        return self._ink_by_page.get(page, ())

    def preceding_epoch(self, position):
        self._ensure_facts()
        ordinal = bisect_right(self._position_keys, position) - 1
        return self._positions[ordinal][3] if ordinal >= 0 else -1

    def __setitem__(self, key, value):
        self._facts_dirty = True
        return super().__setitem__(key, value)

    def __delitem__(self, key):
        self._facts_dirty = True
        return super().__delitem__(key)

    def update(self, *args, **kwargs):
        self._facts_dirty = True
        return super().update(*args, **kwargs)

    def setdefault(self, key, default=None):
        self._facts_dirty = True
        return super().setdefault(key, default)

    def pop(self, *args):
        self._facts_dirty = True
        return super().pop(*args)

    def popitem(self):
        self._facts_dirty = True
        return super().popitem()

    def clear(self):
        self._facts_dirty = True
        return super().clear()

    def __ior__(self, other):
        self._facts_dirty = True
        return super().__ior__(other)


def usage_scope_map(document: PdfDocument, directories=()):
    """Pure 15/16 scope facts with separately proved manuscript epochs.

    Shared label scopes and physical keys remain untouched. A second complete
    thesis requires its native cover, independent TOC, genuine first chapter
    and ordinary research paragraphs in order. Its front matter, bibliography
    and real appendix never become body merely because a caption is present.
    """
    from .reference_identity_repair import _scope_map
    from .bibliography_scope_resume import _formal_nonbody_title
    directory_pages = _usage_directory_pages(document)
    directory = (set(directories) | toc_line_keys(document) | _running_header_keys(document)
                 | {(p.number, l.bbox) for p in document.pages if p.number in directory_pages for l in p.lines})
    base, _ = _scope_map(document, directory)
    pages = {p.number: p for p in document.pages}
    ordered = sorted(document.lines, key=lambda l: (l.page_number, l.bbox[1], l.bbox[0]))
    fragments = {p.number: _appendix_title_fragments(p, directory) for p in document.pages}
    chapters = [l for l in ordered if _usage_first_chapter(l, pages[l.page_number], directory, fragments[l.page_number])
                and _usage_chapter_prose(document, l, directory)]
    covers = [p.number for p in document.pages if _usage_thesis_cover(p)]
    proofs = []
    for cover in covers:
        if not any(l.page_number < cover for l in chapters):
            continue
        next_cover = next((p for p in covers if p > cover), float('inf'))
        chapter = next((l for l in chapters if cover < l.page_number < next_cover
                        and any(cover < p < l.page_number for p in directory_pages)), None)
        if chapter is not None:
            proofs.append((cover, chapter))
    starts = {(l.page_number, l.bbox): epoch for epoch, (_, l) in enumerate(proofs, 1)}
    cover_epochs = {p: epoch for epoch, (p, _) in enumerate(proofs, 1)}
    result = {}
    epoch = 0
    active = False
    scope = 'body'
    previous_base = 'body'
    for line in ordered:
        key = line.page_number, line.bbox
        page = pages[line.page_number]
        if line.page_number in cover_epochs and epoch < cover_epochs[line.page_number]:
            epoch = cover_epochs[line.page_number]
            active = False
            scope = '_nonbody'
        bscope = base.get(key, previous_base)
        if key in starts:
            epoch = starts[key]
            active = True
            scope = 'body'
        elif epoch:
            if (_appendix_heading(line, page, directory) or id(line) in fragments[page.number]):
                active = False
                scope = bscope if bscope not in ('body', '_nonbody') else '_nonbody'
            elif (key not in directory and
                  (_formal_nonbody_title(line, _body_size(page), ordered, pages)
                   or (_heading_style(line, page) and re.fullmatch(
                       r'学术论文和科研成果目录|科研成果|研究成果|致\s*谢|Acknowledg(?:e)?ments',
                       normalize_text(line.text).strip(), re.I)))):
                active = False
                scope = '_nonbody'
            elif active:
                scope = 'body'
        else:
            scope = bscope
        result[key] = ('_nonbody' if key in directory else scope, epoch)
        previous_base = bscope
    return _UsageScopeFacts(result)


def _scope_anchors(scopes, line):
    rows = (scopes.ink_on_page(line.page_number) if isinstance(scopes, _UsageScopeFacts)
            else ((box, value) for (page, box), value in scopes.items()
                  if page == line.page_number))
    return [(box, value) for box, value in rows
            if min(line.bbox[2], box[2]) > max(line.bbox[0], box[0])
            and min(line.bbox[3], box[3])-max(line.bbox[1], box[1])
                >= min(line.bbox[3]-line.bbox[1], box[3]-box[1])*.5]


def usage_scope_identity(scopes, line_or_label):
    """Resolve an expanded caption rectangle by its original native anchor."""
    line = getattr(line_or_label, 'line', line_or_label)
    key = line.page_number, line.bbox
    if key in scopes:
        return scopes[key]
    anchors = _scope_anchors(scopes, line)
    identities = {value for _, value in anchors}
    if len(identities) == 1:
        return next(iter(identities))
    # A synthesized span crossing a real boundary cannot inherit whichever
    # label or nearby row happens to be first. Missing ink is likewise unknown.
    return '_nonbody', -1


def is_body_usage_scope(scopes, line_or_label):
    return usage_scope_identity(scopes, line_or_label)[0] == 'body'


def usage_epoch(scopes, line_or_label):
    return usage_scope_identity(scopes, line_or_label)[1]


def usage_reference_epoch(scopes, reference):
    """Keep original explicit refs on excluded pages in their proved epoch.

    The usage document can clear appendix ink while retaining the immutable
    original reference label. Only the established preceding manuscript page
    interval supplies its identity; unknown/cross-boundary spans never default
    to the first manuscript or acquire a body's eligibility.
    """
    epoch = usage_epoch(scopes, reference)
    if epoch >= 0:
        return epoch
    line = getattr(reference, 'line', reference)
    overlap = _scope_anchors(scopes, line)
    if overlap:
        return -1
    position = line.page_number, line.bbox[1], line.bbox[0]
    if isinstance(scopes, _UsageScopeFacts):
        return scopes.preceding_epoch(position)
    preceding = [(page, box[1], box[0], identity[1])
                 for (page, box), identity in scopes.items()
                 if (page, box[1], box[0]) <= position]
    return max(preceding)[3] if preceding else -1
