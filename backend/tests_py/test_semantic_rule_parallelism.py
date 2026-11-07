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


def test_abstract_model_omission_is_preserved_in_final_mismatches(monkeypatch):
    lint = module()
    facts = {'chinese_abstract': '中文有额外结论。', 'english_abstract': 'English omits it.'}
    monkeypatch.setattr(lint, 'request_json', lambda _: ({
        'outcome': 'inconsistent', 'summary': '英文摘要遗漏中文摘要中的可复用框架结论。',
        'mismatches': [{'mismatch_type': 'missing_in_english', 'chinese_claim': '中文有额外结论'}],
    }, {'input_tokens': 1, 'output_tokens': 1}))
    monkeypatch.setattr(lint, '_anchors_and_evidence', lambda *_: ([], []))
    result = lint._run_semantic_rule({}, facts, 'bilingual_abstract_consistency_check')
    assert result['outcome'] == 'issues_found'
    assert result['params']['mismatches'][0]['mismatch_type'] == 'missing_in_english'


def test_directional_abstract_audits_promote_exact_source_backed_omissions(monkeypatch):
    lint = module()
    facts = {
        'chinese_abstract': '本文说明循环依赖会约束迭代顺序并限制并行执行。',
        'english_abstract': 'This work improves compilation performance.',
    }
    replies = iter([
        ({'from_chinese': [{
            'source_id': 1,
            'status': 'missing',
            'source_sentence': '本文说明循环依赖会约束迭代顺序并限制并行执行。',
            'target_ids': [],
            'target_sentence': '',
            'reason': '英文摘要未表达该约束。',
        }]}, {'input_tokens': 1, 'output_tokens': 1}),
        ({'from_english': []}, {'input_tokens': 1, 'output_tokens': 1}),
        ({'outcome': 'consistent', 'mismatches': [{
            'mismatch_type': 'missing_in_english',
            'chinese_claim': '循环依赖会约束迭代顺序并限制并行执行',
            'reason': '英文摘要未表达该约束。',
        }]}, {'input_tokens': 1, 'output_tokens': 1}),
    ])
    prompts = []
    def request(messages):
        prompts.append(messages[0]['content'])
        return next(replies)
    monkeypatch.setattr(lint, 'request_json', request)
    monkeypatch.setattr(lint, '_anchors_and_evidence', lambda *_: ([], []))
    result = lint._run_semantic_rule({}, facts, 'bilingual_abstract_consistency_check')
    assert result['outcome'] == 'issues_found'
    assert result['params']['comparison_mode'] == 'sentence_alignment_v4'
    assert len(prompts) == 3
    assert '英文摘要片段' in prompts[1]
    assert '以下为句级初查候选' in prompts[-1]
    assert result['params']['mismatches'][-1]['mismatch_type'] == 'missing_in_english'
    assert '英文摘要缺失' in result['findings'][0]['message']


def test_abstract_sentences_keep_the_whole_causal_sentence():
    lint = module()
    sentence = '循环携带依赖使不同迭代之间存在执行约束，可能增大流水线启动间隔并限制算子并行度。'
    assert lint._abstract_sentences(sentence + '结论成立。') == [sentence, '结论成立。']
    assert lint._causal_result_ids([sentence, '结论成立。']) == [1]
    assert lint._abstract_sentences('At 1.5 GHz, it works. It is reusable.') == [
        'At 1.5 GHz, it works.', 'It is reusable.',
    ]


def test_abstract_summary_is_bounded_and_uses_verified_differences():
    lint = module()
    summary = lint._abstract_mismatch_summary([
        {'mismatch_type': 'missing_in_english', 'reason': '缺少流水线启动间隔。' + '详情' * 100},
        {'mismatch_type': 'conflict', 'reason': '方法不同。'},
    ])
    assert '流水线启动间隔' in summary
    assert '方法不同' in summary
    assert len(summary) < 110


def test_abstract_does_not_report_rejected_or_invented_evidence(monkeypatch):
    lint = module()
    facts = {'chinese_abstract': '我们提出一种编译方法。', 'english_abstract': 'We propose a compilation method.'}
    responses = iter([
        {'from_chinese': [{'source_id': 1, 'status': 'missing'}]},
        {'from_english': []},
        {'outcome': 'consistent', 'mismatches': [
            {'mismatch_type': 'missing_in_english', 'chinese_claim': '不存在的摘录'},
            {'mismatch_type': 'missing_in_english', 'chinese_id': 1,
             'reason': '属于详略差异，不保留。'},
        ]},
    ])
    monkeypatch.setattr(lint, 'request_json', lambda _: (
        next(responses), {'input_tokens': 1, 'output_tokens': 1},
    ))
    result = lint._run_semantic_rule({}, facts, 'bilingual_abstract_consistency_check')
    assert result['outcome'] == 'passed'
    assert result['params']['mismatches'] == []


def test_abstract_requires_final_review_to_accept_initial_candidate(monkeypatch):
    lint = module()
    facts = {'chinese_abstract': '本方法采用决策树。', 'english_abstract': 'Our method uses a neural network.'}
    responses = iter([
        {'from_chinese': [{'source_id': 1, 'target_ids': [1], 'status': 'conflict',
                           'reason': '英文将决策树改为神经网络。'}]},
        {'from_english': []},
        {'outcome': 'consistent', 'mismatches': []},
    ])
    monkeypatch.setattr(lint, 'request_json', lambda _: (
        next(responses), {'input_tokens': 1, 'output_tokens': 1},
    ))
    result = lint._run_semantic_rule({}, facts, 'bilingual_abstract_consistency_check')
    assert result['outcome'] == 'passed'
    assert result['findings'] == []


def test_abstract_report_limits_three_independent_findings(monkeypatch):
    lint = module()
    claims = ['研究对象不同', '实验条件不同', '性能指标不同', '结论适用范围不同']
    facts = {'chinese_abstract': '。'.join(claims) + '。', 'english_abstract': 'English abstract.'}
    responses = iter([
        {'from_chinese': []},
        {'from_english': []},
        {'outcome': 'inconsistent', 'mismatches': [
            {'mismatch_type': 'missing_in_english', 'chinese_claim': claim, 'reason': claim}
            for claim in claims
        ]},
    ])
    monkeypatch.setattr(lint, 'request_json', lambda _: (
        next(responses), {'input_tokens': 1, 'output_tokens': 1},
    ))
    result = lint._run_semantic_rule({}, facts, 'bilingual_abstract_consistency_check')
    assert len(result['params']['mismatches']) == 3
    assert len(result['findings']) == 3
    assert len({row['finding_id'] for row in result['findings']}) == 3
    for finding, claim in zip(result['findings'], claims[:3]):
        assert claim in finding['message']


def test_abstract_issue_highlights_only_its_source_sentence(tmp_path):
    import fitz
    lint = module()
    path = tmp_path / 'abstract.pdf'
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), 'Our method uses a neural network.')
    page.insert_text((72, 150), 'Another unrelated sentence.')
    doc.save(path)
    doc.close()
    quote = 'Our method uses a neural network.'
    anchors, evidence = lint._abstract_issue_anchors(
        {'source_artifacts': [{'kind': 'pdf', 'path': str(path)}]},
        {'english_abstract': quote + ' Another unrelated sentence.',
         'locations': {'english_abstract': {'page_number': 1}}},
        {'english_claim': quote})
    assert len(anchors) == 1
    assert anchors[0]['location']['type'] == 'pdf_bbox'
    assert anchors[0]['location']['bounding_rect']['y2'] < 100
    assert evidence[0]['quote'] == quote
