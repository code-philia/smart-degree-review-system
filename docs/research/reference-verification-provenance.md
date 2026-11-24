# Multi-source reference verification provenance

This application's `reference_verification_check` follows the identifier-first,
metadata-comparison and source-disclosure approach explored by
[RefChecker](https://github.com/markrussinovich/refchecker), inspected at commit
`27a81896c0c3d7361fb95b4d14b24a86f02c9c0d` (upstream MIT license).
The compact category presentation was informed by
[RefCheck](https://refcheck-tb6kzeogjer.qoder.zone/).

The adapter and database client here are repository-native implementations;
RefChecker's complete server, UI, authentication, model providers and dependency
tree are not bundled. This release queries OpenAlex and Crossref metadata and
the arXiv API for explicit arXiv identifiers. An optional user-supplied SerpAPI
Google Scholar key supplements unresolved references. It makes no model-powered
web-search or OCR calls. Source availability is reported separately from a
reference's identity and field comparisons.

These capabilities do not establish novel reference-verification research
contributions. Comparisons with upstream require controlled real-paper
evaluation rather than assuming accuracy from implemented feature lists.
