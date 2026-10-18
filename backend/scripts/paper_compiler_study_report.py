#!/usr/bin/env python3
"""Read existing frozen study artifacts; never execute a detector or model client."""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import csv
import difflib
import hashlib
import json
import os
from pathlib import Path
import sys

VERSION = 'paper-study-report/1.0'
CONDITIONS = ('initial', 'program_only', 'joint')


def _sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _digest(value):
    return hashlib.sha256((json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()).hexdigest()


def _save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False)+'\n', encoding='utf-8')


class Reader:
    def __init__(self, root): self.root, self.hashes = Path(root).resolve(), {}
    def path(self, path):
        path = Path(path); path = path if path.is_absolute() else self.root/path
        path = path.resolve()
        if not path.is_relative_to(self.root): raise ValueError('study artifact escapes source root')
        return path
    def read(self, path, default=None):
        path = self.path(path)
        if not path.is_file(): return default
        if 'oracle' in path.name: raise ValueError('sealed oracle is not a report input')
        self.hashes[str(path.relative_to(self.root))] = _sha(path)
        return json.loads(path.read_text(encoding='utf-8'))
    def text(self, path):
        path = self.path(path)
        if not path.is_file(): return None
        self.hashes[str(path.relative_to(self.root))] = _sha(path)
        return path.read_text(encoding='utf-8')


def _integrity(reader, complete):
    index = reader.read('artifact-index.json')
    if not isinstance(index, dict) or not isinstance(index.get('files'), dict):
        return {'status': 'failed' if complete else 'checkpoint_unindexed', 'failures': ['artifact-index.json missing']}
    failures = []
    for name, expected in index['files'].items():
        try: path = reader.path(name)
        except ValueError: failures.append('unsafe index path'); continue
        if not path.is_file() or _sha(path) != expected: failures.append(str(name))
    if complete:
        for required in ('summary.json', 'protocol.json', 'selection-frozen.json', 'frozen-benchmark.json'):
            if required not in index['files']: failures.append(required+' unindexed')
    return {'status': 'failed' if failures else 'verified', 'files_checked': len(index['files']), 'failures': failures}


def metric_row(records):
    valid = [r for r in records if r.get('expected') in {'PASS', 'VIOLATION'}]
    negatives = [r for r in valid if r['expected'] == 'VIOLATION']; controls = [r for r in valid if r['expected'] == 'PASS']
    correct = lambda r: r.get('before') == 'PASS' and r.get('after') == r['expected']
    nr, pr = sum(map(correct, negatives)), sum(map(correct, controls))
    unknown = sum('UNKNOWN' in {r.get('before'), r.get('after')} for r in valid)
    errors = sum('ERROR' in {r.get('before'), r.get('after')} for r in valid)
    all_error = bool(valid) and errors == len(valid)
    return {'valid_cases': len(valid), 'excluded_records': len(records)-len(valid), 'negative_cases': len(negatives), 'controls': len(controls),
        'parent_groups': len({r.get('parent_group') for r in valid if r.get('parent_group')}),
        'strict_correct_negatives': nr, 'strict_correct_controls': pr,
        'strict_balanced_accuracy': (nr/len(negatives)+pr/len(controls))/2 if negatives and controls else None,
        'mutant_detection_rate': sum(r.get('after') == 'VIOLATION' for r in negatives)/len(negatives) if negatives and not all_error else None,
        'control_false_positive_rate': sum('VIOLATION' in {r.get('before'), r.get('after')} for r in controls)/len(controls) if controls and not all_error else None,
        'unknown': unknown, 'errors': errors, 'not_applicable': sum('NOT_APPLICABLE' in {r.get('before'), r.get('after')} for r in valid),
        'conclusive_cases': sum({r.get('before'), r.get('after')} <= {'PASS', 'VIOLATION'} for r in valid),
        'after_statuses': dict(Counter(r.get('after', 'MISSING') for r in valid)),
        'status': 'ERROR' if all_error else 'measured' if valid else 'MISSING',
        'semantic_detection_metrics': None if all_error or not valid else {'conclusive_cases': sum({r.get('before'), r.get('after')} <= {'PASS', 'VIOLATION'} for r in valid)}}


def _manual(path):
    if path is None: return {'status': 'not_recorded', 'interventions': None, 'task_specific_lines_added': None, 'events': None}
    value = json.loads(Path(path).read_text(encoding='utf-8')); events = value.get('events')
    if not isinstance(events, list): raise ValueError('manual audit requires events')
    identifiers = set()
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get('id'), str) or event['id'] in identifiers or event.get('kind') not in {
                'manual_intervention', 'task_specific_code', 'generic_framework_change'}: raise ValueError('invalid manual audit event')
        identifiers.add(event['id'])
        for key in ('lines_added', 'lines_removed'):
            if key in event and (type(event[key]) is not int or event[key] < 0): raise ValueError('manual line counts must be nonnegative integers')
    return {'status': 'self_reported_unverified', 'input_sha256': _sha(path), 'events': len(events),
        'interventions': sum(e['kind'] == 'manual_intervention' for e in events),
        'task_specific_code_events': sum(e['kind'] == 'task_specific_code' for e in events),
        'task_specific_lines_added': sum(e['lines_added'] for e in events if e['kind'] == 'task_specific_code') if all('lines_added' in e for e in events if e['kind'] == 'task_specific_code') else None,
        'generic_framework_change_events': sum(e['kind'] == 'generic_framework_change' for e in events)}


def _usage(value):
    if isinstance(value, dict) and isinstance(value.get('resource_usage'), dict): return value['resource_usage']
    return value if isinstance(value, dict) else None


def _resource_columns(value):
    usage = _usage(value)
    fields = ('elapsed_seconds', 'budget_before', 'budget_after', 'spent_cny_delta', 'committed_cny_delta',
              'requests_delta', 'prompt_tokens_delta', 'completion_tokens_delta', 'accounting_scope')
    row = {key: usage.get(key) if usage is not None else None for key in fields}
    wrapper = value if isinstance(value, dict) and isinstance(value.get('resource_usage'), dict) else {}
    return {**row, 'resource_usage': usage, 'resource_usage_available': usage.get('available') if usage is not None else None,
            'resource_usage_status': wrapper.get('status'), 'resource_usage_started_at': wrapper.get('started_at'),
            'api_cost_cny': row['spent_cny_delta'],
            'resource_attribution': 'shared ledger interval; concurrent calls may be included; not exact per-task attribution' if usage is not None else None}


def _cost(summary):
    usage = _usage(summary.get('resource_usage'))
    if usage is not None:
        return {'spent_cny_delta': usage.get('spent_cny_delta'), 'committed_cny_delta': usage.get('committed_cny_delta'),
            'api_requests_delta': usage.get('requests_delta'), 'prompt_tokens_delta': usage.get('prompt_tokens_delta'),
            'completion_tokens_delta': usage.get('completion_tokens_delta'), 'elapsed_seconds': usage.get('elapsed_seconds'),
            'budget_before': usage.get('budget_before'), 'budget_after': usage.get('budget_after'),
            'resource_usage_available': usage.get('available'), 'accounting_scope': usage.get('accounting_scope'),
            'elapsed_seconds_semantics': 'recorded cumulative active time across resumes; offline waiting excluded',
            'per_condition_or_round_cost': None, 'scope': 'shared-ledger study interval; concurrent requests may be included; separate round intervals are not exact attribution and are not summed'}
    before, after = summary.get('budget_before') or {}, summary.get('budget') or {}
    fields = {'spent_cny_delta': 'spent_cny', 'committed_cny_delta': 'committed_cny', 'api_requests_delta': 'requests',
              'prompt_tokens_delta': 'prompt_tokens', 'completion_tokens_delta': 'completion_tokens'}
    result = {key: str(Decimal(str(after[field]))-Decimal(str(before[field]))) if field in before and field in after else None
              for key, field in fields.items()}
    return {**result, 'elapsed_seconds': summary.get('elapsed_seconds'), 'per_condition_or_round_cost': None,
            'accounting_scope': 'shared_ledger_interval' if any(value is not None for value in result.values()) else None,
            'elapsed_seconds_semantics': 'legacy summary value; accumulation across resumes is not established',
            'scope': 'shared-ledger study interval; concurrent requests may be included; per-round fields stay null when absent from legacy artifacts'}


def _csv(path, rows):
    names = list(dict.fromkeys(key for row in rows for key in row)) or ['status']
    with Path(path).open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=names); writer.writeheader()
        for row in rows: writer.writerow({key: json.dumps(value, ensure_ascii=True, sort_keys=True) if isinstance(value, (dict, list)) else value for key, value in row.items()})


def _comparison(condition, rid, evaluation, forced=None):
    metrics = metric_row(evaluation.get('records', [])) if isinstance(evaluation, dict) else metric_row([])
    if not isinstance(evaluation, dict):
        metrics = {key: None for key in metrics}
        metrics['status'] = 'MISSING'
    if forced:
        metrics.update(status=forced, strict_balanced_accuracy=None, mutant_detection_rate=None, control_false_positive_rate=None)
    return {'condition': condition, 'rule_id': rid, 'split': 'test', **metrics,
            'reported_metrics': evaluation.get('metrics') if isinstance(evaluation, dict) else None}


def _round_data(reader, summary, initial_model):
    rows, examples, patches = [], [], []
    for condition, value in summary.get('conditions', {}).items():
        for rid, loop in value.get('rules', {}).items():
            folder = Path('conditions')/condition/('task-'+_digest(str(rid))[:12])
            previous_model, previous_analysis, previous_code = initial_model, None, None
            records = list(loop.get('rounds', [])); known = {record['round'] for record in records}
            for sidecar in sorted(reader.path(folder).glob('round-*/resource-usage.json')):
                suffix = sidecar.parent.name.removeprefix('round-')
                if not suffix.isdigit() or int(suffix) in known: continue
                index = int(suffix); where = folder/sidecar.parent.name
                record = reader.read(where/'round.json')
                records.append(record if record is not None else {'round': index, 'status': 'resource_only_incomplete_round'})
                known.add(index)
            for raw in sorted(records, key=lambda record: record['round']):
                index = raw['round']; where = folder/f'round-{index:03d}'
                record = reader.read(where/'round.json', raw)
                row = {'condition': condition, 'rule_id': str(rid), 'round': index, 'status': record.get('status'),
                    'version_id': record.get('version_id'), 'model_version': record.get('model_version'),
                    'selected': record.get('version_id') == loop.get('best_version') and bool(record.get('version_id')),
                    'cross_rule_passed': record.get('cross_rule_validation', {}).get('passed'),
                    'selection_score': record.get('validation_score')}
                usage = record.get('resource_usage')
                if usage is None: usage = reader.read(where/'resource-usage.json')
                row.update(_resource_columns(usage))
                failures = record.get('failures', []) + record.get('cross_rule_validation', {}).get('failures', [])
                row['failure_types'] = sorted({kind for failure in failures for kind in failure.get('failure_types', [])})
                row['loop_stop_reason'] = loop.get('stop_reason')
                row['remaining_feedback_errors'] = loop.get('remaining_feedback_errors')
                if record.get('status') == 'candidate_failed':
                    for failure in failures[:3]:
                        examples.append({'condition': condition, 'rule_id': str(rid), 'round': index, 'split': 'feedback_compile_or_contract', 'failure': failure})
                for split, name in (('feedback', 'feedback.json'), ('validation', 'validation-evaluation.json')):
                    evaluation = reader.read(where/name)
                    if isinstance(evaluation, dict):
                        metric = metric_row(evaluation.get('records', []))
                        for key in ('valid_cases', 'negative_cases', 'controls', 'unknown', 'errors', 'strict_balanced_accuracy'):
                            row[split+'_'+key] = metric[key]
                        if split == 'feedback':
                            for failure in evaluation.get('failures', [])[:3]:
                                examples.append({'condition': condition, 'rule_id': str(rid), 'round': index, 'split': 'feedback', 'failure': failure})
                model = reader.read(where/'package/model.json'); spec = reader.read(where/'package/program-spec.json')
                code = reader.text(where/'package/checks.py')
                row['model_changed'] = model.get('node_types') != previous_model.get('node_types') if model is not None and previous_model is not None else None
                row['changed_node_types'] = sorted(k for k in set(model.get('node_types', {})) | set(previous_model.get('node_types', {}))
                    if model.get('node_types', {}).get(k) != previous_model.get('node_types', {}).get(k)) if model is not None and previous_model is not None else None
                contract = {key: spec.get(key) for key in ('requires', 'analysis_requests')} if spec is not None else None
                row['analysis_contract_changed'] = contract != previous_analysis if contract is not None and previous_analysis is not None else None
                row['generated_nonempty_code_lines'] = sum(bool(line.strip()) for line in code.splitlines()) if code is not None else None
                if code is not None and previous_code is not None and code != previous_code:
                    patches.append({'condition': condition, 'rule_id': str(rid), 'round': index,
                        'diff': ''.join(difflib.unified_diff(previous_code.splitlines(True), code.splitlines(True), fromfile='previous/checks.py', tofile='candidate/checks.py'))})
                if model is not None: previous_model = model
                if contract is not None: previous_analysis = contract
                if code is not None: previous_code = code
                rows.append(row)
    return rows, examples, patches



def _failure_partition(reader, condition, selected, current, rules, protocol, indexed):
    errors=[];prefix=condition+': '
    versions=selected.get('program_versions',{});failed=selected.get('failed_selections',{})
    if not isinstance(versions,dict) or not isinstance(failed,dict):return [prefix+'invalid selection partition']
    if (set(versions)|set(failed)!=set(rules) or set(versions)&set(failed) or
            any(not isinstance(v,str) or not v.strip() for v in versions.values())):
        errors.append(prefix+'successful/failed selections do not partition the rule inventory')
    if failed!=current.get('failed_selections',{}):errors.append(prefix+'failed selection metadata differs from summary')
    if selected.get('suite_version')!=current.get('suite_version'):errors.append(prefix+'selection/suite mismatch')
    if not failed:
        if current.get('has_complete_executable_suite') is False or selected.get('has_complete_executable_suite') is False:
            errors.append(prefix+'complete selection is declared partial without failed rules')
        return errors
    if current.get('has_complete_executable_suite') is not False or selected.get('has_complete_executable_suite') is not False:
        errors.append(prefix+'failed selection cannot claim a complete executable suite')
    limit=protocol.get('max_rounds')
    for rid,metadata in failed.items():
        label=prefix+str(rid)+': ';loop=current.get('rules',{}).get(rid,{})
        expected={'status':'terminal_failure','reason':'no_executable_candidate','stop_reason':'round_limit','rounds_completed':limit}
        if (type(limit) is not int or not 1<=limit<=5 or not isinstance(metadata,dict) or
                any(metadata.get(key)!=value for key,value in expected.items()) or type(metadata.get('rounds_completed')) is not int):
            errors.append(label+'invalid terminal failure metadata');continue
        rounds=loop.get('rounds',[])
        if (loop.get('stop_reason')!='round_limit' or loop.get('rounds_completed')!=limit or
                loop.get('best_version') is not None or loop.get('best_package_path') is not None or
                loop.get('pending_round') is not None or not isinstance(rounds,list) or len(rounds)!=limit):
            errors.append(label+'failure was not a completed round exhaustion');continue
        for index,record in enumerate(rounds):
            path=Path('conditions')/condition/('task-'+_digest(str(rid))[:12])/f'round-{index:03d}'/'round.json'
            evidence=record.get('failures',[]) if isinstance(record,dict) else []
            if (not isinstance(record,dict) or record.get('round')!=index or record.get('status')!='candidate_failed' or
                    not isinstance(evidence,list) or not any(isinstance(e,dict) and e.get('failure_types') and
                    (e.get('reason') or e.get('message') or e.get('error_type')) for e in evidence) or
                    str(path) not in indexed or reader.read(path)!=record):
                errors.append(label+'missing or mismatched failed-round evidence');break
    if not versions:
        if current.get('suite_version') is not None or current.get('suite_path') is not None:
            errors.append(prefix+'zero executable programs must not have a suite')
        return errors
    suite_path=current.get('suite_path')
    if not isinstance(suite_path,str):return errors+[prefix+'partial suite path missing']
    try:
        suite=reader.path(suite_path);manifest=reader.read(suite/'manifest.json');validation=reader.read(suite/'validation.json')
    except ValueError:return errors+[prefix+'partial suite escapes study root']
    if (not isinstance(manifest,dict) or not isinstance(validation,dict) or
            str((suite/'manifest.json').relative_to(reader.root)) not in indexed or
            str((suite/'validation.json').relative_to(reader.root)) not in indexed or
            manifest.get('version_id')!=current.get('suite_version') or
            sorted(manifest.get('program_versions',[]))!=sorted(versions.values()) or
            validation.get('status')!='passed' or validation.get('complete_rule_coverage') is not False or
            validation.get('failed_selections')!=failed):
        errors.append(prefix+'partial suite coverage/versions do not match the failure partition')
    return errors


def _failed_evaluation_valid(evaluation):
    records=evaluation.get('records',[]);metrics=evaluation.get('metrics')
    if not records or not isinstance(metrics,dict):return False
    if any(record.get('before')!='ERROR' or record.get('after')!='ERROR' or record.get('correct') is not False or
           record.get('execution_performed') is not False or record.get('failure_types')!=['no_executable_candidate'] for record in records):return False
    strict=metric_row(records)['strict_balanced_accuracy']
    return (metrics.get('strict_balanced_accuracy')==strict and metrics.get('errors')==len(records) and
            all(metrics.get(name) is None for name in ['mutant_detection_rate','control_false_positive_rate','precision','recall','f1']))

def _plots(out, report, plot_libs):
    if plot_libs is not None: sys.path.insert(0, str(Path(plot_libs).resolve()))
    os.environ.setdefault('MPLCONFIGDIR', '/data/cache/paper-compiler-matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    matplotlib.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'svg.fonttype': 'none', 'savefig.dpi': 300})
    folder = out/'figures'; folder.mkdir(); files = []
    banner = 'TEST ONLY — ' if report['test_only'] else ''
    colors = {'initial': '#777777', 'program_only': '#4477AA', 'joint': '#228833'}
    def save(fig, name):
        for extension in ('png', 'svg'):
            fig.savefig(folder/(name+'.'+extension), bbox_inches='tight', metadata={'Title': banner+name})
            files.append('figures/'+name+'.'+extension)
        plt.close(fig)
    if report['heldout_available']:
        rows = report['comparison']; rules = sorted({r['rule_id'] for r in rows})
        fig, ax = plt.subplots(figsize=(max(7, len(rules)*2), 4.5), layout='constrained')
        for offset, condition in enumerate(CONDITIONS):
            for index, rid in enumerate(rules):
                row = next(r for r in rows if r['condition'] == condition and r['rule_id'] == rid)
                x = index + (offset-1)*.24; score = row['strict_balanced_accuracy']
                if score is not None:
                    ax.bar(x, score, width=.22, color=colors[condition], label=condition if index == 0 else None)
                    ax.text(x, score+.025, f'{score:.2f}'+('\nERROR' if row['status'] == 'ERROR' else ''), ha='center', fontsize=8)
                else: ax.text(x, .04, row['status'], rotation=90, ha='center', fontsize=8)
        labels = []
        for rid in rules:
            denominator = next(r for r in rows if r['condition'] == 'joint' and r['rule_id'] == rid)
            labels.append(rid+'\nn='+str(denominator['valid_cases'])+' (V='+str(denominator['negative_cases'])+', C='+str(denominator['controls'])+')')
        ax.set(xticks=range(len(rules)), xticklabels=labels, ylabel='Strict balanced accuracy', ylim=(0, 1.15),
               title=banner+'Frozen heldout comparison')
        ax.grid(axis='y', alpha=.2); ax.set_axisbelow(True); ax.legend(frameon=False, loc='upper left', bbox_to_anchor=(1, 1))
        fig.text(.01, -.04, 'All valid cases remain in denominators. ERROR failure scores reflect unavailable execution; semantic metrics are not measured.', fontsize=8)
        save(fig, 'heldout')
    measured = [r for r in report['rounds'] if any(r.get(split+'_strict_balanced_accuracy') is not None for split in ('feedback', 'validation'))]
    if measured:
        rules = sorted({r['rule_id'] for r in measured}); fig, axes = plt.subplots(len(rules), 1, figsize=(7, max(3.2, 2.6*len(rules))), squeeze=False, layout='constrained')
        for index, rid in enumerate(rules):
            ax = axes[index, 0]
            for condition in ('program_only', 'joint'):
                selected = [r for r in measured if r['rule_id'] == rid and r['condition'] == condition]
                for split, style in (('feedback', '--'), ('validation', '-')):
                    available = [r for r in selected if r.get(split+'_strict_balanced_accuracy') is not None]
                    ax.plot([r['round'] for r in available], [r[split+'_strict_balanced_accuracy'] for r in available],
                            style, marker='o', color=colors[condition], label=condition+' / '+split)
            ax.set(title=rid, xlabel='Candidate round (initial = 0)', ylabel='Strict balanced accuracy', ylim=(-.03, 1.06),
                   xticks=sorted({r['round'] for r in measured if r['rule_id'] == rid}))
            ax.grid(alpha=.2); ax.legend(fontsize=8, frameon=False, loc='lower right')
        fig.suptitle(banner+'Feedback and validation observations — '+report['status'])
        fig.text(.01, -.025, 'Curves can coincide. Only recorded integer candidate rounds are shown; no convergence is inferred.', fontsize=8)
        save(fig, 'rounds')
    return {'renderer': 'matplotlib', 'matplotlib_version': matplotlib.__version__, 'python_version': sys.version,
            'files': files, 'missing_scores_are_not_zero': True}


def build_report(study_root, output_dir, *, interventions=None, test_only=False, plot_libs=None):
    reader = Reader(study_root); summary = reader.read('summary.json')
    if summary is None: summary = reader.read('checkpoint.json', {'status': 'incomplete', 'stop_reason': 'study_summary_and_checkpoint_missing'})
    source_status = summary.get('status', 'incomplete'); integrity = _integrity(reader, source_status == 'completed')
    protocol = reader.read('protocol.json', {}); selection = reader.read('selection-frozen.json')
    benchmark = reader.read('frozen-benchmark.json', {}); shared = reader.read('shared-initial.json', {})
    stage_resources = {}
    preparation = reader.read('initial-preparation.json')
    if isinstance(preparation, dict):
        stage_resources['initial_preparation'] = {**_cost(preparation), 'status': preparation.get('status'),
            'included_in_study_interval_total': False, 'source_path': str(reader.path('initial-preparation.json')),
            'source_sha256': reader.hashes['initial-preparation.json'],
            'note': 'Separate preparation stage interval; never added to or substituted for the study interval.'}
    initial_resources = {}
    for rid, initial in summary.get('initial', {}).items():
        usage = initial.get('resource_usage')
        if usage is None: usage = reader.read(Path('initial')/('task-'+_digest(str(rid))[:12])/'resource-usage.json')
        if usage is not None:
            initial_resources[str(rid)] = {**_resource_columns(usage),
                'note': 'Recorded initial-candidate/reuse interval inside study; do not add it again to the study total.'}
    if initial_resources: stage_resources['initial_candidates'] = initial_resources
    rules = sorted({str(c['rule_id']) for c in benchmark.get('cases', [])} | set(summary.get('initial', {})) |
                   {str(rid) for condition in summary.get('conditions', {}).values() for rid in condition.get('rules', {})})
    status = 'ERROR' if integrity['status'] == 'failed' else source_status
    protocol_errors = []
    heldout = source_status == 'completed' and integrity['status'] == 'verified' and isinstance(selection, dict) and bool(rules)
    if heldout:
        indexed = reader.read('artifact-index.json')['files']
        for condition in ('joint', 'program_only'):
            selected = selection.get('conditions', {}).get(condition, {})
            current = summary.get('conditions', {}).get(condition, {})
            protocol_errors.extend(_failure_partition(reader,condition,selected,current,rules,protocol,indexed))
            for rid in rules:
                loop = current.get('rules', {}).get(rid, {})
                folder = Path('conditions')/condition/('task-'+_digest(rid)[:12])
                expected = {case['id'] for case in benchmark.get('cases', []) if str(case['rule_id']) == rid and case.get('split') == 'test'}
                for field, name in (('final_test', 'heldout-final.json'), ('baseline_test', 'heldout-shared-initial.json')):
                    artifact = folder/name; evaluation = reader.read(artifact)
                    records = evaluation.get('records', []) if isinstance(evaluation, dict) else []
                    if (str(artifact) not in indexed or evaluation != loop.get(field) or not expected or
                            len(records) != len(expected) or {r.get('id') for r in records} != expected or
                            any(r.get('expected') not in {'PASS', 'VIOLATION'} for r in records)):
                        protocol_errors.append(condition+'/'+rid+': missing or mismatched actual heldout '+field)
                    elif field=='final_test' and rid in selected.get('failed_selections',{}) and not _failed_evaluation_valid(evaluation):
                        protocol_errors.append(condition+'/'+rid+': terminal failure grading is not explicit ERROR without execution')
        heldout = not protocol_errors
    if source_status == 'completed' and not heldout:
        status = 'ERROR'
        if not protocol_errors: protocol_errors.append('completed study lacks verified frozen selection and actual heldout records')
    failed_selections={condition:current.get('failed_selections',{}) for condition,current in summary.get('conditions',{}).items() if current.get('failed_selections')}
    if heldout and failed_selections:status='completed_with_failures'
    comparison, groups = [], []
    by_case = {c['id']: c for c in benchmark.get('cases', [])}
    for rid in rules:
        for condition in CONDITIONS:
            source = summary.get('conditions', {}).get('joint' if condition == 'initial' else condition, {}).get('rules', {}).get(rid, {})
            evaluation = source.get('baseline_test' if condition == 'initial' else 'final_test') if heldout else None
            row = _comparison(condition, rid, evaluation, None if heldout else 'ERROR' if status == 'ERROR' else 'NOT_EVALUATED')
            if condition == 'initial' and summary.get('initial', {}).get(rid, {}).get('status') == 'invalid_initial' and heldout:
                row['execution_note'] = 'Initial compile failed; recorded strict failure scoring only; semantic detection not executed.'
                row['semantic_detection_metrics'] = None
            if heldout and condition!='initial' and rid in failed_selections.get(condition,{}):
                row.update(selection_status='terminal_failure',execution_performed=False,semantic_detection_metrics=None,
                    execution_note='Failed selection: no executable candidate after the recorded round limit; strict failure scoring only, semantic detection not executed.')
            comparison.append(row)
            if isinstance(evaluation, dict):
                for axis in ('context_origin', 'evidence_domain', 'mutation_type'):
                    subsets = defaultdict(list)
                    for record in evaluation.get('records', []):
                        case = by_case.get(record['id'], {})
                        subsets[str(record.get(axis) or case.get(axis) or 'unspecified')].append(record)
                    groups.extend({'condition': condition, 'rule_id': rid, 'axis': axis, 'group': name, **metric_row(records)} for name, records in subsets.items())
    if integrity['status'] != 'failed': rounds, examples, patches = _round_data(reader, summary, shared.get('model'))
    else: rounds, examples, patches = [], [], []
    selected_changes = []
    for condition in ('joint', 'program_only'):
        current=summary.get('conditions',{}).get(condition,{})
        suite=current.get('suite_path') or Path('conditions')/condition/'suite'
        model = reader.read(Path(suite)/'manifest.json') if integrity['status'] != 'failed' and current.get('has_complete_executable_suite') is not False else None
        selected_changes.append(model['model'].get('node_types') != shared['model'].get('node_types') if model and shared.get('model') else None)
    report = {'schema_version': VERSION, 'status': status, 'source_status': source_status, 'stop_reason': summary.get('stop_reason'),
        'test_only': bool(test_only), 'heldout_available': bool(heldout), 'integrity': integrity, 'protocol_errors': protocol_errors, 'comparison': comparison, 'rounds': rounds,
        'groups': groups, 'failed_selections':failed_selections, 'cost': _cost(summary), 'stage_resources': stage_resources, 'manual_effort': _manual(interventions),
        'model_changes': {'candidate_changes': sum(row.get('model_changed') is True for row in rounds) if any(row.get('model_changed') is not None for row in rounds) else None,
            'selected_condition_changes': sum(selected_changes) if all(v is not None for v in selected_changes) else None,
            'condition_changed': dict(zip(('joint', 'program_only'), selected_changes))},
        'scope': {'observed_rules': len(rules), 'rule_ids': rules, 'validated_scaling_beyond_observed_rules': False},
        'limitations': ['Heldout is read only after recorded selection freeze and a completed hash-verified study.',
            'Model-assisted label independence and correlated-model bias require a separate audit.',
            'Controlled-catalog absence does not establish public-world nonexistence; constructed contexts are separate strata.',
            'Manual audit is self-reported; missing manual/cost/time attribution is unknown, never zero.',
            'Feedback stopping reasons are observations, not proof of convergence or scaling to 30/300 rules.'],
        'provenance': {'study_root': str(reader.root), 'source_sha256': reader.hashes,
            'benchmark_sha256': summary.get('benchmark_sha256'), 'model_config': protocol.get('model_config'),
            'selection_frozen': selection is not None, 'implementation_sha256': _sha(__file__)}}
    out = Path(output_dir).resolve()
    if out == reader.root or out.is_relative_to(reader.root): raise ValueError('report output must be separate from frozen study input')
    out.mkdir(parents=True, exist_ok=False)
    if plot_libs is None:
        configured = os.environ.get('PAPER_COMPILER_REPORT_LIBS', '/data/envs/paper-compiler-report-libs')
        plot_libs = configured if Path(configured).is_dir() else None
    report['plots'] = _plots(out, report, plot_libs)
    for name, rows in (('comparison.csv', comparison), ('rounds.csv', rounds), ('groups.csv', groups)):
        _csv(out/name, rows)
    _save(out/'examples.json', examples); _save(out/'patches.json', patches)
    banner = 'TEST ONLY — fixture results; excluded from formal experiments.\n\n' if test_only else ''
    lines = ['# Existing study results', '', banner+'Status: '+status+'; source stop reason: '+str(report['stop_reason']), '',
        'Formal heldout available: '+str(bool(heldout))+'. Observed rules: '+str(len(rules))+'.', '',
        '| Condition | Rule | Valid cases | Mutants | Controls | UNKNOWN | ERROR | Strict balanced accuracy |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for row in comparison:
        score = row['strict_balanced_accuracy']
        lines.append('| '+ ' | '.join(str(row[key]) if row[key] is not None else 'NA' for key in ('condition', 'rule_id', 'valid_cases', 'negative_cases', 'controls', 'unknown', 'errors')) + ' | '+(f'{score:.4f}' if score is not None else row['status'])+' |')
    lines.extend(['', 'Costs and elapsed time: `'+json.dumps(report['cost'], sort_keys=True)+'`.', '',
        'Separate stage resources: `'+json.dumps(report['stage_resources'], sort_keys=True)+'`.', '',
        'Round resource intervals are exported in rounds.csv/JSON. Shared-ledger intervals may include concurrent benchmark calls; no exact per-task attribution or sum of overlapping intervals is claimed.', '',
        'Human effort: `'+json.dumps(report['manual_effort'], sort_keys=True)+'`.', '',
        'Observed model changes: `'+json.dumps(report['model_changes'], sort_keys=True)+'`.', '',
        'Protocol errors: `'+json.dumps(protocol_errors)+'`.', '',
        'Terminal failed selections: `'+json.dumps(failed_selections,sort_keys=True)+'`. Failed selection rows have no executable candidate and no semantic detection; they retain explicit ERROR grading only.', '',
        'Recorded strict failure scores retain their valid denominators. An initial compile failure has no semantic detection metrics; an absent evaluation has no score.', '',
        'The separate CSV files retain effective denominators, source/evidence strata and candidate round observations. Existing feedback examples and generated code diffs are supplied as JSON; generated code lines are not human code counts.', '', *['- '+item for item in report['limitations']]])
    for name in report['plots']['files']:
        if name.endswith('.png'): lines.extend(['', '!['+name+']('+name+')'])
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    _save(out/'results.json', report)
    _save(out/'artifact-index.json', {'schema_version': VERSION, 'files': {str(p.relative_to(out)): _sha(p) for p in sorted(out.rglob('*')) if p.is_file()}})
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--study-root', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    p.add_argument('--interventions', type=Path); p.add_argument('--test-only', action='store_true'); p.add_argument('--plot-libs', type=Path)
    args = p.parse_args(argv)
    try: report = build_report(args.study_root, args.out, interventions=args.interventions, test_only=args.test_only, plot_libs=args.plot_libs)
    except Exception as error:
        print(json.dumps({'status': 'ERROR', 'error_type': type(error).__name__, 'message': 'Report generation failed; inspect existing study artifacts and plotting dependencies.'})); return 1
    print(json.dumps({'status': report['status'], 'output': str(args.out), 'heldout_available': report['heldout_available'], 'test_only': report['test_only']})); return 0


if __name__ == '__main__': sys.exit(main())
