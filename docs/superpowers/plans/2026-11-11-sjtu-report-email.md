# SJTU Report Completion Email Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, then one independent whole-branch review. Steps use checkbox syntax.

**Goal:** Send report completion notifications through the approved SJTU notification API using the verified sender account, with thesis name, result summary and an authenticated report link.

**Architecture:** Preserve the existing report completion transaction, outbox, retry policy, recipient policy, mail template and SMTP behavior. Add an explicitly selected `sjtu-notification` provider with cached password-grant OAuth tokens and bounded HTTPS requests. Keep all credentials outside Git. Apply a deployment cutover date so old queued notices remain untouched.

**Tech stack:** Node 22 built-in fetch, existing CommonJS backend, SQLite outbox, Vitest. No new dependency.

**Spec:** User request in this chat and https://developer.sjtu.edu.cn/api/notification.html. Existing design: 2026-11-07-report-completion-email.md. Verified password grant: gs.xwb1 succeeds; dlu fails. Never log credentials or tokens.

## Global constraints
- Do not change Chinese/English UI, PDF layout or detection verdict logic.
- Keep the default SMTP provider compatible; require explicit selection for SJTU.
- Use only the official HTTPS OAuth and notification endpoints, no redirects, 15/20-second timeouts.
- SMTP/API transport failures never change a completed detection or discard its report.
- Test recipient for student01 remains 123090058@link.cuhk.edu.cn.
- Retain 39 pre-existing pending notifications without automatically sending them.
- Credentials are private server files, permissions 0600, and are never committed.

## Review focus
- A 200 response with a failed business status must not mark an email sent.
- A stale token must not duplicate accepted submissions; renew only after an explicit 401 rejection.
- Configuration changes must not reuse another sender's token.
- Unconfigured or invalid provider settings must fail closed.
- The cutover boundary must not deliver old notifications or alter their attempts.

## Task 1: Add and test the SJTU transport
Files: backend/src/notifications/mailConfig.js, new sjtuNotificationSender.js; tests/report-email-sjtu.test.js.
- [ ] Write failing tests for provider configuration, exact OAuth/notification contract, reuse/expiry, config isolation, malformed/failed replies and unauthorized retry.
- [ ] Observe red; implement minimum configuration validation and createSjtuNotificationSender({request,now}) returning async send(mail,settings).
- [ ] Validate returned notification id and errno=0, use Authorization header, keep secrets out of errors.
- [ ] Run provider tests and existing MIME tests green.

## Task 2: Integrate the existing outbox
Files: backend/src/notifications/reportEmailService.js; tests/report-email-delivery.test.js.
- [ ] Write a failing test proving a cutover excludes old queued notifications and sends new notifications.
- [ ] Select transport by explicit provider and apply created_at boundary to queue claiming/unblocking.
- [ ] Keep five attempts, leases, cancellation, recipient policy and report transaction unchanged.
- [ ] Run all report-email and jAccount integration tests. Independent branch review.

## Task 3: Verify real delivery and prepare release
- [ ] Use a real student01 report and the production application credentials to submit exactly one authorized test email to the fixed test recipient.
- [ ] Capture sanitized API receipt; independently verify report link access control. Distinguish API acceptance from confirmed mailbox receipt.
- [ ] Keep production email disabled until reviewed code and explicit activation configuration are ready; record cutover and backup.
- [ ] Recheck remote main, commit/push English Conventional Commits, use the existing deployment authorization and standard publisher when activating; preserve users/reports/detector files.

## User latency follow-up: 2026-11-11

The API accepted the test at 16:33:05 CST; Outlook displayed it at 16:35 and the user confirmed arrival. The user requested faster receipt. Official SMTP on mail.sjtu.edu.cn:465 authenticated successfully. A second authorized test using the same account and recipient was accepted in 1321 ms at 16:41:24 CST; the user confirmed receipt. Prefer SMTP in production, retain the explicit API option without automatic cross-provider fallback.

- [x] Prove the initial worker does not wake for a newly completed job until its next poll (RED).
- [x] After `completeJob` commits a new outbox row, signal `reportEmailWakeup` asynchronously. Subscribe/unsubscribe in the email worker; latch a wake while another drain is active. Keep the 15-second recovery scan.
- [x] Verify a committed report remains completed while delivery is deliberately blocked, and stopping the worker removes the wake listener (GREEN).
- [x] Restrict API token renewal to explicit HTTP 401; forbid unnecessary renewal after HTTP 403 (RED/GREEN).
- [x] Run 105 related mail, authentication and job tests; no detector verdict or front-end changes.
- [ ] Review the added completion wake-up, then deploy code with mail still disabled. Configure SMTP and a fresh cutover only after healthy code activation.
- [ ] Verify old queued rows, users, stored result JSON, shared model rate and public assets remain intact; record live configuration and receipt confirmation.
