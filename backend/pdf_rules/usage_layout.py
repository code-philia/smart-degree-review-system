"""Read original cached layout for usage-only runs without API or cache writes."""
from pathlib import Path
import pymupdf
from .mineru_cache import RawLayoutCache
from .mineru_layout import normalize_layout


def read_usage_layout(pdf_path, cache_folder, *, page_limit=180):
    """Use the exact canonical upload keys; reject incomplete layout evidence.

    Structural/size retries can have cached smaller segments rather than the
    whole initial segment. Try those same binary subdivisions read-only.
    This never reads any detector result or modifies the native extraction.
    """
    if not cache_folder or not Path(cache_folder).is_dir():
        return None
    if not 1 <= page_limit <= 200:
        raise ValueError('page_limit must be between 1 and 200')
    path = Path(pdf_path)
    cache = RawLayoutCache(cache_folder)
    with pymupdf.open(path) as document:
        total = len(document)
        if total < 1:
            return None
        rotated = {i for i, page in enumerate(document) if page.rotation}
        for index in rotated:
            document[index].set_rotation(0)

        def segment(start, stop):
            if start == 0 and stop == total and not rotated:
                payload = path.read_bytes()
            else:
                with pymupdf.open() as chunk:
                    chunk.insert_pdf(document, from_page=start, to_page=stop-1)
                    payload = chunk.tobytes(garbage=4, deflate=True, no_new_id=True)
            key = cache.key(payload)
            pages = cache.read(key, stop-start)
            if pages is not None:
                sizes = [(float(document[i].rect.width), float(document[i].rect.height))
                         for i in range(start, stop)]
                try:
                    return normalize_layout(pages, start+1, sizes, source_namespace=key)
                except (ValueError, TypeError, KeyError):
                    return None
            if stop-start <= 1:
                return None
            middle = start+(stop-start)//2
            left = segment(start, middle)
            if left is None:
                return None
            right = segment(middle, stop)
            return None if right is None else left+right

        objects = []
        for start in range(0, total, page_limit):
            parsed = segment(start, min(start+page_limit, total))
            if parsed is None:
                return None
            objects.extend(parsed)
        return objects
