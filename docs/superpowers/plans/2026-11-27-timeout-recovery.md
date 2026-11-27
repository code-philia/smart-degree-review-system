# Timeout recovery implementation plan

Goal: implement the user-approved timeout recovery and publish external only.
Spec: ../specs/2026-11-27-timeout-recovery.md

- [x] TDD: timeout classifier, bounded retry shared with format repair, queue/deadline/billing receipts, sentence split/partial completion/source locations, and benchmark logical retry records.
- [x] Implement focused recovery helper, semantic transport and typo discovery adaptation, truthful copy and benchmark context integration. Run relevant Python/JS and offline harness checks.
- [ ] Fresh whole-change review, evidenced fixes, target Linux and archived failing-input recovery verification; commit/push/deploy through official publisher. Check source, health, old process cleanup and historical data. Pressure test stays stopped.

Review focus: retries after usage-returning format failures, timeout nested in URLError vs cancellation, split boundary/repeated text locations, partial child failures, unchanged overall deadline and unknown billing.

Ledger: existing linked worktree reused; production source clean at54e050f. Local harness changes from previous request remain untracked output; preserve their current source and all old raw/results. No new production edits yet.

RED→GREEN: initial7failures exposed missing recovery/deadline/copy behavior (one control expected existing HTTP wrapping and was corrected). Recovery keeps partial child findings with original source rectangles, status remains inconclusive when coverage fails; malformed discovery cannot claim completed coverage. Actual billing test proves unknown+settled receipts and one known debit. Quota test proves the retry waits for conservative unknown TPM reservation.

Fresh review:4Important findings accepted;6regression cases reproduced deadline splitting, cross-child row truncation, repeated context mislocation, provider-forged spans and fallback deadline overshoot. Fixed with typed provider-read/exhausted exceptions, local owned windows and per-child bounds, ambiguity explicitly incomplete, and fallback deadline checks. The truthful empty-timeout-copy finding is required by the user and was also fixed/covered. No deferred findings. Live provider/deployment/load outcomes were deferred by reviewer and verified separately below; no pressure load was restarted.

Validation:20timeout-specific checks; local326passed/1Windows-/proc baseline case deselected; external Linux326passed/1unrelated baseline case deselected; frontend26passed; local harness27offline checks passed including Unixsocket tests. Linux native PDF image clipping test fails identically on the existing54e050f release, before this change; the extraction source is unchanged and that baseline issue is retained, not hidden or rewritten.

Archived failing input validation: chunk18 (pages34–36), SHA2564b50526384f3c56642671b94de71a02f2fbc308bd6a7604e77284d162c6e7e70. Injected2body-read failures (no HTTP for those), then2real child requests returned200; known usage1509input+69output. Recovery completed. Helper SHA256b39f54216aeaefcb06e897252b574005892fc83be73547cdacd5bf2ad8273075. Proof in output/timeout-recovery-20261127. This validates handling, not a claim that the upstream can never time out again. External publication follows the user's existing authorization.
