# Account token credit — verification record

Scope: one-time account credit, actual model token settlement, the approved upload interface and replacement of the three-report cap. Source base: `a64d5a3de3bb8afa6d2847df1a570d626b662e38`.

## Verified behavior

- Existing/new account grants are idempotent. Restarting initialization cannot reset spent funds. Roles have no billing exemption.
- Atomic integer reservations prevent thread/process/account races and overdraft. Actual usage and tariff snapshots determine settlement; duplicate receipts cannot debit twice.
- Cached input is priced separately. Missing/invalid usage is recorded without guessed charges. Valid usage settles even if answer content is malformed.
- Rejected/failed/429 attempts, cancellation, live-worker reservations and stopped-worker recovery are covered. Service recovery reuses durably completed rules and preserves report metadata, avoiding repeated debit for completed work.
- Qwen translation, local rules, response-cache reuse and report viewing/exporting do not debit credit. A zero balance still permits free checks. Deleting reports does not refund or erase the ledger.
- Live credit is authenticated and owner-bound. Late responses from a previous account cannot replace the current account's balance. Active checks refresh every two seconds; idle/focus/cross-tab refresh is covered.
- Chinese/English product components, responsive layout, balance details, rule order, original selection controls and approved estimates were inspected. No detector prompt or detection criterion was changed.

## Automated verification

- Backend: **93 passed**, 12 focused credit/job/auth/announcement/progress/queue/stream/API suites, in an isolated server checkout.
- Python: **53 passed**, accounting, actual transport entry, cache, thread attribution, native-only typo and campus queue tests.
- Frontend: **41 passed** across four credit/upload/announcement/compatibility suites; production Vite build passed.
- Additional existing PDF gzip test fails with `body.stream is not a function` in local jsdom. The same failure was reproduced from an immutable source archive of the base commit. Three stale-fixture failures in `NormativeCheckPage.jobs` were also observed before implementation. Neither is represented as a passing test.
- Backend Node 24 tests preload the existing shared ESM presentation module to avoid an independently reproduced baseline CJS/ESM import-order race. This is a test-only invocation option, not a runtime code change.

## Real archived-paper verification

All four paid rules ran against archived paper 5, original PDF SHA-256 `3238231ea4d51bb941fa5d5a835f1b97f93c791434f2549571dc92c0479b6d5f`.

The isolated SQLite ledger contains **56 settled real calls**, totaling **¥0.240266** across the verification runs. Every receipt was recomputed from its returned ordinary/cache/output token counts and stored tariff; the sum matches the account debit. No reservations remain. A warm keyword response-cache rerun made zero calls and incurred zero additional debit. Numeric verification and independent abstract review can intentionally make fresh calls, so they are not incorrectly characterized as globally free reruns.

The initial combined run hit an existing shared-IR concurrency failure in the typo detector (`dictionary changed size during iteration`); that rule produced no receipt or charge. Sequential verification of the unchanged detector then completed with 33 settled typo calls. This unrelated detector issue was not broadened into this accounting release or claimed repaired. Original PDFs and production reports were not modified.

## Independent review and release

Whole-branch read-only review identified restart replay and a recovery report-shape regression. Both received failing regression tests, narrow fixes, green reruns and a final **Ready to merge: Yes** review.

Deployment must use the unchanged guarded Publisher, exact reviewed source and official-main proof. Migration permits only the three credit tables, the one-time grant trigger and corresponding account grants. Existing report/PDF/configuration/WIP preservation and authenticated live balance are verified at activation; private release receipts record the final deployed revision.
