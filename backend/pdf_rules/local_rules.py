from .model import DocumentIndex, Label, PdfLine


MESSAGES = {
    11: "正文引用的图 {token} 不存在",
    15: "图 {token} 未被全文引用",
    16: "表 {token} 未被全文引用",
    29: "引用的附录 {token} 不存在",
}


def same_target(reference: Label, target: Label) -> bool:
    if reference.number != target.number:
        return False
    if reference.qualified:
        return target.scope != "body"
    return reference.scope == target.scope


def location(line: PdfLine) -> dict:
    x1, y1, x2, y2 = line.bbox
    rect = {
        "x1": x1, "y1": y1, "x2": x2, "y2": y2,
        "width": line.page_width, "height": line.page_height,
        "page_number": line.page_number,
    }
    return {
        "type": "pdf_bbox", "page_number": line.page_number,
        "bounding_rect": rect, "rects": [rect], "text_excerpt": line.text,
    }


def finding(rule: int, label: Label) -> dict:
    return {
        "rule_id": str(rule),
        "page": label.line.page_number,
        "token": label.number,
        "message": MESSAGES[rule].format(token=label.number),
        "text_excerpt": label.line.text,
        "location": location(label.line),
    }


def detect_rules(index: DocumentIndex, selected_rule_numbers) -> dict[str, dict]:
    selected = set(selected_rule_numbers)
    result = {}
    unreadable = not index.lines or any(page.unreadable for page in index.document.pages)
    for rule in selected:
        if rule not in MESSAGES:
            result[str(rule)] = {"status": "unsupported", "reason": "该规则尚需 MinerU 版面结果", "findings": []}
            continue
        if unreadable:
            result[str(rule)] = {"status": "unsupported", "reason": "PDF 页面文字无法完整提取", "findings": []}
            continue
        if rule == 11:
            labels = [ref for ref in index.figure_refs
                      if not any(same_target(ref, target) for target in index.figures)]
        elif rule == 15:
            labels = [target for target in index.figures
                      if not any(same_target(ref, target) for ref in index.figure_refs)]
        elif rule == 16:
            labels = [target for target in index.tables
                      if not any(same_target(ref, target) for ref in index.table_refs)]
        else:
            existing = {label.number for label in index.appendices}
            labels = [ref for ref in index.appendix_refs if ref.number not in existing]
        result[str(rule)] = {"status": "completed", "findings": [finding(rule, label) for label in labels]}
    return result

