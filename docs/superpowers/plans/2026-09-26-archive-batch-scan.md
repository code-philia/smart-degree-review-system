# Archive Batch Scan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run any selected subset of four local rules against every archived PDF and let administrators review persistent, located results.

**Architecture:** SQLite stores one job and one result row per paper; an in-process, restartable sequential worker calls the existing Python detector on original paths. New admin-only APIs provide progress, filtered results and safe PDF streaming; React pages reuse the paper-lint viewer.

**Tech Stack:** Express 5, sqlite3, PyMuPDF detector, React 19, React Router 7, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-26-archive-batch-scan-design.md`

## Global Constraints

- Archive root: `/opt/sjtu-archive-479`, configurable for tests; do not duplicate or mutate PDFs.
- Rule IDs: `sjtu_rule_18`, `sjtu_rule_22`, `sjtu_rule_24`, `sjtu_rule_28` only.
- One active job at a time; persist after every document and resume after restart.
- Admin-only routes and navigation; do not accept arbitrary filesystem paths from clients.

## Review Focus

- Corrupt or encrypted PDF: record a per-paper failure and continue.
- PDF above 50 MB: scan from disk and stream via Range request.
- Service restart mid-paper: resume unfinished paper without duplicate completed results.
- Path traversal or symlink: reject original-file access outside the archive root.
- Unavailable detector: mark paper failure while retaining other results and task progress.

---

### Task 1: Persistent job repository

**Files:** `backend/src/database/init_db.js`, new `backend/src/normative/archiveScanRepository.js`, new `backend/tests/archive-scan-repository.test.js`.

**Interfaces:** `createJob({userId, ruleIds, documents})`, `listJobs()`, `getJob(id)`, `listResults({jobId, ruleId, outcome, query, page})`, `getResult(jobId, documentId)`, `markResult(...)`, `resumeIncompleteJobs()`.

- [ ] Write failing repository tests for creation, progress, filtering, and restart recovery.
- [ ] Add tables and repository methods; rerun focused tests.

### Task 2: Scanner and worker

**Files:** new `backend/src/normative/archiveScanService.js`, `backend/src/index.js`, new `backend/tests/archive-scan-service.test.js`.

**Interfaces:** `listArchivePdfs(root)`, `startJob({userId, ruleIds})`, `resumeJobs()`, `archivePdfPath(jobId, documentId)`. Inject detector and archive root for tests.

- [ ] Test actual PDF enumeration, selected-rule validation, one-job limit, failed-paper continuation, and resume.
- [ ] Implement sequential worker using `runLocalFiveRules(pdfPath, ruleIds)` and checkpoint after each paper.

### Task 3: Authenticated API and PDF streaming

**Files:** new `backend/src/normative/archiveScanRoutes.js`, `backend/src/normative/normativeRoutes.js`, new `backend/tests/archive-scan-routes.test.js`.

- [ ] Test role restrictions, start/list/detail/results endpoints, path safety and HTTP Range.
- [ ] Add routes under `/api/normative/archive-scans`, with admin-only middleware.

### Task 4: Frontend task experience

**Files:** new `frontend/src/api/archiveScans.ts`, new `frontend/src/pages/ArchiveScanPage.tsx`, `frontend/src/pages/NormativeCheckPage.tsx`, `frontend/src/pages/NormativeReportPage.tsx`, `frontend/src/App.tsx`, new `frontend/tests/archive-scan-page.test.tsx`.

- [ ] Test third tab, single/multi-rule start, progress, task history, role visibility, and navigation.
- [ ] Implement four rule cards, selection bar, polling progress, saved tasks and paginated results.

### Task 5: Paper drilldown and PDF location

**Files:** new `frontend/src/pages/ArchiveScanResultPage.tsx`, `frontend/src/components/paperLint/PdfPane.tsx`, `frontend/src/components/paperLint/Workspace.tsx`, `frontend/src/App.tsx`, tests for report and PDF URL loading.

- [ ] Test document result, rule statuses, PDF source URL, and location click.
- [ ] Extend PDF viewer input to support authenticated same-origin URL and reuse finding overlays.

### Task 6: Release

- [ ] Run focused and complete backend/frontend tests, lint, typecheck, formatting and build; compare historical formatting failures.
- [ ] Push the feature commit to GitHub main and deploy with the handoff script, without a database backup.
- [ ] Verify public route, API authorization, service health, active release and clean source worktree.
