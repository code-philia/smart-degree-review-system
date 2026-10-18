"""Private, bounded online fault injection; never a formal benchmark result.

Only the current materialized input is a parent. The general builder supplies
real IR edits plus fresh blind label/review. Accepted cases are projected into
an online regression inventory, with labels kept outside detector IR.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .benchmark_builder import build_benchmark, ORACLE_PROTOCOL
from .contracts import ir_hash, validate_ir
from .program_analysis import _base_kind, _ground_fields, _hash, _target_data
from .programs import target_nodes
from .storage import json_bytes, write_json_atomic


def mutation_policy(resources):
    value = (resources or {}).get('online_mutation_validation', {})
    if type(value) is bool:
        return {'enabled': value, 'when': 'on_feedback'}
    if not isinstance(value, dict) or set(value) - {'enabled', 'when'}:
        raise ValueError('online_mutation_validation must be a boolean or enabled/when object')
    enabled, when = value.get('enabled', True), value.get('when', 'on_feedback')
    if type(enabled) is not bool or when not in {'on_feedback', 'always'}:
        raise ValueError('invalid online mutation enabled/when policy')
    return {'enabled': enabled, 'when': when}


def _check(client):
    check = getattr(client, 'check', None)
    if callable(check):
        check()


def _immutable(path, value):
    if path.exists():
        if path.read_bytes() != json_bytes(value):
            raise ValueError('online mutation checkpoint changed')
    else:
        write_json_atomic(path, value, exclusive=True)


def _private_parent(ir, folder):
    private = deepcopy(ir)
    sources = folder / 'private-parent' / 'sources'
    sources.mkdir(parents=True, exist_ok=True)
    for source in private['source_artifacts']:
        original = Path(source['path']).resolve()
        if not original.is_file():
            raise ValueError('online parent source file missing')
        payload = original.read_bytes()
        if hashlib.sha256(payload).hexdigest() != source['sha256']:
            raise ValueError('online parent source hash mismatch')
        copied = sources / (source['sha256'] + ('.pdf' if source['kind'] == 'pdf' else '.txt'))
        if not copied.exists():
            try:
                with copied.open('xb') as stream:
                    stream.write(payload)
            except FileExistsError:
                pass
        if copied.read_bytes() != payload:
            raise ValueError('private online source changed')
        source['path'] = str(copied.resolve())
    validate_ir(private, folder)
    path = folder / 'private-parent' / 'ir.json'
    _immutable(path, private)
    return path


def _prepare(ir, packages, analysis, gateway, environment, client):
    tasks, sources, seeds, semantic_rules = [], {}, [], set()
    work_cache = {}
    analysis = deepcopy(analysis)
    nodes = {n['id']: n for n in ir['nodes']}
    for package in packages:
        rid = str(package['program_spec']['rule_id'])
        targets = list(target_nodes(package, ir).values())
        reference = any(_base_kind(ir, n['kind']) == 'ReferenceUse' for n in targets)
        task = {'rule_id': rid, 'rule_text': package['input']['rule_text'],
                'basis': deepcopy(package['input']['basis']),
                'target_kinds': list(package['program_spec']['target_kinds']),
                'required_source_roles': ['basis'] if package['input']['basis'] else [],
                'allowed_context_origins': [ir.get('metadata', {}).get('context_origin', 'real')]}
        if reference:
            semantic_rules.add(rid)
            task['restrict_to_citation_seeds'] = True
            task['required_source_roles'] += ['original_cited_work_content', 'mutated_cited_work_content']
            task['semantic_requirements'] = {'min_quote_content_chars': 8,
                'require_bound_citation_context': True, 'preserve_reference_bindings': True,
                'online_grounding_contract': {
                    'original_basis': 'Return original_basis=explicit_support and a substantive original_reason explaining actual support.',
                    'basis': 'Return basis=explicit_support for changed PASS, or explicit_scope_contradiction for changed VIOLATION.',
                    'policy': 'For BOTH sides quote actual citing prose and identified cited content. Topic mismatch, absence and missing details never prove misuse. Original and changed PASS require positive support, not merely two unrelated quotes.'}}
            for target in targets:
                _check(client)
                if _base_kind(ir, target['kind']) != 'ReferenceUse':
                    continue
                data, ready = _target_data(ir, analysis, target, gateway, environment, work_cache)
                works = data.get('external_works', [])
                binding = next((b for b in analysis['bindings'] if b['use_id'] == target['id'] and b['status'] == 'resolved'), None)
                entries = [nodes[nid] for nid in binding['target_ids'] if nid in nodes] if binding else []
                if not ready or len(works) != 1 or len(entries) != 1:
                    continue
                context_id = data['citation_context']['node_id']
                if context_id not in nodes or nodes[context_id]['kind'] not in {'Paragraph', 'Caption'}:
                    continue
                ids = []
                for source in data['sources']:
                    if source['origin'] != 'external' or source.get('work_id') != works[0]['id']:
                        continue
                    sid = source['source_id']
                    record = {'id': sid, 'text': source['text'], 'roles': ['cited_work_content'],
                              'work_id': works[0]['id'], 'coverage': source.get('coverage', 'unknown')}
                    if sid in sources and sources[sid] != record:
                        raise ValueError('ambiguous online cited content source')
                    sources[sid] = record; ids.append(sid)
                if ids:
                    seed = {'parent_id': ir['document_id'], 'edit_node_id': context_id,
                            'target_node_id': target['id'], 'bibliography_entry': entries[0]['text'],
                            'work': deepcopy(works[0]), 'source_ids': ids}
                    if seed not in seeds:
                        seeds.append(seed)
        tasks.append(task)
    resources = {'sources': list(sources.values()), 'citation_seeds': seeds}
    if environment and environment.get('domain') == 'controlled_catalog':
        catalog = deepcopy(environment.get('catalog', []))
        resources.update(controlled_catalog=catalog, catalog_environment={'id': 'controlled_catalog'})
        resources['sources'].append({'id': 'online-controlled-catalog-' + _hash(catalog)[:20],
            'text': json.dumps(catalog, sort_keys=True, ensure_ascii=False),
            'coverage': 'complete_controlled_catalog', 'roles': ['catalog_identity_scope']})
    return tasks, resources, semantic_rules


def _semantic_case(oracle, original, changed, resources):
    """Both independent oracles must ground BOTH semantic sides, with fixed binding."""
    target_id = oracle['target_node_id']
    from .citations import citation_context
    before, after = citation_context(original, target_id), citation_context(changed, target_id)
    work_sources = {s['id']: s for s in resources['sources'] if 'cited_work_content' in s.get('roles', [])}
    edit = oracle['source_edit']
    if edit['node_id'] != before['node_id'] or before['selector'] != after['selector']:
        return 'semantic edit must preserve the identified citation binding'
    for label in [oracle['label'], oracle['review']]:
        for side, context, sid, value in [('original', before, 'original-node', True),
                                           ('changed', after, 'mutated-node', oracle['status'] == 'PASS')]:
            basis = label.get('original_basis') if side == 'original' else label.get('basis')
            reason = label.get('original_reason') if side == 'original' else label.get('reason')
            expected_basis = 'explicit_support' if value else 'explicit_scope_contradiction'
            if basis != expected_basis:
                return side + ' citation basis is missing or does not establish positive support/contradiction'
            bound_ids = {s['source_id'] for s in oracle['evidence_requirements']['sources'].get(
                'original_cited_work_content' if side == 'original' else 'mutated_cited_work_content', [])}
            data = {'citation_context': context, 'sources': [{'source_id': sid, 'origin': 'paper',
                     'node_id': context['node_id'], 'text': context['text'], 'complete': True}]}
            for work_id in bound_ids:
                source = work_sources.get(work_id)
                if source:
                    data['sources'].append({'source_id': work_id, 'origin': 'external',
                        'text': source['text'], 'work_id': source['work_id'], 'content_id': work_id,
                        'complete': source.get('coverage') == 'full_text'})
            allowed = {s['source_id'] for s in data['sources']}
            quotes = [q for q in label['quotes'] if q['source_id'] in allowed]
            facts, _ = _ground_fields({'fields': {'supported': 'boolean'}}, {'fields': {'supported': {
                'state': 'observed', 'value': value, 'basis': basis, 'reason': reason, 'quotes': quotes}}}, data, True)
            if facts['supported']['state'] != 'observed':
                return side + ' citation observation is not grounded in actual context and identified content'
    return None


def build_online_cases(ir, packages, analysis, *, client, gateway, output_dir, resources=None):
    """One negative plus one changed compliant control per rule, one proposal batch.

    A partial result is diagnostic only: online_refine retains the active suite.
    Formal data, external oracle paths and caller-supplied answers are not read.
    """
    validate_ir(ir)
    _check(client)
    folder = Path(output_dir).resolve(); folder.mkdir(parents=True, exist_ok=True)
    parent_path = _private_parent(ir, folder)
    private = json.loads(parent_path.read_text())
    tasks, evidence, semantic_rules = _prepare(private, packages, analysis, gateway,
        (resources or {}).get('evidence_environment'), client)
    blocked = [task['rule_id'] for task, package in zip(tasks, packages, strict=True)
               if task['rule_id'] in semantic_rules and not any(
                   seed['target_node_id'] in target_nodes(package, private) for seed in evidence['citation_seeds'])]
    if blocked:
        outcome = {'status': 'incomplete', 'cases': [], 'case_count': 0,
            'summary': {task['rule_id']: {'violations': 0, 'controls': 0,
                         'missing_violations': 1, 'missing_controls': 1} for task in tasks},
            'rejections': [{'rule_id': rid, 'reason': 'identified cited-work content and a resolved citation context are required'}
                           for rid in blocked], 'protocol': ORACLE_PROTOCOL,
            'origin': 'online-regression', 'formal_evaluation': False}
        _immutable(folder/'online-cases.json', outcome)
        return outcome
    result = build_benchmark(tasks, [parent_path], client=client, output_dir=folder/'builder',
        resources=evidence, negatives_per_rule=1, controls_per_rule=1, seed=31, max_proposal_batches=1)
    _check(client)
    path = Path(result['manifest_path'])
    if hashlib.sha256(path.read_bytes()).hexdigest() != result['frozen_manifest_sha256']:
        raise ValueError('online mutation manifest hash mismatch')
    manifest = json.loads(path.read_text())
    if manifest['stop_reason'] == 'budget_exhausted':
        outcome = {'status': 'budget_limit', 'cases': [], 'case_count': 0,
            'summary': {task['rule_id']: {'violations': 0, 'controls': 0,
                         'missing_violations': 1, 'missing_controls': 1} for task in tasks},
            'builder_summary': manifest['summary'], 'rejections': json.loads((path.parent/'rejections.json').read_text()),
            'protocol': ORACLE_PROTOCOL, 'origin': 'online-regression', 'formal_evaluation': False,
            'builder_manifest_path': str(path), 'builder_manifest_sha256': result['frozen_manifest_sha256']}
        write_json_atomic(folder/'budget-checkpoint.json', outcome)
        return outcome
    if manifest['label_protocol'] != ORACLE_PROTOCOL or any(g['split'] != 'feedback' for g in manifest['groups'].values()):
        raise ValueError('online mutations must use the current independent oracle protocol and feedback-only grouping')
    rejections = json.loads((path.parent/'rejections.json').read_text())
    cases = []
    for item in manifest['cases']:
        for name in ['ir_path', 'oracle_path', 'original_ir_path']:
            artifact = Path(item[name]).resolve()
            if not artifact.is_relative_to(path.parent):
                raise ValueError('online mutation artifact escapes private build')
            if hashlib.sha256(artifact.read_bytes()).hexdigest() != manifest['artifact_sha256'][str(artifact)]:
                raise ValueError('online mutation artifact hash mismatch')
        changed = json.loads(Path(item['ir_path']).read_text())
        original = json.loads(Path(item['original_ir_path']).read_text())
        oracle = json.loads(Path(item['oracle_path']).read_text())
        validate_ir(changed, folder)
        rid = str(oracle['rule_id'])
        if (item['split'] != 'feedback' or oracle['valid'] is not True or
                oracle['label_protocol'] != ORACLE_PROTOCOL or
                ir_hash(changed) != oracle['mutant_sha256'] or ir_hash(original) != oracle['parent_sha256'] or
                ir_hash(changed) == ir_hash(original) or oracle['status'] != oracle['proposal_claimed_status']):
            raise ValueError('invalid independently verified online mutation')
        if rid in semantic_rules:
            reason = _semantic_case(oracle, original, changed, evidence)
            if reason:
                rejections.append({'rule_id': rid, 'case_id': item['id'], 'reason': reason}); continue
        cases.append({'id': 'online-' + item['id'], 'verified': True, 'origin': 'online-regression',
            'split': 'feedback', 'validation_role': 'local-control' if oracle['status'] == 'PASS' else 'local-mutant',
            'label_protocol': ORACLE_PROTOCOL, 'label_provenance': deepcopy(oracle['label_provenance']),
            'label_evidence_sha256': _hash([oracle['label'], oracle['review']]),
            'ir': changed, 'expected': [{'rule_id': rid, 'node_id': oracle['target_node_id'], 'status': oracle['status']}],
            'source_edit': deepcopy(oracle['source_edit']), 'label_evidence': {
                'label': oracle['label'], 'review': oracle['review'], 'evidence_requirements': oracle['evidence_requirements']},
            'evidence_environment': deepcopy((resources or {}).get('evidence_environment'))})
    summary = {}
    for task in tasks:
        rid = task['rule_id']; labels = [c['expected'][0]['status'] for c in cases if c['expected'][0]['rule_id'] == rid]
        negative, control = labels.count('VIOLATION'), labels.count('PASS')
        summary[rid] = {'violations': negative, 'controls': control,
                        'missing_violations': max(0, 1-negative), 'missing_controls': max(0, 1-control)}
    complete = all(not row['missing_violations'] and not row['missing_controls'] for row in summary.values())
    outcome = {'status': 'complete' if complete else 'incomplete', 'cases': cases, 'case_count': len(cases),
               'summary': summary, 'rejections': rejections, 'protocol': ORACLE_PROTOCOL,
               'origin': 'online-regression', 'builder_manifest_path': str(path),
               'builder_manifest_sha256': result['frozen_manifest_sha256'], 'formal_evaluation': False}
    _immutable(folder/'online-cases.json', outcome)
    return outcome
