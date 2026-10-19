"""Complete-work attribution is separate from positive contradiction evidence."""
from copy import deepcopy
import json
import pytest
from paper_compiler import conflict_review as review
from paper_compiler.program_analysis import _ground_fields, analyze_programs
from test_paper_compiler_program_analysis import Model, Gateway, paper, package, grounded_reference

BASIS = 'complete_work_unsupported_attribution'
def sample():
    citing = 'This cited framework proves termination for all programs [1].'
    body = 'We present a configuration detection and remediation framework. Our contributions are a detector and a remediation pipeline.'
    data = {'node': {'id': 'use'}, 'citation_context': {'node_id': 'p', 'text': citing},
        'external_works': [{'id': 'work'}], 'sources': [
            {'source_id': 'paper:p', 'origin': 'paper', 'node_id': 'p', 'text': citing, 'complete': True},
            {'source_id': 'external:body', 'origin': 'external', 'work_id': 'work', 'content_id': 'body',
             'text': body, 'complete': True, 'coverage': 'full_text'}]}
    raw = {'fields': {'relation': {'state': 'observed', 'value': 'unsupported_attribution', 'basis': BASIS,
        'reason': 'The attributed theorem is outside the identified work contribution and method scope.',
        'quotes': [{'source_id': 'paper:p', 'quote': citing}, {'source_id': 'external:body', 'quote': body}]}}}
    return {'fields': {'relation': 'string'}}, raw, data

def answer_wire(data):
    results = {}
    for node in data['nodes']:
        citing = next(a for a in node['assertions'] if a['origin'] == 'paper')
        cited = next(a for a in node['assertions'] if a['origin'] == 'external')
        results[node['node']['id']] = {'decision': 'confirmed_unsupported_attribution',
            'same_entity': True, 'same_property': True, 'same_scope': True,
            'citation_purpose': 'assertion', 'attribution_kind': 'contribution',
            'relation': BASIS, 'reason': 'The asserted theorem is attributed as a contribution, while the complete work establishes its contribution as configuration detection and remediation.',
            'full_text_source_ids': [s['source_id'] for s in data['sources'] if s['origin'] == 'external' and s.get('complete') is True and s.get('coverage') == 'full_text'], 'witness': {
                'citing': {'quote_span_id': citing['assertion_span_ids'][0],
                    'entity': 'identified work', 'property': 'contribution', 'scope': 'this work', 'value': 'termination proof'},
                'cited': {'quote_span_id': cited['assertion_span_ids'][0],
                    'entity': 'identified work', 'property': 'contribution', 'scope': 'this work', 'value': 'configuration detection and remediation'}}}
    return {'results': results}

def answer(packet):
    return answer_wire(review.model_input(packet))

def test_complete_work_non_support_requires_independent_host_proof():
    request, raw, data = sample(); before = deepcopy((raw, data))
    assert _ground_fields(request, raw, data, True)[0]['relation']['state'] == 'unknown'
    packet = review.prepare_review(request, raw, data)
    assert len(packet['items']) == 1
    proofs = review.accept_review(packet, answer(packet))
    fact = _ground_fields(request, raw, data, True, conflict_verifications=proofs)[0]['relation']
    assert fact['state'] == 'observed' and fact['value'] == 'unsupported_attribution'
    verified = fact['support_verification']
    assert verified['kind'] == BASIS
    assert verified['witness']['full_text_sources'][0]['source_id'] == 'external:body'
    assert verified['witness']['full_text_sources'][0]['source_sha256']
    assert (raw, data) == before

@pytest.mark.parametrize('change', [{'complete': False}, {'coverage': 'abstract'}, {'work_id': 'foreign'}])
def test_incomplete_or_foreign_work_never_enters_complete_scope_review(change):
    request, raw, data = sample(); data['sources'][1].update(change)
    assert review.prepare_review(request, raw, data)['items'] == []

@pytest.mark.parametrize('change', [
    {'decision': 'insufficient'}, {'decision': 'supported_nonconflict'},
    {'citation_purpose': 'background'}, {'citation_purpose': 'criticism'},
    {'citation_purpose': 'comparison'}, {'citation_purpose': 'transfer'},
    {'attribution_kind': 'author_new_proposal'}, {'full_text_source_ids': []},
    {'full_text_source_ids': ['external:foreign']}, {'same_entity': False}])
def test_missing_support_or_legitimate_citation_purpose_cannot_mint_proof(change):
    request, raw, data = sample(); packet = review.prepare_review(request, raw, data)
    assert packet['items']
    result = answer(packet); next(iter(result['results'].values())).update(change)
    assert not review.accept_review(packet, result)

def test_review_receives_complete_body_without_producer_conclusion_or_private_reason():
    request, raw, data = sample(); raw['fields']['relation']['reason'] = 'PRIVATE_PRODUCER_CONCLUSION'
    packet = review.prepare_review(request, raw, data); wire = review.model_input(packet)
    assert ''.join(s['text'] for s in wire['quote_spans'] if s['source_id'] == 'external:body' and s['scope'] == 'full_source') == data['sources'][1]['text']
    assert 'PRIVATE_PRODUCER_CONCLUSION' not in json.dumps(wire)
    assert 'unsupported_attribution' not in json.dumps(wire)

def test_changed_complete_body_invalidates_prior_scope_proof():
    request, raw, data = sample(); packet = review.prepare_review(request, raw, data)
    assert packet['items']
    proofs = review.accept_review(packet, answer(packet))
    data['sources'][1]['text'] += ' Extra substantive body.'
    assert _ground_fields(request, raw, data, True, conflict_verifications=proofs)[0]['relation']['state'] == 'unknown'

class ThinkingModel(Model):
    max_attempts = 1
    def __init__(self):
        super().__init__(grounded_reference); self.semantic_thinking = False; self.limits = []
    def complete_json(self, task, instructions, data, max_tokens):
        if task == 'generated-analysis/2.0': self.limits.append(max_tokens)
        return super().complete_json(task, instructions, data, max_tokens)

def test_semantic_thinking_changes_fact_policy_and_does_not_reuse_old_analysis(tmp_path):
    model = ThinkingModel(); ir = paper(tmp_path); pkg = package('ReferenceUse', {'related': 'boolean'})
    first = analyze_programs(ir, [pkg], client=model, gateway=Gateway(), cache_dir=tmp_path/'cache')
    assert 'semantic_thinking' not in first['policy'] and model.limits == [3000]
    model.semantic_thinking = True
    second = analyze_programs(ir, [pkg], client=model, gateway=Gateway(), cache_dir=tmp_path/'cache')
    assert second['policy']['semantic_thinking'] is True and model.semantic_calls == 2
    assert model.limits[-1] >= 6000

class ScopeReviewer:
    max_attempts = 1
    semantic_thinking = True
    def __init__(self): self.calls = []; self.token_limits = []
    def complete_json(self, task, instructions, data, max_tokens):
        self.calls.append(deepcopy(data)); self.token_limits.append(max_tokens)
        return answer_wire(data)

def test_complete_scope_review_uses_semantic_cap_and_receipt_binds_flag():
    request, raw, data = sample(); client = ScopeReviewer()
    proofs, receipt, reason = review.resolve_review(request, raw, data, client=client)
    assert proofs and reason is None and client.token_limits[0] >= 6000
    client.semantic_thinking = False
    review.resolve_review(request, raw, data, client=client, receipt=receipt)
    assert len(client.calls) == 2


def test_fixed_r33_emits_only_independently_verified_complete_work_attribution(tmp_path, monkeypatch):
    from paper_compiler.fixed_r33 import build_r33_package
    from paper_compiler.pipeline import detect
    from paper_compiler.conflict_review import TASK
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE', '1')
    class CompleteSemantic(Model):
        max_attempts = 1
        semantic_thinking = True
        def __init__(self): super().__init__(); self.reviews = 0
        def complete_json(self, task, instructions, data, max_tokens):
            if task == TASK:
                self.reviews += 1
                return answer_wire(data)
            if task == 'generated-analysis/2.0':
                paper_source = next(s for s in data['sources'] if s.get('node_id') == data['citation_context']['node_id'])
                ext = next(s for s in data['sources'] if s['origin'] == 'external')
                return {'fields': {'relation': {'state': 'observed', 'value': 'unsupported_attribution', 'basis': BASIS,
                    'reason': 'The attributed result is outside this identified work contribution scope.', 'quotes': [
                        {'source_id': paper_source['source_id'], 'quote': paper_source['text']},
                        {'source_id': ext['source_id'], 'quote': ext['text']}]}}}
            return super().complete_json(task, instructions, data, max_tokens)
    client = CompleteSemantic(); ir = paper(tmp_path)
    _, analysis, report = detect(ir, [build_r33_package()], client=client, gateway=Gateway(), cache_dir=tmp_path/'cache')
    assert client.reviews == 1
    assert report['rules'][0]['results'][0]['status'] == 'VIOLATION'
    fact = analysis['results']['fixed_citation_support_v1']['use']['relation']
    assert fact['support_verification']['kind'] == BASIS
    for f in (tmp_path/'cache/program-analysis').glob('*.json'): f.unlink()
    detect(ir, [build_r33_package()], client=client, gateway=Gateway(), cache_dir=tmp_path/'cache')
    assert client.reviews == 1


def test_review_output_alias_is_short_explicit_and_strictly_bound():
    request, raw, data = sample(); packet = review.prepare_review(request, raw, data)
    wire = review.model_input(packet)
    assert wire['nodes'][0]['node']['id'] == 'review-0'
    row = next(iter(answer(packet)['results'].values()))
    assert review.accept_review(packet, {'results': {'review-0': row}})
    assert not review.accept_review(packet, {'results': {'p': row}})
    assert not review.accept_review(packet, {'results': {packet['items'][0]['id']: row}})


def test_review_exact_span_pool_preserves_complete_source_and_hash():
    request, raw, data = sample(); data['sources'][1]['text'] += ' Detail.' * 400
    packet = review.prepare_review(request, raw, data); wire = review.model_input(packet)
    assert 'quote_spans' in wire
    assert 'text' not in wire['sources'][1]
    text = ''.join(s['text'] for s in wire['quote_spans'] if s['source_id'] == 'external:body' and s['scope'] == 'full_source')
    assert text == data['sources'][1]['text']
    assert wire['sources'][1]['complete'] is True and wire['sources'][1]['coverage'] == 'full_text'
    assert wire['sources'][1]['source_sha256']
    assert all(len(s['text']) <= 1000 for s in wire['quote_spans'])

def test_review_only_copies_explicit_valid_span_ids_without_mutating_answer():
    request, raw, data = sample(); packet = review.prepare_review(request, raw, data)
    result = answer(packet); row = next(iter(result['results'].values()))
    assert 'quote_span_id' in row['witness']['citing']
    before = deepcopy(result); assert review.accept_review(packet, result); assert result == before
    row['witness']['cited']['quote_span_id'] = 'not-provided'
    assert not review.accept_review(packet, result)
    row['witness']['cited']['quote_span_id'] = row['witness']['citing']['quote_span_id']
    assert not review.accept_review(packet, result)


def test_only_complete_work_review_may_select_scope_outside_producer_assertion():
    request, raw, data = sample()
    raw['fields']['relation']['quotes'][1]['quote'] = 'We present a configuration detection and remediation framework.'
    packet = review.prepare_review(request, raw, data); wire = review.model_input(packet)
    result = answer(packet); row = next(iter(result['results'].values()))
    full = next(s for s in wire['quote_spans'] if s['source_id'] == 'external:body' and s['scope'] == 'full_source')
    row['witness']['cited']['quote_span_id'] = full['id']
    assert review.accept_review(packet, result)
    raw['fields']['relation']['basis'] = 'explicit_scope_contradiction'
    packet = review.prepare_review(request, raw, data); wire = review.model_input(packet)
    row.update(decision='confirmed_conflict', relation='mutually_exclusive_values')
    row['witness']['cited']['quote_span_id'] = next(s['id'] for s in wire['quote_spans'] if s['source_id'] == 'external:body' and s['scope'] == 'full_source')
    assert not review.accept_review(packet, result)
