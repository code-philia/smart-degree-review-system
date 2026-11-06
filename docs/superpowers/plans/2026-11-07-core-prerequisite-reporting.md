# Core prerequisite reporting implementation plan

> Execute inline, using failing regression tests before production changes.

**Goal:** Core completeness is severe; dependency failures explain missing sections once; source-code ellipses cannot supply a missing contents section.

**Spec:** User requests in this chat on 2026-11-07. Applies to all prerequisite failures, not only eight numbered examples. Explicitly selected core checks remain visible. Non-papers remain rejected; genuine partial papers remain usable by independent rules. No OCR or external model/API tests. Preserve right-side report layout and existing business data.

**Architecture:** Keep structural admission in Python. Carry section prerequisite metadata in unavailable rule runs. Filter only automatically added findings already explained by those runs, consistently in progress, final, archive and incremental results. Set core severity through the rule catalog and backend result construction.

## Tasks

- [ ] Add and observe failing regressions for severe core findings, generic prerequisite deduplication, explicit selection, unrelated missing sections, progress/archive/incremental persistence.
- [ ] Implement section-based deduplication in `paperStructureChecks.js` and its result/progress consumers; retain background validation and prerequisite messages.
- [ ] Add and observe failing Python regressions for body code ellipses and genuine contents leaders, including wrapped/positioned PDF text. Tighten contents recognition using entry text and page-number evidence.
- [ ] Run relevant Node and Python suites; rerun real original thesis, eight section-removal selections, explicit core, independent rules and non-paper controls without OCR/API.
- [ ] Review the complete diff; fix material review findings; commit using English Conventional Commits, merge latest main and push.
- [ ] Stage an immutable intranet release, verify native scenarios before activation, back up database/config, atomically activate with rollback, verify actual service version and VPN HTTP assets.

## Review focus

- Explicit core selection must not be hidden by unavailable dependencies.
- Unrelated missing sections must remain severe and visible.
- Progress and incremental merges must not resurrect suppressed automatic findings.
- Missing/partial abstracts and missing keyword tails must remain distinct.
- Real contents with split leaders/page numbers must remain recognizable; body diagrams/code must not count.

## Execution record

Ruling: Work on a new branch in the existing checkout; keep unrelated untracked files untouched. The user has authorized branch creation, main push and intranet deployment.
Baseline: main/origin main `12e409f`; real missing-contents thesis previously reproduced the ellipsis false positive.
