# Frozen corpus execution and coverage protocol

This protocol prepares T33/T48/T51/T53. It does not claim the final 479-paper scan, experiment results, metered costs or publication criteria have been completed. The formal suite is still pending benchmark/study acceptance. No paid corpus run was started while implementing this entry point.

## Inputs and isolation

Use `backend/scripts/paper_compiler_corpus.py` with the existing Python environment `/data/envs/six-rule-dev/bin/python`. The only corpus input reused from round 001 is its frozen inventory: `/data/results/paper-compiler/round-001/frozen.json`, `inventory.items`. Historical packages, model configuration and the historical 1000-CNY setting in that file do not select the new runtime or authorize spending. The script does not edit this file, source papers, prepared mutants, production files or the protected CSV.

A `run` requires a hash-verified `paper-suite/1.0` whose member packages are `paper-program/2.0`, with `validation.json.status=passed`. An explicit `--rule` set must match every suite rule exactly, preventing a two-rule candidate from silently satisfying the three-rule protocol. It runs the fixed suite once per paper through `frontend.build_paper` and `pipeline.detect`. All rules share the materialized model and analysis. It never calls online refinement, promotes a package or generates a replacement program. Semantic APIs remain usable under this fixed program/model/prompt configuration.

The output root freezes normalized source IDs/absolute paths/SHA256, the full source-inventory file SHA256, suite/model/program metadata, suite validation hash, runtime source hashes and a public runner fingerprint. The fingerprint includes the public semantic model identity, explicit evidence snapshot, provider configuration, cache path, existing ledger path, phase and budget. A changed frozen input/configuration/suite/runtime refuses to continue the same root; use a new explicitly reviewed run for another final candidate. Credentials are excluded from the fingerprint and errors disclose exception types only.

## Read-only preparation commands

Run these from `/data/projects/smart-degree-review-system/backend`. Choose new output files; inspect/estimate use exclusive creation and cannot overwrite an existing result.

```bash
/data/envs/six-rule-dev/bin/python scripts/paper_compiler_corpus.py inspect \
  --inventory /data/results/paper-compiler/round-001/frozen.json \
  --rule 31 --rule 32 --rule 33 --verify-hashes \
  --out /data/results/paper-compiler/corpus-preparation-20261019/inventory-report.json

/data/envs/six-rule-dev/bin/python scripts/paper_compiler_corpus.py estimate \
  --inventory /data/results/paper-compiler/round-001/frozen.json \
  --ir /data/results/paper-compiler/round-001/parents/pdf-005b17aadceceb6a8a2b/original.json \
  --ir /data/results/paper-compiler/round-001/parents/pdf-00ad8721a76b03d5e80c/original.json \
  --ir /data/results/paper-compiler/round-001/parents/pdf-011e577ab5066fb1c95e/original.json \
  --out /data/results/paper-compiler/corpus-preparation-20261019/workload-report.json
```

When a final suite exists, add `--suite FINAL_SUITE` to `estimate` to count its declared generated analysis request targets. The estimator reads existing IR only; it does not parse all PDFs, contact a provider or instantiate a model client/ledger. It checks that sample source hashes belong to the inventory. It marks the sample as nonrepresentative, leaves actual currency unset and distinguishes an illustrative one-request-per-entry/use scenario from the current suite's declared requests. Section reclassification, cache reuse, unavailable sources and unseen document sizes prevent the extrapolation from being a guaranteed bound.

## Explicit final run, resume and summary

The following is a template for use only after the final candidate is accepted. `FINAL_SUITE` and `NEW_OUTPUT_ROOT` must be concrete reviewed paths; this command was not executed during preparation.

```bash
/data/envs/six-rule-dev/bin/python scripts/paper_compiler_corpus.py run \
  --inventory /data/results/paper-compiler/round-001/frozen.json \
  --suite FINAL_SUITE --out NEW_OUTPUT_ROOT --expected-documents 479 \
  --rule 31 --rule 32 --rule 33 \
  --evidence-snapshot final-corpus-20261019 \
  --ledger /data/runtime/paper-compiler/budget.sqlite3 \
  --cache /data/runtime/paper-compiler \
  --budget 200 --phase final-corpus --phase-budget 200
```

The same command resumes the same frozen root. No new ledger is allowed: a paid run requires an existing ledger and uses its existing cumulative limit. Both command limits must be positive and at most 200 CNY; existing `BudgetLedger` rejects a conflicting limit and reserves worst-case charges before sending requests. `MaasClient(max_attempts=1)` adds no hidden paid retry. Model configuration uses the existing private configuration file without copying its values. A cache override never creates another budget. `--offline` skips model/evidence APIs and budget creation; offline UNKNOWN is not evidence of a successful semantic scan.

One OS lock owns an output root. Each paper has `started.json`, an atomic `result.json` containing IR, analysis, raw report and costs, then an immutable hash-linked `checkpoint.json`. Completed output is revalidated and reused. A committed result with a missing checkpoint is recovered without calling the runner. A started attempt without committed output becomes `ERROR/InterruptedAttempt`; uncertain work is not implicitly charged again. Review its caches and ledger before an explicit retry in a new run. Ordinary runner failures preserve exception type as terminal ERROR and do not erase other papers. Budget exhaustion stops all further calls; remaining paper/rule rows are `ERROR/BudgetNotRun`, `attempted=false`. Thus a table can have 1437 terminal records while execution coverage is incomplete. `all_documents_executed`, failed/pending document counts and measured object coverage show that distinction.

Rebuild derived reports without a model configuration or API using:

```bash
/data/envs/six-rule-dev/bin/python scripts/paper_compiler_corpus.py summarize \
  --suite FINAL_SUITE --out NEW_OUTPUT_ROOT
```

Summary verifies suite identity, checkpoint ownership and result hashes. Missing checkpoints remain pending; summary never manufactures terminal outcomes or starts execution. `records.jsonl` and `summary.json` are derived outputs; records are atomically replaced and their SHA256 is included in the summary. Historical frozen source and result artifacts remain immutable.

## Coverage and cost interpretation

`records.jsonl` contains one record per completed terminal paper/rule pair, with original source hash, suite/program/model/pipeline versions and result hash/path. UNKNOWN, NOT_APPLICABLE and ERROR remain separate from PASS/VIOLATION. No all-paper labels are assumed, and `accuracy_metrics` stays null.

The summary counts target objects independently of diagnostic row count. It reports measured targets, unique reported/missing objects, conclusive objects, per-object states and unmeasured failed documents per rule. It retains IR scope coverage separately, including partial pages/bibliography/reference-use coverage. Empty targets and missing diagnostics do not become PASS. Evidence availability is counted by kind and content coverage. Diagnostic-linked source spans inherit their linked content level; only usable `coverage=full_text` counts as complete full text. Abstract-only and truncated full text remain separate. A document having some full text does not imply that every object or citation is covered.

The paid runner samples the same shared ledger before/after frontend and pipeline stages, and before/after each paper. It records spent and conservatively committed CNY, request and token deltas, uncertain request deltas, and per-stage totals for successful stages. Failed attempts retain the available whole-attempt ledger interval; unavailable stage attribution is not invented. These intervals may include concurrent calls on the shared ledger, which is disclosed. Actual prices/usage are determined by the existing client and ledger, not by the estimator. Final reporting still needs a metered accepted-candidate pilot, actual all-corpus usage, and experiment/ablation costs from their own phases.

## Inventory evidence recorded on 2026-10-19

The preparation command verified all 479 source hashes without modifying the input. There are 479 distinct contents, total 7,169,860,758 bytes, largest 213,091,485 bytes. The input frozen file SHA256 is `d9fe8a7fccab01a70aeee573917c13cee3252a744668e4678ce15fd37c246b6f`. Three rules imply 1437 required terminal records. The separate reports are under `/data/results/paper-compiler/corpus-preparation-20261019/`.

Only three historical original IRs were present: 25/60/210 bibliography entries and 39/96/401 reference uses. An illustrative cold scenario with two optional frontend/model calls, bibliography extraction batches of two, one generated request per entry and one per use yields 79/188/718 opportunities per sampled paper; scaling the smallest/largest to 479 gives 37,841–343,922. This is conditional workload, not an actual paid-call count or a statistical confidence interval. Fully reusable caches can require zero new paid calls. The final suite may declare more/fewer requests and the other 476 papers may lie outside this range. No monetary estimate or sufficient remaining budget is claimed.

## Validation and remaining acceptance

Tests use fake external boundaries and the real offline `pipeline.detect`, never paid Maas. They cover source tampering, version/configuration changes, completed and interrupted recovery, budget termination, mixed successes/failures, output locking, missing objects/rules, partial scope coverage, evidence levels, same-ledger deltas, no-model summary and subprocess CLI operation.

The entry-point implementation supports T33/T48/T51/T53 but does not by itself complete any of those whole acceptance items. Required remaining evidence includes stage costs on real accepted candidates, per-round plots/counterexamples and experiment reports, complete final frozen reproduction artifacts, and the actual accepted final 479×3 scan with its object/evidence coverage. Deployment and permissions are outside this protocol's implementation.
