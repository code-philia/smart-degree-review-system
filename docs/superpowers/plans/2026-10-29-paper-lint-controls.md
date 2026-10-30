# Paper lint job and report controls

**Goal:** Let the signed-in user stop a running PDF check and delete individual or selected historical PDF reports.

**Approach:** Extend the current Express/SQLite job queue and React screens. Keep the existing development directory and runtime data. Add no dependencies or detector changes.

**Decisions:** Stopping aborts the actual worker and its child processes, does not save a late report, and remains stopped after reload/restart. The stop button becomes available after the upload has produced a job ID. Delete actions require a browser confirmation and apply only to the signed-in user's reports. Batch deletion validates the entire selection before deleting anything. Store an explicit cancellation timestamp and expose a cancelled job state while retaining the existing SQLite status constraint.

## Tasks

- [x] Add failing tests for active/queued cancellation, ownership, late completion, restart, single/batch deletion, confirmation and selection, and stale frontend polling.
- [x] Add cancellation persistence and an abort signal through the existing queue/runner; add authenticated job cancellation and report deletion routes.
- [x] Add Stop Check, report checkboxes, select-all, single delete and batch delete controls with pending/error handling.
- [ ] Run the focused tests, normal test commands, existing MVP checks and production builds. Independently review cancellation/deletion races, then push and deploy the reviewed main revision.

## Review focus

- A user must never cancel or delete another user's objects.
- Cancellation during report persistence must not leave a new report behind.
- Cancelling a queued check must not invoke its detector or restart it later.
- A stale polling response must not undo cancellation or interfere with a subsequent check.
- A batch containing a foreign/missing report must not partially delete the allowed reports.

## Verification and review

- Backend MVP: 52 passed, 2 optional engine tests skipped. Frontend MVP: 43 passed.
- Compiler resource and actual descendant cancellation tests: 7 passed.
- Actual mixed-family cancellation smoke: three real worker processes exited in 2011 ms; no late report, no recovery restart, no external API request.
- Review findings addressed with failing regressions: delayed cancellation response, semantic-only synchronous execution, parallel cleanup barriers, and surviving compiler workers. Native local workers share the same process-group helper.
- History loading now depends on the account ID rather than object identity; repeated equivalent session objects no longer restart loading.
- Broad legacy suites are not green: the original main revision reproduces 23 backend failures and the same 72 frontend failures. One additional repair-cache failure passed when rerun alone. These involve retired routes/catalog selections or old repair-model fixtures and are outside this feature.
- Push and deployment remain the final integration steps.
