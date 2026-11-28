# Numeric uncertainty response compatibility

The external 16-paper numeric cohort stopped with two incomplete results despite 54 successful HTTP responses and zero 429s. One response claimed a contradiction with an explicitly empty evidence list; another valid uncertain response omitted its optional suggestion. Their bounded repairs repeated the same response.

Keep the required reason and source/citation contracts. Default an absent or null optional suggestion to an empty display string. When an otherwise well-formed result cites an explicitly empty evidence list, downgrade any asserted agreement/contradiction to inconclusive, record the normalization, and retain its explanation as an informational finding. Never certify agreement, fabricate evidence, or relax malformed/missing required fields and invalid citation checks.

Verification: reproduce both cases before implementation, run the full numeric regression suite, and replay saved real responses without HTTP calls. Confirm previously successful results retain their substantive fields. Independently review the change before publishing.

Publish only this numeric validation change; keep the deployed RPM-first joint dispatch, two queues, output caps, and safe quota window unchanged. Preserve the stopped cohort and its provenance, clear its active table row, and resume that cohort followed by remaining tiers. Preserve the actual implementation release for every cohort rather than relabeling historical measurements as a new release.
