# Saved analysis evidence fallback implementation plan

**Goal:** When a numeric finding has no saved source excerpts, display candidate descriptions already present in its saved analysis under the existing Evidence heading.

**Architecture:** A pure frontend helper selects sentences describing referenced evidence and retains their qualifiers. The existing card displays those descriptions only when saved evidence is absent. It never creates source excerpts, page locations, verdicts or model requests.

**Tech stack:** Existing React/TypeScript frontend and Vitest.

**Spec:** Existing numerical finding design, with the user's explicit correction: no additional origin badge or heading; retain the existing verdict and do not rerun checks.

## Constraints

- Preserve claim → evidence → discrepancy order, all saved report data, verdicts and counts.
- Extract descriptions only from saved analysis; retain negative and applicability clauses.
- Do not present generated descriptions as source quotations or invent source navigation.
- Keep all descriptions visible with the existing typography and spacing.
- Resolve the selected language through the existing report translation state; do not leak untranslated analysis in English.

## Task

- [x] Add failing tests for missing excerpts, the six-reference report, qualifiers, unrelated statements, existing evidence priority, English updates and immutability.
- [x] Add the pure sentence helper and the display-only fallback to NumericFindingContent.
- [x] Run related tests, production build and the historical100 read-only replay.
- [ ] Review, integrate main, deploy the authorized external site through the normal publisher, and verify the target report without rerunning it.
