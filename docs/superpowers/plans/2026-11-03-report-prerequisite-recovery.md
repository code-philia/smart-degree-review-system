# Report prerequisite recovery

User authorization: fix the two diagnosed report issues, push main, and deploy campus.

## Scope and approach

Keep the existing report selector and strict citation identity checks. Show the existing prerequisite detail cards in the all-level view, respecting the selected rule. Recover bibliography localization after an unavailable model request only when one source candidate has a prominent heading followed by sequential numbered references in the latter part of the document. Retain partial coverage and the original model error. Ambiguous candidates remain unresolved; do not clear request protection or fabricate a successful model response.

## Tasks

1. Add failing report tests for all-level prerequisite details, coexistence with findings, and selected-rule filtering. Reuse the existing cards without adding prerequisite notices to the issue count. Run the report and numeric frontend tests.
2. Add failing PDF tests for recovery from a model error with corroborated source layout, and rejection of ambiguous or unsupported candidates. Implement conservative structural recovery in `frontend.py`. Run frontend extraction, citation, and reference regressions.
3. Replay the supplied PDF with the real blocked-request path, verify extracted entries, build the production frontend, review the diff, verify remote main, commit and push. Deploy a sealed release with backup and rollback, and verify actual service-user behavior and HTTP health.

## Verification and constraints

Preserve the original report and all business data. Preserve private key configuration and request guard records. Do not modify the protected mutation-results CSV. Existing unrelated test failures must be reported separately. Use English Conventional Commits. Remote main is checked before integration and push.

## Progress

- Remote main verified via the existing public development server: `01f4bcb`; local HTTPS fetch is unavailable. No incoming commits.
- Root causes verified from the target report, raw compiler artifact, and request guard records.
- Frontend regression reproduced before implementation; focused checks: 26 passed.
- Backend recovery regression reproduced before implementation; related extraction/evidence checks: 172 passed.
- Real PDF source replay under the service account recovered 161 bibliography candidates while retaining partial coverage.
- Production frontend build passed. Full frontend suite: 318 passed, 84 failed; untouched baseline: 317 passed, the same 84 failed. No new failures. Detailed names are retained in the deployment validation artifact.
- Independent review found no critical or important issues.
