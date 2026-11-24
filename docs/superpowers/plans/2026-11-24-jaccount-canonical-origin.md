# jAccount Canonical Origin Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this scoped deployment repair.

**Goal:** Keep campus login and all browser navigation on `https://thesis-review.sjtu.edu.cn`, and verify the existing first-return fix.

**Architecture:** Repair the confirmed stale campus callback and insecure HTTP cookie setting in protected server configuration. Commit the matching nginx deployment template and a credential-free hand-off check; preserve the existing authentication code, external origin and all saved data.

**Tech Stack:** nginx, systemd, Python standard library, existing Node/React auth regression suites.

## Scope and verification

- [x] Run the hand-off check against the current campus deployment and observe callback-origin/Secure failures.
- [x] Verify nginx canonical redirects, HTTPS gateway forwarding and loopback access using the actual nginx binary and temporary listening ports.
- [x] Run existing callback, concurrent-attempt, private-admin and frontend first-return regression tests: 138 backend and 36 frontend tests pass.
- [ ] Review the diff, commit and fast-forward remote main without changing the formal-login branch.
- [ ] Deploy the same main revision to both services. Back up protected campus config, nginx and databases; update only the campus callback, cookie setting and canonical entry points. Preserve external config.
- [ ] Verify HTTPS login hand-off, old IP redirects, homepage/report routes, service health, release identities and saved account/report data. Retain rollback backups.

Baseline limits: `frontend/tests/login-routing.test.tsx` has 10 pre-existing failures expecting the removed public password form; it is outside this configuration repair. Backend auth tests use Node 22.23.2 because Node 24 with the cached Vitest runner fails during CommonJS/ESM loading before test execution. No real jAccount credentials were used.
