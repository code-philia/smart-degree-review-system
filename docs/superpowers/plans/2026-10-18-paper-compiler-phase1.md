# Paper Compiler Phase 1 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task. Track steps and evidence in the execution ledger. One independent review follows the implementation.

**Goal:** Compile natural-language citation rules into versioned checks over a typed Paper IR, execute rules 31–33 with sourced evidence, and deliver a frozen first mutation evaluation for user review.

**Architecture:** A Python package under `backend/paper_compiler/` owns contracts, compilation, analysis, evidence and evaluation. The existing Node application adapts its bounded JSON protocol; the existing PDF frontend supplies observations. Generated checks use a constrained expression language and registered capabilities; they never reopen PDFs or read evaluation answers.

**Tech Stack:** Existing Python 3.12 / PyMuPDF / pytest, Python standard library, Node 22 / Express / Vitest, React. Avoid new runtime dependencies when existing libraries suffice.

**Spec:** `docs/superpowers/specs/2026-10-18-paper-model-design.md`, its `ir-contract.md` and `phase1-citations.md`, and `docs/规则编译开发交接_20261018.md` (latest collaboration/API decisions override older spec descriptions).

## Global Constraints

- Work only in `/data/projects/smart-degree-review-system`, branch `rules-11-20-detectors`; no new worktree. Preserve four existing untracked pnpm files.
- Preserve production service, database, PDFs, old ten rules, collaborator workspace and deployment tooling. Use `/data` for dependencies, caches and results.
- Never modify `30条规则_变异检测结果.csv`. First-round results are immutable; subsequent experiments get new directories.
- User authorized cumulative Huawei API spending up to CNY 1000 on 2026-10-18; initial cost measurement uses at most CNY 5 of this total. Public literature sources only; no new paid service subscriptions.
- Count all model attempts, including invalid model output and retries. Reserve conservative per-request cost atomically before network transmission; keep uncertain-charge reservations on network failures. No reset of the cumulative ledger between tasks or rounds.
- Use the private main-line Huawei configuration. Never log credentials. Citation and retrieved text are untrusted data.
- Paper Model, Paper IR, Rule IR, derived analysis, diagnostics and evaluation oracle are distinct. Analyses must match the current serialized IR hash.
- Preserve observed / confirmed_absent / unknown / not_applicable; unknown is never success or violation. Return PASS / VIOLATION / UNKNOWN / NOT_APPLICABLE / ERROR and document passed / rejected / inconclusive separately.
- Check source markers and bibliography formats for R31. R32 concerns external work identity; unsuccessful search is not proof of nonexistence. R33 concerns each local citation purpose, with grounded external content.
- First-round minimum: 100 distinct real parents per rule, at least 300 valid pairs in total. Report invalid/undecidable candidates and genuine shortfalls; synthetic parents do not replace real ones. Controlled-catalogue tests remain explicitly scoped.
- Deliver frozen first-round raw results before setting publication thresholds. No production publication in this plan's execution before that user decision.
- Git author and committer: `czh1302 <157283781+czh1302@users.noreply.github.com>`.

## Review Focus

1. A malformed/partial PDF, bibliography or OCR observation must preserve content and produce explicit missing coverage, never silently pass an empty target set (Tasks 1, 3, 6).
2. Concurrent processes, timeouts and malformed API output must not exceed or reset the shared spending authorization (Task 2).
3. Untrusted rule/document/evidence text must not cause arbitrary generated-code execution, secret access, private-network retrieval or oracle leakage (Tasks 4, 5, 7).
4. A wrong DOI, translated title, inaccessible abstract or multidisciplinary method citation must not become an unsupported R32/R33 violation (Tasks 5, 6).
5. Mutating source content must invalidate relevant analyses and source claims; existing unrelated findings must not count as a mutation kill (Tasks 1, 7).

## Task 1: Typed contracts and immutable snapshots

**Files:** create `backend/paper_compiler/{__init__,contracts,storage}.py`; create `backend/tests_py/test_paper_compiler_contracts.py`.

**Interfaces:** `validate_ir(ir: dict, source_root: Path | None = None) -> None`; `serialize_ir(ir: dict) -> bytes`; `ir_hash(ir: dict) -> str`; `validate_analysis(ir: dict, analysis: dict) -> None`; `write_json_atomic(path: Path, value: dict, exclusive: bool = False) -> None`.

- [ ] Write failing tests for duplicate IDs, cycles, multi-parent/unreachable nodes, invalid spans/coordinates, unsupported attributes/types, missing source files/hash mismatch, invalid missing-state claims, answer leakage and stale analyses. Valid dangling references remain loadable.
- [ ] Run `cd backend && /data/envs/six-rule-dev/bin/python -m pytest tests_py/test_paper_compiler_contracts.py -q`; observe failures from missing functionality.
- [ ] Implement versioned node/observation contracts, deterministic serialization, source integrity checks and atomic output. Existing design fixtures are imported explicitly as fixtures, not accepted as runtime model output.
- [ ] Run the test command to green and commit `feat: add typed paper IR contracts and snapshot validation`.

## Task 2: Metered Huawei adapter and durable budget

**Files:** create `backend/paper_compiler/{budget,llm}.py`; create `backend/tests_py/test_paper_compiler_budget.py`; create `backend/tests_py/test_paper_compiler_llm.py`.

**Interfaces:** `BudgetLedger(path: Path, limit_cny: Decimal)` with `reserve(request_id, max_cost_cny, phase, phase_limit_cny)`, `settle(request_id, usage, charged_cny)`, `summary()`; `MaasClient(config_path, ledger, cache_dir, phase, phase_limit_cny).complete_json(task: str, instructions: str, data: dict, max_tokens: int) -> dict`.

- [ ] Write failing tests using a local HTTP server: concurrency reservations, cumulative/phase limits, stale inflight calls, timeout charging uncertainty, invalid JSON, output token cap, cache/version separation, secret redaction and bounded retries.
- [ ] Run the two test modules and observe the intended failures.
- [ ] Implement SQLite atomic reservations in integer micro-CNY, fixed authorized model loading, structured request/response records without secrets, content-addressed cache and explicit token ceilings. Conservative accounting uses the verified daytime rates without assuming discounts: input CNY 2 / million, output CNY 8 / million; record rate source/version. Count request-byte upper bounds plus protocol overhead before sending.
- [ ] Run tests to green; commit. Only then execute a small real structured call from the CNY 5 pilot envelope and record usage/cost; no second unrestricted adapter path.

## Task 3: PDF frontend, structural nodes and citation source mapping

**Files:** create `backend/paper_compiler/{frontend,citations}.py`; create `backend/tests_py/test_paper_compiler_frontend.py`.

**Interfaces:** `build_paper(pdf: Path, *, client=None, layout_cache=None) -> dict`; `citation_context(ir: dict, use_id: str) -> dict`; frontend returns the Task 1 contract with source spans and coverage.

- [ ] Write failing tests with actual generated PDFs for page/rotation mapping, cross-line bibliography entries, title/section/paragraph nesting, numeric ranges and author-year citations, repeated headers, nonbibliographic brackets, blank/image pages and source text conservation.
- [ ] Run frontend tests to observe intended failures.
- [ ] Reuse `pdf_rules.pdf_extract.extract_pdf` for observations; retain glyph/layout detail where needed. Construct typed structure, bibliography entries and reference uses. Use bounded model extraction only for ambiguity, require source IDs/substring offsets, retain unknown blocks and incomplete coverage.
- [ ] Run tests to green and a read-only sample of real archive PDFs; save quality summaries and source-linked examples. Commit.

## Task 4: Natural-language compiler, expression backend and capability extension

**Files:** create `backend/paper_compiler/{compiler,expressions,capabilities}.py`; create `backend/tests_py/test_paper_compiler_compiler.py`; create `backend/tests_py/test_paper_compiler_capabilities.py`.

**Interfaces:** `compile_rule(text: str, basis: list[dict], registry: dict, client, output_dir: Path) -> dict`; `interpret_rule(rule_ir: dict, ir: dict, analysis: dict) -> list[dict]`; `generate_code(rule_ir: dict) -> str`; `ensure_capabilities(requests: list[dict], registry: dict, client, output_dir: Path) -> dict`.

- [ ] Write failing tests for field/type errors, unsupported expressions, malicious strings, UNKNOWN propagation, all/any conditions, changed natural-language constraints, generated/interpreted result equivalence and capability validation failures.
- [ ] Run tests to observe intended failures.
- [ ] Have the real model produce a structured RuleSpec against a published schema; check types and evidence obligations before lowering to Rule IR. Generate Python from safe templates and literal encoding. The runtime only reads provided IR/analysis and registered operations.
- [ ] Generate initial missing capabilities as constrained declarative extraction/analysis programs, schema and prompts; render executable wrappers through the same safe backend and validate in an isolated process. Independent known-answer checks govern registration; generated tests alone do not establish correctness. Failed candidates remain failed.
- [ ] Save original text/standard/model/prompt/schema hashes, RuleSpec, Rule IR, generated code, dependency versions and test results. Demonstrate a separately specified rule variation and at least one model-generated capability extension.
- [ ] Run tests to green and commit.

## Task 5: Public literature evidence and identity resolution

**Files:** create `backend/paper_compiler/{evidence,identity}.py`; create `backend/tests_py/test_paper_compiler_evidence.py`.

**Interfaces:** `EvidenceGateway(cache_dir, providers, transport).lookup(query: dict) -> list[dict]`; `.content(work: dict) -> list[dict]`; `resolve_identity(entry: dict, records: list[dict], client=None) -> dict`.

- [ ] Write failing tests for wrong DOI with real alternate work, ambiguous names, translations, empty results, missing abstract, 404/429/timeout, cached failures, redirected/private URLs, bounded response sizes and unsupported negative identity claims.
- [ ] Run tests to observe intended failures.
- [ ] Implement source-specific public metadata adapters, DOI/content follow-up and conservative matching with model-assisted ambiguity resolution. Store full retrieval provenance and coverage; treat dependent indexes as related sources. Use eligible public publisher/repository content for R33; inaccessible evidence stays explicit.
- [ ] Run tests to green, verify public source availability from the server without sending private credentials, and commit.

## Task 6: Shared analysis and actual 31–33 rule packages

**Files:** create `backend/paper_compiler/{analysis,standards,runtime}.py`; create `backend/tests_py/test_paper_compiler_analysis.py`; create `backend/tests_py/test_paper_compiler_runtime.py`; add verified standards evidence under `backend/paper_compiler/resources/`.

**Interfaces:** `enrich(ir: dict, rule_packages: list[dict], *, client, gateway, cache_dir: Path) -> dict`; `check(ir: dict, analysis: dict, rule_packages: list[dict]) -> dict`; returns per-object results plus coverage and document status.

- [ ] Write failing tests for evidence ID validation, field source matching, applicable resource types, optional DOI/URL exceptions, unresolved binding, scoped negative identity evidence, abstract insufficiency, multidisciplinary methods, criticism, group citation purposes and errors versus unknowns.
- [ ] Run tests to observe intended failures.
- [ ] Read and visually verify the relevant supplied GB/T 7714—2025 clauses, including bibliography resource types and citation systems; save clause coverage/limitations. Compile R31–R33 from their original natural-language text through Task 4 with the real model.
- [ ] Plan shared passes; parse fields without deleting source punctuation, bind reference uses, retrieve identities/content and judge citation intent with quoted evidence. Evidence insufficiency triggers bounded enrichment/reparse; never auto-edit system code.
- [ ] Run tests to green, execute the small live cost pilot and save per-stage token counts, calls, latency and extrapolated costs. Continue within the CNY 1000 authorization without requesting approval again unless the cap/source access blocks progress. Commit.

## Task 7: IR mutations, sealed oracle and resumable evaluation

**Files:** create `backend/paper_compiler/{mutations,evaluation,batch}.py`; create `backend/tests_py/test_paper_compiler_mutations.py`; create `backend/tests_py/test_paper_compiler_evaluation.py`.

**Interfaces:** `mutate(ir: dict, recipe: dict) -> tuple[dict, dict]`; `evaluate(case_manifest: Path, report_root: Path, runner) -> dict`; `run_batch(manifest: Path, config: dict, output_root: Path) -> dict`.

- [ ] Write failing tests for parent/child hashes, source versus synthetic provenance, analysis invalidation, oracle isolation, precondition failures, exact target localization, unrelated preexisting findings, distinct-parent counting, resume/version conflicts and failure retention.
- [ ] Run tests to observe intended failures.
- [ ] Implement source-content/structure mutations, independent precondition/expected-result checks, sealed evaluation input and a detector process with only normal input artifacts. Keep synthetic, controlled-catalogue and real external evidence separate.
- [ ] Build frozen manifests and report every denominator, including missing coverage, invalid and undecidable pairs. Use atomic per-paper checkpoints and preserve failures across restarts. Commit after tests pass.

## Task 8: CLI and website adapter

**Files:** create `backend/scripts/paper_compiler.py`; create `backend/src/normative/paperCompilerService.js`; modify the existing single-paper/archived rule dispatch and frontend report types as needed; add Python CLI, Node protocol and frontend report tests.

**Interfaces:** CLI subcommands `build`, `compile`, `check`, `batch`, `evaluate`, `budget`; bounded JSON result protocol. Node exports `getCompilerRules`, `isCompilerRuleId`, `runCompilerRules`; disabled/unconfigured capabilities are reported unavailable, never passed.

- [ ] Write failing tests for cancellation/timeout, malformed or oversized output, partial rule terminal records, native versus synthetic PDF locations, UNKNOWN rendering, evidence links, selection of old/new rules together and access checks.
- [ ] Run the targeted test commands and observe intended failures.
- [ ] Connect the existing job/progress/report UI with 31–33 and evidence/coverage fields. Provide the natural-language compilation entry as an authenticated/background CLI task, without adding a compiler management page. Keep production activation pending the first-round decision.
- [ ] Run targeted and relevant existing regression tests plus frontend build, then commit.

## Task 9: Independent review and frozen first-round experiment

**Files:** immutable outputs under `/data/results/paper-compiler/round-001/`; local readable summary copy under `output/paper-compiler/`.

- [ ] Request one independent review of the implementation against the spec, this plan and the review focus. Fix material findings with reproducing tests before freezing the version.
- [ ] Freeze compiler/model/rule packages, real-PDF manifest, evidence and mutation seeds. Build archive IR, choose at least 100 independently valid real parents per rule where available, and record all exclusions.
- [ ] Execute original/variant checks, valid/equivalent controls, evidence-insufficient and service-failure cases with the CNY 1000 shared budget. No failure-driven code edits inside the frozen run.
- [ ] Generate complete raw results and readable per-rule statistics, usage and example evidence; explicitly state any shortfall rather than substituting synthetic parents.
- [ ] Verify output hashes, protected CSV hash and website health. Deliver the first-round report and await the user's publication criteria. Final 479 × 3 evaluation, release and production verification follow that decision in a later recorded round.

## Execution Ledger

Use `docs/superpowers/plans/2026-10-18-paper-compiler-progress.md` for durable task status, commands, commit references and rulings. This tracked ledger replaces host-specific scratch helpers because the controlling shell is Windows and the sole authorized development checkout is on SSH. Preserve it through compaction and resume at the first incomplete task.
