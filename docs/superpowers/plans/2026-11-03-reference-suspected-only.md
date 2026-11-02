# Reference suspicion presentation implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Show only evidence-supported suspected nonexistent references as individual informational review items; show a clean zero when completed verification produces no supported suspicion.

**Architecture:** Keep the existing strict detector and publication gate. Do not promote retrieval misses or identity ambiguity into findings. Preserve internal UNKNOWN diagnostics and actual execution failures, while adapting completed R32 runs to the user-approved zero-or-review presentation in the shared live/saved report pane.

**Tech stack:** Node adapter, React/TypeScript, Vitest, existing Python evidence checks.

**Spec:** User confirmed on 2026-11-03 that evidence insufficiency should display no problem, and only strongly supported suspected nonexistent citations should be listed under Info for manual review. Identifier mismatch boundaries are deferred.

## Constraints and review focus

- Do not weaken existence proof or turn UNKNOWN into an internal PASS.
- Only confirmed/publication-approved findings become informational review items. Legacy SerpAPI misses do not qualify.
- Preserve entry text, evidence and PDF location for every supported review item.
- Completed ambiguous references display green zero; real execution errors still display detection failure.
- Apply identically to live and saved reports, including old saved UNKNOWN/SerpAPI runs.
- Do not rewrite saved reports, business data, credentials or the protected results CSV.

## Tasks

- [x] Add adapter and shared-pane regressions for internal UNKNOWN with clean presentation, legacy misses, two individually located review items, severity filtering and publication suppression; run RED.
- [x] Adapt R32 findings to Info/manual review and keep diagnostics internal; normalize historical report presentation without modifying stored results.
- [x] Render each supported reference's source excerpt and review request. Keep automatic repair actions off informational review items.
- [x] Run focused Node, frontend and existing strict Python evidence checks; build and independently review.
- [ ] Verify main and push with czh1302.

Verification: 99 frontend, 32 adapter and 27 strict Python checks passed; production build passed. Additional archive checks had four passes and one pre-existing failure: `archive-saved-repair-suggestions.test.tsx > shows all saved archive suggestions without generation buttons, including inactive citation cards`. The same missing automatic load callback assertion fails with the baseline FindingsPane from b87232c; no R32 rows are involved. Scope remains this rule's presentation rather than unrelated suggestion loading.
