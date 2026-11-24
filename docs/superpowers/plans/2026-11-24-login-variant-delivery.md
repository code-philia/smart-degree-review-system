# Login variant delivery implementation plan

> Execute inline in the existing isolated feature worktree; obtain a final independent review.

**Goal:** Make either approved login page selectable for ordinary delivery from the same application source.

**Architecture:** One AuthPage with shared authentication logic and two presentation branches. Build selection defaults to campus. A generated manifest binds the selected page to backend preload. Cross-platform npm commands select the variant explicitly.

**Spec:** `docs/superpowers/specs/2026-11-24-login-variant-delivery.md`

**Constraints:** No main mutation or production 3000 restart; no changes to business/detection/report/credit logic, private configuration or product wording. Keep the formal preview split and all approved visuals intact.

1. Add failing build-selection and backend manifest tests (campus, split, legacy fallback, malformed/unknown values).
2. Add build selection/manifest and cross-platform build commands; restore the approved campus presentation conditionally inside the same AuthPage. Keep jAccountEntry shared.
3. Make backend preload read the manifest; run auth/session/static/proxy checks for both variants and clean-build both variants.
4. Independently review changes, document development sync and final delivery/rollback, push only the feature branch, and update the independent preview using the split build.
5. Verify both built variants in the browser, chosen assets/headers, main/production preservation, and record delivery evidence.

Review focus: no campus renderer/image on split mount, no split style leakage into campus, malformed configuration fails clearly, image preload always matches the selected build, and the normal application must not depend on the separate preview proxy.
