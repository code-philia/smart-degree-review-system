# Reference identity repairs implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax.

**Goal:** Remove the confirmed reference-verification false positives while retaining genuine DOI, author and title errors.

**Architecture:** Repair the new rule's private native extractor and deterministic identity comparison. Use bounded, fixed-host authoritative evidence for historical versions or dates; never guess equivalence or hide warnings without resolving their cause.

**Tech Stack:** Existing Python native PDF adapter, Node service and Vitest/pytest.

**Spec:** User-approved approach in this conversation: no LLM; correct authors, years, titles, group attribution and historical versions; regress the 10 real PDFs / 757 references and preserve valid alerts.

## Global constraints

- Do not modify other rules, PDFs, saved reports, feedback or credential policy. The only frontend copy change is the user-requested native-text explanation removal in both languages.
- No OCR, LLM, automatic paid searches, blanket mismatch suppression or corpus-specific identifiers/allowlists.
- Preserve original citation text and PDF anchors.
- Supplementary requests must be bounded, cancellable, fixed-host and bound to the cited identifier.
- An unverified result is not a verified repair; report any remaining uncertainty explicitly.

## Review focus

- Short uppercase surnames must remain separate while APA initials remain joined.
- DOI, arXiv identifiers and access dates must not replace publication years.
- Genuine author differences and incomplete titles must still raise meaningful results.
- Current and explicitly cited historical versions must not be conflated.
- Unavailable, malformed or identifier-mismatched supplementary evidence cannot establish equivalence.

## Tasks

### 1. Private native field extraction

**Files:** `backend/scripts/reference_verification_extract.py`; new `backend/tests_py/test_reference_identity_archive_regressions.py`.

- [x] Add explicit real-citation regression cases for author splitting, arXiv years, embedded title quotations, compound names and numbered labels with trailing punctuation, plus APA/IEEE controls.
- [x] Run the new tests and confirm expected failures.
- [x] Repair field boundaries and parsing without changing source text or provenance.
- [x] Run the private adapter and boundary suites; record results.

### 2. Deterministic metadata comparison and bounded evidence

**Files:** `backend/src/normative/referenceVerificationCore.js`; optional focused metadata parsing helper; new `backend/tests/reference-identity-archive-regressions.test.js`.

- [x] Add failing provider-boundary cases for subtitles, mathematical notation, author transliteration, corporate-leading author lists, authoritative group attribution, print/online dates and arXiv versions. Include genuine mismatches and unavailable/forged evidence controls.
- [x] Normalize only equivalent representations; preserve known source dates and explicit versions.
- [x] Resolve disputed dates/version/group names from bounded authoritative evidence. Do not accept arbitrary author overlap or title similarity as an exact identity.
- [x] Run related service/access/security/rate/cancellation regressions.

### 3. Real corpus verification and review

**Artifacts:** `output/reference-identity-final-20261125/`.

- [x] Re-extract the same 10 source PDFs using candidate code and rerun only this rule against real providers in an isolated database.
- [x] Compare all 757 entries, original anchors, 109 confirmed false positives and 3 real citation differences; enumerate residual unverified items and any new alerts.
- [x] Run the backend test command; distinguish pre-existing failures if any. Do not change unrelated failures.
- [x] Obtain a fresh whole-change review and resolve material issues with regression tests.
- [x] Produce the final before/after evidence and report precise source/deployment status. No historical-report edits are authorized by this task.


## Validation outcome

- 10 real archive PDFs, including 3 English-body theses; 757 references.
- 109 previously confirmed false alerts now have supported results: 106 verified, 3 publication upgrades. All 3 genuine bibliographic differences remain; no new substantive alerts in this corpus.
- Full batch plus targeted historical/group-author rechecks; original citation text, IDs and PDF anchors unchanged. PDFs, saved reports, feedback and credentials were not updated.
- Related checks: 252 backend, 64 native extraction and 27 frontend tests passed; frontend build passed. Whole-suite legacy/environment failures were isolated using an unchanged baseline and targeted reruns; the full suite is not claimed green.
- Fresh code review: all identified material issues resolved with regression cases, final review found no further P1/P2 in scope.
- User cancelled the card redesign. Only the explicitly requested native-text explanation removal remains in both languages.
- Repair source and evidence are local; no main push, service deployment or saved-report migration performed in this task.
