from .mineru_layout import LayoutObject


def _horizontal_overlap(left: LayoutObject, right: LayoutObject) -> float:
    x1 = max(left.bbox[0], right.bbox[0])
    x2 = min(left.bbox[2], right.bbox[2])
    return max(0.0, x2 - x1) / max(1.0, min(left.bbox[2] - left.bbox[0],
                                              right.bbox[2] - right.bbox[0]))


def _matches(target: LayoutObject, caption: LayoutObject) -> bool:
    if _horizontal_overlap(target, caption) < 0.25:
        return False
    if target.page_number == caption.page_number:
        if target.kind == "figure":
            return 0 <= caption.bbox[1] - target.bbox[3] <= 80
        return 0 <= target.bbox[1] - caption.bbox[3] <= 80
    if caption.page_number == target.page_number + 1 and target.kind == "figure":
        return target.bbox[3] >= target.page_height * 0.75 and caption.bbox[1] <= caption.page_height * 0.15
    if caption.page_number == target.page_number - 1 and target.kind == "table":
        return caption.bbox[3] >= caption.page_height * 0.75 and target.bbox[1] <= target.page_height * 0.15
    return False


def _location(obj: LayoutObject) -> dict:
    x1, y1, x2, y2 = obj.bbox
    rect = {"x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "width": obj.page_width, "height": obj.page_height,
            "page_number": obj.page_number}
    return {"type": "pdf_bbox", "page_number": obj.page_number,
            "bounding_rect": rect, "rects": [rect], "text_excerpt": obj.text}


def detect_caption_rules(objects: list[LayoutObject], selected_rule_numbers) -> dict:
    result = {}
    selected = set(selected_rule_numbers)
    for rule, target_kind, caption_kind, label in (
        (13, "figure", "figure_caption", "图"),
        (14, "table", "table_caption", "表"),
    ):
        if rule not in selected:
            continue
        if not objects:
            result[str(rule)] = {"status": "unsupported", "reason": "MinerU 未返回可核查版面", "findings": []}
            continue
        captions = [obj for obj in objects if obj.kind == caption_kind]
        findings = []
        for target in (obj for obj in objects if obj.kind == target_kind):
            if any(_matches(target, caption) for caption in captions):
                continue
            findings.append({
                "rule_id": str(rule), "page": target.page_number,
                "message": f"{label}对象附近缺少{label}题",
                "text_excerpt": target.text,
                "location": _location(target),
            })
        result[str(rule)] = {"status": "completed", "findings": findings}
    return result

