# Report exports

Exports use the interface language captured when the user starts the download.
The six formats contain one Chinese or one English edition. Report notification
emails keep the complete Chinese letter followed by the complete English letter.
Source quotations, filenames and replacement text retain their original wording.
English explanatory text uses the existing Qwen translation cache; Chinese export
does not request English translation. None of this reruns the checking engines.

PDF and page images are typeset with XeLaTeX on the server after the existing
report ownership check. DOCX contains editable article paragraphs. Markdown,
plain text and JSON share the same selected-language model and scope.

## Runtime

The Python renderer requires Python 3, XeLaTeX, fontspec, xeCJK, xcolor,
needspace, framed, fancyhdr, hyperref and bookmark. Fonts are Latin Modern Roman,
Noto Serif CJK SC, DejaVu Serif and Latin Modern Math. Poppler `pdfinfo` inspects
the PDF; `pdftoppm` creates image pages. `pdftotext` is used only in QA.

Runtime paths can be set with `REPORT_EXPORT_PYTHON`, `REPORT_EXPORT_XELATEX`,
`REPORT_EXPORT_PDFINFO` and `REPORT_EXPORT_PDFTOPPM`. Defaults are the standard
`/usr/bin` programs. On the external server, the newly added Poppler utilities
are stored under `/data/envs/smartdegree-report-tools/bin`; the two production
path settings live in the private `bilingual.env` configuration. QA can set
`REPORT_EXPORT_PDFTOTEXT` too. Keep new installations on the data disk in line
with the workspace storage agreement.

Each request uses a private temporary directory, removes it when finished and
disables TeX shell escape and unrestricted file access. Limits are two concurrent
exports globally, one per user, 120 seconds, 150 pages and 40 MB. An oversized
export returns an error rather than silently omitting image pages. Cancellation
terminates the active renderer. Export responses are private and not cached.

## Validation

Run the backend `tests/report-export.test.js`, mail design/delivery/notification
tests and jAccount return-path tests. Frontend export, language-link and auth
tests cover locale capture before asynchronous work and language persistence
through sign-in. Render real saved-report PDF and DOCX files and inspect them;
XML/text extraction alone does not verify typography.

The isolated real-report smoke workflow generated all six formats in both
languages from a saved 13-rule, 41-finding report without submitting a new check.
The existing frontend and backend full suites contain baseline failures; compare
failure names against clean main before attributing failures to this change.
