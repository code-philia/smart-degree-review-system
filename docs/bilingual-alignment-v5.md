# Bilingual abstract alignment v5

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
