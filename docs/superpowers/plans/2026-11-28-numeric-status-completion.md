# Numeric verifier status completion

The 32-paper external cohort exposed a separate format failure: one paper's three verifier responses omitted `status` despite supplying reasons and source citations. Full-response repair repeated the omission for two declarations.

When status is the only invalid field, request a compact model-authored `{declaration_id,status}` response. Require exactly the requested IDs and canonical status values. Copy only those explicit labels into a deep copy of the existing response; preserve reasons and evidence, then revalidate the full source contract. Do not infer labels from natural-language explanations in program code.

Permit at most one full source repair and one status-only completion per verifier group. A failed status completion is terminal; there is no retry loop. A full source repair that corrects citations but omits status may receive the one compact completion. All calls retain normal quota, billing, usage and private tracing.

Before release: reproduce missing status and source-repair-then-missing-status as failing tests; run the complete numeric suite and independent review; test compact completion against the three real saved responses and verify prior successful results retain their substantive fields. Keep the queue strategy and other rules unchanged. Archive and clear the failed 32-paper cohort, preserve earlier cohort versions, and resume remaining cohorts with cold caches.
