"""Run bilingual semantic rules using the repository Paper Model and campus API."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from paper_compiler.campus_requests import campus_request
from paper_compiler.semantic_cache import SemanticResponseCache
from paper_compiler.storage import json_bytes


BILINGUAL_RULES = {
    "bilingual_abstract_consistency_check",
    "bilingual_keywords_correspondence_check",
}
TYPO_RULE = "typo_detection_check"
NUMERIC_RULE = "abstract_numeric_consistency_check"
API_CAPACITY_MESSAGE = "当前系统使用人数较多，API 调用暂时繁忙，请稍后重试。"
RULE_RETRY_MESSAGE = "当前规则暂时无法完成，请稍后重试。"


def public_failure_message(error: object) -> str:
    """Keep transport, SQLite and provider internals out of user reports."""
    detail = str(error or "").lower()
    capacity_markers = (
        "database is locked", "locked", "timeout", "timed out", "http 429",
        "http_429", "rate limit", "too many requests", "api request", "connection",
        "deepseek", "campus api", "shared slot", "service unavailable",
    )
    return API_CAPACITY_MESSAGE if any(marker in detail for marker in capacity_markers) else RULE_RETRY_MESSAGE


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--rule", action="append", required=True)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--progress-jsonl", action="store_true")
    parser.add_argument("--allow-incomplete-structure", action="store_true")
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


def request_json(messages: list[dict[str, str]], *, observer=None) -> tuple[dict[str, Any], dict[str, int]]:
    global _LAST_REQUEST_AT
    key, base_url, model, _provider = api_config()
    if _provider != "sjtu":
        try:
            min_interval = max(0.0, float(os.environ.get("SJTU_API_MIN_INTERVAL_SECONDS", "6")))
        except (TypeError, ValueError):
            min_interval = 6.0
        wait = min_interval - (time.monotonic() - _LAST_REQUEST_AT)
        if wait > 0:
            time.sleep(wait)
        _LAST_REQUEST_AT = time.monotonic()
    # PDF font maps may expose unpaired UTF-16 code units. Keep those units as
    # literal escapes in model input: campus proxies also require scalar UTF-8
    # after decoding JSON. The original messages/IR remain untouched.
    model_messages = [{name: value.encode('utf-8', 'backslashreplace').decode('utf-8')
                       if isinstance(value, str) else value for name, value in message.items()}
                      for message in messages]
    payload = {
        "model": model,
        "messages": model_messages,
        "temperature": 0,
        "max_tokens": 8192,
        "response_format": {"type": "json_object"},
    }
    if _provider == 'sjtu' and observer is None:
        # Match the campus compiler's extraction mode; numeric audits retain
        # their existing request contract and trace.
        payload['chat_template_kwargs'] = {'thinking': False}
    cache = None
    cache_root = os.environ.get('SJTU_API_RESPONSE_CACHE_DIR', '').strip()
    if _provider == 'sjtu' and observer is None and cache_root:
        cache = SemanticResponseCache(cache_root, base_url, key, payload)
        cached = cache.read()
        if cached is not None:
            return cached, {'input_tokens': 0, 'output_tokens': 0}
    if observer:
        from urllib.parse import urlsplit
        observer('request_config', {'provider': _provider, 'host': urlsplit(base_url).hostname, 'parameters': payload})
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json_bytes(payload),
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
    attempts = 0
    def send(remaining):
        nonlocal attempts
        attempts += 1
        if observer:
            observer('request_attempt', {'attempt': attempts})
        try:
            with opener.open(request, timeout=remaining) as response:
                return response.read(8 * 1024 * 1024 + 1)
        except urllib.error.HTTPError as error:
            if observer:
                observer('http_error', {'attempt': attempts, 'status': error.code})
            raise
    try:
        raw = campus_request(request.full_url, dict(request.header_items()), request_timeout, send)
    except urllib.error.HTTPError as error:
        detail = error.read(2000).decode("utf-8", "replace")
        raise RuntimeError(f"校内 DeepSeek 请求失败（HTTP {error.code}）：{detail[:500]}") from error
    if observer:
        observer('raw_response', {'body': raw.decode('utf-8', 'replace')})
    data = json.loads(raw)
    if observer and (data.get('choices') or [{}])[0].get('finish_reason') == 'length':
        raise ValueError('模型输出达到上限，数值核验未完成')
    content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content")
    if isinstance(content, dict):
        result = content
    else:
        result = _json_object(content)
    if cache and (data.get('choices') or [{}])[0].get('finish_reason') == 'stop':
        cache.write(result)
    usage = data.get("usage") or {}
    return result, {
        "input_tokens": int(usage.get("prompt_tokens") or 0),
        "output_tokens": int(usage.get("completion_tokens") or 0),
    }


def prompt_for(rule_id: str, facts: dict[str, Any]) -> str | None:
    if rule_id == NUMERIC_RULE:
        return None
    if rule_id == "bilingual_abstract_consistency_check":
        left, right = facts.get("chinese_abstract"), facts.get("english_abstract")
        if not left or not right:
            return None
        return (
            "比较同一学位论文的中文摘要和英文摘要，逐项核对研究对象、方法、数据/实验条件、主要结果和结论是否对应。"
            "必须双向覆盖：任一摘要包含另一摘要没有的核心研究信息，属于信息缺失型不一致，即使两者没有直接矛盾。"
            "不要求逐字翻译，也不要把纯语言润色、背景或同义改写判为不一致。请用简体中文填写 summary 和 mismatches。"
            "仅返回 JSON，键为：outcome (consistent|inconsistent|inconclusive), summary, mismatches (array of objects; "
            "each object has category, chinese_claim, english_claim, mismatch_type (missing_in_chinese|missing_in_english|conflict), reason)。\n"
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


def _abstract_sentences(text: str) -> list[str]:
    normalized = _model_piece(text)
    sentences = re.split(r"(?<=[。！？；.!?])\s*", normalized)
    return [sentence.strip() for sentence in sentences
            if 20 <= len(_compact_claim(sentence)) <= 500]


def _abstract_atomic_claims(text: str) -> list[str]:
    """Split compound abstract sentences into independently checkable facts."""
    claims = []
    for sentence in _abstract_sentences(text):
        parts = re.split(r"[，；;,]", sentence)
        usable = [part.strip() for part in parts if len(_compact_claim(part)) >= 16]
        claims.extend(usable if len(usable) > 1 else [sentence])
    return list(dict.fromkeys(claims))


def abstract_sentence_coverage_prompt(source_language: str, claims: list[str],
                                      target_language: str, target_text: str) -> str:
    """Align complete source sentences to complete target sentences."""
    mismatch_type = "missing_in_english" if source_language == "中文" else "missing_in_chinese"
    target_sentences = _abstract_sentences(target_text)
    return (
        f"你正在进行中英文摘要的句子级语义对齐。逐句判断每个{source_language}摘要句子是否能在"
        f"{target_language}摘要中找到语义对应句或对应句组。必须考虑一对多、多对一、拆句、合句和"
        "自然翻译，不要求逐字对应。只有当源句中的核心研究对象、方法、条件、结果或结论在目标摘要"
        "中确实缺失，才标记 missing；若核心含义相反才标记 conflict。对包含逗号、分号或 and/while"
        "连接多个分句的句子，必须分别检查每个因果、条件、限制和结果分句；目标句只保留前半句或"
        "只保留同一主题的笼统表述时，不能算作完整对应。不要因为缩写未展开、措辞更"
        "具体、背景细节或语序不同而报告问题。\n"
        "仅返回需要关注的 missing/conflict 项，不要返回 aligned/uncertain 项。\n"
        "仅返回 JSON：{\"alignments\":[{\"source_id\":1,\"status\":\"missing|conflict\","
        "\"source_sentence\":\"逐字复制源句\",\"target_ids\":[1],"
        "\"target_sentence\":\"目标对应句；没有则为空\",\"reason\":\"简短依据\"}]}。\n"
        f"若 status 为 missing，则 mismatch_type 为 {mismatch_type}。\n"
        f"{source_language}摘要句子：\n" + json.dumps(
            [{"id": index + 1, "text": claim} for index, claim in enumerate(claims)],
            ensure_ascii=False) + "\n\n" +
        f"{target_language}摘要句子：\n" + json.dumps(
            [{"id": index + 1, "text": sentence} for index, sentence in enumerate(target_sentences)],
            ensure_ascii=False)
    )


def _compact_claim(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).replace("-", "").lower()


def _sentence_coverage_mismatches(payload: Any, *, claims: list[str],
                                  mismatch_type: str) -> list[dict[str, Any]]:
    """Keep only exact, source-backed sentence-level mismatches."""
    rows = payload.get("alignments") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return []
    source_field = "chinese_claim" if mismatch_type == "missing_in_english" else "english_claim"
    target_field = "english_claim" if mismatch_type == "missing_in_english" else "chinese_claim"
    accepted = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or str(row.get("status") or "").lower() not in {"missing", "conflict"}:
            continue
        claim_id = row.get("source_id")
        if not isinstance(claim_id, int) or not 1 <= claim_id <= len(claims):
            continue
        expected = claims[claim_id - 1]
        claim = str(row.get("source_sentence") or "").strip()
        compact = _compact_claim(claim)
        if len(compact) < 8 or compact not in _compact_claim(expected):
            continue
        # Some model responses have historically used status=missing while their
        # own explanation explicitly says the two formulations are equivalent.
        # Never turn that internally contradictory output into a user warning.
        reason = str(row.get("reason") or "")
        if any(marker in reason for marker in (
                "语义等价", "语义相当", "语义一致", "已表达", "已包含", "已涵盖", "对应表述")):
            continue
        if "不构成缺失" in reason:
            continue
        # A bilingual abstract may legitimately compress an expansion, acronym,
        # scope qualifier or implementation detail.  Those are not the
        # information-omission failures this rule reports.  Keep only an explicit
        # absence of a material proposition; the model's own explanation is the
        # conservative signal used for this distinction.
        key = (mismatch_type, compact)
        if key in seen:
            continue
        seen.add(key)
        accepted.append({
            "category": str(row.get("category") or "other"),
            source_field: claim,
            target_field: "",
            "mismatch_type": "conflict" if str(row.get("status") or "").lower() == "conflict" else mismatch_type,
            "reason": reason or "目标摘要缺少该核心信息。",
        })
    return accepted


def _abstract_directional_coverage(source_language: str, source_text: str,
                                   target_language: str, target_text: str,
                                   mismatch_type: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    claims = _abstract_sentences(source_text)
    findings: list[dict[str, Any]] = []
    usage_total = {"input_tokens": 0, "output_tokens": 0}
    if not claims:
        return findings, usage_total
    audit, usage = request_json([{"role": "user", "content": abstract_sentence_coverage_prompt(
        source_language, claims, target_language, target_text)}])
    usage_total["input_tokens"] += usage["input_tokens"]
    usage_total["output_tokens"] += usage["output_tokens"]
    findings.extend(_sentence_coverage_mismatches(
        audit, claims=claims, mismatch_type=mismatch_type))
    return findings, usage_total


def _abstract_mismatch_summary(payload: dict[str, Any], omissions: list[dict[str, Any]]) -> str:
    base = _chinese_summary(payload.get("summary"), True)
    directions = []
    if any(row.get("mismatch_type") == "missing_in_english" for row in omissions):
        directions.append("英文摘要缺少中文摘要中的核心信息")
    if any(row.get("mismatch_type") == "missing_in_chinese" for row in omissions):
        directions.append("中文摘要缺少英文摘要中的核心信息")
    if not directions:
        return base
    return base.rstrip("。") + "。另经双向覆盖核验发现：" + "；".join(directions) + "。"




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
    return """角色

你是一名中文学术论文错别字检测器，不是论文润色助手，也不是语法修改助手。

你的唯一任务是识别输入文本中具有明确证据的中文错别字，并提出最小必要修改。

# 检测范围

仅允许报告以下错误：

1. 音近或同音字误用，例如“在接在厉”中的“接”。
2. 字形相近造成的错误，例如“未”与“末”误用。
3. 常见固定词语、成语中明显的用字错误，例如“按步就班”中的“步”。

# 严格禁止

以下情况一律不得报告：

- 语句不通顺、语法不规范、措辞不佳。
- 风格润色、学术表达优化、语义改写。
- 专业术语、算法名称、英文缩写、变量名称及公式符号。
- 合法的不同表达方式、同义词替换。
- 需要跨段落推理才能确定的问题。
- 仅凭语言习惯认为某个词“更常用”的情况。
- 无法在原文中精确定位的错误。

# 判断规则

1. 必须先判断原文是否确实存在错别字，再考虑如何修改。
2. 必须能够说明原字为什么不正确，而不只是解释新字为什么更常见。
3. 修改应当以单字替换为主，不得整句重写。
4. 如果原文表达本身成立，不得报告。
5. 如果两种用字均可能合理，不得报告。
6. 如果不能明确判断，直接忽略该候选。
7. 原文完全正确时，必须返回空数组，禁止为了完成任务而制造错误。

# 输出格式

仅输出 JSON：

{"errors":[{"original":"错误原字","corrected":"修改后字","context":"包含错误字的原文片段","reason":"指出具体的用字错误依据"}]}

没有明确错别字时，输出：

{"errors":[]}

只检查以下指定的目标段落。其他上下文仅用于理解，不得从上下文中提取告警。

目标段落：
""" + text


def typo_verification_prompt(*, original: str, corrected: str, context: str,
                             reason: str) -> str:
    """Independently confirm one model-produced typo candidate.

    Discovery is deliberately permissive enough to find a candidate in a short
    academic-text chunk.  This second, isolated decision is deliberately
    conservative: it is an acceptance gate, never a source of new findings.
    """
    return f'''角色

你是中文学术论文错别字候选复核器。你不是润色助手；只能确认或否决给定候选，绝不能提出新候选。

仅当以下条件全部满足时 accepted 才能为 true：
1. 原字确实出现在目标段落的给定上下文中；
2. 原字属于明确的音近、同音、形近误用，或固定词语中的明显用字错误；
3. corrected 是对该原字的单字最小替换；
4. 原文用字不成立，而不是仅仅存在更常见的表达。

专业术语、算法名称、英文缩写、变量、公式、标点、空格、大小写、排版、语法或措辞问题一律否决。只要存在合理歧义或无法证明，accepted 必须为 false。

仅输出 JSON：
{{"accepted":true,"reason":"简短说明原字为何明确错误"}}
或
{{"accepted":false,"reason":"简短说明为何不能确认"}}

目标段落：{context}
候选原字：{original}
候选修改：{corrected}
候选理由：{reason}
'''


def typo_field_repair_prompt(*, original: str, corrected: str, context: str,
                             reason: str) -> str:
    """Repair only malformed fields from an already surfaced model candidate."""
    return f'''角色

你是中文学术论文错别字候选字段复核器。第一阶段已经在下列目标段落中提出一个候选，但可能把错误字和修改后字填错。你只能核对这一条候选，不能从段落中寻找或新增其他错误。

“第一阶段原字字段”和“第一阶段修改字段”是不可信的元数据，绝不能因为它们相同或错误就沿用、否决或限制实际的单字定位。必须以目标段落和候选理由为准：若理由明确指出“某字应为某字”，且该替换能在目标段落中精确验证，就返回那一对实际汉字。

仅当候选理由能够在目标段落中明确证明存在唯一的、单个汉字替换时，返回 accepted=true，并给出原文中实际错误字 original 与修改后字 corrected。若原文正确、存在歧义、不能精确定位，或候选理由不足，必须返回 accepted=false。

不得修改标点、空格、大小写、排版、英文、专业术语、变量、公式或整句措辞。original 与 corrected 必须是不同的单个汉字，且 original 必须在目标段落中出现。

仅输出 JSON：
{{"accepted":true,"original":"错误原字","corrected":"修改后字","reason":"明确的单字误用依据"}}
或
{{"accepted":false,"reason":"不能确认的原因"}}

目标段落：{context}
第一阶段原字字段：{original}
第一阶段修改字段：{corrected}
第一阶段理由：{reason}
'''


def _single_cjk_replacement(original: str, corrected: str) -> tuple[str, str] | None:
    """Reduce a model's word-level rendering to its one actual CJK substitution.

    The public result is still always a one-character correction.  Some models
    return ``布署 -> 部署`` despite being instructed to name the erroneous
    character.  That is safe to accept only when the two returned surfaces have
    identical length and exactly one Chinese character differs; phrase rewrites
    and insertions/deletions remain rejected.
    """
    if (not original or not corrected or len(original) != len(corrected)
            or len(original) > 24):
        return None
    changes = [(before, after) for before, after in zip(original, corrected)
               if before != after]
    if len(changes) != 1:
        return None
    before, after = changes[0]
    if not (_is_cjk(before) and _is_cjk(after)):
        return None
    return before, after


def run_typo_rule_from_ir(ir: dict[str, Any]) -> dict[str, Any]:
    findings = []
    # The same Paper Model source span can be surfaced through more than one
    # layout node.  Never turn that extraction detail into duplicate findings.
    seen_findings: set[tuple[Any, ...]] = set()
    usage_total = {"input_tokens": 0, "output_tokens": 0}
    # A typo is decided from its sentence-level lexical context.  A 1200-char
    # technical aggregate diluted clear candidates (for example “分祈”) during
    # a full-paper run even though the same paragraph was detected in isolation.
    # _body_chunks still prefers punctuation, so this is not a blind character
    # split across a sentence.
    chunks = _body_chunks(ir, size=1200)
    failure = None
    workers = 8 if all(os.environ.get(name, '').strip() for name in
                       ('SJTU_API_KEY', 'SJTU_API_BASE_URL', 'SJTU_API_MODEL')) else 4
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(request_json, [{"role": "user", "content": typo_prompt(chunk["model_text"])}]) for chunk in chunks]
        for index, chunk in enumerate(chunks):
            try:
                payload, usage = futures[index].result()
            except Exception as exc:
                # A transient API/cache failure must not discard findings from
                # other completed chunks.  Continue collecting them, but retain
                # the failed chunk in the run status for a retryable result.
                failure = failure or (str(exc)[:300] or type(exc).__name__)
                continue
            usage_total["input_tokens"] += usage["input_tokens"]
            usage_total["output_tokens"] += usage["output_tokens"]
            rows = payload.get("errors") if isinstance(payload, dict) else []
            if not isinstance(rows, list):
                rows = []
            for row in rows[:20]:
                if not isinstance(row, dict):
                    continue
                raw_original = str(row.get("original") or "").strip()
                raw_suggestion = str(row.get("corrected") or "").strip()
                context = _model_piece(str(row.get("context") or ""))
                replacement = _single_cjk_replacement(raw_original, raw_suggestion)
                # The public contract deliberately emits only one explicit
                # Chinese-character replacement.  A model may describe it as a
                # short word pair (e.g. 布署→部署), which we reduce only if it
                # contains exactly one same-length CJK substitution.
                if not context:
                    continue
                repaired_reason = None
                if not replacement:
                    # The discovery model sometimes identifies the right word
                    # in its explanation but repeats the same character in both
                    # JSON fields (e.g. 表→表 while explaining 名→明).  A
                    # separate constrained call may repair only those fields;
                    # it cannot create a candidate outside this exact context.
                    try:
                        repaired, repaired_usage = request_json([{
                            "role": "user",
                            "content": typo_field_repair_prompt(
                                original=raw_original,
                                corrected=raw_suggestion,
                                context=context,
                                reason=str(row.get("reason") or ""),
                            ),
                        }])
                    except Exception as exc:
                        failure = failure or (str(exc)[:300] or type(exc).__name__)
                        continue
                    usage_total["input_tokens"] += repaired_usage["input_tokens"]
                    usage_total["output_tokens"] += repaired_usage["output_tokens"]
                    if not isinstance(repaired, dict) or repaired.get("accepted") is not True:
                        continue
                    replacement = _single_cjk_replacement(
                        str(repaired.get("original") or "").strip(),
                        str(repaired.get("corrected") or "").strip(),
                    )
                    repaired_reason = str(repaired.get("reason") or "")
                if not replacement:
                    continue
                original, suggestion = replacement
                if original not in context:
                    continue
                surface_normalize = lambda value: re.sub(r"[^\w\u3400-\u9fff]", "", value.casefold())
                if surface_normalize(original) == surface_normalize(suggestion):
                    continue
                # English-looking identifiers and mathematical symbols are common in papers.
                # They are not spelling candidates even when the model proposes a plausible replacement.
                if _looks_like_code_or_math(original) or _looks_like_code_or_math(suggestion):
                    continue
                model_text = chunk.get("model_text", "")
                context_start = model_text.find(context)
                if context_start < 0:
                    continue
                match_start = context_start + context.find(original)
                if match_start < 0:
                    continue
                match_end = match_start + len(original)
                if _looks_like_code_context(model_text, match_start, match_end):
                    continue
                # Do not trust a discovery response by itself.  The verifier
                # sees only the candidate and its exact local source context;
                # it can veto a plausible-looking but unsupported correction,
                # while never manufacturing a new typo.
                try:
                    verification, verification_usage = request_json([{
                        "role": "user",
                        "content": typo_verification_prompt(
                            original=original,
                            corrected=suggestion,
                            context=context,
                            reason=repaired_reason or str(row.get("reason") or ""),
                        ),
                    }])
                except Exception as exc:
                    failure = failure or (str(exc)[:300] or type(exc).__name__)
                    continue
                usage_total["input_tokens"] += verification_usage["input_tokens"]
                usage_total["output_tokens"] += verification_usage["output_tokens"]
                if not isinstance(verification, dict) or verification.get("accepted") is not True:
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
                # Use the concrete source rectangles where available.  A text
                # key alone is insufficient: the same legitimate correction
                # may occur at distinct places in a paper.
                rect_key = tuple((rect["page_number"], round(rect["x1"], 1),
                                  round(rect["y1"], 1), round(rect["x2"], 1),
                                  round(rect["y2"], 1)) for rect in rects)
                finding_key = (surface_normalize(original),
                               surface_normalize(suggestion), rect_key or
                               (pages[0] if pages else None, match_start))
                if finding_key in seen_findings:
                    continue
                seen_findings.add(finding_key)
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
                                  "provider": "repo-paper-model", "quote": context[:120]}],
                    "reason": (repaired_reason or str(row.get("reason") or ""))[:300],
                })
    return {"rule_run_id": f"run_{TYPO_RULE}", "rule_id": TYPO_RULE, "severity": "warning",
            "params": {"chunk_count": len(chunks), "chunk_size": 1200,
                       **({"technical_failure": failure} if failure else {})},
            "execution_status": "error" if failure else "completed", "evidence_mode": "derived",
            "outcome": "inconclusive" if failure else ("issues_found" if findings else "passed"),
            "message": (f"错别字分块检测未完成：{public_failure_message(failure)}" if failure else None),
            "findings": findings, "model_usage": usage_total}

def run_numeric_consistency_rule(ir: dict[str, Any], run_id=None) -> dict[str, Any]:
    from numeric_consistency import run_numeric
    from numeric_run_trace import NumericRunTrace
    from numeric_navigation import attach_navigation
    source = next((a.get('path') for a in ir.get('source_artifacts', []) if a.get('kind') == 'pdf'), None)
    if source and Path(source).is_file():
        attach_navigation(source, ir)
    trace = NumericRunTrace(ir, task_id=run_id)
    result = run_numeric(ir, extract_bilingual_facts(ir), lambda messages: trace.call(request_json, messages), trace=trace)
    return trace.finish(result)

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
    """Ignore a candidate only when *itself* occurs in code-like syntax.

    A former 200-character window rejected ordinary Chinese prose whenever an
    unrelated identifier appeared later in the same technical paragraph (for
    example ``FPGA`` or ``PU3`` near ``布署``).  That was a false-negative
    filter, not protection against a code token.  Code syntax must therefore be
    local to the candidate.
    """
    window = text[max(0, start - 12):min(len(text), end + 12)]
    patterns = (
        r"\x60",
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


def _run_semantic_rule(ir, facts, rule_id, run_id=None):
    if rule_id == TYPO_RULE:
        return run_typo_rule_from_ir(ir)
    if rule_id == NUMERIC_RULE:
        return run_numeric_consistency_rule(ir, run_id=run_id)
    prompt = prompt_for(rule_id, facts)
    if prompt is None:
        return {
            "rule_run_id": f"run_{rule_id}",
            "rule_id": rule_id,
            "severity": "warning",
            "params": None,
            "execution_status": "completed",
            "evidence_mode": "derived",
            "outcome": "inconclusive",
            "message": "未能从 Paper Model 中同时识别中英文摘要或关键词。",
            "findings": [],
        }
    payload, usage = request_json([{"role": "user", "content": prompt}])
    params = None
    if rule_id == "bilingual_abstract_consistency_check":
        chinese = str(facts.get("chinese_abstract") or "")
        english = str(facts.get("english_abstract") or "")
        directional = []
        if chinese and english:
            for source_language, source, target_language, target, mismatch_type in (
                ("中文", chinese, "英文", english, "missing_in_english"),
                ("英文", english, "中文", chinese, "missing_in_chinese"),
            ):
                audited, audit_usage = _abstract_directional_coverage(
                    source_language, source, target_language, target, mismatch_type)
                usage["input_tokens"] += audit_usage["input_tokens"]
                usage["output_tokens"] += audit_usage["output_tokens"]
                directional.extend(audited)
        primary = payload.get("mismatches") if isinstance(payload.get("mismatches"), list) else []
        # Preserve model-reported mismatches, then supplement them with the
        # sentence-alignment pass.  The previous implementation discarded all
        # model omission rows, which made the final result depend on the audit
        # helper rather than the declared output schema.
        primary = [row for row in primary if isinstance(row, dict)
                   and str(row.get("mismatch_type") or "") in {
                       "missing_in_chinese", "missing_in_english", "conflict"}]
        primary = [row for row in primary
                   if not any(marker in str(row.get("reason") or "")
                              for marker in ("不构成缺失", "语义等价", "语义一致"))]
        merged = []
        seen = set()
        for row in [*primary, *directional]:
            key = (str(row.get("mismatch_type") or ""),
                   _compact_claim(row.get("chinese_claim") or row.get("english_claim") or
                                  row.get("source_sentence") or row.get("source_claim")))
            if key in seen:
                continue
            seen.add(key)
            merged.append(row)
        params = {"comparison_mode": "sentence_alignment_v3",
                  "mismatches": merged}
        if merged:
            payload = {**payload, "outcome": "inconsistent",
                       "summary": _abstract_mismatch_summary(payload, merged)}
        elif str(payload.get("outcome") or "").lower() == "inconsistent":
            payload = {**payload, "outcome": "consistent",
                       "summary": "未发现具有可追溯原文证据的摘要核心信息差异。"}
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
    return {
        "rule_run_id": f"run_{rule_id}",
        "rule_id": rule_id,
        "severity": "warning",
        "params": params,
        "execution_status": "completed",
        "evidence_mode": "derived",
        "outcome": "issues_found" if findings else (
            "inconclusive" if outcome == "inconclusive" else "passed"
        ),
        "message": str(payload.get("summary")) if outcome == "inconclusive" else None,
        "findings": findings,
        "model_usage": usage,
    }


def run(pdf: Path, rule_ids: list[str], run_id=None, on_rule_complete=None,
        allow_incomplete_structure=False) -> dict[str, Any]:
    ir = build_paper(pdf, include_citations=False,
                     allow_incomplete_structure=allow_incomplete_structure)
    facts = extract_bilingual_facts(ir) if any(rule in BILINGUAL_RULES for rule in rule_ids) else {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_run_semantic_rule, ir, facts, rule, run_id): index
                   for index, rule in enumerate(rule_ids)}
        runs = [None] * len(rule_ids)
        for future in as_completed(futures):
            try:
                completed = future.result()
            except Exception as error:
                rule_id = rule_ids[futures[future]]
                completed = {
                    'rule_id': rule_id, 'rule_run_id': f'run_{rule_id}', 'severity': 'warning',
                    'execution_status': 'error', 'evidence_mode': 'unsupported',
                    'outcome': 'inconclusive', 'findings': [],
                    'params': {'technical_failure': str(error)[:300]},
                    'message': public_failure_message(error),
                }
            runs[futures[future]] = completed
            if on_rule_complete:
                on_rule_complete(completed)
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
    unknown = [rule for rule in args.rule if rule not in BILINGUAL_RULES and rule not in {TYPO_RULE, NUMERIC_RULE}]
    if unknown:
        raise RuntimeError(f"未知双语语义规则：{unknown[0]}")
    def publish(completed):
        print(json.dumps({'type': 'paper_lint_rule_complete', 'rule_run': completed},
                         ensure_ascii=True), flush=True)
    result = run(args.pdf, args.rule, run_id=args.run_id,
                 on_rule_complete=publish if args.progress_jsonl else None,
                 allow_incomplete_structure=args.allow_incomplete_structure)
    print(json.dumps(result, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True))
        raise SystemExit(1)
