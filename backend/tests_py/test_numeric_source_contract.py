import copy

import pytest

import numeric_consistency as n
from test_numeric_consistency import fixture


def source_structure(abstract):
    ir, _, structure = fixture()
    model = n.source_model(ir)
    context = n.structure_context({'chinese_abstract': abstract}, model)
    structure['contributions'] = [{'id': 'c1', 'abstract_span_id': 'a1'}]
    structure['declarations'] = [{**structure['declarations'][0], 'abstract_span_id': 'a2'}]
    structure['declarations'][0].pop('text')
    return ir, model, context, structure


@pytest.mark.parametrize('marker', ['1）', '1)'])
def test_bare_list_indexes_are_not_numeric_results(marker):
    text = '主要工作包括：' + marker + '提出模型，有效提升知识准确性。2）构建应用，降低调用成本。'
    candidates, excluded = n.numeric_candidates(text)
    assert candidates == []
    assert {row['value'] for row in excluded} == {'1', '2'}


def test_real_result_following_list_index_remains_in_scope():
    candidates, _ = n.numeric_candidates('主要工作包括：1）模型F1提升7.0%，Pass@1提升14.6%。2020年完成。')
    assert {row['value'] for row in candidates} == {'7', '14.6'}


@pytest.mark.parametrize('number,source', [('', '模型在F1和AUC上取得最优结果'), ('50', '模型降低通信带宽竞争')])
def test_only_proven_non_numeric_extra_rows_are_removed(number, source):
    _, model, context, structure = source_structure('本文提出融合模型。准确率92.5%。' + source + '。')
    extra = {**structure['declarations'][0], 'id': 'extra', 'abstract_span_id': 'a3', 'number': number}
    structure['declarations'].append(extra)
    structure['mappings'].append({**copy.deepcopy(structure['mappings'][0]), 'declaration_id': 'extra'})
    resolved = n.resolve_structure(structure, context, model)
    cleaned, audit = n.prune_non_numeric_declarations(resolved, context)
    assert [row['id'] for row in cleaned['declarations']] == ['d1']
    assert [row['declaration_id'] for row in cleaned['mappings']] == ['d1']
    assert [row['declaration_id'] for row in audit] == ['extra']
    assert n.validate_structure(cleaned, context, model)
    assert len(resolved['declarations']) == 2


def test_all_rows_dropped_cannot_turn_missing_true_candidate_into_pass():
    _, model, context, structure = source_structure('本文提出融合模型。准确率92.5%。F1取得最优结果。')
    structure['declarations'][0].update(abstract_span_id='a3', number='')
    resolved = n.resolve_structure(structure, context, model)
    cleaned, audit = n.prune_non_numeric_declarations(resolved, context)
    assert not audit
    with pytest.raises(n.ContractError):
        n.validate_structure(cleaned, context, model)


@pytest.mark.parametrize('number,span', [('88', 'a2'), ('92.5', 'a3'), ('', 'a2')])
def test_wrong_or_missing_real_candidate_numbers_are_not_pruned(number, span):
    _, model, context, structure = source_structure('本文提出融合模型。准确率92.5%。F1取得最优结果。')
    structure['declarations'][0].update(number=number, abstract_span_id=span)
    resolved = n.resolve_structure(structure, context, model)
    cleaned, audit = n.prune_non_numeric_declarations(resolved, context)
    assert not audit
    with pytest.raises(n.ContractError):
        n.validate_structure(cleaned, context, model)


def test_wrong_number_in_same_source_span_is_contract_error():
    _, model, context, structure = source_structure('本文提出融合模型。准确率92.5%。')
    structure['declarations'][0]['number'] = '88'
    resolved = n.resolve_structure(structure, context, model)
    with pytest.raises(n.ContractError, match='numeric value.*source'):
        n.validate_structure(resolved, context, model)


def test_missing_percentage_candidate_still_uses_original_coverage_guard():
    _, model, context, structure = source_structure('本文提出融合模型。准确率92.5%。召回率88%。')
    resolved = n.resolve_structure(structure, context, model)
    cleaned, _ = n.prune_non_numeric_declarations(resolved, context)
    with pytest.raises(n.ContractError, match='missing abstract percentage'):
        n.validate_structure(cleaned, context, model)


def independent_experiment():
    ir, facts, structure = fixture()
    next(row for row in ir['nodes'] if row['id'] == 'body')['children'] = ['ch', 'exp', 'other']
    next(row for row in ir['nodes'] if row['id'] == 'ch')['children'].remove('exp')
    model = n.source_model(ir)
    context = n.structure_context(facts, model)
    condition = next(row for row in structure['preconditions'] if row['id'] == 'experiment_subsection')
    condition.update(passed=False, reason='原实验映射失败', suggestion='检查映射')
    return model, context, structure


def test_failed_fallback_keeps_original_conditions_and_mappings():
    model, context, structure = independent_experiment()
    structure['mappings'] = []
    original = copy.deepcopy(structure)
    assert n._single_contribution_fallback(structure, context, model) is False
    assert structure == original


def test_valid_fallback_is_published_only_after_full_contract_validation():
    model, context, structure = independent_experiment()
    # This independent experiment is the only fallback root and has source evidence.
    context['abstract'] = '本文提出融合模型，在数据集A准确率92.5%。'
    context['numeric_candidates'], context['excluded_numeric_tokens'] = n.numeric_candidates(context['abstract'])
    assert n._single_contribution_fallback(structure, context, model)
    assert n.validate_structure(structure, context, model)


def test_failed_fallback_result_does_not_publish_all_true_conditions():
    ir, facts, structure = fixture()
    next(row for row in ir['nodes'] if row['id'] == 'body')['children'].append('exp')
    next(row for row in ir['nodes'] if row['id'] == 'ch')['children'].remove('exp')
    next(row for row in structure['preconditions'] if row['id'] == 'experiment_subsection')['passed'] = False
    structure['mappings'] = []
    result = n.run_numeric(ir, facts, lambda _messages: (copy.deepcopy(structure), {}))
    assert result['execution_status'] == 'completed'
    assert result['outcome'] == 'inconclusive'
    assert not all(row['passed'] for row in result['params']['preconditions'])
    assert result['params']['mapping_fallback_attempts'] == [{'status': 'rejected', 'reason': 'missing declaration mapping'}]


def test_extra_row_cannot_hide_missing_non_percentage_result_in_same_span():
    _, model, context, structure = source_structure('本文提出融合模型。平均误差3.57 m和3.69 m。F1取得最优结果。')
    structure['declarations'][0].update(number='3.57', metric='平均误差', unit='m')
    structure['declarations'].append({**structure['declarations'][0], 'id': 'extra',
                                      'abstract_span_id': 'a3', 'number': ''})
    structure['mappings'].append({**copy.deepcopy(structure['mappings'][0]), 'declaration_id': 'extra'})
    resolved = n.resolve_structure(structure, context, model)
    cleaned, audit = n.prune_non_numeric_declarations(resolved, context)
    assert not audit
    with pytest.raises(n.ContractError):
        n.validate_structure(cleaned, context, model)


def test_explicit_source_context_numbers_allow_proven_extra_row_cleanup():
    _, model, context, structure = source_structure('本文提出融合模型。在26个应用和8节点上准确率92.5%。F1取得最优结果。')
    structure['declarations'][0]['condition'] = '26个应用和8节点'
    structure['declarations'].append({**structure['declarations'][0], 'id': 'extra',
                                      'abstract_span_id': 'a3', 'number': ''})
    resolved = n.resolve_structure(structure, context, model)
    cleaned, audit = n.prune_non_numeric_declarations(resolved, context)
    assert audit
    assert n.validate_structure(cleaned, context, model)


def test_wrong_source_number_gets_one_repair_and_preserves_inconsistency():
    from test_numeric_consistency import valid_output
    ir, model, context, structure = source_structure('本文提出融合模型。准确率92.5%。')
    structure = n.resolve_structure(structure, context, model)
    bad = copy.deepcopy(structure)
    bad['declarations'][0]['number'] = '88'
    candidates, _ = n.retrieve_candidates(structure['declarations'], structure['mappings'], model)
    answer = valid_output(next(row for row in candidates if row['source_node_id'] == 'data'))
    responses = iter([bad, structure, answer])
    result = n.run_numeric(ir, {'chinese_abstract': context['abstract']}, lambda _messages: (next(responses), {}))
    assert result['execution_status'] == 'completed'
    assert result['outcome'] == 'issues_found'
    assert result['params']['contract_repairs'][0]['errors'] == ['numeric value not grounded in declaration source']
    assert len(result['params']['contract_repairs']) == 1
    assert result['params']['numeric_results'][0]['status'] == 'inconsistent'
    assert result['findings'][0]['severity'] == 'warning'


@pytest.mark.parametrize('condition', ['3.69 m', '26个应用和8节点'])
def test_condition_cannot_cover_a_missing_result_with_an_unrelated_number(condition):
    _, model, context, structure = source_structure('本文提出融合模型。平均误差3.57 m和3.69 m。F1取得最优结果。')
    structure['declarations'][0].update(number='3.57', metric='平均误差', unit='m', condition=condition)
    structure['declarations'].append({**structure['declarations'][0], 'id': 'extra',
                                      'abstract_span_id': 'a3', 'number': ''})
    resolved = n.resolve_structure(structure, context, model)
    cleaned, audit = n.prune_non_numeric_declarations(resolved, context)
    assert not audit
    assert len(cleaned['declarations']) == 2


@pytest.mark.parametrize('text', ['平均误差分别为：1、2米。', '准确率分别为：1、2%。',
                                 '平均误差分别为：1、 2米。', '平均误差分别为：1.  2米。'])
def test_parallel_measurements_after_colon_are_not_list_indexes(text):
    candidates, excluded = n.numeric_candidates(text)
    assert {row['value'] for row in candidates} == {'1', '2'}
    assert not excluded
