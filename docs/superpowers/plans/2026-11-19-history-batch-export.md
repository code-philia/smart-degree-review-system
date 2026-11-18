# History batch export and selection

**Goal:** Select reports across history pages and download the selected saved reports as one ZIP in any existing export format.

**Design:** Retain the history table and management toolbar. Keep the existing page checkbox and add explicit toolbar actions for selecting the current page, all matching records, and clearing selection. Searching resets selection, as today. Show the selected count and a primary export action beside the existing delete action.

Reuse the six single-report export formats and their saved-report model. Fetch the rule catalog once, then process reports sequentially, including saved repair suggestions and optional document metrics. Preserve the selected language throughout. Package files with numbered unique names in a ZIP; stop with a visible error if any report fails. Cancellation/unmount prevents downloads and subsequent work. Bound archive contents to 128 MiB and advise selecting fewer reports if exceeded.

**Approach:** Extend the existing frontend; existing authenticated detail/export endpoints already enforce ownership. A new server batch endpoint would duplicate rendering and authorization. Multiple automatic browser downloads would require extra browser permissions and lose a single completion signal.

**Constraints:** No report writes, new detection, PDF changes, detector/model/limit configuration changes, dependency installation, or edits to server reportExport WIP files. Preserve bilingual UI and existing delete behavior. Use the existing isolated source checkout, a feature branch, and the standard external publisher. User has explicitly authorized push and external deployment.

## Implementation / verification

- [x] Add failing behavior tests: cross-page select-all, filtered scope, deselection and export entry.
- [x] Add failing ZIP tests: unique names, saved contents, sequential calls, saved suggestions, failure, cancellation and size bound.
- [x] Implement selection controls, shared format choices, a batch dialog, and bounded ZIP utility.
- [x] Verify bilingual UI, cancellation, stable language and existing selection/deletion/export tests; build production.
- [x] Obtain a fresh independent whole-change review; fix substantive findings and rerun affected tests.
- [ ] Merge/push main, standard check/prepare/deploy, preserve existing DB/PDF/config/WIP state, and verify public resources plus real history selection/download without running detection.

## Ledger

- Root cause: existing header checkbox only uses visible page IDs; no action selects all matching records across pages. Batch management currently only provides deletion.
- Implementation choice: ZIP of individual exports, preserving existing format and language behavior. Fail the batch visibly instead of silently excluding reports.

- Verification: 9 new behavior tests failed before implementation, then passed. Related 15 suites / 125 tests passed. Production build passed. Targeted typecheck exposed one new locale annotation error, corrected; the existing model.ts and layout.ts diagnostics are outside this change and retained.

- Review: independent whole-branch review found zero Critical/Important findings and one minor English progress issue. Added a failing assertion, fixed the split text, then 15 suites / 126 tests passed, including a complete English selection/export flow.
