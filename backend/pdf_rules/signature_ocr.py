"""Recover text outside an identified committee-signature table.

The administrative table is already supplied by MinerU. Its surrounding scan
is independently read with CPU OCR; references there remain ordinary rule input.
No paper identifiers, evaluation labels or mutation coordinates are used.
"""
from dataclasses import replace
from time import monotonic
import pymupdf
from .layout_context import decision_form, containment, union, ADMIN_TITLE, CHAPTER
from .model import PdfDocument, PdfLine
from .numbering import normalize_text, FIGURE_REFERENCE, TABLE_REFERENCE, APPENDIX_REFERENCE
from .local_ocr import read_remainder, has_unread_text, signature_remainder_view

FIELDS=("答辩委员会","工作职务","姓名","职称","工作单位","签名","主席","秘书")


def _form_context(page):
    if decision_form(page):
        return True
    # Native text has no MinerU table role. Require the actual form title,
    # full candidate fields and a formal verdict before using it as context.
    text="".join(normalize_text(line.text).replace(" ","") for line in page.lines)
    return (any(ADMIN_TITLE.fullmatch(normalize_text(line.text).replace(" ",""))
                for line in page.lines)
            and all(word in text for word in ("姓名","学号","所在学科","指导教师",
                "答辩日期","答辩地点","论文题目","评语和决议","答辩委员会"))
            and "同意通过" in text and "建议授予" in text
            and not any(CHAPTER.match(normalize_text(line.text)) for line in page.lines)
            and not any(pattern.search(text) for pattern in
                        (FIGURE_REFERENCE,TABLE_REFERENCE,APPENDIX_REFERENCE)))


def _signature_structure_candidate(pages,index):
    page=pages[index]
    previous=pages[index-1] if index else None
    following=pages[index+1] if index+1<len(pages) else None
    text=''.join(normalize_text(line.text).replace(' ','') for line in page.lines)
    # A page-sized raster can contain a complete signing form with no native
    # text at all. A CPU schema attempt is only a proposal; source pixels and
    # the full administrative structure must still prove any exclusion.
    from .signature_structure import _research
    from .signature_source_artifacts import scan_carrier_partition
    scanned=(not _research(page.lines) and scan_carrier_partition(page.images,page.width,page.height))
    # Nearby forms identify candidates, never permission to exclude a page.
    return bool(previous is not None and page.number==previous.number+1 and _form_context(previous)
        or following is not None and following.number==page.number+1 and _form_context(following)
        or any(word in text for word in ('原创性声明','使用授权','本人郑重声明')) or scanned)


def has_signature_structure_candidates(document,unreadable_numbers):
    """Discover administrative candidates without rendering or using a clock."""
    return any(page.number in unreadable_numbers and _signature_structure_candidate(document.pages,index)
               for index,page in enumerate(document.pages))


def _display_box(page,box):
    x1,y1,x2,y2=box
    return {0:box,90:(page.height-y2,x1,page.height-y1,x2),
            180:(page.width-x2,page.height-y2,page.width-x1,page.height-y1),
            270:(y1,page.width-x2,y2,page.width-x1)}[page.display_rotation%360]


def recovery_regions(previous,page):
    if page.number!=previous.number+1 or not _form_context(previous):
        return []
    previous_text="".join(normalize_text(line.text).replace(" ","") for line in previous.lines)
    complete_roster=all(word in previous_text for word in FIELDS if word not in {"秘书"}) and previous_text.count("委员")>=2
    display_height=page.width if page.display_rotation%180 else page.height
    def verdict_row(line):
        text=normalize_text(line.text).replace(" ","")
        return (len(text)<160 and any(word in text for word in
                ("投票表决结果","答辩结论","答辩委员会主席"))
                and not any(pattern.search(text) for pattern in
                    (FIGURE_REFERENCE,TABLE_REFERENCE,APPENDIX_REFERENCE)))
    pending=[line for line in page.lines if (line.role in {"table","table_body"} or verdict_row(line))
             and _display_box(page,line.bbox)[3]<display_height*.65]
    result=[]
    while pending:
        group=[pending.pop(0)]
        while True:
            joined=[line for line in pending if any(
                containment(line.bbox,other.bbox)>.1 or containment(other.bbox,line.bbox)>.1
                for other in group)]
            if not joined:
                break
            group.extend(joined)
            pending=[line for line in pending if line not in joined]
        text=normalize_text(" ".join(line.text for line in group)).replace(" ","")
        box=_display_box(page,union([line.bbox for line in group]))
        width=page.height if page.display_rotation%180 else page.width
        full=all(word in text for word in FIELDS) and text.count("委员")>=3
        continuation=(complete_roster and "秘书" in text
                      and any(word in text for word in ("学院","工作单位","职称")))
        verdict=all(word in text for word in ("答辩委员会主席","签字","建议授予"))
        if (full or continuation or verdict) and box[2]-box[0]>width*.4:
            # Keep original fragments: text in their gaps stays OCR input.
            result.extend(line.bbox for line in group)
    return result


def signature_regions(previous,page):
    if page.number!=previous.number+1 or not decision_form(previous):
        return []
    # Grid OCR can return the left and right halves of one table separately.
    # Join only geometrically overlapping table fragments before validating
    # the complete signature schema; isolated prose never participates.
    pending=[line for line in page.lines if line.role in {"table","table_body"}
             and line.bbox[3]<page.height*.5]
    result=[]
    while pending:
        group=[pending.pop(0)]
        while True:
            joined=[line for line in pending if any(
                containment(line.bbox,other.bbox)>.1 or containment(other.bbox,line.bbox)>.1
                for other in group)]
            if not joined:
                break
            group.extend(joined)
            pending=[line for line in pending if line not in joined]
        text=normalize_text(" ".join(line.text for line in group)).replace(" ","")
        box=union([line.bbox for line in group])
        if (all(word in text for word in FIELDS) and text.count("委员")>=3
                and box[2]-box[0]>page.width*.4):
            # The bounding union is for schema validation only. Mask the
            # original rectangles so text in any gap remains OCR input.
            result.extend(line.bbox for line in group)
    return result


def recover_signature_pages(document, unreadable_numbers, *, max_seconds=180, structure_only=False):
    pages=list(document.pages);evidence=[];deadline=monotonic()+max_seconds
    from .signature_structure import recover_structure
    for index,page in enumerate(pages):
        if page.number not in unreadable_numbers:
            continue
        previous=pages[index-1] if index else None
        if not _signature_structure_candidate(pages,index):
            continue
        try:
            answer=recover_structure(document,previous,page,deadline)
            if answer is not None:
                updated,record=answer;evidence.append(record)
                if updated is not None:
                    pages[index]=updated
        except Exception as exc:
            evidence.append({'page':page.number,'method':'displayed_signature_structure_cpu_ocr',
                             'status':'error','error_type':type(exc).__name__})
    if structure_only:
        return PdfDocument(document.path,tuple(pages)),evidence
    for index in range(1,len(pages)):
        page=pages[index]
        if page.number not in unreadable_numbers:
            continue
        if any(l.source=='signature_structure_cpu' and l.role.startswith('signature_verified_') for l in page.lines):
            continue
        regions=recovery_regions(pages[index-1],page)
        if not regions:
            continue
        record={"page":page.number,"method":"signature_remainder_cpu_ocr",
                "administrative_regions":[list(box) for box in regions]}
        try:
            import numpy as np
            with pymupdf.open(document.path) as source:
                raw=source[page.number-1];raw.set_rotation(0)
                scale=min(3,3000/max(raw.rect.width,raw.rect.height))
                pix=raw.get_pixmap(matrix=pymupdf.Matrix(scale,scale),colorspace=pymupdf.csGRAY,alpha=False)
                gray=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width).copy()
            paper=int(np.bincount(gray.ravel(),minlength=256).argmax())
            # Only the already-read form is masked in the temporary OCR view.
            # Text outside the form is retained, including below or beside it.
            gray,guard_boxes,artifacts=signature_remainder_view(gray,scale,regions,display_rotation=page.display_rotation)
            record["scan_artifacts"]=artifacts
            observations=[]
            hits,tiles=read_remainder(gray,scale,deadline=deadline,observations=observations,guard_boxes=guard_boxes,
                source_flat_paper=artifacts[-1]["source_flat_paper"])
            record.update(tiles=tiles,observations=observations,texts=[{"text":h.text,"score":h.score,"detection_score":h.detection_score,"bbox":list(h.bbox)} for h in hits])
            complete=not has_unread_text(hits)
            record["quality"]="low_confidence" if any(h.score<.8 for h in hits) else "normal"
            record["completion_meaning"]="OCR pipeline completed; recognition accuracy is not guaranteed"
            lines=list(page.lines)
            for hit in hits:
                if hit.text.strip() and not any(normalize_text(line.text)==normalize_text(hit.text)
                        and containment(hit.bbox,line.bbox)>.8 for line in lines):
                    lines.append(PdfLine(page.number,hit.text,hit.bbox,page.width,page.height,
                                         source="rapidocr",role="text"))
            pages[index]=replace(page,lines=tuple(sorted(lines,key=lambda line:(line.bbox[1],line.bbox[0]))),
                                 unreadable=not complete)
            record["status"]="completed" if complete else "unread_text"
        except Exception as exc:
            # Optional OCR backends use their own Exception subclasses (ONNX,
            # OpenCV, etc.). Preserve prior parsing/results at this boundary.
            record.update(status="error",error_type=type(exc).__name__)
        evidence.append(record)
    return PdfDocument(document.path,tuple(pages)),evidence
