"""Regression for an actual grounded citation reason rejected by word substrings."""
import copy

import pytest

from paper_compiler.program_analysis import _ground_fields

ACTUAL_REASON = "The citing context attributes to [44] the claim that Lewis et al. 2020 proposed the RAG framework, which retrieves relevant content from external knowledge sources before generation. The identified cited work (Lewis et al., Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks) states that RAG models combine pre-trained parametric and non-parametric memory for language generation, with the non-parametric memory being a dense vector index of Wikipedia accessed with a pre-trained neural retriever. This supports the attribution."

def ground(reason, *, wrong_quote=False, negative=False):
    data = {'citation_context': {'node_id': 'p'}, 'sources': [
        {'source_id': 'paper:p', 'origin': 'paper', 'node_id': 'p',
         'text': 'RAG retrieves external content before generation [1].'},
        {'source_id': 'external:body', 'origin': 'external', 'content_id': 'body',
         'work_id': 'work', 'text': 'The model retrieves passages and uses them when generating text.'}]}
    raw = {'fields': {'relation': {'state': 'observed', 'value': 'contradicted' if negative else 'supported',
        'basis': 'explicit_scope_contradiction' if negative else 'explicit_support', 'reason': reason, 'quotes': [
            {'source_id': 'paper:p', 'quote': data['sources'][0]['text']},
            {'source_id': 'external:body', 'quote': 'invented' if wrong_quote else data['sources'][1]['text']}
        ]}}}
    before = copy.deepcopy((raw, data))
    facts, evidence = _ground_fields({'fields': {'relation': 'string'}}, raw, data, True)
    assert (raw, data) == before
    return facts['relation'], evidence

def test_actual_knowledge_title_is_not_a_negative_reason():
    fact, evidence = ground(ACTUAL_REASON)
    assert fact['state'] == 'observed'
    assert fact['value'] == 'supported'
    assert {item['origin'] for item in evidence} == {'paper', 'external'}

@pytest.mark.parametrize('reason', [
    'The source does not mention this method.',
    'The source never discusses this method.',
    'There is no stated algorithm for this use.',
    '全文未提及该方法。',
    'The reasoning depends on absence of this detail.',
])
def test_actual_missing_detail_reasons_remain_unknown(reason):
    fact, _ = ground(reason, negative=True)
    assert fact['state'] == 'unknown'

def test_word_boundary_fix_does_not_accept_wrong_source_quotes():
    fact, _ = ground(ACTUAL_REASON, wrong_quote=True)
    assert fact['state'] == 'unknown'
