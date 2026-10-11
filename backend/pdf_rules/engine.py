from .mineru_layout import remap_layout_object
from hashlib import sha256
import os
from pathlib import Path
from dataclasses import replace
import tempfile
from time import monotonic
import pymupdf

from .caption_rules import detect_caption_rules
from .index import build_index
from .layout_context import recover_document, research_document, prepare_caption_layout
from .local_rules import detect_rules
from .mineru_api import MinerUError, parse_layout, MAX_POLL_SECONDS
from .pdf_extract import extract_pdf
from .page_policy import exclude_signature_pages


def _rule_document(document, objects=()):
    filtered, _, _ = exclude_signature_pages(document, objects or ())
    return research_document(filtered)


LOCAL = {11, 15, 16, 29}
CLOUD = {13, 14}


def detect(pdf_path: str | Path, selected_rule_numbers, *, token=None, http_client=None) -> dict:
    selected = set(selected_rule_numbers)
    usage_only = bool(selected) and selected <= {15, 16}
    def ocr_document(source, layout=()):
        view = _rule_document(source, layout)
        if usage_only:
            from .usage_scope import usage_document
            return usage_document(view)
        return view
    document = extract_pdf(pdf_path)
    from .decorative_layers import remove_decorative_layers
    _,document=remove_decorative_layers([],document)
    results = {}
    objects = None
    cloud_error = None
    if usage_only:
        from .usage_layout import read_usage_layout
        objects = read_usage_layout(pdf_path, os.environ.get('MINERU_CACHE_DIR'))
        if objects is not None:
            document = recover_document(document, objects)
    initial_view = ocr_document(document, objects) if usage_only else ocr_document(document)
    needs_ocr = bool(selected & LOCAL) and any(page.unreadable for page in initial_view.pages)
    attempts=[];recovery=[]
    if selected & CLOUD or needs_ocr:
        deadline = monotonic() + MAX_POLL_SECONDS
        def budget(cap=MAX_POLL_SECONDS,reserve=0):
            remaining = deadline - monotonic() - reserve
            if remaining <= 0:
                raise MinerUError("MinerU task timed out",retryable=True)
            return min(cap,remaining)
        secret = token if token is not None else os.environ.get("MINERU_API_TOKEN")
        # Retry a temporary full-layout failure within the same reserved
        # window. Raw task state lets the second attempt resume its upload.
        for attempt in range(2):
            stage="initial_layout" if attempt==0 else "initial_layout_retry"
            try:
                initial_budget=budget(420 if needs_ocr else MAX_POLL_SECONDS,
                                      reserve=600 if needs_ocr else 0)
                if selected & CLOUD:
                    objects=parse_layout(pdf_path,secret,http_client,max_seconds=initial_budget)
                else:
                    fresh=_ocr_missing_pages(pdf_path,ocr_document(document),secret,http_client,max_seconds=initial_budget)
                    objects=_replace_ocr_text(objects or [],fresh) if usage_only and objects else fresh
                attempts.append({"stage":stage,"status":"completed"})
                document=recover_document(document,objects)
                cloud_error=None
                break
            except MinerUError as exc:
                cloud_error=str(exc)
                attempts.append({"stage":stage,"status":"failed","reason":str(exc)})
                if not exc.retryable:break
        # Text recovery remains available after layout failure. Independent
        # OCR passes continue after a temporary failure of any preceding pass.
        # Resolve scanned administrative structures before requesting extra
        # cloud OCR. This also applies when only caption rules were selected.
        missing={p.number for p in ocr_document(document,objects).pages if p.unreadable}
        if missing:
            from .signature_ocr import recover_signature_pages,has_signature_structure_candidates
            if has_signature_structure_candidates(document,missing):
                document,structural=recover_signature_pages(document,missing,
                    max_seconds=min(180,max(0,deadline-monotonic())),structure_only=True)
                recovery.extend(structural)
        unresolved=ocr_document(document,objects)
        if selected & LOCAL and any(page.unreadable for page in unresolved.pages):
            with pymupdf.open(pdf_path) as original:
                rotated_missing=any(original[page.number-1].rotation for page in unresolved.pages if page.unreadable)
            stages=[("forced_ocr",180 if rotated_missing else 240,{"force_ocr":True})]
            if rotated_missing:
                stages.append(("upright_ocr",120,{"force_ocr":True,"upright":True}))
            stages.append(("grid_ocr",120 if rotated_missing else 180,{"force_ocr":True,"tiled":"grid"}))
            for index,(name,cap,options) in enumerate(stages):
                unresolved=ocr_document(document,objects)
                if not any(page.unreadable for page in unresolved.pages):break
                # Retain the remaining independent methods and CPU window.
                reserve=180+sum(stage[1] for stage in stages[index+1:])
                try:
                    fresh=_ocr_missing_pages(pdf_path,unresolved,secret,http_client,
                                              max_seconds=budget(cap,reserve),**options)
                    objects=_replace_ocr_text(objects or [],fresh)
                    document=recover_document(document,objects)
                    attempts.append({"stage":name,"status":"completed"})
                except MinerUError as exc:
                    attempts.append({"stage":name,"status":"failed","reason":str(exc)})
    rule_document, rule_objects, excluded_pages = exclude_signature_pages(document,objects or ())
    if selected & LOCAL:
        text_document=research_document(rule_document)
        if usage_only:
            from .usage_scope import usage_document
            readable_document = usage_document(text_document)
        else:
            readable_document = text_document
        unreadable_numbers={page.number for page in readable_document.pages if page.unreadable}
        if unreadable_numbers:
            from .signature_ocr import recover_signature_pages
            recovered,late_recovery=recover_signature_pages(document,unreadable_numbers,
                max_seconds=min(180,max(0,deadline-monotonic())))
            recovery.extend(late_recovery)
            document=recovered
            rule_document, rule_objects, excluded_pages = exclude_signature_pages(document,objects or ())
            text_document=research_document(rule_document)
    evidence = prepare_caption_layout(rule_objects, rule_document) if rule_objects else None
    if selected & LOCAL:
        from .reference_identity_repair import repair_reference_identity
        index = repair_reference_identity(build_index(text_document, evidence), evidence or ())
        from .cross_page_typed_references import recover_cross_page_typed_references
        index = recover_cross_page_typed_references(index, evidence or (), evidence=None)
        results.update(detect_rules(index, selected & LOCAL))
    if selected & CLOUD:
        if cloud_error:
            for number in selected & CLOUD:
                results[str(number)] = {"status": "unsupported", "reason": cloud_error, "findings": []}
        else:
            if evidence:
                results.update(detect_caption_rules(evidence, selected & CLOUD, rule_document))
            elif objects:
                # All parsed objects were explicitly identified as nonresearch.
                results.update({str(number): {"status": "completed", "findings": []}
                                for number in selected & CLOUD})
            else:
                results.update(detect_caption_rules([], selected & CLOUD))
    _display_locations(results, pdf_path)
    output={"pages": len(document.pages), "rules": results}
    if excluded_pages:
        output["excluded_signature_pages"]=[{"page":n,"reason":reason} for n,reason in sorted(excluded_pages.items())]
    if recovery:
        output["parse_recovery"]=recovery
    if attempts:
        output["parse_attempts"]=attempts
    return output


def _ocr_missing_pages(pdf_path, document, token, http_client, *, force_ocr=False, tiled=False, upright=False, max_seconds=MAX_POLL_SECONDS):
    missing = [page.number for page in document.pages if page.unreadable]
    sources = {page.number: page for page in document.pages}
    mapping = []
    with tempfile.TemporaryDirectory(prefix="pdf-rule-ocr-") as folder:
        path = Path(folder) / "scanned-pages.pdf"
        with pymupdf.open(pdf_path) as original, pymupdf.open() as subset:
            for number in missing:
                source = original[number-1]
                if not upright:source.set_rotation(0)
                width, height = source.rect.width, source.rect.height
                tiles = ((0, height),) if not tiled else ((0, height*.45), (height*.30, height*.75), (height*.60, height))
                columns = ((0, width),) if tiled != "grid" else ((0, width*.65), (width*.35, width))
                for top, bottom in tiles:
                    for left, right in columns:
                        subset.insert_pdf(original, from_page=number-1, to_page=number-1)
                        if tiled:
                            crop = source.cropbox
                            subset[-1].set_cropbox(pymupdf.Rect(crop.x0+left, crop.y0+top, crop.x0+right, crop.y0+bottom))
                        mapping.append((number, left, top))
            path.write_bytes(subset.tobytes(garbage=4, deflate=True, no_new_id=True))
        view_scope = ("ocr:" + sha256(path.read_bytes()).hexdigest()
                      + f":{int(force_ocr)}:{int(upright)}:{tiled}")
        options={"respect_rotation":True} if upright else {}
        objects = parse_layout(path, token, http_client, force_ocr=force_ocr, max_seconds=max_seconds,**options)
    result = []
    for obj in objects:
        number, left, top = mapping[obj.page_number-1]
        page = sources[number]
        def shift(box):
            return (box[0]+left, box[1]+top, box[2]+left, box[3]+top)
        result.append(remap_layout_object(obj,shift,page_number=number,
                      page_width=page.width,page_height=page.height,source_namespace=view_scope))
    return result


def _replace_ocr_text(objects, fresh):
    pages = {obj.page_number for obj in fresh}
    return [obj for obj in objects if obj.page_number not in pages
            or obj.kind in {"figure", "table"}] + fresh


def _display_locations(results, pdf_path):
    """Convert the canonical parsing frame to the original PDF display frame."""
    with pymupdf.open(pdf_path) as original:
        for result in results.values():
            for finding in result.get("findings", []):
                location = finding.get("location", {})
                number = location.get("page_number")
                if not number or not original[number-1].rotation:
                    continue
                page = original[number-1]
                def rotate(rect):
                    box = pymupdf.Rect(*(rect[key] for key in ("x1", "y1", "x2", "y2"))) * page.rotation_matrix
                    return {**rect, **dict(zip(("x1", "y1", "x2", "y2"), box)),
                            "width": float(page.rect.width), "height": float(page.rect.height)}
                location["bounding_rect"] = rotate(location["bounding_rect"])
                location["rects"] = [rotate(rect) for rect in location.get("rects", [])]
