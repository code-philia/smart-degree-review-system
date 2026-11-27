# Campus TPM and RPM queues

The user requests pre-request TPM budgeting, explicitly chooses two queues, and authorizes pushing and deploying the external service. Existing production RPM spacing (0.6s at 100RPM), API concurrency (32 in the external configuration), model parameters and campus deployment remain unchanged.

## Approach

Use two per-key, cross-process FIFO queues in the existing SQLite coordinator: TPM budget first, RPM/concurrent-slot dispatch second. This is the implementation choice for the user's two-queue requirement. A combined queue was rejected by the user; process-local counters cannot protect shared quota.

The TPM queue atomically reserves estimated input plus declared output budget before permitting entry to the dispatch queue. Estimate text requests consistently with the verified LiteLLM1.87.0 gateway. A reserved request waiting for RPM holds no API lease. Both stages retain their FIFO tickets while waiting and honor cancellation and caller deadlines.

The dispatch queue marks reservations in flight. Successful responses reconcile to validated actual input/output usage, retained conservatively for60s after completion. Unknown outcomes retain their reservation for60s; known429 rejection releases its unused budget while preserving existing shared cooldown/retry. Unsent cancellation and dead unsent owners release budget. Dead/expired in-flight owners transition to a bounded uncertainty window rather than silently refunding potentially consumed tokens.

No document text or API credentials enter the coordinator database. All shipping campus transport entry points supply payloads. Other providers bypass these gates as before. A single request larger than the configured TPM limit fails before any HTTP attempt.

## Acceptance

Tests must prove separate queues, atomic cross-instance/process reservation, no premature HTTP dispatch, reconciliation, missing/invalid usage, cancellation/deadlines/dead owners, unchanged RPM/concurrency/FIFO, and shared budget across compiler and semantic transports. Validate against the real external model with short requests and an isolated coordinator; do not restart the stopped pressure benchmark. Deploy through the existing external publisher with source/health/data checks and rollback support.
