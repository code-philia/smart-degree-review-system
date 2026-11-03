# Compact Upload Page Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement the single task inline. Steps use checkboxes for tracking.

**Goal:** Apply the selected compact single-column design with a taller upload target.

**Architecture:** Keep the existing React component, state and handlers. Express the reviewed preview with local Tailwind classes and a semantic instructions heading; add no dependencies or global style overrides.

**Tech Stack:** React, TypeScript, Tailwind CSS, Vitest, real-browser visual checks.

**Spec:** `docs/superpowers/specs/2026-11-03-compact-upload-page-design.md`

## Global Constraints

- Develop and push directly on `main`, as explicitly instructed by the user.
- Preserve report cards, upload/rule/job behavior, all instructions and the removed eyebrow.
- Instructions remain 14px / 28px. Upload target: desktop 216px minimum; narrow screens 192px minimum.
- Protect the results CSV and unrelated untracked files. Keep backend and campus business data untouched.

## Review Focus

- Long filenames must wrap inside the drop target.
- Narrow screens must not develop horizontal overflow.
- Expanded rule groups must retain all controls and disabled states.
- File removal, running/restored jobs and stop actions must retain their handlers.
- Instructions must precede progress and the live report in document order.

## Task 1: Apply and verify the compact upload layout

**Files:** Modify `frontend/src/components/paperLint/ThesisUploadPanel.tsx` only for product code. Include the spec and this plan in the final commit.

**Interfaces:** Existing `Props`, callbacks and page-header interface remain unchanged.

- [ ] Translate the preview into component-local classes: 1152px content width, 20px card radius, 48px upload icon, consistent step labels, shallow blue instructions region with heading. Increase the drop target to the dimensions above.
- [ ] Run existing upload, detection-scope, history-controls, report-copy and live-progress tests, plus the production build. Do not add tests that merely assert styling classes.
- [ ] Verify the real built page in the browser: desktop dimensions, 390px width, long filename, expanded rules, pending/running state, intact instructions and default collapsed rule selection.
- [ ] Request one independent review, resolve material findings, and commit using an English Conventional Commit.
- [ ] Push using the authorized `czh1302` GitHub account, deploy the verified frontend release, and verify live asset hashes and health.
