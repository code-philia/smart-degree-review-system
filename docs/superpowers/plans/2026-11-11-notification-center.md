# Notification center implementation plan

> Execute inline with superpowers:executing-plans. Verify each stage before continuing.

**Goal:** Add a bell between Pilot and Feedback with a small red unread dot, readable complete filenames and persistent read state.

**Architecture:** Derive report-ready, mail-sent, detection-failed and terminal mail-failed notices from existing per-user jobs, reports and outbox. Store only read receipts and a first-activation timestamp. Reuse Radix Popover, existing theme tokens and locale store. No detector, mail sender or PDF layout changes.

**Tech stack:** Express, SQLite, React, Tailwind, Radix, Vitest and Testing Library.

**Design:** Existing header proportions remain intact. A 36px bell button has an 8px red dot. The 420px maximum panel uses title, full filename, short explanation, timestamp and an icon-before-text action. Natural filename wrapping, internal scrolling, readable dark colors, reactive Chinese/English. Opening does not mark all read; item actions and explicit Mark all as read do. No notification flood from pre-activation history. Mail sent means accepted for sending, not confirmed inbox delivery.

**Approach:** Read-only derived events avoid changing report/mail transitions and unnecessary content copies. A separate event-emission pipeline would touch critical detection paths. Browser-only read state would fail across devices, so receipts belong to the authenticated user in SQLite.

## Constraints and review focus

- Preview only; production remains on abb6f2b until user asks to release.
- Preserve existing report JSON, user data, processing rules and layout; no real mail in preview.
- Every query and acknowledgement must enforce the authenticated owner, including administrators.
- An old or out-of-order response must never overwrite a new account or a read action.
- Mark all affects current notices only; later arrivals remain unread.
- Full filenames and original source text remain unchanged under locale switching.

## Task 1: Authenticated feed and read receipts

Files: backend/src/notifications/{notificationRepository,notificationRoutes}.js; backend/src/database/init_db.js; backend/src/app.js; backend/tests/notifications.integration.test.js.

- [x] Write integration tests; observe missing route fail.
- [x] Add activation marker and receipts, own-user derived feed and bounded acknowledgements.
- [x] Test four events, access control, read persistence, cutoff, cancelled jobs, retries, deletion and unchanged source data.

## Task 2: Header bell and panel

Files: frontend/src/{api/notifications.ts,components/NotificationBell.tsx,layout/AppShell.tsx}; frontend/tests/notification-bell.test.tsx.

- [x] Write component tests; observe red state before implementation.
- [x] Build panel using current components and theme tokens; red dots, clear filenames, bilingual copy.
- [x] Test read actions, empty/error states, switching language/account and late responses; build production assets.

## Task 3: Isolated preview and review

- [x] Restart only preview with sending disabled; seed own QA fixture notices backed by copied real report.
- [x] Visually inspect Chinese/English, light/dark, long filenames, narrow window, keyboard and read persistence.
- [x] Fresh whole-branch review, address substantive findings and rerun relevant checks.
- [x] Deliver preview and actual screenshots; do not deploy production.


## Verification ledger (2026-11-11)

- Remote main verified through GitHub branch API: abb6f2ba5a7775128bbb57121d8dfeab24b23e4d. Feature branch created in the existing sole development directory.
- Backend integration tests exercised all four notices, exact filenames, admin/owner isolation, malformed requests, bounds, read persistence, rollout cutoff, cancellations/retries, deletion and unchanged source results. Initial route and migration tests failed before implementation.
- Final related suites: backend 62 tests and frontend 15 tests passed. Production frontend build passed. No full-suite claim.
- Fresh reviewer found safe-error-response and read-retry issues; both reproduced, fixed, regression-tested and independently rechecked.
- User steering: unread dot is red; removed repeated footer unread count; header items share vertical center. English narrow header uses a shorter accurate action and a compact accessible count at <=380px, without shrinking fonts.
- Actual browser: Chinese light and English dark checked, full filenames wrap, report link works, unread 5 -> 4 -> 0 and reload retains reads. English 390px centers equal with 11.73px gap; 320px centers equal with 21.59px gap, no panel overflow. Restored default viewport and left Chinese light preview open.
- Preview fixtures are confined to the existing own QA account/database, copied from a real saved 79-page report. They do not invoke detection or send email. Verified REPORT_EMAIL_ENABLED=0 and isolated ARC_DB_FILE before seeding.
- Production release, original report JSON and mail processing code remain unchanged. No production deployment or push in this task.
