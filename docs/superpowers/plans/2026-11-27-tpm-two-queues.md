# TPM two-queue implementation plan

> Execution: inline using executing-plans and test-driven-development; fresh whole-change review before publication.

**Goal:** add TPM reservation before external model dispatch, retaining separate TPM and RPM queues.

**Architecture:** extend the existing SQLite coordinator with token waiters and reservations; acquire TPM budget before entering the unchanged paced/concurrent dispatch queue; reconcile validated usage afterward.

**Spec:** ../specs/2026-11-27-tpm-two-queues-design.md

## Constraints

- Preserve100RPM paced dispatch, external32API slots and existing429retry; no campus deployment.
- Keep model parameters and rule verdict logic unchanged.
- Preserve prior stopped drafts in output/tpm-two-queues-20261127/preexisting; exclude their unrelated rolling-RPM changes from publication.
- Pressure benchmarks remain stopped. User already authorized implementation, push and external deployment; no extra approval gate.

## Review focus

Missing usage, cancellation at either queue, process death with in-flight work, racing processes, and long waits must not lose budget or leak slots.

## Tasks

1. [x] Add failing coordinator/transport tests in backend/tests_py/test_campus_token_budget.py. Run and observe the missing TPM behavior.
2. [x] Implement token_waiters/token_reservations, estimator and settlement in backend/paper_compiler/campus_requests.py; wire payloads through paper_compiler/llm.py and scripts/run_bilingual_semantic_lint.py. Run new and existing campus/semantic/credit tests.
3. [ ] Review the whole change, fix evidenced defects with tests, perform a short real-model validation, commit and push main. Deploy external only with the official publisher, verify active source, two-queue behavior, health and preserved data.

## Ledger

Current worktree is already isolated; no additional worktree created. Existing source baseline d5210b2. Three pre-existing dirty files backed up byte-for-byte before restoring the production baseline for this feature. The old untracked rolling-quota test remains untouched and is not the specification for this change.

Task1: complete. RED:27 new checks failed on the production baseline (missing estimator/budget APIs and unthrottled transports); cross-process check included in GREEN. Task2 initial GREEN:28checks passed. Two added edge checks failed first (pre-send scope cancellation retained budget; extreme valid actual usage overflowed SUM), then passed after fixing the admission transition and saturating accounted usage at the configured limit. New suite30passed. Existing credit transport mocks updated to accept the payload keyword. Windows baseline had50passed/1failure in a Linux /proc-dependent killed-owner test before implementation; full Linux verification is required before publication.

Final review: fresh reviewer found4Important items, all accepted: slow socket responses needed renewable transport/budget leases; preflight CreditError needed an explicit unsent classification; pending reservations needed bounded expiry independent of PID reuse; migration needed an unknown-usage quiet window. Added5cases, observed4failures and1post-send control pass, then implemented heartbeat renewal, bounded pending leases, RequestNotSentError only around billing preflight, and a one-time persisted60s migration hold. External publisher uses systemd KillMode=control-group; verify old owned workers are gone when switching releases. Regression mocks for semantic cache now accept payload; a stale CLI progress fixture must supply the current CLI arguments. No pressure test resumed; no campus deployment.

Task2: complete. Final local regression258passed/1baseline Linux-only case deselected. External Linux, same candidate source:259passed in22.70s, including real multiprocess budget sharing and dead-owner cleanup. Whole-change review has no deferred minors; stopped benchmark drafts and campus deployment remain outside the user's active scope. Live validation and official external publication are Task3.

Task3 validation: candidate coordinator SHA256bf2d1d9637cac406cbc022ea957e83f78706875cda65a833ad2e82ed15fa656a. Two tiny real API requests using an isolated36token local budget both returned200 (10actual tokens each). Before the second send, token_waiters=1, RPM waiters=0 and API leases=0; second HTTP began60.194seconds after the first response completed; zero429. This is a functional smoke check, not a resumed pressure benchmark or a change to the school's quota. Official external publication follows the user's existing push/deploy authorization.
