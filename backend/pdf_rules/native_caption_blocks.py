"""Recover a native multi-row title from physical and parser ownership.

This proof is deliberately narrower than the ordinary caption grammar. It
does not infer titles from a verb, a cloud rectangle, or proximity alone.
"""
from collections import Counter
from dataclasses import dataclass
import re

from .model import PdfLine
from .numbering import FIGURE_CAPTION, TABLE_CAPTION, normalize_label, normalize_text


@dataclass(frozen=True)
class NativeCaptionBlock:
    rows: tuple[PdfLine, ...]
    owner_bbox: tuple[float, float, float, float]
    source_container: str
    caption_source: str


def _area(box):
    return max(0, box[2]-box[0])*max(0, box[3]-box[1])


def _intersection(a, b):
    return (max(0, min(a[2], b[2])-max(a[0], b[0]))
            * max(0, min(a[3], b[3])-max(a[1], b[1])))


def _covered(a, b, fraction=.85):
    return bool(_area(a) and _intersection(a, b)/_area(a) >= fraction)


def _compact(text):
    return re.sub(r"\s+", "", normalize_text(text))


def _caption_source(obj):
    """Follow the actual body/caption child relationship in parser output."""
    if obj.role != "image_caption" or not obj.source_id or not obj.parent_id:
        return None
    if obj.parent_kind == "image_caption":
        if not re.fullmatch(re.escape(obj.parent_id)+r":lines:\d+", obj.source_id):
            return None
        parent = re.fullmatch(r"(.+):blocks:\d+", obj.parent_id)
        if parent and obj.parent_bbox:
            return parent.group(1), obj.parent_id, obj.parent_bbox
    if obj.parent_kind == "image":
        if re.fullmatch(re.escape(obj.parent_id)+r":blocks:\d+", obj.source_id):
            return obj.parent_id, obj.source_id, obj.bbox
    return None


def _title_rows(line, page):
    rows = tuple(sorted((r for r in page.lines
                         if r.block_id == line.block_id and r.text.strip()),
                        key=lambda r: (r.bbox[1], r.bbox[0])))
    if len(rows) < 2 or rows[0] != line:
        return None
    height = max(1, line.bbox[3]-line.bbox[1])
    for i, row in enumerate(rows):
        if (row.source != "native" or not row.bold or not row.font_size
                or abs(row.direction[0]) < .9
                or abs(row.font_size-line.font_size) > line.font_size*.08):
            return None
        if i:
            previous = rows[i-1]
            gap = row.bbox[1]-previous.bbox[3]
            if not -1 <= gap <= max(6, height*.65):
                return None
            # A second independently declared object ends the title block.
            if any(p.match(normalize_text(row.text))
                   for p in (FIGURE_CAPTION, TABLE_CAPTION)):
                return None
            aligned = abs(row.bbox[0]-line.bbox[0]) <= height*1.5
            centred = abs((row.bbox[0]+row.bbox[2]
                           -line.bbox[0]-line.bbox[2])/2) <= height*1.5
            if not (aligned or centred):
                return None
    return rows


def native_caption_block(line, page, kind, objects=()):
    """Return only the native rows proved to belong to one image title.

    The helper reads passed-in layout only. It never invokes preparation,
    extraction, OCR, or a detector, and does not change an object or PDF line.
    """
    if (kind != "figure" or line.source != "native" or not line.bold
            or not line.font_size or line.block_id is None
            or abs(line.direction[0]) < .9 or page.display_rotation):
        return None
    match = FIGURE_CAPTION.match(normalize_text(line.text))
    if not match or len(re.findall(r"[A-Za-z\u4e00-\u9fff]",
                                   normalize_text(line.text)[match.end("number"):])) < 3:
        return None
    rows = _title_rows(line, page)
    if not rows:
        return None
    height = max(1, line.bbox[3]-line.bbox[1])
    block = (min(r.bbox[0] for r in rows), rows[0].bbox[1],
             max(r.bbox[2] for r in rows), rows[-1].bbox[3])
    prose = [r for r in page.lines if r.source == "native" and not r.bold
             and r.block_id != line.block_id and r.font_size
             and abs(r.direction[0]) > .9
             and r.bbox[2]-r.bbox[0] > page.width*.6
             and page.height*.09 < r.bbox[1] < page.height*.92
             and len(re.findall(r"[A-Za-z\u4e00-\u9fff]", r.text)) >= 12]
    sizes = Counter(round(r.font_size, 1) for r in prose)
    if not sizes or line.font_size >= sizes.most_common(1)[0][0]*.95:
        return None
    page_objects = [o for o in objects or () if o.page_number == page.number]
    families = {}
    for obj in page_objects:
        source = _caption_source(obj)
        if source:
            container, caption, scope = source
            families.setdefault((container, caption), []).append((obj, scope))
    proofs = []
    for (container, caption), family in families.items():
        # A broad parent box must not hide ordinary native prose.
        scopes = {tuple(scope) for _, scope in family}
        if len(scopes) != 1:
            continue
        scope = next(iter(scopes))
        if (not all(_covered(r.bbox, scope) for r in rows)
                or any(r not in rows and r.source == "native" and r.text.strip()
                       and _intersection(r.bbox, scope) > _area(r.bbox)*.15
                       for r in page.lines)):
            continue
        observed = _compact(" ".join(o.text for o, _ in family))
        declared = FIGURE_CAPTION.match(normalize_text(
            min(family, key=lambda item: (item[0].bbox[1], item[0].bbox[0]))[0].text))
        if (not declared or normalize_label(declared.group("number"))
                != normalize_label(match.group("number"))
                or any(_compact(r.text) not in observed for r in rows)):
            continue
        owners = [o for o in page_objects if o.kind == "figure"
                  and o.role == "image_body" and o.parent_kind == "image"
                  and o.parent_id == container
                  and re.fullmatch(re.escape(container)+r":blocks:\d+", o.source_id or "")]
        if len(owners) != 1:
            continue
        owner = owners[0]
        box = owner.bbox
        overlap = max(0, min(box[2], block[2])-max(box[0], block[0]))
        if (box[2]-box[0] < page.width*.15 or box[3]-box[1] < 20
                or not 0 <= block[1]-box[3] <= 65
                or overlap < min(box[2]-box[0], block[2]-block[0])*.65
                or abs((line.bbox[0]+line.bbox[2]-box[0]-box[2])/2)
                   > max(height*1.8, (box[2]-box[0])*.1)):
            continue
        # A parser body is corroboration, not the physical object itself.
        # Reciprocal native coverage rejects page backgrounds and stray panels.
        native_visuals = (*page.images, *getattr(page, "graphics", ()))
        if not any(_covered(box, native, .8) and _covered(native, box, .8)
                   for native in native_visuals):
            continue
        # A different styled native title within this physical owner reveals
        # an unresolved composite; a broad parser body is not exclusive proof.
        conflicting = False
        for peer in page.lines:
            declared = FIGURE_CAPTION.match(normalize_text(peer.text))
            if (peer in rows or peer.source != "native" or not peer.bold
                    or not peer.font_size or not declared
                    or peer.font_size > line.font_size*1.15
                    or normalize_label(declared.group("number"))
                       == normalize_label(match.group("number"))):
                continue
            within_owner = _covered(peer.bbox, box)
            below_owner = (box[3] <= peer.bbox[1] <= block[3]
                           and peer.bbox[2] > box[0] and peer.bbox[0] < box[2])
            if within_owner or below_owner:
                conflicting = True
                break
        if conflicting:
            continue
        # A body paragraph between the image and candidate title severs ownership.
        if any(box[3]+1 < r.bbox[1] < block[1] and r.bbox[2] > box[0]
               and r.bbox[0] < box[2] for r in prose):
            continue
        # The native block must end before the next paragraph begins.
        if any(0 <= r.bbox[1]-block[3] < height*.85
               and r.bbox[2] > block[0] and r.bbox[0] < block[2] for r in prose):
            continue
        # A second independent visual near this title makes its owner ambiguous.
        visuals = [o.bbox for o in page_objects if o.kind == "figure"]
        visuals.extend((*page.images, *getattr(page, "graphics", ())))
        competing = False
        for visual in visuals:
            if (visual[2]-visual[0] < page.width*.15
                    or visual[3]-visual[1] < 20):
                continue
            if _intersection(visual, box) >= min(_area(visual), _area(box))*.85:
                continue  # Native duplicate or a panel within the same physical owner.
            horizontal = max(0, min(visual[2], block[2])-max(visual[0], block[0]))
            gap = max(block[1]-visual[3], visual[1]-block[3], 0)
            if horizontal >= min(visual[2]-visual[0], block[2]-block[0])*.5 and gap <= 65:
                competing = True
                break
        if not competing:
            proofs.append(NativeCaptionBlock(rows, box, container, caption))
    return proofs[0] if len(proofs) == 1 else None
