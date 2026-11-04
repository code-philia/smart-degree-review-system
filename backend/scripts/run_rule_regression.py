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
    ir = build_paper(pdf, include_citations=False)
    if not live_llm:
        old_request_json = semantic_lint.request_json
        semantic_lint.request_json = lambda _messages: ({"findings": []}, {"input_tokens": 0, "output_tokens": 0})
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
    args = parser.parse_args(argv)
    if not args.pdf_root:
        parser.error("provide --pdf-root or RULE_REGRESSION_PDF_ROOT")
    pdf_root = Path(args.pdf_root)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    failures: list[str] = []
    for case in manifest["cases"]:
        pdf = pdf_root / case["file"]
        if not pdf.is_file():
            failures.append(f"{case['id']}: fixture missing: {pdf}")
            continue
        actual = sha256(pdf)
        if actual != case["sha256"]:
            failures.append(f"{case['id']}: SHA-256 mismatch ({actual})")
            continue
        result = run_case(case, pdf, live_llm=args.live_llm)
        for failure in evaluate_case(case, result):
            failures.append(f"{case['id']}: {failure}")
        print(f"PASS {case['id']}" if not evaluate_case(case, result) else f"FAIL {case['id']}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"PASS {len(manifest['cases'])} rule regression case(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
