# Unified experimental rule and incremental results

User specification: one upload workflow, groups named 格式规范, 内容规范, and 论文逻辑审查（实验型功能）. Move external-reference existence into content; merge former text/language groups. Include numeric abstract checking as an experimental opt-in rule. Remove implementation details from rule descriptions. Display completed rules immediately, including restored jobs; push main using czh1302 on the public server and deploy both servers.

## Constraints
- Preserve detector ownership, API request contracts, shared PDF extraction, cancellation and persistence.
- No OCR, new paid requests, runtime budget/guard changes, data migration, or replacement of existing user files.
- Preserve independent findings and numeric evidence for mixed reports; retain old numeric URLs and job recovery.

## Steps
1. Add failing frontend grouping and incremental job tests, Python completion-order test, and backend streaming transport tests.
2. Implement explicit presentation groups, optional experimental rule, unified navigation and mixed-report details.
3. Stream per-rule JSONL from the existing parallel semantic runner; serialize progress persistence, deduplicate completions and update upload results on every snapshot.
4. Run focused regression tests and builds, review the complete diff, push main without overwriting concurrent changes.
5. Publish immutable releases on public and campus hosts, retaining configuration, databases, archives and port mappings. Verify catalog, auth, reports, PDF ranges and frontend assets on both.

## Decisions / progress
- Numeric rule remains opt-in: experimental work should not silently add latency to all existing uploads.
- Existing numeric URLs resolve to the unified upload page, retaining recovery of old numeric jobs.
- Full report and repair/feedback controls remain on saved reports; the running upload page shows completion-order outcomes and findings without pretending it has a saved report.
- Verified: frontend focused regression 8 files / 52 tests; backend MVP 13 files / 59 passed, 2 skipped; new streaming transport/orchestration tests pass; Python fast-before-slow/shared-parse regression passes; frontend production build passes.
- Review: fixed pane state loss when switching mixed-report tabs; real-pane regression failed before the fix and passes afterward. Final review has no important outstanding findings.
- Baseline-only failures independently reproduced at unchanged c341988: numeric-review-details expects an obsolete PDF-link interface; paper-lint-jobs submits retired rule IDs (6 failures). Neither detector nor component is changed to restore those obsolete contracts.
