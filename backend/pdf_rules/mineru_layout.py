from dataclasses import dataclass, replace
from typing import Iterable
import re
from html.parser import HTMLParser

from .numbering import normalize_text, caption_match


@dataclass(frozen=True)
class LayoutObject:
    kind: str
    page_number: int
    bbox: tuple[float, float, float, float]
    text: str
    page_width: float
    page_height: float
    role: str = ""
    text_lines: tuple[tuple[str, tuple[float, float, float, float]], ...] = ()
    # Physical constituent bounds survive semantic merges. The rectangular
    # envelope may include whitespace belonging to a neighbouring panel.
    panel_boxes: tuple[tuple[float, float, float, float], ...] = ()
    # Parser lineage is evidence, not permission to merge academic objects.
    # A flat box list cannot distinguish shared panels from independent figures.
    source_id: str = ""
    parent_id: str | None = None
    parent_bbox: tuple[float, float, float, float] | None = None
    parent_kind: str = ""
    # Assigned only after original-source ownership and retained native title proof.
    caption_owner_id: str = ""


def caption_identity(obj):
    from hashlib import sha256
    import json
    return sha256(json.dumps([obj.kind,obj.page_number,obj.bbox,obj.text,obj.source_id,obj.parent_id],ensure_ascii=True,separators=(",", ":")).encode()).hexdigest()


def remap_layout_object(obj, transform, *, page_number=None, page_width=None,
                        page_height=None, source_namespace=""):
    """Map every physical observation together; scope distinct OCR views.

    Source paths identify parser observations, not academic objects. A partial
    or tiled OCR PDF is a different source view even if its local page is 1.
    """
    def scoped(value):
        return f"{source_namespace}/{value}" if source_namespace and value else value
    return replace(obj, bbox=tuple(transform(obj.bbox)),
                   page_number=obj.page_number if page_number is None else page_number,
                   page_width=obj.page_width if page_width is None else page_width,
                   page_height=obj.page_height if page_height is None else page_height,
                   text_lines=tuple((text, tuple(transform(box))) for text, box in obj.text_lines),
                   panel_boxes=tuple(tuple(transform(box)) for box in obj.panel_boxes),
                   parent_bbox=tuple(transform(obj.parent_bbox)) if obj.parent_bbox is not None else None,
                   source_id=scoped(obj.source_id), parent_id=scoped(obj.parent_id))


TARGET_KINDS = {"image": "figure", "figure": "figure", "chart": "figure",
                "table": "table"}
FIGURE_CAPTION = re.compile(
    r"^\s*(?:图|Figure|Fig\.?)\s*[A-Z]?\d+(?:[.\-]\d+)*\s*(?:[.．、:：]\s*|\s+)\S",
    re.I,
)
TABLE_CAPTION = re.compile(
    r"^\s*(?:表|Table)\s*[A-Z]?\d+(?:[.\-]\d+)*\s*(?:[.．、:：]\s*|\s+)\S",
    re.I,
)
CONTINUED_TABLE = re.compile(r"^\s*(?:续表|Table\s+[A-Z]?\d+(?:[.\-]\d+)*\s*[（(]?[Cc]ontinued)", re.I)


class _TableText(HTMLParser):
    """Retain table cell semantics without inventing per-cell geometry."""
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_endtag(self, tag):
        if tag in {"td", "th", "tr", "p", "br"}:
            self.parts.append(" ")


def _block_text(block: dict) -> str:
    parts = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            if isinstance(span.get("html"), str):
                parser = _TableText()
                parser.feed(span["html"])
                parts.append("".join(parser.parts))
            else:
                parts.append(str(span.get("content", "")))
    return "".join(parts).strip()


def _caption_kind(text: str) -> str | None:
    text = normalize_text(text)
    # A malformed/missing chapter prefix is a numbering issue, not a missing
    # title. Preserve the title for rules 13/14 without inventing a correct ID.
    if re.match(r"^\s*(?:图|Figure|Fig\.?)\s*\.\d+\s+\S", text, re.I):
        return "figure_caption"
    if re.match(r"^\s*(?:表|Table)\s*\.\d+\s+\S", text, re.I):
        return "table_caption"
    if caption_match(text, "figure"):
        return "figure_caption"
    if caption_match(text, "table") or CONTINUED_TABLE.match(text):
        return "table_caption"
    return None


def normalize_layout(
    pages: Iterable[dict],
    first_page: int,
    original_sizes: list[tuple[float, float]],
    *, source_namespace: str = "",
) -> list[LayoutObject]:
    objects = []
    seen_pages = set()
    for page in pages:
        index = page.get("page_idx")
        if type(index) is not int or index < 0 or index >= len(original_sizes) or index in seen_pages:
            raise ValueError("Invalid MinerU page index")
        seen_pages.add(index)
        raw_size = page.get("page_size")
        if not isinstance(raw_size, list) or len(raw_size) != 2 or min(raw_size) <= 0:
            raise ValueError("Invalid MinerU page dimensions")
        width, height = original_sizes[index]
        scale_x, scale_y = width / raw_size[0], height / raw_size[1]

        def convert(block, kind, text="", *, source_id="", parent=None):
            box = block.get("bbox")
            if not isinstance(box, list) or len(box) != 4:
                raise ValueError("Invalid MinerU bounding box")
            x1, y1, x2, y2 = (float(box[0]) * scale_x, float(box[1]) * scale_y,
                              float(box[2]) * scale_x, float(box[3]) * scale_y)
            if not (0 <= x1 < x2 <= width + 2 and 0 <= y1 < y2 <= height + 2):
                raise ValueError("MinerU bounding box outside source page")
            # Keep paragraph text for reference semantics, and physical OCR
            # lines separately: its outer envelope cannot prove complete OCR.
            text_lines = []
            for line in block.get("lines", []):
                line_box = line.get("bbox")
                line_text = _block_text({"lines": [line]})
                if any(span.get("html") for span in line.get("spans", [])):
                    continue  # HTML has only a table envelope, not OCR line boxes.
                if not line_text or not isinstance(line_box, list) or len(line_box) != 4:
                    continue
                try:
                    lx1, ly1, lx2, ly2 = (float(line_box[0]) * scale_x, float(line_box[1]) * scale_y,
                                          float(line_box[2]) * scale_x, float(line_box[3]) * scale_y)
                except (TypeError, ValueError):
                    continue
                if 0 <= lx1 < lx2 <= width + 2 and 0 <= ly1 < ly2 <= height + 2:
                    text_lines.append((line_text, (lx1, ly1, lx2, ly2)))
            parent_id, parent_box, parent_kind = None, None, ""
            if parent is not None:
                parent_id, parent_block = parent
                parent_kind = str(parent_block.get("type", ""))
                raw_parent_box = parent_block.get("bbox")
                if isinstance(raw_parent_box, list) and len(raw_parent_box) == 4:
                    try:
                        candidate_box = tuple(float(v) * scale for v, scale in
                                              zip(raw_parent_box, (scale_x, scale_y, scale_x, scale_y)))
                        px1, py1, px2, py2 = candidate_box
                        if 0 <= px1 < px2 <= width + 2 and 0 <= py1 < py2 <= height + 2:
                            parent_box = candidate_box
                    except (TypeError, ValueError):
                        pass  # Invalid parent geometry cannot become grouping evidence.
            objects.append(LayoutObject(kind, first_page + index, (x1, y1, x2, y2),
                                        text, width, height, str(block.get("type", "")), tuple(text_lines),
                                        source_id=source_id, parent_id=parent_id,
                                        parent_bbox=parent_box, parent_kind=parent_kind))

        for collection in ("para_blocks", "discarded_blocks"):
            for block_index, block in enumerate(page.get(collection, [])):
                source_id = f"mineru:{source_namespace + ':' if source_namespace else ''}{first_page + index}:{collection}:{block_index}"
                children = list(enumerate(block.get("blocks", [])))
                target_kind = TARGET_KINDS.get(block.get("type"))
                if target_kind:
                    bodies = [(i, child) for i, child in children
                              if str(child.get("type", "")).endswith("_body")]
                    if bodies:
                        for child_index, body in bodies:
                            convert(body, target_kind, _block_text(body),
                                    source_id=f"{source_id}:blocks:{child_index}",
                                    parent=(source_id, block))
                    else:
                        convert(block, target_kind, _block_text(block), source_id=source_id)
                for child_index, candidate in [(-1, block), *children]:
                    candidate_id = source_id if child_index < 0 else f"{source_id}:blocks:{child_index}"
                    parent = None if child_index < 0 else (source_id, block)
                    # Keep mathematical span geometry independently of the prose
                    # envelope. Native equation glyph bitmaps otherwise become
                    # unrelated figures after paragraph text is flattened.
                    for line_index, line in enumerate(candidate.get("lines", [])):
                        for span_index, span in enumerate(line.get("spans", [])):
                            if span.get("type") == "inline_equation" and span.get("content"):
                                convert(span, "equation", span["content"],
                                        source_id=f"{candidate_id}:lines:{line_index}:spans:{span_index}",
                                        parent=(candidate_id, candidate))
                    if candidate.get("type") == "table_body" and _block_text(candidate):
                        convert(candidate, "text", _block_text(candidate),
                                source_id=candidate_id, parent=parent)
                        continue
                    text = _block_text(candidate)
                    kind = _caption_kind(text)
                    if kind:
                        convert(candidate, kind, text, source_id=candidate_id, parent=parent)
                    elif text and candidate.get("type") in {"text", "paragraph", "list"}:
                        # Preserve soft-wrap semantics and original parser ownership.
                        convert(candidate, "text", text, source_id=candidate_id, parent=parent)
                    elif text:
                        # Keep original OCR lines without flattening their source identity.
                        for line_index, line in enumerate(candidate.get("lines", [])):
                            line_text = _block_text({"lines": [line]})
                            if line_text:
                                raw = {**candidate, "bbox": line.get("bbox", candidate.get("bbox")), "lines": [line]}
                                convert(raw, "text", line_text,
                                        source_id=f"{candidate_id}:lines:{line_index}",
                                        parent=(candidate_id, candidate))
    if seen_pages != set(range(len(original_sizes))):
        raise ValueError("MinerU omitted pages")
    return objects
