import copy
import hashlib
import json
from pathlib import Path

import pytest

from paper_compiler.contracts import ContractError, validate_ir, serialize_ir, ir_hash, validate_analysis
from paper_compiler.storage import write_json_atomic


def paper(tmp_path):
    source = tmp_path / 'source.txt'
    source.write_text('Hello [1]', encoding='utf-8')
    return {
        'schema_version': 'paper-ir/1.0', 'model_version': 'paper-model/1.0',
        'document_id': 'doc-1', 'revision': 'original',
        'source_artifacts': [{'id': 'src', 'kind': 'text', 'path': str(source),
                              'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}],
        'root_id': 'root', 'profile': {'id': 'archive479-citations-v1'},
        'nodes': [
            {'id': 'root', 'kind': 'Paper', 'text': None, 'children': ['p'], 'attrs': {}, 'provenance': []},
            {'id': 'p', 'kind': 'Paragraph', 'text': 'Hello [1]', 'children': ['u'], 'attrs': {},
             'provenance': [{'kind': 'source', 'source_id': 'src', 'char_start': 0, 'char_end': 9}]},
            {'id': 'u', 'kind': 'ReferenceUse', 'text': '[1]', 'children': [],
             'attrs': {'namespace': 'bibliography', 'scope_id': 'root', 'expected_kind': 'BibliographyEntry',
                       'selector': {'kind': 'numeric', 'value': '1'}},
             'provenance': [{'kind': 'source', 'source_id': 'src', 'char_start': 6, 'char_end': 9}]},
        ],
        'coverage': {'bibliography': {'status': 'partial', 'reason': 'No verified bibliography coverage'}},
        'layout': {'pages': []}, 'metadata': {}, 'extensions': {},
    }


def analysis(ir):
    return {'schema_version': 'paper-analysis/1.0', 'model_version': ir['model_version'],
            'paper_ir_sha256': ir_hash(ir), 'capability_versions': {}, 'bindings': [],
            'entities': [], 'edges': [], 'evidence': [], 'results': {}, 'coverage': {}}


def test_dangling_reference_is_a_legal_paper_defect(tmp_path):
    ir = paper(tmp_path)
    validate_ir(ir, tmp_path)
    validate_analysis(ir, analysis(ir))


@pytest.mark.parametrize('change', [
    lambda x: x['nodes'].append(copy.deepcopy(x['nodes'][1])),
    lambda x: x['nodes'][2]['children'].append('root'),
    lambda x: x['nodes'][0]['children'].append('u'),
    lambda x: x['nodes'][0]['children'].clear(),
    lambda x: x['nodes'][0]['children'].append('missing'),
    lambda x: x['nodes'][0]['children'].append('p'),
    lambda x: x['nodes'][1].update(kind='CitationUse'),
    lambda x: x['nodes'][1].update(unrecognized=True),
    lambda x: x['nodes'][1]['attrs'].update(typo_field='lost'),
    lambda x: x['nodes'][2]['attrs'].update(scope_id='missing'),
    lambda x: x['nodes'][2]['attrs'].update(namespace=42),
    lambda x: x['nodes'][2]['attrs']['selector'].update(value=7),
    lambda x: x['nodes'][1].update(text=123),
    lambda x: x.update(schema_version='paper-ir-design/0.2'),
    lambda x: x.update(oracle={'expected': 'PASS'}),
    lambda x: x['extensions'].update(expected_diagnostics=[]),
    lambda x: x['nodes'][1]['provenance'][0].update(char_start=-1),
    lambda x: x['nodes'][1]['provenance'][0].update(char_end=100),
    lambda x: x['nodes'][1]['provenance'][0].update(source_id='absent'),
    lambda x: x['nodes'][1]['provenance'].clear(),
    lambda x: x['source_artifacts'][0].update(sha256='0'*64),
    lambda x: x['source_artifacts'][0].update(path='/does/not/exist'),
])
def test_rejects_broken_structure_source_or_contract(tmp_path, change):
    ir = paper(tmp_path)
    change(ir)
    with pytest.raises(ContractError):
        validate_ir(ir, tmp_path)


def test_canonical_serialization_and_source_change_invalidate_analysis(tmp_path):
    ir = paper(tmp_path)
    before = analysis(ir)
    reordered = {key: ir[key] for key in reversed(ir)}
    assert serialize_ir(reordered) == serialize_ir(ir)
    assert ir_hash(ir) == hashlib.sha256(serialize_ir(ir)).hexdigest()
    ir['nodes'][1]['text'] = 'Changed [1]'
    with pytest.raises(ContractError, match='stale'):
        validate_analysis(ir, before)


@pytest.mark.parametrize('change', [
    lambda a: a['bindings'].append({'use_id': 'u', 'status': 'resolved', 'target_ids': ['missing']}),
    lambda a: a['bindings'].append({'use_id': 'u', 'status': 'resolved', 'target_ids': ['p']}),
    lambda a: a['bindings'].append({'use_id': 'missing', 'status': 'unresolved', 'target_ids': []}),
    lambda a: a['edges'].append({'type': 'identifies', 'from': 'p', 'to': 'missing', 'evidence_ids': []}),
    lambda a: a['results'].update(oracle={'expected': 'PASS'}),
    lambda a: a.update(model_version='another-version'),
])
def test_rejects_invalid_derived_links_and_answer_leakage(tmp_path, change):
    ir = paper(tmp_path)
    a = analysis(ir)
    change(a)
    with pytest.raises(ContractError):
        validate_analysis(ir, a)


def test_unknown_observation_does_not_become_confirmed_absence(tmp_path):
    ir = paper(tmp_path)
    ir['nodes'][1]['attrs']['role'] = {'state': 'unknown', 'reason': 'Unclear'}
    validate_ir(ir, tmp_path)
    ir['nodes'][1]['attrs']['role'] = {'state': 'confirmed_absent'}
    with pytest.raises(ContractError, match='evidence|scope'):
        validate_ir(ir, tmp_path)


def test_pdf_span_must_fit_known_page_and_coordinate_system(tmp_path):
    ir = paper(tmp_path)
    ir['layout']['pages'] = [{'page_index': 0, 'width': 600, 'height': 800, 'rotation': 0,
                              'printed_page_label': None, 'lines': []}]
    ir['source_artifacts'][0]['page_count'] = 1
    ir['nodes'][1]['provenance'] = [{'kind': 'source', 'source_id': 'src', 'page_index': 0,
        'bbox': [10, 20, 60, 30], 'coordinate_system': 'unrotated_top_left_points'}]
    validate_ir(ir, tmp_path)
    ir['nodes'][1]['provenance'][0]['bbox'][2] = 700
    with pytest.raises(ContractError, match='bbox'):
        validate_ir(ir, tmp_path)


def test_synthetic_content_keeps_ancestor_location_without_claiming_source(tmp_path):
    ir = paper(tmp_path)
    ir['nodes'][1]['text'] = 'Mutated text'
    ir['nodes'][1]['provenance'] = [{'kind': 'synthetic', 'operation_id': 'operation-1',
        'ancestor_provenance': ir['nodes'][1]['provenance']}]
    validate_ir(ir, tmp_path)
    ir['nodes'][1]['provenance'][0].pop('operation_id')
    with pytest.raises(ContractError):
        validate_ir(ir, tmp_path)


def test_atomic_exclusive_output_cannot_overwrite_frozen_result(tmp_path):
    path = tmp_path / 'round' / 'report.json'
    write_json_atomic(path, {'result': 'first'}, exclusive=True)
    with pytest.raises(FileExistsError):
        write_json_atomic(path, {'result': 'changed'}, exclusive=True)
    assert json.loads(path.read_text()) == {'result': 'first'}
    assert len(list(path.parent.iterdir())) == 1
