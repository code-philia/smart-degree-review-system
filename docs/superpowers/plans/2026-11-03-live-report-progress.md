# Live report progress and statistics implementation plan

**Goal:** Show selected experimental-rule execution warnings as an explicit statistic, preserve pending rules in live severity filters, and prioritize numeric warnings before numeric informational findings.

**Scope:** Shared live/saved report components and their focused regressions. Preserve confirmed severity counts, total inclusion of execution warnings, strict reference suspicion presentation, existing rule selection and business records. The execution-warning filter continues to include only affected rules, never unrelated pending rules.

## Steps

- [x] Add regressions for conditional live/saved execution-warning statistics (including zero before completion), pending-rule visibility and loading across error/warning/info, transition to completion, and warning-before-info numeric ordering; run RED (nine expected failures).
- [x] Include running options in severity visibility before severity counts, while retaining the execution category boundary. Reuse the predicate for selection and loading state.
- [x] Add responsive conditional statistic cards when the numeric rule was selected; reuse numericExecutionWarnings and existing presentation totals.
- [x] Sort findings of the numeric rule by severity before page/index, preserving other rules' order and PDF identities.
- [x] Run focused frontend checks (112 passed), production build and independent review.

Release procedure: verify remote main/account, push and deploy with backup and HTTP/asset checks.
