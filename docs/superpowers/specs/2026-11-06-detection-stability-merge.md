# Detection stability branch integration

User-directed integration of `fix/issues-5-10-detection-stability` into current main. Base: `a12ac4e`; incoming: `dbb84d1`. This supersedes the earlier requirement that every core-section omission must globally block a genuine paper.

- Preserve the incoming branch history and fixes, plus main's issue #7, #8 and #12 fixes and dark sidebar.
- Identify a document as a paper before building any Paper nodes. Non-papers, unreadable documents, crashes, malformed/stale proofs remain blocked; no rule executes.
- Genuine papers may explicitly compile a partial IR when a core section is missing or incomplete. Preserve missing vs incomplete and Chinese vs English abstract diagnostics.
- Report R6 structural defects. Continue independent rules. Mark only rules depending on unavailable evidence as inconclusive/unsupported, with a reason; never call them passed.
- Keep the default compiler strict; production dispatchers explicitly opt into partial compilation after the identity gate. Complete papers retain normal execution.
- No OCR or live model/API verification. Native PDF regression and controlled external-service doubles only. This integration does not claim all unfinished issues on the branch are solved.

Approach: resolve the two admission conflicts semantically rather than taking either side wholesale. Retain main's detailed structure assessment, add the incoming partial path, validate complete/partial proofs defensively, and narrow reference dependency handling to an actually missing bibliography. No deployment is requested in this task.
