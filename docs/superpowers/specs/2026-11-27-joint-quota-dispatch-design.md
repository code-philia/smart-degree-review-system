# RPM-first checks with joint dispatch admission

The user approved: first wait for RPM capacity without reserving tokens; if TPM is insufficient, wait in the separate TPM queue without spending RPM; recheck both limits and occupy both only immediately before dispatch. Keep two wait queues and preserve waiting order across transfers. A request is in at most one waiting queue. Waiting owns no API concurrency lease. Actual transport attempts, including retries, each acquire both limits.

Production retains paced 100 RPM, the existing concurrency cap, and the current immediate actual-usage TPM settlement. The local pressure harness retains rolling 100 requests/60 seconds and no additional concurrency cap. Do not restore the reverted full-window reservation policy or claim this change guarantees no upstream 429.

Deployment is authorized for the external host only. Synchronize the canonical local harness and its offline checks, but do not launch pressure tests, make real model calls, or change historical result rows. Keep cancellation, deadlines, process recovery, shared Retry-After cooldown, usage validation and account isolation intact.

Approach: check RPM readiness first, then TPM capacity/FIFO; keep stable tickets across reason changes. In production the dispatch transaction reserves TPM, registers the RPM start and creates the API lease together. The single-threaded broker performs the equivalent admission without an await between checks and mutations. Merely reversing two consuming gates would hold RPM while waiting for TPM and does not meet the approved behavior.
