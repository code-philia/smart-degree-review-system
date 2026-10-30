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
_KEYWORDS = re.compile(r"^\s*(关键词|关键字|key\s*words?|keywords?)\s*[:：]\s*(.*)$", re.I)
_SEPARATOR = re.compile(r"\s*(?:[,，;；、]|\s+and\s+)\s*", re.I)


def _keyword_match_values(values: list[str]) -> list[str]:
    """Return values unchanged when no line-boundary metadata is available."""
    return [str(value) for value in values]


def _join_wrapped_keyword_lines(parts: list[str], *, remove_wrap_hyphen: bool = False) -> str:
    """Join PDF keyword lines, optionally normalizing only wrap hyphens."""
    if not parts:
        return ""
    combined = parts[0].strip()
    for part in parts[1:]:
        next_part = part.strip()
        if not next_part:
            continue
        if re.search(r"[A-Za-z]-$", combined) and re.match(r"^[A-Za-z]", next_part):
            combined = (combined[:-1] if remove_wrap_hyphen else combined) + next_part
        elif _CJK.search(combined[-1:]) and _CJK.match(next_part):
            combined += next_part
        else:
            combined += " " + next_part
    return combined


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


def _keyword_layout_lines(lines):
    """Rejoin source fragments on a keyword row in physical reading order."""
    replacements, consumed = {}, set()
    for index, line in enumerate(lines):
        if not _KEYWORDS.match(str(line.get("text", "")).strip()) or not line.get("bbox"):
            continue
        x1, y1, _x2, y2 = line["bbox"]
        members = []
        for other_index, other in enumerate(lines):
            box = other.get("bbox")
            if not box or box[0] < x1:
                continue
            if other_index != index and _KEYWORDS.match(str(other.get("text", "")).strip()):
                continue
            overlap = min(y2, box[3]) - max(y1, box[1])
            if overlap >= max(1, min(y2 - y1, box[3] - box[1]) * .5):
                members.append((other_index, other))
        members.sort(key=lambda item: item[1]["bbox"][0])
        if len(members) < 2:
            continue
        text, right, joined = "", x1, []
        for other_index, other in members:
            if other["bbox"][0] < right - .5:
                continue
            part = str(other.get("text", "")).strip()
            if text and part and text[-1].isalnum() and part[0].isalnum():
                text += " "
            text += part
            right = other["bbox"][2]
            joined.append(other_index)
        first = min(joined)
        replacements[first] = {**line, "text": text,
                               "bbox": [x1, min(lines[i]["bbox"][1] for i in joined),
                                        right, max(lines[i]["bbox"][3] for i in joined)]}
        consumed.update(joined)
    return [replacements[i] if i in replacements else line
            for i, line in enumerate(lines) if i in replacements or i not in consumed]


def _overlapping_keyword_fragment(previous_bbox, current_bbox, previous_text, current_text):
    """Ignore a stray text layer overlapping a wrapped keyword line.

    Some PDFs contain a short duplicated/overlaid text span between ``Re-`` and
    the next physical line. It must not become part of the keyword value.
    Restrict this heuristic to an ASCII token, a preceding hyphen, and clear
    vertical overlap with the preceding line so normal hyphenated keywords are
    preserved.
    """
    if not (previous_bbox and current_bbox and previous_text.rstrip().endswith("-")):
        return False
    if not re.fullmatch(r"[A-Za-z]{2,16}", current_text.strip()):
        return False
    px1, py1, px2, py2 = map(float, previous_bbox)
    cx1, cy1, cx2, cy2 = map(float, current_bbox)
    overlap = min(py2, cy2) - max(py1, cy1)
    height = min(py2 - py1, cy2 - cy1)
    return overlap >= max(1.0, height * 0.5) and cx2 <= px1 + 12


def extract_bilingual_facts(ir):
    nodes = ir.get("nodes", [])
    by_id = {node.get("id"): node for node in nodes if node.get("id")}
    # Native layout is authoritative: paragraph nodes can contain only the first
    # keyword row, or can still belong to a front-matter section after its end.
    flat = [(page, line) for page in ir.get("layout", {}).get("pages", [])
            for line in _keyword_layout_lines(page.get("lines", []))
            if str(line.get("text", "")).strip()]

    def compact(text):
        return re.sub(r"\s+", "", text).casefold()

    def text_at(index):
        return str(flat[index][1].get("text", "")).strip()

    def locator(text):
        return bool(re.fullmatch(r"(?:[-—–]\s*)?(?:第\s*)?[ivxlcdm\d]+(?:\s*页)?(?:\s*[-—–])?",
                                 text.strip(), re.I))

    def metadata(text):
        return bool(re.match(r"^(?:中图分类号|分类号|CLC\s*code|UDC)\s*[:：]", text, re.I))

    def section_boundary(text, index=None, previous_body=None):
        value = compact(text)
        numbered = False
        if index and previous_body is not None and re.fullmatch(r"\d+(?:\.\d+)*\s+\S.{0,65}", text):
            box = flat[index][1].get("bbox")
            previous_box = flat[previous_body][1].get("bbox")
            numbered = bool(box and previous_box and box[3] - box[1] >
                            (previous_box[3] - previous_box[1]) * 1.2)
        return (value in {"目录", "目次", "contents", "tableofcontents", "摘要", "abstract"}
                or metadata(text) or numbered
                or bool(re.match(r"^(?:第[一二三四五六七八九十百\d]+章|chapter\s+\d+)",
                                 text, re.I)))

    def location(index):
        page, _line = flat[index]
        return {"page_number": int(page.get("page_index", 0)) + 1,
                "text_excerpt": text_at(index)[:500]}

    keywords = []
    keyword_locations = {}
    for index, (page, line) in enumerate(flat):
        match = _KEYWORDS.match(text_at(index))
        if not match:
            continue
        parts = [match.group(2)]
        previous = line
        for following_page, following_line in flat[index + 1:]:
            following = str(following_line.get("text", "")).strip()
            if following_page.get("page_index") != page.get("page_index"):
                break
            if _overlapping_keyword_fragment(previous.get("bbox"), following_line.get("bbox"),
                                             str(previous.get("text", "")), following):
                continue
            if locator(following) or _KEYWORDS.match(following) or section_boundary(following):
                break
            previous_box, box = previous.get("bbox"), following_line.get("bbox")
            if previous_box and box:
                line_height = max(previous_box[3] - previous_box[1], box[3] - box[1], 1)
                # A continuation is the next physical text row, not arbitrary
                # subsequent text elsewhere on the page.
                gap = box[1] - previous_box[3]
                if gap < -line_height * .5 or gap > line_height * 1.5:
                    break
            parts.append(following)
            previous = following_line
        combined = _join_wrapped_keyword_lines(parts)
        match_combined = _join_wrapped_keyword_lines(parts, remove_wrap_hyphen=True)
        values = [item.strip() for item in _SEPARATOR.split(combined) if item.strip()]
        if not values:
            continue
        item = {"label": match.group(1), "values": values,
                "match_values": [item.strip() for item in _SEPARATOR.split(match_combined) if item.strip()],
                "text": combined}
        keywords.append(item)
        keyword_locations[id(item)] = location(index)

    if not flat:
        for node in nodes:
            for part in str(node.get("text") or "").splitlines():
                match = _KEYWORDS.match(part)
                if match:
                    values = [value.strip() for value in _SEPARATOR.split(match.group(2)) if value.strip()]
                    if values:
                        keywords.append({"label": match.group(1), "values": values,
                                         "match_values": _keyword_match_values(values), "text": part})

    ignored_ids = {source.get("line_id") for node in nodes
                   if node.get("attrs", {}).get("role") in {"running_header", "running_footer", "page_number"}
                   for source in node.get("provenance", [])}
    top_rows = {}
    top_sizes = {}
    for page, line in flat:
        box = line.get("bbox")
        if box and box[1] < float(page.get("height") or 840) * .13:
            value = compact(str(line.get("text", "")))
            top_rows.setdefault(value, set()).add(page.get("page_index"))
            top_sizes.setdefault(value, []).append(float(line.get("font_size") or box[3] - box[1]))

    def noise(index):
        page, line = flat[index]
        if line.get("id") in ignored_ids or locator(text_at(index)):
            return True
        box = line.get("bbox")
        return bool(box and box[1] < float(page.get("height") or 840) * .13
                    and len(top_rows.get(compact(text_at(index)), set())) > 1)

    def heading_end(index, label):
        value = compact(text_at(index))
        end = index
        if value != label:
            if not (label == "摘要" and value == "摘" and index + 1 < len(flat)
                    and compact(text_at(index + 1)) == "要"
                    and flat[index + 1][0].get("page_index") == flat[index][0].get("page_index")):
                return None
            first_box, next_box = flat[index][1].get("bbox"), flat[index + 1][1].get("bbox")
            if first_box and next_box and abs(first_box[1] - next_box[1]) > max(first_box[3] - first_box[1], 1) * .5:
                return None
            end += 1
        # TOC labels may be exposed as exact titles with a separate page
        # locator on the same baseline. They are not content headings.
        box = flat[end][1].get("bbox")
        if box:
            for other_page, other in flat[end + 1:end + 4]:
                other_box = other.get("bbox")
                if other_page.get("page_index") != flat[index][0].get("page_index"):
                    break
                if (other_box and abs(other_box[1] - box[1]) <= max(box[3] - box[1], 1) * .5
                        and locator(str(other.get("text", "")))):
                    return None
        return end

    def section(label):
        candidates = []
        for start in range(len(flat)):
            end = heading_end(start, label)
            if end is None:
                continue
            if noise(start):
                line = flat[start][1]
                box = line.get("bbox")
                size = float(line.get("font_size") or (box[3] - box[1] if box else 0))
                # A real title can share its text and top-margin position with
                # smaller continuation headers. Retain its source typography.
                if size <= min(top_sizes.get(compact(text_at(start)), [size])):
                    continue
            body = []
            first_body = None
            previous_body = None
            matched_keywords = False
            cursor = end + 1
            while cursor < len(flat):
                text = text_at(cursor)
                keyword = _KEYWORDS.match(text)
                if keyword:
                    matched_keywords = bool(_CJK.search(keyword.group(1))) == (label == "摘要")
                    break
                repeated_heading = heading_end(cursor, label)
                if repeated_heading is not None:
                    cursor = repeated_heading + 1
                    continue
                if section_boundary(text, cursor, previous_body):
                    break
                if not noise(cursor):
                    body.append(text)
                    first_body = first_body or location(cursor)
                    previous_body = cursor
                cursor += 1
            if body:
                candidates.append((matched_keywords, "\n".join(body), first_body))
        if candidates:
            # A matching keyword terminator corroborates the actual abstract,
            # rather than a title mentioned elsewhere in the front matter.
            selected = next((item for item in candidates if item[0]), candidates[0])
            return selected[1], selected[2]
        if not flat:
            abstracts = [_node_text(node, by_id) for node in nodes if node.get("kind") == "Abstract"]
            return next((text for text in abstracts if text and bool(_CJK.search(text)) == (label == "摘要")), None), None
        return None, None

    chinese_abstract, chinese_abstract_location = section("摘要")
    english_abstract, english_abstract_location = section("abstract")
    chinese_keywords = next((item for item in keywords if _CJK.search(item["label"])), None)
    english_keywords = next((item for item in keywords if not _CJK.search(item["label"])), None)
    return {
        "model_version": ir.get("model_version"),
        "schema_version": ir.get("schema_version"),
        "chinese_abstract": chinese_abstract,
        "english_abstract": english_abstract,
        "chinese_keywords": chinese_keywords,
        "english_keywords": english_keywords,
        "locations": {
            "chinese_abstract": chinese_abstract_location,
            "english_abstract": english_abstract_location,
            "chinese_keywords": keyword_locations.get(id(chinese_keywords)),
            "english_keywords": keyword_locations.get(id(english_keywords)),
        },
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
            prompt = ("Match Chinese and English thesis keywords by meaning, not by count. English alphabetic hyphens may be caused by a PDF line wrap; ignore that presentation difference during semantic matching and do not call it a spelling error. Return JSON only with keys: outcome (consistent|inconsistent|inconclusive), summary, pairs (array of objects with chinese, english, match, reason), missing_chinese (array), missing_english (array).\nChinese keywords: " + json.dumps(left.get("match_values", left["values"]), ensure_ascii=False) + "\nEnglish keywords: " + json.dumps(right.get("match_values", right["values"]), ensure_ascii=False))
        payload = _json_object(await self._ainvoke([PromptMessage("human", prompt)]))
        outcome = str(payload.get("outcome", "inconclusive")).lower()
        if outcome == "inconclusive":
            return self._contracts["RuleRun"](rule_id=entry.rule_id, severity=entry.severity, params=entry.params, execution_status="completed", evidence_mode="derived", outcome="inconclusive", message=str(payload.get("summary") or "语义证据不足"), findings=[])
        if outcome != "inconsistent": return completed_from_findings(entry, findings=[], evidence_mode="derived")
        default_message = "中英文摘要在研究内容上存在语义不一致。" if self.rule_id.endswith("abstract_consistency_check") else "中英文关键词存在语义不对应。"
        default_suggestion = "请依据中文摘要核对英文摘要的研究对象、方法、数据、结果和结论。" if self.rule_id.endswith("abstract_consistency_check") else "请按语义逐项核对中文关键词与英文关键词，并补齐、删除或修正不对应项。"
        finding = self._contracts["Finding"](rule_id=entry.rule_id, message=str(payload.get("summary") or default_message), suggestion=default_suggestion, location=None, anchors=[])
        return completed_from_findings(entry, findings=[finding], evidence_mode="derived")
