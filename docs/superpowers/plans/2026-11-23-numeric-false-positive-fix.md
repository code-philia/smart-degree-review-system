# Numeric false-positive repair implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Correct source scope, native table evidence, metric checks and contribution coverage, validated against actual archived PDFs before publishing.

**Architecture:** Keep `numeric_consistency.py` as the orchestrator. Isolate native-table recovery and metric-evidence/arithmetic helpers in separate modules with explicit interfaces. Preserve the current public report contract, source geometry, and all unrelated rule behavior.

**Tech Stack:** Python, PyMuPDF, Decimal, existing Paper IR, pytest, current Node/Vitest backend and frontend, existing model provider and Publisher.

**Spec:** `docs/superpowers/specs/2026-11-23-numeric-false-positive-fix-design.md`.

## Global constraints

No frontend or public wording changes, no OCR, no original-file or saved-report updates, no production evaluation exception lists, no unrelated rule changes. Use existing managed worktree and private server test copies. Preserve the original publisher and user WIP. Default language behavior remains unchanged.

## Review focus

- A matching value from another dataset, baseline, metric, view angle or method must never prove the target.
- A partial table cannot establish a global maximum; definitions and all required comparison rows must remain grounded.
- Native multilevel/merged headers and neighboring tables must not be combined by proximity alone.
- A formula must be explicitly source-defined and restricted to safe arithmetic; unsupported expressions remain uncertain.
- Multiple-method scope must be justified by the actual abstract contribution; unrelated-method larger values remain excluded.

### Task 1: Pin the target and pipeline integration

**Files:** Modify `backend/scripts/numeric_consistency.py`; create `backend/tests_py/test_numeric_target_scope.py`, `backend/tests_py/test_numeric_integration_coverage.py` and `backend/tests_py/test_numeric_conflict_audit.py`.

- [ ] Add failing tests for a six-value sentence with one scalar target, non-percent units, duplicate-valued conditions and genuinely ambiguous source spans.
- [ ] Preserve grounded full source while exposing an exact atomic target to the verifier; validate source offsets and retain range/comparison semantics.
- [ ] Add failing integration tests for false average/maximum vetoes, incomplete comparison evidence and source-grounded multi-chapter contributions.
- [ ] Implement bounded candidate enrichment/coverage and wire helper modules without changing public messages or report storage.
- [ ] Run new and existing numeric source, lexical, native navigation and panel-ownership tests.

### Task 2: Native table evidence

**Files:** Create `backend/scripts/numeric_native_tables.py`, `backend/tests_py/test_numeric_native_tables.py`; orchestrator integration owned by Task 1.

**Interface:** `recover_native_tables(pdf_path, model, structure_builder, *, version) -> (tables, diagnostics)`. `structure_builder` has the existing `_table_structure(table, page_number, table_index, model, page_height, page=page)` contract. Tables retain current keys and source geometry; diagnostics retain version/attempted_pages/successes/failures.

- [ ] Show failures for text-mode data missed when a weak line-mode table exists, split/multilevel headers and adjacent unrelated tables.
- [ ] Recover both strategy alternatives, conservatively select/corroborate complete native tables, and retain uncertainty and source binding.
- [ ] Verify actual affected native pages without OCR and guard negative geometry/condition cases.

### Task 3: Metric definitions and arithmetic

**Files:** Create `backend/scripts/numeric_metric_evidence.py`, `backend/tests_py/test_numeric_metric_evidence.py`; orchestrator integration owned by Task 1.

**Interfaces:** Source-context enrichment `metric_context(declaration, mapping, model, *, max_items=8, max_chars=6000) -> list[dict]`, returning exact native block quotes with source IDs/pages/sections; safe arithmetic `evaluate_expression(expression, variables) -> Decimal`, rejecting unsupported syntax, unknown variables, nonfinite values and invalid operations.

- [ ] Add failing tests for source-defined formulas, cross-page definitions, MAE/average headers, maximum coverage, wrong-dataset definitions and unsafe arithmetic.
- [ ] Retrieve only bounded grounded definitions/formulas and implement restricted Decimal arithmetic, without verdict-by-number matching or hardcoded AUC conventions.
- [ ] Validate original metric pages and negative/no-definition controls.

### Task 4: Real corpus evaluation

**Private files:** `output/numeric-false-positive-fix-20261123` and `/data/tmp/numeric-false-positive-fix-20261123`; do not commit original texts, model traces or evaluation labels.

- [ ] Establish exact a8fcda7 baseline, original PDF/data hashes and existing real findings; demonstrate relevant old failures with deterministic replay and targeted formal runs.
- [ ] Evaluate the 15 target findings, six prose-supported cases, four partial cases and actual existing true findings through formal integration.
- [ ] Cover the complete test-type matrix and representative real-source cases using private outputs, as clarified by the user; no new 100-paper sweep, online upload jobs, mail or stored reports.
- [ ] Review each newly introduced or lost alert against the original pages. Add meaningful derived positive/negative controls without representing them as original defects.
- [ ] Verify no OCR, no input mutation, source geometry and public result conversion.

### Task 5: Review and external release

- [ ] Obtain independent whole-diff and real-evidence review, resolve findings and rerun affected checks.
- [ ] Commit only scoped source/tests/spec/plan, run exact merged-source checks, and push the verified commit to main.
- [ ] Use the existing Publisher check/prepare/deploy path, preserve database/config/WIP/PDF hashes, and verify active/enabled healthy status and external assets.
- [ ] Report exact version, completed real-paper coverage, remaining limitations and historical-report preservation.

## Recorded source adjudication

The user clarified that completeness means coverage of test types, not a large corpus, and requested rapid release. The planned 100-paper detection sweep is superseded by representative real-source cases plus complete positive/negative/condition/rounding/geometry/contract coverage. Hash preservation of the 100 original PDFs remains a read-only integrity check, not a claim of running all 100.

The initial strict set contained A395. Full original-PDF review found the 17.61% cold-start result and a separate 21.36% overlapped-user result under the same contribution. This item must remain a scope clarification, with the old missing-evidence reason corrected, rather than be forced to pass. Effective evaluation: 14 strict false findings in seven papers, six separate prose cases, five partial controls and four established true findings. The original audit labels and historical reports remain unchanged; a private source-grounded amendment records the correction.
