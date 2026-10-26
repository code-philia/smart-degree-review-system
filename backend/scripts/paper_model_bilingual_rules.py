"""Paper Model backed bilingual abstract and keyword semantic checks."""
from __future__ import annotations
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_compiler.frontend import build_paper

_CJK = re.compile(r"[\u3400-\u9fff]")
_KEYWORDS = re.compile(r"^\s*(关键词|关键字|key\s*words?|keywords?)\s*[:：]\s*(.+)$", re.I)
_SEPARATOR = re.compile(r"\s*(?:[,，;；、]|\s+and\s+)\s*", re.I)

@dataclass(frozen=True)
class PromptMessage:
    type: str
    content: str

def load_paper_model(pdf_path: Path) -> dict[str, Any]:
    return build_paper(pdf_path, include_citations=False)

def _node_text(node: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> str:
    parts = []
    for child_id in node.get("children", []):
        child = by_id.get(child_id)
        if not child: continue
        if child.get("kind") != "Heading" and child.get("text"): parts.append(str(child["text"]))
        parts.append(_node_text(child, by_id))
    return "\n".join(part for part in parts if part).strip()

def _line_rows(ir):
    return [str(line.get("text", "")).strip() for page in ir.get("layout", {}).get("pages", []) for line in page.get("lines", []) if str(line.get("text", "")).strip()]

def extract_bilingual_facts(ir):
    nodes = ir.get("nodes", [])
    by_id = {node.get("id"): node for node in nodes if node.get("id")}
    abstracts = [_node_text(node, by_id) for node in nodes if node.get("kind") == "Abstract" and _node_text(node, by_id)]
    keywords = []
    for line in [str(node.get("text") or "") for node in nodes] + _line_rows(ir):
        for part in line.splitlines():
            match = _KEYWORDS.match(part)
            if match:
                values = [item.strip() for item in _SEPARATOR.split(match.group(2)) if item.strip()]
                item = {"label": match.group(1), "values": values, "text": part}
                if item not in keywords: keywords.append(item)
    # Paper Model layout is authoritative even when a split heading (摘/要) leaves
    # the body as ordinary paragraphs. Stitch each abstract from native lines.
    flat = [(page.get("page_index", 0), str(line.get("text", "")).strip())
            for page in ir.get("layout", {}).get("pages", [])
            for line in page.get("lines", []) if str(line.get("text", "")).strip()]
    # Rejoin keyword lines split by PDF layout (e.g. Re- / verse).
    for i, (_, text) in enumerate(flat):
        match = _KEYWORDS.match(text)
        if not match:
            continue
        parts = [match.group(2)]
        for _, following in flat[i + 1:i + 9]:
            compact_following = re.sub(r"\s+", "", following)
            if re.fullmatch(r"[ivxlcdm]+", compact_following, re.I) or _KEYWORDS.match(following):
                break
            if compact_following in {"目录", "目次", "contents", "abstract"}:
                break
            parts.append(following)
        combined = " ".join(parts)
        values = [item.strip() for item in _SEPARATOR.split(combined) if item.strip()]
        candidate = {"label": match.group(1), "values": values, "text": combined}
        for index, existing in enumerate(keywords):
            if existing["label"].casefold() == candidate["label"].casefold():
                if len(candidate["text"]) > len(existing["text"]): keywords[index] = candidate
                break
        else:
            keywords.append(candidate)

    def section(label, stop):
        start = next((i for i, (_, text) in enumerate(flat)
                      if text.casefold() == label), None)
        if start is None and label == "摘要":
            start = next((i for i in range(len(flat)-1)
                          if flat[i][1] == "摘" and flat[i+1][1] == "要"), None)
        if start is None: return None
        body = []
        for _, text in flat[start + 1:]:
            compact = re.sub(r"\s+", "", text).casefold()
            if compact in stop: break
            if compact in {label, "摘 要", "abstract"}: continue
            body.append(text)
            if len(body) >= 180: break
        return "\n".join(body).strip() or None
    chinese_abstract = section("摘要", {"关键词", "关键字", "keywords", "keywords"})
    english_abstract = section("abstract", {"关键词", "关键字", "keywords", "keywords"})
    if not chinese_abstract:
        chinese_abstract = next((text for text in abstracts if _CJK.search(text)), None)
    if not english_abstract:
        english_abstract = next((text for text in abstracts if not _CJK.search(text) and re.search(r"[A-Za-z]", text)), None)
    return {
        "model_version": ir.get("model_version"),
        "schema_version": ir.get("schema_version"),
        "chinese_abstract": chinese_abstract,
        "english_abstract": english_abstract,
        "chinese_keywords": next((item for item in keywords if _CJK.search(item["label"])), None),
        "english_keywords": next((item for item in keywords if not _CJK.search(item["label"])), None),
    }

def _bounded_text(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    head = limit // 2
    return text[:head] + "\n...[middle omitted]...\n" + text[-head:]

def _json_object(content: str):
    """Decode one JSON object from an OpenAI-compatible model response.

    Some compatible gateways prepend a short instruction or wrap the object in
    Markdown even when ``response_format=json_object`` is requested. Keep the
    semantic rule contract strict (one object, no arrays or scalar values), but
    tolerate that transport envelope by scanning for the first complete object.
    """
    if not isinstance(content, str):
        raise ValueError("DeepSeek response must be JSON text")
    value = content.strip()
    decoder = json.JSONDecoder(parse_constant=lambda token: (_ for _ in ()).throw(
        ValueError(f"invalid JSON constant: {token}")))
    try:
        result = decoder.decode(value)
    except (json.JSONDecodeError, ValueError):
        result = None
        for index, char in enumerate(value):
            if char != "{":
                continue
            try:
                candidate, _ = decoder.raw_decode(value[index:])
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(candidate, dict):
                result = candidate
                break
    if not isinstance(result, dict):
        raise ValueError("DeepSeek response must contain one JSON object")
    return result

PAPER_MODEL_FACTS = None

def set_paper_model_facts(facts):
    global PAPER_MODEL_FACTS
    PAPER_MODEL_FACTS = facts

class PaperModelBilingualRule:
    default_severity = "warning"
    params_model = None
    def __init__(self, *, rule_id: str, ainvoke: Callable[[list[PromptMessage]], Awaitable[str]], contracts):
        self.rule_id, self._ainvoke, self._contracts = rule_id, ainvoke, contracts
    async def execute(self, context, entry):
        from novref.domain.paper_lint.rules.base import completed_from_findings, unsupported
        facts = PAPER_MODEL_FACTS
        if not facts: return unsupported(entry, message="paper_model_unavailable")
        if self.rule_id.endswith("abstract_consistency_check"):
            left, right = facts["chinese_abstract"], facts["english_abstract"]
            if not left or not right: return unsupported(entry, message="bilingual_abstracts_not_detected")
            prompt = ("Compare the Chinese and English abstracts of the same thesis. Judge research object, method, data, main results and conclusion. Do not require literal translation. Return JSON only with keys: outcome (consistent|inconsistent|inconclusive), summary, mismatches (array).\nChinese abstract:\n" + _bounded_text(left) + "\n\nEnglish abstract:\n" + _bounded_text(right))
        else:
            left, right = facts["chinese_keywords"], facts["english_keywords"]
            if not left or not right: return unsupported(entry, message="bilingual_keywords_not_detected")
            prompt = ("Match Chinese and English thesis keywords by meaning, not by count. Return JSON only with keys: outcome (consistent|inconsistent|inconclusive), summary, pairs (array of objects with chinese, english, match, reason), missing_chinese (array), missing_english (array).\nChinese keywords: " + json.dumps(left["values"], ensure_ascii=False) + "\nEnglish keywords: " + json.dumps(right["values"], ensure_ascii=False))
        payload = _json_object(await self._ainvoke([PromptMessage("human", prompt)]))
        outcome = str(payload.get("outcome", "inconclusive")).lower()
        if outcome == "inconclusive":
            return self._contracts["RuleRun"](rule_id=entry.rule_id, severity=entry.severity, params=entry.params, execution_status="completed", evidence_mode="derived", outcome="inconclusive", message=str(payload.get("summary") or "语义证据不足"), findings=[])
        if outcome != "inconsistent": return completed_from_findings(entry, findings=[], evidence_mode="derived")
        default_message = "中英文摘要在研究内容上存在语义不一致。" if self.rule_id.endswith("abstract_consistency_check") else "中英文关键词存在语义不对应。"
        default_suggestion = "请依据中文摘要核对英文摘要的研究对象、方法、数据、结果和结论。" if self.rule_id.endswith("abstract_consistency_check") else "请按语义逐项核对中文关键词与英文关键词，并补齐、删除或修正不对应项。"
        finding = self._contracts["Finding"](rule_id=entry.rule_id, message=str(payload.get("summary") or default_message), suggestion=default_suggestion, location=None, anchors=[])
        return completed_from_findings(entry, findings=[finding], evidence_mode="derived")
