"""Corpus runs bind frozen source bytes to a suite and never hide missing coverage."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from paper_compiler.budget import BudgetExceeded
from paper_compiler.pipeline import detect, save_suite
from paper_compiler.programs import build_program
from test_paper_compiler_compiler import fixture
from test_paper_compiler_programs import candidate


def api():
    path = Path(__file__).resolve().parents[1]/'scripts'/'paper_compiler_corpus.py'
    assert path.is_file(), 'corpus protocol is not implemented'
    spec = importlib.util.spec_from_file_location('corpus_test_entry', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def setup(tmp_path, count=3):
    ir, _ = fixture(tmp_path)
    items = []
    for index in range(count):
        path = tmp_path/f'paper-{index}.json'; path.write_text(json.dumps(ir))
        items.append({'id': f'paper-{index}', 'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    inventory = tmp_path/'inventory.json'; inventory.write_text(json.dumps({'inventory': {'items': items}}))
    packages = [build_program({**candidate(), 'rule_id': rule}, rule_text='The entry must be Hello',
                             basis=[{'id': 'test', 'text': 'The entry must be Hello'}]) for rule in ('new-A', 'new-B', 'new-C')]
    suite = tmp_path/'suite'; save_suite(packages, suite, validated=True, validation={'status': 'passed', 'method': 'test'})
    return inventory, suite, packages, ir


class Runner:
    fingerprint = {'semantic_model': 'fake-no-network', 'evidence_snapshot': 'snapshot-fixed', 'offline': True}
    def __init__(self, packages, ir, cache):
        self.packages, self.ir, self.cache = packages, ir, cache
        self.calls = []
    def __call__(self, path, work):
        self.calls.append(path.name)
        ir, analysis, report = detect(copy.deepcopy(self.ir), self.packages, client=None, gateway=None, cache_dir=self.cache)
        return {'ir': ir, 'analysis': analysis, 'report': report}


def test_inventory_verifies_original_bytes_without_modifying_frozen_input(tmp_path):
    inventory, suite, packages, ir = setup(tmp_path)
    before = inventory.read_bytes()
    value = api().inspect_inventory(inventory, rule_ids=['new-A', 'new-B', 'new-C'], verify_hashes=True)
    assert value['documents'] == 3 and value['expected_terminal_records'] == 9
    assert value['distinct_content'] == 1 and value['hashes_verified'] == 3
    assert inventory.read_bytes() == before
    Path(json.loads(before)['inventory']['items'][1]['path']).write_text('changed')
    with pytest.raises(ValueError, match='hash'): api().inspect_inventory(inventory, verify_hashes=True)


def test_suite_scan_generates_every_paper_rule_terminal_and_reuses_completed_work(tmp_path):
    inventory, suite, packages, ir = setup(tmp_path, 2)
    runner = Runner(packages, ir, tmp_path/'cache'); root = tmp_path/'out'
    report = api().run_corpus(inventory, suite, root, runner=runner, expected_documents=2)
    assert report['complete'] is True and report['terminal_records'] == report['expected_terminal_records'] == 6
    assert report['documents_completed'] == 2 and len(runner.calls) == 2
    assert report['rule_status_counts']['new-A'] == {'UNKNOWN': 2}
    assert report['objects']['new-A']['targets'] == 2 and report['objects']['new-A']['reported'] == 2
    rows = [json.loads(line) for line in (root/'records.jsonl').read_text().splitlines()]
    assert len(rows) == 6 and all(row['input_sha256'] for row in rows)
    assert {row['program_version'] for row in rows} == {p['manifest']['version_id'] for p in packages}
    assert all(row['suite_version'] and row['result_sha256'] for row in rows)
    class NoCall(Runner):
        def __call__(self, *args): raise AssertionError('completed records must be reused')
    assert api().run_corpus(inventory, suite, root, runner=NoCall(packages, ir, tmp_path/'cache')) == report


def test_resume_recovers_a_committed_result_when_terminal_publication_was_interrupted(tmp_path, monkeypatch):
    module = api(); inventory, suite, packages, ir = setup(tmp_path, 1)
    runner = Runner(packages, ir, tmp_path/'cache'); root = tmp_path/'out'
    original = module._write_terminal
    monkeypatch.setattr(module, '_write_terminal', lambda *a, **kw: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt): module.run_corpus(inventory, suite, root, runner=runner)
    monkeypatch.setattr(module, '_write_terminal', original)
    result = module.run_corpus(inventory, suite, root, runner=runner)
    assert result['terminal_records'] == 3 and result['documents_completed'] == 1
    assert len(runner.calls) == 1


def test_uncommitted_interrupted_attempt_is_explicit_error_without_repaying(tmp_path):
    module = api(); inventory, suite, packages, ir = setup(tmp_path, 2)
    class Interrupted(Runner):
        def __call__(self, path, work): self.calls.append(path.name); raise KeyboardInterrupt()
    runner = Interrupted(packages, ir, tmp_path/'cache'); root = tmp_path/'out'
    with pytest.raises(KeyboardInterrupt): module.run_corpus(inventory, suite, root, runner=runner)
    resumed = Runner(packages, ir, tmp_path/'cache')
    result = module.run_corpus(inventory, suite, root, runner=resumed)
    assert len(resumed.calls) == 1 and result['terminal_records'] == 6
    assert result['rule_status_counts']['new-A'] == {'ERROR': 1, 'UNKNOWN': 1}
    rows = [json.loads(line) for line in (root/'records.jsonl').read_text().splitlines()]
    assert rows[0]['error_type'] == 'InterruptedAttempt' and rows[0]['attempted'] is True


def test_budget_exhaustion_records_unattempted_errors_and_stops_all_further_calls(tmp_path):
    module = api(); inventory, suite, packages, ir = setup(tmp_path)
    class Exhausted(Runner):
        def __call__(self, path, work): self.calls.append(path.name); raise BudgetExceeded('private-test-sentinel')
    runner = Exhausted(packages, ir, tmp_path/'cache'); root = tmp_path/'out'
    result = module.run_corpus(inventory, suite, root, runner=runner)
    assert len(runner.calls) == 1 and result['terminal_records'] == 9 and result['complete']
    assert result['budget_stopped'] and result['rule_status_counts']['new-A'] == {'ERROR': 3}
    rows = [json.loads(line) for line in (root/'records.jsonl').read_text().splitlines()]
    assert rows[0]['attempted'] and rows[0]['error_type'] == 'BudgetExceeded'
    assert rows[-1]['attempted'] is False and rows[-1]['error_type'] == 'BudgetNotRun'
    assert all('private-test-sentinel' not in p.read_text() for p in root.rglob('*.json'))
    assert module.run_corpus(inventory, suite, root, runner=runner) == result and len(runner.calls) == 1


def test_runner_failure_is_a_terminal_error_and_does_not_erase_other_papers(tmp_path):
    inventory, suite, packages, ir = setup(tmp_path, 2)
    class Once(Runner):
        def __call__(self, path, work):
            if not self.calls: self.calls.append(path.name); raise RuntimeError('must not publish credentials')
            return super().__call__(path, work)
    result = api().run_corpus(inventory, suite, tmp_path/'out', runner=Once(packages, ir, tmp_path/'cache'))
    assert result['terminal_records'] == 6 and result['documents_failed'] == 1
    assert result['rule_status_counts']['new-A'] == {'ERROR': 1, 'UNKNOWN': 1}
    assert result['objects']['new-A']['unmeasured_documents'] == 1


@pytest.mark.parametrize('change', ['input', 'runner', 'result', 'suite'])
def test_frozen_run_rejects_changed_inputs_configuration_and_artifacts(tmp_path, change):
    module = api(); inventory, suite, packages, ir = setup(tmp_path, 1)
    root = tmp_path/'out'; runner = Runner(packages, ir, tmp_path/'cache')
    module.run_corpus(inventory, suite, root, runner=runner)
    if change == 'input': Path(json.loads(inventory.read_text())['inventory']['items'][0]['path']).write_text('changed')
    if change == 'runner': runner.fingerprint = {**runner.fingerprint, 'semantic_model': 'changed'}
    if change == 'result': (root/'items'/'paper-0'/'result.json').write_text('{}')
    if change == 'suite': (suite/'manifest.json').write_text('{}')
    with pytest.raises(ValueError): module.run_corpus(inventory, suite, root, runner=runner)
    assert len(runner.calls) == 1


def test_unknown_and_missing_object_evidence_are_not_counted_as_conclusive(tmp_path):
    inventory, suite, packages, ir = setup(tmp_path, 1)
    class Unknown(Runner):
        def __call__(self, *args):
            result = super().__call__(*args)
            for rule in result['report']['rules']:
                rule.update(status='UNKNOWN', results=[], counts={})
            result['ir']['coverage']['bibliography'] = {'status': 'partial', 'reason': 'unreadable boundary'}
            from paper_compiler.contracts import ir_hash
            result['analysis']['paper_ir_sha256'] = ir_hash(result['ir'])
            result['report'].update(paper_ir_sha256=ir_hash(result['ir']), coverage=result['ir']['coverage'])
            return result
    result = api().run_corpus(inventory, suite, tmp_path/'out', runner=Unknown(packages, ir, tmp_path/'cache'))
    assert result['rule_status_counts']['new-A'] == {'UNKNOWN': 1}
    assert result['objects']['new-A']['missing'] == 1 and result['objects']['new-A']['conclusive'] == 0
    assert result['scope_coverage']['bibliography'] == {'partial': 1}
    assert result['evidence']['full_text_objects'] == 0 and result['accuracy_metrics'] is None


def test_evidence_distinguishes_abstract_truncated_and_complete_fulltext(tmp_path):
    inventory, suite, packages, ir = setup(tmp_path, 1)
    class Content(Runner):
        def __call__(self, *args):
            result = super().__call__(*args)
            evidence = [{'id': 'abstract', 'status': 'ok', 'coverage': 'abstract_only', 'level': 'abstract', 'text': 'Abstract'},
                        {'id': 'full', 'status': 'ok', 'coverage': 'full_text', 'level': 'full_text', 'text': 'Complete'},
                        {'id': 'truncated', 'status': 'ok', 'coverage': 'truncated_full_text', 'level': 'full_text', 'text': 'Partial'}]
            result['report']['evidence'] = result['analysis']['evidence'] = evidence
            result['report']['rules'][0]['results'][0]['evidence_ids'].append('abstract')
            result['report']['rules'][1]['results'][0]['evidence_ids'].append('full')
            result['report']['rules'][2]['results'][0]['evidence_ids'].append('truncated')
            return result
    result = api().run_corpus(inventory, suite, tmp_path/'out', runner=Content(packages, ir, tmp_path/'cache'))
    assert result['evidence']['content_coverage'] == {'abstract_only': 1, 'full_text': 1, 'truncated_full_text': 1}
    assert result['objects']['new-A']['full_text'] == 0 and result['objects']['new-A']['abstract_only'] == 1
    assert result['objects']['new-B']['full_text'] == 1 and result['objects']['new-C']['truncated_full_text'] == 1


def test_unvalidated_suite_and_wrong_inventory_size_fail_before_execution(tmp_path):
    module = api(); inventory, suite, packages, ir = setup(tmp_path, 1)
    runner = Runner(packages, ir, tmp_path/'cache')
    with pytest.raises(ValueError): module.run_corpus(inventory, suite, tmp_path/'a', runner=runner, expected_documents=479)
    (suite/'validation.json').write_text('{"status":"not_evaluated"}')
    with pytest.raises(ValueError): module.run_corpus(inventory, suite, tmp_path/'b', runner=runner)
    assert runner.calls == []


def test_preflight_workload_range_is_explicitly_conditional_not_an_accuracy_or_cost_claim(tmp_path):
    inventory, suite, packages, ir = setup(tmp_path, 2)
    paths = [Path(json.loads(inventory.read_text())['inventory']['items'][0]['path'])]
    result = api().estimate_workload(inventory, suite=suite, ir_paths=paths)
    assert result['observed_ir_documents'] == 1 and result['corpus_documents'] == 2
    assert result['paid_call_range']['minimum'] == 0 and result['currency_estimate_cny'] is None
    assert result['sample_is_representative'] is False
    assert 'not a guaranteed upper bound' in result['limitations']


def test_cost_report_uses_the_same_ledger_deltas_and_resume_adds_no_charge(tmp_path):
    inventory, suite, packages, ir = setup(tmp_path, 2)
    class Metered(Runner):
        def meter(self):
            amount = len(self.calls)
            return {'spent_cny': str(amount), 'committed_cny': str(amount), 'requests': amount,
                    'prompt_tokens': amount*100, 'completion_tokens': amount*30, 'uncertain_requests': 0}
    runner = Metered(packages, ir, tmp_path/'cache'); root = tmp_path/'out'
    result = api().run_corpus(inventory, suite, root, runner=runner)
    assert result['cost']['measured'] and result['cost']['delta']['spent_cny'] == '2'
    assert result['cost']['delta']['requests'] == '2'
    assert api().run_corpus(inventory, suite, root, runner=runner) == result and len(runner.calls) == 2


def test_locked_output_rejects_concurrent_owner_before_any_runner_call(tmp_path):
    import fcntl
    inventory, suite, packages, ir = setup(tmp_path, 1)
    root = tmp_path/'out'; root.mkdir()
    runner = Runner(packages, ir, tmp_path/'cache')
    with (root/'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match='already running'): api().run_corpus(inventory, suite, root, runner=runner)
    assert runner.calls == []


def test_unversioned_or_missing_rule_output_becomes_explicit_error_for_entire_document(tmp_path):
    inventory, suite, packages, ir = setup(tmp_path, 1)
    class Missing(Runner):
        def __call__(self, *args):
            result = super().__call__(*args); result['report']['rules'].pop(); return result
    result = api().run_corpus(inventory, suite, tmp_path/'out', runner=Missing(packages, ir, tmp_path/'cache'))
    assert result['terminal_records'] == 3 and result['documents_failed'] == 1
    assert all(counts == {'ERROR': 1} for counts in result['rule_status_counts'].values())


def test_cli_offline_suite_run_and_read_only_inspection_need_no_model_configuration(tmp_path):
    import subprocess, sys
    inventory, suite, packages, ir = setup(tmp_path, 1)
    script = Path(__file__).resolve().parents[1]/'scripts'/'paper_compiler_corpus.py'
    p = subprocess.run([sys.executable, str(script), 'run', '--inventory', str(inventory), '--suite', str(suite),
                        '--out', str(tmp_path/'out'), '--offline', '--expected-documents', '1',
                        '--evidence-snapshot', 'test-fixed', '--config', str(tmp_path/'missing-private.env')], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout+p.stderr
    assert json.loads(p.stdout)['terminal_records'] == 3
    saved = json.loads((tmp_path/'out'/'items'/'paper-0'/'result.json').read_text())
    assert set(saved['stage_costs']) == {'frontend', 'pipeline'}
    p = subprocess.run([sys.executable, str(script), 'inspect', '--inventory', str(inventory), '--rule', 'new-A',
                        '--out', str(tmp_path/'inventory-report.json'), '--verify-hashes'], capture_output=True, text=True)
    assert p.returncode == 0 and json.loads(p.stdout)['hashes_verified'] == 1


def test_linked_spans_inherit_content_evidence_but_truncation_never_becomes_fulltext(tmp_path):
    module = api()
    evidence = {'span': {'content_id': 'body'}, 'body': {'status': 'ok', 'coverage': 'truncated_full_text'}}
    assert module._evidence_levels(['span'], evidence) == {'truncated_full_text'}
    evidence['body'].update(coverage='full_text')
    assert module._evidence_levels(['span'], evidence) == {'full_text'}
    evidence['body'].update(status='unavailable')
    assert module._evidence_levels(['span'], evidence) == set()


def test_read_only_summarization_verifies_saved_results_without_a_model_client(tmp_path):
    module = api(); inventory, suite, packages, ir = setup(tmp_path, 2)
    root = tmp_path/'out'; result = module.run_corpus(inventory, suite, root, runner=Runner(packages, ir, tmp_path/'cache'))
    assert result['records_sha256'] == hashlib.sha256((root/'records.jsonl').read_bytes()).hexdigest()
    assert module.summarize_run(root, suite=suite) == result
    (root/'items'/'paper-1'/'checkpoint.json').unlink()
    partial = module.summarize_run(root, suite=suite)
    assert partial['complete'] is False and partial['terminal_records'] == 3 and partial['documents_pending'] == 1
    (root/'items'/'paper-0'/'result.json').write_text('{}')
    with pytest.raises(ValueError, match='hash'): module.summarize_run(root, suite=suite)


def test_paid_entry_refuses_a_new_ledger_before_model_configuration_or_calls(tmp_path):
    module = api(); inventory, suite, packages, ir = setup(tmp_path, 1)
    ledger = tmp_path/'new-ledger.sqlite3'
    args = module.parser().parse_args(['run', '--inventory', str(inventory), '--suite', str(suite),
        '--out', str(tmp_path/'out'), '--evidence-snapshot', 'fixed', '--expected-documents', '1',
        '--ledger', str(ledger), '--config', str(tmp_path/'missing-private.env')])
    with pytest.raises(ValueError, match='existing.*ledger'): module.execute(args)
    assert not ledger.exists()


def test_declared_final_rule_set_cannot_silently_scan_a_different_suite(tmp_path):
    module = api(); inventory, suite, packages, ir = setup(tmp_path, 1)
    args = module.parser().parse_args(['run', '--inventory', str(inventory), '--suite', str(suite),
        '--out', str(tmp_path/'out'), '--offline', '--evidence-snapshot', 'fixed', '--expected-documents', '1', '--rule', 'other'])
    with pytest.raises(ValueError, match='rule'): module.execute(args)
    assert not (tmp_path/'out'/'items').exists()
