# Bounded background paper batches

Paper submissions continue to use the existing authenticated PDF endpoint and durable per-paper jobs. Multiple accepted jobs are processed by a bounded worker queue; each completed paper remains a separate report under its owning account. No new upload format or detector is introduced.

`REVIEW_PILOT_MAX_CONCURRENT_RUNS` determines the paper engine capacity (default 2). `PAPER_LINT_JOB_CONCURRENCY` optionally selects a smaller positive integer worker count. The queue never exceeds the engine capacity or 32 workers. Set both to 8 for an eight-paper deployment; jobs beyond capacity remain queued. These are paper counts, not API request rates.

The existing model coordinator remains responsible for request pacing across worker processes. Model request concurrency (`SJTU_API_MAX_CONCURRENCY`) is separate from paper concurrency and requests/minute.

## Versioned campus request rate

Deployments default independently to **100 campus requests/minute**. Upgrading the source and restarting the service applies this policy even when a server retains the retired `SJTU_API_REQUESTS_PER_MINUTE=20`, `80` or `90` setting in a private environment file. The retired variable is no longer used for rate resolution; changing only a fallback default would not migrate those servers.

For a deliberate later operating override, set `SJTU_API_REQUESTS_PER_MINUTE_OVERRIDE` to an integer from1 through100 and restart the service. Missing or invalid overrides use100. Do not set this override when deploying the requested100RPM policy. `campus_requests_per_minute()` reports the effective setting without making a request or modifying coordination state.

The coordinator database remains local to each host. Models using the same API account share that host's pacing and concurrent slots. This development policy allows each host100RPM independently; it does not create a cross-host100RPM limit or increase the provider's shared quota. Existing provider429 cooldown and bounded retries remain unchanged. Maximum model concurrency, paper workers, FIFO fairness, request deadlines, API payloads and detector rules are not changed by this policy.

Workers preserve atomic quota admission, idempotent request IDs, cancellation, per-job progress, report ownership, failure visibility and completion transactions. A repeated submission for an active request does not replace the running task's cancellation controller. One failed task releases its slot and does not stop the remaining queue.

Trusted backend operators may reserve a batch job through `paperLintJobRepository.createJob` with `notifyCompletion: false`; this writes the existing durable notification flag at creation. It is not a public HTTP option. The normal default is still true. The ordinary submission endpoint can enqueue the reserved request using the same user/request ID; it must submit the same original PDF and rules. This avoids introducing a second detector path or racing email suppression after completion. Operators should keep a batch manifest and stable request IDs for restart safety.

Campus model calls retain their FIFO queue ticket while waiting for request-rate or concurrent capacity. Queue waiting and provider 429 cooldowns do not consume the per-call HTTP timeout: each admitted transport attempt receives that timeout in full. A provider 429 releases the active slot and queues another attempt after the shared cooldown instead of becoming a detector failure. Non-429 transport errors still propagate normally. Caller cancellation and the existing overall job deadlines remain in force; this policy does not disable those protections or persist request payloads in the coordinator database.

For the 479-paper audit, keep one frozen detector version, use school_admin01, select all 14 MVP rules except sjtu_rule_32, and suppress test emails. Preserve the original PDFs and old reports. Report failed/inconclusive/not-applicable checks separately from reviewed false positives. Increasing concurrency is an operating change; it must not rewrite detector findings or prompts.
