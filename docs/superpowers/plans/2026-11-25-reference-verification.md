# Reference verification implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:executing-plans. Independent settings, onboarding and provider modules may run in parallel with explicit file ownership.

**Goal:** Deliver multi-source reference checking, encrypted account OpenAlex keys and replayable two-step onboarding.

**Architecture:** New rule ID and service integrate with existing durable paper jobs; the retired rule remains hidden. Native PDF extraction and source-grounded metadata comparison feed existing reports. Settings secrets never enter public results.

**Tech stack:** Node 22, SQLite, AES-GCM, Python/PyMuPDF, React/Radix and existing locale/theme systems.

**Spec:** `docs/superpowers/specs/2026-11-25-reference-verification-design.md`.

## Global constraints

- No OCR, model web search, unrelated copy changes, historical report rewrites or alternate login deployment.
- New rule `reference_verification_check`; old `sjtu_rule_32` stays retired.
- Optional per-account encrypted OpenAlex key with platform/Crossref fallback.
- New onboarding version for all accounts, replayable in Settings.

## Review focus

1. Wrong account or encryption-key loss must never reveal or use another user's secret.
2. Provider downtime or uncatalogued works must not become fabricated-reference alarms.
3. Preprints, name variants and cross-page extraction must not become false mismatches.
4. New rule results must remain visible in jobs/history/export without reviving old rule results.
5. Account changes, narrow screens, dark mode and keyboard replay must work.

## Task 1: Secure reference preferences

Files: `backend/src/auth/referenceSettingsService.js`, `referenceSettingsRoutes.js`, database schema and focused integration tests.
Interface: GET/PUT/DELETE `/api/auth/reference-settings`, writes require `expected_user_id`; PUT accepts `api_key`; GET returns `{configured,key_hint,storage_available}`. `getReferenceCredentials(userId)` returns private `{personalKey,platformKeys}` only to runtime callers. `REFERENCE_SETTINGS_ENCRYPTION_KEY` is 32-byte base64. Red/green tests cover auth, ciphertext, invalid data, isolation and deletion.

## Task 2: Settings and guide

Files: `SettingsDialog.tsx`, `AccountAnnouncement.tsx`, `FeedbackAnnouncement.tsx`, new scoped API/UI files, `announcementService.js`, existing shell only as needed. Consume Task 1 contract. Replay event `smart-degree:replay-guide`; second step opens reference settings. Tests cover bilingual settings, sensitive response absence, account switching, versioned claim and replay.

## Task 3: Provider verification core

Files: `backend/src/normative/referenceVerificationCore.js`, focused tests. Interface `verifyReference(entry,{personalKey,platformKeys,signal,fetchImpl})`; entry includes `{id,text,title,authors,year,doi,arxiv_id,type_code,location}`. Return `{category,reason_code,matched,comparisons,sources,coverage}`. Categories verified/suspected/mismatch/upgrade/incomplete/unverified. Fixed OpenAlex/Crossref/arXiv destinations, no model calls. Use failing fixtures then minimum implementation for title/identity matches, metadata conflicts, uncovered works, provider failures, quota fallback, cache credential isolation and cancellation.

## Task 4: PDF, orchestration and presentation

Files: new native extraction script and Python tests, `referenceVerificationService.js`, catalog/job service, rule registry/groups, finding component and export model. Parse numbered/author-year entries with physical page provenance; partial extraction remains unverified. Run native core under cancellation and existing job deadlines, passing authenticated `userId` internally. Show category/source/field comparison, including unverified entries and honest totals. Do not offer unrelated AI repairs. Tests prove old hidden rule and other rules remain unchanged.

## Task 5: Verification and deployment

- Run focused backend/frontend/Python tests and build; compare known baseline suite failures rather than claim all suites green.
- Run real archived English and Chinese PDFs read-only and live provider probes using public cited metadata; cover success and failures with deterministic fixtures.
- Review secret boundaries and GUI keyboard/theme/locale/mobile behavior.
- Commit/push main, configure private encryption material, stage immutable releases, back up data, deploy both existing sites and check health/version/assets. Preserve all original reports and feedback.
