"""The real synthesis request discloses the existing private-name boundary."""
from paper_compiler.synthesis import synthesize_program


def test_synthesis_prompt_discloses_throwaway_loop_and_comprehension_name_contract(tmp_path):
    class CapturingClient:
        def complete_json(self, task, instructions, data, max_tokens):
            self.instructions = instructions
            return {'rule_id': data['requested_rule_id'], 'title': 'Synthetic local contract',
                    'requires': [], 'target_kinds': ['Paragraph'], 'analysis_requests': [],
                    'model_patch': {}, 'code': 'def detect(payload):\n    return []\n'}
    client = CapturingClient()
    synthesize_program({'rule_id': 'synthetic-private-name-contract',
                        'rule_text': 'Check a local source property.', 'basis': []}, client, tmp_path)
    assert "Variable names must never start with '_'" in client.instructions
    assert 'throwaway comprehension or loop targets' in client.instructions
    assert 'use public names such as unused instead' in client.instructions
