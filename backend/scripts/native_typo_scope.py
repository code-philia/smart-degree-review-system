"""Restrict typo checks to independently visible native PDF body text.

This module reads PDF drawing provenance only. It never renders/recognizes text,
uses OCR, changes the compiler IR, or treats an existing PDF text layer as proof
of native text. A raster union covering 80% of a page is conservatively a scan:
the entire page is skipped even when it has a visible or invisible text overlay.
On a mixed page, only visible native source lines outside every raster region
are retained. Ordinary body text beside a raster figure remains eligible; text
inside the figure is outside the supported scope. Unsupported/ambiguous source
lines are excluded rather than joined across a removed span.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import math
from pathlib import Path
import re
import statistics
from typing import Any

import pymupdf
from pdf_rules.visible_images import visible_images


_ADMIN_TITLE = re.compile(
    r"^(?:.{0,30}大学)?(?:博士|硕士)?(?:学位)?论文(?:答辩(?:委员会)?决议书?|原创性声明|版权使用授权书|使用授权书|授权声明)$"
    r"|^(?:学位论文)?(?:原创性声明|版权使用授权书|答辩委员会决议书|答辩决议书)$"
    r"|^(?:(?:doctoral|master'?s?|degree)?thesis|dissertation)?(?:defen[cs]eresolution|defen[cs]ecommitteeresolution|declarationoforiginality|copyrightauthorization)$",
    re.I,
)
_CHAPTER_TITLE = re.compile(r"^(?:第[一二三四五六七八九十百\d]+章\s*\S|Chapter\s+\d+\b|\d+(?:\.\d+)*\s+\S)", re.I)


def _rect(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        result = tuple(float(v) for v in value)
    except (TypeError, ValueError):
        return None
    return result if all(math.isfinite(v) for v in result) and result[2] > result[0] and result[3] > result[1] else None


def _intersection(left, right):
    x0, y0 = max(left[0], right[0]), max(left[1], right[1])
    x1, y1 = min(left[2], right[2]), min(left[3], right[3])
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def _union_area(rectangles):
    """Area of the actual rectangle union; repeated overlays cannot inflate it."""
    edges = sorted({r[i] for r in rectangles for i in (0, 2)})
    area = 0.0
    for left, right in zip(edges, edges[1:]):
        spans = sorted((r[1], r[3]) for r in rectangles if r[0] < right and r[2] > left)
        covered, end = 0.0, -math.inf
        for lower, upper in spans:
            covered += max(0.0, upper - max(lower, end))
            end = max(end, upper)
        area += (right - left) * covered
    return area


def _body_nodes(ir):
    nodes = {node.get("id"): node for node in ir.get("nodes", []) if isinstance(node, dict)}
    bodies = [node for node in nodes.values() if node.get("kind") == "Body"]
    eligible, seen = set(), set()

    def walk(node_id):
        if node_id in seen:
            return
        seen.add(node_id)
        node = nodes.get(node_id, {})
        if node.get("kind") in {"Paragraph", "Heading"}:
            eligible.add(node_id)
        for child in node.get("children", []) or []:
            walk(child)

    for body in bodies:
        walk(body.get("id"))
    return nodes, eligible


def _line_status(page, text, box):
    """A source line must match PDF glyphs, all visible and raster-independent."""
    if not box:
        return "source_geometry_unavailable"
    glyphs = [glyph for glyph in page["glyphs"]
              if box[0] - .5 <= glyph["cx"] <= box[2] + .5
              and box[1] - .5 <= glyph["cy"] <= box[3] + .5]
    if not glyphs:
        return "native_glyphs_unavailable"
    if any(not glyph["visible"] for glyph in glyphs):
        return "nonvisible_text"
    if any(any(_intersection(glyph["bbox"], image) > .1 * glyph["area"]
               for image in page["images"]) for glyph in glyphs):
        return "raster_backed_text"
    observed = Counter(glyph["text"] for glyph in glyphs if not glyph["text"].isspace())
    expected = Counter(char for char in text if not char.isspace())
    # Font-metric line boxes can also enclose an adjacent formula's superscript.
    # Every requested character needs native evidence; extra visible glyphs do
    # not invalidate the independently sourced line.
    if not expected or expected - observed:
        return "native_text_mismatch"
    # Glyph counts prove available paint, not source reading order. Corroborate
    # the complete line against the same rawdict character order/box convention
    # used by the compiler. This permits native columns and separately painted
    # glyphs without allowing stale/reordered text to borrow the same glyphs.
    compact = "".join(char for char in text if not char.isspace())
    if not any(compact == "".join(char for char in line["text"] if not char.isspace())
               and max(abs(a - b) for a, b in zip(box, line["bbox"])) <= .05
               for line in page["native_lines"]):
        return "native_text_mismatch"
    return None


def _observe_page(page):
    # Compiler provenance is explicitly unrotated; inspect in that same frame.
    page.set_rotation(0)
    width, height = float(page.rect.width), float(page.rect.height)
    images = []
    for image in page.get_image_info():
        image_box = pymupdf.Rect(image["bbox"]) & page.rect
        if not image_box.is_empty:
            images.append(tuple(image_box))
    # Image-info placements do not include active PDF/Form clipping. Reuse the
    # existing native SVG display-list reader; its conservative fallback keeps
    # unknown image regions. This is geometric parsing, never text recognition.
    images = list(visible_images(page, tuple(images)))
    glyphs, dedup = [], set()
    for span in page.get_texttrace():
        visible = span.get("type") in (0, 1) and float(span.get("opacity", 0)) > 0
        for char in span.get("chars", []):
            box = _rect(char[3])
            if box is None or not 0 <= char[0] <= 0x10FFFF:
                continue
            # Fill+stroke fonts may expose the same visible glyph twice.
            key = (char[0], tuple(round(v, 3) for v in box), visible)
            if key in dedup:
                continue
            dedup.add(key)
            glyphs.append({"text": chr(char[0]), "bbox": box,
                           "cx": (box[0] + box[2]) / 2, "cy": (box[1] + box[3]) / 2,
                           "area": (box[2] - box[0]) * (box[3] - box[1]), "visible": visible})
    result = {"images": images, "glyphs": glyphs, "width": width, "height": height,
              "raster_coverage": _union_area(images) / (width * height), "administrative_title": False}
    raw = page.get_text("rawdict", sort=True, flags=pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
    lines = []
    for block in raw["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            chars = [char for span in line["spans"] for char in span.get("chars", [])]
            if not chars:
                continue
            box = [max(0, min(width, min(char["bbox"][0] for char in chars))),
                   max(0, min(height, min(char["bbox"][1] for char in chars))),
                   max(0, min(width, max(char["bbox"][2] for char in chars))),
                   max(0, min(height, max(char["bbox"][3] for char in chars)))]
            lines.append({**line, "text": "".join(char["c"] for char in chars), "bbox": box})
    result["native_lines"] = lines
    sizes = [float(span["size"]) for line in lines for span in line["spans"]]
    normal = statistics.median(sizes) if sizes else 12
    for line in sorted(lines, key=lambda row: (row["bbox"][1], row["bbox"][0]))[:4]:
        value = line["text"]
        compact = re.sub(r"\s+", "", value)
        prominent = any(float(span["size"]) >= normal * 1.1 or span.get("flags", 0) & 16 for span in line["spans"])
        if (_ADMIN_TITLE.fullmatch(compact) and line["bbox"][1] < height * .35 and prominent
                and _line_status(result, value, _rect(line["bbox"])) is None):
            result["administrative_title"] = True
            break
    return result


def filter_native_typo_ir(pdf: Path | str | None, ir: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a typo-only IR clone and JSON-safe, one-based page coverage audit.

    Call before creating typo chunks. Use ``coverage == 'none'`` as no supported
    input, never as a completed whole-document check. This IR is a private view
    for the typo rule; other rules must keep using the original compiler IR.
    Missing files/provenance fail closed. No filename/content allowlists exist.
    """
    cloned = deepcopy(ir)
    nodes, body_ids = _body_nodes(ir)
    try:
        if not pdf:
            raise ValueError('native PDF source is unavailable')
        with pymupdf.open(pdf) as document:
            pages = [_observe_page(page) for page in document]
    except (OSError, RuntimeError, ValueError):
        pages = []
        source_status = "unavailable"
    else:
        source_status = "observed"
    candidate_pages = [source["page_index"] for node_id in body_ids
                       for source in nodes[node_id].get("provenance", [])
                       if isinstance(source, dict) and type(source.get("page_index")) is int]
    first_body_page = min(candidate_pages) if candidate_pages else len(pages)
    chapter_pages = {source["page_index"] for node_id in body_ids
                     if nodes[node_id].get("kind") == "Heading" and _CHAPTER_TITLE.match(str(nodes[node_id].get("text") or ""))
                     for source in nodes[node_id].get("provenance", [])
                     if isinstance(source, dict) and type(source.get("page_index")) is int}
    administrative, active_admin = set(), False
    for index, page in enumerate(pages):
        if index in chapter_pages:
            active_admin = False
        if page["administrative_title"] and index >= first_body_page:
            active_admin = True
        if active_admin:
            administrative.add(index)
    counts = [{"eligible": 0, "excluded": 0, "reasons": Counter()} for _ in pages]
    reasons = Counter()
    replacement_ids, additions = {}, []
    existing_ids = set(nodes)
    for node in cloned.get("nodes", []):
        if not isinstance(node, dict) or not isinstance(node.get("text"), str):
            continue
        original_text = node["text"]
        # Empty everything outside Body too: _body_chunks has a legacy fallback
        # that otherwise reintroduces front/back matter when no body survives.
        if node.get("id") not in body_ids:
            node["text"], node["provenance"] = "", []
            continue
        groups, current = [], []
        sources = node.get("provenance") or []
        if not sources:
            reasons["source_provenance_unavailable"] += 1
        previous_end = -1
        for source in sources:
            reason, page_index, piece = None, None, ""
            if not isinstance(source, dict):
                reason = "source_provenance_unavailable"
            else:
                page_index = source.get("page_index")
                start, end = source.get("node_text_start"), source.get("node_text_end")
                if source.get("kind") != "source" or source.get("source_id") != "pdf":
                    reason = "non_pdf_source"
                elif type(page_index) is not int or not 0 <= page_index < len(pages):
                    reason = "pdf_page_unavailable"
                elif type(start) is not int or type(end) is not int or not 0 <= start < end <= len(original_text) or start < previous_end:
                    reason = "source_offsets_unavailable"
                else:
                    previous_end = end
                    piece = original_text[start:end]
                    if pages[page_index]["raster_coverage"] >= .8:
                        reason = "page_raster_scan"
                    elif page_index in administrative:
                        reason = "administrative_back_matter"
                    else:
                        reason = _line_status(pages[page_index], piece, _rect(source.get("bbox")))
            if reason:
                reasons[reason] += 1
                if type(page_index) is int and 0 <= page_index < len(pages):
                    counts[page_index]["excluded"] += 1
                    counts[page_index]["reasons"][reason] += 1
                if current:
                    groups.append(current)
                    current = []
            else:
                counts[page_index]["eligible"] += 1
                current.append((piece, source))
        if current:
            groups.append(current)
        replacement_ids[node.get("id")] = []
        if not groups:
            node["text"], node["provenance"] = "", []
        for index, group in enumerate(groups):
            target = node if index == 0 else deepcopy(node)
            if index:
                candidate = f"{node['id']}__native_typo_{index}"
                while candidate in existing_ids:
                    candidate += "_"
                existing_ids.add(candidate)
                target["id"] = candidate
                target["children"] = []
                additions.append(target)
            target["text"], target["provenance"] = "", []
            for piece, source in group:
                if target["text"]:
                    target["text"] += "\n"
                copied = deepcopy(source)
                copied["node_text_start"] = len(target["text"])
                target["text"] += piece
                copied["node_text_end"] = len(target["text"])
                target["provenance"].append(copied)
            replacement_ids[node.get("id")].append(target["id"])
    cloned.setdefault("nodes", []).extend(additions)
    for node in cloned["nodes"]:
        if "children" in node:
            node["children"] = [new_id for child in node["children"] for new_id in replacement_ids.get(child, [child])]
    decisions = []
    for index, (page, count) in enumerate(zip(pages, counts)):
        page_reasons = set(count["reasons"])
        if page["raster_coverage"] >= .8:
            page_reasons.add("page_raster_scan")
        if index in administrative:
            page_reasons.add("administrative_back_matter")
        status = "partial" if count["eligible"] and count["excluded"] else "eligible" if count["eligible"] else "excluded" if page_reasons else "out_of_scope"
        decisions.append({"page_index": index, "page_number": index + 1, "status": status,
                          "reasons": sorted(page_reasons), "raster_coverage": round(page["raster_coverage"], 6),
                          "eligible_source_count": count["eligible"], "excluded_source_count": count["excluded"]})
    eligible_count = sum(count["eligible"] for count in counts)
    scanned = [i + 1 for i, page in enumerate(pages) if page["raster_coverage"] >= .8]
    audit = {"policy": "native_visible_body_without_raster/1", "source_status": source_status,
             "coverage": "none" if not eligible_count else "partial" if reasons or scanned or administrative else "native_body",
             "eligible_pages": [i + 1 for i, count in enumerate(counts) if count["eligible"]],
             "excluded_pages": [row["page_number"] for row in decisions if row["status"] == "excluded"],
             "scanned_pages": scanned, "administrative_pages": sorted(i + 1 for i in administrative),
             "eligible_source_count": eligible_count, "excluded_source_count": sum(reasons.values()),
             "skip_reasons": dict(sorted(reasons.items())), "page_decisions": decisions}
    return cloned, audit
