# Typo schema recovery

The user requires fixing rule failures before continuing the external benchmark. A cached offline replay of the failed Du paper used 80 valid cached responses and identified exactly one missing invalid `typo-discovery` response at chunk index 26. All 283 HTTP requests in that concurrency cohort succeeded; this is an incomplete structured answer, not queue or HTTP failure.

Keep the strict schema checks. Route parseable but invalid typo discovery/review/field answers through the existing one-format-retry allowance, add an explicit stage schema reminder, and keep the original source messages unchanged. Each actual attempt still enters RPM/TPM admission and billing. Validate the second answer, accumulate both usage receipts, cache only valid results under the original request, and preserve partial coverage/error if both attempts remain invalid. Share the existing read-timeout allowance and respect deadlines. Individually valid candidates from incomplete responses must survive retries and still pass the original source matching/verifier; a failed retry must not discard them or make the chunk clean. Keep the normal 20-candidate chunk limit. A read-timeout split can retain up to 20 parent candidates plus 20 from each of its two children, with explicit source windows.

- [x] Add regression tests and observe incomplete-schema failures before the fix.
- [x] Implement bounded validation/retry, verify existing timeout, cache, billing and chunk coverage behavior.
- [ ] Fresh review, push and deploy externally; verify the exact failed chunk with the repaired transport.
- [ ] Start a fresh 28-cohort report using one deployed version. Preserve the failed benchmark as diagnostic evidence; never rewrite its failure as success.

No change to the RPM-first joint dispatch policy, token budget estimation, strict validators, archived sample order or production data.

Before publishing, all four archived papers must complete all four rules on this exact candidate (16 real runs). Capture raw model bodies privately for any future diagnostic instead of guessing at an unrecorded response. Only then freeze/deploy the candidate and start a fresh, empty formal matrix.
