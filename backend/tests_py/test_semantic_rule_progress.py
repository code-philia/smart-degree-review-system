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
