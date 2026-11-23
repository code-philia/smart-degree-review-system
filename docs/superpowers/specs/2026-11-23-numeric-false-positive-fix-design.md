# Numeric consistency evidence repair

The user approved the five-part repair proposal on 2026-11-23 and explicitly requested complete real-paper testing, a main push, and external deployment. This document records that agreed scope; no further approval is required to implement it.

## Goal

Repair the 15 confirmed table-supported numeric false findings in eight original theses, without converting unsupported, contradictory, or condition-mismatched claims into passes. Also verify the six separately identified prose-supported cases, four partial findings, and the complete 100-original-PDF numeric corpus.

**Evaluation correction after full-scope source review:** A395 is partially false positive: the main cold-start table explicitly supports 17.61%, while a separate overlapped-user table reports 21.36%. The old missing-evidence reason is incorrect, but the abstract's unqualified maximum still needs a population-scope clarification. The effective strict repair set is therefore 14 findings in seven papers, with five partial controls. The original 15-item audit is preserved and the correction is appended privately with exact native quotes and arithmetic checks; no report-specific production rule is permitted.

A subsequent atomic-target adjudication moves A177 to true false positive: the combined-prefetch throughput is 3.69× and supports approximately 3.7×; the 2.1× statement is offload-only, and the 285.25s contradiction concerns the separate timing target A176. Effective counts return to 15 strict findings in eight papers and four partial controls, with corrected membership. On the user's clarification, validation prioritizes complete test types and representative real-source cases; the full 100-paper detection sweep is no longer required.

## Design

1. Keep the grounded source sentence, but represent each verification target separately: number, metric, unit, method, baseline, dataset, condition, comparison, and exact native source offsets. Values such as 3.57 m must not inherit unrelated values as new obligations merely because the abstract sentence contains six numbers.
2. Recover native PDF tables using both available line/text strategies. Preserve geometry and raw cells; merge alternatives only on corroborated geometry and source identity. Recover multilevel headers and continuation context only when native evidence supports them. Do not invent values or silently treat every limited table as reliable.
3. Replace keyword-only average/maximum vetoes with evidence checks. Definitions, table headers, and the complete in-scope comparison set can establish semantics. A single matching value, an incomplete range, or a missing definition still cannot prove the claim.
4. Retrieve bounded native metric definitions and formulas in addition to result rows. Verify arithmetic using a restricted Decimal expression evaluator with source-bound inputs. Never execute model-generated code or assume every AUC improvement subtracts 0.5.
5. A summary contribution can cover multiple genuine child methods and their chapters. Extend internal mapping only with source-grounded contribution/method evidence; keep unrelated chapters excluded. Recheck missing evidence in bounded, relevant scopes rather than globally increasing retrieval size.
6. Follow explicit native table references within the same research chapter to recover floats that cross subsection headings. Keep the full native target sentence, plus a bounded preceding sentence for anaphoric conditions, separate from the atomic public declaration.
7. A source-only second check may examine a consistent result when a selected table and explicit same-method/metric prose contain competing measurements. It must cite the selected table and the competing paragraph, cannot use definitions as measurements, and cannot invent a scope distinction. Calls are bounded to one check and one contract repair per triggered declaration.

## Constraints

- No frontend, translation, user-facing message, or suggestion wording changes. Internal verifier instructions and audit metadata may change.
- No OCR or scanned-page interpretation. Native PDF text, table geometry, and page rendering only.
- No stored report, original PDF, schema, quota, account, mail, or unrelated rule changes.
- Preserve native offsets, page geometry, evidence identities, existing public outcome types and report compatibility.
- No hardcoded report IDs, author names, gold numbers, or paper-specific verdict exceptions in production.
- Genuine contradictions must remain actionable; uncertainty must not become passed.

## Validation

Use failing unit/source-contract tests before production changes, then integration and adversarial tests. The original read-only audit is in output/numeric-fp-reaudit-20261123 (outside the product repository). It records 15 strict table false findings, six prose cases, and four partial findings; these are evaluation labels, not production inputs. Evaluate actual original PDFs and formal model integration in private offline runs, followed by a 100-paper numeric-only sweep. Compare original PDF hashes and all saved database rows. Review every new candidate alert and lost established true alert, not only aggregate counts. Obtain independent review and exact merged-source checks before main push and the standard Publisher external release.
