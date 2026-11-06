# Report advice and count consistency

User request: fix misleading suggestions in the two referenced saved reports and align history totals with detail totals; push main and deploy intranet.

- Reproduce the saved missing-contents and missing-Chinese-abstract runs. Trace advice to pre-merge commit `548c0d9`, and counting divergence to raw repository summary versus frontend execution-warning presentation.
- Add failing regressions for chapter-specific guidance, legacy messages, operational errors, and history/detail parity without database rewrites.
- Share a pure display-summary function between frontend and backend. Include execution warnings, numeric prerequisites/results, reference suspicion filtering and finding severities. Keep raw detector results and user records intact.
- Verify actual saved reports, numerical and reference edge cases, live/final/export consumers, frontend build, and independent review. Merge and push latest main.
- Stage and validate an immutable intranet release with database backup and rollback; verify existing report links and VPN assets after activation.

Constraints: no OCR/model API tests, preserve unrelated untracked files, preserve report card layout, retain chapter prerequisite deduplication and severe core completeness behavior.
