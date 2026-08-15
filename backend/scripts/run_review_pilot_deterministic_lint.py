"""Run approved PDF-only review-pilot rules for the Node backend.

Deterministic rules run locally. Selected semantic rules use one fixed
DeepSeek Official model through its OpenAI-compatible API. This bridge does
not import review-pilot's task/database stack and never accepts model choices
from browser input.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Any


FIXED_DEEPSEEK_MODEL = "deepseek-v4-flash"
FIXED_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_API_KEY_ENV = "REVIEW_PILOT_DEEPSEEK_API_KEY"
SEMANTIC_RULE_IDS = frozenset(
    {
        "bilingual_abstract_consistency_check",
        "claim_evidence_inconsistency_check",
        "strong_claim_without_evidence_check",
    }
)


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
    "figure_table_formula_numbering_check": (
        "图表公式编号连续性",
        "检查图、表和公式标签的编号是否从 1 起连续。",
    ),
    "reference_basic_format_check": (
        "参考文献基础著录",
        "检查参考文献编号、四位年份和文献类型标识等可见基础字段。",
    ),
    "chinese_english_symbol_mix_check": (
        "中英文符号与全半角",
        "检查中文文本中的英文半角标点及全角英文字母、数字。",
    ),
    "bilingual_keywords_correspondence_check": (
        "中英文关键词对应",
        "检查已识别中英文关键词的数量是否一致。",
    ),
    "heading_numbering_sequence_check": (
        "标题编号连续性",
        "检查同级章节标题是否存在缺号、重号或错序。",
    ),
    "toc_body_heading_consistency_check": ("目录正文一致性", "检查目录条目是否能在正文识别到同名标题。"),
    "required_section_completeness_check": ("核心章节完整性", "检查摘要、关键词、目录和参考文献等核心章节。"),
    "page_number_sequence_check": ("页码连续性", "检查页面底部可识别页码是否连续。"),
    "citation_footnote_sequence_check": ("引注编号连续性", "检查正文可识别方括号引注的首次编号顺序。"),
    "bilingual_abstract_consistency_check": (
        "中英文摘要内容一致性",
        "使用 DeepSeek 检查中英文摘要的研究对象、方法、结果和结论是否实质一致。",
    ),
    "claim_evidence_inconsistency_check": (
        "论点与论据一致性",
        "使用 DeepSeek 检查论文中的数值论点与候选实验论据是否矛盾。",
    ),
    "strong_claim_without_evidence_check": (
        "强论断支撑检查（试验性）",
        "使用 DeepSeek 查找缺少可追溯证据的作者强论断；结果需要人工复核。",
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-dir", type=Path, required=True)
    parser.add_argument("--catalog", action="store_true")
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--rule", action="append", default=[])
    return parser.parse_args()


def semantic_rules_requested(rule_ids: list[str]) -> bool:
    return bool(SEMANTIC_RULE_IDS.intersection(rule_ids))


def require_deepseek_api_key() -> str:
    api_key = os.environ.get(DEEPSEEK_API_KEY_ENV, "").strip()
    if not api_key:
        raise RuntimeError("语义规则尚未配置 DeepSeek 官方 API Key")
    return api_key


def load_engine(
    backend_dir: Path,
    requested_rule_ids: list[str],
    *,
    deepseek_api_key: str | None,
) -> dict[str, Any]:
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
    from paper_lint_extended_rules import (
        BilingualKeywordsCorrespondenceRule,
        ChineseEnglishSymbolMixRule,
        FigureTableFormulaNumberingRule,
        HeadingNumberingSequenceRule,
        TocBodyHeadingConsistencyRule,
        RequiredSectionCompletenessRule,
        PageNumberSequenceRule,
        CitationFootnoteSequenceRule,
        ReferenceBasicFormatRule,
    )

    rule_factories = {
        rule_type.rule_id: rule_type
        for rule_type in [
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
            FigureTableFormulaNumberingRule,
            ReferenceBasicFormatRule,
            ChineseEnglishSymbolMixRule,
            BilingualKeywordsCorrespondenceRule,
            HeadingNumberingSequenceRule,
            TocBodyHeadingConsistencyRule,
            RequiredSectionCompletenessRule,
            PageNumberSequenceRule,
            CitationFootnoteSequenceRule,
        ]
    }

    if semantic_rules_requested(requested_rule_ids):
        if deepseek_api_key is None:
            raise RuntimeError("语义规则尚未配置 DeepSeek 官方 API Key")

        from openai import AsyncOpenAI

        from novref.domain.paper_lint.rules.bilingual_abstract_consistency_check import (
            BilingualAbstractConsistencyRule,
        )
        from novref.domain.paper_lint.rules.claim_evidence_inconsistency_check import (
            ClaimEvidenceInconsistencyRule,
        )
        from novref.domain.paper_lint.rules.semantic_atomic import SemanticCheckResponse
        from novref.domain.paper_lint.rules.strong_claim_without_evidence_check import (
            StrongClaimWithoutEvidenceRule,
        )

        deepseek = AsyncOpenAI(
            api_key=deepseek_api_key,
            base_url=FIXED_DEEPSEEK_BASE_URL,
            max_retries=0,
            timeout=120.0,
        )

        async def invoke_deepseek_json(messages):
            role_by_type = {
                "system": "system",
                "human": "user",
                "ai": "assistant",
            }
            request_messages = []
            for message in messages:
                role = role_by_type.get(message.type)
                if role is None:
                    raise ValueError(f"unsupported DeepSeek message type: {message.type}")
                request_messages.append({"role": role, "content": str(message.content)})
            request_messages.append(
                {
                    "role": "system",
                    "content": (
                        "Return exactly one valid JSON object. Do not include markdown "
                        "fences or any text outside the JSON object."
                    ),
                }
            )
            response = await deepseek.chat.completions.create(
                model=FIXED_DEEPSEEK_MODEL,
                messages=request_messages,
                temperature=0,
                max_tokens=8192,
                response_format={"type": "json_object"},
                extra_body={"thinking": {"type": "disabled"}},
            )
            content = response.choices[0].message.content
            if not content or not content.strip():
                raise ValueError("DeepSeek returned empty JSON content")
            return content

        async def invoke_semantic_check(messages):
            content = await invoke_deepseek_json(messages)
            return SemanticCheckResponse.model_validate_json(content)

        if "bilingual_abstract_consistency_check" in requested_rule_ids:
            rule_factories["bilingual_abstract_consistency_check"] = (
                lambda: BilingualAbstractConsistencyRule(
                    ainvoke=invoke_semantic_check,
                )
            )
        if "claim_evidence_inconsistency_check" in requested_rule_ids:
            rule_factories["claim_evidence_inconsistency_check"] = (
                lambda: ClaimEvidenceInconsistencyRule(
                    ainvoke=invoke_deepseek_json,
                )
            )
        if "strong_claim_without_evidence_check" in requested_rule_ids:
            rule_factories["strong_claim_without_evidence_check"] = (
                lambda: StrongClaimWithoutEvidenceRule(
                    ainvoke=invoke_deepseek_json,
                )
            )

    return {
        "PaperLintContext": PaperLintContext,
        "PaperLintResultRuleset": PaperLintResultRuleset,
        "PaperLintSummary": PaperLintSummary,
        "PaperLintTaskResult": PaperLintTaskResult,
        "RuleExecutionEntry": RuleExecutionEntry,
        "execute": execute_rule_entries,
        "rule_factories": rule_factories,
    }


class SelectedRuleCatalog:
    def __init__(self, rule_factories: dict[str, Any]) -> None:
        self.rule_factories = rule_factories

    def create(self, rule_id: str):
        factory = self.rule_factories.get(rule_id)
        return factory() if factory else None


def catalog_payload(engine: dict[str, Any]) -> dict[str, Any]:
    rules = []
    semantic_available = bool(os.environ.get(DEEPSEEK_API_KEY_ENV, "").strip())
    for rule_id, (title, description) in RULE_METADATA.items():
        is_semantic = rule_id in SEMANTIC_RULE_IDS
        rule_factory = engine["rule_factories"].get(rule_id)
        rules.append(
            {
                "rule_id": rule_id,
                "title": title,
                "description": description,
                "default_severity": (
                    getattr(rule_factory, "default_severity", "warning")
                ),
                "default_enabled": not is_semantic,
                "execution_mode": "semantic" if is_semantic else "deterministic",
                "uses_external_model": is_semantic,
                "available": semantic_available if is_semantic else True,
            }
        )
    return {
        "engine": "review-pilot",
        "mode": "pdf_lint",
        "semantic_model": FIXED_DEEPSEEK_MODEL,
        "rules": rules,
    }


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
    unknown = [rule_id for rule_id in rule_ids if rule_id not in engine["rule_factories"]]
    if unknown:
        raise RuntimeError(f"Unknown paper-lint rule: {unknown[0]}")

    entries = [
        engine["RuleExecutionEntry"](
            rule_id=rule_id,
            severity=getattr(
                engine["rule_factories"][rule_id],
                "default_severity",
                "warning",
            ),
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
        SelectedRuleCatalog(engine["rule_factories"]),
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
            id="review-pilot-pdf-lint",
            name="review-pilot PDF 规则",
            version_number=1,
            version_label="当前部署版本",
        ),
        rule_runs=rule_runs,
        summary=build_summary(engine, rule_runs),
    )
    return result.model_dump(mode="json")


def main() -> int:
    args = parse_args()
    unknown = [rule_id for rule_id in args.rule if rule_id not in RULE_METADATA]
    if unknown:
        raise RuntimeError(f"Unknown paper-lint rule: {unknown[0]}")
    deepseek_api_key = (
        require_deepseek_api_key() if semantic_rules_requested(args.rule) else None
    )
    captured_stdout = io.StringIO()
    with contextlib.redirect_stdout(captured_stdout):
        engine = load_engine(
            args.backend_dir,
            args.rule,
            deepseek_api_key=deepseek_api_key,
        )
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
