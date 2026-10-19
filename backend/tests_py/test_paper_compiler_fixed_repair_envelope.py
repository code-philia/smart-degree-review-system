from copy import deepcopy

import pytest

from paper_compiler.study import _FixedAnalysisClient
from paper_compiler.synthesis import PROMPT_VERSION


class Client:
    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

    def complete_json(self, *args):
        self.calls += 1
        return deepcopy(self.answer)


def test_program_only_accepts_nested_repair_candidate_and_preserves_raw_checkpoint(tmp_path):
    original = {'requires': ['bibliography_fields'], 'analysis_requests': []}
    answer = {'repair_plan': [{'change': 'Fix checking code while retaining the analysis interface.'}],
              'candidate': {**original, 'rule_id': 'new-rule', 'code': 'actual source'}}
    client = Client(answer)
    fixed = _FixedAnalysisClient(client, original, tmp_path)
    first = fixed.complete_json(PROMPT_VERSION, 'instructions', {'input': 1}, 1000)
    assert first == answer
    assert fixed.complete_json(PROMPT_VERSION, 'instructions', {'input': 1}, 1000) == answer
    assert client.calls == 1


@pytest.mark.parametrize('envelope', [False, True])
def test_program_only_still_rejects_changed_analysis_contract(tmp_path, envelope):
    original = {'requires': ['bibliography_fields'], 'analysis_requests': []}
    candidate = {'requires': ['external_work'], 'analysis_requests': [], 'rule_id': 'new-rule'}
    answer = {'repair_plan': [], 'candidate': candidate} if envelope else candidate
    fixed = _FixedAnalysisClient(Client(answer), original, tmp_path)
    with pytest.raises(ValueError, match='fixed'):
        fixed.complete_json(PROMPT_VERSION, 'instructions', {'input': 1}, 1000)


def test_plain_fixed_contract_response_remains_compatible(tmp_path):
    original = {'requires': ['bibliography_fields'], 'analysis_requests': []}
    fixed = _FixedAnalysisClient(Client(original), original, tmp_path)
    assert fixed.complete_json(PROMPT_VERSION, 'instructions', {}, 1000) == original
