"""Summary contributions can cover child methods without borrowing unrelated data."""
import copy

import numeric_consistency as n


def case():
    contributions=[{'id':'c1','text':'针对监督信号重塑，研究基于模态条件扩散的监督信号重塑方法。'},
                   {'id':'c2','text':'进一步研究基于跨域伪监督构造的监督信号重塑方法。'},
                   {'id':'c3','text':'研究社交关系去噪的信息协同建模方法。'}]
    abstract=''.join(c['text'] for c in contributions)+'面向监督信号重塑的相关方法最高提升17.61%。'
    d={'id':'d1','contribution_id':'c1','number':'17.61','metric':'Recall/NDCG','unit':'%',
       'condition':'面向监督信号重塑的相关方法','method':'','text':'面向监督信号重塑的相关方法最高提升17.61%。'}
    structure={'contributions':contributions,'declarations':[d],
               'mappings':[{'declaration_id':'d1','chapter_id':'ch4','experiment_section_ids':['e4']} ]}
    sections={}
    blocks=[]
    for i,title in [(4,'基于模态条件扩散的监督信号重塑方法'),(5,'基于跨域伪监督构造的监督信号重塑方法'),(6,'基于社交关系去噪的信息协同建模方法')]:
        sections[f'ch{i}']={'parent_id':None,'title':title,'section_id':f'ch{i}'}
        sections[f'e{i}']={'parent_id':f'ch{i}','title':f'{i}.4 实验结果与分析','section_id':f'e{i}'}
        blocks.append({'block_id':f'b{i}','section_id':f'ch{i}','source_node_id':f'n{i}','page':i,'block_type':'Heading','text':title,'provenance':[]})
    return structure,{'abstract':abstract},{'sections':sections,'blocks':blocks}


def test_summary_scope_covers_both_grounded_child_methods_not_unrelated_chapter():
    structure,context,model=case()
    result=n.expand_contribution_scope(structure,context,model)
    extra=result['mappings'][0]['contribution_scope']
    assert set(extra['chapter_ids'])=={'ch4','ch5'}
    assert set(extra['experiment_section_ids'])=={'e4','e5'}
    assert 'ch6' not in extra['chapter_ids']
    assert set(extra['contribution_ids'])=={'c1','c2'}
    assert all(e['quote'] in context['abstract'] for e in extra['abstract_evidence'])


def test_named_single_method_must_not_expand_to_sibling_method():
    structure,context,model=case()
    structure['declarations'][0]['method']='DiffusionA'
    structure['declarations'][0]['text'] = 'DiffusionA最高提升17.61%。'
    context['abstract'] += structure['declarations'][0]['text']
    result=n.expand_contribution_scope(structure,context,model)
    assert 'contribution_scope' not in result['mappings'][0]


def test_unmatched_child_title_cannot_borrow_a_chapter_with_only_common_category():
    structure,context,model=case()
    model['sections']['ch5']['title']='基于另一种未声明机制的监督信号重塑方法'
    result=n.expand_contribution_scope(structure,context,model)
    assert 'contribution_scope' not in result['mappings'][0]


def test_ungrounded_contribution_does_not_establish_additional_scope():
    structure,context,model=case()
    structure['contributions'][1]['text']='原摘要没有的新方法'
    result=n.expand_contribution_scope(structure,context,model)
    assert 'contribution_scope' not in result['mappings'][0]


def test_original_structure_and_source_model_remain_unchanged():
    structure,context,model=case()
    before=copy.deepcopy((structure,context,model))
    n.expand_contribution_scope(structure,context,model)
    assert (structure,context,model)==before


def test_generic_group_source_overrides_a_locator_invented_single_method():
    structure, context, model = case()
    structure['declarations'][0]['method'] = 'DiffusionA'
    result = n.expand_contribution_scope(structure, context, model)
    assert result['declarations'][0]['method'] == ''
    assert result['declarations'][0]['model_method'] == 'DiffusionA'
    assert set(result['mappings'][0]['contribution_scope']['chapter_ids']) == {'ch4', 'ch5'}


def test_locator_group_condition_without_grouped_native_target_cannot_expand():
    structure, context, model = case()
    structure['declarations'][0]['text'] = '其中一种方法最高提升17.61%。'
    result = n.expand_contribution_scope(structure, context, model)
    assert 'contribution_scope' not in result['mappings'][0]


def test_native_named_method_condition_is_not_erased_by_atomic_clause_trimming():
    structure, context, model = case()
    d = structure['declarations'][0]
    d['method'] = 'DiffusionA'
    d['source_context'] = 'DiffusionA中，' + d['text']
    context['abstract'] += d['source_context']
    result = n.expand_contribution_scope(structure, context, model)
    assert result['declarations'][0]['method'] == 'DiffusionA'
    assert 'contribution_scope' not in result['mappings'][0]


def test_grouped_locator_contribution_does_not_erase_native_child_method_spans():
    structure, context, model = case()
    texts = ['本文针对监督信号重塑，研究基于模态条件扩散的监督信号重塑方法。',
             '本\n文进一步研\n究基于跨域伪监督构造的监督信号重塑方法。',
             structure['declarations'][0]['text']]
    context.update(abstract=''.join(texts), abstract_spans=[
        {'id': f'a{i}', 'text': text} for i, text in enumerate(texts, 1)])
    structure['contributions'] = [{'id': 'c1', 'text': texts[-1], 'abstract_span_id': 'a3'}]
    expanded = n.expand_contribution_scope(structure, context, model)
    scope = expanded['mappings'][0]['contribution_scope']
    assert set(scope['chapter_ids']) == {'ch4', 'ch5'}
    assert {e['abstract_span_id'] for e in scope['abstract_evidence']} == {'a1', 'a2'}
    assert all(e['quote'] in context['abstract'] for e in scope['abstract_evidence'])


def test_native_child_span_fallback_never_uses_background_or_ungrounded_text():
    structure, context, model = case()
    target = structure['declarations'][0]['text']
    structure['contributions'] = [{'id': 'c1', 'text': target}]
    context['abstract_spans'] = [{'id': 'background', 'text': '现有研究基于跨域伪监督构造的监督信号重塑方法。'},
                                 {'id': 'forged', 'text': '本文研究基于模态条件扩散的监督信号重塑方法。'}]
    expanded = n.expand_contribution_scope(structure, context, model)
    assert 'contribution_scope' not in expanded['mappings'][0]


def test_explicitly_negated_native_method_is_not_an_affirmative_child_contribution():
    structure, context, model = case()
    texts = ['本文研究基于模态条件扩散的监督信号重塑方法。',
             '本文未研究基于跨域伪监督构造的监督信号重塑方法。',
             structure['declarations'][0]['text']]
    context.update(abstract=''.join(texts), abstract_spans=[
        {'id': f'a{i}', 'text': text} for i, text in enumerate(texts, 1)])
    structure['contributions'] = [{'id': 'c1', 'text': texts[-1]}]
    expanded = n.expand_contribution_scope(structure, context, model)
    assert 'contribution_scope' not in expanded['mappings'][0]
