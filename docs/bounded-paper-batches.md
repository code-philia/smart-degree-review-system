# Bounded background paper batches

Paper submissions continue to use the existing authenticated PDF endpoint and durable per-paper jobs. Multiple accepted jobs are processed by a bounded worker queue; each completed paper remains a separate report under its owning account. No new upload format or detector is introduced.

`REVIEW_PILOT_MAX_CONCURRENT_RUNS` determines the paper engine capacity (default 2). `PAPER_LINT_JOB_CONCURRENCY` optionally selects a smaller positive integer worker count. The queue never exceeds the engine capacity or 32 workers. Set both to 8 for an eight-paper deployment; jobs beyond capacity remain queued. These are paper counts, not API request rates.

The existing model coordinator remains responsible for per-process/shared-provider pacing. Its `SJTU_API_MAX_CONCURRENCY` and `SJTU_API_REQUESTS_PER_MINUTE` settings are separate from paper concurrency. A coordinator database is local to its host: deployments sharing a provider quota must reserve a combined request budget rather than each assuming the full provider allowance. Increasing paper workers does not increase provider quotas.

Workers preserve atomic quota admission, idempotent request IDs, cancellation, per-job progress, report ownership, failure visibility and completion transactions. A repeated submission for an active request does not replace the running task's cancellation controller. One failed task releases its slot and does not stop the remaining queue.

Trusted backend operators may reserve a batch job through `paperLintJobRepository.createJob` with `notifyCompletion: false`; this writes the existing durable notification flag at creation. It is not a public HTTP option. The normal default is still true. The ordinary submission endpoint can enqueue the reserved request using the same user/request ID; it must submit the same original PDF and rules. This avoids introducing a second detector path or racing email suppression after completion. Operators should keep a batch manifest and stable request IDs for restart safety.

For the 479-paper audit, keep one frozen detector version, use school_admin01, select all 14 MVP rules except sjtu_rule_32, and suppress test emails. Preserve the original PDFs and old reports. Report failed/inconclusive/not-applicable checks separately from reviewed false positives. Increasing concurrency is an operating change; it must not rewrite detector findings or prompts.
