# Issue 7: distinguish array dimensions from bibliography references

Source: https://github.com/code-philia/smart-degree-review-system/issues/7

The original thesis produces eight false missing-reference findings for 4096:
six in native C function-parameter declarations on PDF page 58, one in the
inline bias tensor W2[4096] on page 116, and one in a figure's separately
positioned W2 (HBM) / [4096] label on page 117. These are three distinct native
text/layout cases, not a bibliography-number threshold problem.

Keep the shared citation parser used by missing-reference and uncited-reference
checks consistent. Recognize bounded typed array declarations, explicit tensor
nouns with short symbolic variables plus positive computational/memory context,
and diagram dimensions supported by nearby
same-column variable/storage labels and another labelled multidimensional shape.
Preserve source positions. Superscript citation markers and ordinary citations
after model names or elsewhere on the same page remain citations. Neither a
large number nor an isolated bracket list is sufficient to discard a marker.

Do not alter R12, R4, report layouts, or core-section compilation behavior. Use
native PDF text/geometry only, with no OCR or model/API calls. Work on
fix/issue-7-array-citations, then merge main, push and deploy externally after
verification. Campus deployment remains deferred until VPN access returns.

All issue expectations and acceptance criteria:

1. Original thesis: all eight false 4096 findings disappear (6/1/1 on pages
   58/116/117), with no replacement findings elsewhere.
2. R02 v1/v2/v3 still report their injected true invalid citations.
3. Explicitly preserve invalid [188], [199] and [177], including when next to
   array syntax. Large genuine citations such as [4096] remain detectable.
4. Numeric array subscripts/tensor dimensions are not citations; they must not
   count as reference uses even if the same number exists in the bibliography.
5. M01 and M02 mixed regressions retain all genuine missing citations and lose
   the inherited eight false positives. Retain unaffected rule results and
   native PDF coordinates for genuine findings.

Uncertain bracketed prose remains eligible for citation checking. The detector
does not infer arbitrary program semantics or silently suppress an entire page.
