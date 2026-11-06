import importlib.util
from pathlib import Path
import threading


def module():
    path = Path(__file__).parents[1] / 'scripts/run_bilingual_semantic_lint.py'
    spec = importlib.util.spec_from_file_location('parallel_semantic_test', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_independent_semantic_rules_overlap_and_preserve_selected_order(monkeypatch):
    lint = module()
    barrier = threading.Barrier(4, timeout=1)
    parsed = []
    ir = {'nodes': []}
    monkeypatch.setattr(lint, 'build_paper', lambda *a, **k: parsed.append(1) or ir)
    monkeypatch.setattr(lint, 'extract_bilingual_facts', lambda _: {})
    monkeypatch.setattr(lint, 'prompt_for', lambda rule, facts: rule)
    def local(rule):
        barrier.wait()
        return {'rule_id': rule, 'execution_status': 'completed', 'findings': []}
    monkeypatch.setattr(lint, 'run_typo_rule_from_ir', lambda _: local(lint.TYPO_RULE))
    monkeypatch.setattr(lint, 'run_numeric_consistency_rule', lambda *a, **k: local(lint.NUMERIC_RULE))
    def request(messages):
        barrier.wait()
        return {'outcome': 'consistent'}, {'input_tokens': 1, 'output_tokens': 1}
    monkeypatch.setattr(lint, 'request_json', request)
    ids = [lint.TYPO_RULE, *sorted(lint.BILINGUAL_RULES), lint.NUMERIC_RULE]
    result = lint.run(Path('unused.pdf'), ids)
    assert [row['rule_id'] for row in result['rule_runs']] == ids
    assert result['summary']['completed_rule_count'] == 4
    assert parsed == [1]


def test_typo_chunks_overlap_without_changing_usage_totals(monkeypatch):
    lint = module()
    barrier = threading.Barrier(4, timeout=1)
    chunks = [{'model_text': f'piece{i}'} for i in range(4)]
    monkeypatch.setattr(lint, '_body_chunks', lambda *_, **__: chunks)
    def request(messages):
        barrier.wait()
        return {'findings': []}, {'input_tokens': 3, 'output_tokens': 2}
    monkeypatch.setattr(lint, 'request_json', request)
    result = lint.run_typo_rule_from_ir({})
    assert result['execution_status'] == 'completed'
    assert result['params']['chunk_count'] == 4
    assert result['model_usage'] == {'input_tokens': 12, 'output_tokens': 8}


def test_eight_typo_chunks_can_run_together(monkeypatch):
    lint = module()
    for name, value in [('SJTU_API_KEY', 'test-campus-key'), ('SJTU_API_BASE_URL', 'https://models.sjtu.edu.cn/api/v1'), ('SJTU_API_MODEL', 'deepseek-chat')]:
        monkeypatch.setenv(name, value)
    barrier = threading.Barrier(8, timeout=2)
    chunks = [{'model_text': f'piece{i}'} for i in range(8)]
    monkeypatch.setattr(lint, '_body_chunks', lambda *_, **__: chunks)
    def request(messages):
        barrier.wait()
        return {'findings': []}, {'input_tokens': 3, 'output_tokens': 2}
    monkeypatch.setattr(lint, 'request_json', request)
    result = lint.run_typo_rule_from_ir({})
    assert result['execution_status'] == 'completed'
    assert result['model_usage'] == {'input_tokens': 24, 'output_tokens': 16}


def test_typo_capacity_failure_hides_sqlite_detail_but_keeps_it_for_diagnostics(monkeypatch):
    lint = module()
    monkeypatch.setattr(lint, '_body_chunks', lambda *_, **__: [{'model_text': '正文内容。'}])
    monkeypatch.setattr(lint, 'request_json', lambda _: (_ for _ in ()).throw(RuntimeError('database is locked')))
    result = lint.run_typo_rule_from_ir({})
    assert result['execution_status'] == 'error'
    assert '当前系统使用人数较多' in result['message']
    assert 'database is locked' not in result['message']
    assert result['params']['technical_failure'] == 'database is locked'


def test_non_typo_semantic_failure_uses_retry_copy(monkeypatch):
    lint = module()
    monkeypatch.setattr(lint, 'build_paper', lambda *_, **__: {'nodes': []})
    monkeypatch.setattr(lint, 'extract_bilingual_facts', lambda _: {})
    monkeypatch.setattr(lint, '_run_semantic_rule', lambda *_: (_ for _ in ()).throw(RuntimeError('HTTP 429')))
    result = lint.run(Path('unused.pdf'), ['bilingual_abstract_consistency_check'])
    run = result['rule_runs'][0]
    assert run['execution_status'] == 'error'
    assert run['message'] == lint.API_CAPACITY_MESSAGE
    assert run['params']['technical_failure'] == 'HTTP 429'


def test_abstract_prompt_requires_bidirectional_coverage_for_omitted_information():
    lint = module()
    prompt = lint.prompt_for('bilingual_abstract_consistency_check', {
        'chinese_abstract': '中文摘要中的方法与结论。',
        'english_abstract': 'The method and conclusion in the English abstract.',
    })
    assert '必须双向覆盖' in prompt
    assert '信息缺失型不一致' in prompt
    assert 'missing_in_english' in prompt


def test_abstract_omission_returned_by_model_becomes_a_finding(monkeypatch):
    lint = module()
    facts = {'chinese_abstract': '中文有额外结论。', 'english_abstract': 'English omits it.'}
    monkeypatch.setattr(lint, 'request_json', lambda _: ({
        'outcome': 'inconsistent', 'summary': '英文摘要遗漏中文摘要中的可复用框架结论。',
        'mismatches': [{'mismatch_type': 'missing_in_english'}],
    }, {'input_tokens': 1, 'output_tokens': 1}))
    monkeypatch.setattr(lint, '_anchors_and_evidence', lambda *_: ([], []))
    result = lint._run_semantic_rule({}, facts, 'bilingual_abstract_consistency_check')
    assert result['outcome'] == 'issues_found'
    assert len(result['findings']) == 1
