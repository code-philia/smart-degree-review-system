# PDF Page Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Allow direct physical-page navigation in both report previews.

**Architecture:** PdfPane owns the editable page field, validation and toolbar. PdfViewer exposes pagechanging events through an optional callback while retaining its existing navigation handle. Both report types already share these components.

**Tech Stack:** React, TypeScript, Tailwind, PDF.js, Vitest, Playwright.

**Spec:** ../specs/2026-11-03-pdf-page-navigation-design.md

## Global Constraints

- Preserve existing finding/anchor navigation and document loading recovery.
- No backend changes, new dependencies or protected CSV edits.
- Use main and English Conventional Commits; push with the user's GitHub account.
- Deploy the frontend atomically and retain the current backend process.

## Review Focus

- Invalid, fractional and out-of-range page input must never reach PDF.js.
- Loading, load failure and PDF replacement must not retain stale page bounds.
- Manual page position must survive live finding refresh.
- Editing must not rebuild the viewer or lose typed input to page events.
- Page event listeners must use current callbacks and be removed on unmount.

### Task 1: Shared navigation and synchronization

Files: frontend/src/components/paperLint/PdfPane.tsx, PdfViewer.tsx; frontend/tests/pdf-page-navigation.test.tsx, paper-lint-viewer-navigation.test.tsx.

- [x] Write tests for no-finding jumps, validation, bounds, loading, document changes, live refresh, page events and listener cleanup.
- [x] Run the new tests and observe failures before implementing.
- [x] Add the toolbar and optional onPageChange callback without viewer reinitialization.
- [x] Run navigation, loading, workspace and report regression suites, then build production assets.

### Task 2: Review and publication

- [x] Obtain an independent review and resolve important findings.
- [ ] Commit/push verified changes to main using czh1302.
- [ ] Package exact committed source and tested production assets; deploy frontend only with rollback checks.
- [ ] Verify actual page jumps, bounds, scrolling, finding links and responsive layout in live and saved reports.

## Verification record

- Observed the navigation suite fail on the previous implementation (13 failures), and the event-forwarding test fail against the previous viewer.
- Final related regression: 30 suites, 179 tests passed; production Vite build passed.
- Independent review: no important or critical findings. The field deliberately retains an unsubmitted draft after blur so clicking Jump preserves the typed destination.
- Publication and actual-browser evidence is stored separately in output/pdf-page-navigation-20261103; pending release checkboxes are completed operationally after this source commit.
