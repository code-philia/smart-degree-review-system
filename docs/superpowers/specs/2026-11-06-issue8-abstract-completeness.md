# Issue 8: abstract completeness

An abstract heading alone does not establish a complete abstract. Core-section
validation must distinguish a missing section from an incomplete one before
constructing a typed Paper. Failed compilation creates one severe finding and
skips every selected detector.

Use native PDF text and layout only: no OCR, model/API calls, or arbitrary
minimum abstract length. Bound each abstract by its own heading, the next
abstract, contents or a main chapter. Thesis abstracts need readable body text
and a nonempty keyword closing within that scope. Research articles do not
acquire thesis-specific keyword or bilingual requirements. This is structural
validation, not a claim to detect arbitrary semantic omissions within prose.

Preserve short and multi-page abstracts, repeated running headers, split
keyword labels, inline article abstracts, and an English abstract titled 摘要.
Never borrow prose/keywords from another abstract, contents, body or appendix.
R6 checking an edited IR must use current nodes, not restore removed text from
the original layout. User messages name missing versus incomplete sections and
explain the observed evidence without calling a confirmed thesis a non-paper.

For a Chinese thesis, report “缺少中文摘要” or “缺少英文摘要（Abstract）”
when the respective abstract is absent. Name partial sections separately as
“中文摘要不完整” / “英文摘要（Abstract）不完整” with the observed structural
cause. English theses and research articles retain their own section profiles.
Keep these specifics in both the run summary and severe finding. Show one
overall explanation that compilation failed and all thesis rules were skipped;
the user explicitly does not want an individual reason for each skipped rule.

Work on fix/issue-8-abstract-completeness; test offline, review, merge to main,
push and deploy externally. Campus deployment waits for VPN access.
