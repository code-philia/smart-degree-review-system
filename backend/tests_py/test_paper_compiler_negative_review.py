"""Negative citation facts always require source-only review, regardless of vocabulary."""
from copy import deepcopy
import pytest
from paper_compiler import conflict_review as review
from paper_compiler.program_analysis import _ground_fields
from test_paper_compiler_complete_work_support import sample, answer as scope_answer
from test_paper_compiler_conflict_witness import answered as conflict_answer

BASIS = review.COMPLETE_WORK_BASIS


def fixed_sample(producer_basis='explicit_scope_contradiction'):
    _, raw, data = sample()
    request = {'name': 'fixed_citation_support_v1', 'targets': ['ReferenceUse'],
               'fields': {'relation': 'string'}}
    raw['fields']['relation'].update(
        basis=producer_basis,
        value='contradicted' if producer_basis == 'explicit_scope_contradiction' else 'unsupported_attribution')
    return request, raw, data


def test_unrelated_no_sentence_never_authenticates_negative_fact_without_review():
    request, raw, data = fixed_sample()
    data['sources'][1]['text'] += ' No warranties are provided.'
    raw['fields']['relation']['quotes'][1]['quote'] = data['sources'][1]['text']
    fact = _ground_fields(request, raw, data, True)[0]['relation']
    assert fact['state'] == 'unknown'


def test_unrelated_no_sentence_still_receives_independent_review_and_can_be_rejected():
    request, raw, data = fixed_sample()
    data['sources'][1]['text'] += ' No warranties are provided.'
    raw['fields']['relation']['quotes'][1]['quote'] = data['sources'][1]['text']
    class InsufficientReviewer:
        max_attempts = 1
        def __init__(self): self.calls = 0
        def complete_json(self, task, instructions, data, max_tokens):
            self.calls += 1
            assert task == review.TASK
            assert data['nodes'][0]['node']['id'] == 'review-0'
            return {'results': {'review-0': {'decision': 'insufficient'}}}
    client = InsufficientReviewer()
    proofs, receipt, reason = review.resolve_review(request, raw, data, client=client)
    assert client.calls == 1
    assert not proofs and receipt['status'] == 'completed' and reason
    assert _ground_fields(request, raw, data, True, conflict_verifications=proofs)[0]['relation']['state'] == 'unknown'


@pytest.mark.parametrize('producer_basis,proof_kind,expected_value,expected_basis,verification', [
    ('explicit_scope_contradiction', BASIS, 'unsupported_attribution', BASIS, 'support_verification'),
    (BASIS, 'positive_conflict', 'contradicted', 'explicit_scope_contradiction', 'conflict_verification'),
])
def test_fixed_relation_uses_actual_independent_proof_kind_not_producer_category(
        producer_basis, proof_kind, expected_value, expected_basis, verification):
    request, raw, data = fixed_sample(producer_basis)
    if proof_kind == 'positive_conflict':
        data['sources'][0]['text'] = 'The cited framework never proves termination [1].'
        data['citation_context']['text'] = data['sources'][0]['text']
        data['sources'][1]['text'] = 'Our framework proves termination for all programs.'
        for q, source in zip(raw['fields']['relation']['quotes'], data['sources']): q['quote'] = source['text']
    before = deepcopy((raw, data))
    packet = review.prepare_review(request, raw, data)
    assert packet['items'][0]['full_text_sources'][0]['source_id'] == 'external:body'
    answer = scope_answer(packet) if proof_kind == BASIS else conflict_answer(packet)
    proofs = review.accept_review(packet, answer)
    assert proofs
    facts, evidence = _ground_fields(request, raw, data, True, conflict_verifications=proofs)
    fact = facts['relation']
    assert fact['state'] == 'observed'
    assert fact['value'] == expected_value and fact['basis'] == expected_basis
    assert fact[verification]['kind'] == proof_kind
    assert set(fact['evidence_ids']) == {e['id'] for e in evidence}
    assert ('conflict_verification' if verification == 'support_verification' else 'support_verification') not in fact
    assert (raw, data) == before


@pytest.mark.parametrize('producer_basis', ['explicit_scope_contradiction', BASIS])
@pytest.mark.parametrize('change', [{'complete': False}, {'coverage': 'abstract'}])
def test_incomplete_sources_may_be_reviewed_but_cannot_mint_unsupported_proof(producer_basis, change):
    request, raw, data = fixed_sample(producer_basis)
    data['sources'][1].update(change)
    packet = review.prepare_review(request, raw, data)
    assert len(packet['items']) == 1
    assert packet['items'][0]['full_text_sources'] == []
    answer = scope_answer(packet)
    assert review.accept_review(packet, answer) == {}
    answer['results']['review-0']['full_text_source_ids'] = ['external:body']
    assert review.accept_review(packet, answer) == {}


def test_incomplete_work_can_establish_positive_conflict_within_producer_assertions():
    request, raw, data = fixed_sample(BASIS)
    data['sources'][1].update(complete=False, coverage='abstract')
    packet = review.prepare_review(request, raw, data)
    proofs = review.accept_review(packet, conflict_answer(packet))
    assert proofs
    fact = _ground_fields(request, raw, data, True, conflict_verifications=proofs)[0]['relation']
    assert fact['value'] == 'contradicted' and fact['basis'] == 'explicit_scope_contradiction'
    assert fact['conflict_verification']['kind'] == 'positive_conflict'


@pytest.mark.parametrize('producer_basis', ['explicit_scope_contradiction', BASIS])
def test_cross_kind_cannot_guess_arbitrary_generated_field_value(producer_basis):
    request, raw, data = fixed_sample(producer_basis)
    request['name'] = 'other_generated_capability'
    packet = review.prepare_review(request, raw, data)
    answer = scope_answer(packet) if producer_basis == 'explicit_scope_contradiction' else conflict_answer(packet)
    proofs = review.accept_review(packet, answer)
    assert proofs
    assert _ground_fields(request, raw, data, True, conflict_verifications=proofs)[0]['relation']['state'] == 'unknown'


def test_positive_review_cannot_expand_assertion_scope_even_if_producer_claimed_complete_work():
    request, raw, data = fixed_sample(BASIS)
    raw['fields']['relation']['quotes'][1]['quote'] = 'We present a configuration detection and remediation framework.'
    packet = review.prepare_review(request, raw, data)
    answer = conflict_answer(packet)
    spans = review.model_input(packet)['quote_spans']
    answer['results']['review-0']['witness']['cited']['quote_span_id'] = next(
        s['id'] for s in spans if s['source_id'] == 'external:body' and s['scope'] == 'full_source')
    assert review.accept_review(packet, answer) == {}


def test_negative_review_policy_versions_reject_old_fact_receipts():
    assert review.POLICY == 'positive-conflict-witness/2.3'
    assert review.COMPLETE_WORK_POLICY == 'complete-work-attribution-witness/2.3'


@pytest.mark.parametrize('producer_basis,proof_kind', [
    ('explicit_scope_contradiction', BASIS), (BASIS, 'positive_conflict')])
def test_fixed_program_uses_review_kind_and_replays_original_producer_binding(
        tmp_path, monkeypatch, producer_basis, proof_kind):
    from paper_compiler.fixed_r33 import build_r33_package
    from paper_compiler.pipeline import detect
    from test_paper_compiler_program_analysis import Model, Gateway, paper
    from test_paper_compiler_complete_work_support import answer_wire as scope_wire
    from test_paper_compiler_conflict_witness import answered_wire as conflict_wire
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE', '1')
    class ReviewedModel(Model):
        max_attempts = 1
        def __init__(self):
            super().__init__(); self.review_calls = 0
        def complete_json(self, task, instructions, data, max_tokens):
            if task == review.TASK:
                self.review_calls += 1
                return scope_wire(data) if proof_kind == BASIS else conflict_wire(data)
            if task == 'generated-analysis/2.0':
                self.semantic_calls += 1
                sources = [next(s for s in data['sources'] if s.get('node_id') == data['citation_context']['node_id']),
                           next(s for s in data['sources'] if s['origin'] == 'external')]
                return {'fields': {'relation': {'state': 'observed',
                    'value': 'contradicted' if producer_basis == 'explicit_scope_contradiction' else 'unsupported_attribution',
                    'basis': producer_basis, 'reason': 'The attributed property conflicts with the identified work scope.',
                    'quotes': [{'source_id': s['source_id'], 'quote': s['text']} for s in sources]}}}
            return super().complete_json(task, instructions, data, max_tokens)
    model = ReviewedModel(); ir = paper(tmp_path); package = build_r33_package(); cache = tmp_path/'cache'
    first_ir, analysis, report = detect(ir, [package], client=model, gateway=Gateway(), cache_dir=cache)
    fact = analysis['results']['fixed_citation_support_v1']['use']['relation']
    expected = 'unsupported_attribution' if proof_kind == BASIS else 'contradicted'
    assert fact['value'] == expected and report['rules'][0]['results'][0]['status'] == 'VIOLATION'
    for path in (cache/'program-analysis').glob('*.json'): path.unlink()
    second_ir, replay, second = detect(ir, [package], client=model, gateway=Gateway(), cache_dir=cache)
    assert replay['results']['fixed_citation_support_v1']['use']['relation'] == fact
    assert second_ir == first_ir and second['rules'] == report['rules']
    assert model.semantic_calls == 1 and model.review_calls == 1
