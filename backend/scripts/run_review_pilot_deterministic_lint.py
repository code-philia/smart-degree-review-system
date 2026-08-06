"""Run the approved deterministic review-pilot paper-lint rules.

This process is a JSON bridge for the Node backend. It intentionally imports
neither semantic rules nor review-pilot's task/database stack.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import sys
from pathlib import Path
from typing import Any


RULE_METADATA: dict[str, tuple[str, str]] = {
    "body_heading_format_check": (
        "正文标题格式",
        "检查编号正文标题的层级、字体、字号、对齐和间距。",
    ),
    "chinese_abstract_length_check": ("中文摘要长度", "检查中文摘要字符数上限。"),
    "chinese_keywords_format_check": (
        "中文关键词格式",
        "检查中文关键词标签、字体、字号和分隔符。",
    ),
    "chinese_title_format_check": ("中文论文题名格式", "检查中文论文题名页版式。"),
    "english_abstract_length_check": ("英文摘要长度", "检查英文摘要词数上限。"),
    "english_keywords_format_check": (
        "英文关键词格式",
        "检查英文 Key words 标签、字体和字号。",
    ),
    "english_title_format_check": ("英文论文题名格式", "检查英文论文题名页版式。"),
    "first_body_chapter_intro_check": (
        "正文首章绪论",
        "检查第一个编号正文章是否为绪论或引言类章节。",
    ),
    "heading_numbering_hierarchy_check": ("标题编号层级", "检查标题编号和父级层级。"),
    "last_body_chapter_summary_check": (
        "正文末章总结",
        "检查最后一个编号正文章是否为总结或结论类章节。",
    ),
    "toc_format_check": ("目录格式", "检查目录标题、条目、缩进和页码对齐。"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-dir", type=Path, required=True)
    parser.add_argument("--catalog", action="store_true")
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--rule", action="append", default=[])
    return parser.parse_args()


def load_engine(backend_dir: Path) -> dict[str, Any]:
    resolved = backend_dir.resolve()
    if not (resolved / "novref" / "domain" / "paper_lint").is_dir():
        raise RuntimeError(f"review-pilot backend is unavailable: {resolved}")
    sys.path.insert(0, str(resolved))

    from novref.domain.paper_lint.context import PaperLintContext
    from novref.domain.paper_lint.contracts import (
        PaperLintResultRuleset,
        PaperLintSummary,
        PaperLintTaskResult,
    )
    from novref.domain.paper_lint.rules.body_heading_format_check import BodyHeadingFormatRule
    from novref.domain.paper_lint.rules.chinese_abstract_length_check import ChineseAbstractLengthRule
    from novref.domain.paper_lint.rules.chinese_keywords_format_check import ChineseKeywordsFormatRule
    from novref.domain.paper_lint.rules.chinese_title_format_check import ChineseTitleFormatRule
    from novref.domain.paper_lint.rules.english_abstract_length_check import EnglishAbstractLengthRule
    from novref.domain.paper_lint.rules.english_keywords_format_check import EnglishKeywordsFormatRule
    from novref.domain.paper_lint.rules.english_title_format_check import EnglishTitleFormatRule
    from novref.domain.paper_lint.rules.executor import RuleExecutionEntry, execute_rule_entries
    from novref.domain.paper_lint.rules.first_body_chapter_intro_check import FirstBodyChapterIntroRule
    from novref.domain.paper_lint.rules.heading_numbering_hierarchy_check import HeadingNumberingHierarchyRule
    from novref.domain.paper_lint.rules.last_body_chapter_summary_check import LastBodyChapterSummaryRule
    from novref.domain.paper_lint.rules.toc_format_check import TocFormatRule

    rule_types = [
        ChineseTitleFormatRule,
        EnglishTitleFormatRule,
        ChineseAbstractLengthRule,
        EnglishAbstractLengthRule,
        ChineseKeywordsFormatRule,
        EnglishKeywordsFormatRule,
        BodyHeadingFormatRule,
        HeadingNumberingHierarchyRule,
        FirstBodyChapterIntroRule,
        LastBodyChapterSummaryRule,
        TocFormatRule,
    ]
    return {
        "PaperLintContext": PaperLintContext,
        "PaperLintResultRuleset": PaperLintResultRuleset,
        "PaperLintSummary": PaperLintSummary,
        "PaperLintTaskResult": PaperLintTaskResult,
        "RuleExecutionEntry": RuleExecutionEntry,
        "execute": execute_rule_entries,
        "rule_types": {rule_type.rule_id: rule_type for rule_type in rule_types},
    }


class SelectedRuleCatalog:
    def __init__(self, rule_types: dict[str, type]) -> None:
        self.rule_types = rule_types

    def create(self, rule_id: str):
        rule_type = self.rule_types.get(rule_id)
        return rule_type() if rule_type else None


def catalog_payload(engine: dict[str, Any]) -> dict[str, Any]:
    rules = []
    for rule_id, rule_type in engine["rule_types"].items():
        title, description = RULE_METADATA[rule_id]
        rules.append(
            {
                "rule_id": rule_id,
                "title": title,
                "description": description,
                "default_severity": rule_type.default_severity,
                "default_enabled": True,
            }
        )
    return {"engine": "review-pilot", "mode": "deterministic", "rules": rules}


def build_summary(engine: dict[str, Any], rule_runs: list[Any]):
    return engine["PaperLintSummary"](
        rule_count=len(rule_runs),
        completed_rule_count=sum(run.execution_status == "completed" for run in rule_runs),
        unsupported_rule_count=sum(run.execution_status == "unsupported" for run in rule_runs),
        error_rule_count=sum(run.execution_status == "error" for run in rule_runs),
        issue_rule_count=sum(run.outcome == "issues_found" for run in rule_runs),
        finding_count=sum(len(run.findings) for run in rule_runs),
        error_finding_count=sum(len(run.findings) for run in rule_runs if run.severity == "error"),
        warning_finding_count=sum(
            len(run.findings) for run in rule_runs if run.severity == "warning"
        ),
        info_finding_count=sum(len(run.findings) for run in rule_runs if run.severity == "info"),
        derived_rule_count=sum(run.evidence_mode == "derived" for run in rule_runs),
    )


async def run_lint(engine: dict[str, Any], pdf_path: Path, rule_ids: list[str]) -> dict[str, Any]:
    if not pdf_path.is_file():
        raise RuntimeError("PDF input is missing")
    if not rule_ids:
        raise RuntimeError("At least one rule must be selected")
    unknown = [rule_id for rule_id in rule_ids if rule_id not in engine["rule_types"]]
    if unknown:
        raise RuntimeError(f"Unknown deterministic rule: {unknown[0]}")

    entries = [
        engine["RuleExecutionEntry"](
            rule_id=rule_id,
            severity=engine["rule_types"][rule_id].default_severity,
            params=None,
            display_order=index,
        )
        for index, rule_id in enumerate(rule_ids)
    ]
    context = engine["PaperLintContext"].from_bytes(
        pdf_path.read_bytes(),
        message_language="zh",
    )
    rule_runs = await engine["execute"](
        context,
        entries,
        SelectedRuleCatalog(engine["rule_types"]),
    )
    paper_title = "未识别论文标题"
    for line in context.raw.lines[:80]:
        text = " ".join(line.text.split())
        if text:
            paper_title = text[:160]
            break

    result = engine["PaperLintTaskResult"](
        paper_title=paper_title,
        ruleset=engine["PaperLintResultRuleset"](
            id="review-pilot-deterministic",
            name="review-pilot 确定性规则",
            version_number=1,
            version_label="当前部署版本",
        ),
        rule_runs=rule_runs,
        summary=build_summary(engine, rule_runs),
    )
    return result.model_dump(mode="json")


def main() -> int:
    args = parse_args()
    captured_stdout = io.StringIO()
    with contextlib.redirect_stdout(captured_stdout):
        engine = load_engine(args.backend_dir)
        if args.catalog:
            payload = catalog_payload(engine)
        else:
            if args.pdf is None:
                raise RuntimeError("--pdf is required")
            payload = asyncio.run(run_lint(engine, args.pdf, args.rule))
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - process boundary
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from exc
