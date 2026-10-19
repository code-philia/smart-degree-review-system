import copy
import json

from paper_compiler.synthesis import synthesize_program
from test_paper_compiler_programs import candidate, CODE
from test_paper_compiler_repair_feedback import failure

TASK = {'rule_id': 'new-rule', 'rule_text': 'Check greeting',
        'basis': [{'id': 'test', 'text': 'Greeting is Hello.'}],
        'target_kinds': ['BibliographyEntry']}


class Client:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete_json(self, task, instructions, data, max_tokens):
        self.calls.append(copy.deepcopy(data))
        self.instructions = instructions
        return copy.deepcopy(self.response)


def test_repair_uses_diverse_feedback_and_retains_raw_decisions(tmp_path):
    raw = {'repair_plan': [{'failure_types': ['false_negative'], 'basis_ids': ['test'],
                           'change': 'Compare the source greeting value, rather than mere availability.'}],
           'candidate': candidate(CODE)}
    rows = [failure(i) for i in range(30)]
    rows.append(failure(30, expected='PASS', before='VIOLATION', after='VIOLATION',
                        types=['false_positive_original', 'false_positive_mutant']))
    client = Client(raw)
    package = synthesize_program(TASK, client, tmp_path, feedback=rows,
                                 repair_context={'attempt': 1, 'history': []})
    assert package['code'] == CODE
    data = client.calls[0]
    assert data['feedback_summary']['total_failures'] == 31
    assert len(data['feedback']) == 4
    assert data['feedback_summary']['selected_examples'] == 4
    assert data['feedback_summary']['omitted_examples'] == 27
    assert '30' in data['feedback_summary']['selected_ids']
    assert json.loads((tmp_path / 'synthesis-response.json').read_text()) == raw
    assert json.loads((tmp_path / 'repair-plan.json').read_text()) == raw['repair_plan']
    assert 'repair_plan' in client.instructions


def test_plain_candidate_remains_readable_but_no_plan_is_fabricated(tmp_path):
    synthesize_program(TASK, Client(candidate(CODE)), tmp_path, feedback=[failure(1)],
                       repair_context={'attempt': 1, 'history': []})
    assert not (tmp_path / 'repair-plan.json').exists()
