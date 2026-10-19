import copy

import pytest

import paper_compiler.analysis as shared
from paper_compiler.model_runtime import base_model
from paper_compiler.program_analysis import analyze_programs
from paper_compiler.registry import REGISTRY
from test_paper_compiler_program_analysis import paper, Model


@pytest.mark.parametrize('batch_size', ['1', '8'])
def test_extraction_policy_invalidates_derived_analysis_without_changing_model_input(tmp_path, monkeypatch, batch_size):
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE', batch_size)
    ir = paper(tmp_path)
    package = {'program_spec': {'requires': ['bibliography_fields'], 'analysis_requests': []},
               'registry': copy.deepcopy(REGISTRY), 'model': base_model(),
               'manifest': {'version_id': 'fixture-generation'}}
    client = Model()
    kwargs = dict(client=client, gateway=None, cache_dir=tmp_path / 'cache', snapshot_id='fixed')
    old = analyze_programs(ir, [package], **kwargs)
    assert old['policy']['bibliography_extraction'] == shared.BIBLIOGRAPHY_EXTRACTION_POLICY
    first_request = copy.deepcopy(client.requests[0])
    monkeypatch.setattr(shared, 'BIBLIOGRAPHY_EXTRACTION_POLICY', 'test-new-transcription-policy')
    new = analyze_programs(ir, [package], **kwargs)
    assert new['policy']['bibliography_extraction'] == 'test-new-transcription-policy'
    assert len(list((tmp_path / 'cache/program-analysis').glob('*.json'))) == 2
    # A MaasClient sees precisely the same task/instructions/data and can reuse
    # its successful response cache; only source interpretation changed.
    assert len(client.requests) == 2
    assert client.requests[1] == first_request
