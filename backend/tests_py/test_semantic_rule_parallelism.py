import importlib.util
from pathlib import Path
import threading
import pytest


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


def test_abstract_sentences_keep_the_whole_causal_sentence():
    lint = module()
    sentence = '循环携带依赖使不同迭代之间存在执行约束，可能增大流水线启动间隔并限制算子并行度。'
    assert lint._abstract_sentences(sentence + '结论成立。') == [sentence, '结论成立。']
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


@pytest.mark.parametrize('direction,verdict,expected', [
    ('from_chinese','core_omission',1),
    ('from_english','core_omission',1),
    ('from_chinese','detail_difference',0),
    ('from_chinese','equivalent',0),
    ('from_chinese','uncertain',0),
    ('from_chinese','contradiction',1),
    ('from_chinese','partial_omission',1),
])
def test_sentence_candidates_require_structured_full_review(monkeypatch,direction,verdict,expected):
    lint=module()
    alignment={'from_chinese':[{'source_id':1,'target_ids':[1],'status':'matched'}],
               'from_english':[{'source_id':1,'target_ids':[1],'status':'matched'}]}
    alignment[direction][0].update(status='partial',target_ids=[])
    replies=iter([alignment,{'reviews':[{'candidate_id':direction+':1','verdict':verdict,
        'missing_in':'english',
        'target_ids':[1] if verdict in {'contradiction','partial_omission'} else [],'reason':'独立结论完全缺失。'}]}])
    prompts=[]
    def request(messages):
        prompts.append(messages[0]['content'])
        return next(replies),{'input_tokens':2,'output_tokens':1}
    monkeypatch.setattr(lint,'request_json',request)
    result=lint._run_semantic_rule({}, {'chinese_abstract':'本文提出可复用框架。','english_abstract':'We propose a reusable framework.'},'bilingual_abstract_consistency_check')
    assert len(result['findings'])==expected
    assert len(prompts)==2
    assert all('中文摘要全文' in p and '英文摘要全文' in p for p in prompts)
    assert result['model_usage']=={'input_tokens':4,'output_tokens':2}
    assert result['params']['candidate_reviews']


def test_reordered_and_merged_sentence_mapping_needs_no_review(monkeypatch):
    lint=module()
    calls=[]
    def request(messages):
        calls.append(messages)
        return {'from_chinese':[{'source_id':1,'target_ids':[2],'status':'matched'},
                               {'source_id':2,'target_ids':[1,2],'status':'matched'}],
                'from_english':[{'source_id':1,'target_ids':[2],'status':'matched'},
                                {'source_id':2,'target_ids':[1,2],'status':'matched'}]}, {'input_tokens':1,'output_tokens':1}
    monkeypatch.setattr(lint,'request_json',request)
    result=lint._run_semantic_rule({}, {'chinese_abstract':'提出方法。结果有效。','english_abstract':'Results are effective. We propose a method.'},'bilingual_abstract_consistency_check')
    assert result['outcome']=='passed'
    assert len(calls)==1


def test_missing_sentence_alignment_is_technical_failure(monkeypatch):
    lint=module()
    monkeypatch.setattr(lint,'request_json',lambda _: ({'from_chinese':[], 'from_english':[]},{'input_tokens':1,'output_tokens':1}))
    with pytest.raises(ValueError,match='missing or duplicate'):
        lint._run_semantic_rule({}, {'chinese_abstract':'方法有效。','english_abstract':'It works.'},'bilingual_abstract_consistency_check')


def test_verified_omissions_stay_independent_and_capped(monkeypatch):
    lint=module()
    zh=['贡献甲。','贡献乙。','贡献丙。','贡献丁。']
    alignment={'from_chinese':[dict(source_id=i,status='missing',target_ids=[]) for i in range(1,5)],
               'from_english':[dict(source_id=1,status='matched',target_ids=[1])]}
    reviews={'reviews':[dict(candidate_id=f'from_chinese:{i}',accepted=True,verdict='core_omission',target_ids=[],reason=f'缺少第{i}项独立贡献。') for i in range(1,5)]}
    replies=iter([alignment,reviews])
    monkeypatch.setattr(lint,'request_json',lambda _:(next(replies),{'input_tokens':1,'output_tokens':1}))
    result=lint._run_semantic_rule({},dict(chinese_abstract=''.join(zh),english_abstract='A study.'),'bilingual_abstract_consistency_check')
    assert len(result['findings'])==3
    assert len({f['finding_id'] for f in result['findings']})==3
    assert len(result['params']['candidate_reviews'])==4


def test_review_cannot_invent_candidates(monkeypatch):
    lint=module()
    replies=iter([{'from_chinese':[dict(source_id=1,status='missing',target_ids=[])],
                   'from_english':[dict(source_id=1,status='matched',target_ids=[1])]},
                  {'reviews':[dict(candidate_id='invented',accepted=True,verdict='core_omission')]}])
    monkeypatch.setattr(lint,'request_json',lambda _:(next(replies),{'input_tokens':1,'output_tokens':1}))
    with pytest.raises(ValueError,match='missing or duplicate candidates'):
        lint._run_semantic_rule({},dict(chinese_abstract='本文贡献。',english_abstract='A study.'),'bilingual_abstract_consistency_check')


def test_explanation_explicitly_dismissing_difference_is_rejected():
    lint=module()
    assert lint._dismisses_mismatch('但核心贡献一致，不构成实质差异。')
    assert not lint._dismisses_mismatch('英文未保留独立的贡献结论。')
