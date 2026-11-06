# Issue 8 Abstract Completeness Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reject incomplete abstracts accurately without rejecting complete papers.

**Architecture:** Extend the native source grammar with bounded abstract evidence.
Carry separate missing/incomplete sections through compilation rejection and R6.

**Tech Stack:** Python/PyMuPDF, Node/CommonJS, pytest, Vitest.

**Spec:** docs/superpowers/specs/2026-11-06-issue8-abstract-completeness.md

## Global Constraints

- No OCR, model/API calls, or abstract length thresholds.
- Preserve article grammar, multilingual titles, cross-page abstracts and current IR mutations.
- Severe compilation rejection skips all detectors; separate missing/incomplete copy.
- Separate issue branch, merge to main after testing; deploy externally, no campus access.

## Review Focus

- Keyword labels split across lines or glyphs must not reject a normal thesis.
- Running headers and page numbers must not fabricate body or a second abstract.
- Another section's keywords must not close a truncated abstract.
- Very short complete abstracts and keyword-free articles must compile.
- Edited IR cannot recover missing abstract text from immutable PDF observations.

### Task 1: Native grammar and R6

**Files:** backend/paper_compiler/structure.py, document_admission.py,
local_checks.py; backend/tests_py/test_abstract_completeness.py and
test_paper_structure_compilation.py.

- [x] Add missing/partial/complete, short, multilingual, cross-page, header,
  keyword-boundary, article and edited-IR tests; run pytest and observe RED.
  Expected: current code passes incomplete abstracts and fails new expectations.
- [x] Implement bounded evidence and distinct incomplete_sections/reasons.
- [x] Run focused pytest and original versus modified archive PDFs offline.
  Expected: original compiles; R06 v3/v4 and M04 name incomplete abstracts;
  whole removed abstracts name missing sections; no original-PDF IR restoration.

### Task 2: Dispatch proof and user copy

**Files:** backend/src/normative/paperDocumentAdmission.js;
backend/tests/paper-document-admission.test.js.

- [x] Add rejected incomplete-proof and missing/incomplete copy tests; run RED.
- [x] Enforce complete proof and appropriate corrective suggestions.
- [x] Run targeted Vitest and related native regression suites. Expected: green;
  no detectors invoked after any structural rejection.
- [x] Obtain a fresh whole-branch review; address important findings with tests.
- [x] Commit, merge main, push, external deployment and static/service verification (7714a60; recorded in the deployment log).


## Verification before integration

- Native admission/R6/abstract/punctuation regressions: 195 passed, 45 subtests passed.
- Dispatch and archive boundary: 29 passed; formal/live report presentation: 8 passed.
- Original 157-page PDF compiles; R06 v4, R06 v3 and M04 reject incomplete abstracts.
  Fully removed CN/EN abstract fixtures reject as missing. Four other real CN/EN
  archived papers retain complete abstract evidence; no OCR or model calls.
- Independent review's four important findings reproduced RED and fixed GREEN:
  inline titles, chapter-description prose, mixed glyph keywords and page furniture.
  Corrective suggestions now name affected sections without adding thesis-only
  requirements to articles; malformed rejection fields cannot crash the report.
- Full JS suite has pre-existing failures; every candidate failure also appears
  on untouched db5005c under the same offline environment. The old English
  fragment test also fails unchanged on db5005c (three subcases); it is excluded
  from the focused run. Broad Python run stopped after it reached unrelated
  failures; no full-suite success is claimed.
- Scope decision: detect native structural loss only. Arbitrary sentence deletion
  that retains valid structure cannot be established without semantic comparison.
- External service uses the existing immutable deployment/backup/rollback CLI.
  Campus deployment remains deferred by the user's VPN constraint.

## Follow-up acceptance: explicit user-facing diagnoses

The first deployment did not make the two abstract names explicit enough.
The user withdrew the request to show a separate reason for each skipped rule:
retain one severe compilation finding with the specific section failure and
one overall statement that all selected rules were not executed.

- [x] Verify failing tests for “缺少中文摘要”, “缺少英文摘要（Abstract）” and
  separate “中文摘要不完整” / “英文摘要（Abstract）不完整” diagnostics.
- [x] Share profile-aware display names between admission and R6 while keeping
  internal section keys stable. Put the precise cause in the report/run message.
- [x] Verify real v2/v3/v4/M04 and whole-abstract deletion fixtures through the
  complete dispatcher, with detector/network calls blocked; complete original
  papers must still compile. Check the production Python selection.
- [x] Verify backend-produced messages in both report modes; no per-rule list.
- [ ] Review, merge/push the follow-up and deploy externally.

Follow-up evidence: seven native regression assertions and four report-summary
assertions failed before the change, then passed. Focused Python regressions:
196 passed, 45 subtests passed, the same legacy English fragment test excluded.
Linux admission/stream/archive checks: 33 passed. Frontend backend-to-report
rendering: 12 passed. The Windows archive symlink case cannot create a symlink
(EPERM); the same archive suite passes on Linux. No production frontend layout
or right-card components changed.

The actual runPaperLint entry point was exercised offline with all 15 MVP rules
selected: whole Chinese/English abstract deletion, R06_v4/v3, M04 and R06_v2 all
returned exactly one severe compilation finding, zero completed thesis rules,
the explicit diagnosis in both live progress and final output, and all selected
rule IDs recorded as skipped. A subprocess allowlist rejected any detector
launch; Node and Python network guards recorded no API/network calls. The
original 157-page PDF still earned a compiled admission proof. Production
runtime resolution was checked against the running service: SIX_RULE_PYTHON
resolves to /data/envs/six-rule-dev/bin/python with PyMuPDF 1.28.2 installed.

Focused independent review found no Critical or Important findings. Follow-up
fixture evidence and CLI logs are retained under output/issue8-online-probe-20261106
and output/external-deploy-20261106 outside Git; deployment remains the final step.
