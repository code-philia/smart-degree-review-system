# Stable external benchmark gate

The user requires fixing failures before another full run. Keep formal benchmarking stopped until this exact candidate passes both offline fault tests and all 20 real-paper eligibility tasks (the original failed Du paper alone through all four rules, then all four archived papers concurrently through each rule).

The initial schema repair preflight found an independent TPM incident: local available budget was 13,289 while the gateway reported 5,982; the declined request reserved 8,673. Several unused budgets had just been returned locally within 12 ms of the next dispatch. Receiving an HTTP response is not acknowledgement of the gateway's asynchronous refund.

Hold at least each dispatched request's estimated budget for 60 seconds after completion; larger confirmed actual usage increases that amount. Only unsent/known rejected requests refund immediately, including when actual successful usage is zero. Preserve the RPM-first joint admission and both separate wait queues. A versioned one-time upgrade window covers settled rows produced by the previous immediate-refund policy.

The previously reverted full-output hold used 8,192 output tokens for every tiny typo response and made one paper queue excessively. Pair safe accounting with stage-specific output limits: discovery starts at 2,048, review and field repair at 512. On actual `finish_reason=length`, double the cap up to the original 8,192 ceiling, validate completion, accumulate all actual usage and reacquire both quotas for each attempt. Do not silently truncate, invent a clean result or lose usable candidates. The single format retry and shared read-timeout allowance remain bounded.

Before formal testing, prove each single-paper rule has no avoidable TPM wait, and all four papers complete all four rules concurrently within each four-paper cohort with zero rule failures and zero upstream 429. If the gate fails, keep the formal matrix stopped. Use a fresh report and one deployed code version after the gate passes. Do not overwrite historical failures.

Typo transport validation accepts only a complete top-level JSON value with confirmed `stop` termination. For a physically truncated errors array, complete candidate objects from its anchored top-level prefix survive the bounded retry and still require the normal source matching/verifier. Nested objects in malformed outer envelopes cannot be promoted to clean answers. The gate and subsequent benchmark persist private raw requests/responses for all four rules.
