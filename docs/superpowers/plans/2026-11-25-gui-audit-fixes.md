# GUI Audit Failures Repair Plan

> **For agentic workers:** Use systematic debugging and test-driven development. Independent backend, navigation/layout and accessibility work is dispatched in parallel; root owns history error handling, integration and deployment.

**Goal:** Resolve the 14 failing GUI cases, push the reviewed changes to main, and deploy the identical commit to the campus and public sites.

**Architecture:** Keep the current report, auth, UI and release architecture. Separate saved-finding feedback eligibility from AI-repair eligibility; surface history fetch failures; correct layout containment, focus/layer behavior and accessibility while preserving existing interactions and copy.

**Tech Stack:** React 19, TypeScript, Radix/shadcn, Express/SQLite, Vitest, Playwright 1.57.0.

**Spec:** The user's request to repair all failures in output/campus-gui-20261125/summary.json. Baseline: main 7c74821203138fe3702af804419ade754f0404bb, 115 GUI cases, 101 passing and 14 failures across six defect groups.

## Global Constraints

- Existing Chinese and English copy stays intact; reuse existing translated error components. Administrator pages remain Chinese-only.
- Preserve ownership checks, AI-repair restrictions, historical reports/feedback, credit accounting and unrelated detection rules.
- Keep the alternative login-page branch/service untouched.
- Real tests may create only registered GUI_TEST data and clean only that data; completion emails are already authorized.
- Work in the existing isolated worktree on codex/gui-audit-fixes-20261125; integrate to main only after verification/review.

## Tasks

- [x] Backend feedback: add a failing regression for document_type_check feedback; validate legitimate saved findings independently of repair support; retain wrong-owner/forged-target failures and AI-repair restrictions.
- [x] History: reproduce fetch errors in unit tests, remove the error-to-empty fallback, and verify errors and genuine empty/success states remain distinct.
- [x] Admin/navigation: correct table/page containment at 390/768px, restore feedback-dialog focus and first-Escape behavior; fix admin contrast without copy changes.
- [x] Public/credit/report accessibility: correct failing contrast shades and nested card semantics; retain keyboard/click/PDF/feedback behavior.
- [x] Run focused and full frontend/backend suites, build/type checks, and the existing failing GUI cases before broad verification.
- [ ] Review integrated changes and commit/push main. Prepare immutable releases and backups using existing deployment tools; deploy both sites while preserving environment/canonical domain.
- [ ] Re-run the full campus GUI matrix and public smoke tests, verify registered-data cleanup and both live commits, then deliver updated results/links.

## Review Focus

- A valid report owned by another user must never become a valid feedback target.
- Allowing document-level feedback must not make document-level AI repair available.
- A failed history request must not present a successful empty state or stale other-user records.
- Keyboard navigation must preserve focus and first-Escape dismissal while nested feedback controls remain usable.
- Both themes and languages, narrow layouts, and the independent login preview must retain their current behavior.

## Verification before publication

- 14 targeted compiled-UI browser cases passed on loopback preview using real read-only backend data.
- Feedback/repair/retirement regressions: 34 passed. History regressions: 15 passed. Navigation/admin: 18 passed. Public/credit/report focused suites: 101 passed.
- Production frontend build passed. Full frontend baseline: 836 passed/106 failed; candidate: 850 passed/100 failed, with no new failing test titles. The later account-isolation addition also passed its focused regression.
- Type checking reports the same four baseline errors outside the edited files. Full backend on Windows reports 845 passed/71 failed/38 skipped; changed feedback suite passed, with platform/legacy failures outside the changed scope documented in output logs.
- Independent review found no remaining important issues after clearing stale history rows on account changes. These baseline limitations do not constitute a green full-unit-suite claim.
