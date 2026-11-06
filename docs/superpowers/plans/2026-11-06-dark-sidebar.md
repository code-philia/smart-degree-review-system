# Dark Sidebar Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline and obtain one fresh whole-branch review.

**Goal:** Give the shared navigation a coherent navy theme and deploy it externally.
**Architecture:** Scope sidebar tokens and state styles to desktop/mobile surfaces; keep the light workspace.
**Tech Stack:** Existing React, Tailwind, shadcn and CSS.
**Spec:** docs/superpowers/specs/2026-11-06-dark-sidebar.md

## Constraints and review focus

- Only frontend/src/index.css and frontend/src/layout/AppShell.tsx need product changes.
- Preserve route behavior, widths, typography sizes and the red/white brand asset.
- Mobile Sheet uses a portal: theme the actual surface, not just an ancestor.
- Brand/tagline, active/inactive icons, account states, separators, focus and
  collapsed navigation must remain legible. Keep the main workspace light.
- Existing tests verify behavior; visual checks verify styling. No new tests
  that merely repeat CSS values (developer instruction for low-impact edits).

## Task 1: Theme and release

- [x] Inspect the shared shell/theme and fetch main; create style/dark-academic-sidebar.
- [x] Update scoped sidebar surface/state colors and brand text styles.
- [x] Run shell/navigation tests, typecheck and build.
- [x] Inspect full upload/history pages, account menu, collapsed nav and mobile Sheet.
- [x] Obtain one fresh code review and address material findings.
- [ ] Commit, merge/push main, guarded external deployment and deployed asset/visual checks.

User authorization covers merging/pushing/deploying; no extra approval step.
Retain unrelated untracked previews/logs and the server checkout's existing deletion.

Verification: shell/navigation8tests passed; local production build passed.
Typecheck reports9 existing model.ts diagnostics, identical on untouched565343e
and changed sources. Main content remains light; mobile portal receives the
same theme; focus outline visible; text contrast minimum6.93:1. One independent
review reported no Critical or Important findings. Screenshots/evidence live
outside Git under output/dark-sidebar-20261106.
