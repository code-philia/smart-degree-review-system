"""Usage-only immutable text normalization; shared numbering stays unchanged."""
from functools import lru_cache
from .numbering import normalize_text as _native_normalize_text


@lru_cache(maxsize=8192)
def _cached_normalize(value):
    return _native_normalize_text(value)


def normalize_text(text):
    if type(text) is str and len(text)<=4096:
        return _cached_normalize(text)
    return _native_normalize_text(text)
