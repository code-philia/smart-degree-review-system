# Frontend Refresh Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement the tasks inline. The user chose the recommended direction and explicitly requested direct implementation.

**Goal:** Direct guests to sign-in and refresh the login page, navigation, and shared visual styling.

**Architecture:** Keep React, React Router, Tailwind, and existing UI components. Add a session gate outside the workspace shell. Use the original 1920 × 1080 campus gate background from the SJTU teaching portal, as requested by the user's later steering, with CSS/SVG document and AI artwork; no new runtime dependency or remote image request.

**Scope:** Login page, whole-site navigation, and common styles only. Keep detection/report layouts, backend APIs, permissions, and data unchanged.

## Global Constraints

- Work in the existing server development checkout on rules-31-33-detectors. Preserve concurrent work and untracked files; compare source hashes before applying edits.
- Keep jAccount and local password authentication usable, including callback errors and logout.
- Add the complete system explanation from the user verbatim.
- Use English Conventional Commits. Main push and deployment require authorization.
- Use CSS transform/opacity animation only on decorative artwork, with prefers-reduced-motion support. Do not animate PDF content.
- Use local campus assets; retain source attribution. No OCR or detector/API changes.

## Review Focus

- A slow session lookup must not flash the workspace or prematurely redirect a signed-in user.
- Guests opening report URLs must reach sign-in before report requests mount.
- Local login must safely return to a requested local route; external redirect targets must be rejected.
- At narrow widths and 200% zoom, login controls, disclosure links, and navigation must remain reachable without horizontal overflow.
- Reduced motion must stop decorative animation, and keyboard focus must remain visible.

## Task 1: Session gate and route behavior

- [x] Write routing tests for anonymous root/deep links, pending session lookup, signed-in access, and safe return after local sign-in.
- [x] Run these tests against the existing implementation and observe the guest routing failures.
- [x] Add RequireSession.tsx, gate the workspace routes in App.tsx, and safely restore the intended route from LocalAccountLoginForm.tsx.
- [x] Run routing and existing authentication tests; preserve all previously passing auth behavior.

## Task 2: Academic technology login and shared visual refresh

- [x] Replace the old hero with campus photography, a paper-review illustration, AI nodes, and restrained decorative motion.
- [x] Make jAccount the clear primary alternative beside a clean local login form; keep trial/help content accessible in compact disclosures.
- [x] Add the full requested system explanation, with a readable responsive layout.
- [x] Tighten the shell width, navigation spacing, and header. Update shared buttons/cards and tokens without restructuring detection or report pages.
- [x] Build and inspect desktop, mobile, reduced-motion, keyboard, and authenticated navigation flows in a preview isolated from production.

## Task 3: Verification and handoff

- [x] Compare the complete frontend test results with the recorded baseline (193 tests: 121 passing, 72 existing failures); list any differences.
- [x] Perform a fresh review, resolve consequential findings, and record evidence.
- [x] Commit explicit files on the daily development branch. Provide a preview and concise test results; publish only within the user's authorization.

## Verification results

- Targeted authentication, session routing, and navigation: 31/31 passing.
- Full frontend: 202 tests, 130 passing, the same 72 baseline failures by exact test name; no new failures.
- Browser checks: widths 320, 390, 720, 768, desktop 1440; no horizontal overflow, local login/logout, protected report routing, navigation collapse, trial disclosure, keyboard focus, and reduced motion passing.
- Build passing. Fresh read-only review: no Critical, Important, or Minor issues.
- Actual external campus authentication remains covered by the unchanged integration; no real personal jAccount login was performed. Existing mobile drawer animations are unchanged.
- Evidence stored outside the repository at /data/results/frontend-refresh-20261031/. Main and deployment remain unchanged pending a user request.
