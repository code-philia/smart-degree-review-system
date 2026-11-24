# Supervision Console Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement the tasks in this session, with independent review before main integration.

**Goal:** Deliver the owner's Chinese-only read-only administrator console on both deployed sites.

**Architecture:** Exact admin identity and a distinct supervision session; dedicated login and scoped GET APIs; independent React shell and report/feedback views. Reuse existing report presentation and PDF navigation without changing student ownership checks.

**Spec:** `docs/superpowers/specs/2026-11-24-supervision-console-design.md`

**Tech Stack:** Existing Express, SQLite/bcrypt, React/TypeScript, lucide, Vitest and local CSS.

## Constraints and review focus

- Username admin; same password as the four local accounts; no credential literals in new source or frontend.
- Chinese administrator UI; ordinary bilingual UI and formal-login preview unchanged.
- No new schema or dependencies, no model calls and no modification/deletion of saved user data.
- Reject ordinary/trial/private-admin cookies and forged supervision prefixes at new endpoints.
- Reject supervision cookies at all ordinary protected APIs; allow restoration/logout.
- Parameterize search, bound pagination and ensure stable ordering; support missing PDFs/reports and untrusted feedback text.

## Tasks

- [x] Add failing backend integration cases for dedicated login, other-user report/PDF access, all feedback categories, filtering/pagination and write denials. Run against the baseline in an isolated temporary DB.
- [x] Implement `auth/supervisionPolicy.js`, scoped authentication updates, `supervision/supervisionRoutes.js` and repository; add a guarded provisioning CLI. Run the new and existing authentication/feedback regression suites.
- [x] Add failing frontend tests for the Chinese login, route gates, independent shell, filtering and feedback/report navigation. Implement `api/supervision.ts`, pages and `supervision.css`; use the existing report workspace without mutation callbacks. Run focused frontend tests and production build.
- [x] Inspect local desktop/narrow layouts with the browser, correct visual defects and obtain an independent security/implementation review.
- [ ] Push reviewed commit to main, prepare immutable releases, back up both databases/configs, provision the exact new admin identity and deploy both services. Preserve campus HTTPS canonical-origin configuration.
- [ ] Verify live admin login/restoration, report/PDF/feedback reads and write/ordinary-user denials on both deployments. Verify all old account/report/feedback data and formal preview unchanged. Deliver both admin URLs.

## Verification evidence

- New backend integration and provisioning: 33/33 passing, plus existing authentication and archive coverage (190/191 across the selected nine suites).
- The sole selected-suite failure is the retired sjtu_rule_32 warning-feedback test; identical 404 vs 200 failure reproduced on the unmodified 653671c baseline (11/12 there). The retired rule remains hidden as requested.
- Frontend: 44/44 across five focused console/authentication suites; includes Chinese report findings with uppercase admin URL and lang=en, and persisted light/dark switching.
- Production build passes. Full TypeScript check retains unrelated existing errors; no supervision production errors.
- Real cloned external data: 285 reports across all four stored report types, 10 feedback records; saved suggestion version and original finding reviewed in the browser.
- User additions: larger type and stronger secondary-text contrast; existing appearance preference used for light/dark; both desktop login headings verified at the same y=202 baseline.

- Final user refinements: remove sidebar note and top read-only badge; reposition left login content; category-select search uses strict server allowlists and separate-field tests. Actual dark report surfaces and PDF rendering visually verified.
