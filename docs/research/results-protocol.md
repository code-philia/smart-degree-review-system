# Existing study results reporting protocol

This entry point prepares evidence for T48/T49/T50/T51. It does not run a benchmark, detector, semantic API, feedback loop, heldout evaluation or deployment. It does not mark an experiment complete or establish performance on 30/300 rules. The report is a derived view of existing artifacts from `paper_compiler.study.run_study`.

## Input contract and command

From `/data/projects/smart-degree-review-system/backend`:

```bash
TMPDIR=/data/tmp MPLCONFIGDIR=/data/cache/paper-compiler-matplotlib \
/data/envs/six-rule-dev/bin/python scripts/paper_compiler_study_report.py \
  --study-root EXISTING_STUDY_ROOT --out NEW_SEPARATE_REPORT_ROOT \
  --plot-libs /data/envs/paper-compiler-report-libs
```

Optional `--interventions HUMAN_AUDIT.json` supplies an explicitly self-reported human-effort audit. Add `--test-only` for every fake/fixture demonstration; its JSON, Markdown and figure titles are labelled TEST ONLY. Test output belongs under `/data/tmp/.../test-only-report`, never the formal study or results roots. The command needs no model configuration or API keys. Exit 0 means the report was produced; inspect its `status`, `integrity`, `protocol_errors` and `heldout_available` to determine experiment status. A data error is represented as ERROR rather than converted into a successful experiment.

The output directory must be new and outside the frozen study root. Inputs are never rewritten. The reader accepts only paths within the study root and never parses files named oracle. It reads `summary.json`, or `checkpoint.json` for an incomplete study, plus `protocol.json`, `frozen-benchmark.json`, `shared-initial.json`, `selection-frozen.json`, `artifact-index.json`, condition loop records and round/evaluation/package artifacts. The benchmark manifest is used for existing case/split/source-domain metadata; its sealed oracle paths are not followed. No results are fed back into revision or selection.

A completed study requires a matching artifact index, indexed protocol/summary/benchmark/selection files, both conditions with every rule frozen as an executable version or a verified terminal failure, real suite identities wherever executable packages exist, and actual indexed `heldout-final.json` and `heldout-shared-initial.json` records for every rule. These files must match their summary entries and the frozen test-case IDs/counts. An empty evaluation object or a `completed` flag is insufficient. Failed integrity or protocol completeness yields ERROR and suppresses heldout comparison figures. Incomplete studies retain their stop reason, feedback/validation observations and unavailable heldout values; they do not acquire invented test scores.

## Outputs and metric semantics

- `results.json` retains source status, integrity, protocol problems, comparison rows, round data, stratification, cost availability, observed model changes, human-effort audit status and source SHA256 provenance.
- `comparison.csv` compares the common initial draft, `program_only` and `joint` on existing post-selection test records. `rounds.csv` separates feedback and validation observations, candidate errors, cross-rule rejection, selected candidates, actual model/analysis-contract differences and recorded resource intervals. Its JSON counterpart retains the original `resource_usage` fields; CSV serializes the budget snapshots as JSON strings. `groups.csv` separates real/constructed context, open/controlled evidence domains and declared mutation types.
- `examples.json` contains bounded examples from existing feedback failures, with their original source/evidence details. `patches.json` contains observed generated-code diffs between recorded candidates. Neither output is sent to a generator. Generated code line counts describe generated artifacts and are not counts of human-written special code.
- `report.md` links the derived figures and tables and states limitations. The output `artifact-index.json` hashes every emitted file. Source artifact hashes and the report implementation hash support reproduction.
- `figures/heldout.{png,svg}` exists only for a completed, verified selected study with actual heldout records or explicitly unexecuted per-case terminal-failure records. `figures/rounds.{png,svg}` shows recorded feedback/validation candidate rounds where measurements exist. Missing measurements are not drawn at zero. PNG uses 300 dpi and SVG retains vector/text output from Matplotlib.

The strict balanced accuracy denominator includes every valid verified negative/control case. A negative/control is strictly correct only when the original target is PASS and the changed target has its expected outcome. UNKNOWN and ERROR remain in the denominator and receive no strict credit; their counts and conclusive-case denominator are exported separately. A missing class makes balanced accuracy undefined. An absent evaluation has null metrics, including case/UNKNOWN/ERROR counts; it does not report zero observations as measured performance. A compiler-failed initial draft with actual per-case ERROR records and both class denominators keeps its genuine strict failure score of 0, retains the observed strict failure metrics and states that semantic detection was not executed; semantic detection rates remain null. Its `semantic_detection_metrics` is null; no diagnostic precision/recall is claimed. Zero strict failure scoring and missing evaluation are different states.

The initial comparison is shared rather than presented as two independent initial systems. Final `program_only` and `joint` rows refer to their frozen selections, not whichever candidate most recently appeared. Recorded feedback stopping reasons do not establish scientific convergence. Curves may overlap when observed results are equal. Candidate-round axes show only integer recorded rounds. Heldout labels are neither read from sealed files nor used to tune a candidate here.

## Source, evidence and independent evaluation limitations

Origin and evidence-domain strata remain separate; constructed contexts cannot stand in for untouched paper prose, and controlled-catalog absence cannot establish nonexistence on the public web. This report can describe only the recorded sources and tested tasks. It does not infer unseen evidence coverage from a successful status. Full corpus object/content coverage is supplied by the separate corpus protocol.

Model-assisted labels and same-model correlation require disclosure and an independent audit. The script does not infer judge independence from missing metadata. A disjoint heldout split controls selection leakage but does not by itself prove human label validity or model-family independence. Unobserved rule counts, formal all-corpus precision/recall, confidence intervals and scaling to 30/300 tasks are not invented.

## Human code and intervention audit

Without an audit, human intervention and task-specific code counts are `not_recorded`/null, not zero. A supplied audit is `self_reported_unverified`; its source SHA256 is recorded. It may contain:

```json
{"events":[
  {"id":"review-1","kind":"manual_intervention","rule_id":"example","description":"Reviewed source grounding."},
  {"id":"adapter-1","kind":"task_specific_code","rule_id":"example","description":"Declared a special adapter.","lines_added":4,"lines_removed":0},
  {"id":"framework-1","kind":"generic_framework_change","description":"Implemented a shared framework facility."}
]}
```

Event IDs must be unique; line counts must be nonnegative integers when supplied. Task-specific line totals stay null if a task-specific-code event lacks a line count. Generic framework changes, generated program size and task-specific human code remain distinct. This format makes reporting possible; a complete audit and independent verification remain separate work.

## Costs, timing and actual revisions

The report prefers the study's saved `resource_usage` over legacy summary counters. It exports the recorded `elapsed_seconds`, `budget_before`, `budget_after`, `spent_cny_delta`, `committed_cny_delta`, `requests_delta`, `prompt_tokens_delta`, `completion_tokens_delta`, `available` and `accounting_scope` values. Current elapsed time is cumulative active execution across resumes, including active failed/interrupted attempts and excluding offline waiting. A legacy summary's elapsed time is retained with an explicit caveat that accumulation across resumes is not established. Legacy study-level CNY/request/token totals use only observed `budget_before` to `budget` differences; absent round measurements stay null. An observed zero remains zero, and a negative committed-cost delta remains negative.

Each round's real `resource_usage` is exported to `results.json` and `rounds.csv`, including the original budget snapshots. A `round-*/resource-usage.json` sidecar may exist without a completed `round.json`; its wrapper status and start time are retained as `resource_usage_status` and `resource_usage_started_at`. Such a row is explicitly `resource_only_incomplete_round`, with no invented evaluation score or successful selection. `available=false` means the shared ledger snapshots were unavailable: the measured active elapsed time can still be present, while budget snapshots and cost/request/token deltas remain null. It does not mean the execution took zero time or cost zero.

`accounting_scope='shared_ledger_interval'` denotes an observed shared-ledger interval, not exact per-condition/task attribution. Concurrent benchmark calls may be included; formal study runs should be sequential where practical and disclose overlap. Round or initial-candidate intervals are not summed into a second study total, since their scopes can overlap. The report retains separate `initial/task-*/resource-usage.json` or `summary.initial[rule_id].resource_usage` observations without charging cached initial artifacts again to condition round 0. A root `initial-preparation.json` is exported under `stage_resources.initial_preparation` with its own source hash and `included_in_study_interval_total=false`: that earlier preparation fee is neither added to nor substituted for the measured study interval. No additional budget ledger is created or queried, no ledger contents are read by this entry point, and no prices are guessed.

Model revisions are measured from saved model `node_types` differences and final selected suite models relative to the common initial ontology, not from whether a prompt claimed to revise a model. Candidate changes, analysis-contract changes and final selected condition changes are separate. Rejected candidates and compile failures do not become successful selected model revisions. A change between shared artifacts does not by itself identify which individual task caused every cross-rule difference.

## Plotting dependency isolation and verification

On 2026-10-19, Matplotlib 3.11.2, NumPy 2.5.4 and Pillow 13.0.0 were installed exclusively under `/data/envs/paper-compiler-report-libs`. The existing `six-rule-dev` environment, production environment and system disk were not changed. Pip cache was `/data/cache/pip-paper-compiler` and temporary files `/data/tmp`. The installation command used the existing Python's pip with `--target /data/envs/paper-compiler-report-libs --only-binary=:all: --no-compile`. The CLI supports `--plot-libs`, or `PAPER_COMPILER_REPORT_LIBS`; its default discovers that dedicated target. Matplotlib configuration/font cache is under `/data/cache/paper-compiler-matplotlib`. Each result records the actual Matplotlib and Python versions.

Tests use fake clients and the real study artifact format, all labelled TEST ONLY. They cover ordinary/failed initial comparisons, incomplete budget stops, hash tampering, missing selection or actual heldout records, UNKNOWN/ERROR denominators, accepted semantic model changes, manual unknown counts, shared-ledger arithmetic, cumulative resource records across resumes, real zero/negative deltas, legacy/no-ledger null values, interrupted-round sidecars, separate preparation fees and no-model CLI operation. Tests create no paid requests. Static figures are inspected for clipping/readability; their fixture values are not experimental results. Complete formal studies and their independent audit are still required before T48/T49/T50/T51 can be marked complete.


## Exhausted selection failures

The pre-evaluation amendment `framework-20261019/study-protocol-v4.json` was recorded after inspecting an existing shared initial compile failure, before any formal heldout prediction. A loop that has recorded every allowed attempt, ends with `round_limit`, and has no executable best candidate freezes an explicit terminal failed selection. Budget limits, interrupted or partial rounds, and freeze stops remain incomplete and never acquire fabricated outcomes. Successful versions and explicit failed selections must be disjoint and together cover every requested rule in each condition before heldout evaluation starts.

`program_versions` contains only genuine executable versions. `failed_selections` records the failed rule, exhausted stop reason and attempt count; no version or program is invented. A real suite containing only successful rules is explicitly partial (`has_complete_executable_suite=false`, `complete_rule_coverage=false`); no executable package means no suite version. The final website acceptance still requires all three configured rules and cannot deploy such a partial suite as a complete system.

A frozen terminal failure produces an auditable per-case ERROR/ERROR record with `execution_performed=false`, the original denominators, strict failure score zero and null semantic detection rates. This is failure accounting, not actual detector execution. Other genuinely selected candidates are independently tested after all selection outcomes freeze. A study may therefore complete its experiment with failed selections; completion does not imply that every condition produced a runnable detector.

The saved initial R33 answer contains a reserved generated-analysis name. The program-only condition freezes that analysis contract, while the joint condition may revise it. This limitation is disclosed explicitly: an improvement caused by repairing this initial contract cannot establish that a richer semantic ontology improved citation reasoning. Neither the initial answer nor its sealed benchmark labels is manually repaired, and no replacement first answer is sampled.
