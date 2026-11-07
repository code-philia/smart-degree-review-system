"""Manifest-driven PDF regressions for externally stored rule fixtures."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from paper_compiler.frontend import build_paper
from fast_local_detector import run as run_fast_local
import run_bilingual_semantic_lint as semantic_lint

DEFAULT_MANIFEST = ROOT / "tests_py" / "fixtures" / "rule_regression_20261104" / "manifest.json"
ABSTRACT_RULE = "bilingual_abstract_consistency_check"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def typo_pairs(result: dict[str, Any]) -> list[tuple[str, str]]:
    pairs = []
    for finding in result.get("findings") or []:
        message = str(finding.get("message") or "")
        prefix = "疑似错别字："
        if message.startswith(prefix):
            pairs.append((message[len(prefix):], str(finding.get("suggestion") or "")))
    return pairs


def _location_key(finding: dict[str, Any]) -> tuple[Any, ...]:
    location = finding.get("location") or {}
    rect = location.get("bounding_rect") or {}
    return (location.get("page_number"), rect.get("x1"), rect.get("y1"),
            rect.get("x2"), rect.get("y2"), finding.get("message"))


def evaluate_case(case: dict[str, Any], result: dict[str, Any]) -> list[str]:
    """Return all contract failures, so one CI run reports every regression."""
    failures: list[str] = []
    if case["engine"] == "bilingual_abstract":
        if result.get("execution_status") != "completed" or result.get("outcome") != "issues_found":
            return [f"expected completed abstract finding, got {result.get('outcome')}"]
        rows = (result.get("params") or {}).get("mismatches") or []
        finding = (result.get("findings") or [{}])[0]
        message = finding.get("message") or ""
        for expected in case["must_find"]:
            if not any(row.get("mismatch_type") == expected["mismatch_type"] and all(
                semantic_lint._compact_claim(value) in semantic_lint._compact_claim(row.get(field))
                for field, value in expected["evidence"].items()
            ) for row in rows):
                failures.append(f"missing required mismatch: {expected['mismatch_type']} {expected['evidence']}")
            if not any(term in message for term in expected["message_any"]):
                failures.append("report message omits the expected substantive difference")
        if not message:
            failures.append("missing report message")
        return failures
    if case["engine"] == "fast_local":
        findings = ((result.get("rules") or {}).get(str(case["rule"])) or {}).get("findings") or []
        observed = [str(item.get("token") or "") for item in findings]
        if len(observed) < int(case.get("min_findings", 0)):
            failures.append(f"expected at least {case['min_findings']} finding(s), got {len(observed)}")
        for token in case.get("must_find", []):
            if token not in observed:
                failures.append(f"missing required token: {token}")
        return failures

    findings = result.get("findings") or []
    pairs = typo_pairs(result)
    for expected in case.get("must_find", []):
        pair = (str(expected["text"]), str(expected["suggestion"]))
        if pair not in pairs:
            failures.append(f"missing required typo: {pair[0]} -> {pair[1]}")
    messages = [str(item.get("message") or "") for item in findings]
    for forbidden in case.get("must_not_find", []):
        if any(forbidden in message for message in messages):
            failures.append(f"unexpected typo finding: {forbidden}")
    if case.get("no_duplicate_locations"):
        keys = [_location_key(item) for item in findings]
        if len(keys) != len(set(keys)):
            failures.append("duplicate finding at the same PDF location")
    return failures


def run_case(case: dict[str, Any], pdf: Path, *, live_llm: bool) -> dict[str, Any]:
    if case["engine"] == "fast_local":
        return run_fast_local(pdf, [int(case["rule"])])
    if case["engine"] == "bilingual_abstract":
        if live_llm:
            return semantic_lint.run(pdf, [ABSTRACT_RULE], allow_incomplete_structure=True)["rule_runs"][0]
        ir = build_paper(pdf, include_citations=False, allow_incomplete_structure=True)
        facts = semantic_lint.extract_bilingual_facts(ir)
        rows = []
        for expected in case["must_find"]:
            evidence = expected["evidence"]
            present = all(semantic_lint._compact_claim(value) in semantic_lint._compact_claim(
                facts.get(field.replace("_claim", "_abstract"))
            ) for field, value in evidence.items())
            absent = all(semantic_lint._compact_claim(value) not in semantic_lint._compact_claim(facts.get(field))
                         for field, value in expected.get("absent", {}).items())
            if present and absent:
                rows.append({"mismatch_type": expected["mismatch_type"], "reason": expected["reason"], **evidence})

        def model_contract(messages):
            prompt = messages[0]["content"]
            if prompt.startswith("检查同一论文的中英文摘要片段"):
                payload = {"from_chinese": [], "from_english": []}
            else:
                payload = {"outcome": "consistent", "mismatches": rows}
            return payload, {"input_tokens": 0, "output_tokens": 0}

        from unittest.mock import patch
        with patch.object(semantic_lint, "request_json", model_contract):
            return semantic_lint._run_semantic_rule(ir, facts, ABSTRACT_RULE)
    ir = build_paper(pdf, include_citations=False)
    if not live_llm:
        old_request_json = semantic_lint.request_json
        expected = [
            {"original": str(item["text"]), "corrected": str(item["suggestion"]),
             "source": str(item.get("source") or item["text"])}
            for item in case.get("must_find", [])
        ]

        def model_contract(messages):
            prompt = str(messages[0].get("content") or "")
            if "候选复核器" in prompt:
                return {"accepted": True, "reason": "回归模型契约确认"}, {"input_tokens": 0, "output_tokens": 0}
            target = prompt.rsplit("目标段落：", 1)[-1]
            rows = []
            for item in expected:
                original, corrected, source = item["original"], item["corrected"], item["source"]
                at = target.find(source)
                if at < 0:
                    continue
                # Keep the mocked model context byte-for-byte locatable in the
                # Paper Model text.  Real model responses may supply a longer
                # sentence, but a synthetic newline-normalised window would
                # test a different failure mode than this contract harness.
                context = source
                rows.append({"original": original, "corrected": corrected,
                             "context": context, "reason": "回归模型契约候选"})
            return {"errors": rows}, {"input_tokens": 0, "output_tokens": 0}

        semantic_lint.request_json = model_contract
        try:
            return semantic_lint.run_typo_rule_from_ir(ir)
        finally:
            semantic_lint.request_json = old_request_json
    return semantic_lint.run_typo_rule_from_ir(ir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--pdf-root", type=Path, default=os.environ.get("RULE_REGRESSION_PDF_ROOT"))
    parser.add_argument("--live-llm", action="store_true")
    parser.add_argument("--case", action="append", help="Run only this case ID (repeatable)")
    args = parser.parse_args(argv)
    if not args.pdf_root:
        parser.error("provide --pdf-root or RULE_REGRESSION_PDF_ROOT")
    pdf_root = Path(args.pdf_root)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    failures: list[str] = []
    cases = [case for case in manifest["cases"] if not args.case or case["id"] in args.case]
    unknown = set(args.case or []) - {case["id"] for case in cases}
    if unknown:
        parser.error(f"unknown case ID(s): {', '.join(sorted(unknown))}")
    for case in cases:
        pdf = pdf_root / case["file"]
        if not pdf.is_file():
            failures.append(f"{case['id']}: fixture missing: {pdf}")
            continue
        actual = sha256(pdf)
        if actual != case["sha256"]:
            failures.append(f"{case['id']}: SHA-256 mismatch ({actual})")
            continue
        result = run_case(case, pdf, live_llm=args.live_llm)
        case_failures = evaluate_case(case, result)
        for failure in case_failures:
            failures.append(f"{case['id']}: {failure}")
        print(f"PASS {case['id']}" if not case_failures else f"FAIL {case['id']}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"PASS {len(cases)} rule regression case(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
