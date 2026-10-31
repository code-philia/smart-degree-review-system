"""Run bilingual semantic rules using the repository Paper Model and campus API."""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
import urllib.error
import time

_LAST_REQUEST_AT = 0.0
from pathlib import Path
from typing import Any

from paper_model_bilingual_rules import extract_bilingual_facts, _json_object, _bounded_text
from paper_compiler.frontend import build_paper


BILINGUAL_RULES = {
    "bilingual_abstract_consistency_check",
    "bilingual_keywords_correspondence_check",
}
TYPO_RULE = "typo_detection_check"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--rule", action="append", required=True)
    return parser.parse_args()


def api_config() -> tuple[str, str, str, str]:
    campus = (
        os.environ.get("SJTU_API_KEY", "").strip()
        and os.environ.get("SJTU_API_BASE_URL", "").strip()
        and os.environ.get("SJTU_API_MODEL", "").strip()
    )
    if campus:
        return (
            os.environ["SJTU_API_KEY"].strip(),
            os.environ["SJTU_API_BASE_URL"].rstrip("/"),
            os.environ["SJTU_API_MODEL"].strip(),
            "sjtu",
        )
    key = os.environ.get("REVIEW_PILOT_DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise RuntimeError("语义规则尚未配置校内 SJTU_API_*")
    return key, "https://api.deepseek.com", "deepseek-v4-flash", "deepseek"


def request_json(messages: list[dict[str, str]]) -> tuple[dict[str, Any], dict[str, int]]:
    global _LAST_REQUEST_AT
    try:
        min_interval = max(0.0, float(os.environ.get("SJTU_API_MIN_INTERVAL_SECONDS", "6")))
    except (TypeError, ValueError):
        min_interval = 6.0
    wait = min_interval - (time.monotonic() - _LAST_REQUEST_AT)
    if wait > 0:
        time.sleep(wait)
    _LAST_REQUEST_AT = time.monotonic()
    key, base_url, model, _provider = api_config()
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 8192,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        request_timeout = max(
            120.0,
            float(os.environ.get("SJTU_API_REQUEST_TIMEOUT_SECONDS", "300")),
        )
    except (TypeError, ValueError):
        request_timeout = 300.0
    for attempt in range(4):
        try:
            with opener.open(request, timeout=request_timeout) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
            break
        except urllib.error.HTTPError as error:
            detail = error.read(2000).decode("utf-8", "replace")
            if error.code == 429 and attempt < 3:
                retry_after = error.headers.get("Retry-After") if error.headers else None
                try: delay = min(30.0, max(1.0, float(retry_after)))
                except (TypeError, ValueError): delay = float(2 ** attempt)
                time.sleep(delay)
                continue
            raise RuntimeError(f"校内 DeepSeek 请求失败（HTTP {error.code}）：{detail[:500]}") from error
    data = json.loads(raw)
    content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content")
    if isinstance(content, dict):
        result = content
    else:
        result = _json_object(content)
    usage = data.get("usage") or {}
    return result, {
        "input_tokens": int(usage.get("prompt_tokens") or 0),
        "output_tokens": int(usage.get("completion_tokens") or 0),
    }


def prompt_for(rule_id: str, facts: dict[str, Any]) -> str | None:
    if rule_id == "bilingual_abstract_consistency_check":
        left, right = facts.get("chinese_abstract"), facts.get("english_abstract")
        if not left or not right:
            return None
        return (
            "比较同一学位论文的中文摘要和英文摘要，判断研究对象、方法、数据、主要结果和结论是否对应。"
            "不要求逐字翻译。请用简体中文填写 summary 和 mismatches。仅返回 JSON，键为："
            "outcome (consistent|inconsistent|inconclusive), summary, mismatches (array)。\n"
            "中文摘要：\n" + _bounded_text(left) +
            "\n\n英文摘要：\n" + _bounded_text(right)
        )
    left, right = facts.get("chinese_keywords"), facts.get("english_keywords")
    if not left or not right:
        return None
    return (
        "按语义而不是数量匹配中文和英文关键词。英文关键词中，字母之间的单个连字符可能来自 PDF 跨行换行；语义匹配时忽略这种版式差异，不要将其判为拼写错误。请用简体中文填写 summary、reason 和其它说明字段。"
        "仅返回 JSON，键为：outcome (consistent|inconsistent|inconclusive), "
        "summary, pairs (array of objects with chinese, english, match, reason), "
        "missing_chinese (array), missing_english (array)。\n"
        "中文关键词：" + json.dumps(left.get("match_values", left.get("values", [])), ensure_ascii=False) +
        "\n英文关键词：" + json.dumps(right.get("match_values", right.get("values", [])), ensure_ascii=False)
    )




def _normalize_for_model(text: str) -> str:
    # PDF extraction may insert spaces inside Chinese words (e.g. "剔 除").
    return re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", text)


def _is_cjk(char: str) -> bool:
    return bool(char) and "\u3400" <= char <= "\u9fff"


def _normalize_layout_line_breaks(text: str) -> str:
    # A PDF line break inside one paragraph is layout, not a sentence boundary.
    # Rejoin hyphenated Latin words and CJK text before sending the chunk to the model.
    text = re.sub(r"([A-Za-z])-\s*\r?\n\s*([A-Za-z])", r"\1-\2", text)
    text = re.sub(r"(?<=[\u3400-\u9fff])\s*\r?\n\s*(?=[\u3400-\u9fff])", "", text)
    text = re.sub(r"(?<=[A-Za-z])\s*\r?\n\s*(?=[A-Za-z])", " ", text)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _model_piece(text: str) -> str:
    return _normalize_for_model(_normalize_layout_line_breaks(text)).strip("\r\n")


def _join_model_parts(parts: list[str]) -> str:
    result = ""
    for raw in parts:
        piece = _model_piece(raw)
        if not piece:
            continue
        if result and not (_is_cjk(result[-1:]) and _is_cjk(piece[:1])):
            result += "\n"
        result += piece
    return result


def _split_piece(text: str, size: int) -> list[str]:
    pieces = []
    remaining = text
    punctuation = "。！？；.!?;\n"
    while len(remaining) > size:
        candidates = [i + 1 for i, char in enumerate(remaining[:size]) if char in punctuation]
        cut = max(candidates) if candidates else size
        pieces.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        pieces.append(remaining)
    return pieces


def _body_chunks(ir: dict[str, Any], size: int = 6000) -> list[dict[str, Any]]:
    """Return sentence-aware chunks and source segments for precise locations."""
    nodes = {node.get("id"): node for node in ir.get("nodes", [])}
    body = next((node for node in ir.get("nodes", []) if node.get("kind") == "Body"), None)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    def walk(node_id: str) -> None:
        if node_id in seen: return
        seen.add(node_id)
        node = nodes.get(node_id)
        if not node: return
        if node.get("kind") in {"Paragraph", "Heading"}:
            candidates.append(node)
        for child in node.get("children", []) or []: walk(child)
    for child in (body or {}).get("children", []) or []: walk(child)

    def source_box(node: dict[str, Any], first: bool) -> tuple[int, list[float]] | None:
        sources = [item for item in (node.get("provenance") or [])
                   if isinstance(item, dict) and isinstance(item.get("page_index"), int)
                   and isinstance(item.get("bbox"), list) and len(item["bbox"]) == 4]
        if not sources:
            return None
        item = sources[0] if first else sources[-1]
        return int(item["page_index"]), [float(value) for value in item["bbox"]]

    def is_layout_continuation(left: dict[str, Any], right: dict[str, Any]) -> bool:
        left_text = str(left.get("text") or "").strip()
        right_text = str(right.get("text") or "").strip()
        if left.get("kind") != "Heading" or right.get("kind") != "Paragraph":
            return False
        if len(left_text) < 20 or not left_text or not right_text:
            return False
        if not _is_cjk(left_text[-1:]) or not (_is_cjk(right_text[:1]) or right_text[:1].isalnum()):
            return False
        if re.search(r"[。！？；.!?;：:]$", left_text):
            return False
        if not re.search(r"[，、：,:]", left_text):
            return False
        left_source = source_box(left, False)
        right_source = source_box(right, True)
        if not left_source or not right_source or left_source[0] != right_source[0]:
            return False
        gap = right_source[1][1] - left_source[1][3]
        return 0 <= gap <= 12

    ordered: list[dict[str, Any]] = []
    index = 0
    while index < len(candidates):
        node = candidates[index]
        if node.get("kind") == "Heading" and index + 1 < len(candidates):
            following = candidates[index + 1]
            if is_layout_continuation(node, following):
                following["_join_previous_layout_node"] = True
                ordered.append(node)
                index += 1
                node = following
        if node.get("kind") == "Paragraph":
            ordered.append(node)
        index += 1
    if not ordered:
        ordered = [node for node in ir.get("nodes", [])
                   if node.get("kind") in {"Paragraph", "UnknownBlock"} and str(
                       node.get("text") or "").strip()]
    page_sizes = {int(page.get('page_index', -1)) + 1: (float(page.get('width') or 0), float(page.get('height') or 0)) for page in (ir.get('layout', {}).get('pages', []) or [])}
    chunks: list[dict[str, Any]] = []
    current: list[str] = []
    current_model: list[str] = []
    segments: list[dict[str, Any]] = []
    length = 0
    model_length = 0
    def flush() -> None:
        nonlocal current, current_model, segments, length, model_length
        if current:
            chunks.append({"text": "\n".join(current), "model_text": "".join(current_model), "segments": segments[:], "page": segments[0].get("page") if segments else None})
        current, current_model, segments, length, model_length = [], [], [], 0, 0
    for node in ordered:
        raw = str(node.get("text") or "").strip()
        if not raw: continue
        provenance = node.get("provenance") or []
        source_parts = []
        for source in provenance:
            if not isinstance(source, dict) or not isinstance(source.get("page_index"), int):
                continue
            start = source.get("node_text_start")
            end = source.get("node_text_end")
            if not isinstance(start, int) or not isinstance(end, int) or not (0 <= start < end <= len(raw)):
                continue
            source_parts.append((raw[start:end], int(source["page_index"]) + 1,
                                 source.get("bbox") if isinstance(source.get("bbox"), list) else None))
        if not source_parts:
            source = next((item for item in provenance if isinstance(item.get("page_index"), int)), {})
            source_parts = [(raw, int(source["page_index"]) + 1 if isinstance(source.get("page_index"), int) else None,
                            source.get("bbox") if isinstance(source.get("bbox"), list) else None)]
        paragraph_break = bool(current) and not node.get("_join_previous_layout_node")
        for source_text, page, bbox in source_parts:
            for piece in _split_piece(source_text, size):
                if length and length + len(piece) + 1 > size:
                    flush()
                    paragraph_break = False
                normalized_piece = _model_piece(piece)
                # Keep paragraph boundaries, but join CJK split across lines
                # inside the same paragraph. This prevents unrelated rows from
                # becoming one artificial word while preserving source offsets.
                separator_length = 0
                previous_normalized = _model_piece(current[-1]) if current else ""
                if current and paragraph_break:
                    separator_length = 2
                elif current and previous_normalized and normalized_piece and _is_cjk(previous_normalized[-1:]) and _is_cjk(normalized_piece[:1]):
                    separator_length = 0
                elif current:
                    separator_length = 1
                model_length += separator_length
                current.append(piece)
                current_model.append(("\n" * separator_length) + normalized_piece)
                paragraph_break = False
                page_width, page_height = page_sizes.get(page, (0.0, 0.0))
                segments.append({"text": piece, "page": page, "bbox": bbox,
                                 "page_width": page_width, "page_height": page_height,
                                 "start": model_length, "end": model_length + len(normalized_piece)})
                model_length += len(normalized_piece)
                length += len(piece) + 1
    flush()
    return chunks


def typo_prompt(text: str) -> str:
    return (
        "你是学位论文校对助手。只报告有充分证据的单字、词语或很短的局部短语错误，绝不得返回完整句子或句子片段。"
        "英文只检查自然语言中的普通单词拼写；程序变量、函数名、类名、文件名、命令、路径、协议名、模型名、缩写和数学符号一律不是错别字。"
        "不得只修改标点、空格、换行、连字符、大小写或排版；不得修改专业术语、作者名、缩写、模型名、代码库名、公式、数字、引用或专有名词。"
        "PDF 同一段落中的换行已经由程序归一化；如遇跨行连字符（如 \"re-\nverse\"）或中文词内提取空格（如“剔 除”），不得报告。"
        "每个候选必须有 confidence，范围为 0 到 1；confidence < 0.85 时不要返回。中文错别字只有在存在明确的常见字词替换关系、替换后语义明显合理且原字明显不合理，并且同一术语在正文其他位置有稳定写法或上下文能够证明当前字词不成立时才可返回。"
        "请用简体中文返回严格 JSON，不要 Markdown："
        "{\"findings\":[{\"text\":\"原文中的短词或短语\",\"suggestion\":\"建议文字\",\"reason\":\"简短理由\",\"confidence\":0.0,\"common_confusion\":true,\"semantic_validity\":true,\"stable_usage\":false,\"context_proof\":true}]}。原文如下：\n" + text
    )


def run_typo_rule_from_ir(ir: dict[str, Any]) -> dict[str, Any]:
    findings = []
    usage_total = {"input_tokens": 0, "output_tokens": 0}
    chunks = _body_chunks(ir)
    failure = None
    for index, chunk in enumerate(chunks):
        try:
            payload, usage = request_json([{"role": "user", "content": typo_prompt(chunk["model_text"])}])
        except Exception as exc:
            failure = str(exc)[:300]
            break
        usage_total["input_tokens"] += usage["input_tokens"]
        usage_total["output_tokens"] += usage["output_tokens"]
        rows = payload.get("findings") if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            continue
        for row in rows[:20]:
            if not isinstance(row, dict) or not str(row.get("text") or "").strip():
                continue
            original = str(row.get("text") or "").strip()
            suggestion = str(row.get("suggestion") or "").strip()
            try:
                confidence = float(row.get("confidence"))
            except (TypeError, ValueError):
                continue
            if confidence < 0.85:
                continue
            # Full sentences and layout-only edits are never typo findings.
            if len(original) > 30 or re.search(r"[。！？；.!?]", original):
                continue
            surface_normalize = lambda value: re.sub(r"[^\w\u3400-\u9fff]", "", value.casefold())
            if surface_normalize(original) == surface_normalize(suggestion):
                continue
            # English-looking identifiers and mathematical symbols are common in papers.
            # They are not spelling candidates even when the model proposes a plausible replacement.
            if _looks_like_code_or_math(original) or _looks_like_code_or_math(suggestion):
                continue
            needle = _normalize_for_model(original)
            model_text = chunk.get("model_text", "")
            match_start = model_text.find(needle)
            if match_start < 0:
                continue
            match_end = match_start + len(needle)
            if _looks_like_code_context(model_text, match_start, match_end):
                continue
            # Do not accept a substring cut out of a longer CJK word.
            if _has_cjk(original):
                before = model_text[match_start - 1:match_start]
                after = model_text[match_end:match_end + 1]
                if (_is_cjk(original[:1]) and _is_cjk(before)) or (_is_cjk(original[-1:]) and _is_cjk(after)):
                    continue
            matched_segments = [item for item in chunk.get("segments", [])
                                if item.get("end", 0) > match_start and item.get("start", 0) < match_end]
            pages = [item.get("page") for item in matched_segments if item.get("page")]
            rects = []
            for item in matched_segments:
                bbox = item.get("bbox")
                if bbox and len(bbox) == 4 and item.get("page"):
                    x1, y1, x2, y2 = [float(value) for value in bbox]
                    rects.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2,
                                  "width": float(item.get("page_width") or 0),
                                  "height": float(item.get("page_height") or 0),
                                  "page_number": item["page"]})
            location = None
            if pages and rects:
                x1 = min(rect["x1"] for rect in rects); y1 = min(rect["y1"] for rect in rects)
                x2 = max(rect["x2"] for rect in rects); y2 = max(rect["y2"] for rect in rects)
                first_rect = rects[0]
                bounding = {"x1": x1, "y1": y1, "x2": x2, "y2": y2,
                            "width": first_rect["width"], "height": first_rect["height"],
                            "page_number": pages[0]}
                location = {"type": "pdf_bbox", "page_number": pages[0], "bounding_rect": bounding, "rects": rects, "text_excerpt": original[:120]}
            elif pages:
                location = {"type": "pdf_page", "page_number": pages[0], "text_excerpt": original[:120]}
            findings.append({
                "finding_id": f"{TYPO_RULE}_{len(findings) + 1}", "rule_id": TYPO_RULE,
                "message": f"疑似错别字：{original[:120]}",
                "suggestion": suggestion,
                "location": location,
                "anchors": ([{"anchor_id": f"typo-{len(findings) + 1}",
                               "role": "source_span", "label": "疑似错别字",
                               "description": original, "location": location}]
                             if location else []),
                "evidence": [{"id": f"typo-chunk-{index + 1}", "kind": "source_span",
                              "provider": "repo-paper-model", "quote": str(row.get("text"))[:120]}],
                "reason": str(row.get("reason") or "")[:300],
            })
    return {"rule_run_id": f"run_{TYPO_RULE}", "rule_id": TYPO_RULE, "severity": "warning",
            "params": {"chunk_count": len(chunks), "chunk_size": 6000},
            "execution_status": "error" if failure else "completed", "evidence_mode": "derived",
            "outcome": "inconclusive" if failure else ("issues_found" if findings else "passed"),
            "message": (f"错别字分块检测未完成：{failure}" if failure else None),
            "findings": findings, "model_usage": usage_total}

def _has_cjk(value: Any) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in str(value or ""))


def _looks_like_code_or_math(value: Any) -> bool:
    """Reject identifiers/symbols before turning an LLM guess into a finding."""
    text = str(value or "").strip()
    if not text:
        return True
    # Non-ASCII characters outside CJK/whitespace are normally math glyphs or
    # styled variables in extracted PDF text (𝑓, 𝑟, subscripts, etc.).
    if any(ord(ch) > 127 and not ("\u3400" <= ch <= "\u9fff") and not ch.isspace()
               for ch in text):
        return True
    if any(ch.isdigit() for ch in text) or re.search(r"[_\/$=<>\[\]{}()^~|]", text):
        return True
    if re.search(r"[a-z][A-Z]|[A-Z][a-z].*[A-Z]", text):
        return True
    if text.isascii() and text.isalpha():
        if len(text) == 1 or (text.isupper() and len(text) <= 16):
            return True
    return False


def _looks_like_code_context(text: str, start: int, end: int) -> bool:
    """Ignore ordinary-looking words when they occur in code/identifier prose."""
    window = text[max(0, start - 100):min(len(text), end + 100)]
    patterns = (
        r"\x60",
        r"(?:参数名|变量名|变量|函数名|函数|方法名|类名|标识符|代码|代码片段|"
        r"命令|路径|协议名|模型名|库名|调用|返回值|接口)",
        r"\b(?:def|class|return|import|from|if|else|for|while|try|except)\b",
        r"[A-Za-z_]\w*\s*(?:\(|=|::)",
    )
    return any(re.search(pattern, window, flags=re.IGNORECASE) for pattern in patterns)


def _location(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    page = value.get("page_number")
    if not isinstance(page, int) or page < 1:
        return None
    return {"type": "pdf_page", "page_number": page,
            "text_excerpt": str(value.get("text_excerpt") or "")[:500]}


def _anchors_and_evidence(facts: dict[str, Any], kind: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    locations = facts.get("locations") or {}
    labels = (("chinese_abstract", "中文摘要"), ("english_abstract", "英文摘要")) if kind == "abstract" else (("chinese_keywords", "中文关键词"), ("english_keywords", "英文关键词"))
    anchors = []
    evidence = []
    for index, (key, label) in enumerate(labels, 1):
        loc = _location(locations.get(key))
        if not loc:
            continue
        anchors.append({"anchor_id": f"{kind}-{index}", "role": "source_span",
                        "label": label, "description": label, "location": loc})
        value = facts.get(key)
        quote = str(value.get("text") if isinstance(value, dict) else value or "").strip()
        evidence.append({"id": f"{kind}-{index}", "kind": "source_span",
                         "provider": "repo-paper-model", "quote": quote[:2000]})
    return anchors, evidence


def _chinese_summary(value: Any, abstract: bool) -> str:
    text = str(value or "").strip()
    if _has_cjk(text):
        return text
    return ("中英文摘要在研究对象、方法、数据、主要结果或结论中的至少一项存在语义不一致，请结合两侧原文核对。"
            if abstract else
            "中英文关键词存在语义不对应，请结合两侧关键词原文逐项核对。")


def run(pdf: Path, rule_ids: list[str]) -> dict[str, Any]:
    ir = build_paper(pdf, include_citations=False)
    facts = extract_bilingual_facts(ir) if any(rule in BILINGUAL_RULES for rule in rule_ids) else {}
    runs = []
    for rule_id in rule_ids:
        if rule_id == TYPO_RULE:
            runs.append(run_typo_rule_from_ir(ir))
            continue
        prompt = prompt_for(rule_id, facts)
        if prompt is None:
            runs.append({
                "rule_run_id": f"run_{rule_id}",
                "rule_id": rule_id,
                "severity": "warning",
                "params": None,
                "execution_status": "completed",
                "evidence_mode": "derived",
                "outcome": "inconclusive",
                "message": "未能从 Paper Model 中同时识别中英文摘要或关键词。",
                "findings": [],
            })
            continue
        payload, usage = request_json([{"role": "user", "content": prompt}])
        outcome = str(payload.get("outcome", "inconclusive")).lower()
        findings = []
        if outcome == "inconsistent":
            abstract = rule_id.endswith("abstract_consistency_check")
            anchors, evidence = _anchors_and_evidence(facts, "abstract" if abstract else "keywords")
            primary_location = anchors[0]["location"] if anchors else None
            findings.append({
                "finding_id": f"{rule_id}_1",
                "rule_id": rule_id,
                "message": _chinese_summary(payload.get("summary"), abstract),
                "suggestion": (
                    "请依据下方中文摘要和英文摘要原文，定位研究对象、方法、数据、结果或结论的具体差异，并只对不一致的一侧作最小修改。"
                    if abstract else
                    "请依据下方中英文关键词原文，逐项核对语义对应关系；对不对应项进行补齐、删除或修正，不要仅按数量调整。"
                ),
                "location": primary_location,
                "anchors": anchors,
                "evidence": evidence,
            })
        runs.append({
            "rule_run_id": f"run_{rule_id}",
            "rule_id": rule_id,
            "severity": "warning",
            "params": None,
            "execution_status": "completed",
            "evidence_mode": "derived",
            "outcome": "issues_found" if findings else (
                "inconclusive" if outcome == "inconclusive" else "passed"
            ),
            "message": str(payload.get("summary")) if outcome == "inconclusive" else None,
            "findings": findings,
            "model_usage": usage,
        })
    finding_count = sum(len(item["findings"]) for item in runs)
    return {
        "type": "paper_lint",
        "paper_title": "上传论文",
        "ruleset": {
            "id": "repo-paper-model-bilingual",
            "name": "仓库 Paper Model 双语语义规则",
            "version_number": 1,
            "version_label": "repo paper_compiler",
        },
        "rule_runs": runs,
        "summary": {
            "rule_count": len(runs),
            "completed_rule_count": sum(item.get("execution_status") == "completed" for item in runs),
            "unsupported_rule_count": sum(item.get("execution_status") == "unsupported" for item in runs),
            "error_rule_count": sum(item.get("execution_status") == "error" for item in runs),
            "issue_rule_count": sum(bool(item["findings"]) for item in runs),
            "finding_count": finding_count,
            "error_finding_count": 0,
            "warning_finding_count": finding_count,
            "info_finding_count": 0,
            "derived_rule_count": len(runs),
        },
    }


def main() -> None:
    args = parse_args()
    unknown = [rule for rule in args.rule if rule not in BILINGUAL_RULES and rule != TYPO_RULE]
    if unknown:
        raise RuntimeError(f"未知双语语义规则：{unknown[0]}")
    print(json.dumps(run(args.pdf, args.rule), ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
