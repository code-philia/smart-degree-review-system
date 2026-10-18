"""Read-only reporting consumes existing study records; all fixtures are test-only."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
from test_paper_compiler_study import benchmark, Model, runner_for
from paper_compiler.study import run_study


def api():
    path = Path(__file__).resolve().parents[1]/'scripts'/'paper_compiler_study_report.py'
    assert path.is_file(), 'study reporting entry point is missing'
    spec = importlib.util.spec_from_file_location('study_report_test', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def study(tmp_path, *, invalid=False, budget_after=None):
    tasks, manifest, splits = benchmark(tmp_path, ('alpha', 'beta'))
    root = tmp_path/'study'; model = Model(invalid_initial=invalid, budget_after=budget_after)
    result = run_study(tasks, manifest, client=model, output_dir=root,
                       runner=runner_for(root, splits, []), max_rounds=2)
    return root, result


def test_real_study_format_produces_test_only_tables_and_matplotlib_figures(tmp_path):
    source, original = study(tmp_path); out = tmp_path/'test-only-report'
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    result = api().build_report(source, out, test_only=True)
    assert result['status'] == 'completed' and result['heldout_available'] and result['test_only']
    assert result['integrity']['status'] == 'verified'
    rows = {(r['condition'], r['rule_id']): r for r in result['comparison']}
    assert len(rows) == 6 and rows['initial', 'alpha']['strict_balanced_accuracy'] == .5
    assert rows['joint', 'alpha']['strict_balanced_accuracy'] == 1
    assert rows['program_only', 'alpha']['valid_cases'] == 2 and rows['joint', 'alpha']['negative_cases'] == 1
    assert result['manual_effort']['status'] == 'not_recorded' and result['manual_effort']['interventions'] is None
    assert result['scope']['observed_rules'] == 2 and result['cost']['spent_cny_delta'] is None
    for name in ['results.json', 'comparison.csv', 'rounds.csv', 'groups.csv', 'examples.json', 'report.md',
                 'figures/heldout.png', 'figures/heldout.svg', 'figures/rounds.png', 'figures/rounds.svg']:
        assert (out/name).stat().st_size > 0
    assert (out/'figures/heldout.png').read_bytes().startswith(b'\x89PNG')
    assert result['plots']['renderer'] == 'matplotlib'
    assert 'TEST ONLY' in (out/'report.md').read_text()
    assert before == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}


def test_failed_initial_keeps_observed_strict_failure_score_and_no_semantic_metrics(tmp_path):
    source, original = study(tmp_path, invalid=True)
    result = api().build_report(source, tmp_path/'test-only-report', test_only=True)
    initial = [r for r in result['comparison'] if r['condition'] == 'initial']
    assert all(r['status'] == 'ERROR' and r['strict_balanced_accuracy'] == 0 and r['errors'] == 2 and r['semantic_detection_metrics'] is None for r in initial)
    assert all(r['reported_metrics']['strict_balanced_accuracy'] == 0 and 'compile failed' in r['execution_note'] for r in initial)
    assert all(r['strict_balanced_accuracy'] == 1 for r in result['comparison'] if r['condition'] == 'joint')
    assert any('compile_or_contract' in r.get('failure_types', []) for r in result['rounds'])
    assert any('compile_or_contract' in e['failure'].get('failure_types', []) for e in json.loads((tmp_path/'test-only-report'/'examples.json').read_text()))


def test_incomplete_study_never_draws_heldout_and_does_not_read_oracle_files(tmp_path, monkeypatch):
    source, original = study(tmp_path, budget_after=2)
    assert original['status'] == 'incomplete'
    original_read = Path.read_text
    def guarded(path, *args, **kwargs):
        assert 'oracle' not in path.name, 'report must not read sealed answers'
        return original_read(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', guarded)
    out = tmp_path/'test-only-report'; result = api().build_report(source, out, test_only=True)
    assert result['status'] == 'incomplete' and not result['heldout_available']
    assert not (out/'figures/heldout.png').exists()
    assert all(r['strict_balanced_accuracy'] is None and r['unknown'] is None and r['errors'] is None and r['valid_cases'] is None for r in result['comparison'])
    assert original['stop_reason'] in (out/'report.md').read_text()


def test_artifact_tampering_becomes_explicit_integrity_error_without_scores(tmp_path):
    source, _ = study(tmp_path)
    target = next((source/'conditions').glob('joint/task-*/round-000/round.json'))
    target.write_text('{}')
    out = tmp_path/'test-only-report'; result = api().build_report(source, out, test_only=True)
    assert result['status'] == 'ERROR' and result['integrity']['status'] == 'failed'
    assert not result['heldout_available'] and not (out/'figures/heldout.svg').exists()
    assert all(r['strict_balanced_accuracy'] is None for r in result['comparison'])


def test_missing_selection_freeze_cannot_present_formal_heldout_comparison(tmp_path):
    source, _ = study(tmp_path); (source/'selection-frozen.json').unlink()
    result = api().build_report(source, tmp_path/'test-only-report', test_only=True)
    assert not result['heldout_available'] and result['status'] == 'ERROR'


def test_unknown_error_and_zero_denominators_are_retained_as_distinct_states():
    records = [{'id': 'a', 'expected': 'VIOLATION', 'before': 'PASS', 'after': 'UNKNOWN', 'correct': False},
               {'id': 'b', 'expected': 'PASS', 'before': 'ERROR', 'after': 'PASS', 'correct': False}]
    result = api().metric_row(records)
    assert result['unknown'] == result['errors'] == 1 and result['valid_cases'] == 2
    assert result['conclusive_cases'] == 0 and result['strict_balanced_accuracy'] == 0
    empty = api().metric_row([])
    assert empty['strict_balanced_accuracy'] is None and empty['mutant_detection_rate'] is None


def test_manual_effort_is_only_an_explicit_self_report_and_actual_model_changes_are_separate(tmp_path):
    source, _ = study(tmp_path)
    audit = tmp_path/'human-audit.json'
    audit.write_text(json.dumps({'events': [{'id': 'fix1', 'kind': 'manual_intervention', 'rule_id': 'alpha', 'description': 'Reviewed data boundaries.'},
                                          {'id': 'code1', 'kind': 'task_specific_code', 'rule_id': 'alpha', 'description': 'Declared special adapter.', 'lines_added': 4}]}))
    result = api().build_report(source, tmp_path/'test-only-report', test_only=True, interventions=audit)
    assert result['manual_effort']['status'] == 'self_reported_unverified'
    assert result['manual_effort']['interventions'] == 1 and result['manual_effort']['task_specific_lines_added'] == 4
    assert result['model_changes']['selected_condition_changes'] == 0
    assert any(row['axis'] == 'context_origin' and row['group'] == 'constructed' for row in result['groups'])
    assert any(row['axis'] == 'evidence_domain' and row['group'] == 'open' for row in result['groups'])


def test_cli_needs_no_model_config_and_records_the_actual_plotting_version(tmp_path):
    source, _ = study(tmp_path); script = Path(__file__).resolve().parents[1]/'scripts'/'paper_compiler_study_report.py'
    out = tmp_path/'test-only-report'
    process = subprocess.run([sys.executable, str(script), '--study-root', str(source), '--out', str(out), '--test-only'], capture_output=True, text=True)
    assert process.returncode == 0, process.stdout+process.stderr
    result = json.loads((out/'results.json').read_text())
    assert result['plots']['matplotlib_version'] and result['provenance']['source_sha256']['summary.json']


def test_completed_flag_without_actual_heldout_records_is_not_formal_evidence(tmp_path):
    source, _ = study(tmp_path)
    path = source/'summary.json'; value = json.loads(path.read_text())
    value['conditions']['joint']['rules']['alpha']['final_test']['records'] = []
    path.write_text(json.dumps(value))
    index_path = source/'artifact-index.json'; index = json.loads(index_path.read_text())
    index['files']['summary.json'] = hashlib.sha256(path.read_bytes()).hexdigest(); index_path.write_text(json.dumps(index))
    result = api().build_report(source, tmp_path/'test-only-report', test_only=True)
    assert result['status'] == 'ERROR' and not result['heldout_available']
    assert not (tmp_path/'test-only-report'/'figures/heldout.png').exists()


def test_actual_accepted_semantic_model_change_is_counted_from_saved_models(tmp_path):
    from paper_compiler.model_runtime import base_model, extend_model
    tasks, manifest, splits = benchmark(tmp_path, ('alpha',)); source = tmp_path/'study'
    initial = extend_model(base_model(), {'node_types': {'Method': {'base_kind': 'Section', 'description': 'Initial method semantics.', 'attrs': {}}}})
    class Changes(Model):
        def complete_json(self, task, instructions, data, max_tokens):
            value = super().complete_json(task, instructions, data, max_tokens)
            if data['feedback'] and data['allow_model_refinement']:
                value['model_patch'] = {'node_types': {'Method': {'description': 'Revised grounded method semantics.'}}}
            return value
    run_study(tasks, manifest, client=Changes(), output_dir=source, runner=runner_for(source, splits, []), max_rounds=2, initial_model=initial)
    result = api().build_report(source, tmp_path/'test-only-report', test_only=True)
    assert result['model_changes']['selected_condition_changes'] == 1
    assert result['model_changes']['condition_changed'] == {'joint': True, 'program_only': False}
    assert any(r['model_changed'] is True and r['changed_node_types'] == ['Method'] for r in result['rounds'])


def test_cost_and_missing_manual_line_counts_are_not_fabricated(tmp_path):
    module = api()
    value = module._cost({'budget_before': {'spent_cny': '4.10', 'requests': 8},
                          'budget': {'spent_cny': '5.30', 'requests': 11}, 'elapsed_seconds': 23.4})
    assert value['spent_cny_delta'] == '1.20' and value['api_requests_delta'] == '3' and value['elapsed_seconds'] == 23.4
    audit = tmp_path/'audit.json'; audit.write_text(json.dumps({'events': [{'id': 'a', 'kind': 'task_specific_code'}]}))
    assert module._manual(audit)['task_specific_lines_added'] is None



def resource_fixture():
    return {'available': True, 'elapsed_seconds': 3.75,
            'budget_before': {'spent_cny': '1.00', 'requests': 5},
            'budget_after': {'spent_cny': '1.25', 'requests': 7},
            'spent_cny_delta': '0.25', 'committed_cny_delta': '-0.10', 'requests_delta': 2,
            'prompt_tokens_delta': 120, 'completion_tokens_delta': 40,
            'accounting_scope': 'shared_ledger_interval'}


def round_fixture(tmp_path, usage=None, *, sidecar=False):
    module = api(); folder = tmp_path/'conditions'/'joint'/('task-'+module._digest('alpha')[:12])/'round-000'
    folder.mkdir(parents=True)
    record = {'round': 0, 'status': 'evaluated'}
    if sidecar:
        (folder/'resource-usage.json').write_text(json.dumps({'schema_version': 'resource-test/1.0', 'status': 'budget_exhausted', 'started_at': '2026-10-19T00:00:00+00:00', 'resource_usage': usage}))
        rounds = []
    else:
        if usage is not None: record['resource_usage'] = usage
        (folder/'round.json').write_text(json.dumps(record)); rounds = [record]
    summary = {'conditions': {'joint': {'rules': {'alpha': {'rounds': rounds}}}}}
    return module, summary


def test_round_resource_schema_exports_observed_intervals_to_json_and_csv(tmp_path):
    import csv
    usage = resource_fixture(); module, summary = round_fixture(tmp_path, usage)
    rows, _, _ = module._round_data(module.Reader(tmp_path), summary, None); row = rows[0]
    assert row['resource_usage'] == usage and row['resource_usage_available'] is True
    assert row['elapsed_seconds'] == 3.75 and row['api_cost_cny'] == '0.25'
    for key in ['spent_cny_delta', 'committed_cny_delta', 'requests_delta', 'prompt_tokens_delta', 'completion_tokens_delta', 'budget_before', 'budget_after', 'accounting_scope']:
        assert row[key] == usage[key]
    module._csv(tmp_path/'rounds.csv', rows)
    with (tmp_path/'rounds.csv').open(encoding='utf-8-sig') as stream: saved = next(csv.DictReader(stream))
    assert saved['spent_cny_delta'] == '0.25' and saved['requests_delta'] == '2'
    assert json.loads(saved['budget_before']) == usage['budget_before']
    zero = {**usage, 'elapsed_seconds': 0.0, 'spent_cny_delta': '0.000000', 'requests_delta': 0}
    other_module, other_summary = round_fixture(tmp_path/'observed-zero', zero)
    observed = other_module._round_data(other_module.Reader(tmp_path/'observed-zero'), other_summary, None)[0][0]
    assert observed['elapsed_seconds'] == 0.0 and observed['api_cost_cny'] == '0.000000' and observed['requests_delta'] == 0


@pytest.mark.parametrize('usage', [None, {'available': False, 'elapsed_seconds': 2.5, 'budget_before': None, 'budget_after': None,
    'spent_cny_delta': None, 'committed_cny_delta': None, 'requests_delta': None, 'prompt_tokens_delta': None,
    'completion_tokens_delta': None, 'accounting_scope': 'shared_ledger_interval'}])
def test_legacy_or_no_ledger_resource_values_stay_null(tmp_path, usage):
    module, summary = round_fixture(tmp_path, usage)
    row = module._round_data(module.Reader(tmp_path), summary, None)[0][0]
    assert row['elapsed_seconds'] == (2.5 if usage else None)
    assert row['api_cost_cny'] is None and row['requests_delta'] is None and row['budget_before'] is None
    assert row['resource_usage_available'] == (False if usage else None)


def test_budget_interrupted_resource_sidecar_is_not_a_successful_evaluated_round(tmp_path):
    module, summary = round_fixture(tmp_path, resource_fixture(), sidecar=True)
    rows = module._round_data(module.Reader(tmp_path), summary, None)[0]
    assert len(rows) == 1 and rows[0]['status'] == 'resource_only_incomplete_round'
    assert rows[0]['elapsed_seconds'] == 3.75 and rows[0]['spent_cny_delta'] == '0.25'
    assert rows[0]['resource_usage_status'] == 'budget_exhausted'
    assert rows[0]['resource_usage_started_at'] == '2026-10-19T00:00:00+00:00'
    assert rows[0].get('validation_strict_balanced_accuracy') is None and rows[0]['selected'] is False


def test_cumulative_study_resource_record_precedes_legacy_resume_summary_values():
    usage = resource_fixture(); usage['elapsed_seconds'] = 18.5
    row = api()._cost({'resource_usage': usage, 'elapsed_seconds': 1.0,
                      'budget_before': {'spent_cny': '10.0'}, 'budget': {'spent_cny': '99.0'}})
    assert row['elapsed_seconds'] == 18.5 and row['spent_cny_delta'] == '0.25'
    assert row['api_requests_delta'] == 2 and row['accounting_scope'] == 'shared_ledger_interval'


def test_initial_preparation_charge_is_exported_as_a_separate_stage(tmp_path):
    source, original = study(tmp_path)
    # This extra measurement fixture is not part of the original frozen study index.
    preparation = {'status': 'prepared', 'formal_evaluation_pending': True,
        'budget_before': {'spent_cny': '10.000000', 'requests': 1},
        'budget': {'spent_cny': '10.013494', 'requests': 2}}
    (source/'initial-preparation.json').write_text(json.dumps(preparation))
    result = api().build_report(source, tmp_path/'test-only-report', test_only=True)
    assert result['cost']['spent_cny_delta'] is None
    stage = result['stage_resources']['initial_preparation']
    assert stage['spent_cny_delta'] == '0.013494' and stage['api_requests_delta'] == '1'
    assert stage['included_in_study_interval_total'] is False
