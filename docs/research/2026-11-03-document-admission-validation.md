# Paper identity and structural compilation validation

## Incident and cause

The two-page CCF dissertation recommendation form was accepted by the old PDF frontend. Its native text was placed under a `Paper` root, and IR contract validation checked node types, references and coordinates without establishing paper identity or required core sections. Partial scan handling then suppressed missing-section findings; zero findings were displayed as a pass. A valid serialized IR was incorrectly treated as a valid paper.

## Compilation contract

The public builder now checks document identity and source-level core structure before creating typed paper nodes. The shared service preflight calls this public builder and accepts only a complete compilation proof bound to the PDF SHA-256, contract version and exact profile requirements. Uploads, incremental runs and archive scans use the same admission gate. Invalid, stale, incomplete or unavailable proofs fail closed; rejected inputs execute zero paper rules and produce one severe document finding. Incremental reuse cannot restore old passes after rejection.

Chinese theses require both abstracts, keywords, contents, introduction, body, conclusion and references. English theses require their abstract, keywords, contents, introduction, body, conclusion and references. Research articles require abstract, introduction, body, conclusion and references. Cover pages, originality statements and authorization pages remain ordinary formatting checks, as explicitly confirmed by the user. Document identity rejection is distinguished from a recognized paper with incomplete core structure and from an unreadable/unconfirmed input.

Source checks exclude contents entries and numbered introductory prose from actual chapter evidence. They account for split chapter labels, heading hierarchy, mixed fonts, Chinese heading spacing and IEEE Roman section numbers. Native-text extraction is required; this change does not add OCR or claim universal semantic identification of arbitrary PDFs.

## Verification on 2026-11-03

- 203 Python tests and 13 subtests passed, including identity, structure, public builder, bibliography boundaries and existing local rules.
- 44 backend integration tests passed, including dispatcher rejection, incremental reuse, archive scans, cancellation and invalid proof handling.
- 7 queue/deadline tests passed under Node 22.
- 84 frontend tests passed, including live and saved blocked reports, rule filtering, scopes and exports.
- Production frontend build and `git diff --check` passed.

The supplied recommendation form and four independently sourced non-paper PDFs were rejected by the actual dispatcher with one severe finding and zero executed rules. Sources:

| Type | Source |
| --- | --- |
| Tax form | https://www.irs.gov/pub/irs-pdf/fw9.pdf |
| Software manual | https://www.gnu.org/software/bash/manual/bash.pdf |
| Declaration | https://www.un.org/sites/un2.un.org/files/2021/03/udhr.pdf |
| Thesis writing guide | https://sph.csu.edu.cn/fujian08zhongnandaxueyanjiushengxueweilunwenzhuanxieguifan.pdf |

All six supplied genuine theses (Du Xueying, Li Jia, Lin Bo, Ran Dezhi, Sun Zaisheng and Zhao Yingquan) and three published research articles compiled successfully. Their generated Paper models were identical to the baseline parser output after excluding the new admission metadata. The article controls included a paper about invoices, protecting against rejection based on topic words alone:

- https://arxiv.org/pdf/1706.03762
- https://mural.maynoothuniversity.ie/id/eprint/11620/1/KD-Linear-2017.pdf
- https://arxiv.org/pdf/2208.04011

Independent review found no remaining important or critical findings in the reviewed admission and compilation cases. Detailed local evidence is retained separately under `output/non-paper-gate-20261103/`; source PDFs and business report data are not committed.

## Follow-up: abstract title language false positive

Report `bc19c18a-a347-4bf0-970f-5feeddc5e108` was incorrectly rejected for a missing English abstract. Visual inspection of the original PDF confirmed that page 5 contains a substantial English abstract and an English Keywords line, while its heading is the Chinese word for abstract. Requiring an English-language heading confused title conventions with section existence.

Source grammar and the core-section rule now share a conservative recovery path: separate front-matter abstract sections must contain substantial Chinese/English prose in the corresponding language and a matching keyword line. Only prose after the abstract marker and before keywords counts; contents and body text cannot supply an abstract. Joined source glyph headings retain their source order. IR rule checks use current visible node text and provenance so deletion or editing cannot resurrect a section from immutable layout observations.

Regression cases cover the mislabeled title through the public builder and completed CLI proof, missing actual abstracts, unrelated English text on the cover/contents/body, unrelated preface prose before or after an abstract marker, and deletion of the English abstract from the IR. The original failing case is retained privately as a real-PDF control alongside the six theses, three articles and five non-paper controls.

Follow-up verification passed 261 relevant Python tests and 13 subtests. All ten paper controls compiled with unchanged model content after excluding admission metadata; all five non-paper controls remained rejected. Independent review confirmed both ordering and IR-deletion regressions are covered with no remaining important or critical findings.

## Follow-up: semantic consumers and cross-page keywords

Report `fdcb13fe-3ea4-4766-96cc-ae1659face72` used the same source PDF and compiled successfully, but the bilingual semantic consumer still extracted abstracts by their heading language. The prior recovery had updated compilation and core-section presence only; it had not updated this downstream extractor. Consequently, the English abstract was absent from the semantic facts and no comparison request was sent. The English keyword list also ended in `Classifica-` on page 5 and continued on page 6, while extraction stopped at the page boundary, incorrectly reducing six keywords to three.

The semantic extractor now accepts an alternate-language abstract heading only when bounded prose language and the terminating keyword label corroborate the target language. Actual abstract titles remain section boundaries; small top-margin continuation headers preserve multi-page abstracts, including headers only slightly smaller than the main title. A hyphenated keyword may continue onto the immediately adjacent page after corroborated running furniture, with actual next-section titles retained as boundaries. Existing source-preserving hyphens remain in display values and are removed only in the separate semantic matching values.

The source yields 670 Chinese abstract characters, 2326 English abstract characters and six complete English match keywords, anchored on pages 4/5. A real campus-model verification ran both bilingual rules in parallel in 11.71 seconds: both passed with model usage recorded. Regression checks compare the six genuine theses and three articles against the previous extractor, and tests cover missing keyword boundaries, repeated actual titles, small continuation headers, and public builder-to-semantic-consumer integration.

Final verification passed 293 relevant Python tests and 13 subtests. The six genuine theses and three article controls retain exactly the same extracted facts as before this semantic-extraction change. The independent boundary review found no remaining important or critical findings; the final real-PDF compatibility check additionally protects single continuation headers and 11.4/10.5-point title/header combinations.

## Follow-up: introductory diagram mistaken for the final conclusion

The latest campus GUI retest rejected an archived 149-page doctoral thesis (source SHA-256 `379127ea9b2d7834ebbcde7e6d4f3fae3c659a2ffcd0c7175ab2127df2cc6094`) as missing its body and skipped all 15 selected rules. Source-level tracing showed that a 9.72-point conclusion label in an introductory diagram on physical page 26 ended the body scope before the later main chapters; the actual introductory heading was 16 points. The parser had correctly extracted those main chapters, but the admission boundary discarded them.

Conclusion candidates now use the established introductory heading's font size and numbered section hierarchy. Smaller diagram labels and numbered introductory summary subsections cannot end the body or satisfy the required final conclusion. The same filtered candidates govern both checks. Unknown style retains the existing fallback; paper identity, required core sections and non-paper rejection remain in force.

Three regression cases were observed failing before the fix and passing afterward: an introductory diagram label preceding a real body/conclusion, that label without any actual conclusion, and an introductory summary subsection without a final conclusion. Fresh verification passed 296 relevant Python tests and 13 subtests. Thirteen real paper controls, including all three latest GUI samples, compile with unchanged model content after excluding admission metadata; five non-paper controls remain rejected. Independent review found no remaining important or critical findings.

The retest's PDF export uncertainty was checked separately in standard Microsoft Edge through real student login and browser download events. The six-page report downloaded successfully, and both it and the 107-page original PDF were rendered and visually inspected. The embedded preview reported ready, with no page errors. This does not assert that the in-app browser's separate native PDF viewer has been fixed. Local evidence is retained under `output/campus-gui-fix-20261103/`.

## Follow-up: source surrogate in full semantic execution

The post-deployment full 15-rule GUI run successfully admitted the doctoral thesis, then exposed previously blocked failures in the typo and numeric rules. One native source paragraph on physical page 78 contains a lone U+D835 surrogate. The typo HTTP request encoded unescaped JSON directly as UTF-8; numeric auditing did the same while recording the entire model. Both failed before their remaining work could execute. The source model itself was preserved correctly, including this unpaired source character.

Semantic HTTP requests now use the same escaped JSON byte serializer as the compiler transport. Live preflight additionally established that the campus proxy itself rejects unpaired surrogates after decoding JSON. These code units are therefore represented as literal escapes in the model input before outer JSON serialization, leaving valid Chinese/mathematical Unicode intact. Original messages, Paper IR and audit source text retain the original units. Numeric audit records and semantic progress/final/error output also escape JSON strings. No source replacement or deletion is performed. Regression cases first reproduced failures for audited and unaudited requests, trace initialization, strict UTF-8 CLI output, and the decoded provider input, then passed after the boundary fixes. Tests verify source values, trace artifact hashes and replay, and request/cache behavior. Two preexisting stale typo test fixtures were separately reproduced at the parent commit and updated to the existing confidence and word-boundary contract; production typo filtering is unchanged.

Fresh verification passed 307 relevant Python tests and 13 subtests. The actual doctoral model round-trips through trace serialization unchanged; its affected prompt chunk produces valid UTF-8 provider text with literal source-code-unit escapes in a network-free reproduction. Independent serialization review found no remaining important or critical issues. Live provider acceptance and complete web execution are checked separately rather than inferred from the stubbed transport tests.
