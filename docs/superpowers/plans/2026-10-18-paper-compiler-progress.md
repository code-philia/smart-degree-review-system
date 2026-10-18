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
