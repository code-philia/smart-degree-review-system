"""Extract bounded, location-aware text context for a repair request."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pymupdf


def distance(block, target):
    left, top, right, bottom, *_ = block
    x1, y1, x2, y2 = target
    dx = max(left - x2, x1 - right, 0)
    dy = max(top - y2, y1 - bottom, 0)
    return dx * dx + dy * dy


def extract(pdf_path: Path, page_number: int, target: tuple[float, float, float, float] | None) -> dict:
    with pymupdf.open(pdf_path) as document:
        if not 1 <= page_number <= len(document):
            raise ValueError('page_number is outside the PDF')
        page = document[page_number - 1]
        blocks = [block for block in page.get_text('blocks', sort=True) if block[4].strip()]
    if not blocks:
        return {'page_number': page_number, 'text': '', 'block_count': 0, 'truncated': False}
    nearest = min(range(len(blocks)), key=lambda index: distance(blocks[index], target)) if target else 0
    selected = blocks[max(0, nearest - 3):min(len(blocks), nearest + 4)]
    text = '\n'.join(block[4].strip() for block in selected).strip()
    limit = 6000
    return {
        'page_number': page_number,
        'text': text[:limit],
        'block_count': len(selected),
        'truncated': len(text) > limit,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--pdf', type=Path, required=True)
    parser.add_argument('--page', type=int, required=True)
    parser.add_argument('--x1', type=float)
    parser.add_argument('--y1', type=float)
    parser.add_argument('--x2', type=float)
    parser.add_argument('--y2', type=float)
    args = parser.parse_args()
    values = (args.x1, args.y1, args.x2, args.y2)
    target = values if all(value is not None for value in values) else None
    print(json.dumps(extract(args.pdf, args.page, target), ensure_ascii=True))


if __name__ == '__main__':
    main()
