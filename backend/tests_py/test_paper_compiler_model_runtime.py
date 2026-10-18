"""Shared model definitions must preserve source facts and baseline IR safety."""
import copy
import hashlib
import importlib
import importlib.util
from pathlib import Path

import pytest

from paper_compiler.contracts import ContractError, ir_hash, validate_analysis, validate_ir


def runtime():
    assert importlib.util.find_spec('paper_compiler.model_runtime') is not None, 'shared model runtime is missing'
    return importlib.import_module('paper_compiler.model_runtime')


def patch():
    return {'node_types': {'Method': {'base_kind': 'Section',
            'description': 'A section describing the research method.',
            'attrs': {'confidence': 'number', 'reviewed': 'boolean', 'tags': 'array',
                      'details': 'object', 'summary': 'string'}}}}


def paper(tmp_path):
    text = '2 Method\nWe measure the sample [99].\n3 Results\nAccuracy is reported.'
    source = tmp_path / 'paper.txt'
    source.write_text(text, encoding='utf-8')
    def node(nid, kind, value=None, children=(), attrs=None):
        provenance = []
        if value is not None:
            start = text.index(value)
            provenance = [{'kind': 'source', 'source_id': 'text',
                           'char_start': start, 'char_end': start + len(value)}]
        return {'id': nid, 'kind': kind, 'text': value, 'children': list(children),
                'attrs': attrs or {}, 'provenance': provenance}
    return {'schema_version': 'paper-ir/1.0', 'model_version': 'paper-model/1.0',
            'document_id': 'paper', 'revision': 'original', 'root_id': 'root',
            'source_artifacts': [{'id': 'text', 'kind': 'text', 'path': str(source),
                                  'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}],
            'nodes': [node('root', 'Paper', children=['body', 'bibliography']),
                      node('body', 'Body', children=['method', 'results']),
                      node('method', 'Section', children=['heading', 'paragraph'],
                           attrs={'number': '2', 'level': 1, 'extensions': {'existing': True}}),
                      node('heading', 'Heading', '2 Method'),
                      node('paragraph', 'Paragraph', 'We measure the sample [99].', children=['use']),
                      node('use', 'ReferenceUse', '[99]', attrs={
                          'namespace': 'bibliography', 'expected_kind': 'BibliographyEntry',
                          'selector': {'kind': 'numeric', 'value': '99'}}),
                      node('results', 'Section', children=['result_heading', 'result_text']),
                      node('result_heading', 'Heading', '3 Results'),
                      node('result_text', 'Paragraph', 'Accuracy is reported.'),
                      node('bibliography', 'Bibliography', children=['entry']),
                      node('entry', 'BibliographyEntry')],
            'coverage': {}, 'profile': {}, 'layout': {'pages': []}, 'extensions': {'kept': True}}


def by_id(ir, nid):
    return next(n for n in ir['nodes'] if n['id'] == nid)


class Classifier:
    def __init__(self, classifications):
        self.answer = {'classifications': classifications}
        self.requests = []

    def complete_json(self, task, instructions, data, max_tokens):
        self.requests.append((task, instructions, copy.deepcopy(data), max_tokens))
        return copy.deepcopy(self.answer)


def test_base_model_applies_without_filling_missing_paper_facts(tmp_path):
    api = runtime()
    model = api.base_model()
    assert model == {'schema_version': 'paper-model-definition/1.0',
                     'base_version': 'paper-model/1.0', 'version': 'paper-model/1.0', 'node_types': {}}
    ir = paper(tmp_path)
    before = copy.deepcopy(ir)
    result = api.apply_model(ir, model)
    validate_ir(result, tmp_path)
    assert ir == before
    assert result['nodes'] == before['nodes']
    assert result['extensions'] == {'kept': True, 'paper_model': model}
    assert result['extensions']['paper_model'] is not model
    assert 'title' not in by_id(result, 'root')['attrs']
    assert by_id(result, 'entry')['attrs'] == {}
    assert by_id(result, 'use')['attrs']['selector']['value'] == '99'


def test_extensions_are_order_independent_versioned_and_do_not_mutate_inputs():
    api = runtime()
    base = api.base_model()
    change = patch()
    original = copy.deepcopy(change)
    extended = api.extend_model(base, change)
    reordered = copy.deepcopy(change)
    reordered['node_types']['Method']['attrs'] = dict(reversed(list(reordered['node_types']['Method']['attrs'].items())))
    assert api.extend_model(base, reordered) == extended
    assert extended['version'].startswith('paper-model/1.0+sha256:')
    assert len(extended['version'].rsplit(':', 1)[1]) == 64
    assert base['node_types'] == {} and change == original
    assert api.extend_model(extended, change) == extended
    api.validate_model(extended)
    extended['node_types']['Method']['description'] = 'Changed semantic contract.'
    with pytest.raises(ContractError, match='version|hash'):
        api.validate_model(extended)


def test_extensions_can_inherit_other_extensions_without_overwriting_them(tmp_path):
    api = runtime()
    model = api.extend_model(api.base_model(), patch())
    model = api.extend_model(model, {'node_types': {'Experiment': {
        'base_kind': 'Method', 'description': 'An experimental method.', 'attrs': {'replicates': 'number'}}}})
    result = api.apply_model(paper(tmp_path), model)
    node = by_id(result, 'method')
    node['kind'] = 'Experiment'
    node['attrs'].update(confidence=.9, replicates=3)
    validate_ir(result, tmp_path)
    node['attrs']['level'] = '1'
    with pytest.raises(ContractError, match='attribute'):
        validate_ir(result, tmp_path)


@pytest.mark.parametrize('bad', [
    {'node_types': {'Section': {'base_kind': 'Paragraph', 'description': 'Override', 'attrs': {}}}},
    {'node_types': {'Method': {'base_kind': 'Absent', 'description': 'Unknown base', 'attrs': {}}}},
    {'node_types': {'Method': {'base_kind': 'Method', 'description': 'Cycle', 'attrs': {}}}},
    {'node_types': {'Method': {'base_kind': 'Section', 'description': '', 'attrs': {}}}},
    {'node_types': {'Method': {'base_kind': 'Section', 'description': 'Bad type', 'attrs': {'score': 'integer'}}}},
    {'node_types': {'Method': {'base_kind': 'Section', 'description': 'Weakens type', 'attrs': {'level': 'string'}}}},
    {'node_types': {'Method': {'base_kind': 'Section', 'description': 'Leaks answer', 'attrs': {'expected': 'string'}}}},
    {'node_types': {'Method': None}},
    {'node_types': {}, 'remove': ['Section']},
])
def test_rejects_unsafe_model_patches(bad):
    api = runtime()
    with pytest.raises(ContractError):
        api.extend_model(api.base_model(), bad)


def test_compatible_revision_merges_attributes_and_updates_semantic_description(tmp_path):
    api = runtime()
    model = api.extend_model(api.base_model(), patch())
    original = copy.deepcopy(model)
    change = {'node_types': {'Method': {
        'description': 'A source section explaining the reproducible research method.',
        'attrs': {'instrument': 'string'}}}}
    revised = api.extend_model(model, change)
    assert model == original
    assert revised['node_types']['Method']['base_kind'] == 'Section'
    assert revised['node_types']['Method']['attrs'] == {
        'confidence': 'number', 'reviewed': 'boolean', 'tags': 'array',
        'details': 'object', 'summary': 'string', 'instrument': 'string'}
    assert revised['node_types']['Method']['description'] == change['node_types']['Method']['description']
    assert revised['version'] != model['version']
    assert api.extend_model(revised, change) == revised
    assert api.extend_model(revised, {'node_types': {'Method': {'attrs': {}}}}) == revised
    assert api.extend_model(revised, {'node_types': {'Method': {'attrs': {'instrument': 'string'}}}}) == revised
    api.validate_model(revised)
    ir = api.apply_model(paper(tmp_path), revised)
    by_id(ir, 'method')['kind'] = 'Method'
    by_id(ir, 'method')['attrs'].update(instrument='microscope', confidence=.95)
    validate_ir(ir, tmp_path)


@pytest.mark.parametrize('change', [
    {'base_kind': 'Paragraph'},
    {'attrs': {'summary': 'number'}},
    {'attrs': {'summary': None}},
    {'attrs': None},
    {'remove_attrs': ['summary']},
])
def test_incompatible_extension_revisions_cannot_change_bases_or_attribute_types(change):
    api = runtime()
    model = api.extend_model(api.base_model(), patch())
    with pytest.raises(ContractError):
        api.extend_model(model, {'node_types': {'Method': change}})


def test_parent_revision_adds_inherited_attributes_to_existing_subtypes(tmp_path):
    api = runtime()
    model = api.extend_model(api.base_model(), patch())
    model = api.extend_model(model, {'node_types': {'Experiment': {
        'base_kind': 'Method', 'description': 'An experimental method.', 'attrs': {'replicates': 'number'}}}})
    revised = api.extend_model(model, {'node_types': {'Method': {'attrs': {'instrument': 'string'}}}})
    assert revised['node_types']['Experiment'] == model['node_types']['Experiment']
    ir = api.apply_model(paper(tmp_path), revised)
    by_id(ir, 'method')['kind'] = 'Experiment'
    by_id(ir, 'method')['attrs'].update(instrument='microscope', confidence=.95, replicates=3)
    validate_ir(ir, tmp_path)


def test_model_applies_without_client_and_preserves_source_bytes(tmp_path):
    api = runtime()
    ir = paper(tmp_path)
    source = Path(ir['source_artifacts'][0]['path'])
    before = source.read_bytes()
    model = api.extend_model(api.base_model(), patch())
    result = api.apply_model(ir, model)
    assert result['model_version'] == model['version']
    assert result['nodes'] == ir['nodes']
    assert source.read_bytes() == before
    validate_ir(result, tmp_path)


def test_source_backed_section_classification_preserves_structure_and_provenance(tmp_path):
    api = runtime()
    ir = paper(tmp_path)
    before = copy.deepcopy(ir)
    model = api.extend_model(api.base_model(), patch())
    client = Classifier([{'node_id': 'method', 'kind': 'Method', 'quote': 'We measure the sample'}])
    result = api.apply_model(ir, model, client=client)
    classified = by_id(result, 'method')
    assert classified['kind'] == 'Method'
    assert classified['children'] == by_id(ir, 'method')['children']
    assert classified['provenance'] == by_id(ir, 'method')['provenance']
    assert classified['attrs']['number'] == '2' and classified['attrs']['level'] == 1
    assert classified['attrs']['extensions']['existing'] is True
    evidence = classified['attrs']['extensions']['paper_model_classification']
    assert evidence['quote'] == 'We measure the sample' and evidence['evidence_node_id'] == 'paragraph'
    assert ir == before
    assert by_id(result, 'results')['kind'] == 'Section'
    task, instructions, data, max_tokens = client.requests[0]
    assert task == 'paper-model-classification/1.0' and instructions and max_tokens > 0
    assert 'We measure the sample' in str(data) and '2 Method' in str(data)
    validate_ir(result, tmp_path)


@pytest.mark.parametrize('classification', [
    {'node_id': 'method', 'kind': 'Method', 'quote': 'Invented method words'},
    {'node_id': 'method', 'kind': 'Method', 'quote': 'Accuracy is reported.'},
    {'node_id': 'method', 'kind': 'Method', 'quote': ''},
    {'node_id': 'method', 'kind': 'Method', 'quote': 'we measure the sample'},
    {'node_id': 'paragraph', 'kind': 'Method', 'quote': 'We measure the sample'},
    {'node_id': 'missing', 'kind': 'Method', 'quote': 'We measure the sample'},
    {'node_id': 'method', 'kind': 'Unsupported', 'quote': 'We measure the sample'},
    {'node_id': 'method', 'kind': 'Claim', 'quote': 'We measure the sample'},
    None,
])
def test_rejects_unverified_or_incompatible_classifications(tmp_path, classification):
    api = runtime()
    change = patch()
    change['node_types']['Claim'] = {'base_kind': 'Paragraph', 'description': 'A claim.', 'attrs': {}}
    model = api.extend_model(api.base_model(), change)
    ir = paper(tmp_path)
    result = api.apply_model(ir, model, client=Classifier([classification]))
    assert result['nodes'] == ir['nodes']


def test_synthetic_text_is_not_misrepresented_as_an_original_source_quote(tmp_path):
    api = runtime()
    ir = paper(tmp_path)
    paragraph = by_id(ir, 'paragraph')
    paragraph['provenance'] = [{'kind': 'synthetic', 'operation_id': 'op1',
                                'ancestor_provenance': paragraph['provenance']}]
    model = api.extend_model(api.base_model(), patch())
    result = api.apply_model(ir, model, client=Classifier([
        {'node_id': 'method', 'kind': 'Method', 'quote': 'We measure the sample'}]))
    assert by_id(result, 'method')['kind'] == 'Section'


@pytest.mark.parametrize('change', [
    lambda ir: ir.update(model_version='paper-model/1.0+sha256:' + '0' * 64),
    lambda ir: ir['extensions']['paper_model']['node_types']['Method'].update(description='Tampered'),
    lambda ir: ir['extensions'].pop('paper_model'),
    lambda ir: by_id(ir, 'method')['attrs'].update(level=True),
    lambda ir: by_id(ir, 'method')['attrs'].update(confidence=True),
    lambda ir: by_id(ir, 'method')['attrs'].update(confidence=float('nan')),
    lambda ir: by_id(ir, 'method')['attrs'].update(summary=7),
    lambda ir: by_id(ir, 'method')['attrs'].update(unknown=7),
    lambda ir: by_id(ir, 'paragraph')['provenance'].clear(),
    lambda ir: by_id(ir, 'paragraph')['provenance'][0].update(char_end=9999),
    lambda ir: by_id(ir, 'method')['children'].append('missing'),
    lambda ir: ir['extensions'].update(expected_status='PASS'),
])
def test_extended_ir_keeps_baseline_version_type_source_structure_and_leakage_checks(tmp_path, change):
    api = runtime()
    model = api.extend_model(api.base_model(), patch())
    ir = api.apply_model(paper(tmp_path), model)
    by_id(ir, 'method')['kind'] = 'Method'
    change(ir)
    with pytest.raises(ContractError):
        validate_ir(ir, tmp_path)


def test_invalid_base_ir_is_not_repaired_or_sent_to_classifier(tmp_path):
    api = runtime()
    ir = paper(tmp_path)
    by_id(ir, 'method')['children'].append('missing')
    client = Classifier([])
    with pytest.raises(ContractError):
        api.apply_model(ir, api.extend_model(api.base_model(), patch()), client=client)
    assert client.requests == []


def analysis(ir):
    return {'schema_version': 'paper-analysis/1.0', 'model_version': ir['model_version'],
            'paper_ir_sha256': ir_hash(ir), 'capability_versions': {}, 'results': {},
            'coverage': {}, 'bindings': [], 'edges': [], 'entities': [], 'evidence': []}


def test_analysis_accepts_inherited_and_extended_attributes(tmp_path):
    api = runtime()
    ir = api.apply_model(paper(tmp_path), api.extend_model(api.base_model(), patch()))
    by_id(ir, 'method')['kind'] = 'Method'
    result = analysis(ir)
    result['node_attributes'] = {'method': {
        'level': {'state': 'observed', 'value': 1, 'evidence_ids': ['heading']},
        'confidence': {'state': 'observed', 'value': .9, 'evidence_ids': ['paragraph']}}}
    validate_analysis(ir, result)


@pytest.mark.parametrize('value', [True, float('nan')])
def test_analysis_extension_numbers_are_finite_and_not_booleans(tmp_path, value):
    api = runtime()
    ir = api.apply_model(paper(tmp_path), api.extend_model(api.base_model(), patch()))
    by_id(ir, 'method')['kind'] = 'Method'
    result = analysis(ir)
    result['node_attributes'] = {'method': {'confidence': {
        'state': 'observed', 'value': value, 'evidence_ids': ['paragraph']}}}
    with pytest.raises(ContractError, match='resolved attribute type mismatch'):
        validate_analysis(ir, result)


def test_analysis_reference_edges_accept_source_backed_section_subtypes(tmp_path):
    api = runtime()
    ir = api.apply_model(paper(tmp_path), api.extend_model(api.base_model(), patch()))
    by_id(ir, 'method')['kind'] = 'Method'
    result = analysis(ir)
    result['edges'] = [{'type': 'refers_to', 'from': 'use', 'to': 'method', 'evidence_ids': []}]
    validate_analysis(ir, result)


def test_analysis_bindings_honor_reference_and_bibliography_subtypes(tmp_path):
    api = runtime()
    model = api.extend_model(api.base_model(), {'node_types': {
        'CitationCall': {'base_kind': 'ReferenceUse', 'description': 'A citation call.', 'attrs': {}},
        'SourceRecord': {'base_kind': 'BibliographyEntry', 'description': 'A source record.', 'attrs': {}}}})
    ir = api.apply_model(paper(tmp_path), model)
    by_id(ir, 'use')['kind'] = 'CitationCall'
    by_id(ir, 'entry')['kind'] = 'SourceRecord'
    validate_ir(ir, tmp_path)
    result = analysis(ir)
    result['bindings'] = [{'use_id': 'use', 'status': 'resolved', 'target_ids': ['entry']}]
    validate_analysis(ir, result)
    by_id(ir, 'use')['attrs']['expected_kind'] = 'Paragraph'
    result['paper_ir_sha256'] = ir_hash(ir)
    with pytest.raises(ContractError, match='binding target type mismatch'):
        validate_analysis(ir, result)


def test_exact_multiline_quote_can_span_consecutive_source_lines(tmp_path):
    api = runtime()
    ir = paper(tmp_path)
    source = Path(ir['source_artifacts'][0]['path'])
    source.write_text(source.read_text().replace('We measure the sample', 'We measure\nthe sample'), encoding='utf-8')
    ir['source_artifacts'][0]['sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    node = by_id(ir, 'paragraph')
    node['text'] = 'We measure\nthe sample [99].'
    start = node['provenance'][0]['char_start']
    node['provenance'] = [
        {'kind': 'source', 'source_id': 'text', 'char_start': start, 'char_end': start + 10,
         'node_text_start': 0, 'node_text_end': 10},
        {'kind': 'source', 'source_id': 'text', 'char_start': start + 11, 'char_end': start + len(node['text']),
         'node_text_start': 11, 'node_text_end': len(node['text'])}]
    model = api.extend_model(api.base_model(), patch())
    result = api.apply_model(ir, model, client=Classifier([
        {'node_id': 'method', 'kind': 'Method', 'quote': 'We measure\nthe sample'}]))
    assert by_id(result, 'method')['kind'] == 'Method'
    assert by_id(result, 'paragraph')['provenance'] == node['provenance']
    validate_ir(result, tmp_path)
