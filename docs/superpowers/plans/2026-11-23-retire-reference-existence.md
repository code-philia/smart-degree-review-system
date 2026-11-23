# Retire external reference verification

Goal: take sjtu_rule_32 offline and hide its results from every user's saved reports, counts, warnings, scope and exports. Keep original database records and PDFs. Other checks must remain unchanged.

Architecture: one shared retirement predicate; public catalogs and submission validation reject the check. A response-only result projection filters the retired run and associated display metadata, recomputes counters, and is shared by saved/live backend responses and frontend presentation. History lists retain original selected IDs solely for their existing report-category classification, while detail responses expose only active selections. Stale export payloads are rejected rather than exported with removed results. Both language interfaces use the same projection.

- [ ] Add failing catalog, stale-request, two-owner persistence, summary, actual UI and bilingual export regressions.
- [ ] Implement the retirement guard, projection and scope/export/translation boundaries. Preserve unrelated rules and stored data.
- [ ] Run relevant tests and read-only audit all real saved reports without re-detection or model calls.
- [ ] Independent review; commit, push main, standard external Publisher deployment and integrity verification.

Constraints: preserve private config, user report/export WIP, original PDFs and all database rows; no model/OCR/mail, no campus deployment. Previously documented admission test failure is outside scope.

Ruling: operator-only historical archive scan datasets remain original audit material; the requested history surface is every owner's saved paper reports. New archive selections of this rule are disabled too. Metadata-only cleanup preserves existing document admission counters exactly.
