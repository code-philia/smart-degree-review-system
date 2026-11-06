# Detection stability merge implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, with one final independent review.

**Goal:** Merge the named branch into main while allowing partial genuine papers and blocking non-papers.
**Architecture:** Retain both histories, resolve admission contracts, and make evidence dependencies section-specific.
**Tech Stack:** Python/PyMuPDF, Node, TypeScript/React, pytest/Vitest.
**Spec:** `docs/superpowers/specs/2026-11-06-detection-stability-merge.md`

## Global constraints

No OCR or live model/API calls. Preserve unrelated work. Push main after verification; no deployment in this request.

## Review focus

- Non-paper cannot become Paper through partial opt-in.
- Missing and incomplete abstracts both produce consistent partial proofs.
- Missing English abstract cannot disable bibliography checks.
- Missing bibliography leaves R6 and independent rules executable and dependent runs explicitly unavailable.
- Full papers preserve prior fixes and genuine-paper admission.

### Task 1: Integrate and verify

Files: the incoming branch's 24 files, conflict files `backend/paper_compiler/document_admission.py` and `backend/src/normative/paperDocumentAdmission.js`, dependency handling in both dispatchers, and focused regression tests.

- [x] Read branch changes and issues #5, #6, #9, #10; baseline admission Python 86 passed; Node 20 passed / 8 Linux-only skipped.
- [x] Add tests for missing/incomplete partial compilation, non-paper rejection under opt-in, malformed proofs, dependency isolation and UI unavailable states; run before conflict resolution to confirm failures.
- [x] Resolve conflicts preserving main diagnostics and incoming partial compilation. Correct evidence dependency isolation with shared logic.
- [x] Run focused and related Python/Node/frontend regressions, six PDF manifest contracts without live LLM, and native original/missing-section/non-paper PDF checks. Run Linux-only dispatcher tests in isolated server scratch if needed.
- [x] Verify frontend build and compare existing typecheck diagnostics with base. Obtain fresh whole-branch review, resolve significant findings with regression tests.
- [ ] Commit merge; fast-forward main; refetch and push without force. Verify remote main contains both parent tips.

Final review fixes, each reproduced before correction: propagate partial structure into the compiler CLI; preserve typo source location when reducing a word to one character; retain resource outages alongside confirmed reference findings; supply a complete report envelope for all-unavailable archive selections. Verified on Linux: Python 241 tests plus 31 subtests, Node 77 tests. Frontend related 67 tests passed. Full frontend suite retains the same 83 failing tests as clean main, with no newly failing tests; nine TypeScript diagnostics and one legacy archive adapter test also reproduce on clean main. Detailed logs and native acceptance evidence are retained outside Git under `output/merge-issues-5-10-20261106` in the project evidence root.
