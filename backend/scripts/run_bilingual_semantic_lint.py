"""Run bilingual semantic rules using the repository Paper Model and campus API."""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

from paper_model_bilingual_rules import extract_bilingual_facts, _json_object, _bounded_text
from paper_compiler.frontend import build_paper


BILINGUAL_RULES = {
    "bilingual_abstract_consistency_check",
    "bilingual_keywords_correspondence_check",
}


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
        with opener.open(request, timeout=120) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as error:
        detail = error.read(2000).decode("utf-8", "replace")
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
        "按语义而不是数量匹配中文和英文关键词。请用简体中文填写 summary、reason 和其它说明字段。"
        "仅返回 JSON，键为：outcome (consistent|inconsistent|inconclusive), "
        "summary, pairs (array of objects with chinese, english, match, reason), "
        "missing_chinese (array), missing_english (array)。\n"
        "中文关键词：" + json.dumps(left.get("values", []), ensure_ascii=False) +
        "\n英文关键词：" + json.dumps(right.get("values", []), ensure_ascii=False)
    )


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
    facts = extract_bilingual_facts(build_paper(pdf, include_citations=False))
    runs = []
    for rule_id in rule_ids:
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
            "completed_rule_count": len(runs),
            "unsupported_rule_count": 0,
            "error_rule_count": 0,
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
    unknown = [rule for rule in args.rule if rule not in BILINGUAL_RULES]
    if unknown:
        raise RuntimeError(f"未知双语语义规则：{unknown[0]}")
    print(json.dumps(run(args.pdf, args.rule), ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
