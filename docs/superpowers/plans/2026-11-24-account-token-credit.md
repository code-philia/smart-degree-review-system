# Account token credit implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable one-time account ¥100 token credit, the approved live UI and external deployment.
**Architecture:** Add account/operation/call tables to the existing SQLite database. Node establishes immutable job operation context; Python reserves and settles each real model transport against the same database. The UI reads authenticated live credit and displays only estimates beside selected model rules.
**Tech Stack:** Existing Express/sqlite3, Python sqlite3/contextvars, React/TypeScript/Vitest/pytest; no new runtime dependency.
**Spec:** docs/superpowers/specs/2026-11-24-account-token-credit-design.md

## Global Constraints
- User authorized implementation, main push and external release; no additional approval step.
- One-time100 CNY for every account; replace three-report admission. No historical charges or report mutation.
- Rates per1M tokens: ordinary input1 CNY, cached input0.02 CNY, output4 CNY; version snapshots retained.
- Qwen translation/local rules/cache reuse free. Only four review rules billable. Unknown/missing usage is audited, never invented.
- Integer nanoyuan storage; no negative available credit, duplicate debit or browser-controlled ownership/pricing.
- Preserve existing model prompts/detectors, pacing/429 queue, source PDFs, private config and unrelated WIP.
- Approved local credit UI and original selection controls; Chinese/English parity; no unrelated copy edits.

## Review Focus
- Cancellation or service restart while a request is in flight must not release a live worker's reservation or lose already settled charges.
- Concurrent rules, typo child threads and multiple jobs must retain exact rule/account attribution and atomic spending.
- Malformed model content with valid usage must still settle; invalid/missing usage must not become a fabricated debit.
- Cache hits, rejected PDFs, reused report rules and Qwen must incur no new charges.
- Account changes, late HTTP responses and cross-tab activity must never show another account's balance.

### Task 1: Persistent credit and authenticated API
**Files:** shared/paper-lint-credit-policy.json; backend/src/database/credit_schema.sql; backend/src/database/init_db.js; backend/src/normative/paperLintCredit.js; paperLintQuota.js; paperLintJobRepository.js; reviewPilotPaperLintRoutes.js; backend/tests/paper-lint-credit.test.js.
**Interfaces:** getAccountCredit(userId), beginCreditOperation(jobId), finishCreditOperation(operationId), recoverCreditOperations(); credit context {database_file,operation_id}.
- [x] Write failing tests: existing/new grants once, restart/migration, account isolation, >3 free jobs, zero-credit paid refusal/free admission, idempotent submit, authenticated credit API and durable ledger after report deletion.
- [x] Run backend focused tests and observe RED before implementation.
- [x] Implement additive schema, grant trigger, Node operation lifecycle/API and new balance admission; legacy quota API reports no report-count limit.
- [x] Run focused backend tests GREEN; commit task.

### Task 2: Per-request token accounting
**Files:** backend/paper_compiler/account_credit.py; backend/scripts/run_bilingual_semantic_lint.py; backend/tests_py/test_account_credit.py; backend/tests_py/test_credit_rule_transport.py.
**Interfaces:** billing_rule(rule_id) context manager; bill_model_request(payload,send,rule_id=None) preserves returned raw response and raises CreditError on insufficient credit.
- [x] Write failing tests for nanoyuan/cached arithmetic, missing/invalid/cache details, idempotency, parallel reserve, failure/429 release, known usage before content parse, stale context, cross-process reserve, zero balance/Qwen/free exclusions and child-thread attribution.
- [x] Run pytest to observe RED.
- [x] Implement reserve/settle/release in SQLite transactions, per-call IDs/rate snapshots, operation ownership validation and scoped transport wrapper inside each actual send.
- [x] Bind each semantic worker's rule; explicitly propagate typo chunk attribution. Preserve cache and all detector request contracts.
- [x] Run credit and existing semantic/campus request suites GREEN; commit task.

### Task 3: Worker lifecycle and recovery
**Files:** backend/src/normative/paperLintJobService.js; reviewPilotPaperLintService.js; backend/tests/paper-lint-credit-lifecycle.test.js.
- [x] Add failing integration tests for job-owned environment, retries, cancellation, partial results, recovery and free path.
- [x] Establish credit operation from stored job, supply context only to paid worker, strip inherited credit env from other subprocesses, and finish only after child shutdown.
- [x] Recover old operations conservatively, retaining live-worker reservations until response or process exit. Never recharge reused rules.
- [x] Run backend job, cancellation, report, queue and credit suites GREEN; commit task.

### Task 4: Approved live frontend
**Files:** frontend/src/api/paperLint.ts; frontend/src/hooks/usePaperLintCredit.ts; frontend/src/components/paperLint/PaperLintCredit.tsx and CSS; ThesisUploadPanel.tsx; NormativeCheckPage.tsx; frontend/src/i18n/locale.js; related tests.
- [x] Write failing account isolation/refresh, live ring/percentage, estimate/free-rule and zero-balance free-start tests.
- [x] Replace quota-count hook/UI with authenticated credit, request/focus/visibility/active-run polling and safe owner-bound updates.
- [x] Port approved private preview layout/styles and original selection controls to product; preserve other copy and update only the three-review clause in both languages.
- [x] Verify Chinese/English narrow/desktop, theme, details, keyboard and correct paid-only disabling. Build and run focused frontend tests GREEN; commit task.

### Task 5: Real request verification and release
**Files:** private output/token-credit-20261124 implementation verification; docs deployment record.
- [x] Run isolated real archived-paper checks with new formal billing context, preserving production reports. Compare actual returned usage to stored per-rule charges; verify warm-cache zero charge and free/Qwen path.
- [x] Run complete accounting failure/concurrency type matrix and relevant detector regressions; inspect exact changed files.
- [x] Independent whole-branch review per requesting-code-review skill; fix material findings with RED/GREEN tests and rerun affected suites.
- [ ] Recheck remote main, merge/commit only scoped changes, push main and deploy through existing guarded Publisher. Allow only the new credit schema/trigger and one-time account grants in database preservation checks.
- [ ] Verify active release, service health, authenticated live balance, served assets and historical report/PDF preservation; give exact version and test evidence.
