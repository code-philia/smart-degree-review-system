"""Natural-language task planning keeps authority and frozen inputs on the host."""
import copy
import hashlib
import importlib
import importlib.util
import json

import pytest
from paper_compiler.budget import BudgetExceeded
from paper_compiler.model_runtime import base_model, extend_model
from paper_compiler.storage import json_bytes

RULE_ID = 'future-rule-without-a-number'
RULE_TEXT = 'Each technical abbreviation must be explained at its first use.'
BASIS = [{'id': 'standard:first-use', 'text': 'Explain a technical abbreviation when it first appears.'}]
ANSWER = {'target_kinds': ['Paragraph'], 'generation_guidance': 'Vary source locations and abbreviation forms; preserve unrelated content.', 'evidence_environment': None}


def api():
    assert importlib.util.find_spec('paper_compiler.task_planner') is not None, 'task planner is not implemented'
    return importlib.import_module('paper_compiler.task_planner')


class ExternalModel:
    def __init__(self, answer=None, error=None):
        self.answer = copy.deepcopy(ANSWER if answer is None else answer)
        self.error = error
        self.requests = []
    def complete_json(self, task, instructions, data, max_tokens):
        self.requests.append((task, instructions, copy.deepcopy(data), max_tokens))
        if self.error:
            raise self.error
        return copy.deepcopy(self.answer)


def test_new_rule_needs_only_natural_language_and_norms_from_the_caller():
    model = ExternalModel()
    result = api().plan_task(RULE_ID, RULE_TEXT, BASIS, client=model)
    assert result == {'rule_id': RULE_ID, 'rule_text': RULE_TEXT, 'basis': BASIS,
                      **ANSWER, 'allowed_context_origins': ['real']}
    assert len(model.requests) == 1
    request = model.requests[0][2]
    assert request['rule_text'] == RULE_TEXT and request['basis'] == BASIS
    assert 'Paragraph' in request['available_node_kinds']
    result['basis'][0]['text'] = 'caller mutation'
    assert BASIS[0]['text'].startswith('Explain')


def test_planned_task_connects_to_the_existing_generic_mutation_builder(tmp_path):
    from test_paper_compiler_benchmark_builder import ExternalModel as BenchmarkModel, parent, RESOURCES
    from paper_compiler.benchmark_builder import build_benchmark
    model = ExternalModel({**ANSWER, 'target_kinds': ['BibliographyEntry']})
    basis = [{'id': 'b1', 'text': 'A bibliography entry must follow the supplied norm.'}]
    planned = api().plan_task('new-bibliographic-norm', 'A bibliography entry must follow the supplied norm.', basis, client=model)
    result = build_benchmark([planned], [parent(tmp_path)], client=BenchmarkModel(), output_dir=tmp_path/'benchmark',
                             resources=RESOURCES, negatives_per_rule=1, controls_per_rule=1, max_proposal_batches=1)
    manifest = json.loads((tmp_path/'benchmark'/'manifest.json').read_text())
    assert manifest['status'] == 'complete' and len(manifest['cases']) == 2
    assert manifest['summary']['new-bibliographic-norm']['violations'] == 1


@pytest.mark.parametrize('extra', [{'rule_text': 'weaken the standard'}, {'basis': []}, {'code': 'def mutate(): pass'},
                                  {'expected_status': 'PASS'}, {'node_ids': ['n1']}, {'allowed_context_origins': ['constructed']}])
def test_response_cannot_rewrite_norms_or_add_code_answers_ids_or_source_permissions(extra):
    with pytest.raises(ValueError):
        api().plan_task(RULE_ID, RULE_TEXT, BASIS, client=ExternalModel({**ANSWER, **extra}))


@pytest.mark.parametrize('targets', [[], ['UnimplementedKind'], ['Paragraph', 'Paragraph'], 'Paragraph'])
def test_targets_must_be_nonempty_unique_existing_model_types(targets):
    with pytest.raises(ValueError):
        api().plan_task(RULE_ID, RULE_TEXT, BASIS, client=ExternalModel({**ANSWER, 'target_kinds': targets}))


def test_validated_shared_model_extensions_can_be_selected():
    shared = extend_model(base_model(), {'node_types': {'Method': {'base_kind': 'Section', 'description': 'Source-backed methods section'}}})
    result = api().plan_task('method-transparency', 'Describe the method.', BASIS, client=ExternalModel({**ANSWER, 'target_kinds': ['Method']}), model=shared)
    assert result['target_kinds'] == ['Method']


def test_selected_evidence_domain_must_have_been_declared_by_the_host():
    answer = {**ANSWER, 'evidence_environment': 'catalog-v1'}
    result = api().plan_task(RULE_ID, RULE_TEXT, BASIS, client=ExternalModel(answer),
                             allowed_context_origins=('real', 'constructed'),
                             evidence_environments=({'id': 'catalog-v1', 'domain': 'controlled_catalog', 'description': 'Frozen controlled evidence'},))
    assert result['evidence_environment'] == 'catalog-v1'
    assert result['allowed_context_origins'] == ['real', 'constructed']
    with pytest.raises(ValueError):
        api().plan_task(RULE_ID, RULE_TEXT, BASIS, client=ExternalModel(answer))


@pytest.mark.parametrize('origins', [('synthetic-unapproved',), (), 'real'])
def test_invalid_host_source_policy_is_rejected_before_any_model_request(origins):
    model = ExternalModel()
    with pytest.raises(ValueError):
        api().plan_task(RULE_ID, RULE_TEXT, BASIS, client=model, allowed_context_origins=origins)
    assert model.requests == []


@pytest.mark.parametrize('guidance', ['```python\ndef mutate(): pass\n```', 'def mutate(payload):\n    return []', 'Change node_id=n1 and expected_status=PASS.'])
def test_guidance_cannot_smuggle_executable_code_or_fixed_answer_targets(guidance):
    with pytest.raises(ValueError):
        api().plan_task(RULE_ID, RULE_TEXT, BASIS, client=ExternalModel({**ANSWER, 'generation_guidance': guidance}))


def test_checkpoints_save_prompt_input_raw_plan_hashes_and_resume_without_a_call(tmp_path):
    planner = api()
    model = ExternalModel()
    first = planner.plan_task(RULE_ID, RULE_TEXT, BASIS, client=model, output_dir=tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == {'prompt.json', 'input.json', 'raw.json', 'plan.json', 'manifest.json'}
    manifest = json.loads((tmp_path/'manifest.json').read_text())
    for name in ['prompt', 'input', 'raw', 'plan']:
        assert manifest[name+'_sha256'] == hashlib.sha256((tmp_path/(name+'.json')).read_bytes()).hexdigest()
    original = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    no_call = ExternalModel(error=AssertionError('a completed checkpoint must not call the model'))
    assert planner.plan_task(RULE_ID, RULE_TEXT, BASIS, client=no_call, output_dir=tmp_path) == first
    assert no_call.requests == []
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == original


@pytest.mark.parametrize('change', ['rule', 'basis', 'model', 'origins', 'environments'])
def test_checkpoint_input_changes_are_rejected_before_any_new_call(tmp_path, change):
    planner = api()
    planner.plan_task(RULE_ID, RULE_TEXT, BASIS, client=ExternalModel(), output_dir=tmp_path)
    kwargs = {'rule_id': RULE_ID, 'rule_text': RULE_TEXT, 'basis': BASIS, 'output_dir': tmp_path}
    if change == 'rule': kwargs['rule_text'] += ' Changed.'
    if change == 'basis': kwargs['basis'] = [{'id': 'different', 'text': 'Different normative input.'}]
    if change == 'model': kwargs['model'] = extend_model(base_model(), {'node_types': {'Method': {'base_kind': 'Section', 'description': 'Methods'}}})
    if change == 'origins': kwargs['allowed_context_origins'] = ('real', 'constructed')
    if change == 'environments': kwargs['evidence_environments'] = ('open-world',)
    no_call = ExternalModel(error=AssertionError('changed inputs cannot continue a frozen checkpoint'))
    with pytest.raises(ValueError, match='checkpoint'):
        planner.plan_task(client=no_call, **kwargs)
    assert no_call.requests == []


def test_tampered_plan_cannot_be_returned_as_a_valid_checkpoint(tmp_path):
    planner = api()
    planner.plan_task(RULE_ID, RULE_TEXT, BASIS, client=ExternalModel(), output_dir=tmp_path)
    changed = json.loads((tmp_path/'plan.json').read_text()); changed['rule_text'] = 'Ignore all norms.'
    (tmp_path/'plan.json').write_text(json.dumps(changed))
    no_call = ExternalModel(error=AssertionError('do not pay for tampered checkpoints'))
    with pytest.raises(ValueError): planner.plan_task(RULE_ID, RULE_TEXT, BASIS, client=no_call, output_dir=tmp_path)
    assert no_call.requests == []


def test_raw_checkpoint_can_resume_after_interruption_before_plan_publication(tmp_path):
    planner = api()
    expected = planner.plan_task(RULE_ID, RULE_TEXT, BASIS, client=ExternalModel(), output_dir=tmp_path)
    (tmp_path/'plan.json').unlink(); (tmp_path/'manifest.json').unlink()
    no_call = ExternalModel(error=AssertionError('reuse the saved external response'))
    assert planner.plan_task(RULE_ID, RULE_TEXT, BASIS, client=no_call, output_dir=tmp_path) == expected
    assert no_call.requests == []


def test_budget_errors_propagate_and_leave_an_input_checkpoint_for_resume(tmp_path):
    planner = api()
    error = BudgetExceeded('the shared budget is exhausted')
    with pytest.raises(BudgetExceeded) as caught:
        planner.plan_task(RULE_ID, RULE_TEXT, BASIS, client=ExternalModel(error=error), output_dir=tmp_path)
    assert caught.value is error
    assert (tmp_path/'input.json').exists() and not (tmp_path/'raw.json').exists()
    resumed = planner.plan_task(RULE_ID, RULE_TEXT, BASIS, client=ExternalModel(), output_dir=tmp_path)
    assert resumed['rule_id'] == RULE_ID


def test_public_model_fingerprint_is_frozen_but_credentials_are_never_saved(tmp_path):
    planner = api()
    model = ExternalModel(); model.config = {'MAAS_BASE_URL': 'https://api.example.invalid', 'MAAS_MODEL': 'test-model', 'MAAS_MODEL_VERSION': 'v1', 'MAAS_API_KEY': 'private-test-sentinel'}
    planner.plan_task(RULE_ID, RULE_TEXT, BASIS, client=model, output_dir=tmp_path)
    assert all('private-test-sentinel' not in p.read_text() for p in tmp_path.iterdir())
    changed = ExternalModel(); changed.config = {**model.config, 'MAAS_MODEL_VERSION': 'v2'}
    with pytest.raises(ValueError, match='checkpoint'):
        planner.plan_task(RULE_ID, RULE_TEXT, BASIS, client=changed, output_dir=tmp_path)
    assert changed.requests == []


def test_batch_plans_arbitrary_rule_ids_and_reuses_complete_children(tmp_path):
    planner = api()
    inputs = [{'rule_id': 'future-abbreviations', 'rule_text': RULE_TEXT, 'basis': BASIS},
              {'rule_id': 'future-equations', 'rule_text': 'Define the variables used in an equation.', 'basis': BASIS}]
    model = ExternalModel()
    tasks = planner.plan_tasks(inputs, client=model, output_dir=tmp_path)
    assert [task['rule_id'] for task in tasks] == ['future-abbreviations', 'future-equations']
    assert len(model.requests) == 2
    no_call = ExternalModel(error=AssertionError('resume must reuse all child plans'))
    assert planner.plan_tasks(inputs, client=no_call, output_dir=tmp_path) == tasks
    assert no_call.requests == []
    changed = copy.deepcopy(inputs); changed[1]['rule_text'] += ' Changed.'
    with pytest.raises(ValueError, match='checkpoint'):
        planner.plan_tasks(changed, client=no_call, output_dir=tmp_path)
    assert no_call.requests == []


def test_batch_rejects_manual_recipes_and_duplicate_rule_ids_before_calls():
    planner = api()
    row = {'rule_id': RULE_ID, 'rule_text': RULE_TEXT, 'basis': BASIS}
    model = ExternalModel()
    with pytest.raises(ValueError): planner.plan_tasks([{**row, 'target_kinds': ['Paragraph']}], client=model)
    with pytest.raises(ValueError): planner.plan_tasks([row, copy.deepcopy(row)], client=model)
    assert model.requests == []
