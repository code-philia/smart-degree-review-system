# B-v5 Login Release Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Publish the user-approved B-v5 login preview to the external site, preserving the latest remote main.
**Architecture:** Port the approved HTML/CSS into AuthPage; retain real jAccount redirects and the existing trial-account dialog. Reuse the approved water solver/rendering and wind geometry with React-managed cleanup. Ship the exact original 4K PNG and embedded brand image as named public assets.
**Tech Stack:** React, TypeScript, Vite, CSS, WebGL, Vitest, existing immutable-release publisher.
**Spec:** User-approved local login-B-v5-filing-preview.html (SHA256 f882503edc9c590268ff3a4f0bf5e72c7b3fffc1bb240bd190844dd3fa2b03a7).

## Global Constraints
- Develop only in /data/projects/smart-degree-review-system; preserve .codex-release-build and prior stash.
- Start from remote main 82b4bb17af30bbd28d4c0e3af25d4555ee1fd749, then recheck remote main before pushing.
- Exact B-v5 PNG, original service label weight, 1px divider, desktop card left -24px / top -64px, 82% card white with 5px blur.
- Keep water, five leaves and two swaying grass groups; no gear interaction or hand animation.
- Show 沪交ICP备20260352 at lower right. Preserve production data, authentication and configuration.
- External deployment only, using existing status/check/deploy workflow; no internal deployment.
- Preserve file-navigation policy restriction; do not bypass it for preview automation.

## Review Focus
- Water masks must exclude foreground hands, paper, cup, pen, plinth and bank at all cover aspect ratios.
- Reduced motion, unmount and page visibility must stop/restart loops without duplicate listeners.
- Real jAccount safe return targets and error messages must work, with trial accounts still hidden behind the version label.
- CSS must remain scoped to sign-in and preserve trial-dialog portal styling.
- Released source, public image, built assets and service cwd must match the pushed revision; old report JSON must remain unchanged.

### Task 1: Baseline and integration
- [x] Read instructions, fetch/check remote main and fast-forward; create feature branch in existing directory.
- [x] Run baseline targeted sign-in/report tests; capture results.
- [x] Update scene tests for selected B-v5, no gear, real login/filing and foreground mask checks; confirm new cases fail on old implementation.
- [x] Port AuthPage.tsx, auth-campus.css, AuthCampusScene.tsx, waterSurface.ts, pondRenderer.js and .d.ts; add exact public image/brand assets.
- [x] Verify selected preview assets/CSS provenance and targeted tests/build.

### Task 2: Review, push and publish
- [x] Request independent code review and resolve findings.
- [ ] Recheck remote main; integrate upstream updates if any, rerun affected checks.
- [ ] Commit with czh1302 identity, merge/push main without force.
- [ ] Capture read-only production data snapshot and run publisher status/check/deploy.
- [ ] Verify public health, frontend/image hashes, service active/enabled/cwd and preserved reports/users.
- [ ] Record deployment evidence and clean up task-only helpers.
