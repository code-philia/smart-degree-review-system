# Recover understated publication-list headings

Goal: fix the false missing-achievements finding in report96c6609d without changing any other check. Its physical page264 has a centered, bold14.04pt “List of Publications”, body12pt; shared IR merges it into the preceding BibliographyEntry and rule34's14.64pt recovery threshold rejects it.

Design: retain existing heading and large-title paths. Add a conservative rule34-only native recovery path requiring an exact live title alias, full bold source glyphs, at least body-size text, centered standalone line, first body text on its page, preceding spacing and a following publication-list label or numbered item. Continue excluding page furniture, ToC/table/figure/unknown ancestors and source text removed from live IR. Do not lower shared thresholds or change bibliography boundaries, schema or other rules.

- [ ] Add failing native PDF regressions for modest/body-size English headings and negative heading-like text.
- [ ] Implement only the local achievements recovery predicate and run focused/full related checks.
- [ ] Fresh-parse the affected English264-page PDF and all100 archived original PDFs (including10 English theses), compare all six native rule outputs and IR against exact2faa1eb. Independently verify native achievements headings; preserve the existing unrelated core findings. Add positive/negative independent copies where useful; do not count copies as real papers.
- [ ] Independent review; push main and deploy external with existing Publisher and complete source/data/public verification.

Constraints: no model/OCR/mail, no online re-detection jobs, no original PDF changes, no campus deployment. The user explicitly authorized correcting only this confirmed finding in the linked saved report: retain all other runs and row fields, back up the original row, update the exact finding/outcome/three counts with a compare-and-swap guard after deployment, and verify all other database rows unchanged. Test this correction against an isolated database copy first. Keep runtime configuration and report-export WIP untouched. Existing unrelated test failures require exact-base proof.
