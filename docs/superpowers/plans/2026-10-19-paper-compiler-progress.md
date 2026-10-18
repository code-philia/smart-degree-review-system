# Execution ledger — plan: docs/superpowers/plans/2026-10-19-paper-compiler-execution.md

2026-10-19: execution resumed; baseline d368deb; no new model costs.
Ruling: retain sole existing checkout per user instructions; no worktree.
Ruling: use bounded independent model/runtime-control implementation in parallel, root owns synthesis and feedback; shared interfaces fixed above.
Pre-flight: model contract is consumed by programs and synthesis; runtime control is consumed by online refinement and Node control.

Ruling: empty-scope test had a mismatched detector emitting bibliography rows while declaring Figure; use an empty detector for empty Figure scope. Retain strict rejection of undeclared diagnostic targets.

2026-10-19: user briefly requested stop; active goal paused and all three agents interrupted. Latest edited objective explicitly resumes TODO execution and asks verified items to be checked off. Runtime default remains freeze=false.
Ruling: frozen-input fingerprint must be verified before dataset-isolation validation on resume so altered sealed manifests are rejected as changes, while fresh manifests still enforce parent separation.

Integrity fixes verified with RED reproductions: direct Python rejects spoofed model manifests and stale capability contracts; merge model type dependencies as whole definitions; restore latest shared model alongside resumed package.

Verified task markers: T03,T05,T06,T08,T09,T10,T11,T12,T13,T14,T15,T17,T18,T21,T22,T24,T25,T27,T28,T29,T30,T32,T34,T69 — compiler-all-current.log 377 passed; API smoke actual-api-repair.json proves initial contract failure→API-generated changed version→actual rerun UNKNOWN with deliberately unavailable facts; control-http-d0cd4zzt/control-http.log verifies admin permissions and persisted default=false. Formal behavioral improvement, benchmark, online and release items remain open.

R31 smoke-v3 loop completed 5 real API rounds with no heldout gain (strict balanced accuracy 0.5→0.5, remaining feedback error1); raw results retained. Inspection found shared synthesis interface incorrectly advertised absent instead of confirmed_absent, so candidates kept treating an explicitly missing carrier field as unknown. Corrected generic observation contract for future runs, no hand-edit to generated detector and no overwrite of smoke scores. Formal study has not started.
Real online API probe achieved verified missed defect→API repair→IR rebuild/rerun→atomic suite promotion, then frozen/resumed checks reused promoted version; evidence online-resource-type-cli-v2.json and online-two-modes-summary.json.

Verified additional markers T16/T23/T31/T47/T59/T61/T62/T66/T67/T68/T70/T71/T72: real-api-smoke-20261019.md and linked raw artifacts, exact API provenance and remaining errors retained. Reopen T18/T22 after discovering weak label-source-role acceptance; all old benchmark candidates pending stronger revalidation, never treated as final300.
