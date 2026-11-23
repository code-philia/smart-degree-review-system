# Account login announcement implementation plan

**Goal:** Publish the approved feedback notice once per account, for both existing and newly created users.

**Approved UI:** 484px maximum-width card; Chinese-only title “欢迎反馈” and button “开始使用”; bilingual notice label, descriptions, WeChat link and feedback spotlight. No decorative emblem, one-time-display caption or “direct communication” caption. English uses Segoe UI/Arial. Button minimum width 112px with a light visible keyboard focus outline. WeChat URL: https://feedback-chat-5d9.pages.dev/.

**Architecture:** Authenticated AppShell requests an atomic, account-scoped announcement claim. A dedicated SQLite receipt table records a fixed announcement version, authenticated user ID and idempotency token. The approved dialog renders only for a successful first claim. Repeated authentication, refreshes and other browsers get no further claim. Local, trial and jAccount sessions share the existing authentication middleware. Authentication redirects and reports remain unchanged.

**Delivery semantics:** Receipt is recorded when the server grants the display, not in browser storage. Retrying the same request token returns the original grant; different tokens for an already recorded account do not. A bounded client retry reuses the token. A page abandoned before rendering cannot prove human readership; the record represents the granted login announcement. Session restoration is an authenticated entry and follows the same account rule.

**Execution:** Inline implementation using executing-plans; one independent whole-change review before main integration. User has approved implementation, testing, main push and external deployment.

## Task 1 — Persistent authenticated claim

- [x] Write a failing HTTP test for authenticated-only claim access.
- [x] Add user_announcement_receipts through idempotent database initialization; preserve existing tables and records.
- [x] Add backend/src/auth/announcementService.js and the authenticated claim endpoint in authRoutes.js.
- [x] Verify existing/new users, all session identities, multiple browsers, concurrency, same-token retry, invalid requests, account isolation and database restart/migration.

## Task 2 — Login UI integration

- [x] Write failing AppShell tests for first display and returning-user suppression.
- [x] Add frontend/src/api/announcements.ts, AccountAnnouncement.tsx and the approved FeedbackAnnouncement.tsx/CSS.
- [x] Connect a real feedback-trigger ref through SystemFeedbackDialog and mount the account coordinator in AppShell.
- [x] Verify StrictMode, account changes, stale responses, bounded retry, dismissal, focus return, keyboard access, invariant bilingual content and exact link attributes.
- [x] Run relevant session, callback, AppShell, feedback, locale and build checks; inspect rendered approved UI.

## Task 3 — Review and publish

- [x] Independent review; resolve material findings and rerun affected checks.
- [x] Commit only reviewed product code/tests and this plan; exclude private preview fixtures and unrelated work.
- [x] Verify current official main and active external version before integration.
- [ ] Use the standard publisher, allowing only the new receipt table as a database migration; preserve all original tables, PDFs, private configuration and user work.
- [ ] Verify healthy release, published assets and official main; provide exact version and validation results.

**Verification:** 156 backend tests and 91 frontend tests passed. Production Vite build passed. Three pre-existing TypeScript diagnostics were reproduced on the exact base and are unchanged. Independent review resolved transaction rollback and shared-cookie account-race findings; final review ready to merge. Real component checked at desktop and 375px in English; approved bilingual content and focus return preserved.
