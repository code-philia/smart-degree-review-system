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
    for attempt in range(4):
        try:
            with opener.open(request, timeout=120) as response:
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
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    def walk(node_id: str) -> None:
        if node_id in seen: return
        seen.add(node_id)
        node = nodes.get(node_id)
        if not node: return
        if node.get("kind") == "Paragraph": ordered.append(node)
        for child in node.get("children", []) or []: walk(child)
    for child in (body or {}).get("children", []) or []: walk(child)
    if not ordered:
        ordered = [node for node in ir.get("nodes", [])
                   if node.get("kind") in {"Paragraph", "UnknownBlock"} and str(node.get("text") or "").strip()]
    chunks: list[dict[str, Any]] = []
    current: list[str] = []
    segments: list[dict[str, Any]] = []
    length = 0
    def flush() -> None:
        nonlocal current, segments, length
        if current:
            chunks.append({"text": "\n".join(current), "model_text": "\n".join(_normalize_for_model(x) for x in current), "segments": segments[:], "page": segments[0].get("page") if segments else None})
        current, segments, length = [], [], 0
    for node in ordered:
        raw = str(node.get("text") or "").strip()
        if not raw: continue
        provenance = node.get("provenance") or []
        source = next((item for item in provenance if isinstance(item.get("page_index"), int)), {})
        page = int(source["page_index"]) + 1 if isinstance(source.get("page_index"), int) else None
        bbox = source.get("bbox") if isinstance(source.get("bbox"), list) else None
        for piece in _split_piece(raw, size):
            if length and length + len(piece) + 1 > size: flush()
            current.append(piece)
            segments.append({"text": piece, "page": page, "bbox": bbox})
            length += len(piece) + 1
    flush()
    return chunks[:80]


def typo_prompt(text: str) -> str:
    return (
        "你是学位论文校对助手。只检查下面正文中明确可判断的中文错别字或明显的英文拼写错误。"
        "不要修改专业术语、作者名、缩写、公式、数字、引用、专有名词，也不要把 PDF 跨行连字符"
        "（如 \"re-\nverse\"）当作拼写错误。PDF 提取可能在中文词内插入空格（如“剔 除”），这不是错别字，必须忽略。无法确定时不要报告。请用简体中文返回严格 JSON："
        "{\"findings\":[{\"text\":\"原文短语\",\"suggestion\":\"建议文字\","
        "\"reason\":\"简短理由\"}]}。原文如下：\n" + text
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
            suggestion = str(row.get("suggestion") or "请结合上下文核对").strip()
            if _normalize_for_model(original) == _normalize_for_model(suggestion):
                continue
            segment = next((item for item in chunk.get("segments", [])
                            if _normalize_for_model(original) in _normalize_for_model(item.get("text", ""))), None)
            location = None
            if segment and segment.get("page"):
                if segment.get("bbox") and len(segment["bbox"]) == 4:
                    x1, y1, x2, y2 = [float(value) for value in segment["bbox"]]
                    rect = {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "width": x2 - x1, "height": y2 - y1, "page_number": segment["page"]}
                    location = {"type": "pdf_bbox", "page_number": segment["page"], "bounding_rect": rect, "rects": [rect], "text_excerpt": original[:120]}
                else:
                    location = {"type": "pdf_page", "page_number": segment["page"], "text_excerpt": original[:120]}
            findings.append({
                "finding_id": f"{TYPO_RULE}_{len(findings) + 1}", "rule_id": TYPO_RULE,
                "message": f"疑似错别字：{original[:120]}",
                "suggestion": suggestion[:300],
                "location": location,
                "anchors": [],
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
