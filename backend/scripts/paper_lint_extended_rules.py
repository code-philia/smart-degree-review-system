"""Additional deterministic PDF rules for the degree-review pilot.

The rules consume the review-pilot parser's extracted visible text; they offer
locatable, explainable checks and deliberately avoid claims beyond visible PDF facts.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from pydantic import BaseModel, Field

from novref.domain.paper_lint.context import PaperLintContext
from novref.domain.paper_lint.contracts import Finding, RuleRun
from novref.domain.paper_lint.pdf_location import location_from_lines
from novref.domain.paper_lint.pdf_raw import PdfLintTextLine
from novref.domain.paper_lint.rules.base import completed_from_findings, unsupported
from novref.domain.paper_lint.rules.executor import RuleExecutionEntry
from novref.domain.paper_lint.rules.heading_numbering_hierarchy_check import (
    _detect_numbered_heading_candidates,
)
from novref.domain.paper_lint.rules.toc_format_check import (
    _TOC_ENTRY_TRAILER_RE,
    _find_toc_snapshot,
)

_REFERENCE_HEADING = re.compile(r"^(参考文献|references|bibliography)$", re.I)
_REFERENCE_HEADING_PREFIX = re.compile(
    r"^(?:(?:参考文献|references|bibliography)\s*)+(?=\[\d+])", re.I
)
_NEXT_SECTION = re.compile(
    r"^(致谢|致\s*$|附录|学术论文和科研成果目录|攻读.*期间.*成果|个人简历|"
    r"acknowledg(e)?ments?|appendix|checklist|supplemental materials?)",
    re.I,
)
_APPENDIX_LETTER = re.compile(r"^[A-Z]$")
_REFERENCE_NUMBERED_START = re.compile(r"^\s*\[(?P<number>\d+)]\s*(?P<body>.*)$")
_REFERENCE_APA_START = re.compile(
    r"^\s*(?!\[\d+])(?=.{2,180}?\.\s*\((?:19|20)\d{2}[a-z]?\)\.?)",
    re.I,
)
_GBT_REFERENCE_PATTERNS = (
    re.compile(
        r"^\[\d+]\s*.+\[(?:J|M|D|C|N|P|R|S|Z|DB|CP|EB)"
        r"(?:/[A-Z]{1,3})?].*(?:19|20)\d{2}",
        re.I,
    ),
)
_APA7_REFERENCE_PATTERNS = (
    re.compile(
        r"^(?!\[\d+])[^()]{2,240}\((?:19|20)\d{2}[a-z]?\)\.?\s+.{2,}$",
        re.I,
    ),
)
_IEEE_REFERENCE_PATTERNS = (
    re.compile(
        r"^\[\d+]\s+.+?(?:[\"“][^\"”]+[\"”].*"
        r"|\b(?:vol\.|no\.|pp\.|proc\.|doi|\d+(?:st|nd|rd|th)\s+ed\.).*)"
        r"(?:19|20)\d{2}",
        re.I,
    ),
)
_REFERENCE_STYLE_LABELS = {
    "gbt": "GB/T 7714",
    "apa7": "APA 7",
    "ieee": "IEEE",
}
_CJK = re.compile(r"[\u4e00-\u9fff]")
_ASCII_PUNCTUATION = re.compile(r"[\u4e00-\u9fff][,;:!?][\u4e00-\u9fff]")
_FULLWIDTH_ALNUM = re.compile(r"[Ａ-Ｚａ-ｚ０-９]")
_KEYWORDS = re.compile(
    r"^\s*(关键词|关键字|key\s*words?|keywords?)\s*[:：]\s*(.+)$", re.I
)
_OBJECT = re.compile(
    r"^\s*(?P<kind>图|figure|fig\.?|表|table|公式|式|equation)\s*(?P<number>\d+)(?:\s*[-.]\s*(?P<section>\d+))?\b",
    re.I,
)
_CITATION = re.compile(r"\[(\d+(?:\s*[,，、-]\s*\d+)*)]")
_FOOTNOTE = re.compile(r"^(?:注|脚注)\s*(\d+)|^(\d+)\s*[）.)、]")
_OBJECT_NUMBER_PATTERN = (
    r"\d+(?:\s*[-.．]\s*\d+)*(?:\s*[（(][A-Za-z0-9]+[)）])?"
)
_OBJECT_PREFIX_PATTERNS = {
    "figure": re.compile(
        rf"^\s*(?:图|fig(?:ure)?\.?)\s*(?P<number>{_OBJECT_NUMBER_PATTERN})(?P<tail>.*)$",
        re.I,
    ),
    "table": re.compile(
        rf"^\s*(?:表|table)\s*(?P<number>{_OBJECT_NUMBER_PATTERN})(?P<tail>.*)$",
        re.I,
    ),
}
_OBJECT_REFERENCE_PATTERNS = {
    "figure": re.compile(
        rf"(?:图|fig(?:ure)?s?\.?)\s*(?P<number>{_OBJECT_NUMBER_PATTERN})",
        re.I,
    ),
    "table": re.compile(
        rf"(?:表|tables?)\s*(?P<number>{_OBJECT_NUMBER_PATTERN})",
        re.I,
    ),
}
_CAPTION_REFERENCE_STARTERS = {
    "figure": (
        "所示",
        "可知",
        "显示",
        "展示",
        "给出",
        "如下",
        "图中",
        "是",
        "为",
        "shows",
        "is shown",
        "is presented",
        "is depicted",
        "illustrates",
        "presents",
        "depicts",
    ),
    "table": (
        "所示",
        "可知",
        "显示",
        "列出",
        "给出",
        "如下",
        "表中",
        "是",
        "为",
        "shows",
        "is shown",
        "is presented",
        "lists",
        "presents",
        "reports",
    ),
}
_LIST_ENTRY_TRAILER = re.compile(
    r"(?:\.{3,}|…{2,}|⋯{2,}|·{3,})\s*(?:\d+|[ivxlcdm]+)\s*$",
    re.I,
)


class _Params(BaseModel):
    max_findings: int = Field(default=20, gt=0, le=200)


class _ReferenceParams(_Params):
    min_recognized_entries: int = Field(default=2, ge=1, le=20)
    min_style_share: float = Field(default=0.6, ge=0.5, le=1.0)


@dataclass(frozen=True, slots=True)
class _ReferenceEntry:
    text: str
    line: PdfLintTextLine


def _lines(context: PaperLintContext):
    return sorted(
        (line for line in context.raw.lines if line.text.strip()),
        key=lambda line: (
            line.page_number,
            line.bbox.y2,
            line.bbox.x1,
            line.bbox.y1,
            line.reading_order,
        ),
    )


def _finding(rule_id: str, line, message: str, suggestion: str) -> Finding:
    return Finding(
        rule_id=rule_id,
        message=message,
        suggestion=suggestion,
        location=location_from_lines([line], text_excerpt=line.text.strip()),
    )


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def _reference_section_entries(
    lines: list[PdfLintTextLine], start: int
) -> list[_ReferenceEntry]:
    entries: list[_ReferenceEntry] = []
    current_text: list[str] = []
    current_line = None

    def flush() -> None:
        nonlocal current_text, current_line
        if current_line is not None and current_text:
            entries.append(
                _ReferenceEntry(
                    text=" ".join(part for part in current_text if part).strip(),
                    line=current_line,
                )
            )
        current_text = []
        current_line = None

    for line_index, line in enumerate(lines[start + 1 :], start=start + 1):
        text = re.sub(r"\s+", " ", line.text.strip())
        if (
            line.bbox.y2 < line.bbox.height * 0.105
            or line.bbox.y1 > line.bbox.height * 0.9
        ):
            continue
        is_split_appendix_heading = False
        if _APPENDIX_LETTER.fullmatch(text):
            for following in lines[line_index + 1 : line_index + 4]:
                if following.page_number != line.page_number:
                    break
                following_text = re.sub(r"\s+", " ", following.text.strip())
                vertical_gap = following.bbox.y2 - line.bbox.y2
                looks_like_heading = (
                    abs(vertical_gap) <= 2
                    or (
                        0 < vertical_gap <= 40
                        and len(following_text) <= 120
                        and following_text.upper() == following_text
                    )
                )
                if looks_like_heading:
                    is_split_appendix_heading = bool(
                        len(following_text) >= 3
                        and not _REFERENCE_NUMBERED_START.match(following_text)
                        and not _REFERENCE_APA_START.match(following_text)
                    )
                    break
        if _NEXT_SECTION.match(text) or is_split_appendix_heading:
            break
        if _REFERENCE_HEADING.match(text):
            continue
        text = _REFERENCE_HEADING_PREFIX.sub("", text).strip()
        if not text or text.isdigit():
            continue
        is_start = bool(
            _REFERENCE_NUMBERED_START.match(text)
            or _REFERENCE_APA_START.match(text)
        )
        if is_start:
            flush()
        if current_line is None:
            current_line = line
        current_text.append(text)
    flush()
    return entries


def _reference_style(text: str) -> str | None:
    normalized = re.sub(r"\s+", " ", text).strip()[:4000]
    profiles = (
        ("gbt", _GBT_REFERENCE_PATTERNS),
        ("apa7", _APA7_REFERENCE_PATTERNS),
        ("ieee", _IEEE_REFERENCE_PATTERNS),
    )
    for style, patterns in profiles:
        if any(pattern.search(normalized) for pattern in patterns):
            return style
    return None


def _dominant_reference_style(
    styles: list[str | None], params: _ReferenceParams
) -> tuple[str | None, dict[str, int]]:
    counts = {
        style: styles.count(style)
        for style in _REFERENCE_STYLE_LABELS
        if styles.count(style)
    }
    recognized = sum(counts.values())
    if recognized < params.min_recognized_entries or not counts:
        return None, counts
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None, counts
    if ranked[0][1] / len(styles) < params.min_style_share:
        return None, counts
    return ranked[0][0], counts


def _normalize_object_number(number: str) -> str:
    normalized = number.translate(str.maketrans({"．": ".", "（": "(", "）": ")"}))
    normalized = re.sub(r"\s+", "", normalized).lower()
    normalized = re.sub(r"\([a-z0-9]+\)$", "", normalized)
    return re.sub(r"-", ".", normalized)


def _caption_number(line: PdfLintTextLine, kind: str) -> str | None:
    match = _OBJECT_PREFIX_PATTERNS[kind].match(line.text.strip())
    if match is None:
        return None
    tail = match.group("tail").strip(" \t:：.-—")
    lowered = tail.lower()
    if any(lowered.startswith(value) for value in _CAPTION_REFERENCE_STARTERS[kind]):
        return None
    if _LIST_ENTRY_TRAILER.search(line.text.strip()):
        return None
    return _normalize_object_number(match.group("number"))


def _object_reference_occurrences(
    lines: list[PdfLintTextLine], kind: str
) -> tuple[set[str], dict[str, tuple[PdfLintTextLine, str]]]:
    captions: set[str] = set()
    caption_line_ids: set[str] = set()
    for line in lines:
        number = _caption_number(line, kind)
        if number is not None:
            captions.add(number)
            caption_line_ids.add(line.line_id)

    occurrences: dict[str, tuple[PdfLintTextLine, str]] = {}
    in_references = False
    for line in lines:
        text = line.text.strip()
        if _REFERENCE_HEADING.match(text):
            in_references = True
        if (
            in_references
            or line.line_id in caption_line_ids
            or _LIST_ENTRY_TRAILER.search(text)
        ):
            continue
        for match in _OBJECT_REFERENCE_PATTERNS[kind].finditer(text):
            number = _normalize_object_number(match.group("number"))
            occurrences.setdefault(number, (line, match.group("number").strip()))
    return captions, occurrences


class FigureTableFormulaNumberingRule:
    rule_id = "figure_table_formula_numbering_check"
    default_severity = "warning"
    params_model = _Params

    async def execute(
        self, context: PaperLintContext, entry: RuleExecutionEntry
    ) -> RuleRun:
        params = self.params_model.model_validate(entry.params or {})
        groups = defaultdict(list)
        for line in _lines(context):
            match = _OBJECT.match(line.text.strip())
            if match:
                kind = match.group("kind").lower()
                name = (
                    "图"
                    if kind in {"图", "figure", "fig", "fig."}
                    else "表"
                    if kind in {"表", "table"}
                    else "公式"
                )
                chapter_or_number = int(match.group("number"))
                section = match.group("section")
                groups[(name, chapter_or_number if section else None)].append(
                    (int(section) if section else chapter_or_number, line)
                )
        if not groups:
            return unsupported(
                entry, message="figure_table_formula_labels_not_detected"
            )
        findings = []
        for (name, section), entries in groups.items():
            expected = 1
            for number, line in entries:
                if number != expected:
                    findings.append(
                        _finding(
                            entry.rule_id,
                            line,
                            f"{name}编号不连续：当前序号为 {number}，同组下一序号应为 {expected}。",
                            "请检查是否遗漏、重复或错序编号，并保持同一章节内连续编号。",
                        )
                    )
                expected = max(expected + 1, number + 1)
                if len(findings) >= params.max_findings:
                    break
        return completed_from_findings(
            entry,
            findings=findings[: params.max_findings],
            evidence_mode="derived",
            params=params.model_dump(),
        )


class ReferenceBasicFormatRule:
    rule_id = "reference_basic_format_check"
    default_severity = "warning"
    params_model = _ReferenceParams

    async def execute(
        self, context: PaperLintContext, entry: RuleExecutionEntry
    ) -> RuleRun:
        params = self.params_model.model_validate(entry.params or {})
        lines = _lines(context)
        start = next(
            (
                index
                for index, line in enumerate(lines)
                if _REFERENCE_HEADING.match(line.text.strip())
            ),
            None,
        )
        if start is None:
            return unsupported(entry, message="reference_section_not_detected")
        references = _reference_section_entries(lines, start)
        if not references:
            return unsupported(entry, message="reference_entries_not_detected")
        styles = [_reference_style(reference.text) for reference in references]
        dominant, counts = _dominant_reference_style(styles, params)
        findings = []
        if dominant is None:
            detected = "、".join(
                f"{_REFERENCE_STYLE_LABELS[style]} {count} 条"
                for style, count in sorted(counts.items())
            )
            findings.append(
                _finding(
                    entry.rule_id,
                    references[0].line,
                    "无法稳定判断全文参考文献采用的统一格式"
                    + (f"：当前识别到 {detected}。" if detected else "。"),
                    "请统一采用 GB/T 7714、APA 7 或 IEEE 中的一种格式，并检查无法识别的条目。",
                )
            )
            message = "reference_style_inconclusive"
        else:
            label = _REFERENCE_STYLE_LABELS[dominant]
            message = f"自动识别的参考文献格式：{label}"
            for reference, style in zip(references, styles):
                if style == dominant:
                    continue
                actual = (
                    _REFERENCE_STYLE_LABELS[style]
                    if style is not None
                    else "无法识别的格式"
                )
                findings.append(
                    _finding(
                        entry.rule_id,
                        reference.line,
                        f"该参考文献呈现为{actual}，与全文自动识别的 {label} 格式不一致。",
                        f"请按 {label} 格式补全作者、题名、年份和来源等著录字段。",
                    )
                )
                if len(findings) >= params.max_findings:
                    break

            if dominant in {"gbt", "ieee"}:
                expected = 1
                for reference in references:
                    match = _REFERENCE_NUMBERED_START.match(reference.text)
                    if match is None:
                        continue
                    number = int(match.group("number"))
                    if number != expected:
                        findings.append(
                            _finding(
                                entry.rule_id,
                                reference.line,
                                f"参考文献编号应为 [{expected}]，实际为 [{number}]。",
                                "请调整参考文献编号，使其从 [1] 起连续递增。",
                            )
                        )
                    expected = max(expected + 1, number + 1)
                    if len(findings) >= params.max_findings:
                        break
        return completed_from_findings(
            entry,
            findings=findings[: params.max_findings],
            evidence_mode="derived",
            message=message,
            params=params.model_dump(),
        )


class _ObjectReferenceTargetRule:
    kind = ""
    object_label = ""
    default_severity = "warning"
    params_model = _Params

    async def execute(
        self, context: PaperLintContext, entry: RuleExecutionEntry
    ) -> RuleRun:
        params = self.params_model.model_validate(entry.params or {})
        captions, references = _object_reference_occurrences(
            _lines(context), self.kind
        )
        if not references:
            return unsupported(
                entry, message=f"{self.kind}_references_not_detected"
            )
        findings = []
        for number, (line, display_number) in references.items():
            if number in captions:
                continue
            findings.append(
                _finding(
                    entry.rule_id,
                    line,
                    f"正文引用了“{self.object_label} {display_number}”，但全文未识别到对应{self.object_label}题注。",
                    f"请检查{self.object_label}是否缺失、题注是否遗漏，或正文引用与题注编号是否一致。",
                )
            )
            if len(findings) >= params.max_findings:
                break
        return completed_from_findings(
            entry,
            findings=findings,
            evidence_mode="derived",
            message=f"根据正文引用与{self.object_label}题注编号进行交叉核对。",
            params=params.model_dump(),
        )


class FigureReferenceTargetRule(_ObjectReferenceTargetRule):
    rule_id = "figure_reference_target_check"
    kind = "figure"
    object_label = "图"


class TableReferenceTargetRule(_ObjectReferenceTargetRule):
    rule_id = "table_reference_target_check"
    kind = "table"
    object_label = "表"


class ChineseEnglishSymbolMixRule:
    rule_id = "chinese_english_symbol_mix_check"
    default_severity = "warning"
    params_model = _Params

    async def execute(
        self, context: PaperLintContext, entry: RuleExecutionEntry
    ) -> RuleRun:
        params = self.params_model.model_validate(entry.params or {})
        findings = []
        for line in _lines(context):
            text = line.text.strip()
            if _FULLWIDTH_ALNUM.search(text):
                findings.append(
                    _finding(
                        entry.rule_id,
                        line,
                        "检测到全角英文字母或数字。",
                        "请将英文字母和阿拉伯数字统一为半角字符。",
                    )
                )
            if _CJK.search(text) and _ASCII_PUNCTUATION.search(text):
                findings.append(
                    _finding(
                        entry.rule_id,
                        line,
                        "中文文本中混用了英文半角标点。",
                        "请根据院校规范统一使用中文全角标点，英文或公式内容除外。",
                    )
                )
            if len(findings) >= params.max_findings:
                break
        return completed_from_findings(
            entry,
            findings=findings,
            evidence_mode="derived",
            params=params.model_dump(),
        )


class BilingualKeywordsCorrespondenceRule:
    rule_id = "bilingual_keywords_correspondence_check"
    default_severity = "warning"
    params_model = _Params

    async def execute(
        self, context: PaperLintContext, entry: RuleExecutionEntry
    ) -> RuleRun:
        params = self.params_model.model_validate(entry.params or {})
        chinese = english = None
        for line in _lines(context):
            match = _KEYWORDS.match(line.text.strip())
            if not match:
                continue
            label, content = match.group(1).lower(), match.group(2)
            count = len(
                [value for value in re.split(r"[,，;；、]", content) if value.strip()]
            )
            if label in {"关键词", "关键字"} and chinese is None:
                chinese = (count, line)
            elif label not in {"关键词", "关键字"} and english is None:
                english = (count, line)
        if chinese is None or english is None:
            return unsupported(entry, message="bilingual_keywords_not_detected")
        findings = []
        if chinese[0] != english[0]:
            findings.append(
                _finding(
                    entry.rule_id,
                    english[1],
                    f"中英文关键词数量不一致：中文 {chinese[0]} 个，英文 {english[0]} 个。",
                    "请核对中英文关键词并保持数量和含义一一对应。",
                )
            )
        return completed_from_findings(
            entry,
            findings=findings[: params.max_findings],
            evidence_mode="derived",
            params=params.model_dump(),
        )


class HeadingNumberingSequenceRule:
    rule_id = "heading_numbering_sequence_check"
    default_severity = "warning"
    params_model = _Params

    async def execute(
        self, context: PaperLintContext, entry: RuleExecutionEntry
    ) -> RuleRun:
        params = self.params_model.model_validate(entry.params or {})
        headings = _detect_numbered_heading_candidates(
            context.raw.lines,
            min_heading_y_pt=90,
            max_heading_chars=90,
            max_numbering_depth=4,
        )
        headings = [
            heading for heading in headings if heading.number and heading.issue is None
        ]
        if not headings:
            return unsupported(
                entry, message="heading_numbering_candidates_not_detected"
            )
        previous, findings = {}, []
        for heading in headings:
            parent, current = heading.number[:-1], heading.number[-1]
            if parent not in previous and current != 1:
                expected = ".".join(map(str, parent + (1,)))
                findings.append(
                    Finding(
                        rule_id=entry.rule_id,
                        message=f"标题编号未从 1 开始：在 {'.'.join(map(str, parent)) or '章节'} 下发现“{heading.number_text}”。",
                        suggestion=f"请确认该同级标题是否应从“{expected}”开始编号。",
                        location=location_from_lines(
                            context.lines_by_id(list(heading.line_ids)),
                            text_excerpt=heading.text,
                        ),
                    )
                )
            elif parent in previous and current != previous[parent] + 1:
                expected = ".".join(map(str, parent + (previous[parent] + 1,)))
                findings.append(
                    Finding(
                        rule_id=entry.rule_id,
                        message=f"标题编号不连续：在 {'.'.join(map(str, parent)) or '章节'} 下发现“{heading.number_text}”，应接续为“{expected}”。",
                        suggestion="请检查标题是否遗漏、重复或错序，并使同级标题按顺序连续编号。",
                        location=location_from_lines(
                            context.lines_by_id(list(heading.line_ids)),
                            text_excerpt=heading.text,
                        ),
                    )
                )
            previous[parent] = current
            if len(findings) >= params.max_findings:
                break
        return completed_from_findings(
            entry,
            findings=findings,
            evidence_mode="derived",
            params=params.model_dump(),
        )


class TocBodyHeadingConsistencyRule:
    rule_id = "toc_body_heading_consistency_check"
    default_severity = "warning"
    params_model = _Params

    async def execute(
        self, context: PaperLintContext, entry: RuleExecutionEntry
    ) -> RuleRun:
        params = self.params_model.model_validate(entry.params or {})
        snapshot = _find_toc_snapshot(context.raw.lines, context.raw.runs)
        if snapshot is None:
            return unsupported(entry, message="toc_not_detected")
        toc_line_ids = {item.line.line_id for item in snapshot.entries}
        body = {
            _compact(line.text)
            for line in _lines(context)
            if line.line_id not in toc_line_ids
        }
        findings = []
        for item in snapshot.entries:
            title = _TOC_ENTRY_TRAILER_RE.sub("", item.text).strip()
            if title and _compact(title) not in body:
                findings.append(
                    _finding(
                        entry.rule_id,
                        item.line,
                        f"目录条目“{title}”未在正文中识别到同名标题。",
                        "请核对目录与正文标题是否一致；如为换行标题，请人工确认。",
                    )
                )
            if len(findings) >= params.max_findings:
                break
        return completed_from_findings(
            entry,
            findings=findings,
            evidence_mode="derived",
            params=params.model_dump(),
        )


class RequiredSectionCompletenessRule:
    rule_id = "required_section_completeness_check"
    default_severity = "warning"
    params_model = _Params

    async def execute(
        self, context: PaperLintContext, entry: RuleExecutionEntry
    ) -> RuleRun:
        params = self.params_model.model_validate(entry.params or {})
        lines = _lines(context)
        visible = [_compact(line.text) for line in lines]
        first_page = _compact(context.raw.pages[0].text) if context.raw.pages else ""
        required = {
            "摘要": {"摘要", "abstract"},
            "关键词": {"关键词", "关键字", "keywords", "key words"},
            "目录": {"目录", "contents"},
            "参考文献": {"参考文献", "references", "bibliography"},
        }
        findings = []
        anchor = lines[0] if lines else None
        if anchor is not None and not any(
            token in first_page for token in ("学位论文", "硕士论文", "博士论文")
        ):
            findings.append(
                _finding(
                    entry.rule_id,
                    anchor,
                    "首页未识别到学位论文封面标识。",
                    "请确认封面页包含学位论文类型与题名；非标准模板或扫描件可能无法识别。",
                )
            )
        for label, candidates in required.items():
            if (
                not any(
                    any(item.startswith(value) for item in visible)
                    for value in candidates
                )
                and anchor is not None
            ):
                findings.append(
                    _finding(
                        entry.rule_id,
                        anchor,
                        f"未识别到必备章节“{label}”。",
                        "请确认论文包含该章节；扫描件或非标准标题可能导致无法识别。",
                    )
                )
        return completed_from_findings(
            entry,
            findings=findings[: params.max_findings],
            evidence_mode="derived",
            params=params.model_dump(),
        )


class PageNumberSequenceRule:
    rule_id = "page_number_sequence_check"
    default_severity = "warning"
    params_model = _Params

    async def execute(
        self, context: PaperLintContext, entry: RuleExecutionEntry
    ) -> RuleRun:
        params = self.params_model.model_validate(entry.params or {})
        candidates = []
        for line in _lines(context):
            text = line.text.strip()
            if line.bbox.y2 >= line.bbox.height * 0.85 and text.isdigit():
                candidates.append((int(text), line))
        if len(candidates) < 2:
            return unsupported(entry, message="page_numbers_not_detected")
        findings = []
        for (previous, _), (current, line) in zip(candidates, candidates[1:]):
            if current != previous + 1:
                findings.append(
                    _finding(
                        entry.rule_id,
                        line,
                        f"页码不连续：上一页显示 {previous}，当前页显示 {current}。",
                        "请核对页码起始页、连续性和页码格式。",
                    )
                )
        return completed_from_findings(
            entry,
            findings=findings[: params.max_findings],
            evidence_mode="derived",
            params=params.model_dump(),
        )


class CitationFootnoteSequenceRule:
    rule_id = "citation_footnote_sequence_check"
    default_severity = "warning"
    params_model = _Params

    async def execute(
        self, context: PaperLintContext, entry: RuleExecutionEntry
    ) -> RuleRun:
        params = self.params_model.model_validate(entry.params or {})
        findings, seen, expected = [], set(), 1
        in_references = False
        for line in _lines(context):
            text = line.text.strip()
            if _REFERENCE_HEADING.match(text):
                in_references = True
            if in_references:
                continue
            for match in _CITATION.finditer(text):
                for value in re.findall(r"\d+", match.group(1)):
                    number = int(value)
                    if number not in seen and number != expected:
                        findings.append(
                            _finding(
                                entry.rule_id,
                                line,
                                f"正文首次引用序号应为 [{expected}]，但识别到 [{number}]。",
                                "请核对正文引注、脚注与参考文献编号的连续性。",
                            )
                        )
                    if number not in seen:
                        seen.add(number)
                        expected = max(expected + 1, number + 1)
            if len(findings) >= params.max_findings:
                break
        if not seen:
            return unsupported(entry, message="citations_not_detected")
        return completed_from_findings(
            entry,
            findings=findings,
            evidence_mode="derived",
            params=params.model_dump(),
        )
