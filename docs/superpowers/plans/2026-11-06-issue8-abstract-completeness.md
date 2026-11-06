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
- [ ] Commit, merge main, push, external deployment and static/service verification (recorded in the deployment log).


## Verification before integration

- Native admission/R6/abstract/punctuation regressions: 193 passed, 45 subtests passed.
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
