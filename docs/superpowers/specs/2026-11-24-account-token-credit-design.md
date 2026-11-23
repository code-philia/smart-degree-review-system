# Account token credit — proposed design

## Intent and confirmed requirements

Each existing/new account receives a one-time CNY100 allowance. The user confirmed that this replaces, rather than supplements, the lifetime three-report limit. Only token-consuming review rules consume credit. Qwen report translation is free. The four currently exposed model rules are native-body typo detection, bilingual abstract consistency, bilingual keyword correspondence, and abstract numeric/evidence consistency. Add a dedicated credit icon and a measured price beside each of these rules; retain the approved rule ordering and other copy.

This is a software allowance expressed in CNY. No payment, recharge, cash withdrawal, calendar reset, retrospective deduction, or historical-report mutation is requested. All accounts receive the same allowance; do not carry over the old administrator/trial exemptions without approval.

## Approaches

1. Fixed fee per rule: simple but long/short papers and cache hits produce different actual token usage, so it does not match the supplied usage-based pricing example.
2. **Recommended: measured estimates in the rule selector, actual usage-based settlement.** Model unit rates are versioned internally; every returned usage is recorded per account, task and rule. This matches the screenshot and avoids presenting an estimate as a fixed fee.

Choice2 is proposed; the user has explicitly selected replacement of the three-report limit. Product implementation awaits design approval. Read-only exploration and the requested live measurement are in progress.

## Reference price policy

Official source checked2026-11-24: https://api-docs.deepseek.com/zh-cn/quick_start/pricing/ . Always use the published off-peak reference prices, independent of execution time, as requested in the screenshot:

| Reference model | Cache-read input CNY/1M | Ordinary input CNY/1M | Output CNY/1M |
|---|---:|---:|---:|
| DeepSeek Flash |0.02|1|4|
| DeepSeek V4 Pro (future explicit mapping only) |0.15|4.5|13.5|

Current campus transport exposes only `deepseek-chat`, including in its response model field. It does not expose a verified upstream version. Proposal: explicitly configure that campus alias to the Flash **reference rate plan** for this product; do not silently rename/change the inference model or represent the virtual debit as the campus provider's actual invoice. Unknown models cannot inherit a random price. A changed price/model mapping creates a new rate version; existing ledger rows retain their original rate snapshot.

First actual measurements show `usage` with prompt_tokens, completion_tokens and total_tokens only; no cache hit/miss counters. When supported response fields exist, use prompt_cache_hit_tokens/prompt_cache_miss_tokens or prompt_tokens_details.cached_tokens; validate consistency and do not charge total prompt plus cached prompt twice. When cache detail is not supplied, the proposed policy treats the returned prompt total as ordinary input and records cache detail as unreported, never fabricating a cache hit. Local application cache reuse makes no model request and costs zero.

Formula: (ordinary_input_tokens × ordinary_input_rate + cache_read_tokens × cache_read_rate + completion_tokens × output_rate) /1000000. In the supplied screenshot, `write` denotes model output, not an additional cache-writing fee. There is no invented fourth charge.

## Persistent accounting and admission

- Add dedicated account-credit, operation and per-call ledger/reservation tables through additive idempotent migrations. Grants use an immutable user key and unique grant marker. Repeated login, refresh, another browser, service restart and deployment never regrant.
- Store integer nanoyuan (CNY×1000000000), avoiding rounding tiny cached-token charges per request. API amounts are decimal strings; UI rounding never changes stored funds. A100CNY grant fits safely within JS integer precision.
- Before each billable network dispatch, atomically reserve a conservative maximum cost using a text-input upper bound and configured maximum completion tokens. Shared SQLite transactions protect against concurrent processes/tabs overspending the same account. Do not reserve the entire estimated full-paper amount as an arbitrary fixed fee.
- Pass only server-established task/owner context to the Python worker; derive account identity again from stored task/operation ownership. Browser-supplied IDs/prices/token counts cannot select debit recipients or alter amounts.
- Settle returned usage before parsing/validating the model's answer: malformed content can still have consumed tokens. Each call has a unique idempotency key; settlement/retry processing cannot debit it twice. A new actual provider attempt with its own returned usage is a distinct charge.
- Internal verification calls for a selected rule are included in its actual cost. No tokens/no actual request means no debit. A failed/cancelled task retains charges for known consumed tokens, releases unused reservations and never receives an automatic second100CNY grant. Missing usage/unknown transport outcomes are recorded for audit and are not guessed as user charges.
- Cancellation/process kill/restart release reservations only after the relevant process group has stopped; paid consumption already settled remains. Prevent stale workers from settling another operation after a new owner session.
- Keep global100RPM scheduling, queue polling and provider retries unchanged. Credit exhaustion is a separate, clear account-balance result; stop new paid calls, preserve completed results, and continue to allow free rules and Qwen translation.
- New checks, incremental reruns and job-resume paths share this accounting. Historical results are not recharged. Only the pending selected rules can create new debits. Keep legacy quota APIs compatible during the UI migration without retaining the three-report restriction.

## Product boundaries

The proposed initial charging scope is review-rule execution only, including its internal verification calls. Existing separate AI repair-proposal and polishing features are not silently brought into billing. Reading old reports, feedback, exports and notices remain free. This scope is a proposed implementation choice, not a user decision yet.

## Frontend

- A compact Coins-style outline icon identifies credit; avoid a dollar-sign icon for CNY. Use the existing blue/slate visual system.
- Show the account's available balance near review selection, with spent/reserved detail available through an accessible tooltip/popover. No payment/recharge button.
- Beside the four billable rule names show that icon and `约¥…/篇` / `Est. ¥…/paper`. Tooltip: price is measured estimate; actual token usage determines debit. Free rules keep their current uncluttered display.
- Estimates come from the requested actual runs on two archived PDFs (indices5 and58, different lengths), using unchanged production detector/prompt source and isolated outputs/cache. Record per-rule calls, usage categories, source hashes, code version and measured low/high/mean. Do not present two samples as a universal accuracy guarantee. Final measured prices will be attached when all runs complete.
- Preserve CN/EN UI parity for every new/necessarily replaced quota label. Do not rewrite unrelated report messages. Keep rule ordering, selection behavior, consent, report layout and notice unchanged.

## Verification and release boundary

Test initial grant exactly once across existing/new users/browser/session/migration/restart; parallel requests/processes; decimal/cache arithmetic; absent/inconsistent usage; Qwen/free-rule exclusions; zero-balance free execution; failed/cancelled/partial/retried tasks; cache reuse; incremental reruns; owner spoofing and account switch; job kill/recovery; all original detector and scheduling regressions. Use real archived PDFs for measured prices and run actual accounting against isolated copies, never overwrite saved user reports.

Inspect Chinese/English desktop/narrow layouts, keyboard access and balance refresh. Preserve original database rows, PDFs, unrelated WIP and private runtime configuration. First deliver a local preview and measurement results: the current user request does not explicitly authorize publishing this new feature yet. Approval of the completed implementation can precede a later main push/deployment.

## Completed measurement (unchanged production implementation)

Two archived PDFs, all4 billable rules per PDF,8 completed runs,102 actual campus model requests. Source PDF hashes remained unchanged in the harness. Total reference consumption: CNY0.290930. A repeat keyword check reused the isolated application cache with zero model requests and zero tokens. No reports, account balances or production source were modified.

| Rule | Paper5 reference CNY | Paper58 reference CNY | Proposed displayed estimate / paper |
|---|---:|---:|---:|
|中英文关键词语义对应|0.006052|0.004333|约¥0.0052|
|中英文摘要内容一致性|0.01793|0.008878|约¥0.0134|
|论点论据一致性|0.11398|0.053106|约¥0.0835|
|正文错别字检测|0.037722|0.048929|约¥0.0433|

Raw usage and full receipt: `D:/HuaweiMoveData/Users/86139/Desktop/交大项目/output/token-credit-20261124/pricing-measurements.json`. These are actual token measurements multiplied by the proposed reference tariff, not an independently verified campus invoice. Builder check found no other material questions beyond confirming this reference tariff and estimate-versus-fixed charging choice.

## User-directed local-preview changes (2026-11-24; supersede display estimates above)

User requested a local frontend preview before implementation. This is an explicitly authorized throwaway spike, not approval to enable production debits. Preserve the original About this review paragraph verbatim except replacing the lifetime3-review clause with initial100CNY credit, in both languages. Use a small gold lightning icon and gold credit text; the existing Experimental/Beta badge precedes the price icon. User selected whole-cent displays; display keyword0.01, abstract0.02, typo0.05 CNY. User explicitly set numeric/evidence consistency to0.10 CNY, overriding the initially rounded0.09 proposal. Allfour selected estimated total0.18 CNY. These UI prices do not silently change the underlying actual-token settlement policy, which remains unimplemented pending confirmation.

## Implementation authorization and final UI (2026-11-24)

The user approved the credit mechanism and explicitly authorized implementation, main push and external deployment. This supersedes all earlier preview-only/approval-pending statements. Use actual returned token settlement at the Flash reference tariff above; selector prices remain estimates, not fixed charges. Replace the three-report limit for every account. Scope is the four selected model review rules including their internal verification; Qwen translation and separate repair features remain outside this allowance.

Approved estimates: keywords0.01, abstracts0.02, typo0.05 and numeric0.10 CNY. The account control is a compact bordered single-line remaining-credit ring, label and balance; no percent inside the ring. Detail has current available percentage in parentheses immediately after its label and the amount aligned right. Use mint/teal, dark balance figures, framed lightning/price labels matching rule-title font sizes, Experimental before price. Restore existing grouped selection buttons. Keywords precede punctuation. Preserve original instructions except replacing the three-review clause. These supersede the earlier gold/Coins display directions.
