# Four-rule false-positive repair plan

> Execute the user's approved repair request with TDD and an independent final review. Root integrates shared semantic-runner edits; independent work may own the citation parser and a standalone native-text scope helper.

**Goal:** Reproduce and repair the four reviewed classes on their original PDFs, exclude scanned pages from typo checks without OCR, then push main and deploy the external service.

**Architecture:** Keep the shared PDF compiler and saved reports intact. Correct bilingual fact extraction and evidence-backed semantic review, recover only citation-like period-separated identifiers, and gate typo source pages using native PDF provenance. No report IDs, names, page numbers or word-specific allowlists in product code.

**Spec:** User request, 2026-11-23: rerun the papers corresponding to keywords/abstract agreement, uncited references and typo checks, reproduce the false positives and fix them all. Do not check scanned pages or use OCR. Push main and publish external after verification.

## Global constraints

- Base: official main 6abf170a96adab3c69ebc8e2db85f4f4ab7a790e, verified with TLS.
- Preserve original PDFs, saved reports, users, quotas, jobs, mail and private runtime configuration; experiments use separate files under /data/tmp/four-rule-fix-20261123.
- Model reruns are authorized for these selected papers/rules; do not create online jobs or send report emails. Record actual provider/model, inputs and outputs without credentials. Reproduction variability must be reported rather than forcing old outputs.
- No OCR requests, dependencies or fallbacks. Scanned/image-backed text must not enter typo-model requests. Preserve native text on mixed pages when its provenance is demonstrably independent of the scan.
- Keep all retired rule code/data and existing visibility policy intact. Any visible copy edits must cover Chinese and English.
- Keep other checks, shared admission, schemas and frontend layout unchanged. Never blanket-suppress findings or mark API errors passed.

## Review focus

1. Keyword continuations versus genuine new titles, headers, empty pages and unrelated prose; delimiters and within-phrase and, plus meaningful hyphens versus layout splits.
2. Real missing/extra keywords and factual conflicts must still alarm after terminology context and review corrections.
3. Abstract omission must be checked against both complete abstracts, permitting many-to-many sentence correspondence while retaining real scope/strength differences.
4. Period-separated citations must not turn decimal values, numeric arrays or section markers into references.
5. Scan/OCR hidden text and administrative appendices must be excluded without silently disabling valid native body typo checks.

## Task 1: Reproduce originals and freeze baseline

- [ ] Fresh native extraction already establishes 17 original findings across 15 papers; retain those verified sources and hashes.
- [ ] Run the selected semantic/local checks on these PDFs with the exact deployed base, isolated outputs and private runtime environment. Save actual reproduced findings and any nondeterministic differences.
- [ ] Capture selected-rule positive controls and database/PDF baseline hashes. Avoid restarting completed batches unnecessarily.

## Task 2: Bilingual extraction and semantic decisions

Files: backend/scripts/paper_model_bilingual_rules.py, backend/scripts/run_bilingual_semantic_lint.py; focused new/old bilingual tests.

- [ ] Add failing native-layout tests for and phrases, three cross-page lists, meaningful cross-/processing- hyphens, and repeated chapter-header abstract continuation.
- [ ] Make bounded extraction fixes; run native tests red then green, and compare unrelated extracted sections.
- [ ] Add failing model-contract tests for semantic equivalents, full-opposite-abstract recovery of a missing claim and genuine contradictions/omissions.
- [ ] Ground keyword matching in delimiters and relevant thesis terminology, and require evidence-backed review of uncertain mismatches. Review abstract candidates against complete opposite text without requiring one-sentence alignment.
- [ ] Run selected real bilingual rules again; inspect all outcomes, retain real non-target issues and confirm the reviewed false claims disappear.

## Task 3: Citation identifier recovery

Files: backend/scripts/five_rule_detector.py; focused new/old citation tests.

- [ ] Reproduce the real [79. 80] caption using rule24.
- [ ] Add failing tests for clearly citation-like period-space groups and negative decimal/array contexts.
- [ ] Implement conservative recovery, run tests and confirm original reference80 is recognized while real uncited references remain flagged.

## Task 4: Native-only typo source

Files: a small native-text scope helper and tests; integration in run_bilingual_semantic_lint.py owned by root.

- [ ] Prove the real page57 hidden OCR text enters the baseline typo input.
- [ ] Add native PDF tests for full-image OCR overlays, scan-only pages, native text pages with diagrams and mixed scans/native content, administrative back matter and genuine body typos.
- [ ] Filter only unsupported text provenance before model chunks; no OCR fallback. Verify model requests cannot contain scan text and no empty scope is falsely advertised as full-document coverage.
- [ ] Rerun the real typo paper; confirm the scan-related original alarm disappears while native-text positive controls still alarm.

## Task 5: Review, integrate, publish

- [ ] Run relevant Python/Node/frontend suites, plus full available suites and record exact-base failures by name. Build production.
- [ ] Independent final code/evidence review. Resolve blocking findings with regressions.
- [ ] Commit scoped changes, merge main and push exact SHA through the existing TLS/credential route.
- [ ] Use unchanged Publisher check/prepare/deploy; verify source hashes, service health, private config, original rows/PDFs and public assets. No campus deployment.
- [ ] Verify deployed detector against targeted native positive/negative fixtures without model rerunning completed batches. Collect receipts and update the project handoff.
