import copy
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


@pytest.mark.parametrize('change', ['false_string', 'missing_condition', 'duplicate_condition', 'unknown_condition', 'missing_mapping', 'bad_parent', 'bad_source', 'bad_contribution', 'duplicate_declaration'])
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
