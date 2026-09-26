from dataclasses import dataclass
from typing import Iterable
import re


@dataclass(frozen=True)
class LayoutObject:
    kind: str
    page_number: int
    bbox: tuple[float, float, float, float]
    text: str
    page_width: float
    page_height: float


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


def _block_text(block: dict) -> str:
    parts = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            parts.append(str(span.get("content", "")))
    return "".join(parts).strip()


def _caption_kind(text: str) -> str | None:
    if FIGURE_CAPTION.match(text):
        return "figure_caption"
    if TABLE_CAPTION.match(text) or CONTINUED_TABLE.match(text):
        return "table_caption"
    return None


def normalize_layout(
    pages: Iterable[dict],
    first_page: int,
    original_sizes: list[tuple[float, float]],
) -> list[LayoutObject]:
    objects = []
    for page in pages:
        index = page.get("page_idx")
        if not isinstance(index, int) or index < 0 or index >= len(original_sizes):
            raise ValueError("Invalid MinerU page index")
        raw_size = page.get("page_size")
        if not isinstance(raw_size, list) or len(raw_size) != 2 or min(raw_size) <= 0:
            raise ValueError("Invalid MinerU page dimensions")
        width, height = original_sizes[index]
        scale_x, scale_y = width / raw_size[0], height / raw_size[1]

        def convert(block, kind, text=""):
            box = block.get("bbox")
            if not isinstance(box, list) or len(box) != 4:
                raise ValueError("Invalid MinerU bounding box")
            x1, y1, x2, y2 = (float(box[0]) * scale_x, float(box[1]) * scale_y,
                              float(box[2]) * scale_x, float(box[3]) * scale_y)
            if not (0 <= x1 < x2 <= width + 2 and 0 <= y1 < y2 <= height + 2):
                raise ValueError("MinerU bounding box outside source page")
            objects.append(LayoutObject(kind, first_page + index, (x1, y1, x2, y2),
                                        text, width, height))

        for block in page.get("para_blocks", []):
            target_kind = TARGET_KINDS.get(block.get("type"))
            if target_kind:
                convert(block, target_kind)
            for candidate in (block, *block.get("blocks", [])):
                text = _block_text(candidate)
                kind = _caption_kind(text)
                if kind:
                    convert(candidate, kind, text)
    return objects

