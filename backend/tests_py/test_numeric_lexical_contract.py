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



def wrong_parent_structure():
    ir, facts, structure = fixture()
    next(node for node in ir['nodes'] if node['id'] == 'other')['children'].append('other_exp')
    ir['nodes'].extend([
        {'id': 'other_exp', 'kind': 'Section', 'children': ['other_exp_heading'], 'attrs': {'level': 2}},
        {'id': 'other_exp_heading', 'kind': 'Heading', 'text': '4.1 实验评估', 'children': [], 'provenance': []},
    ])
    structure['mappings'][0]['experiment_section_ids'] = ['other_exp']
    return ir, facts, structure


def test_cross_chapter_diagnostic_names_declaration_prompt_aliases_and_actual_parent():
    ir, facts, structure = wrong_parent_structure()
    model = n.source_model(ir)
    original = copy.deepcopy(structure)
    with pytest.raises(n.ContractError) as error:
        n.validate_structure(structure, n.structure_context(facts, model), model)
    message = str(error.value)
    assert message.startswith('experiment is not a descendant of chapter')
    for detail in ['declaration_id=d1', 'chapter_id=S1', 'chapter_title=第三章 融合模型',
                   'experiment_id=S4', 'experiment_title=4.1 实验评估',
                   'actual_parent_id=S3', 'actual_parent_title=第四章 无关方法']:
        assert detail in message
    assert structure == original


def test_cross_chapter_diagnostic_without_aliases_uses_native_ids():
    ir, facts, structure = wrong_parent_structure()
    model = n.source_model(ir)
    context = n.structure_context(facts, model)
    context.pop('section_aliases')
    with pytest.raises(n.ContractError) as error:
        n.validate_structure(structure, context, model)
    for detail in ['chapter_id=ch', 'experiment_id=other_exp', 'actual_parent_id=other']:
        assert detail in str(error.value)


@pytest.mark.parametrize('first_bad', [0, 1])
def test_cross_chapter_diagnostic_locates_first_invalid_mapping_without_dropping_any_claim(first_bad):
    ir, facts, structure = wrong_parent_structure()
    structure['declarations'].append({**copy.deepcopy(structure['declarations'][0]), 'id': 'd2'})
    structure['mappings'].append({**copy.deepcopy(structure['mappings'][0]), 'declaration_id': 'd2'})
    if first_bad == 1:
        structure['mappings'][0]['experiment_section_ids'] = ['exp']
    original = copy.deepcopy(structure)
    model = n.source_model(ir)
    with pytest.raises(n.ContractError) as error:
        n.validate_structure(structure, n.structure_context(facts, model), model)
    assert 'declaration_id=d' + str(first_bad + 1) in str(error.value)
    assert structure == original


@pytest.mark.parametrize('invalid', [['unknown'], [None], None, 'other_exp', 5])
def test_cross_chapter_bad_experiment_types_keep_contract_error(invalid):
    ir, facts, structure = wrong_parent_structure()
    structure['mappings'][0]['experiment_section_ids'] = invalid
    model = n.source_model(ir)
    with pytest.raises(n.ContractError):
        n.validate_structure(structure, n.structure_context(facts, model), model)


@pytest.mark.parametrize('invalid', [None, 'other_exp', 5])
def test_cross_chapter_diagnostic_does_not_read_other_unvalidated_mapping_values(invalid):
    ir, facts, structure = wrong_parent_structure()
    structure['declarations'].append({**copy.deepcopy(structure['declarations'][0]), 'id': 'd2'})
    structure['mappings'].append({**copy.deepcopy(structure['mappings'][0]),
                                  'declaration_id': 'd2', 'experiment_section_ids': invalid})
    model = n.source_model(ir)
    with pytest.raises(n.ContractError) as error:
        n.validate_structure(structure, n.structure_context(facts, model), model)
    assert 'declaration_id=d1' in str(error.value)


def test_parent_diagnostic_keeps_valid_descendant_output_unchanged():
    ir, facts, structure = fixture()
    model = n.source_model(ir)
    original = copy.deepcopy(structure)
    assert n.validate_structure(structure, n.structure_context(facts, model), model)
    assert structure == original


def test_parent_diagnostic_keeps_only_explicit_single_contribution_fallback_self_mapping():
    from test_numeric_source_contract import independent_experiment
    model, context, structure = independent_experiment()
    assert n._single_contribution_fallback(structure, context, model)
    assert n.validate_structure(structure, context, model)
    assert structure['mappings'][0]['chapter_id'] in structure['mappings'][0]['experiment_section_ids']
    next(row for row in structure['mappings'] if row['declaration_id'] == 'd1').pop('mapping_mode')
    with pytest.raises(n.ContractError, match='experiment is not a descendant of chapter'):
        n.validate_structure(structure, context, model)


def test_parent_diagnostic_uses_existing_one_repair_and_continued_failure_stays_error():
    ir, facts, structure = wrong_parent_structure()
    calls = []
    def request(messages):
        calls.append(messages)
        return copy.deepcopy(structure), {}
    result = n.run_numeric(ir, facts, request)
    assert len(calls) == 2
    assert 'declaration_id=d1' in calls[1][0]['content']
    assert 'actual_parent_id=S3' in calls[1][0]['content']
    assert result['execution_status'] == 'error'
    assert result['outcome'] == 'inconclusive'
    assert not result['findings']


@pytest.mark.parametrize('unit', ['KB', 'MB', 'GB', 'TB', 'KiB', 'MiB', 'GiB', 'TiB', 'byte', 'bytes'])
def test_source_explicit_data_size_units_are_numeric_candidates_with_exact_source_tokens(unit):
    source = '通信消息规模达到4 ' + unit + '时出现变化。'
    candidates, _ = n.numeric_candidates(source)
    assert len(candidates) == 1
    row = candidates[0]
    assert row['value'] == '4' and row['unit'] == unit
    assert source[row['start']:row['end']] == row['source_text'] == '4'


@pytest.mark.parametrize('text', ['GPT-4版本。', 'GPT-4GB版本。', 'Pass@4GB版本。',
                                 '消息大小4GBps。', '消息大小4GiBextra。'])
def test_data_size_lexing_keeps_identifier_and_unit_boundaries(text):
    assert n.numeric_candidates(text)[0] == []


def test_real_four_gigabyte_declaration_stays_while_count_coverage_guard_remains_closed():
    _, model, context, structure = source_structure('本文提出融合模型。通信消息规模达到4 GB时出现变化。空值额外指标。在26个应用和8节点上准确率7.0%，另一环境提升14.6%。')
    structure['declarations'][0].update(number='4', metric='通信消息规模', unit='GB')
    for did, span, number, unit in [('extra', 'a3', '', ''), ('d2', 'a4', '7.0', '%'), ('d3', 'a4', '14.6', '%')]:
        structure['declarations'].append({**copy.deepcopy(structure['declarations'][0]), 'id': did,
            'abstract_span_id': span, 'number': number, 'unit': unit, 'condition': ''})
        structure['mappings'].append({**copy.deepcopy(structure['mappings'][0]), 'declaration_id': did})
    resolved = n.resolve_structure(structure, context, model)
    cleaned, audit = n.prune_non_numeric_declarations(resolved, context)
    assert {row['value'] for row in context['numeric_candidates']} == {'4', '26', '8', '7', '14.6'}
    assert not audit
    assert [d['id'] for d in cleaned['declarations']] == ['d1', 'extra', 'd2', 'd3']
    assert cleaned['declarations'][0]['unit'] == 'GB'


def test_unrecognized_real_numeric_unit_is_never_deleted_as_qualitative_extra():
    _, model, context, structure = source_structure('本文提出融合模型。通信消息规模达到4 PB时出现变化。准确率92.5%。')
    structure['declarations'][0].update(number='4', metric='通信消息规模', unit='PB')
    structure['declarations'].append({**copy.deepcopy(structure['declarations'][0]), 'id': 'd2',
                                      'abstract_span_id': 'a3', 'number': '92.5', 'unit': '%'})
    structure['mappings'].append({**copy.deepcopy(structure['mappings'][0]), 'declaration_id': 'd2'})
    resolved = n.resolve_structure(structure, context, model)
    cleaned, audit = n.prune_non_numeric_declarations(resolved, context)
    assert any(d['id'] == 'd1' for d in cleaned['declarations'])
    assert not any(d['declaration_id'] == 'd1' for d in audit)
    with pytest.raises(n.ContractError):
        n.validate_structure(cleaned, context, model)


def multi_failure_structure():
    ir, facts, structure = wrong_parent_structure()
    for did in ['d2', 'd3']:
        structure['declarations'].append({**copy.deepcopy(structure['declarations'][0]), 'id': did})
        structure['mappings'].append({**copy.deepcopy(structure['mappings'][0]), 'declaration_id': did})
    structure['declarations'][0]['number'] = ''
    structure['declarations'][2]['number'] = None
    return ir, facts, structure


def test_failed_output_collects_all_invalid_number_fields_and_bad_parent_mappings():
    ir, facts, structure = multi_failure_structure()
    model = n.source_model(ir)
    context = n.structure_context(facts, model)
    original = copy.deepcopy(structure)
    diagnostics = n.structure_failure_diagnostics(structure, context, model)
    numeric = [d for d in diagnostics if d['kind'] == 'invalid_numeric_field']
    parent = [d for d in diagnostics if d['kind'] == 'invalid_parent_mapping']
    assert [d['declaration_id'] for d in numeric] == ['d1', 'd3']
    assert all('abstract_span_id' in d for d in numeric)
    assert [d['declaration_id'] for d in parent] == ['d1', 'd2', 'd3']
    assert all(d['chapter_id'] == 'S1' and d['experiment_id'] == 'S4' and d['actual_parent_id'] == 'S3' for d in parent)
    assert structure == original


@pytest.mark.parametrize('data', [None, [], {'declarations': None, 'mappings': None},
    {'declarations': [None, {'id': 'd1', 'number': {}}], 'mappings': [None, {'chapter_id': [], 'experiment_section_ids': None}]},
    {'declarations': [], 'mappings': [{'chapter_id': 'ch', 'experiment_section_ids': [None, 'unknown', {}]}]}])
def test_failure_diagnostic_collection_is_safe_for_malformed_output(data):
    ir, facts, _ = fixture()
    model = n.source_model(ir)
    assert isinstance(n.structure_failure_diagnostics(data, n.structure_context(facts, model), model), list)


def test_existing_single_repair_receives_all_failure_locations_without_changing_first_error():
    ir, facts, structure = multi_failure_structure()
    calls = []
    def request(messages):
        calls.append(messages)
        return copy.deepcopy(structure), {}
    result = n.run_numeric(ir, facts, request)
    assert len(calls) == 2
    assert result['execution_status'] == 'error' and result['outcome'] == 'inconclusive'
    errors = result['params']['contract_repairs'][0]['errors']
    assert errors[0] == 'invalid numeric value'
    assert errors[1]['additional_diagnostics'] == result['params']['structure_failure_diagnostics']
    assert 'invalid_numeric_field' in calls[1][0]['content'] and 'invalid_parent_mapping' in calls[1][0]['content']
    assert not result['findings']


def test_valid_structure_and_restricted_fallback_have_no_new_diagnostics():
    from test_numeric_source_contract import independent_experiment
    ir, facts, structure = fixture()
    model = n.source_model(ir)
    original = copy.deepcopy(structure)
    assert n.structure_failure_diagnostics(structure, n.structure_context(facts, model), model) == []
    assert structure == original
    model, context, structure = independent_experiment()
    assert n._single_contribution_fallback(structure, context, model)
    assert n.structure_failure_diagnostics(structure, context, model) == []


@pytest.mark.parametrize('identifier', ['Pass@1', 'GPT-4'])
def test_real_number_prune_safety_keeps_existing_proven_identifier_only_extra_cleanup(identifier):
    _, model, context, structure = source_structure('本文提出融合模型。准确率92.5%。模型在' + identifier + '上取得最优结果。')
    structure['declarations'].append({**copy.deepcopy(structure['declarations'][0]), 'id': 'extra',
                                      'abstract_span_id': 'a3', 'number': ''})
    structure['mappings'].append({**copy.deepcopy(structure['mappings'][0]), 'declaration_id': 'extra'})
    cleaned, audit = n.prune_non_numeric_declarations(n.resolve_structure(structure, context, model), context)
    assert [d['declaration_id'] for d in audit] == ['extra']
    assert n.validate_structure(cleaned, context, model)


def test_unknown_real_size_stays_even_when_a_model_identifier_has_the_same_numeric_value():
    _, model, context, structure = source_structure('本文提出融合模型。GPT-4模型通信消息规模达到4 PB时出现变化。准确率92.5%。')
    structure['declarations'][0].update(number='4', metric='通信消息规模', unit='PB')
    structure['declarations'].append({**copy.deepcopy(structure['declarations'][0]), 'id': 'd2',
                                      'abstract_span_id': 'a3', 'number': '92.5', 'unit': '%'})
    structure['mappings'].append({**copy.deepcopy(structure['mappings'][0]), 'declaration_id': 'd2'})
    cleaned, audit = n.prune_non_numeric_declarations(n.resolve_structure(structure, context, model), context)
    assert [d['id'] for d in cleaned['declarations']] == ['d1', 'd2']
    assert not audit



def test_unknown_signed_real_size_is_not_proven_to_be_an_identifier_suffix():
    _, model, context, structure = source_structure('本文提出融合模型。通信消息规模达到-4 PB时出现变化。准确率92.5%。')
    structure['declarations'][0].update(number='-4', metric='通信消息规模', unit='PB')
    structure['declarations'].append({**copy.deepcopy(structure['declarations'][0]), 'id': 'd2',
                                      'abstract_span_id': 'a3', 'number': '92.5', 'unit': '%'})
    structure['mappings'].append({**copy.deepcopy(structure['mappings'][0]), 'declaration_id': 'd2'})
    cleaned, audit = n.prune_non_numeric_declarations(n.resolve_structure(structure, context, model), context)
    assert [d['id'] for d in cleaned['declarations']] == ['d1', 'd2']
    assert not audit



def test_source_deviation_and_rmsd_metrics_keep_real_angstrom_and_energy_values():
    source = '其生成结构与DFT基准的均方\n根偏差（RMSD）仅为0.0978 Å，能量偏差控制在0.995 kcal/mol。'
    candidates, _ = n.numeric_candidates(source)
    assert {d['value'] for d in candidates} == {'0.0978', '0.995'}
    assert all(source[d['start']:d['end']] == d['value'] for d in candidates)


@pytest.mark.parametrize('metric', ['R²', '𝑅²', 'R2', '𝑅2', 'R\n2', '𝑅\n2', 'R ^ 2', '𝑅 \t2'])
def test_r_squared_source_signal_keeps_result_and_excludes_metric_exponent(metric):
    source = '在分布外配体测试中取得0.9124 的' + metric + '，验证了通用性。'
    candidates, _ = n.numeric_candidates(source)
    assert {d['value'] for d in candidates} == {'0.9124'}
    assert source[candidates[0]['start']:candidates[0]['end']] == '0.9124'


def test_source_speed_synonyms_keep_both_multiplier_results_in_their_own_span():
    source = '总体性能提高2.8倍。模块运行速度分别\n加快约2.8× 与2.3×。'
    candidates, _ = n.numeric_candidates(source)
    assert {d['value'] for d in candidates if d['abstract_span_id'] == 'a2'} == {'2.8', '2.3'}


@pytest.mark.parametrize('operand', ['10', 'x', '𝑥', '(x)', '10^3'])
def test_new_speed_signal_does_not_turn_multiplication_into_multiplier_results(operand):
    source = '模块运行速度加快约2.8×' + operand + '。'
    assert n.numeric_candidates(source)[0] == []


@pytest.mark.parametrize('text', ['模型R2D2输出0.9124。', '模型𝑅2D2输出0.9124。',
                                 '模型RMSDNet输出0.0978Å。'])
def test_metric_synonyms_do_not_match_longer_model_identifiers(text):
    assert n.numeric_candidates(text)[0] == []


def test_r_squared_exponent_cannot_be_used_as_the_declared_result():
    _, model, context, structure = source_structure('本文提出融合模型。取得0.9124的𝑅2。')
    structure['declarations'][0].update(number='2', metric='R2', unit='')
    with pytest.raises(n.ContractError):
        n.validate_structure(n.resolve_structure(structure, context, model), context, model)


@pytest.mark.parametrize('source,values', [
    ('端到端时延降低20-30%。', ['20', '30']),
    ('端到端时延降低19-22%。', ['19', '22']),
    ('时延降低11-15%，抖动降低25-28%，丢包率降低5-18%。', ['11', '15', '25', '28', '5', '18']),
    ('追踪干扰降低3.5-12.2倍。', ['3.5', '12.2']),
    ('可建模1-5% 的不可见空闲资源，并提升任务吞吐量。', ['1', '5']),
    ('The latency decreased by 20-30%.', ['20', '30']),
])
def test_explicit_hyphen_interval_preserves_both_source_endpoints(source, values):
    candidates, excluded = n.numeric_candidates(source)
    assert [row['value'] for row in candidates] == values
    assert not excluded
    assert [source[row['start']:row['end']] for row in candidates] == values


@pytest.mark.parametrize('gap', [' ', '\n', '\t'])
def test_hyphen_interval_endpoint_allows_pdf_spacing_without_rewriting_offsets(gap):
    source = '时延降低20' + gap + '-' + gap + '30%。'
    candidates, excluded = n.numeric_candidates(source)
    assert [row['value'] for row in candidates] == ['20', '30']
    assert not excluded
    assert source[candidates[1]['start']:candidates[1]['end']] == '30'


@pytest.mark.parametrize('source,forbidden', [
    ('GPT-4-5%版本提升准确率。', '5'),
    ('Qwen-2.5-7%模型提升准确率。', '7'),
    ('Pass@1-5%提升。', '5'),
    ('Pass@1/3-5%提升。', '5'),
    ('模型R2-5%提升。', '5'),
    ('公式x=1-5%表示误差。', '5'),
    ('公式x -1-5%表示误差。', '5'),
    ('公式1e-3-5%表示误差。', '5'),
    ('公式1E-3-5%表示误差。', '5'),
    ('公式1e-5%表示误差。', '5'),
    ('没有量纲的20-30变化。', '30'),
])
def test_interval_lexing_does_not_admit_identifier_formula_or_unmeasured_suffixes(source, forbidden):
    candidates, _ = n.numeric_candidates(source)
    assert forbidden not in {row['value'] for row in candidates}


@pytest.mark.parametrize('number,unit,source', [
    ('20-30', '%', '时延降低20-30%。'),
    ('3.5-12.2', '倍', '追踪干扰降低3.5-12.2倍。'),
])
def test_hyphen_interval_passes_only_with_exact_source_values(number, unit, source):
    _, model, context, structure = source_structure('本文提出融合模型。' + source)
    structure['declarations'][0].update(number=number, unit=unit, metric='时延降低')
    resolved = n.resolve_structure(structure, context, model)
    assert n.validate_structure(resolved, context, model)
    structure['declarations'][0]['number'] = '20-31' if unit == '%' else '3.5-12.3'
    with pytest.raises(n.ContractError):
        n.validate_structure(n.resolve_structure(structure, context, model), context, model)


@pytest.mark.parametrize('source', [
    '公式x = 1-5%表示误差。',
    'Pass@ 1-5%提升。',
    'Pass@1 / 3-5%提升。',
    '公式1e- 3-5%表示误差。',
    '误差在- 1-5%之间。',
    '公式x^2-5%',
    '公式x^2-5%表示误差。',
])
def test_interval_left_prefix_cannot_hide_formula_index_or_sign_behind_spacing(source):
    candidates, _ = n.numeric_candidates(source)
    assert '5' not in {row['value'] for row in candidates}


@pytest.mark.parametrize('gap', [' ', '\n', '\t'])
@pytest.mark.parametrize('prefix', ['x =', 'Pass@', 'Pass@1 /', '1e-', '-', '+', 'x^', '−', '－', '＋', 'x×'])
def test_pdf_spacing_before_interval_left_preserves_formula_and_identifier_exclusion(prefix, gap):
    source = '误差' + prefix + gap + '1-5%。'
    candidates, _ = n.numeric_candidates(source)
    assert '5' not in {row['value'] for row in candidates}


@pytest.mark.parametrize('identifier', ['Qwen2.5', 'Qwen2.5-Instruct', 'Qwen2.5和GPT-4'])
def test_complete_identifier_token_proof_can_prune_only_a_non_numeric_extra(identifier):
    _, model, context, structure = source_structure('本文提出融合模型。准确率92.5%。模型在' + identifier + '上保持优势。')
    structure['declarations'].append({**copy.deepcopy(structure['declarations'][0]), 'id': 'extra',
                                      'abstract_span_id': 'a3', 'number': ''})
    structure['mappings'].append({**copy.deepcopy(structure['mappings'][0]), 'declaration_id': 'extra'})
    resolved = n.resolve_structure(structure, context, model)
    original = copy.deepcopy(resolved)
    cleaned, audit = n.prune_non_numeric_declarations(resolved, context)
    assert [d['declaration_id'] for d in audit] == ['extra']
    assert n.validate_structure(cleaned, context, model)
    assert resolved == original


@pytest.mark.parametrize('number', ['4', '2.5', '.5'])
def test_identifier_offset_proof_never_covers_a_distinct_unknown_real_quantity(number):
    _, model, context, structure = source_structure('本文提出融合模型。Qwen2.5模型通信消息规模达到' + number + ' PB时出现变化。准确率92.5%。')
    structure['declarations'][0].update(number=number, metric='通信消息规模', unit='PB')
    structure['declarations'].append({**copy.deepcopy(structure['declarations'][0]), 'id': 'd2',
                                      'abstract_span_id': 'a3', 'number': '92.5', 'unit': '%'})
    structure['mappings'].append({**copy.deepcopy(structure['mappings'][0]), 'declaration_id': 'd2'})
    resolved = n.resolve_structure(structure, context, model)
    cleaned, audit = n.prune_non_numeric_declarations(resolved, context)
    assert [d['id'] for d in cleaned['declarations']] == ['d1', 'd2']
    assert audit == []



def source_span_failure_structure():
    abstract = '本文提出融合模型。首次定量评测通信竞争并作定性分类。GPU通信规模达到4 GB。优化应用性能，使26个应用在8节点下总完成时间缩短7.0%，共享网卡时缩短14.6%。'
    ir, model, context, structure = source_structure(abstract)
    structure['declarations'][0].update(number='4', unit='GB', metric='GPU通信规模', condition='')
    for did, number in [('d2', '7.0'), ('d3', '14.6')]:
        structure['declarations'].append({**copy.deepcopy(structure['declarations'][0]),
            'id': did, 'abstract_span_id': 'a4', 'number': number, 'unit': '%', 'metric': '总完成时间缩短'})
        structure['mappings'].append({**copy.deepcopy(structure['mappings'][0]), 'declaration_id': did})
    return ir, model, context, n.resolve_structure(structure, context, model)


def test_failure_diagnostics_locate_wrong_source_span_and_real_uncovered_conditions():
    _, model, context, structure = source_span_failure_structure()
    before = copy.deepcopy((structure, context, model))
    diagnostics = n.structure_failure_diagnostics(structure, context, model)
    wrong = next(d for d in diagnostics if d['kind'] == 'numeric_source_mismatch')
    assert wrong['declaration_id'] == 'd1' and wrong['abstract_span_id'] == 'a2'
    assert wrong['source_excerpt'] == '首次定量评测通信竞争并作定性分类。'
    assert wrong['source_candidates'] == []
    assert any(s['abstract_span_id'] == 'a3' and s['candidates'][0]['value'] == '4'
               and '4 GB' in s['source_excerpt'] for s in wrong['other_source_candidates'])
    missing = next(d for d in diagnostics if d['kind'] == 'uncovered_numeric_candidates' and d['abstract_span_id'] == 'a4')
    assert {c['value'] for c in missing['candidates']} == {'26', '8'}
    assert all(c['required_coverage'] == 'number_or_grounded_condition' for c in missing['candidates'])
    assert '26个应用在8节点' in missing['source_excerpt']
    assert 'condition' in missing['coverage_constraint']
    assert (structure, context, model) == before
    with pytest.raises(n.ContractError, match='declaration has no numeric source'):
        n.validate_structure(structure, context, model)


def test_failure_diagnostics_report_missing_percentage_source_alongside_invalid_parent():
    ir, _, structure = wrong_parent_structure()
    model = n.source_model(ir)
    context = n.structure_context({'chinese_abstract': '本文提出融合模型。平均延迟4ms。准确率90%。'}, model)
    structure['contributions'] = [{'id': 'c1', 'abstract_span_id': 'a1'}]
    structure['declarations'][0].update(abstract_span_id='a2', number='4', unit='ms', metric='平均延迟')
    structure['declarations'][0].pop('text')
    structure = n.resolve_structure(structure, context, model)
    diagnostics = n.structure_failure_diagnostics(structure, context, model)
    missing = next(d for d in diagnostics if d['kind'] == 'uncovered_numeric_candidates')
    assert missing['abstract_span_id'] == 'a3'
    assert [c['value'] for c in missing['candidates']] == ['90']
    assert missing['candidates'][0]['required_coverage'] == 'number'
    assert missing['source_excerpt'] == '准确率90%。'
    assert any(d['kind'] == 'invalid_parent_mapping' for d in diagnostics)
    with pytest.raises(n.ContractError, match='experiment is not a descendant'):
        n.validate_structure(structure, context, model)


def test_source_diagnostics_keep_valid_fields_and_grounded_conditions_unchanged():
    _, model, context, structure = source_span_failure_structure()
    structure['declarations'][0]['abstract_span_id'] = 'a3'
    structure['declarations'][0]['text'] = 'GPU通信规模达到4 GB。'
    structure['declarations'][1]['condition'] = '26个应用在8节点下'
    before = copy.deepcopy((structure, context, model))
    assert n.structure_failure_diagnostics(structure, context, model) == []
    assert n.validate_structure(structure, context, model)
    assert (structure, context, model) == before


def test_source_diagnostic_context_is_bounded_without_changing_invalid_output():
    import json
    _, model, context, structure = source_span_failure_structure()
    structure['declarations'] = [{**copy.deepcopy(structure['declarations'][0]), 'id': 'bad' + str(i)} for i in range(100)]
    before = copy.deepcopy(structure)
    diagnostics = n.structure_failure_diagnostics(structure, context, model)
    assert len(json.dumps(diagnostics, ensure_ascii=False).encode('utf-8')) <= 6000
    assert diagnostics[-1]['kind'] == 'diagnostics_truncated' and diagnostics[-1]['omitted'] > 0
    assert structure == before


def test_source_diagnostics_only_enrich_existing_single_repair_and_keep_first_error():
    ir, _, context, structure = source_span_failure_structure()
    calls = []
    def request(messages):
        calls.append(messages)
        return copy.deepcopy(structure), {}
    result = n.run_numeric(ir, {'chinese_abstract': context['abstract']}, request)
    assert len(calls) == 2
    assert result['execution_status'] == 'error'
    assert result['params']['failure']['message'] == 'declaration has no numeric source'
    assert result['params']['contract_repairs'][0]['errors'][0] == 'declaration has no numeric source'
    assert 'numeric_source_mismatch' in calls[1][0]['content']
    assert 'uncovered_numeric_candidates' in calls[1][0]['content']
    assert '修复后请逐项自查' in calls[1][0]['content']
    assert '百分比' in calls[1][0]['content']
    assert calls[0][0]['content'] == n.structure_prompt(context)
    assert not result['findings']



def test_failed_experiment_diagnostic_lists_only_supported_descendants_of_current_chapter():
    ir, facts, structure = unsupported_experiment()
    for parent, sid, title in [('ch', 'same_chapter_exp', '3.2 实验评估'), ('other', 'other_chapter_exp', '4.1 实验评估')]:
        next(node for node in ir['nodes'] if node['id'] == parent)['children'].append(sid)
        ir['nodes'].extend([
            {'id': sid, 'kind': 'Section', 'children': [sid + '_h'], 'attrs': {'level': 2}},
            {'id': sid + '_h', 'kind': 'Heading', 'text': title, 'children': [], 'provenance': []},
        ])
    model = n.source_model(ir)
    context = n.structure_context(facts, model)
    original = copy.deepcopy(structure)
    diagnostics = n.structure_failure_diagnostics(structure, context, model)
    failed = next(d for d in diagnostics if d['kind'] == 'unsupported_experiment_mapping')
    assert failed['experiment_title'] == 'Model architecture and implementation'
    assert failed['chapter_id'] == 'S1'
    assert [x['title'] for x in failed['same_chapter_supported_sections']] == ['3.2 实验评估']
    for candidate in failed['same_chapter_supported_sections']:
        native = context['section_aliases'][candidate['section_id']]
        assert n.descendant(model, native, 'ch') and n.experimental_support(model, native)
        assert candidate['source_excerpt']
    assert structure == original
    with pytest.raises(n.ContractError, match='mapped experiment classification lacks supporting source text'):
        n.validate_structure(structure, context, model)



@pytest.mark.parametrize('case', ['missing', 'null'])
def test_precondition_metadata_failure_diagnostic_names_each_field_without_normalizing(case):
    ir, facts, structure = fixture()
    for condition in structure['preconditions']:
        if case == 'missing':
            condition.pop('suggestion')
        else:
            condition['suggestion'] = None
    model = n.source_model(ir)
    context = n.structure_context(facts, model)
    before = copy.deepcopy(structure)
    diagnostics = n.structure_failure_diagnostics(structure, context, model)
    fields = [d for d in diagnostics if d['kind'] == 'invalid_precondition_field']
    assert {d['precondition_id'] for d in fields} == n.CONDITIONS
    assert all(d['field'] == 'suggestion' and d['actual_type'] == case and 'string' in d['expected'] for d in fields)
    assert structure == before
    with pytest.raises(n.ContractError, match='precondition suggestion must be text'):
        n.validate_structure(structure, context, model)



def test_valid_numeric_main_path_never_calls_failure_helper_or_adds_model_calls(monkeypatch):
    from test_numeric_consistency import valid_output
    ir, facts, structure = fixture()
    model = n.source_model(ir)
    candidates, _ = n.retrieve_candidates(structure['declarations'], structure['mappings'], model)
    answer = valid_output(next(row for row in candidates if row['source_node_id'] == 'data'))
    replies = iter([structure, answer]); calls = []
    def request(messages):
        calls.append(messages)
        return copy.deepcopy(next(replies)), {}
    def unexpected_helper(*args):
        raise AssertionError('failure diagnostics called on valid main path')
    monkeypatch.setattr(n, 'structure_failure_diagnostics', unexpected_helper)
    result = n.run_numeric(ir, facts, request)
    assert result['execution_status'] == 'completed' and result['outcome'] == 'issues_found'
    assert len(calls) == 2 and 'contract_repairs' not in result['params']



def test_experiment_diagnostic_excerpt_uses_support_page_for_cross_page_source_node():
    ir, facts, structure = unsupported_experiment()
    model = n.source_model(ir)
    model['sections']['cross_page_exp'] = {'section_id': 'cross_page_exp', 'parent_id': 'ch',
        'level': 2, 'title': '3.2 方法实现', 'heading_node_id': None, 'block_ids': []}
    for page, text in [(1, '本节介绍方法实现涉及的参数。'), (2, '实验结果表明方法有效。')]:
        model['blocks'].append({'block_id': 'same-paragraph:p' + str(page),
            'source_node_id': 'same-paragraph', 'section_id': 'cross_page_exp',
            'page': page, 'block_type': 'Paragraph', 'text': text, 'provenance': []})
    context = n.structure_context(facts, model)
    support = n.experimental_support(model, 'cross_page_exp')
    assert len(support) == 1 and support[0]['page'] == 2
    diagnostics = n.structure_failure_diagnostics(structure, context, model)
    failed = next(d for d in diagnostics if d['kind'] == 'unsupported_experiment_mapping')
    candidate = next(c for c in failed['same_chapter_supported_sections'] if c['title'] == '3.2 方法实现')
    assert candidate['source_excerpt'] == '实验结果表明方法有效。'
    assert '参数' not in candidate['source_excerpt']



@pytest.mark.parametrize('include_selected', [False, True])
def test_experiment_hint_order_keeps_supported_ancestor_selected_and_nearby_real_evaluation(include_selected):
    ir, facts, structure = unsupported_experiment()
    model = n.source_model(ir)
    def section(sid, parent, title, text=''):
        model['sections'][sid] = {'section_id': sid, 'parent_id': parent, 'level': 2 if parent == 'ch' else 3,
            'title': title, 'heading_node_id': None, 'block_ids': []}
        if text:
            model['blocks'].append({'block_id': sid + ':p1', 'source_node_id': sid + '_text',
                'section_id': sid, 'page': 1, 'block_type': 'Paragraph', 'text': text, 'provenance': []})
    for i in range(4):
        section('broad' + str(i), 'ch', '3.' + str(i) + ' 背景设计', '本节讨论 performance 背景。')
    section('evaluation', 'ch', '3.4 实验与性能评估')
    section('setup', 'evaluation', '3.4.1 实验环境')
    section('overhead', 'evaluation', '3.4.2 采集开销表现', '评估采集开销。')
    section('accuracy', 'evaluation', '3.4.3 采集准确度表现', '评估采集准确度。')
    bad = model['sections'].pop('exp'); bad['parent_id'] = 'evaluation'; model['sections']['exp'] = bad
    if include_selected:
        section('selected', 'ch', '3.5 已选方案', '实验验证已选方案。')
        structure['mappings'][0]['experiment_section_ids'].append('selected')
    assert n.experimental_support(model, 'broad0')
    context = n.structure_context(facts, model); before = copy.deepcopy(structure)
    diagnostics = n.structure_failure_diagnostics(structure, context, model)
    failed = next(d for d in diagnostics if d['kind'] == 'unsupported_experiment_mapping' and d['declaration_id'] == 'd1')
    choices = failed['same_chapter_supported_sections']
    assert choices[0]['title'] == '3.4 实验与性能评估'
    if include_selected:
        assert choices[1]['title'] == '3.5 已选方案'
    else:
        assert {c['title'] for c in choices} == {'3.4 实验与性能评估', '3.4.1 实验环境', '3.4.2 采集开销表现', '3.4.3 采集准确度表现'}
    for choice in choices:
        sid = context['section_aliases'][choice['section_id']]
        assert n.descendant(model, sid, 'ch') and n.experimental_support(model, sid)
    assert structure == before


def test_structural_self_check_instruction_is_not_added_to_numeric_verifier_repair():
    from test_numeric_consistency import valid_output
    ir, facts, structure = fixture()
    candidates, _ = n.retrieve_candidates(structure['declarations'], structure['mappings'], n.source_model(ir))
    answer = valid_output(next(row for row in candidates if row['source_node_id'] == 'data'))
    answer['results'][0]['evidence'][0]['quote'] = '不存在的原句'
    responses = iter([structure, answer, answer]); calls = []
    def request(messages):
        calls.append(messages)
        return copy.deepcopy(next(responses)), {}
    result = n.run_numeric(ir, facts, request)
    assert len(calls) == 3 and result['execution_status'] == 'error'
    assert '修复后请逐项自查' not in calls[2][0]['content']
