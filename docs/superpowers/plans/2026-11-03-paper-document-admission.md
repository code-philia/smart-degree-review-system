# Paper document admission

Implement the user-requested backend guard before any rule or Paper Model work. Non-papers produce one severe document finding and no rule runs. Preserve real Chinese/English theses and research articles, with valid core structure; missing required core sections now fail compilation. File names, page counts and isolated academic words are not sufficient evidence.

## Approach
Use a shared local source-evidence classifier: detect explicit non-paper cover/form identities first; require combined academic cover/body or research article structure for admission. Add a separate source-level structural grammar check after identity and before typed Paper construction. Chinese theses require Chinese abstract, English abstract, keywords, contents, introduction, body, conclusion and references. English theses require their abstract, keywords, contents, introduction, body, conclusion and references. Articles require abstract, introduction, body, conclusion and references, without contents or bilingual abstract requirements. Cover/declaration/authorization stay ordinary format checks, per explicit user confirmation. Avoid network/model dependency. A document whose identity cannot be established is blocked with an uncertainty-specific message rather than asserted to be a proven non-paper. Apply the same guard at the web dispatcher and public Paper Model builder. Raw parsing helpers remain private for structural-fragment unit tests.

## Tasks
1. Reproduce the recommendation form: record native-text/scan coverage and the empty-findings-to-pass path. Add classifier tests for forms, regulations/manuals, invoices/resumes, slides, blank/scanned and corrupted files; real-paper controls in Chinese and English and missing-section controls.
2. Implement shared admission and preflight CLI. Assert rejection before bibliography selection, model/API calls, typed Paper creation or any detector dispatch. Treat broken/invalid preflight outputs as rejection, never admission.
3. Return a document-level severe result; suppress all requested rule statuses. Protect incremental merge/reuse. Render the document error consistently in live/saved reports with no fake passing rules, running rules or experiment-warning card.
4. Run tests red/green. Download diverse real non-paper PDFs from primary public sources, test the supplied form, and test all six supplied real theses plus public research articles. Check dispatch is never invoked on rejection and real-paper findings remain unchanged.
5. Review, run relevant backend/frontend checks and build. Commit in English Conventional Commits, push main with czh1302, deploy to campus with database backup and rollback. Drain active jobs before backend restart; verify application health and the deployed guard.

## Review focus
- A recommendation form contains academic words and references but remains a form; renaming it must not change admission.
- Real theses can contain recommendation/declaration forms in appendices; non-paper words inside prose/back matter must not reject the paper.
- A recognized paper with a missing core section must fail compilation, receive a severe structure error and execute no rules; it must not be mislabeled as non-paper. Missing cover/declarations/authorization alone must not block compilation.
- Unknown/scan-only input and crashed preflight must fail closed without invoking detectors.
- Incremental reuse must not resurrect old false passes after document rejection.
