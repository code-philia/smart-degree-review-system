# Bilingual abstract alignment v5

## Current review threshold: v5.2

Review must supply `fact_checks`: exact source fragments with a coverage
relation and exact target evidence for each covered fact. Claiming equivalence
without fact evidence is a technical failure. All-covered facts suppress an
unsupported omission verdict; any missing source fact preserves a partial
omission even when the model's overall verdict says equivalent. Missing-source
and untraceable-target evidence are rejected. The report retains `model_verdict`
alongside the final coverage-derived verdict.

This adds no per-sentence API requests. The alignment request and one batched
review request remain the full model workflow. Semantic correctness of the
fact-level relations still depends on the model; literal quote validation alone
cannot prove cross-language entailment.

In a live review replay over the original v1 report's saved alignment, Chinese
sentence 15 was retained, sentences 24 and 31 were suppressed, and sentence 18
was retained. This checks review behavior only and does not modify the historic
report. Fact decomposition and semantic coverage remain model-dependent; the
earlier v5.1 calibration limitations below are retained for comparison.

## Previous review threshold: v5.1

The sentence-alignment stage is unchanged. Review now also accepts
`partial_omission`: a matched sentence/group does not explicitly cover concrete
technical components, operations, conditions, mechanisms, results, or scope.
An umbrella description does not automatically cover such explicit facts.
Only actual fact equivalence, wording differences without factual loss, or
uncertainty are suppressed. Partial omissions identify the actual missing
language through `missing_in`, while retaining both source locations.

Calibration replays the five saved candidates from preview report
`1945a1bd-f870-46be-9ee8-5c2b76f66665` against the live campus API, keeping the
original alignment fixed. Chinese sentence 18 and English sentence 20
are retained; Chinese sentences 24 and 31 remain equivalent. Sentence 15 was
retained in one early calibration but remained incorrectly equivalent in the
final replay: the missing concrete mechanism/metric is still an observed model
failure and is not claimed fixed. This is a review
replay, not a new end-to-end PDF report and not a rewrite of the historic report.
The v5 development behavior described below is historical and superseded by
this threshold for partial factual coverage.

The rule uses the existing Paper Model abstract text and sentence numbering.
It never submits individual sentences as separate requests.

1. One request contains both complete abstracts and returns one alignment record
   for every sentence in each direction. Reordering and one-to-many/many-to-one
   correspondence are allowed. Missing, duplicate, or invalid sentence IDs are
   technical failures, not a clean pass.
2. All partial/missing/conflict candidates are reviewed together in at most one
   additional request, again with both complete abstracts. Equivalent wording,
   differences in detail, and uncertain cases cannot generate findings.
3. Only explicitly accepted core omissions without a matching target sentence,
   or contradictions with source sentences on both sides, produce findings.
   Source excerpts are taken from the validated sentence IDs, not model prose.
4. Findings remain capped at three, with independent IDs and the existing PDF
   anchor/highlight path. Full alignment and candidate review records remain in
   report params (`comparison_mode=full_sentence_alignment_v5`) for diagnosis.

This is semantic detection, not an exact translation requirement. A removed
sentence is an alert only when its independent core fact has no equivalent
expression elsewhere in the target abstract. An elaboration of an already
expressed fact is not a missing core fact.

Offline tests validate coverage, correspondence, review gating, independent
findings, and source navigation contracts. They do not measure model accuracy.
`run_rule_regression.py --live-llm` runs the same external PDF fixture manifest
against the actual configured model; without that flag it uses explicit model
contracts and is not evidence of actual model recall.

## Development validation (2026-11-08)

The source was the actual PDF stored for preview report
`56f436fc-bafa-48ca-b6ef-3f62cef8fde9`. Mutations were applied to its extracted
abstract text in memory, not to the source PDF or archived R11 fixture files.

- Unmodified abstract: no findings in the live alignment checks.
- Remove the English independent contribution-summary sentence: one English
  omission finding. Final targeted run used 5917 input / 3802 output tokens.
- Replace the English technical operation: one deduplicated contradiction
  finding, while the mechanism/detail candidate was rejected as equivalent.
  Final targeted run used 6228 input / 4265 output tokens.

These are limited development observations, not a measured false-positive or
recall rate, and not a claim that all archived R11 PDF fixtures passed.
