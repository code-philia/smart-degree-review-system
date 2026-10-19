"""TEST ONLY candidate corpus scans cannot become release validation."""
import json
from pathlib import Path
import subprocess
import sys

import pytest
from test_paper_compiler_corpus import api, setup, Runner


@pytest.mark.parametrize('validation_status', ['not_evaluated', 'failed'])
def test_explicit_candidate_scan_preserves_unvalidated_history_and_unknown_public_decision(tmp_path, validation_status):
    module = api(); inventory, suite, packages, ir = setup(tmp_path, 2)
    validation = suite/'validation.json'
    validation.write_text(json.dumps({'status': validation_status, 'evidence': 'TEST ONLY original record'}))
    original = validation.read_bytes()
    class Reviewed(Runner):
        def __call__(self, *args):
            value = super().__call__(*args)
            value['report']['publication'] = {'public': {'status': 'NO_ALERT', 'findings': []}}
            return value
    runner = Reviewed(packages, ir, tmp_path/'cache'); out = tmp_path/'out'
    report = module.run_corpus(inventory, suite, out, runner=runner, expected_documents=2, candidate_scan=True)
    assert report['status'] == 'candidate'
    assert report['release_readiness'] == 'not_release_ready'
    assert report['complete'] and report['terminal_records'] == 6
    assert report['rule_status_counts']['new-A'] == {'UNKNOWN': 2}
    rows = [json.loads(line) for line in (out/'records.jsonl').read_text().splitlines()]
    assert all(row['status'] == 'UNKNOWN' and row['public_status'] == 'NO_ALERT' for row in rows)
    assert all(row['release_readiness'] == 'not_release_ready' for row in rows)
    result = json.loads((out/'items/paper-0/result.json').read_text())
    assert result['evaluation']['status'] == result['report']['evaluation']['status'] == 'candidate'
    assert module.summarize_run(out, suite=suite, candidate_scan=True) == report
    assert validation.read_bytes() == original
    with pytest.raises(ValueError):
        module.run_corpus(inventory, suite, tmp_path/'default-path', runner=runner)


def test_candidate_mode_is_frozen_even_if_suite_was_already_validated(tmp_path):
    module = api(); inventory, suite, packages, ir = setup(tmp_path, 1)
    runner = Runner(packages, ir, tmp_path/'cache'); out = tmp_path/'out'
    report = module.run_corpus(inventory, suite, out, runner=runner, candidate_scan=True)
    assert report['status'] == 'candidate' and report['release_readiness'] == 'not_release_ready'
    with pytest.raises(ValueError, match='frozen|candidate'):
        module.run_corpus(inventory, suite, out, runner=runner)
    with pytest.raises(ValueError, match='candidate'):
        module.summarize_run(out, suite=suite)
    assert len(runner.calls) == 1


def test_candidate_flag_does_not_bypass_runtime_artifact_hashes_or_inventory_size(tmp_path):
    module = api(); inventory, suite, packages, ir = setup(tmp_path, 1)
    runner = Runner(packages, ir, tmp_path/'cache')
    with pytest.raises(ValueError, match='document count'):
        module.run_corpus(inventory, suite, tmp_path/'wrong-count', runner=runner, expected_documents=479, candidate_scan=True)
    (suite/'validation.json').write_text('{"status":"not_evaluated"}')
    (suite/'runtime/frontend.py').write_text('# TEST ONLY corrupted runtime artifact')
    with pytest.raises(ValueError, match='runtime artifact hash'):
        module.run_corpus(inventory, suite, tmp_path/'tampered', runner=runner, candidate_scan=True)
    assert runner.calls == []


def test_candidate_execution_errors_remain_errors_and_have_no_invented_public_review(tmp_path):
    module = api(); inventory, suite, packages, ir = setup(tmp_path, 1)
    (suite/'validation.json').write_text('{"status":"not_evaluated"}')
    class Failed(Runner):
        def __call__(self, *args): raise RuntimeError('TEST ONLY execution failure')
    report = module.run_corpus(inventory, suite, tmp_path/'out', runner=Failed(packages, ir, tmp_path/'cache'), candidate_scan=True)
    assert report['status'] == 'candidate' and report['documents_failed'] == 1
    assert report['rule_status_counts']['new-A'] == {'ERROR': 1}
    rows = [json.loads(line) for line in (tmp_path/'out/records.jsonl').read_text().splitlines()]
    assert all(row['status'] == 'ERROR' and row['error_type'] == 'RuntimeError' for row in rows)
    assert all(row['public_status'] is None and row['release_readiness'] == 'not_release_ready' for row in rows)


def test_explicit_candidate_cli_runs_offline_without_validation_or_config_and_keeps_gate_default(tmp_path):
    inventory, suite, packages, ir = setup(tmp_path, 1)
    (suite/'validation.json').write_text('{"status":"not_evaluated"}')
    before = (suite/'validation.json').read_bytes()
    script = Path(__file__).resolve().parents[1]/'scripts/paper_compiler_corpus.py'
    args = [sys.executable, str(script), 'run', '--inventory', str(inventory), '--suite', str(suite),
        '--out', str(tmp_path/'out'), '--offline', '--expected-documents', '1', '--evidence-snapshot', 'TEST-ONLY-fixed',
        '--config', str(tmp_path/'missing.env')]
    blocked = subprocess.run(args, capture_output=True, text=True)
    assert blocked.returncode == 1 and not (tmp_path/'out').exists()
    allowed = subprocess.run(args + ['--candidate-scan'], capture_output=True, text=True)
    assert allowed.returncode == 0, allowed.stdout + allowed.stderr
    report = json.loads(allowed.stdout)
    assert report['status'] == 'candidate' and report['release_readiness'] == 'not_release_ready'
    assert report['terminal_records'] == 3
    assert (suite/'validation.json').read_bytes() == before
