# Execution ledger — plan: docs/superpowers/plans/2026-10-18-paper-compiler-phase1.md

2026-10-18 authorization: user requested immediate progress after clarification; Huawei cap CNY 1000, pilot CNY 5 within the total; public literature sources. Existing v0.4 design accepted. No publication before first-round review.

Execution: inline implementation with one independent final review. Existing server AGENTS requires the sole current checkout, so no worktree is created. A tracked ledger is used across the Windows controller and SSH checkout.

Pre-flight interfaces: T1 IR/hash -> T3/T4/T6/T7; T2 metered client -> T3/T4/T5/T6; T4 rule packages -> T6/T7/T8; T5 evidence -> T6; T6 checks -> T7/T8; all use dictionaries with versioned, validated schemas and explicit status values. No conflicting signatures identified.

Task 1: in progress. Base 82768dd.

Task 1: initial contract tests RED (missing package), then GREEN: 34 passed in 0.22s. Added typed nodes, tree/source validation, canonical IR hash, stale analysis rejection and exclusive atomic outputs. Full pre-change Python baseline is running and contains pre-existing failures; investigating separately before treating old-rule regression as clean.

Task 2: Ruling: Huawei compatible endpoint uses max_completion_tokens, covering answer plus reasoning, and chat_template_kwargs.thinking=false. max_tokens excludes reasoning. Official 2026-10-18 documentation verified; regression failed before correction and passed after. Budget uses daytime no-cache rates CNY 2/8 per million, reservations include all output tokens.
Baseline: 144 failed, 2000 passed, 26 skipped, 79 subtests passed before new package implementation. First legacy failure also reproduced independently. Exact failures saved in paper-compiler-baseline.json. Ruling: preserve existing detector behavior and track these as baseline failures; do not expand this task into fixing all legacy semantics. Any newly introduced failure must still be fixed.

Task 1: complete (commit 71a7994; 34 contract tests passed).
Task 2: complete pending commit; 13 budget/adapter tests plus 34 contract tests passed. Real structured call succeeded: 70 input + 15 output tokens, conservative CNY 0.000260. Durable budget at /data/runtime/paper-compiler/budget.sqlite3, limit CNY 1000; pilot cap CNY 5.
Task 3: in progress. Ruling: frontend reads raw PyMuPDF observations directly rather than routing through old graphic ownership/normalization passes; this preserves exact characters and avoids invoking legacy detector semantics. Shared existing PyMuPDF dependency retained.

Task 2 committed: 67672aa.
Task 3 source frontend milestone: 8 tests passed, 3 real archive PDFs produced typed source IR in 1.1–2.2 seconds each. Bibliography/usage coverage remains provisional; semantic boundary verification is pending Task 6.
Task 4 complete: 23 compiler/capability tests (including bounded candidate retry and actual missing-capability dispatch). A real candidate failed static policy and was retained; policy now supports pure isinstance guards and forbids recursion. Actual model-generated capability passed 4 withheld cases plus an extra 5-word case. Live natural-language rules changed the compiled threshold 1 -> 3; generated/interpreted behavior independently compared on the same source PDF. Live artifacts /data/results/paper-compiler/development/compiler-live-v2. Total conservative API cost CNY 0.009048 across 5 calls.
Task 5 in progress: public provider tests and live server reachability passed. A same-title reupload with a different year was correctly not accepted; added author/year constrained discovery.

## 2026-10-18 continuation: shared citation passes and resumable evaluation
- Task 3: corrected actual bibliography boundary selection after a real PDF diagram label swallowed body text. Three real IRs rebuilt under frontend-pilot-v2; prior artifacts preserved.
- Task 4: added independently withheld semantic gates, canonical generated-code round trips and bounded normative-clause compilation. R32/R33 real candidates pass positive/negative/insufficient controls; R31 full compilation remains in progress. Added a typed sequence-order primitive after the generated candidate exposed a missing DSL operation.
- Task 5: public metadata gateway and identity resolution implemented, with bounded/cacheable source retrieval, source groups, alias/year/DOI ambiguity controls and honest UNKNOWN. No public source can prove universal nonexistence; this will be an explicit R32 negative-evidence coverage limit.
- Task 6: shared quoted field extraction, bindings, work identity, purpose/content analysis and runtime evidence/type/version gates implemented. Compact two-entry extraction succeeds on six real citations; all unsupported/untraceable fields remain unknown.
- Task 7: source IR mutations, sealed oracle, exact target pairing, distinct-parent denominators, immutable manifests and resumable checkpoints implemented; failed outcomes are retained without implicit re-execution.
- Task 8: CLI build/compile/check/batch/evaluate/budget and source-vs-synthetic presentation implemented; website adapter still in progress.
- Ruling: compile R31 by normative clauses and validate the union — whole-rule outputs hit the response limit and repeatedly invented unsupported field operations — risk: cross-clause interactions must be checked in combined controls and final review.
- Ruling: compact bibliography extraction records observed fields plus an explicit absent-name list — full verbose six-entry responses were invalid; missing names stay UNKNOWN — risk: coverage can fall but cannot silently become a missing-field violation.
- Validation: all new paper_compiler test modules passed at this milestone; baseline legacy suite has 144 pre-existing failures and has not yet been re-compared.
