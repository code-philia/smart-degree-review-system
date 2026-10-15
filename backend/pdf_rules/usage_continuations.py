"""Logical continued-table groups private to the usage rules (15/16)."""
import re

from .model import DocumentIndex, Label
from .numbering import normalize_text, caption_match
from .usage_scope import _body_heading


def _continued(group):
    for label in group:
        text = normalize_text(label.line.text)
        match = caption_match(text, 'table')
        if not match:
            continue
        tail = text[match.end('number'):].strip(' \t-:：.,()（）[]【】')
        # Require a standalone marker, not an arbitrary word beginning with 续.
        if re.match(r'^(?:续表|续前页|续|continued(?:\s+from\s+(?:the\s+)?previous\s+page)?)'
                    r'(?:$|[\s)）\]】:：,，.;；-])', tail, re.I):
            return True
    return False


def _table_box(label, page):
    caption = label.line.bbox
    candidates = []
    for box in page.tables:
        overlap = min(box[2], caption[2]) - max(box[0], caption[0])
        gap = max(box[1] - caption[3], caption[1] - box[3], 0)
        if (box[2] - box[0] >= 60 and box[3] - box[1] >= 20
                and overlap > 0 and gap <= 150):
            candidates.append((gap, box))
    return min(candidates, key=lambda x: x[0])[1] if candidates else None


def _header_rows(label, page):
    top = label.line.bbox[3]
    rows = sorted((l for l in page.lines if top <= l.bbox[1] <= top + 85
                   and not caption_match(l.text, 'table')),
                  key=lambda l: (l.bbox[1], l.bbox[0]))
    return {re.sub(r'\s+', '', normalize_text(l.text)).lower() for l in rows
            if len(l.text.strip()) >= 6}


def _continuous(previous, current, pages):
    left, right = previous[-1], current[0]
    if (right.line.page_number != left.line.page_number + 1
            or left.scope != right.scope or left.number != right.number):
        return False
    first, second = pages.get(left.line.page_number), pages.get(right.line.page_number)
    if first is None or second is None:
        return False
    # A new body chapter is a boundary even if an author reuses a number.
    between = [l for p in (first, second) for l in p.lines
               if (p.number == first.number and l.bbox[1] > left.line.bbox[3])
               or (p.number == second.number and l.bbox[1] < right.line.bbox[1])]
    if any(_body_heading(l, first if l.page_number == first.number else second) for l in between):
        return False
    a, b = _table_box(left, first), _table_box(right, second)
    if a is not None and b is not None:
        # Mirror-page margins may shift a grid slightly. A different column
        # footprint is a distinct physical object, even with a reused ID.
        tolerance = max(18, min(a[2] - a[0], b[2] - b[0]) * .08)
        return abs(a[0] - b[0]) <= tolerance and abs(a[2] - b[2]) <= tolerance
    # Native extraction sometimes lacks grids; repeated adjacent table-header
    # rows plus the explicit marker supply independent physical continuity.
    return bool(_header_rows(left, first) & _header_rows(right, second))


def usage_caption_groups(groups: list[list[Label]], index: DocumentIndex,
                         kind: str) -> list[list[Label]]:
    """Merge explicit adjacent continued tables; preserve every orphan target.

    Groups contain members from multiple pages. The caller must use only the
    canonical page's companions when constructing a finding's bounding box.
    """
    if kind != 'table':
        return groups
    pages = {page.number: page for page in index.document.pages}
    ordered = sorted(groups, key=lambda g: (g[0].line.page_number, g[0].line.bbox[1],
                                            g[0].line.bbox[0]) if g else (float('inf'), 0, 0))
    result = []
    for group in ordered:
        if (group and result and result[-1] and _continued(group)
                and _continuous(result[-1], group, pages)):
            result[-1].extend(group)
        else:
            result.append(list(group))
    return result
