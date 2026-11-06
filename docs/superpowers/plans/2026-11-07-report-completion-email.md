# Report completion email implementation plan

**Goal:** Notify every new completed detection job by email and deploy to the external host.
**Architecture:** Existing background detection plus a transactional SQLite outbox and a separate SMTP worker.
**Spec:** docs/superpowers/specs/2026-11-07-report-completion-email-design.md
**Constraints:** Administrator recipient is 123090058@link.cuhk.edu.cn; no secrets in Git; preserve report permissions and existing detection behavior; no historical notification backfill.

## Task 1: Identity and transactional notification records

Modify auth schema/session/profile handling and paperLintJobRepository. Add authenticated notification settings and local-user email update. Add outbox records atomically with successful completion. First add integration tests for profile email, administrator routing, missing local email, one completion record and cancellation/failure exclusion; run RED, implement, run GREEN. Baseline auth/job suite: 33 tests passing.

## Task 2: SMTP delivery and report links

Add mail configuration, report email template and leased outbox worker. Add Nodemailer with a locked registry version compatible with Node 22. Test retries, restart leases, concurrent claims, missing configuration, deleted reports, injection, stable Message-ID and summary parity before implementation. Preserve a validated report destination through jAccount login; test malicious redirect rejection. Verify actual Nodemailer MIME serialization offline, without sending real user data. Real SMTP acceptance requires the missing sender credentials.

## Task 3: User interface and release

Show a compact notification destination/settings row and truthful background-progress copy. Add UI tests for configured/unconfigured service, missing local email and administrator fixed destination. Verify visual layout and keyboard behavior. Run relevant suites and frontend build; compare any unrelated existing full-suite failures to main. Obtain one fresh whole-branch review, address material findings, merge/push main and use the existing immutable external publisher. Verify public assets, service health, configuration/data preservation and the new database schema. Real SMTP delivery remains conditional on receiving valid mailbox authorization; do not claim it is enabled without it.

## Review focus

- A process restart must not lose a newly completed job's notification or resend all historical reports.
- Email server failure must not make a saved report fail or occupy the detection queue.
- Role changes, client-supplied addresses and malformed profile fields must not bypass administrator routing or disclose other users' reports.
- Missing mail credentials must not consume delivery attempts or result in misleading success text.
- Login from an email must preserve only a same-app report path, with authorization checked after login.

User follow-up: prioritize a prominent, harmonious front-end ETA notice. Estimate a single remaining-time number from comparable recent jobs and queued work; insufficient history says estimating, and elapsed jobs beyond the estimate say overdue. Store a new started_at timestamp. When SMTP is not configured, do not promise email delivery; explain report availability in history.
