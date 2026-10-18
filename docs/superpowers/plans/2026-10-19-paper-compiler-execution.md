# Paper compiler execution plan
Spec: ../specs/2026-10-18-mutant-feedback-framework-design.md
TODO: 2026-10-19-paper-compiler-todo.md
Authorization: latest user objective resumed all TODO implementation on 2026-10-19 and requires checking off each verified item; freeze=false is the runtime default. A brief stop was honored, then superseded by this explicit resume.

## Constraints
One existing checkout; all artifacts under /data; total existing budget CNY 200.
Do not change protected CSV, production state, collaborator work, or existing unrelated changes.
Initial deployment remains subject to the user's result/release gate.

## Interfaces and task order
1. Direct Python packages: programs.build_program(candidate, *, rule_text, basis, model=None),
   run_program(package, ir, analysis), check_programs(ir, analysis, packages),
   save_program(package, path), load_program(path). Independent pure worker, no host access.
   Tests: backend/tests_py/test_paper_compiler_programs.py.
2. Shared model: model_runtime.base_model(), extend_model(model, patch),
   apply_model(ir, model, *, client=None), validate_model(model). Agent owns model_runtime and contracts.
3. Runtime control: RuntimeControl(root).snapshot(), set_freeze(bool), promote(version_id,
   candidate_path, expected_version, expected_generation=None), rollback(version), events().
   Agent owns runtime_control.py. Default unfrozen; CAS and freeze checked on promotion.
4. Synthesis and analysis: one stateless generate/repair request per program round, generic
   analysis_requests and model_patch, traceable packages; built-in evidence adapters reused.
5. Benchmark builder: source IR mutation proposals, separate evidence-grounded label/review
   calls, group split; freeze 100 negative mutants + >=30 controls per rule.
6. Feedback loop: feedback only to repair, validation only for selection, heldout after freeze.
   Max 5 candidate rounds including failures; checkpoints and existing budget.
7. Live smoke, full experiments/ablation, 479x3 scan, frontend/API integration and freeze toggle.
8. Fresh independent code review; tests/build/coverage/cost and release-ready report.

## Verification
Write behavior tests before new modules and observe RED then GREEN.
Run affected compiler Python tests and Node/frontend integration tests/build.
Verify actual API correction and candidate rerun with immutable evidence, labels and split.
Use final independent review and report every remaining failure. No forced zero-error result.
