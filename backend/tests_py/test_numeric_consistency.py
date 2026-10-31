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


def test_no_numeric_scope_is_completed_without_llm_call():
    ir, facts, _ = fixture()
    facts = copy.deepcopy(facts)
    facts['chinese_abstract'] = '本文提出融合模型，并介绍了数据集和实验方法。'

    def request(_messages):
        raise AssertionError('locator must not be called without abstract percentages')

    result = n.run_numeric(ir, facts, request)
    assert result['execution_status'] == 'completed'
    assert result['outcome'] == 'not_applicable'
    assert result['params']['stage'] == 'preconditions'
    assert [row['id'] for row in result['params']['preconditions']] == [
        'abstract_numeric', 'contribution_mapping', 'experiment_subsection']
    assert result['params']['preconditions'][0]['status'] == 'failed'
    assert all(row['status'] == 'skipped' for row in result['params']['preconditions'][1:])


def test_non_percentage_numeric_claims_remain_in_scope_and_heading_toc_is_valid():
    ir, facts, _ = fixture()
    facts = copy.deepcopy(facts)
    facts['chinese_abstract'] = '本文方法在三个区域的平均误差分别为3.57 m、3.69 m和3.62 m。'
    model = n.source_model(ir)
    model['toc'] = []
    context = n.structure_context(facts, model)
    assert '3.57' in context['abstract_numeric_inventory']
    assert context['toc'], 'section headings should provide a source-backed ToC fallback'


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
    public = [c for task in json.loads(prompt.split('输入：\n', 1)[1])['tasks'] for c in task['candidates']]
    assert sorted(c['text'] for c in public) == sorted(c['text'] for c in candidates)
    assert public[0]['is_primary']


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
    assert result['params']['contract_repairs'][0]['stage'] == 'numeric_verifier:d1'


def test_program_citations_are_exact_and_never_fix_unknown_or_cross_ids():
    ir, facts, structure = fixture()
    candidates, _ = n.retrieve_candidates(structure['declarations'], structure['mappings'], n.source_model(ir))
    c = next(c for c in candidates if c['source_node_id'] == 'data')
    raw = {'results': [{'declaration_id': 'd1', 'evidence': [{'candidate_id': c['candidate_id']}]}]}
    resolved = n.resolve_citations(raw, candidates)
    assert 'quote' not in raw['results'][0]['evidence'][0]
    assert resolved['results'][0]['evidence'][0]['quote'] == c['text']
    assert resolved['results'][0]['evidence'][0]['quote_origin'] == 'program_candidate'
    for did, cid in [('d1', 'invented'), ('other', c['candidate_id'])]:
        x = n.resolve_citations({'results': [{'declaration_id': did, 'evidence': [{'candidate_id': cid}]}]}, candidates)
        assert 'quote' not in x['results'][0]['evidence'][0]
    aliases = n.resolve_citations({'results': [{'declaration_id': 'd1', 'evidence': [c['candidate_id']]}]}, candidates)
    assert aliases['results'][0]['evidence'][0]['quote'] == c['text']


def test_percentage_inventory_rejects_silent_omission_and_merged_metrics():
    ir, facts, data = fixture()
    model = n.source_model(ir)
    context = n.structure_context({'chinese_abstract': facts['chinese_abstract'] + '整体框架提升18.2%—21.4%。'}, model)
    with pytest.raises(n.ContractError, match='missing abstract percentage'):
        n.validate_structure(data, context, model)
    data['declarations'][0]['text'] += '，同时减少54%程序体积'
    with pytest.raises(n.ContractError):
        n.validate_structure(data, context, model)
    assert n.percentage_values('20.0%与20%及0.2%') == {'20', '0.2'}


def test_identical_interval_bounds_merge_without_changing_raw_output():
    ir, facts, data = fixture()
    d = data['declarations'][0]
    d['text'] = '准确率范围18.2%—21.4%'
    d['number'] = 18.2
    other = {**d, 'id': 'd2', 'number': 21.4}
    data['declarations'].append(other)
    data['mappings'].append({**data['mappings'][0], 'declaration_id': 'd2'})
    normalized, merged = n.merge_duplicate_ranges(data)
    assert len(data['declarations']) == 2 and len(normalized['declarations']) == 1
    assert merged == [{'kept_id': 'd1', 'removed_id': 'd2', 'reason': 'identical_interval_source_and_scope'}]
    assert normalized['declarations'][0]['number'] == '18.2—21.4'


def test_verifier_isolates_claim_inputs_and_preserves_other_claim_after_timeout():
    ir, facts, structure = fixture()
    structure['declarations'].append({**structure['declarations'][0], 'id': 'd2', 'text': '提升5.3个百分点', 'number': 5.3, 'metric': '提升', 'unit': '百分点'})
    structure['mappings'].append({**structure['mappings'][0], 'declaration_id': 'd2'})
    inputs = []
    def request(messages):
        if not inputs:
            inputs.append('locator')
            return structure, {}
        payload = json.loads(messages[0]['content'].split('输入：\n', 1)[1])
        assert len(payload['tasks']) == 1
        task = payload['tasks'][0]
        inputs.append(task['declaration']['id'])
        assert all(c['declaration_id'] == task['declaration']['id'] for c in task['candidates'])
        if task['declaration']['id'] == 'd1': raise TimeoutError('first claim timed out')
        return {'results': [{'declaration_id': 'd2', 'reason': '数值可核验', 'suggestion': '', 'status': 'consistent', 'evidence': [task['candidates'][0]['candidate_id']]}]}, {}
    result = n.run_numeric(ir, facts, request)
    assert inputs == ['locator', 'd1', 'd2']
    assert [r['status'] for r in result['params']['numeric_results']] == ['inconclusive', 'consistent']


@pytest.mark.parametrize('status,claim,reason,source,expected', [
    ('inconsistent', 'F1提升28.9%', '基线不明确，无法确认这一提升', 'F1提升20.3%', 'inconclusive'),
    ('inconsistent', '准确率92.5%', '同一条件准确率89.3%，数值矛盾', '准确率89.3%', 'inconsistent'),
    ('consistent', '攻击面平均减少20%', '0.20可换算20%', 'Util攻击面削减0.20', 'inconclusive'),
    ('consistent', '准确率最高提升25%', '某数据集提升25%', '某数据集提升25%', 'inconclusive'),
    ('consistent', '准确率最高提升25%', '三个数据集最多25%', '三个数据集最多25%', 'consistent'),
])
def test_conservative_statistical_evidence_guard(status, claim, reason, source, expected):
    row = {'declaration_id': 'd1', 'declaration': {'text': claim}, 'status': status, 'reason': reason, 'suggestion': '', 'evidence': [{'quote': source}]}
    limits = n.conservative_evidence_guard([row])
    assert row['status'] == expected
    assert bool(limits) == (expected != status)
    if limits: assert row['model_status'] == status and row['model_reason'] == reason


def test_locator_selects_source_spans_and_program_supplies_exact_heading():
    ir, facts, data = fixture()
    model = n.source_model(ir)
    facts['chinese_abstract'] = '本文提出融合模型，在数据集A准确率92.5%。'
    context = n.structure_context(facts, model)
    span = context['abstract_spans'][0]
    data['contributions'][0].pop('text')
    data['contributions'][0]['abstract_span_id'] = span['id']
    data['declarations'][0].pop('text')
    data['declarations'][0]['abstract_span_id'] = span['id']
    data['mappings'][0].pop('evidence')
    resolved = n.resolve_structure(data, context, model)
    assert 'text' not in data['contributions'][0]
    assert resolved['declarations'][0]['text'] == '在数据集A准确率92.5%'
    assert resolved['mappings'][0]['evidence'][0]['source_node_id'] == 'eh'
    assert n.validate_structure(resolved, context, model)
    data['declarations'][0]['abstract_span_id'] = 'invented'
    with pytest.raises(n.ContractError): n.validate_structure(n.resolve_structure(data, context, model), context, model)


def test_simultaneous_metrics_in_one_span_need_individual_numbers():
    ir, facts, data = fixture()
    facts['chinese_abstract'] = '本文提出融合模型，准确率92.5%，同时降低体积54%。'
    model = n.source_model(ir)
    context = n.structure_context(facts, model)
    span = context['abstract_spans'][0]
    data['contributions'][0]['text'] = '本文提出融合模型'
    data['declarations'][0].pop('text')
    data['declarations'][0]['abstract_span_id'] = span['id']
    with pytest.raises(n.ContractError, match='missing abstract percentage'):
        n.validate_structure(n.resolve_structure(data, context, model), context, model)
    data['declarations'].append({**data['declarations'][0], 'id': 'd2', 'number': 54, 'metric': '体积'})
    data['mappings'].append({**data['mappings'][0], 'declaration_id': 'd2'})
    resolved = n.resolve_structure(data, context, model)
    assert resolved['declarations'][1]['text'] == '同时降低体积54%'
    assert n.validate_structure(resolved, context, model)


def test_source_clause_narrows_broader_indexed_metric_before_verification():
    ir, facts, data = fixture()
    facts['chinese_abstract'] = ('本文提出融合模型，在数据集A的Pass@1/3/5/10指标上均有提升，'
                                 '其中Pass@1相对提升41.46%—53.49%。')
    model = n.source_model(ir)
    context = n.structure_context(facts, model)
    span = context['abstract_spans'][0]
    data['contributions'][0].pop('text')
    data['contributions'][0]['abstract_span_id'] = span['id']
    data['declarations'][0].pop('text')
    data['declarations'][0].update(abstract_span_id=span['id'], number='41.46—53.49',
                                    metric='Pass@1/3/5/10相对提升',
                                    condition='数据集A的Pass@1/3/5/10指标')
    data['mappings'][0].pop('evidence')
    resolved = n.resolve_structure(data, context, model)
    declaration = resolved['declarations'][0]
    assert declaration['text'] == '其中Pass@1相对提升41.46%—53.49%'
    assert declaration['metric'] == 'Pass@1相对提升'
    assert declaration['condition'] == '数据集A的Pass@1指标'
    assert declaration['source_metric_constraint'] == 'Pass@1'
    assert declaration['model_metric'] == 'Pass@1/3/5/10相对提升'
    candidates, _ = n.retrieve_candidates(resolved['declarations'], resolved['mappings'], model)
    prompt = n.verifier_prompt(resolved, candidates)
    task = json.loads(prompt.split('输入：\n', 1)[1])['tasks'][0]['declaration']
    assert task['metric'] == 'Pass@1相对提升'
    assert task['condition'] == '数据集A的Pass@1指标'
    assert 'model_metric' not in task and 'model_condition' not in task


def test_source_clause_only_narrows_the_same_named_indexed_metric():
    row = {'metric': 'Recall@1/5', 'condition': 'Pass@1/3/5/10指标'}
    n.narrow_indexed_metric_constraint(row, '其中Pass@1相对提升41.46%—53.49%')
    assert row['metric'] == 'Recall@1/5'
    assert row['condition'] == 'Pass@1指标'
    assert row['source_metric_constraint'] == 'Pass@1'


def test_named_method_mapping_requires_its_actual_body_chapter():
    ir, facts, data = fixture()
    data['declarations'][0]['method'] = 'GuardMODEL'
    model = n.source_model(ir)
    with pytest.raises(n.ContractError, match='named method GuardMODEL not found'):
        n.validate_structure(data, n.structure_context(facts, model), model)
    next(b for b in model['blocks'] if b['source_node_id'] == 'data')['text'] += ' GuardMODEL'
    assert n.validate_structure(data, n.structure_context(facts, model), model)


def test_locator_section_aliases_cannot_be_confused_with_text_node_ids():
    ir, facts, data = fixture()
    model = n.source_model(ir)
    context = n.structure_context(facts, model)
    public = n.structure_input(context)
    assert all(s['section_id'].startswith('S') for s in public['sections'])
    assert all('source_node_id' not in b and 'block_id' not in b for b in public['blocks'])
    assert all('heading_node_id' not in s for s in public['sections'])
    reverse = {native: alias for alias, native in context['section_aliases'].items()}
    data['mappings'][0] = {'declaration_id': 'd1', 'chapter_id': reverse['ch'], 'experiment_section_ids': [reverse['exp']]}
    resolved = n.resolve_structure(data, context, model)
    assert resolved['mappings'][0]['chapter_id'] == 'ch'
    assert resolved['mappings'][0]['experiment_section_ids'] == ['exp']
    assert n.validate_structure(resolved, context, model)


@pytest.mark.parametrize('claim,observed,expected', [('20', '20.73', 'inconclusive'), ('28.9', '28.6', 'inconclusive'), ('20.7', '20.73', 'consistent')])
def test_approximation_must_obey_decimal_rounding(claim, observed, expected):
    row = {'declaration_id': 'd1', 'declaration': {'text': '准确率' + claim + '%', 'number': claim}, 'status': 'consistent',
           'reason': '属于合理近似和四舍五入', 'suggestion': '', 'evidence': [{'quote': '准确率' + observed + '%'}]}
    n.conservative_evidence_guard([row])
    assert row['status'] == expected


def _fake_table(matrix, bbox=(10, 100, 300, 300)):
    from types import SimpleNamespace
    rows = []
    width = (bbox[2] - bbox[0]) / max(len(matrix[0]), 1)
    height = (bbox[3] - bbox[1]) / max(len(matrix), 1)
    for row_index, row in enumerate(matrix):
        cells = []
        for column_index in range(len(row)):
            cells.append((bbox[0] + column_index * width,
                          bbox[1] + row_index * height,
                          bbox[0] + (column_index + 1) * width,
                          bbox[1] + (row_index + 1) * height))
        rows.append(SimpleNamespace(
            bbox=(bbox[0], bbox[1] + row_index * height, bbox[2],
                  bbox[1] + (row_index + 1) * height),
            cells=cells,
        ))
    return SimpleNamespace(
        bbox=bbox,
        rows=rows,
        header=SimpleNamespace(names=list(matrix[0])),
        extract=lambda: matrix,
    )


def _table_model():
    return {
        'blocks': [{
            'page': 1,
            'block_type': 'Caption',
            'text': 'Table 1 Results',
            'section_id': 'exp',
            'source_node_id': 'caption',
            'provenance': [{'bbox': [10, 50, 100, 70]}],
        }]
    }


def test_structured_table_restores_rows_columns_and_source_binding():
    table, failure = n._table_structure(
        _fake_table([['', 'mean error', 'median error'],
                     ['method A', '3.57', '3.38'],
                     ['method B', '3.73', '3.62']]),
        1, 1, _table_model(), 800,
    )
    assert failure is None
    assert table['reliability'] == 'reliable'
    assert table['matrix'][1][1] == '3.57'
    assert table['rows'][1]['cells'][1]['column_index'] == 1
    assert table['section_id'] == 'exp'
    assert table['source_node_ids'] == ['caption']


def test_structured_table_marks_merged_or_multilevel_headers_limited():
    table, failure = n._table_structure(
        _fake_table([['', 'position', None, None],
                     ['id', 'actual x', 'actual y', 'estimated x'],
                     ['1', '2', '6', '6']]),
        1, 1, _table_model(), 800,
    )
    assert failure is None
    assert table['reliability'] == 'limited'
    assert 'merged_or_multilevel_header_cells' in table['limitations']


def test_structured_table_marks_possible_cross_page_continuation():
    table, failure = n._table_structure(
        _fake_table([['metric', 'value'], ['mean error', '3.57']],
                    bbox=(10, 100, 300, 790)),
        1, 1, _table_model(), 800,
    )
    assert failure is None
    assert table['cross_page'] is True
    assert 'possible_cross_page_continuation' in table['limitations']


def test_unbound_table_is_retained_but_not_claimed_as_reliable():
    model = {'blocks': []}
    table, failure = n._table_structure(
        _fake_table([['metric', 'value'], ['mean error', '3.57']]),
        1, 1, model, 800,
    )
    assert failure is None
    assert table['section_id'] is None
    assert table['reliability'] == 'limited'
    assert 'no_paper_model_source_binding' in table['limitations']


def test_retrieval_prioritizes_traceable_structured_tables():
    ir, facts, data = fixture()
    model = n.source_model(ir)
    model['tables'] = [{
        'table_id': 'p8-t1',
        'page': 8,
        'bbox': [20, 100, 500, 300],
        'caption': 'Table 3-2',
        'source_node_ids': ['caption'],
        'section_id': 'exp',
        'matrix': [['', 'Accuracy'], ['dataset A', '89.3%']],
        'rows': [],
        'column_headers': ['', 'Accuracy'],
        'reliability': 'reliable',
        'limitations': [],
        'cross_page': False,
    }]
    candidates, traces = n.retrieve_candidates(data['declarations'], data['mappings'], model)
    structured = [c for c in candidates if c['block_type'] == 'StructuredTable']
    assert structured and structured[0]['candidate_id'] == 'd1:t1'
    assert structured[0]['is_primary'] is True
    assert structured[0]['provenance'][0]['bbox'] == [20, 100, 500, 300]
