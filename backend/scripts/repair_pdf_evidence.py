"""Extract bounded, location-aware text context for a repair request."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pymupdf


# Start with location-adjacent blocks on the target page. Only when one reading
# direction is sparse do we pull the edge of its immediately adjacent page.
LOCAL_SIDE_BLOCKS = 3
MIN_SIDE_CHARS = 600
MAX_SIDE_CHARS = 1_200
MAX_TARGET_CHARS = 1_200
MAX_ADJACENT_PAGE_CHARS = 1_200
MAX_CONTEXT_CHARS = 4_000


def distance(block, target):
    left, top, right, bottom, *_ = block
    x1, y1, x2, y2 = target
    dx = max(left - x2, x1 - right, 0)
    dy = max(top - y2, y1 - bottom, 0)
    return dx * dx + dy * dy


def text_of(blocks) -> str:
    return '\n'.join(block[4].strip() for block in blocks if block[4].strip()).strip()


def clip(text: str, limit: int, *, tail: bool = False) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return (text[-limit:] if tail else text[:limit]).strip(), True


def page_blocks(document, page_index: int):
    return [block for block in document[page_index].get_text('blocks', sort=True) if block[4].strip()]


def before_context(blocks, nearest: int) -> tuple[str, bool, int, bool]:
    start = max(0, nearest - LOCAL_SIDE_BLOCKS)
    selected = blocks[start:nearest]
    while len(text_of(selected)) < MIN_SIDE_CHARS and start > 0:
        start -= 1
        selected.insert(0, blocks[start])
    raw = text_of(selected)
    text, truncated = clip(raw, MAX_SIDE_CHARS, tail=True)
    return text, len(raw) < MIN_SIDE_CHARS, len(selected), truncated


def after_context(blocks, nearest: int) -> tuple[str, bool, int, bool]:
    end = min(len(blocks), nearest + 1 + LOCAL_SIDE_BLOCKS)
    selected = blocks[nearest + 1:end]
    while len(text_of(selected)) < MIN_SIDE_CHARS and end < len(blocks):
        selected.append(blocks[end])
        end += 1
    raw = text_of(selected)
    text, truncated = clip(raw, MAX_SIDE_CHARS)
    return text, len(raw) < MIN_SIDE_CHARS, len(selected), truncated


def extract(pdf_path: Path, page_number: int, target: tuple[float, float, float, float] | None) -> dict:
    with pymupdf.open(pdf_path) as document:
        if not 1 <= page_number <= len(document):
            raise ValueError('page_number is outside the PDF')
        target_index = page_number - 1
        blocks = page_blocks(document, target_index)
        if not blocks:
            return {'page_number': page_number, 'text': '', 'block_count': 0, 'truncated': False, 'segments': []}

        nearest = min(range(len(blocks)), key=lambda index: distance(blocks[index], target)) if target else 0
        before, before_short, before_count, before_truncated = before_context(blocks, nearest)
        after, after_short, after_count, after_truncated = after_context(blocks, nearest)
        target_text, target_truncated = clip(blocks[nearest][4].strip(), MAX_TARGET_CHARS)
        segments = []
        truncated = before_truncated or after_truncated or target_truncated

        if before_short and target_index > 0:
            previous_text, previous_truncated = clip(
                text_of(page_blocks(document, target_index - 1)),
                min(MAX_ADJACENT_PAGE_CHARS, max(0, MIN_SIDE_CHARS - len(before))),
                tail=True,
            )
            if previous_text:
                segments.append({'page_number': page_number - 1, 'relation': 'before', 'text': previous_text,
                                 'block_count': None, 'truncated': previous_truncated})
                truncated = truncated or previous_truncated

        target_context = '\n'.join(part for part in (before, target_text, after) if part).strip()
        if target_context:
            segments.append({'page_number': page_number, 'relation': 'target', 'text': target_context,
                             'block_count': before_count + 1 + after_count,
                             'truncated': before_truncated or after_truncated or target_truncated})

        if after_short and target_index + 1 < len(document):
            next_text, next_truncated = clip(
                text_of(page_blocks(document, target_index + 1)),
                min(MAX_ADJACENT_PAGE_CHARS, max(0, MIN_SIDE_CHARS - len(after))),
            )
            if next_text:
                segments.append({'page_number': page_number + 1, 'relation': 'after', 'text': next_text,
                                 'block_count': None, 'truncated': next_truncated})
                truncated = truncated or next_truncated

    total = 0
    bounded_segments = []
    for segment in segments:
        remaining = MAX_CONTEXT_CHARS - total
        if remaining <= 0:
            truncated = True
            break
        text, segment_truncated = clip(segment['text'], remaining)
        if text:
            bounded_segments.append({**segment, 'text': text, 'truncated': segment['truncated'] or segment_truncated})
            total += len(text)
            truncated = truncated or segment_truncated
    return {
        'page_number': page_number,
        'text': '\n'.join(segment['text'] for segment in bounded_segments).strip(),
        'block_count': sum(segment['block_count'] or 0 for segment in bounded_segments),
        'truncated': truncated,
        'segments': bounded_segments,
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
