"""Five additional deterministic PDF rules for the degree-review pilot.

The rules consume the review-pilot parser's extracted visible text; they offer
locatable, explainable checks and deliberately do not claim full GB/T coverage.
"""

from __future__ import annotations

import re
from collections import defaultdict

from pydantic import BaseModel, Field

from novref.domain.paper_lint.context import PaperLintContext
from novref.domain.paper_lint.contracts import Finding, RuleRun
from novref.domain.paper_lint.pdf_location import location_from_lines
from novref.domain.paper_lint.rules.base import completed_from_findings, unsupported
from novref.domain.paper_lint.rules.executor import RuleExecutionEntry
from novref.domain.paper_lint.rules.heading_numbering_hierarchy_check import (
    _detect_numbered_heading_candidates,
)

_REFERENCE_HEADING = re.compile(r"^(参考文献|references|bibliography)$", re.I)
_NEXT_SECTION = re.compile(r"^(致谢|附录|acknowledg(e)?ments?|appendix)", re.I)
_REFERENCE = re.compile(r"^\s*\[(\d+)]\s*(.+)$")
_YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_TYPE = re.compile(r"\[[A-Z]{1,3}(?:/[A-Z]{1,3})?]")
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


class _Params(BaseModel):
    max_findings: int = Field(default=20, gt=0, le=200)


def _lines(context: PaperLintContext):
    return sorted(
        (line for line in context.raw.lines if line.text.strip()),
        key=lambda line: (
            line.page_number,
            line.reading_order,
            line.bbox.y1,
            line.bbox.x1,
        ),
    )


def _finding(rule_id: str, line, message: str, suggestion: str) -> Finding:
    return Finding(
        rule_id=rule_id,
        message=message,
        suggestion=suggestion,
        location=location_from_lines([line], text_excerpt=line.text.strip()),
    )


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
    params_model = _Params

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
        findings, expected, entries = [], 1, 0
        for line in lines[start + 1 :]:
            text = line.text.strip()
            if _NEXT_SECTION.match(text):
                break
            match = _REFERENCE.match(text)
            if match is None:
                if re.match(r"^\s*(?:\d+[.)、]|[A-Z][A-Za-z .'-]{1,40}[,:])", text):
                    findings.append(
                        _finding(
                            entry.rule_id,
                            line,
                            "参考文献条目缺少方括号编号。",
                            "请以“[序号]”开头，并按正文出现顺序连续编号。",
                        )
                    )
                continue
            else:
                entries += 1
                number, body = int(match.group(1)), match.group(2)
                if number != expected:
                    findings.append(
                        _finding(
                            entry.rule_id,
                            line,
                            f"参考文献编号应为 [{expected}]，实际为 [{number}]。",
                            "请调整参考文献编号，使其从 [1] 起连续递增。",
                        )
                    )
                if not _YEAR.search(body):
                    findings.append(
                        _finding(
                            entry.rule_id,
                            line,
                            "参考文献条目未识别到四位出版年份。",
                            "请补充规范的出版或发表年份。",
                        )
                    )
                if not _TYPE.search(body):
                    findings.append(
                        _finding(
                            entry.rule_id,
                            line,
                            "参考文献条目未识别到文献类型标识。",
                            "请按采用的 GB/T 7714 模板补充如 [J]、[M]、[D] 等文献类型标识。",
                        )
                    )
                expected = max(expected + 1, number + 1)
            if len(findings) >= params.max_findings:
                break
        if entries == 0 and not findings:
            return unsupported(entry, message="reference_entries_not_detected")
        return completed_from_findings(
            entry,
            findings=findings[: params.max_findings],
            evidence_mode="derived",
            params=params.model_dump(),
        )


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
