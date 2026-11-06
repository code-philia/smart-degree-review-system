# Mandatory background core structure implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, with one whole-branch independent review.

**Goal:** Always surface core structural defects and prevent dependent checks from falsely passing, while preserving optional frontend selection.
**Architecture:** Reuse validated admission structure; create/merge a background core run and derive unavailable-rule reasons in a shared backend helper. Preserve implicit runs in orchestration, jobs and display filtering. Leave upload checkboxes unchanged.
**Tech Stack:** Node/Python, React/TypeScript, Vitest/pytest and native PyMuPDF.
**Spec:** `docs/superpowers/specs/2026-11-06-mandatory-core-structure.md`

## Global constraints

No OCR or live model/API calls. User selection stays unchanged. Non-papers blocked. No new dependencies or database migration. Guarded external deployment only.

## Review focus

- Unselected completeness still reports missing or incomplete CN/EN abstracts; no duplicates when selected.
- Complete English articles/theses avoid Chinese-only structural requirements.
- Missing abstract/keywords gives unavailable keyword count; bibliography rules remain executable.
- Background structural findings survive incremental merging/progress, archive-only selections and report/export filters.
- Non-paper and malformed/stale proofs still block all detectors.

### Task 1: Background structure and dependencies

Files: new backend `paperStructureChecks.js`; both dispatchers, job progress merge, local keyword detector fallback; focused backend/native/frontend regressions; FindingsPane and detection scope expose automatic results without changing checkbox controls.

- [x] Write failing tests for mandatory core findings, duplicates, prerequisites, incremental merge and single-rule keyword execution.
- [x] Implement shared logic, wire live/final/archive results, and preserve requested IDs.
- [x] Run real native missing-abstract/keyword/complete/non-paper fixtures and relevant suites with network guards; verify no new baseline failures.
- [x] Fresh independent review, fix significant findings with RED/GREEN regressions.
- [ ] Merge/push main and perform guarded external prepare/deploy, verify actual running release and served assets.
