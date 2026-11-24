# Campus GUI Audit Plan

> Execute inline with the existing Playwright stack. Parallel source inspection informs coverage; application code must not change.

**Goal:** Run a reproducible GUI audit against https://thesis-review.sjtu.edu.cn/ and deliver scripts, evidence and an honest coverage report.

**Architecture:** Isolated browser contexts with existing trial/admin sessions, explicit live-read/live-write/fault-injection labels, bounded concurrency, exact tracking and cleanup of this run's newly created data. Never seed/reset the deployed database or alter existing reports/feedback.

**Tech:** Playwright Test 1.57.0, Chromium/Edge, Firefox/WebKit where available, axe-core, JSON/HTML/screenshot artifacts.

## Scope and constraints

- User authorized creating uniquely marked GUI_TEST reports and feedback and clearing only those created in this run.
- No fixes, application/configuration changes, commits to main or deployments.
- Preserve existing announcement receipts, notification read states, user settings, reports and feedback; automatic ancillary writes are intercepted.
- Credentials come from environment variables; login traces and storage-state secrets are excluded from deliverable reports.
- Live sessions are established once per account to avoid consuming the production login limiter repeatedly; logout uses a separate session.
- Real jAccount credential exchange cannot be asserted without a jAccount identity. Report that limit explicitly.
- Real browser read flows and injected error states must be reported separately.

## Tasks

- [x] Inspect current route graph/selectors and existing test stack; capture deployed build and initial data IDs.
- [x] Build isolated Playwright harness, safe write guards, session setup, evidence hooks and exact cleanup registry.
- [x] Cover public/admin/student pages, filtering, history, settings, bilingual/theme/responsive/a11y, actual PDF navigation and exports.
- [x] Exercise real newly marked report/feedback lifecycle and intercepted queue/network/credit/error states.
- [x] Run browser matrix, investigate failures as test defect/environment/product issue without fixing product code; retain reproducible evidence.
- [x] Clean only registry-confirmed new records, verify initial IDs/content retained, and deliver Chinese summary and reusable scripts.

Final evidence: 115 distinct cases; known product failures remain asserted. Firefox's five launch failures were resolved with an isolated official browser cache and all five cases passed on rerun, followed by a configuration-only launch check. The final aggregate is 101 passed, 14 failed, zero environment-blocked. Server receipt verifies all original rows across 16 tables unchanged, zero marked rows left, and regenerated feedback archives synchronized. No application code/configuration changed or deployed.
