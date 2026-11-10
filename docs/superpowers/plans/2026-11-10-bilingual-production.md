# Production Bilingual Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deploy the approved English UI and real bilingual reports without changing Chinese behavior or detection logic.

**Architecture:** Canonical detection remains unchanged. Reviewed static translations plus an owner-authorized Qwen presentation cache serve both UI and exports. Existing source directory and feature branch are used per user instructions.

**Tech Stack:** Existing React/Vite/TypeScript, Express/SQLite, Python MaasClient and BudgetLedger; campus qwen.

**Spec:** docs/superpowers/specs/2026-11-10-bilingual-production-design.md

## Global Constraints

Read the full spec. Source changes only at /data/projects/smart-degree-review-system. No worktrees; preserve .codex-release-build/. Chinese/source evidence and detector/prompts unchanged. Do not deploy or commit another task's files. Only root integrates, commits, pushes and releases. Tests first for new consequential behavior; no paid/model calls from agents unless root explicitly asks. Shared API contract is the spec's translation endpoints/response.

## Task 1 — Owner-authorized Qwen presentation translations (backend)

Files: new backend/src/normative/reportTranslation*.js, backend/scripts/report_translation.py, focused backend/tests and tests_py; narrowly register routes in normativeRoutes.js or reviewPilotPaperLintRoutes.js. Existing auth/repository/ledger patterns remain.

- [x] Read the relevant repositories/routes, model transport and tests; write contract tests for auth/owner isolation, cache/dedupe, no canonical mutation, token protection, partial failure and qwen selection.
- [x] Run tests RED, implement bounded extraction/cache/model adapter/routes, run GREEN. No arbitrary client-supplied text or scope/ID/status translation.
- [x] Record exact commands, results and configuration names in /data/tmp/bilingual-production-20261110/backend-report.md. Do not print credentials or call live model.

## Task 2 — Real frontend locale/runtime/UI (frontend)

Files: frontend/src/i18n/*, main.tsx, real AppShell/AuthPage and relevant report components/hooks/api, English-only CSS, Vite/TS config as needed. Own all frontend except utils/reportExport; coordinate that boundary.

- [x] Review approved preview dictionaries/runtime/CSS and protect-source.cjs as references, plus existing production app and tests.
- [x] Write behavioral tests RED for Chinese preservation, persistence, source protection, current-locale async errors and translation hook resource/revision behavior.
- [x] Integrate shared locale and reviewed UI without preview mocks or custom source-build rewrites. Provide exports getLocale/setLocale/subscribe/translate, preserveText or OriginalText, and useReportTranslations hook contract from spec. Publish exact interface to root/export agent early.
- [x] Connect report/job translation states and retry, refresh after repair generation. Preserve original canonical objects, mounted PDF/results and feedback logic.
- [x] Run focused GREEN and build/type checks; record files/tests/limitations at /data/tmp/bilingual-production-20261110/frontend-report.md.

## Task 3 — Real bilingual exports (export)

Own frontend/src/utils/reportExport/* and export-specific tests only; read i18n interfaces from Task 2 and coordinate imports, do not modify main/UI files.

- [x] Write RED tests for English report formats, original filename/title/evidence/source/protected literals, dynamic mappings and no mutation of Chinese/canonical model.
- [x] Port reviewed preview export protections using normal production imports; preserve page/layout logic. Shared dictionary/dynamic mapping localizes presentation copy. Block incomplete English export via clear error/status as needed.
- [x] Run focused GREEN, generate actual English PDF/DOCX fixture artifacts through real exporters and record paths/tests in /data/tmp/bilingual-production-20261110/export-report.md.

## Task 4 — Root integration, real tests, independent review and external deploy

- [x] Reconcile backend/frontend/export contract and run related/full suites once; classify and reproduce unrelated baseline failures if present. Build production bundle. Review absence of detector/prompt changes.
- [x] Use isolated dev DB/files/runtime and disabled emails; query model IDs and test real Qwen translations against real existing report text, record cache reuse and preserved canonical hashes. Upload a real PDF and inspect asynchronous flow without production writes.
- [x] Browser inspect actual app in Chinese/English, all main pages/dialogs, PDF independence and translation progress/retry. Render actual exported PDF/DOCX; inspect English wrapping and source preservation.
- [ ] Request independent whole-branch review, fix important findings with regression evidence. Confirm remote main again, Conventional Commit(s), merge/push main within authorization.
- [ ] Standard deploy status/check/deploy with backup. Compare production report IDs/JSON/config hashes, release assets, service health and public login/language toggle. Preserve records and rollback on a release defect.

## Review Focus

- Model text or quotes imitate UI dictionary entries; source protection must be structural.
- Language changes during live progress, repair generation or export; no stale locale writes, duplicate model requests or lost PDF/feedback state.
- Cache access after user switch/report deletion, malformed model IDs, number/placeholder corruption, timeout and provider quota failure.
- Existing saved reports and arbitrary semantic messages not present in preview dictionaries; actual English translation, not a mock or English-looking labels only.
- Real PDF/Word pagination and long English strings; original Chinese and report IDs/counts/pages remain identical.

## Integration verification — 2026-11-11

- Root ran 62 related frontend/export tests and a normal production build successfully. Backend translation checks pass 33 JavaScript and 4 Python cases.
- Real isolated 159-page PDF upload, deterministic detection, semantic incremental run, live/saved reports, language switches, history actions, evidence navigation and export UI were exercised. Emails were disabled.
- Real Qwen returned all 129 required mappings; cached response took 20 ms. Canonical report JSON and source PDF hashes stayed unchanged. The deployed service account also completed a genuine Qwen transport check while the detection model remained deepseek-chat.
- Actual English PDF and Word exports were generated and rendered as 12-page documents. English word wrapping and source-language evidence were visually checked. Chinese export content and default pagination match the a86e1e7 baseline byte-for-byte.
- Independent review has no unresolved Critical or Important findings. Full-suite baseline limitations remain: 84 frontend and 22 backend failures reproduced on the original baseline; no claim that the whole existing suite passes.
- Release, production invariants and temporary-service cleanup evidence are recorded outside Git in /data/tmp/bilingual-production-20261110/.
