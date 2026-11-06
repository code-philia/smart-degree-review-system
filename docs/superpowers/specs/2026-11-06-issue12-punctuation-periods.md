# Issue 12: native Chinese/English sentence-ending punctuation

Source: https://github.com/code-philia/smart-degree-review-system/issues/12

Read the complete issue and satisfy all four acceptance criteria, using the
original thesis, R12_v1/v2/v3 and M05. Original baseline has zero R12 findings;
v1 has three comma findings; v2 currently finds only the page-9 Chinese full stop
and misses two on page 8; v3/M05 each find a semicolon but miss two Chinese
sentence-ending ASCII periods on page 40.

Root causes: Chinese punctuation candidates omit ASCII periods. Separately,
punctuation_prose rejects a whole English paragraph containing ordinary words
such as "require", treating them as pseudocode regardless of their context. A third cause is whole-paragraph exclusion when
inline mathematics contains an equals sign or arrow, hiding later prose.

Add bounded Chinese sentence-period candidates, including sentence end and
adjacent Chinese sentences. Keep decimals, versions, section numbers,
abbreviations, file names, quoted examples, ellipses, code, diagrams, tables,
bibliography and scanned-text exclusions. Narrow English pseudocode exclusion
to explicit algorithm labels/numbered instructions instead of ordinary words
inside prose. Scope equals/arrow exclusions to their Chinese sentence, so later
prose in the same merged paragraph remains checked. Preserve
the existing English sentence-evidence requirement and comma/semicolon behavior.
Keep source offsets and native glyph coordinates; do not alter text or PDF.

Acceptance matrix:

1. R12_v3: both ASCII full stops on PDF page 40 detected as sentence-ending
   punctuation, with exact glyph locations. Retain its page-27 semicolon.
2. R12_v2: all three injected Chinese full stops detected (two on physical PDF
   page 8, one on page 9), without misclassifying ordinary English prose as code.
3. R12_v1: retain all three page-26 comma findings; v3/M05 semicolons unchanged.
4. M05: detect both page-40 periods and its page-27 semicolon; original thesis
   remains clean. All single/mixed real-PDF and related native regressions pass.

Use native Paper IR/PDF text and geometry only; no OCR or model/API calls. Work
only on fix/issue-12-punctuation-periods from main 1be26a5. No #14 or UI changes.
After review and verification, merge/push main and deploy externally with the
guarded release CLI. Campus deployment waits for VPN. Do not post comments or
close the issue without a user request.
