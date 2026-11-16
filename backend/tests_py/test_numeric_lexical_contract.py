import copy

import pytest

import numeric_consistency as n
from test_numeric_source_contract import source_structure
from test_numeric_consistency import fixture


@pytest.mark.parametrize('written,value', [('一', '1'), ('两', '2'), ('三', '3'), ('十', '10'),
                                          ('十一', '11'), ('二十', '20'), ('二十一', '21'), ('九十九', '99')])
def test_explicit_chinese_integer_multiplier_has_source_value_and_offsets(written, value):
    abstract = '本文系统吞吐量提升超过' + written + '倍，并行执行提升20%。'
    candidates, excluded = n.numeric_candidates(abstract)
    assert n.numeric_values(abstract) == {value, '20'}
    normalized = [row for row in candidates if row.get('normalization') == 'chinese-integer-multiplier/1.0']
    assert len(normalized) == 1
    row = normalized[0]
    assert row['value'] == value and row['unit'] == '倍'
    assert abstract[row['start']:row['end']] == row['source_text'] == written
    assert not excluded


def two_claim_structure(abstract='本文提出融合模型。系统吞吐量提升超过两倍，并行执行提升20%。'):
    ir, model, context, structure = source_structure(abstract)
    structure['declarations'][0].update(number='2', metric='吞吐量提升', unit='倍', comparison='relative')
    second = {**copy.deepcopy(structure['declarations'][0]), 'id': 'd2', 'number': '20', 'unit': '%'}
    structure['declarations'].append(second)
    structure['mappings'].append({**copy.deepcopy(structure['mappings'][0]), 'declaration_id': 'd2'})
    return ir, model, context, structure


def test_twofold_and_twenty_percent_share_source_without_rewriting_comparison():
    _, model, context, structure = two_claim_structure()
    original = copy.deepcopy(structure)
    resolved = n.resolve_structure(structure, context, model)
    assert n.validate_structure(resolved, context, model)
    assert context['abstract_numeric_inventory'] == ['2', '20']
    assert '超过两倍' in resolved['declarations'][0]['text']
    assert resolved['declarations'][0]['number'] == '2'
    assert resolved['declarations'][0]['unit'] == '倍'
    assert resolved['declarations'][0]['comparison'] == 'relative'
    assert structure == original


def test_pure_chinese_multiplier_has_numeric_scope_and_valid_source():
    _, model, context, structure = two_claim_structure('本文提出融合模型。系统吞吐量提升超过两倍。')
    structure['declarations'].pop()
    structure['mappings'].pop()
    resolved = n.resolve_structure(structure, context, model)
    assert context['abstract_numeric_inventory'] == ['2']
    assert n.validate_structure(resolved, context, model)


def test_omitting_chinese_multiplier_keeps_percentage_but_fails_coverage():
    _, model, context, structure = two_claim_structure()
    structure['declarations'].pop(0)
    structure['mappings'].pop(0)
    resolved = n.resolve_structure(structure, context, model)
    with pytest.raises(n.ContractError, match='missing abstract multiplier'):
        n.validate_structure(resolved, context, model)


@pytest.mark.parametrize('change', ['wrong_number', 'wrong_span', 'wrong_parent'])
def test_chinese_source_support_does_not_relax_other_contracts(change):
    _, model, context, structure = two_claim_structure('本文提出融合模型。系统吞吐量提升超过两倍，并行执行提升20%。另一个场景吞吐量提高三倍。')
    structure['declarations'].append({**copy.deepcopy(structure['declarations'][0]), 'id': 'd3',
                                      'abstract_span_id': 'a3', 'number': '3'})
    structure['mappings'].append({**copy.deepcopy(structure['mappings'][0]), 'declaration_id': 'd3'})
    if change == 'wrong_number': structure['declarations'][0]['number'] = '4'
    if change == 'wrong_span': structure['declarations'][0]['abstract_span_id'] = 'a3'
    if change == 'wrong_parent': structure['mappings'][0]['experiment_section_ids'] = ['other']
    resolved = n.resolve_structure(structure, context, model)
    with pytest.raises(n.ContractError):
        n.validate_structure(resolved, context, model)


@pytest.mark.parametrize('text', ['一方面提高性能，二者均可用。', '二维性能与第二章的讨论。',
    '第一倍的词典条目。', '性能提高几倍。', '性能提高二十多倍。', '两倍体材料。',
    '二倍数与二倍率。', '性能提高负两倍。', '性能提高两点五倍。', '性能提高三分之二倍。', '性能提高两倍半。'])
def test_non_numeric_hanzi_ordinals_and_unsupported_multipliers_stay_out(text):
    assert n.numeric_values(text) == set()
    assert n.numeric_candidates(text) == ([], [])


def test_arabic_tokens_and_candidate_rows_remain_exactly_unchanged():
    text = '2020年以来，F1和Pass@1的准确率提升20%，平均误差3.57米。'
    assert n.numeric_values(text) == {'2020', '1', '20', '3.57'}
    candidates, excluded = n.numeric_candidates(text)
    assert candidates == [
        {'abstract_span_id': 'a1', 'value': '20', 'start': 23, 'end': 25},
        {'abstract_span_id': 'a1', 'value': '3.57', 'start': 31, 'end': 35},
    ]
    assert [row['reason'] for row in excluded] == ['year', 'identifier_or_metric_index', 'identifier_or_metric_index']


@pytest.mark.parametrize('text', ['相对误差控制在-5.02%至6.93%。', '误差为-5.02毫秒。',
                                 'The error is -5.02% with a maximum of 6.93%.',
                                 'Latency changed by -5.02 ms.'])
def test_explicit_negative_measured_tokens_are_not_identifier_suffixes(text):
    candidates, _ = n.numeric_candidates(text)
    assert '5.02' in {row['value'] for row in candidates}
    row = next(row for row in candidates if row['value'] == '5.02')
    assert text[row['start']:row['end']] == '5.02'
    assert text[row['start']-1] == '-'


@pytest.mark.parametrize('text', ['GPT-4版本提升准确率。', 'Qwen-2.5模型进行评估。', 'GPT-4%版本。',
                                 'Pass@-1%提升。', '公式x=-5.02%表示偏差。', '公式x -5.02%表示偏差。',
                                 '没有量纲的-5.02变化。'])
def test_identifier_formula_and_unmeasured_hyphens_are_not_negative_results(text):
    candidates, _ = n.numeric_candidates(text)
    assert candidates == []


def test_real_negative_percentage_interval_keeps_exact_source_contract():
    _, model, context, structure = source_structure('本文提出融合模型。相对误差控制在-5.02%至6.93%。')
    structure['declarations'][0].update(number='-5.02 至 6.93', metric='相对误差', unit='%')
    resolved = n.resolve_structure(structure, context, model)
    assert n.validate_structure(resolved, context, model)
    assert {row['value'] for row in context['numeric_candidates']} == {'5.02', '6.93'}
    assert '-5.02%' in resolved['declarations'][0]['text']


def unsupported_experiment():
    ir, facts, structure = fixture()
    for node in ir['nodes']:
        if node['id'] in ['eh', 'data']:
            node['text'] = 'Model architecture and implementation'
            node['provenance'][0]['node_text_end'] = len(node['text'])
    structure['declarations'].append({**copy.deepcopy(structure['declarations'][0]), 'id': 'd2'})
    structure['mappings'].append({**copy.deepcopy(structure['mappings'][0]), 'declaration_id': 'd2'})
    return ir, facts, structure


def test_failed_experiment_source_error_names_prompt_alias_title_and_all_declarations():
    ir, facts, structure = unsupported_experiment()
    model = n.source_model(ir)
    context = n.structure_context(facts, model)
    original = copy.deepcopy(structure)
    with pytest.raises(n.ContractError) as error:
        n.validate_structure(structure, context, model)
    message = str(error.value)
    assert message.startswith('mapped experiment classification lacks supporting source text')
    assert 'section_id=S2' in message
    assert 'Model architecture and implementation' in message
    assert 'declaration_ids=d1,d2' in message
    assert structure == original


def test_missing_alias_old_context_still_rejects_and_names_native_section():
    ir, facts, structure = unsupported_experiment()
    model = n.source_model(ir)
    context = n.structure_context(facts, model)
    context.pop('section_aliases')
    with pytest.raises(n.ContractError, match='section_id=exp'):
        n.validate_structure(structure, context, model)


def test_specific_error_only_uses_existing_single_bounded_repair():
    ir, facts, structure = unsupported_experiment()
    calls = []
    def request(messages):
        calls.append(messages)
        return copy.deepcopy(structure), {}
    result = n.run_numeric(ir, facts, request)
    assert result['execution_status'] == 'error'
    assert len(calls) == 2
    assert 'section_id=S2' in calls[1][0]['content']
    assert 'declaration_ids=d1,d2' in calls[1][0]['content']
    assert result['params']['contract_repairs'][0]['stage'] == 'structure_locator'


def test_real_experiment_source_keeps_original_acceptance():
    ir, facts, structure = fixture()
    model = n.source_model(ir)
    assert n.validate_structure(structure, n.structure_context(facts, model), model)


def test_same_numeric_value_with_percent_unit_cannot_cover_a_chinese_multiplier():
    _, model, context, structure = two_claim_structure('本文提出融合模型。系统吞吐量提升超过二十倍，并行执行提升20%。')
    structure['declarations'].pop(0)
    structure['mappings'].pop(0)
    resolved = n.resolve_structure(structure, context, model)
    with pytest.raises(n.ContractError, match='missing abstract multiplier'):
        n.validate_structure(resolved, context, model)


@pytest.mark.parametrize('invalid', [None, 'exp', 5])
def test_diagnostic_skips_other_unvalidated_non_list_mappings(invalid):
    ir, facts, structure = unsupported_experiment()
    structure['mappings'][1]['experiment_section_ids'] = invalid
    model = n.source_model(ir)
    original = copy.deepcopy(structure)
    with pytest.raises(n.ContractError) as error:
        n.validate_structure(structure, n.structure_context(facts, model), model)
    assert str(error.value).endswith('declaration_ids=d1')
    assert structure == original


@pytest.mark.parametrize('unit', ['times', 'x', '×', 'fold'])
def test_existing_multiplier_unit_spellings_still_cover_the_same_source_claim(unit):
    _, model, context, structure = two_claim_structure()
    structure['declarations'][0]['unit'] = unit
    resolved = n.resolve_structure(structure, context, model)
    assert n.validate_structure(resolved, context, model)
    assert resolved['declarations'][0]['unit'] == unit


@pytest.mark.parametrize('gap', [' ', '\n', '\t'])
@pytest.mark.parametrize('text,wrong_value', [('性能提高负{gap}两倍。', '2'),
    ('性能提高三分之{gap}二倍。', '2'), ('性能提高两点{gap}五倍。', '5'),
    ('性能提高两倍{gap}半。', '2'), ('性能提高一百{gap}两倍。', '2'),
    ('性能提高第{gap}两倍。', '2')])
def test_pdf_whitespace_cannot_turn_unsupported_chinese_forms_into_integer_claims(text, wrong_value, gap):
    source = text.format(gap=gap)
    assert n.numeric_values(source) == set()
    assert n.numeric_candidates(source) == ([], [])
    _, model, context, structure = source_structure('本文提出融合模型。' + source)
    structure['declarations'][0].update(number=wrong_value, metric='性能', unit='倍')
    resolved = n.resolve_structure(structure, context, model)
    with pytest.raises(n.ContractError):
        n.validate_structure(resolved, context, model)


@pytest.mark.parametrize('gap', [' ', '\n', '\t'])
def test_unambiguous_chinese_multiplier_with_pdf_spacing_keeps_original_offsets(gap):
    source = '吞吐量提升超过' + gap + '两' + gap + '倍，并行提升20%。'
    candidates, _ = n.numeric_candidates(source)
    assert {row['value'] for row in candidates} == {'2', '20'}
    row = next(row for row in candidates if row.get('normalization'))
    assert source[row['start']:row['end']] == row['source_text'] == '两'


@pytest.mark.parametrize('gap', [' ', '\n', '\t'])
@pytest.mark.parametrize('prefix', ['Pass@', 'metric/', 'model_'])
def test_pdf_whitespace_before_minus_does_not_turn_identifier_indexes_into_results(prefix, gap):
    candidates, excluded = n.numeric_candidates(prefix + gap + '-1%提升。')
    assert candidates == []
    assert excluded[0]['reason'] == 'identifier_or_metric_index'


@pytest.mark.parametrize('sign', ['+', '-', '−', '＋', '－'])
@pytest.mark.parametrize('gap', ['', ' '])
def test_signed_chinese_multipliers_stay_out_of_unsigned_integer_grammar(sign, gap):
    source = '性能提高' + sign + gap + '两倍。'
    assert n.numeric_values(source) == set()
    assert n.numeric_candidates(source) == ([], [])
    _, model, context, structure = source_structure('本文提出融合模型。' + source)
    structure['declarations'][0].update(number='2', metric='性能', unit='倍')
    with pytest.raises(n.ContractError):
        n.validate_structure(n.resolve_structure(structure, context, model), context, model)
