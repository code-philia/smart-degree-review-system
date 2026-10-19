"""Generator-facing capability namespace regression; synthetic rules and fake API only."""
from copy import deepcopy

import pytest

from paper_compiler.registry import REGISTRY
from paper_compiler.synthesis import synthesize_program


@pytest.mark.parametrize('proposed_name', ['citation_relevance', 'bibliography_fields'])
def test_generator_can_avoid_all_reserved_capability_names(tmp_path, proposed_name):
    class NamespaceAwareClient:
        def complete_json(self, task, instructions, data, max_tokens):
            self.data, self.instructions = deepcopy(data), instructions
            reserved = data.get('reserved_analysis_names', [])
            name = proposed_name if proposed_name not in reserved else 'quoted_assertion'
            return {
                'rule_id': data['requested_rule_id'], 'title': 'Synthetic local assertion',
                'requires': [name], 'target_kinds': ['Paragraph'],
                'analysis_requests': [{
                    'name': name, 'targets': ['Paragraph'], 'fields': {'asserted': 'boolean'},
                    'instructions': 'Extract whether an assertion is explicitly present; quote the exact paragraph.'}],
                'model_patch': {},
                'code': "def detect(payload):\n    return []\n",
            }

    client = NamespaceAwareClient()
    package = synthesize_program({
        'rule_id': 'synthetic-namespace', 'rule_text': 'Check explicit local assertions.',
        'basis': [], 'target_kinds': ['Paragraph']}, client, tmp_path)
    assert package['program_spec']['analysis_requests'][0]['name'] == 'quoted_assertion'
    assert package['program_spec']['requires'] == ['quoted_assertion']
    assert client.data['reserved_analysis_names'] == sorted(REGISTRY['capabilities'])
    assert 'citation_relevance' not in client.data['analysis_registry']
    assert 'reserved_analysis_names' in client.instructions
    assert 'requires' in client.instructions


def test_advertised_builtin_remains_available_without_generated_redefinition(tmp_path):
    class BuiltinClient:
        def complete_json(self, task, instructions, data, max_tokens):
            assert 'bibliography_fields' in data['analysis_registry']
            assert 'bibliography_fields' in data.get('reserved_analysis_names', [])
            return {
                'rule_id': data['requested_rule_id'], 'title': 'Synthetic title check',
                'requires': ['bibliography_fields'], 'target_kinds': ['BibliographyEntry'],
                'analysis_requests': [], 'model_patch': {},
                'code': "def detect(payload):\n    return []\n",
            }
    package = synthesize_program({'rule_id': 'synthetic-builtin', 'rule_text': 'Check the title.',
        'basis': [], 'target_kinds': ['BibliographyEntry']}, BuiltinClient(), tmp_path)
    assert package['program_spec']['requires'] == ['bibliography_fields']
