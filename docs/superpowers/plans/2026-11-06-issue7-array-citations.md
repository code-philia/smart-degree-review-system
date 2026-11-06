# Issue 7 Array Citation Fix Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove all eight array/tensor false citations and retain real invalid citations.

**Architecture:** Extend the existing native citation boundary checks in
five_rule_detector.py. Typed declarations and inline tensors use bounded text
evidence; split diagram labels use conservative local PDF geometry. Both R2
and the uncited-reference check consume the same decisions.

**Tech Stack:** Python/PyMuPDF, unittest/pytest, existing Node dispatcher.

**Spec:** docs/superpowers/specs/2026-11-06-issue7-array-citations.md

## Global Constraints

- Only issue #7, on fix/issue-7-array-citations; base c5b5c8f.
- No OCR, model/API calls, number blacklist or bibliography-range bypass.
- Preserve genuine citation spans, native coordinates and adjacent markers.
- Merge/push only after tests/review; deploy externally with existing guarded
  release CLI. No campus access attempts.

## Review Focus

- A typed multidimensional declaration ending in comma or parameter-list end
  must not create one false reference per dimension.
- Short tensor names and mathematical Unicode must work without treating all
  model-name citations as dimensions; superscript references remain citations.
- A diagram's label must be on the same page/column and close above its shape;
  unrelated distant shapes or prose must not suppress a bare citation.
- Dimension numbers that exist in the bibliography must not count as uses.
- A true [188], [199], [177] or [4096] near code must retain its own position.

### Task 1: Shared native citation boundaries

**Files:** backend/scripts/five_rule_detector.py;
backend/tests_py/test_five_rule_array_dimensions.py.

**Interfaces:** Existing Line, detect_lines, detect_pdf and report schema stay
unchanged. R2 and R3 share _citation_numbers and _rules_22_24.

- [x] Read the complete issue, preserve each expected effect/criterion in spec,
  reproduce all eight actual PDF findings and run clean native baseline tests
  (91 existing five-rule tests passed).
- [x] Add failing tests for typed parameter declarations, inline tensors, split
  figure labels, genuine large/model-name citations, superscripts, page/column/
  distance controls and uncited-reference consistency; observe RED.
- [x] Implement the smallest bounded text/layout evidence checks; observe GREEN.
- [x] Run all existing five-rule tests and related native citation/compiler tests.

### Task 2: Full acceptance and integration

**Files:** same code/tests; execution evidence under output/issue7-native-20261106.

**Interfaces:** Real runPaperLint output/progress must preserve report severity,
positions and findings; permit only native admission and five-rule subprocesses
in offline acceptance probes, with network blocked.

- [x] Compare real original, R02 v1/v2/v3, M01 and M02 before/after; prove removal
  of exactly eight inherited false positives and preservation of every other
  finding/coordinate. Verify [188]/[199]/[177] explicitly.
- [x] Exercise actual dispatcher for original and all five modified PDFs, using
  the production-selected runtime and native R2 only, without OCR/API calls.
- [x] Obtain focused independent whole-branch review; fix important findings
  with RED/GREEN tests. Check every acceptance criterion against evidence.
- [ ] Commit branch, merge main, push, guarded external deployment; verify live
  process/source version and post-deployment native dispatcher behavior.

## Rulings and evidence

User explicitly instructed implementation and the existing per-issue branch
workflow; reuse the clean issue branch at latest known main without creating a
new worktree or requesting redundant design approval. Existing unrelated
untracked preview/log files remain untouched. GitHub issue was re-read in full
after the user's reminder. The initial remote GitHub read timed out; deployment
status remains c5b5c8f. Resolve connectivity and verify main before integration.

## Verification and complete acceptance matrix

| Real PDF | Before R2 findings | After R2 findings | Genuine finding retained |
| --- | ---: | ---: | --- |
| Original 10248_021033910048_LW.pdf | 8 | 0 | No original false findings remain |
| R02_v1 | 9 | 1 | [188], physical PDF page 45 |
| R02_v2 | 9 | 1 | [199], physical PDF page 46 |
| R02_v3 | 9 | 1 | [177], physical PDF page 45 |
| M01 | 8 | 0 | No injected R2 violation |
| M02 | 9 | 1 | [188], physical PDF page 45 |

All retained native finding objects, including coordinates, are equal to the
pre-fix result after removing only the original eight false findings. The
uncited-reference check's results are unchanged on all six real PDFs. The full
runPaperLint path independently confirms these messages, outcomes, coordinates
and live/final agreement; only native admission and five_rule_detector.py may
run, with Node and Python network guards enabled.

Local complete five-rule unittest set: 109 passed. Isolated Linux related native
suite: 250 passed, 5 subtests passed. Admission/stream/archive integration: 33
passed. Initial new tests failed on the old code; independent review exposed
two further Important cases (trailing tensor dimensions and genuine citation
prose). Both were reproduced RED and fixed GREEN in one pass. Whole inline
shapes are handled together; noun-plus-symbol alone no longer suppresses a
citation. No Critical findings remained; each Important finding is covered by
both missing-reference and uncited-reference assertions.

GitHub main was independently re-read at c5b5c8f through the connector and local
Git. For publishing, an SSH reverse tunnel on server loopback forwards GitHub
TLS to this computer's working connection; Git still verifies github.com's
certificate. Original deployment CLI bytes will be restored before closing the
tunnel. No campus access, model/API calls or unrelated UI changes are involved.
