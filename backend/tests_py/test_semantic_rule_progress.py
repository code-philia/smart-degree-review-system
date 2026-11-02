from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
from threading import Event
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_bilingual_semantic_lint as semantic


def test_fast_rule_is_published_while_slow_rule_is_still_running():
    slow, fast = semantic.TYPO_RULE, semantic.NUMERIC_RULE
    release, published = Event(), Event()
    observed = []

    def detect(ir, facts, rule, run_id):
        if rule == slow:
            assert release.wait(5)
        return {'rule_id': rule, 'execution_status': 'completed', 'findings': []}

    def progress(run):
        observed.append(run['rule_id'])
        published.set()

    with patch.object(semantic, 'build_paper', return_value={}) as build, \
            patch.object(semantic, '_run_semantic_rule', side_effect=detect), \
            ThreadPoolExecutor(max_workers=1) as worker:
        future = worker.submit(semantic.run, Path('input.pdf'), [slow, fast], on_rule_complete=progress)
        try:
            assert published.wait(2), 'The fast rule must be visible before the slow one completes'
            assert observed == [fast]
            assert not future.done()
        finally:
            release.set()
        result = future.result(timeout=5)
        assert observed == [fast, slow]
        assert [run['rule_id'] for run in result['rule_runs']] == [slow, fast]
        build.assert_called_once()


def test_one_failed_semantic_rule_does_not_discard_completed_siblings():
    import sqlite3
    ids = [semantic.TYPO_RULE, semantic.NUMERIC_RULE]
    published = []
    def detect(ir, facts, rule, run_id):
        if rule == semantic.TYPO_RULE:
            raise sqlite3.OperationalError('database is locked')
        return {'rule_id': rule, 'execution_status': 'completed', 'outcome': 'passed', 'findings': []}
    with patch.object(semantic, 'build_paper', return_value={}), patch.object(semantic, '_run_semantic_rule', side_effect=detect):
        result = semantic.run(Path('input.pdf'), ids, on_rule_complete=published.append)
    assert [run['rule_id'] for run in result['rule_runs']] == ids
    assert result['rule_runs'][0]['execution_status'] == 'error'
    assert result['rule_runs'][0]['outcome'] == 'inconclusive'
    assert result['rule_runs'][0]['findings'] == []
    assert result['rule_runs'][1]['execution_status'] == 'completed'
    assert result['summary']['error_rule_count'] == 1
    assert len(published) == 2
