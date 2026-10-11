from .model import DocumentIndex, Label, PdfLine
from .caption_identity import caption_groups
from copy import copy


MESSAGES = {
    11: "正文引用的图 {token} 不存在",
    15: "图 {token} 未被全文引用",
    16: "表 {token} 未被全文引用",
    29: "引用的附录 {token} 不存在",
}


def same_target(reference: Label, target: Label) -> bool:
    if reference.number != target.number:
        return False
    if reference.target_scope is not None:
        return reference.target_scope == target.scope
    return reference.scope == target.scope


def resolved_target(reference: Label, target: Label, targets) -> bool:
    if same_target(reference,target):
        return True
    # Chapter-style numeric labels in an appendix can refer back to the body.
    # An explicit appendix qualifier or an existing local target retains scope.
    return (reference.target_scope is None and reference.scope != 'body'
            and target.scope == 'body' and reference.number == target.number
            and reference.number[:1].isdigit() and '.' in reference.number
            and not any(t.number==reference.number and t.scope==reference.scope for t in targets))


def indirect_reference_key(kind, reference):
    """Identity of an inferred use, without changing the native index schema."""
    return (kind, reference.scope, reference.number, reference.target_scope,
            reference.line.page_number, reference.line.bbox, reference.line.text)


def physical_target_key(kind, target):
    return (kind, target.scope, target.number, target.line.page_number, target.line.bbox)


def inferred_target(reference, target, kind, index, groups, targets):
    bindings = getattr(index, 'indirect_reference_targets', {})
    key = indirect_reference_key(kind, reference)
    if key in bindings:
        physical = physical_target_key(kind, target)
        # Caption grouping may expand a native first line into its wrapped
        # title rectangle. The original caption must remain inside that title,
        # on the same page and with the same scope/number/type identity.
        return any(bound[:4] == physical[:4]
                   and physical[4][0]-1 <= bound[4][0] and physical[4][1]-1 <= bound[4][1]
                   and bound[4][2] <= physical[4][2]+1 and bound[4][3] <= physical[4][3]+1
                   for bound in bindings[key])
    # Older native inferred uses have no physical identity. Keep their unique
    # resolution, but never let one unbound number credit distinct objects.
    matching = [g for g in groups if any(resolved_target(reference, t, targets) for t in g)]
    return len(matching) == 1 and any(physical_target_key(kind, target) == physical_target_key(kind, t)
                                    for t in matching[0])


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


def finding(rule: int, label: Label, companions=()) -> dict:
    answer = {
        "rule_id": str(rule),
        "page": label.line.page_number,
        "token": label.number,
        "message": MESSAGES[rule].format(token=label.number),
        "text_excerpt": label.line.text,
        "location": location(label.line),
    }
    if companions:
        lines = [label.line, *[item.line for item in companions]]
        rects = [location(line)["bounding_rect"] for line in lines]
        union = dict(rects[0], x1=min(r["x1"] for r in rects), y1=min(r["y1"] for r in rects),
                     x2=max(r["x2"] for r in rects), y2=max(r["y2"] for r in rects))
        excerpt = "\n".join(line.text for line in lines)
        answer.update(text_excerpt=excerpt, caption_count=len(lines))
        answer["location"].update(bounding_rect=union, rects=rects, text_excerpt=excerpt)
    return answer


def detect_rules(index: DocumentIndex, selected_rule_numbers) -> dict[str, dict]:
    selected = set(selected_rule_numbers)
    result = {}
    unreadable = not index.lines or any(page.unreadable for page in index.document.pages)
    usage_index = None
    for rule in selected:
        if rule not in MESSAGES:
            result[str(rule)] = {"status": "unsupported", "reason": "该规则尚需 MinerU 版面结果", "findings": []}
            continue
        if rule in {15, 16}:
            if usage_index is None:
                from .usage_scope import usage_document
                from .usage_reference_evidence import recover_usage_index
                view = usage_document(index.document)
                eligible = {(line.page_number, line.bbox, line.text) for line in view.lines}
                usage_index = copy(index)
                usage_index.document = view
                usage_index.figures = [target for target in index.figures
                                       if (target.line.page_number, target.line.bbox, target.line.text) in eligible]
                usage_index.tables = [target for target in index.tables
                                      if (target.line.page_number, target.line.bbox, target.line.text) in eligible]
                usage_index = recover_usage_index(usage_index, explicit_only=True)
            # Entire exempt intervals can legitimately leave an empty view.
            if any(page.unreadable for page in usage_index.document.pages) or (
                    not usage_index.lines and usage_index.document == index.document):
                result[str(rule)] = {"status": "unsupported", "reason": "PDF 页面文字无法完整提取", "findings": []}
                continue
            from .usage_continuations import usage_caption_groups
            from .usage_scope import usage_scope_map
            from .usage_reference_evidence import usage_resolved_target, usage_inferred_target
            usage_scopes = usage_scope_map(usage_index.document)
            targets = usage_index.figures if rule == 15 else usage_index.tables
            kind = 'figure' if rule == 15 else 'table'
            direct = usage_index.figure_refs if rule == 15 else usage_index.table_refs
            indirect = usage_index.graphic_figure_refs if rule == 15 else usage_index.graphic_table_refs
            physical_groups = list(caption_groups(targets, usage_index.lines, usage_index.document))
            physical_groups = usage_caption_groups(physical_groups, usage_index, kind)
            groups = [group for ordinal, group in enumerate(physical_groups)
                      if not any(usage_resolved_target(ref, target, targets, usage_scopes)
                                  for target in group for ref in direct)
                      and not any(usage_inferred_target(ref, target, kind, usage_index, physical_groups, targets, usage_scopes)
                                  for target in group for ref in indirect)]
            result[str(rule)] = {"status": "completed", "findings": [
                finding(rule, group[0], [item for item in group[1:]
                                        if item.line.page_number == group[0].line.page_number])
                for group in groups]}
            continue
        if unreadable:
            result[str(rule)] = {"status": "unsupported", "reason": "PDF 页面文字无法完整提取", "findings": []}
            continue
        if rule == 11:
            labels = [ref for ref in index.figure_refs
                      if not any(resolved_target(ref, target, index.figures) for target in index.figures)]
        else:
            existing = {label.number for label in index.appendices}
            labels = [ref for ref in index.appendix_refs if ref.number not in existing]
        groups = caption_groups(labels,index.lines) if rule in {15, 16} else ([label] for label in labels)
        result[str(rule)] = {"status": "completed", "findings": [finding(rule, group[0], group[1:]) for group in groups]}
    return result
