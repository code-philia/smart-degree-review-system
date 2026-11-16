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
    def request(messages, **_local_options):
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
    def request(messages, **_local_options):
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
    def request(messages, **_local_options):
        barrier.wait()
        return {'findings': []}, {'input_tokens': 3, 'output_tokens': 2}
    monkeypatch.setattr(lint, 'request_json', request)
    result = lint.run_typo_rule_from_ir({})
    assert result['execution_status'] == 'completed'
    assert result['model_usage'] == {'input_tokens': 24, 'output_tokens': 16}


def test_typo_capacity_failure_hides_sqlite_detail_but_keeps_it_for_diagnostics(monkeypatch):
    lint = module()
    monkeypatch.setattr(lint, '_body_chunks', lambda *_, **__: [{'model_text': '正文内容。'}])
    monkeypatch.setattr(lint, 'request_json', lambda _, **_local_options: (_ for _ in ()).throw(RuntimeError('database is locked')))
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


def test_abstract_summary_preserves_complete_chinese_and_english_reasons():
    lint = module()
    summary = lint._abstract_mismatch_summary([
        {'mismatch_type': 'missing_in_english', 'reason': '缺少流水线启动间隔。' + '详情' * 100},
        {'mismatch_type': 'conflict', 'reason': '方法不同。'},
        {'mismatch_type': 'missing_in_chinese', 'reason': 'provide a reusable compilation framework for data-intensive applications'},
    ])
    assert '流水线启动间隔' in summary
    assert '方法不同' in summary
    assert '详情' * 100 in summary
    assert 'provide a reusable compilation framework for data-intensive applications' in summary
    assert '…' not in summary


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
        **({'fact_checks':[dict(source_quote='本文提出可复用框架。' if direction=='from_chinese' else 'We propose a reusable framework.',
                            relation='missing' if verdict=='partial_omission' else 'covered',
                            target_quote='' if verdict=='partial_omission' else ('We propose a reusable framework.' if direction=='from_chinese' else '本文提出可复用框架。'))]}
           if verdict not in {'core_omission','contradiction'} else {}),
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


def test_grounded_fact_conflict_survives_omissions_and_invalid_checks(monkeypatch):
    lint = module()
    zh = '研究背景甲。研究背景乙。研究背景丙。该方法使用循环变换。'
    en = 'The method uses branch prediction.'
    alignment = {
        'from_chinese': [
            dict(source_id=i, status='missing', target_ids=[]) for i in range(1, 5)
        ],
        'from_english': [dict(source_id=1, status='matched', target_ids=[4])],
    }
    reviews = [
        dict(candidate_id=f'from_chinese:{i}', verdict='core_omission', target_ids=[],
             reason=f'缺少第{i}项背景。') for i in range(1, 4)
    ]
    reviews.append(dict(candidate_id='from_chinese:4', verdict='partial_omission',
        missing_in='english', target_ids=[1], reason='缺少操作。',
        fact_checks=[
            dict(source_quote='循环变换', relation='contradiction', target_quote='branch prediction'),
            dict(source_quote='编造的片段', relation='missing', target_quote=''),
        ]))
    replies = iter([alignment, {'reviews': reviews}])
    monkeypatch.setattr(lint, 'request_json', lambda _: (next(replies), dict(input_tokens=1, output_tokens=1)))
    result = lint._run_semantic_rule({}, dict(chinese_abstract=zh, english_abstract=en),
                                     'bilingual_abstract_consistency_check')
    assert len(result['findings']) == 3
    assert result['params']['mismatches'][0]['mismatch_type'] == 'conflict'
    assert '循环变换' in result['findings'][0]['message']
    assert 'branch prediction' in result['findings'][0]['message']
    assert result['params']['validation_incomplete'] is True


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


def test_partial_fact_gap_cannot_be_dismissed_by_whole_sentence_equivalence(monkeypatch):
    lint=module()
    facts=dict(chinese_abstract='设备受到带宽限制，并使响应时间增长。',english_abstract='The device is bandwidth constrained.')
    replies=iter([
        {'from_chinese':[dict(source_id=1,status='partial',target_ids=[1])],
         'from_english':[dict(source_id=1,status='matched',target_ids=[1])]},
        {'reviews':[dict(candidate_id='from_chinese:1',verdict='equivalent',target_ids=[1],reason='主题一致。',
            fact_checks=[dict(source_quote='设备受到带宽限制',relation='covered',target_quote='The device is bandwidth constrained.'),
                         dict(source_quote='使响应时间增长',relation='missing',target_quote='')])]}])
    monkeypatch.setattr(lint,'request_json',lambda _:(next(replies),dict(input_tokens=1,output_tokens=1)))
    result=lint._run_semantic_rule({},facts,'bilingual_abstract_consistency_check')
    assert len(result['findings'])==1
    assert result['params']['candidate_reviews'][0]['verdict']=='partial_omission'
    assert result['params']['candidate_reviews'][0]['model_verdict']=='equivalent'
    assert '使响应时间增长' in result['findings'][0]['message']


def test_equivalence_without_fact_evidence_cannot_silently_pass(monkeypatch):
    lint=module()
    replies=iter([
        {'from_chinese':[dict(source_id=1,status='partial',target_ids=[1])],
         'from_english':[dict(source_id=1,status='matched',target_ids=[1])]},
        {'reviews':[dict(candidate_id='from_chinese:1',verdict='equivalent',target_ids=[1],reason='大意相近。')]}])
    monkeypatch.setattr(lint,'request_json',lambda _:(next(replies),dict(input_tokens=1,output_tokens=1)))
    result=lint._run_semantic_rule({},dict(chinese_abstract='设备受限。',english_abstract='Device constrained.'),'bilingual_abstract_consistency_check')
    assert result['execution_status']=='completed'
    assert result['outcome']=='inconclusive'
    assert result['params']['validation_incomplete'] is True
    assert 'fact-level coverage evidence' in result['params']['validation_diagnostics'][0]['reason']


def test_all_covered_facts_suppress_inconsistent_omission_label(monkeypatch):
    lint=module()
    zh='低效通信限制吞吐量。'
    en='Inefficient communication limits throughput.'
    replies=iter([
        {'from_chinese':[dict(source_id=1,status='partial',target_ids=[1])],
         'from_english':[dict(source_id=1,status='matched',target_ids=[1])]},
        {'reviews':[dict(candidate_id='from_chinese:1',verdict='partial_omission',missing_in='english',
            target_ids=[1],reason='措辞不同。',fact_checks=[dict(source_quote=zh,relation='covered',target_quote=en)])]}])
    monkeypatch.setattr(lint,'request_json',lambda _:(next(replies),dict(input_tokens=1,output_tokens=1)))
    result=lint._run_semantic_rule({},dict(chinese_abstract=zh,english_abstract=en),'bilingual_abstract_consistency_check')
    assert result['findings']==[]
    assert result['params']['candidate_reviews'][0]['verdict']=='equivalent'


@pytest.mark.parametrize('include_valid',[True,False])
def test_invalid_fact_evidence_is_isolated_without_losing_verified_findings(monkeypatch,include_valid):
    lint=module()
    checks=[dict(source_quote='模型改写出的不存在片段',relation='missing',target_quote='')]
    if include_valid:
        checks.append(dict(source_quote='使响应时间增长',relation='missing',target_quote=''))
    replies=iter([
        {'from_chinese':[dict(source_id=1,status='partial',target_ids=[1]),dict(source_id=2,status='missing',target_ids=[])],
         'from_english':[dict(source_id=1,status='matched',target_ids=[1])]},
        {'reviews':[
            dict(candidate_id='from_chinese:1',verdict='partial_omission',missing_in='english',target_ids=[1],reason='响应时间事实缺失。',fact_checks=checks),
            dict(candidate_id='from_chinese:2',verdict='core_omission',target_ids=[],reason='第二项缺失。',
                 fact_checks=[dict(source_quote='第二项结论',relation='missing',target_quote='The device is bandwidth constrained.')])]}])
    monkeypatch.setattr(lint,'request_json',lambda _:(next(replies),dict(input_tokens=1,output_tokens=1)))
    result=lint._run_semantic_rule({},dict(chinese_abstract='设备受到带宽限制，并使响应时间增长。第二项结论。',english_abstract='The device is bandwidth constrained.'),'bilingual_abstract_consistency_check')
    assert result['execution_status']=='completed'
    assert result['outcome']==('issues_found' if include_valid else 'inconclusive')
    assert len(result['findings'])==int(include_valid)
    if include_valid:
        assert '使响应时间增长' in result['findings'][0]['message']
    diagnostics=result['params']['validation_diagnostics']
    assert len(diagnostics)==2
    assert any('invalid source evidence' in d['reason'] for d in diagnostics)
    assert any('missing abstract fact cannot have target evidence' in d['reason'] for d in diagnostics)
    assert result['params']['raw_candidate_reviews'][0]['fact_checks'][0]['source_quote']=='模型改写出的不存在片段'



@pytest.mark.parametrize('entrypoint', ['function', 'semantic_run'])
def test_private_typo_worker_limit_keeps_two_requests_in_flight_and_preserves_usage(monkeypatch, entrypoint):
    lint = module()
    for name in ['SJTU_API_KEY','SJTU_API_BASE_URL','SJTU_API_MODEL']: monkeypatch.setenv(name,'controlled')
    monkeypatch.setattr(lint, '_body_chunks', lambda *_, **__: [{'model_text':str(i)} for i in range(8)])
    barrier = threading.Barrier(2, timeout=2)
    lock = threading.Lock()
    active = peak = 0
    def request(messages, **_options):
        nonlocal active, peak
        with lock: active += 1; peak = max(peak,active)
        barrier.wait()
        with lock: active -= 1
        return {'errors':[]},{'input_tokens':3,'output_tokens':2}
    monkeypatch.setattr(lint, 'request_json', request)
    if entrypoint == 'function':
        result = lint.run_typo_rule_from_ir({}, max_workers=2)
    else:
        monkeypatch.setattr(lint, 'build_paper', lambda *_, **__: {})
        result = lint.run(Path('input.pdf'), [lint.TYPO_RULE], typo_workers=2)['rule_runs'][0]
    assert peak == 2
    assert result['execution_status'] == 'completed'
    assert result['params'] == {'chunk_count':8,'chunk_size':1200}
    assert result['model_usage'] == {'input_tokens':24,'output_tokens':16}


@pytest.mark.parametrize('workers', [0,-1,9,True,2.5,'2'])
def test_private_typo_worker_limit_rejects_invalid_values_before_work(monkeypatch, workers):
    lint = module()
    monkeypatch.setattr(lint,'_body_chunks',lambda *_,**__: (_ for _ in ()).throw(AssertionError('must not start work')))
    with pytest.raises(ValueError): lint.run_typo_rule_from_ir({},max_workers=workers)


def test_private_typo_worker_cli_accepts_only_bounded_integers(monkeypatch):
    import sys
    lint = module()
    arguments = ['lint','--pdf','input.pdf','--rule',lint.TYPO_RULE,'--typo-workers']
    monkeypatch.setattr(sys,'argv',arguments+['2'])
    assert lint.parse_args().typo_workers == 2
    for invalid in ['0','9','-1','2.5','invalid']:
        monkeypatch.setattr(sys,'argv',arguments+[invalid])
        with pytest.raises(SystemExit) as error: lint.parse_args()
        assert error.value.code == 2



def _alignment_fixture(zh_count=2, en_count=3):
    facts = {'chinese_abstract': ''.join('中文事实'+str(i)+'。' for i in range(1,zh_count+1)),
             'english_abstract': ' '.join('English fact '+str(i)+'.' for i in range(1,en_count+1))}
    alignment = {'from_chinese':[dict(source_id=i,target_ids=[1],status='matched') for i in range(1,zh_count+1)],
                 'from_english':[dict(source_id=i,target_ids=[1],status='matched') for i in range(1,en_count+1)]}
    return facts, alignment


def test_alignment_contract_repair_receives_both_ranges_and_all_invalid_rows(monkeypatch):
    import copy,json
    lint=module();facts,valid=_alignment_fixture();bad=copy.deepcopy(valid)
    bad['from_chinese'][0]['target_ids']=[0]
    bad['from_chinese'][1]['target_ids']=[4]
    bad['from_english'][0]['target_ids']=[3]
    bad['from_english'][1]['target_ids']=[0]
    original=copy.deepcopy(bad);calls=[]
    def request(messages):
        calls.append(copy.deepcopy(messages))
        return (copy.deepcopy(bad),{'input_tokens':3,'output_tokens':5}) if len(calls)==1 else (copy.deepcopy(valid),{'input_tokens':7,'output_tokens':11})
    monkeypatch.setattr(lint,'request_json',request)
    result=lint._run_aligned_abstract({},facts)
    assert len(calls)==2
    assert calls[1][0]==calls[0][0]
    assert json.loads(calls[1][1]['content'])==original
    diagnostics=json.loads(calls[1][-1]['content'])
    assert diagnostics['index_base']==1
    assert diagnostics['directions']['from_chinese']=={'source_id_range':[1,2],'target_id_range':[1,3]}
    assert diagnostics['directions']['from_english']=={'source_id_range':[1,3],'target_id_range':[1,2]}
    assert {(e['direction'],e['row']) for e in diagnostics['errors']}=={('from_chinese',1),('from_chinese',2),('from_english',1),('from_english',2)}
    assert result['model_usage']=={'input_tokens':10,'output_tokens':16}
    assert result['params']['alignment_repair']['status']=='accepted'
    assert result['params']['alignment']==valid
    assert bad==original


@pytest.mark.parametrize('drop', ['source','direction','duplicate','invalid_again'])
def test_alignment_repair_still_rejects_incomplete_or_invalid_second_output(monkeypatch,drop):
    import copy
    lint=module();facts,valid=_alignment_fixture();bad=copy.deepcopy(valid)
    bad['from_english'][2]['target_ids']=[3]
    second=copy.deepcopy(valid)
    if drop=='source': second['from_chinese'].pop()
    elif drop=='direction': del second['from_english']
    elif drop=='duplicate': second['from_chinese'][1]['source_id']=1
    else: second=copy.deepcopy(bad)
    calls=[]
    def request(messages):
        calls.append(messages)
        return copy.deepcopy(bad if len(calls)==1 else second),{'input_tokens':1,'output_tokens':1}
    monkeypatch.setattr(lint,'request_json',request)
    with pytest.raises(ValueError) as error: lint._run_aligned_abstract({},facts)
    assert len(calls)==2
    assert error.value.alignment_repair['status']=='failed'
    assert 'invalid abstract alignment target' in error.value.alignment_repair['initial_error']


@pytest.mark.parametrize('failure',[TimeoutError('controlled timeout'),RuntimeError('HTTP 429'),ConnectionError('controlled disconnect')])
def test_alignment_transport_failure_does_not_trigger_contract_repair(monkeypatch,failure):
    lint=module();facts,_=_alignment_fixture();calls=[]
    def request(messages): calls.append(messages);raise failure
    monkeypatch.setattr(lint,'request_json',request)
    with pytest.raises(type(failure)):lint._run_aligned_abstract({},facts)
    assert len(calls)==1


def test_alignment_repair_usage_includes_original_repair_and_existing_review(monkeypatch):
    import copy
    lint=module();facts,valid=_alignment_fixture(1,1);bad=copy.deepcopy(valid)
    bad['from_english'][0]['target_ids']=[2]
    valid['from_english'][0].update(status='partial',target_ids=[])
    responses=iter([(bad,{'input_tokens':2,'output_tokens':3}),
                    (valid,{'input_tokens':5,'output_tokens':7}),
                    ({'reviews':[{'candidate_id':'from_english:1','verdict':'uncertain','reason':'证据不足'}]}, {'input_tokens':11,'output_tokens':13})])
    calls=[]
    def request(messages):calls.append(messages);return next(responses)
    monkeypatch.setattr(lint,'request_json',request)
    result=lint._run_aligned_abstract({},facts)
    assert len(calls)==3
    assert result['model_usage']=={'input_tokens':18,'output_tokens':23}
    assert result['params']['candidate_reviews'][0]['verdict']=='uncertain'


def test_alignment_repair_diagnostics_remain_bounded_and_explicitly_report_omissions():
    import copy,json
    lint=module();bad={'from_chinese':[{'source_id':i,'target_ids':[99999],'status':'matched'} for i in range(1,1000)],'from_english':'not an array'}
    original=copy.deepcopy(bad)
    diagnostics=lint._alignment_repair_diagnostics(bad,['甲。'],['A.'],'first failure')
    assert len(json.dumps(diagnostics,ensure_ascii=False,separators=(',',':')).encode('utf-8'))<=6144
    assert diagnostics['omitted_errors']>0 and diagnostics['total_errors']>len(diagnostics['errors'])
    assert diagnostics['directions']['from_english']=={'source_id_range':[1,1],'target_id_range':[1,1]}
    assert bad==original


@pytest.mark.parametrize('zh_count,en_count,source_id,targets',[(40,53,50,[41]),(18,19,19,[19]),(17,18,18,[17,18])])
def test_real_paper_sentence_bounds_require_model_repair_in_reverse_direction(monkeypatch,zh_count,en_count,source_id,targets):
    import copy,json
    lint=module();facts,valid=_alignment_fixture(zh_count,en_count);bad=copy.deepcopy(valid)
    bad['from_english'][source_id-1]['target_ids']=targets
    calls=[]
    def request(messages):
        calls.append(copy.deepcopy(messages))
        return copy.deepcopy(bad if len(calls)==1 else valid),{'input_tokens':1,'output_tokens':1}
    monkeypatch.setattr(lint,'request_json',request)
    result=lint._run_aligned_abstract({},facts)
    assert len(calls)==2 and result['execution_status']=='completed'
    diagnostics=json.loads(calls[1][-1]['content'])
    assert diagnostics['directions']['from_english']['target_id_range']==[1,zh_count]
    assert any(e['direction']=='from_english' and e['row']==source_id for e in diagnostics['errors'])
    assert result['params']['alignment']['from_english'][source_id-1]['target_ids']==[1]


def test_failed_alignment_repair_remains_an_auditable_error_in_final_rule(monkeypatch):
    import copy
    lint=module();facts,valid=_alignment_fixture(1,1);bad=copy.deepcopy(valid);bad['from_english'][0]['target_ids']=[2]
    monkeypatch.setattr(lint,'build_paper',lambda *_,**__: {})
    monkeypatch.setattr(lint,'extract_bilingual_facts',lambda _:facts)
    calls=[]
    def request(messages):calls.append(messages);return copy.deepcopy(bad),{'input_tokens':1,'output_tokens':1}
    monkeypatch.setattr(lint,'request_json',request)
    result=lint.run(Path('input.pdf'),['bilingual_abstract_consistency_check'])
    run=result['rule_runs'][0]
    assert run['execution_status']=='error' and run['outcome']=='inconclusive'
    assert run['params']['alignment_repair']['attempts']==1
    assert run['params']['alignment_repair']['status']=='failed'
    assert len(calls)==2



@pytest.mark.parametrize('kind',['root','direction','row','source_bool','source_zero','status_list','target_bool','matched_null_target'])
def test_alignment_repair_diagnostics_handle_every_validator_shape_failure(monkeypatch,kind):
    import copy
    lint=module();facts,valid=_alignment_fixture(1,1);bad=copy.deepcopy(valid)
    if kind=='root':bad=[]
    elif kind=='direction':bad['from_chinese']=None
    elif kind=='row':bad['from_chinese']=['bad row']
    elif kind=='source_bool':bad['from_chinese'][0]['source_id']=True
    elif kind=='source_zero':bad['from_chinese'][0]['source_id']=0
    elif kind=='status_list':bad['from_chinese'][0]['status']=[]
    elif kind=='target_bool':bad['from_chinese'][0]['target_ids']=[True]
    else:bad['from_chinese'][0]['target_ids']=None
    calls=[]
    def request(messages):calls.append(messages);return copy.deepcopy(bad if len(calls)==1 else valid),{'input_tokens':1,'output_tokens':1}
    monkeypatch.setattr(lint,'request_json',request)
    result=lint._run_aligned_abstract({},facts)
    assert len(calls)==2 and result['execution_status']=='completed'
    assert result['params']['alignment_repair']['status']=='accepted'


def test_alignment_failed_repair_preserves_known_usage_without_an_extra_attempt(monkeypatch):
    import copy
    lint=module();facts,valid=_alignment_fixture(1,1);bad=copy.deepcopy(valid);bad['from_english'][0]['target_ids']=[2]
    calls=[]
    def request(messages):
        calls.append(messages)
        if len(calls)==2:raise TimeoutError('repair transport timed out')
        return copy.deepcopy(bad),{'input_tokens':3,'output_tokens':5}
    monkeypatch.setattr(lint,'request_json',request)
    with pytest.raises(TimeoutError) as error:lint._run_aligned_abstract({},facts)
    assert len(calls)==2
    assert error.value.known_model_usage=={'input_tokens':3,'output_tokens':5}
    assert error.value.alignment_repair['status']=='failed'



@pytest.mark.parametrize('failure', ['transport', 'invalid_review', 'missing_review', 'unhashable_id'])
def test_accepted_alignment_repair_audit_survives_a_later_review_failure(monkeypatch,failure):
    import copy
    lint=module();facts,valid=_alignment_fixture(1,1);bad=copy.deepcopy(valid)
    bad['from_english'][0]['target_ids']=[2]
    valid['from_english'][0].update(status='partial',target_ids=[])
    calls=[]
    def request(messages):
        calls.append(messages)
        if len(calls)==1:return copy.deepcopy(bad),{'input_tokens':2,'output_tokens':3}
        if len(calls)==2:return copy.deepcopy(valid),{'input_tokens':5,'output_tokens':7}
        if failure=='transport':raise TimeoutError('review transport timed out')
        return ({'reviews':None} if failure=='invalid_review' else {'reviews':[{'candidate_id':[]}]} if failure=='unhashable_id' else {'reviews':[]}),{'input_tokens':11,'output_tokens':13}
    monkeypatch.setattr(lint,'request_json',request)
    monkeypatch.setattr(lint,'build_paper',lambda *_,**__: {})
    monkeypatch.setattr(lint,'extract_bilingual_facts',lambda _:facts)
    run=lint.run(Path('input.pdf'),['bilingual_abstract_consistency_check'])['rule_runs'][0]
    assert run['execution_status']=='error' and run['outcome']=='inconclusive'
    assert run['params']['alignment_repair']['status']=='accepted'
    assert run['params']['alignment_repair']['attempts']==1
    assert run['model_usage']==({'input_tokens':7,'output_tokens':10} if failure=='transport' else {'input_tokens':18,'output_tokens':23})
    assert len(calls)==3
