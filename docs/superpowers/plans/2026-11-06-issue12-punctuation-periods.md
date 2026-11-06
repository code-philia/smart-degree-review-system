# Issue 12 Punctuation Period Fix Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, then obtain one fresh whole-branch review.

**Goal:** Detect every injected Chinese/English period without losing existing punctuation precision.

**Architecture:** Keep the existing Paper IR local rule and source anchors.
Add separate bounded ASCII-period evidence for Chinese sentences and narrow
pseudocode keyword exclusions to explicit label/numbered instruction syntax.
Bound inline equals/arrow exclusions to their Chinese sentence. Retain technical
literal and structural exclusions; do not lower English sentence thresholds.

**Tech Stack:** Python/PyMuPDF, unittest/pytest, existing native Node dispatcher.

**Spec:** docs/superpowers/specs/2026-11-06-issue12-punctuation-periods.md

## Global Constraints

- Issue #12 only; branch fix/issue-12-punctuation-periods; base 1be26a5.
- No OCR or model/API calls; original PDF and source text remain unchanged.
- No blanket punctuation replacement or whole-paragraph language guessing.
- Preserve true errors' native glyph positions; keep all existing exclusions.
- After tests/review, merge/push main and deploy externally; no campus access.

## Review Focus

- ASCII periods inside Chinese prose versus decimals, version/file names,
  initials, dot leaders, ellipses and mathematical notation.
- Chinese sentence endings before line end, closing punctuation or a new
  sentence without spaces; valid embedded English abbreviations remain clean.
- Ordinary English words input/output/require/ensure/return must not silently
  suppress paragraphs; actual pseudocode instructions remain excluded.
- Quoted data, source code, scanned layers and figure/table/reference text
  must retain their existing scope exclusions.
- Each multiple error must retain its own character box and live/final output.

### Task 1: Native punctuation boundaries

**Files:** backend/paper_compiler/local_checks.py;
backend/tests_py/test_fast_punctuation_scope.py; new
backend/tests_py/test_punctuation_periods.py.

**Interfaces:** detect_ir(ir,[35]) / fast_local_detector.run return existing
findings; english_prose threshold and report schema stay unchanged.

- [x] Read full issue and comments, fetch latest main, create independent branch.
- [x] Reproduce original and all four modified PDFs; record before findings and
  affected IR nodes. Existing punctuation scope baseline: 14 tests passed.
- [x] Write explicit failing Chinese-period and English-prose regressions,
  including negatives for technical literals and real pseudocode; observe RED.
- [x] Implement bounded period evidence and instruction-specific exclusions.
- [x] Run native scope/period/local/English compatibility and issue #7/#8 checks.

### Task 2: Complete acceptance and release

**Files:** same implementation/tests; spec/plan; evidence outside Git under
output/issue12-native-20261106.

**Interfaces:** real runPaperLint must emit the same precise findings as native
detect_ir, through admission and fast_local_detector only, with network blocked.

- [x] Verify the complete five-PDF acceptance matrix; audit every newly found
  period against the injected native text and exact glyph positions.
- [x] Obtain one independent review; reproduce/fix Important findings RED/GREEN.
- [x] Verify actual dispatcher output/progress with no OCR/model/API calls.
- [ ] Commit issue branch, merge/push main; deploy externally; repeat fixture
  checks against deployed source/runtime and record evidence.

## Rulings

User explicitly asked to implement under the existing per-issue branch workflow;
continue inline without redundant design/worktree approval. Preserve unrelated
untracked logs/previews. Native source confirmed three causes; avoid unrelated
rewrites of the whole punctuation rule or the Paper compiler.

## Verification results

- 72 local unit tests passed. Linux related native suite: 269 passed, 1 legacy
  structural-fragment test deselected, 76 subtests passed. No model/OCR/API calls.
- 32 related Node tests passed across admission, live progress, semantic stream,
  controls and archive counts. A separate old archive-six-rules stub expectation
  fails identically on untouched base 1be26a5; no archive code was changed.
- Real original/R12_v1/v2/v3/M05 matrix and exact native glyph audits all passed.
- Full dispatcher repeated all five cases with Node/Python network blocked;
  admission then fast_local_detector only; live/final messages and boxes match.
- One independent review completed; its two Important findings reproduced RED
  and fixed GREEN alongside the real inline-math merged-paragraph case.
