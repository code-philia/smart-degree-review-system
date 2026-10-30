import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import numeric_consistency as n


def fixture():
    nodes = []
    def add(nid, kind, text='', children=None, page=1, attrs=None):
        nodes.append({'id': nid, 'kind': kind, 'text': text, 'children': children or [], 'attrs': attrs or {},
                      'provenance': [{'page_index': page-1, 'node_text_start': 0, 'node_text_end': len(text), 'bbox': [10, 10, 150, 30]}] if text else []})
    add('body', 'Body', children=['ch', 'other'])
    add('toc', 'ToCEntry', '第三章 融合模型 5')
    add('ch', 'Section', children=['h', 'intro', 'exp'], attrs={'level': 1})
    add('h', 'Heading', '第三章 融合模型', page=5)
    add('intro', 'Paragraph', '本文提出融合模型。', page=5)
    add('exp', 'Section', children=['eh', 'table', 'data'], attrs={'level': 2})
    add('eh', 'Heading', '3.4 实验结果', page=8)
    add('table', 'Table', children=['caption'])
    add('caption', 'Caption', '表3-2 数据集A Accuracy 本文模型 基线', page=8)
    add('data', 'Paragraph', '数据集A 本文模型 Accuracy 89.3% 基线84.0%。', page=8)
    add('other', 'Section', children=['oh', 'op'], attrs={'level': 1})
    add('oh', 'Heading', '第四章 无关方法', page=10)
    add('op', 'Paragraph', '无关实验 准确率92.5%', page=10)
    ir = {'nodes': nodes, 'layout': {'pages': [{'page_index': p-1, 'width': 600, 'height': 800} for p in [1, 5, 8, 10]]}}
    facts = {'chinese_abstract': '本文提出融合模型，在数据集A准确率92.5%，提升5.3个百分点。'}
    data = {'preconditions': [{'id': key, 'passed': True, 'reason': '通过', 'suggestion': ''} for key in sorted(n.CONDITIONS)],
            'contributions': [{'id': 'c1', 'text': '本文提出融合模型'}],
            'declarations': [{'id': 'd1', 'contribution_id': 'c1', 'text': '在数据集A准确率92.5%', 'number': '92.5', 'metric': '准确率', 'unit': '%', 'comparison': 'absolute', 'condition': '数据集A'}],
            'mappings': [{'declaration_id': 'd1', 'chapter_id': 'ch', 'experiment_section_ids': ['exp'], 'evidence': [{'source_node_id': 'intro', 'quote': '本文提出融合模型', 'page': 5}]}]}
    return ir, facts, data


def test_section_body_and_table_preserve_provenance():
    ir, facts, data = fixture()
    model = n.source_model(ir)
    assert {b['source_node_id'] for b in n.section_blocks(model, 'ch')} >= {'intro', 'data', 'caption'}
    assert model['sections']['exp']['parent_id'] == 'ch'
    assert next(b for b in model['blocks'] if b['source_node_id'] == 'data')['page'] == 8
    assert 'table_cells_not_reliably_reconstructed' in model['limitations']
    assert n.validate_structure(data, n.structure_context(facts, model), model)


@pytest.mark.parametrize('change', ['false_string', 'missing_condition', 'duplicate_condition', 'unknown_condition', 'missing_mapping', 'bad_parent', 'bad_source', 'bad_contribution', 'duplicate_declaration', 'condition_object', 'nullable_comparison'])
def test_structure_contract_rejects_invalid(change):
    ir, facts, data = fixture()
    if change == 'false_string': data['preconditions'][0]['passed'] = 'false'
    if change == 'missing_condition': data['preconditions'].pop()
    if change == 'duplicate_condition': data['preconditions'].append(data['preconditions'][0])
    if change == 'unknown_condition': data['preconditions'][0]['id'] = 'unknown'
    if change == 'missing_mapping': data['mappings'] = []
    if change == 'bad_parent': data['mappings'][0]['experiment_section_ids'] = ['other']
    if change == 'bad_source': data['mappings'][0]['evidence'][0]['quote'] = '幻觉来源'
    if change == 'bad_contribution': data['declarations'][0]['contribution_id'] = 'unknown'
    if change == 'duplicate_declaration': data['declarations'].append(data['declarations'][0])
    if change == 'condition_object': data['preconditions'] = {row['id']: row for row in data['preconditions']}
    if change == 'nullable_comparison': data['declarations'][0]['comparison'] = None
    model = n.source_model(ir)
    with pytest.raises(n.ContractError): n.validate_structure(data, n.structure_context(facts, model), model)


def test_gate_and_failure_preserve_first_stage():
    ir, facts, data = fixture()
    data['preconditions'][0]['passed'] = False
    calls = []
    def request(messages):
        calls.append(messages)
        return data, {'input_tokens': 1, 'output_tokens': 1}
    r = n.run_numeric(ir, facts, request)
    assert len(calls) == 1 and r['outcome'] == 'inconclusive' and r['execution_status'] == 'completed'
    data['preconditions'][0]['passed'] = True
    def timeout(messages):
        if calls:
            calls.pop()
            return data, {}
        raise TimeoutError('read timeout')
    r = n.run_numeric(ir, facts, timeout)
    assert r['execution_status'] == 'error' and r['params']['declarations'] == data['declarations']


def valid_output(candidate):
    return {'results': [{'declaration_id': 'd1', 'status': 'inconsistent', 'reason': '数值冲突', 'suggestion': '请核对原始实验数据',
                         'evidence': [{'candidate_id': candidate['candidate_id'], 'quote': candidate['text'], 'page': candidate['page']}]}]}


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'unknown', 'status', 'quote', 'page', 'candidate', 'reason'])
def test_verifier_contract(change):
    ir, facts, data = fixture()
    candidates, _ = n.retrieve_candidates(data['declarations'], data['mappings'], n.source_model(ir))
    payload = valid_output(candidates[0])
    row = payload['results'][0]
    if change == 'missing': payload['results'] = []
    if change == 'duplicate': payload['results'].append(copy.deepcopy(row))
    if change == 'unknown': row['declaration_id'] = 'unknown'
    if change == 'status': row['status'] = 'PASS'
    if change == 'quote': row['evidence'][0]['quote'] = '不存在的原文'
    if change == 'page': row['evidence'][0]['page'] = 9999
    if change == 'candidate': row['evidence'][0]['candidate_id'] = 'fake'
    if change == 'reason': row['reason'] = ''
    results, errors = n.validated_results(payload, data['declarations'], candidates)
    assert errors and len(results) == 1 and results[0]['status'] == 'inconclusive'
    assert not results[0]['evidence']


def test_all_declarations_required_and_valid_evidence_can_locate():
    ir, facts, data = fixture()
    candidates, _ = n.retrieve_candidates(data['declarations'], data['mappings'], n.source_model(ir))
    result, errors = n.validated_results(valid_output(candidates[0]), data['declarations'], candidates)
    assert not errors and result[0]['status'] == 'inconsistent'
    assert n.location(result[0]['evidence'][0], n.source_model(ir))['type'] == 'pdf_bbox'
    declarations = data['declarations'] + [{**data['declarations'][0], 'id': 'd2'}]
    result, errors = n.validated_results(valid_output(candidates[0]), declarations, candidates)
    assert len(result) == 2 and result[1]['status'] == 'inconclusive'


def test_context_never_cuts_json_or_block():
    ir, facts, _ = fixture()
    model = n.source_model(ir)
    kept, coverage = n.pack_blocks(model['blocks'], 200)
    assert coverage['dropped']
    assert json_roundtrip(kept) == kept
    assert all(b['text'] in [s['text'] for s in model['blocks']] for b in kept)


def json_roundtrip(obj):
    import json
    return json.loads(json.dumps(obj))


@pytest.mark.parametrize('metric,number', [('准确率', '92.5'), ('Accuracy', '89.3'), ('提升', '5.3'), ('f1', '999')])
def test_retrieval_conflict_aliases_and_fallback(metric, number):
    ir, facts, data = fixture()
    data['declarations'][0].update(metric=metric, number=number)
    if metric == 'f1':
        data['declarations'][0]['condition'] = '未知数据集'
    model = n.source_model(ir)
    candidates, diagnostics = n.retrieve_candidates(data['declarations'], data['mappings'], model)
    assert 'data' in {c['source_node_id'] for c in candidates}
    assert 'op' not in {c['source_node_id'] for c in candidates}
    assert {'caption', 'data'} <= {c['source_node_id'] for c in candidates}
    assert all(c['page'] == 8 for c in candidates)
    if metric == 'f1':
        assert diagnostics[0]['fallback'] is not None
    else:
        assert any(s['kind'] == 'metric' for c in candidates for s in c['matched_signals']) or metric == '提升'


def test_numeric_match_never_outweighs_metric_condition():
    d = {'metric': '准确率', 'condition': '数据集A', 'number': '92.5'}
    wrong = {'text': '另一个数据集92.5%', 'block_type': 'Paragraph'}
    right = {'text': '数据集A Accuracy89.3%', 'block_type': 'Paragraph'}
    assert n.retrieval_signals(d, right)[0] > n.retrieval_signals(d, wrong)[0]


def test_empty_scope_and_recall_metric():
    ir, facts, data = fixture()
    model = n.source_model(ir)
    candidates, diagnostics = n.retrieve_candidates(data['declarations'], data['mappings'], model)
    assert n.evidence_recall_at_k(candidates, {'d1': ['data']}, 6)['d1'] == 1
    model['blocks'] = []
    candidates, diagnostics = n.retrieve_candidates(data['declarations'], data['mappings'], model)
    assert not candidates and diagnostics[0]['fallback'] == 'empty_experiment_scope'


def test_trace_replay_and_redaction(tmp_path, monkeypatch):
    import json
    from numeric_run_trace import NumericRunTrace, load_replay
    from replay_numeric_run import replay
    monkeypatch.setenv('SJTU_API_KEY', 'unit-test-secret-credential')
    ir, facts, structure = fixture()
    trace = NumericRunTrace(ir, 'task-123', root=tmp_path)
    responses = []
    def transport(messages, observer=None):
        observer('raw_response', {'body': 'unit-test-secret-credential', 'Authorization': 'discard'})
        if not responses:
            responses.append(True)
            return structure, {'input_tokens': 1, 'output_tokens': 2}
        candidates, _ = n.retrieve_candidates(structure['declarations'], structure['mappings'], n.source_model(ir))
        return valid_output(candidates[0]), {'input_tokens': 3, 'output_tokens': 4}
    result = n.run_numeric(ir, facts, lambda messages: trace.call(transport, messages), trace)
    trace.finish(result)
    manifest, artifacts = load_replay(trace.path)
    assert manifest['task_id'] == 'task-123' and len(artifacts['call_input']) == 2
    assert all('unit-test-secret-credential' not in p.read_text() for p in trace.path.glob('*.json'))
    repeated = replay(trace.path)
    assert repeated['outcome'] == result['outcome']
    assert repeated['params']['numeric_results'] == result['params']['numeric_results']
    target = trace.path / manifest['artifacts'][0]['file']
    target.write_text('{}')
    with pytest.raises(ValueError, match='hash mismatch'): load_replay(trace.path)


def test_multiple_experiments_and_dataset_ranking():
    ir, facts, data = fixture()
    extra = [
        {'id': 'exp2', 'kind': 'Section', 'children': ['eh2', 'data2'], 'attrs': {'level': 2}},
        {'id': 'eh2', 'kind': 'Heading', 'text': '3.5 性能评估', 'children': [], 'provenance': []},
        {'id': 'data2', 'kind': 'Paragraph', 'text': '数据集B 本文模型Accuracy92.5% 基线90%', 'children': [],
         'provenance': [{'page_index': 8, 'node_text_start': 0, 'node_text_end': len('数据集B 本文模型Accuracy92.5% 基线90%'), 'bbox': [1, 1, 2, 2]}]},
    ]
    next(x for x in ir['nodes'] if x['id'] == 'ch')['children'].append('exp2')
    ir['nodes'].extend(extra)
    data['mappings'][0]['experiment_section_ids'].append('exp2')
    candidates, diagnostics = n.retrieve_candidates(data['declarations'], data['mappings'], n.source_model(ir))
    assert {'data', 'data2'} <= {c['source_node_id'] for c in candidates}
    by_node = {c['source_node_id']: c for c in candidates}
    assert by_node['data']['retrieval_score'] > by_node['data2']['retrieval_score']
    assert diagnostics[0]['scope'] == ['exp', 'exp2']


def test_real_pdf_frontend_supplies_paragraphs_and_table_text(tmp_path):
    import fitz
    from paper_compiler.frontend import build_paper
    pdf = tmp_path / 'source.pdf'
    document = fitz.open()
    page = document.new_page()
    page.insert_text((60, 80), 'Abstract', fontsize=16)
    page.insert_text((60, 110), 'We propose Fusion. Accuracy on Dataset A is 92.5%.', fontsize=12)
    page.insert_text((60, 145), 'Keywords: Fusion; Accuracy', fontsize=12)
    page.insert_text((60, 200), 'Contents', fontsize=16)
    page.insert_text((60, 230), 'Chapter 3 Fusion model ... 2', fontsize=12)
    page = document.new_page()
    page.insert_text((60, 80), 'Chapter 3 Fusion model', fontsize=16)
    page.insert_text((60, 110), 'Our proposed Fusion method uses dynamic weights.', fontsize=12)
    page.insert_text((60, 160), '3.1 Experiments', fontsize=16)
    page.insert_text((60, 200), 'Table 3-1 Accuracy on Dataset A', fontsize=12)
    page.insert_text((60, 230), 'Method       Dataset       Accuracy', fontsize=12)
    page.insert_text((60, 255), 'Fusion       A             89.3%', fontsize=12)
    document.save(pdf)
    document.close()
    model = n.source_model(build_paper(pdf, include_citations=False))
    source = '\n'.join(b['text'] for b in model['blocks'])
    assert '89.3%' in source and 'Method' in source and 'Table 3-1' in source
    chapter = next(s for s in model['sections'].values() if s['title'] == 'Chapter 3 Fusion model')
    assert 'dynamic weights' in '\n'.join(b['text'] for b in n.section_blocks(model, chapter['section_id']))


@pytest.mark.parametrize('failure', ['malformed', 'timeout', 'empty_results'])
def test_execution_errors_never_become_paper_violations(failure):
    ir, facts, structure = fixture()
    calls = []
    def request(messages):
        calls.append(messages)
        if len(calls) == 1:
            return structure, {}
        if failure == 'timeout': raise TimeoutError('slow request')
        return ({'results': None} if failure == 'malformed' else {'results': []}), {}
    result = n.run_numeric(ir, facts, request)
    assert result['execution_status'] == 'error'
    assert result['outcome'] == 'inconclusive' and not result['findings']
    assert result['params']['declarations'] == structure['declarations']
    assert result['params']['numeric_results'][0]['status'] == 'inconclusive'


@pytest.mark.parametrize('finish_reason', ['stop', 'length'])
def test_transport_observer_records_raw_response_without_network(monkeypatch, finish_reason):
    import json
    import run_bilingual_semantic_lint as transport
    monkeypatch.setenv('SJTU_API_KEY', 'transport-unit-test-secret')
    monkeypatch.setenv('SJTU_API_BASE_URL', 'https://example.invalid/api/v1')
    monkeypatch.setenv('SJTU_API_MODEL', 'test-model')
    monkeypatch.setenv('SJTU_API_MIN_INTERVAL_SECONDS', '0')
    response = {'choices': [{'finish_reason': finish_reason, 'message': {'content': '{"test":true}'}}], 'usage': {'prompt_tokens': 2, 'completion_tokens': 1}}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size): return json.dumps(response).encode()
    class Opener:
        def open(self, *args, **kwargs): return Response()
    monkeypatch.setattr(transport.urllib.request, 'build_opener', lambda *args: Opener())
    events = []
    if finish_reason == 'length':
        with pytest.raises(ValueError, match='达到上限'):
            transport.request_json([{'role': 'user', 'content': 'test'}], observer=lambda key, value: events.append((key, value)))
    else:
        payload, usage = transport.request_json([{'role': 'user', 'content': 'test'}], observer=lambda key, value: events.append((key, value)))
        assert payload == {'test': True} and usage['input_tokens'] == 2
    assert [key for key, _ in events] == ['request_config', 'request_attempt', 'raw_response']
    assert 'transport-unit-test-secret' not in json.dumps(events)


def test_whitespace_cannot_invent_a_numeric_or_english_token():
    assert n.normalized('准确率 92.5 %') == n.normalized('准确率92.5%')
    assert n.normalized('8\n9') != n.normalized('89')
    assert n.normalized('Model A') != n.normalized('ModelA')
    assert not n.grounded_quote('9%', '准确率89%')
    assert not n.grounded_quote('准确率92', '准确率92.5%')
    assert n.grounded_quote('准确率92.5%', '准确率 92.5 %')


def test_abstract_location_preserves_english_wrap_boundaries():
    ir = {'layout': {'pages': [{'page_index': 0, 'width': 600, 'height': 800,
        'lines': [{'text': 'The model achieves', 'bbox': [10, 10, 150, 30]},
                  {'text': '92.5% accuracy.', 'bbox': [10, 35, 150, 55]}]}]}}
    anchors = n.abstract_anchors(ir, 'The model achieves 92.5% accuracy.', 'a1')
    assert len(anchors) == 1
    assert anchors[0]['location']['page_number'] == 1
    assert len(anchors[0]['location']['rects']) == 2


def test_abstract_location_does_not_join_adjacent_numeric_cells():
    ir = {'layout': {'pages': [{'page_index': 0, 'lines': [
        {'text': '8', 'bbox': [10, 10, 20, 30]}, {'text': '9', 'bbox': [30, 10, 40, 30]}]}]}}
    assert not n.abstract_anchors(ir, '89', 'a1')


def test_method_section_cannot_be_admitted_as_experiment_from_only_toc():
    ir, facts, data = fixture()
    next(x for x in ir['nodes'] if x['id'] == 'eh')['text'] = '3.1 Method implementation'
    # Keep source offsets valid after replacing the title.
    next(x for x in ir['nodes'] if x['id'] == 'eh')['provenance'][0]['node_text_end'] = len('3.1 Method implementation')
    for node in ir['nodes']:
        if node['id'] in {'caption', 'data'}:
            node['text'] = 'The architecture combines two dynamic feature streams.'
            node['provenance'][0]['node_text_end'] = len(node['text'])
    model = n.source_model(ir)
    with pytest.raises(n.ContractError, match='classification lacks supporting'):
        n.validate_structure(data, n.structure_context(facts, model), model)


def test_nonstandard_title_can_be_supported_by_experimental_body():
    ir, facts, data = fixture()
    heading = next(x for x in ir['nodes'] if x['id'] == 'eh')
    heading['text'] = '3.4 Model behavior'
    heading['provenance'][0]['node_text_end'] = len(heading['text'])
    paragraph = next(x for x in ir['nodes'] if x['id'] == 'data')
    paragraph['text'] = 'We evaluate the proposed model on Dataset A.'
    paragraph['provenance'][0]['node_text_end'] = len(paragraph['text'])
    model = n.source_model(ir)
    assert n.experimental_support(model, 'exp')
    assert n.validate_structure(data, n.structure_context(facts, model), model)


@pytest.mark.parametrize('off_by_one', [False, True])
def test_pdf_navigation_recovers_split_hierarchy_and_spaced_toc(monkeypatch, off_by_one):
    import pymupdf
    from numeric_navigation import attach_navigation
    nodes = [{'id': 'body', 'kind': 'Body', 'children': ['ch'], 'attrs': {}}]
    pages = [{'page_index': i, 'width': 600, 'height': 800, 'lines': []} for i in range(3)]
    def line(nid, text, page, y, size=12, kind='Paragraph', parent='ch'):
        lid = f'p{page-1}-{nid}'
        box = [10, y, 300, y+size]
        pages[page-1]['lines'].append({'id': lid, 'text': text, 'bbox': box, 'font_size': size})
        nodes.append({'id': nid, 'kind': kind, 'text': text, 'attrs': {}, 'children': [],
                      'provenance': [{'line_id': lid, 'page_index': page-1, 'bbox': box, 'node_text_start': 0, 'node_text_end': len(text)}]})
        if parent:
            next(n for n in nodes if n['id'] == parent)['children'].append(nid)
    nodes.append({'id': 'ch', 'kind': 'Section', 'text': None, 'children': [], 'attrs': {'level': 1}})
    line('toc1', '目', 1, 80, 16, parent=None)
    line('toc2', '录', 1, 80, 16, parent=None)
    line('toc3', '第三章 融合模型........2', 1, 120, parent=None)
    line('header', '第三章 融合模型', 2, 40, 10)
    line('chapter_number', '第三章', 2, 100, 18, 'Heading')
    line('chapter_title', '融合模型', 2, 100, 18)
    line('intro', '模型采用动态权重。', 2, 150)
    line('section_number', '3.1', 3, 100, 14)
    line('section_title', '实验评估', 3, 100, 14)
    line('result', '实验准确率89.3%。', 3, 150, kind='Heading')
    class Doc:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get_toc(self, **kwargs):
            return [[1, '3 融合模型', 2, {'kind': 4, 'to': pymupdf.Point(0, 700)}],
                    [2, '3.1 实验评估', 2 if off_by_one else 3, {'kind': 4, 'to': pymupdf.Point(0, 700)}]]
    monkeypatch.setattr(pymupdf, 'open', lambda *args: Doc())
    ir = {'nodes': nodes, 'layout': {'pages': pages}}
    attach_navigation('unused.pdf', ir)
    model = n.source_model(ir)
    assert len(model['sections']) == 2 and model['toc']
    experiment = next(s for s in model['sections'].values() if s['level'] == 2)
    assert experiment['parent_id'] == 'ch' and experiment['page'] == 3
    assert experiment['section_id'] != 'ch'
    assert '89.3%' in '\n'.join(b['text'] for b in n.section_blocks(model, experiment['section_id']))
    result = next(b for b in model['blocks'] if b['source_node_id'] == 'result')
    assert result['block_type'] == 'Paragraph' and result['paper_model_kind'] == 'Heading'
    assert all('header' != b['source_node_id'] for b in model['blocks'])
    context = n.structure_context({'chinese_abstract': '本文提出融合模型，准确率89.3%。'}, model)
    assert all(b['source_node_id'] != 'chapter_number' for b in context['blocks'])
    assert any('chapter_number' in bid for bid in context['coverage']['dropped'])
    assert any(b['source_node_id'] == 'chapter_title' for b in context['blocks'])


def test_structure_prompt_omits_large_coverage_inventory():
    context = {'abstract': '', 'toc': [], 'sections': [], 'blocks': [], 'coverage': {'kept': [], 'dropped': ['unused-' + str(i) for i in range(20000)], 'characters': 0}}
    public = n.structure_input(context)
    assert public['coverage']['dropped_count'] == 20000
    assert 'unused-19999' not in n.structure_prompt(context)


def test_retrieval_includes_other_result_settings_without_matching_abstract_number():
    d = {'id': 'd1', 'method': 'ExampleMethod', 'metric': '准确率', 'number': 25.5}
    setup = {'text': 'ExampleMethod 实验设置', 'block_type': 'Paragraph'}
    result = {'text': '对RQ2 的回答：Example-\nMethod 在另外两个数据集上分别提升9.4%和26.6%。', 'block_type': 'Paragraph'}
    assert n.retrieval_signals(d, result)[0] > n.retrieval_signals(d, setup)[0]
    assert n.lexical('Example-\nMethod') == 'examplemethod'
    assert n.lexical('Multiplication-Friendly') == 'multiplication-friendly'


def test_explicit_main_chapter_catalog_and_compact_verifier_input():
    ir, facts, structure = fixture()
    model = n.source_model(ir)
    context = n.structure_context(facts, model)
    assert 'ch' in context['main_chapter_ids']
    assert next(s for s in context['sections'] if s['section_id'] == 'exp')['main_chapter_id'] == 'ch'
    candidates, _ = n.retrieve_candidates(structure['declarations'], structure['mappings'], model)
    candidates[0]['debug_payload'] = 'unused-debug' * 10000
    structure['mappings'][0]['evidence'][0]['quote'] = 'locator-only-private-source'
    prompt = n.verifier_prompt(structure, candidates)
    assert 'unused-debug' not in prompt
    assert 'locator-only-private-source' not in prompt
    assert all(c['text'] in json.loads(prompt.split('输入：\n', 1)[1])['candidates'][i]['text'] for i, c in enumerate(candidates))


@pytest.mark.parametrize('metric,text', [('软件攻击面', '攻击面削减得分为0.20'), ('程序体积', '代码体积减少0.54')])
def test_metric_alias_retrieves_fractional_result(metric, text):
    score, signals = n.retrieval_signals({'metric': metric, 'number': 20}, {'text': text, 'block_type': 'Paragraph'})
    assert score >= 6 and any(s['kind'] == 'metric' for s in signals)


def test_contract_repair_is_bounded_and_keeps_raw_trace():
    ir, facts, structure = fixture()
    bad = copy.deepcopy(structure)
    bad['declarations'][0]['text'] = '模型伪造92.5%'
    model = n.source_model(ir)
    candidates, _ = n.retrieve_candidates(structure['declarations'], structure['mappings'], model)
    evidence = next(c for c in candidates if c['source_node_id'] == 'data')
    answer = valid_output(evidence)
    responses = iter([bad, structure, answer])
    events = []
    result = n.run_numeric(ir, facts, lambda messages: (next(responses), {}), lambda kind, data: events.append(kind))
    assert result['execution_status'] == 'completed'
    assert len(result['params']['contract_repairs']) == 1
    assert 'structure_output' in events and 'structure_repaired_output' in events
    calls = []
    def invalid(messages):
        calls.append(messages)
        return bad, {}
    result = n.run_numeric(ir, facts, invalid)
    assert len(calls) == 2 and result['execution_status'] == 'error' and not result['findings']


def test_verifier_contract_repair_is_bounded():
    ir, facts, structure = fixture()
    candidates, _ = n.retrieve_candidates(structure['declarations'], structure['mappings'], n.source_model(ir))
    answer = valid_output(next(c for c in candidates if c['source_node_id'] == 'data'))
    responses = iter([structure, {'results': []}, answer])
    result = n.run_numeric(ir, facts, lambda messages: (next(responses), {}))
    assert result['execution_status'] == 'completed' and result['params']['coverage']['complete']
    assert result['params']['contract_repairs'][0]['stage'] == 'numeric_verifier'
