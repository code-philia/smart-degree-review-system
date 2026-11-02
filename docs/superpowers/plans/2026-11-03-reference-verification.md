# Free reference verification implementation plan

> Execute inline using the executing-plans workflow.

**Goal:** Restore useful, accurate R32 verification without a SerpAPI quota dependency.
**Architecture:** Shared public evidence cache, staged deterministic identity lookup, independent credential pacing, explicit report coverage and historical diagnostics.
**Tech stack:** Existing Python evidence runtime, Node adapter, React report pane.
**Spec:** docs/superpowers/specs/2026-11-03-reference-verification-design.md

## Constraints
No paid providers or Semantic Scholar; no secrets in Git or evidence; no modification of historical report data or protected CSV; main only; campus deployment only after relevant checks.

## Review focus
Empty or unavailable search is never a violation; valid DOI for a different work is never a pass; one failing provider cannot discard other evidence; unresolved historical cache is retried without repaying extraction; a publication NO_ALERT alone is never sufficient for PASS.

- [ ] Add failing Python/Node/UI regressions for source fallback, identity guards, cache recovery, key secrecy and coverage.
- [ ] Implement free multi-source lookup and credential selection; retain frozen snapshots and strict identity matching.
- [ ] Fix R32 availability and report mapping; explain legacy pending reasons in the shared report pane.
- [ ] Run related Python, Node and frontend checks plus production build; test configured keys and real retained references from campus.
- [ ] Recheck remote main, push English Conventional Commit, deploy a verified delta release, and verify service/assets/data counts.
