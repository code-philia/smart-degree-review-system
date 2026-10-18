"""Fair joint/program-only study with shared initial candidates and deferred heldout evaluation."""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from .budget import BudgetExceeded
from .contracts import ir_hash, reject_answers, validate_ir
from .feedback_loop import evaluate_cases, run_feedback_loop, _metrics
from .model_runtime import base_model, extend_model, validate_model
from .pipeline import rebind, save_suite, shared_model
from .programs import build_program, digest, load_program, save_program
from .storage import json_bytes, write_json_atomic
from .synthesis import PROMPT_VERSION, synthesize_program

VERSION = 'paper-study/1.0'
CONDITIONS = ('joint', 'program_only')


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _immutable(path, value):
    path = Path(path)
    if path.exists():
        if path.read_bytes() != json_bytes(value):
            raise ValueError('frozen study artifact changed: ' + str(path))
    else:
        write_json_atomic(path, value, exclusive=True)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _manifest(path, tasks):
    path = Path(path).resolve()
    value = _read(path)
    if value.get('schema_version') != 'paper-benchmark/2.0' or value.get('status') != 'complete':
        raise ValueError('study requires a complete frozen benchmark')
    if not isinstance(value.get('artifact_sha256'), dict) or not value['artifact_sha256']:
        raise ValueError('frozen benchmark artifact hashes are required')
    hashes = {}
    for name, expected in value['artifact_sha256'].items():
        source = Path(name)
        source = source if source.is_absolute() else path.parent / source
        if not source.is_file() or _sha(source) != expected:
            raise ValueError('frozen artifact integrity/hash mismatch: ' + str(source))
        hashes[str(source.resolve())] = expected
    ids, group_splits, source_splits = set(), {}, {}
    rule_ids = {task['rule_id'] for task in tasks}
    splits = defaultdict(set)
    normalized = deepcopy(value)
    if not isinstance(normalized.get('cases'), list) or not normalized['cases']:
        raise ValueError('frozen benchmark cases required')
    for case in normalized['cases']:
        rid, split, group = str(case.get('rule_id')), case.get('split'), case.get('parent_group')
        if case.get('id') in ids or not isinstance(case.get('id'), str) or not case['id']:
            raise ValueError('duplicate/invalid frozen case ID')
        ids.add(case['id'])
        if rid not in rule_ids or split not in {'feedback', 'validation', 'test'} or not isinstance(group, str) or not group:
            raise ValueError('invalid study task/split/parent group')
        if group in group_splits and group_splits[group] != split:
            raise ValueError('shared parent group leaks across splits')
        group_splits[group] = split
        declared = value.get('groups', {}).get(group, {})
        if declared and declared.get('split') != split:
            raise ValueError('frozen parent group split mismatch')
        splits[rid].add(split)
        case['rule_id'] = rid
        for key in ['ir_path', 'original_ir_path', 'oracle_path']:
            source = Path(case[key])
            source = source if source.is_absolute() else path.parent / source
            source = source.resolve()
            if str(source) not in hashes:
                raise ValueError('frozen case artifact hash missing: ' + key)
            case[key] = str(source)
            # Sealed oracle bytes are hashed above, never parsed during selection.
            if key == 'oracle_path':
                continue
            ir = _read(source)
            validate_ir(ir)
            for artifact in ir['source_artifacts']:
                sha = artifact['sha256']
                if sha in source_splits and source_splits[sha] != split:
                    raise ValueError('shared source parent leaks across splits')
                source_splits[sha] = split
                original = Path(artifact['path'])
                original = original if original.is_absolute() else source.parent / original
                if original.is_file() and _sha(original) != sha:
                    raise ValueError('frozen original source hash mismatch')
    if any(splits[rid] != {'feedback', 'validation', 'test'} for rid in rule_ids):
        raise ValueError('every rule requires three disjoint study sets')
    normalized['artifact_sha256'] = hashes
    return normalized, digest({'manifest_sha256': _sha(path), 'artifacts': hashes})


def _verify_outputs(out):
    index = out / 'artifact-index.json'
    if not index.is_file():
        raise ValueError('frozen study output integrity index missing')
    for name, expected in _read(index)['files'].items():
        path = (out / name).resolve()
        if not path.is_relative_to(out.resolve()) or not path.is_file() or _sha(path) != expected:
            raise ValueError('frozen study output integrity/hash mismatch: ' + name)


def _budget(client):
    ledger = getattr(client, 'ledger', None)
    return ledger.summary() if ledger is not None and callable(getattr(ledger, 'summary', None)) else {
        'available': False, 'reason': 'injected client exposes no budget ledger; no cost estimate fabricated'}


def _compatible(packages):
    contracts = {}
    for package in packages:
        for name in package['program_spec']['requires']:
            cap = package['registry']['capabilities'][name]
            if name in contracts and contracts[name] != cap:
                raise ValueError('incompatible shared analysis capability: ' + name)
            contracts[name] = cap


class _FixedAnalysisClient:
    """Freeze the original analysis contract even when initial code did not compile."""
    def __init__(self, client, raw, folder):
        self.client, self.raw, self.folder = client, raw, Path(folder)
        self.config = getattr(client, 'config', {})
        self.ledger = getattr(client, 'ledger', None)

    def complete_json(self, task, instructions, data, max_tokens):
        if task != PROMPT_VERSION:
            return self.client.complete_json(task, instructions, data, max_tokens)
        checkpoint = self.folder / (digest(data) + '.json')
        if checkpoint.exists():
            answer = _read(checkpoint)['raw']
        else:
            answer = self.client.complete_json(task, instructions, data, max_tokens)
            _immutable(checkpoint, {'input_sha256': digest(data), 'raw': answer})
        if (answer.get('analysis_requests', []) != self.raw.get('analysis_requests', []) or
                set(answer.get('requires', [])) != set(self.raw.get('requires', []))):
            raise ValueError('generated analysis contract and requires are fixed to the shared initial candidate')
        return answer


def _cross_validator(condition, rid, suite, raw, cases, runner, initial_model):
    others = [p for name, p in suite.items() if name != rid]
    baseline_model = shared_model(list(suite.values())) if suite else initial_model

    def validate(candidate):
        if condition == 'program_only' and (candidate['program_spec']['analysis_requests'] != raw.get('analysis_requests', []) or
                set(candidate['program_spec']['requires']) != set(raw.get('requires', [])) or candidate['model'] != baseline_model):
            return {'passed': False, 'failures': [{'rule_id': rid, 'failure_types': ['fixed_analysis_contract'],
                                                  'reason': 'program_only representation and analysis are fixed'}]}
        try:
            _compatible([*others, candidate])
            new_model = shared_model([*others, candidate])
        except ValueError as error:
            return {'passed': False, 'failures': [{'rule_id': rid, 'failure_types': ['cross_rule_regression'],
                                                   'reason': str(error)}]}
        if new_model == baseline_model:
            return {'passed': True, 'failures': [], 'checked_cases': 0, 'model_version': new_model['version']}
        failures, checked = [], 0
        for old in others:
            other_id = str(old['program_spec']['rule_id'])
            feedback = [c for c in cases if c['rule_id'] == other_id and c['split'] == 'feedback']
            before = evaluate_cases(rebind([old], baseline_model)[0], feedback, runner)
            after = evaluate_cases(rebind([old], new_model)[0], feedback, runner)
            previous = {r['id']: r for r in before['records']}
            details = {r['id']: r for r in after['failures']}
            checked += len(feedback)
            for record in after['records']:
                if previous[record['id']]['correct'] and not record['correct']:
                    failures.append({**details.get(record['id'], record), 'rule_id': other_id,
                        'failure_types': ['cross_rule_regression'], 'reason': 'A previously correct verified other-rule feedback case regressed',
                        'previous_prediction': previous[record['id']], 'candidate_prediction': record})
        return {'passed': not failures, 'failures': failures, 'checked_cases': checked, 'model_version': new_model['version']}
    return validate


def _grouped(evaluation, cases, rid):
    by_id = {c['id']: c for c in cases}
    output = {}
    for axis in ['rule', 'context_origin', 'evidence_domain', 'mutation_type']:
        groups = defaultdict(list)
        for record in evaluation['records']:
            case = by_id[record['id']]
            key = rid if axis == 'rule' else case.get(axis)
            if axis == 'mutation_type' and key is None:
                oracle = _read(case['oracle_path'])
                key = oracle.get('mutation_type', oracle.get('operation', 'unspecified'))
            groups[str(key or 'unspecified')].append(record)
        output[axis] = {key: {**_metrics(records), 'parent_groups': len({r['parent_group'] for r in records}),
                             'after_statuses': dict(Counter(r['after'] for r in records))}
                        for key, records in groups.items()}
    return output


def _failed_baseline(cases):
    records = []
    for case in cases:
        oracle = _read(case['oracle_path'])
        records.append({'id': case['id'], 'expected': oracle['status'], 'before': 'ERROR', 'after': 'ERROR',
                        'correct': False, 'target_node_id': oracle.get('target_node_id', case.get('target_node_id')),
                        'parent_group': case['parent_group'], 'context_origin': case.get('context_origin'),
                        'evidence_domain': case.get('evidence_domain'), 'reason': 'shared initial candidate failed to compile'})
    return {'metrics': _metrics(records), 'records': records, 'failures': records}


def run_study(tasks, manifest_path, *, client, output_dir, runner, max_rounds=5, initial_model=None):
    """Select both conditions before uniformly evaluating their sealed heldout cases.

    runner(package, ir) supplies only normal task-selected evidence resources.
    It may expose study_fingerprint to pin its evidence/environment configuration.
    No real request is sent except through the injected, cumulatively metered client.
    """
    if type(max_rounds) is not int or not 1 <= max_rounds <= 5:
        raise ValueError('study max_rounds must be 1..5')
    tasks = deepcopy(list(tasks))
    reject_answers(tasks)
    for task in tasks:
        task['rule_id'] = str(task['rule_id'])
        if not task['rule_id'] or not isinstance(task.get('rule_text'), str) or not task['rule_text'].strip() or not isinstance(task.get('basis'), list):
            raise ValueError('study tasks require identity, rule text and basis')
    if not tasks or len({t['rule_id'] for t in tasks}) != len(tasks):
        raise ValueError('study task IDs must be unique')
    initial_model = deepcopy(initial_model or base_model())
    validate_model(initial_model)
    manifest, benchmark_hash = _manifest(manifest_path, tasks)
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    model_config = getattr(client, 'config', {})
    protocol = {'schema_version': VERSION, 'benchmark_sha256': benchmark_hash, 'tasks_sha256': digest(tasks),
        'initial_model': initial_model, 'conditions': list(CONDITIONS), 'max_rounds': max_rounds,
        'selection': 'validation strict balanced accuracy; no heldout access until all condition suites are frozen',
        'regression_policy': 'verified-other-rule-feedback-only/1.0', 'runner_fingerprint': getattr(runner, 'study_fingerprint', None),
        'model_config': {k: model_config.get(k) for k in ['MAAS_MODEL', 'MAAS_MODEL_VERSION']},
        'implementation_sha256': {name: _sha(Path(__file__).with_name(name)) for name in ['study.py', 'feedback_loop.py', 'synthesis.py', 'pipeline.py']}}
    _immutable(out / 'protocol.json', protocol)
    _immutable(out / 'frozen-benchmark.json', manifest)
    if (out / 'summary.json').exists():
        _verify_outputs(out)
        return _read(out / 'summary.json')
    started = time.monotonic()
    result = {'schema_version': VERSION, 'status': 'incomplete', 'conditions': {}, 'initial': {},
        'initial_model_version': initial_model['version'], 'configured_model_version': initial_model['version'], 'benchmark_sha256': benchmark_hash,
        'started_at': datetime.now(timezone.utc).isoformat(), 'budget_before': _budget(client),
        'protocol_path': str((out / 'protocol.json').resolve())}

    def finish(reason, complete=False):
        result.update(status='completed' if complete else 'incomplete', stop_reason=reason,
                      elapsed_seconds=time.monotonic() - started, budget=_budget(client),
                      finished_at=datetime.now(timezone.utc).isoformat())
        write_json_atomic(out / ('summary.json' if complete else 'checkpoint.json'), result)
        if complete:
            files = {str(path.relative_to(out)): _sha(path) for path in sorted(out.rglob('*'))
                     if path.is_file() and path.name not in {'artifact-index.json', 'checkpoint.json'}}
            _immutable(out / 'artifact-index.json', {'schema_version': 'paper-study-artifacts/1.0', 'files': files})
        return result

    raw, initial_packages, invalid_initial = {}, {}, set()
    try:
        for task in tasks:
            rid = task['rule_id']; folder = out / 'initial' / ('task-' + digest(rid)[:12])
            if (folder / 'generation-failed.json').exists() and not (folder / 'synthesis-response.json').exists():
                return finish('initial_generation_failed_without_raw_response')
            try:
                package = synthesize_program(task, client, folder, model=initial_model)
                initial_packages[rid] = package
            except BudgetExceeded:
                return finish('budget_limit_initial')
            except Exception as error:
                if not (folder / 'synthesis-response.json').exists():
                    write_json_atomic(folder / 'generation-failed.json', {'error_type': type(error).__name__, 'reason': str(error)[:3000]})
                    return finish('initial_generation_failed_without_raw_response')
                invalid_initial.add(rid)
                result['initial'][rid] = {'status': 'invalid_initial', 'error_type': type(error).__name__, 'reason': str(error)[:3000]}
            raw[rid] = _read(folder / 'synthesis-response.json')
            result['initial'].setdefault(rid, {})
            result['initial'][rid].update(raw_sha256=digest(raw[rid]), raw_path=str((folder / 'synthesis-response.json').resolve()))
        common_model = deepcopy(initial_model)
        for task in tasks:
            change = raw[task['rule_id']].get('model_patch', {})
            if isinstance(change, dict) and change.get('node_types'):
                try:
                    common_model = extend_model(common_model, change)
                except ValueError:
                    pass  # The exact invalid raw still fails condition round zero.
        result['initial_model_version'] = common_model['version']
        initial_packages = {}
        for task in tasks:
            rid = task['rule_id']
            if rid in invalid_initial:
                continue
            try:
                package = build_program(raw[rid], rule_text=task['rule_text'], basis=task['basis'], model=common_model)
                folder = out / 'initial' / 'shared-packages' / ('task-' + digest(rid)[:12])
                if not (folder / 'manifest.json').exists(): save_program(package, folder)
                else: package = load_program(folder)
                initial_packages[rid] = package
                result['initial'][rid].update(status='compiled', version_id=package['manifest']['version_id'], package_path=str(folder.resolve()))
            except ValueError as error:
                result['initial'][rid].update(status='invalid_initial', error_type=type(error).__name__, reason=str(error)[:3000])
        _compatible(list(initial_packages.values()))
        _immutable(out / 'shared-initial.json', {'model': common_model, 'candidates': result['initial']})
        if initial_packages:
            save_suite(list(initial_packages.values()), out / 'initial' / 'suite')
        selected = {}
        for condition in CONDITIONS:
            condition_out = out / 'conditions' / condition
            state = dict(initial_packages)
            condition_result = {'rules': {}, 'allow_model_refinement': condition == 'joint'}
            result['conditions'][condition] = condition_result
            for task in tasks:
                # Recheck all frozen bytes before each selection, including resumes.
                if _manifest(manifest_path, tasks)[1] != benchmark_hash:
                    raise ValueError('frozen benchmark changed during study')
                rid = task['rule_id']; folder = condition_out / ('task-' + digest(rid)[:12])
                current_model = shared_model(list(state.values())) if state else common_model
                seed = initial_packages.get(rid)
                seed = rebind([seed], current_model)[0] if seed is not None else None
                others = [package for name, package in state.items() if name != rid]
                def run(package, ir, others=others):
                    combined = shared_model([*others, package])
                    return runner(rebind([package], combined)[0], ir)
                api_client = client if condition == 'joint' else _FixedAnalysisClient(client, raw[rid], folder / 'fixed-analysis-responses')
                loop = run_feedback_loop(task, out / 'frozen-benchmark.json', client=api_client,
                    output_dir=folder, runner=run, model=current_model, max_rounds=max_rounds,
                    allow_model_refinement=condition == 'joint', initial_package=seed,
                    initial_candidate=None if seed is not None else raw[rid], defer_test=True,
                    candidate_validator=_cross_validator(condition, rid, state, raw[rid], manifest['cases'], runner, common_model),
                    regression_policy=protocol['regression_policy'])
                condition_result['rules'][rid] = deepcopy(loop)
                if 'budget' in loop.get('stop_reason', ''):
                    return finish('budget_limit_selection')
                if loop.get('status') != 'selected_pending_test' or not loop.get('best_package_path'):
                    return finish('no_executable_selected_candidate')
                state[rid] = load_program(loop['best_package_path'])
                # Selected packages all share the latest accepted compatible model.
                accepted_model = shared_model([p for name, p in state.items() if name != rid] + [state[rid]])
                state = {str(p['program_spec']['rule_id']): p for p in rebind(list(state.values()), accepted_model)}
            _compatible(list(state.values()))
            suite = save_suite(list(state.values()), condition_out / 'suite', validated=True,
                validation={'protocol': VERSION, 'selection_only': True, 'heldout_evaluated': False,
                            'regression_policy': protocol['regression_policy']})
            condition_result.update(suite_version=suite['version_id'], suite_path=str((condition_out / 'suite').resolve()), model_version=suite['model']['version'])
            selected[condition] = state
        if _manifest(manifest_path, tasks)[1] != benchmark_hash:
            raise ValueError('frozen benchmark changed before heldout evaluation')
        selection = {'schema_version': 'paper-study-selection/1.0', 'benchmark_sha256': benchmark_hash,
            'shared_initial_model': common_model,
            'shared_initial': {rid: p['manifest']['version_id'] for rid, p in initial_packages.items()},
            'invalid_initial': sorted(set(raw) - set(initial_packages)),
            'conditions': {name: {'suite_version': result['conditions'][name]['suite_version'],
                'program_versions': {rid: p['manifest']['version_id'] for rid, p in selected[name].items()}}
                for name in CONDITIONS}}
        _immutable(out / 'selection-frozen.json', selection)
        result['selection_frozen_path'] = str((out / 'selection-frozen.json').resolve())
        cache = {}
        for condition in CONDITIONS:
            for task in tasks:
                rid = task['rule_id']
                heldout = [c for c in manifest['cases'] if c['rule_id'] == rid and c['split'] == 'test']
                folder = out / 'conditions' / condition / ('task-' + digest(rid)[:12])
                final_path, base_path = folder / 'heldout-final.json', folder / 'heldout-shared-initial.json'
                if final_path.exists(): final = _read(final_path)
                else:
                    final = evaluate_cases(selected[condition][rid], heldout, runner, cache)
                    final['groups'] = _grouped(final, heldout, rid); _immutable(final_path, final)
                if base_path.exists(): baseline = _read(base_path)
                else:
                    baseline = evaluate_cases(initial_packages[rid], heldout, runner, cache) if rid in initial_packages else _failed_baseline(heldout)
                    baseline['groups'] = _grouped(baseline, heldout, rid); _immutable(base_path, baseline)
                result['conditions'][condition]['rules'][rid].update(final_test=final, baseline_test=baseline)
        if _manifest(manifest_path, tasks)[1] != benchmark_hash:
            raise ValueError('frozen benchmark changed during heldout evaluation')
        result['version_inventory'] = selection
        return finish('all_frozen_selections_evaluated', complete=True)
    except BudgetExceeded:
        return finish('budget_limit')
