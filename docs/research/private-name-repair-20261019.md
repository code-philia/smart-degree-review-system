# Precise generated-program compile feedback

The first four R31 candidates in study-v6 were rejected for the same underscore variable. The generic private-name error did not identify that variable. Replays retain the rejection and now identify its name, line and one-based UTF-8 byte column; the synthesis instructions explicitly describe the existing naming restriction.

The sandbox predicate, AST traversal order, allow/deny rules, detector business logic, labels, metrics and selector are unchanged. No R31 detector was manually patched. This is a manual generic host correction after observed feedback, not an automatic rule improvement.

Validation: 955 selected compiler tests passed, 2170 deselected in 177.50 seconds. All 98 pinned source/test hashes were unchanged across the run. New diagnostic tests were RED before the fix; the targeted suite passed 74 tests. Independent review found no Important issues and verified the normalized worker AST and unchanged remaining synthesis prompt against the parent commit.

Evidence: `/data/results/paper-compiler/framework-20261019/compiler-repair-priority-full-regression-05.json`, `repro-tools/private-name-apply-001/receipt.json`, `repro-tools/private-name-apply-001/independent-review.json` under that same root.

Study-v6 R31 feedback and validation strict balanced accuracy were both zero. These results are retained. The next post-hoc diagnostic must use actual full feedback/validation to establish whether automatic repair improves detection; compiler test success does not establish detector accuracy. No heldout test has been executed for this repair.
