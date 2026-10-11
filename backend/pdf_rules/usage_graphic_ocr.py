"""Read original graphic pixels into source-bound facts for rules 15 and 16.

The caller supplies physical regions after its native evidence checks. This
module does not decide usage, mutate the index, or write the source document.
OCR failures return no evidence; optional caches contain only validated facts.
"""
from functools import lru_cache
from hashlib import sha256
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import tempfile

from .local_ocr import _read_tile


_FORMAT = "usage-graphic-pixels-v1"
_SOURCE = "usage_graphic_ocr_cpu"
_SCALES = (2.5, 3.0)
_MIN_RECOGNITION = .90
_MIN_DETECTION = .80
_FIELDS = {"text", "bbox", "page_number", "source", "confidence",
           "detection_confidence", "pdf_sha", "region_identity", "render_scale"}


def _json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


@lru_cache(maxsize=1)
def _ocr_signature():
    import rapidocr
    from . import local_ocr
    models = Path(rapidocr.__file__).parent / "models"
    files = ("PP-OCRv6_det_small.onnx", "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
             "PP-OCRv6_rec_small.onnx")
    context = {
        "models": {name: sha256((models / name).read_bytes()).hexdigest() for name in files},
        "reader": sha256(Path(local_ocr.__file__).read_bytes()).hexdigest(),
        "pixel_adapter": sha256(Path(__file__).read_bytes()).hexdigest(),
        "versions": {name: version(name) for name in
                     ("rapidocr", "onnxruntime", "PyMuPDF", "opencv-python", "numpy")},
        "scales": _SCALES, "fallback": "only-no-confident-fields",
        "colorspace": "gray", "alpha": False,
        "rotation": 0, "min_recognition": _MIN_RECOGNITION,
        "min_detection": _MIN_DETECTION,
    }
    return sha256(_json(context)).hexdigest()


def _box(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        box = tuple(float(x) for x in value)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(x) for x in box) or box[2] <= box[0] or box[3] <= box[1]:
        return None
    return box


def _text(value):
    return (isinstance(value, str) and bool(value.strip()) and "\ufffd" not in value
            and not any(ord(c) < 32 and not c.isspace() for c in value))


def _confidence(value, minimum):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and minimum <= value <= 1)


def _valid_facts(facts, context):
    if not isinstance(facts, list):
        return False
    a = context["bbox"]
    for fact in facts:
        if not isinstance(fact, dict) or set(fact) != _FIELDS:
            return False
        b = _box(fact["bbox"])
        if (b is None or not _text(fact["text"])
                or not _confidence(fact["confidence"], _MIN_RECOGNITION)
                or not _confidence(fact["detection_confidence"], _MIN_DETECTION)
                or fact["source"] != _SOURCE
                or fact["pdf_sha"] != context["pdf_sha"]
                or fact["page_number"] != context["page_number"]
                or fact["region_identity"] != context["region_identity"]
                or fact["render_scale"] not in _SCALES
                or not (a[0] - .01 <= b[0] < b[2] <= a[2] + .01
                        and a[1] - .01 <= b[1] < b[3] <= a[3] + .01)):
            return False
    return True


def _cached(path, context):
    try:
        if path.stat().st_size > 8 * 1024 * 1024:
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(record, dict)
                or set(record) != {"format", "context", "facts", "facts_sha"}
                or record["format"] != _FORMAT or record["context"] != context
                or not _valid_facts(record["facts"], context)
                or sha256(_json(record["facts"])).hexdigest() != record["facts_sha"]):
            return None
        return record["facts"]
    except (OSError, ValueError, TypeError, KeyError):
        return None


def _save(path, context, facts):
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"format": _FORMAT, "context": context, "facts": facts,
                  "facts_sha": sha256(_json(facts)).hexdigest()}
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent,
                                         prefix="usage-pixels-", suffix=".tmp", delete=False) as f:
            temporary = Path(f.name)
            f.write(_json(record))
        os.replace(temporary, path)
        temporary = None
    except (OSError, ValueError, TypeError):
        pass
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def _observe_at_scale(page, context, scale):
    import numpy as np
    import pymupdf
    page.set_rotation(0)  # In-memory document only; coordinates match native extraction.
    clip = pymupdf.Rect(context["bbox"]) & page.rect
    if clip.is_empty or clip.is_infinite:
        return []
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale),
                          colorspace=pymupdf.csGRAY, alpha=False, clip=clip)
    gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    facts = []
    for hit in _read_tile(gray):
        box = _box(hit.bbox)
        if (box is None or not _text(hit.text)
                or not _confidence(hit.score, _MIN_RECOGNITION)
                or not _confidence(hit.detection_score, _MIN_DETECTION)):
            continue
        # Pixmap origins include raster rounding. Clamp to the actual clip so
        # rounding cannot move a field into the adjacent caption or graphic.
        mapped = [max(clip.x0, (pix.x + box[0]) / scale),
                  max(clip.y0, (pix.y + box[1]) / scale),
                  min(clip.x1, (pix.x + box[2]) / scale),
                  min(clip.y1, (pix.y + box[3]) / scale)]
        if _box(mapped) is None:
            continue
        facts.append({"text": hit.text.strip(), "bbox": mapped,
                      "page_number": context["page_number"], "source": _SOURCE,
                      "confidence": float(hit.score),
                      "detection_confidence": float(hit.detection_score),
                      "pdf_sha": context["pdf_sha"],
                      "region_identity": context["region_identity"],
                      "render_scale": scale})
    return facts


def _observe(page, context):
    for scale in _SCALES:
        facts = _observe_at_scale(page, context, scale)
        if facts:
            return facts
    return []


def graphic_ocr_fields(index, regions):
    """Return confident pixel fields for each supplied physical group.

    Each cache key binds source bytes, physical region, renderer, reader, and
    bundled model bytes. Native evidence and the caller's index stay untouched.
    Unavailable dependencies or any failed region cannot provide usage credit.
    """
    result = {group: [] for group in regions}
    try:
        import pymupdf
        pdf_bytes = Path(index.document.path).read_bytes()
        pdf_sha = sha256(pdf_bytes).hexdigest()
        signature = _ocr_signature()
        cache_dir = os.environ.get("MINERU_USAGE_OCR_CACHE_DIR")
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf:
            for group, areas in regions.items():
                for region in areas:
                    try:
                        number = region.get("page_number")
                        box = _box(region.get("bbox"))
                        if (not isinstance(number, int) or isinstance(number, bool)
                                or not 1 <= number <= len(pdf) or box is None):
                            continue
                        page = pdf[number - 1]
                        page.set_rotation(0)
                        if (pymupdf.Rect(box) & page.rect).is_empty:
                            continue
                        physical = {"pdf_sha": pdf_sha, "page_number": number, "bbox": list(box)}
                        identity = sha256(_json(physical)).hexdigest()
                        context = {**physical, "region_identity": identity, "ocr_signature": signature}
                        cache = (Path(cache_dir) / ("usage-graphic-" + sha256(_json(context)).hexdigest() + ".json")
                                 if cache_dir else None)
                        facts = _cached(cache, context) if cache else None
                        if facts is None:
                            facts = _observe(page, context)
                            if not _valid_facts(facts, context):
                                continue
                            if cache:
                                _save(cache, context, facts)
                        # Returned lists and boxes are independent of cached facts.
                        result[group].extend({**fact, "bbox": list(fact["bbox"])} for fact in facts)
                    except Exception:
                        # No negative/empty cache is written for failed inference.
                        continue
    except Exception:
        return result
    return result
