#!/usr/bin/env python3
"""Explicit frozen-suite corpus scan, recovery, coverage and workload reporting."""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_compiler.contracts import ir_hash, validate_ir, validate_analysis
from paper_compiler.programs import STATUSES, digest, target_nodes
from paper_compiler.pipeline import load_suite
from paper_compiler.storage import json_bytes, write_json_atomic

VERSION = 'paper-corpus/1.0'


def _require(value, message):
    if not value: raise ValueError(message)


def _load(path): return json.loads(Path(path).read_text(encoding='utf-8'))


def file_hash(path):
    hasher = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): hasher.update(block)
    return hasher.hexdigest()


def _immutable(path, value):
    try: write_json_atomic(path, value, exclusive=True)
    except FileExistsError:
        _require(Path(path).read_bytes() == json_bytes(value), 'frozen corpus checkpoint changed: ' + Path(path).name)


def _inventory(path):
    value = _load(path); inventory = value.get('inventory', value)
    items = inventory.get('items')
    _require(isinstance(items, list) and bool(items), 'nonempty frozen inventory required')
    normalized = []
    for item in items:
        _require(isinstance(item, dict) and isinstance(item.get('id'), str) and
                 re.fullmatch(r'[A-Za-z0-9_-]{1,100}', item['id']), 'invalid inventory ID')
        source = item.get('path', item.get('input_path'))
        _require(isinstance(source, str) and Path(source).is_absolute(), 'inventory source path must be absolute')
        _require(isinstance(item.get('sha256'), str) and re.fullmatch('[a-f0-9]{64}', item['sha256']), 'invalid source hash')
        normalized.append({'id': item['id'], 'path': source, 'sha256': item['sha256']})
    _require(len({item['id'] for item in normalized}) == len(normalized), 'duplicate inventory ID')
    return normalized


def inspect_inventory(path, *, rule_ids=(), verify_hashes=False):
    items = _inventory(path); sizes = []
    for item in items:
        source = Path(item['path']); _require(source.is_file(), 'inventory source missing: ' + item['id'])
        sizes.append(source.stat().st_size)
        if verify_hashes: _require(file_hash(source) == item['sha256'], 'frozen source hash mismatch: ' + item['id'])
    return {'schema_version': VERSION, 'inventory_sha256': file_hash(path), 'documents': len(items),
            'distinct_content': len({item['sha256'] for item in items}), 'total_bytes': sum(sizes),
            'largest_bytes': max(sizes), 'rule_ids': list(rule_ids),
            'expected_terminal_records': len(items) * len(rule_ids),
            'hashes_verified': len(items) if verify_hashes else 0}


def _suite(path):
    packages = load_suite(path)
    _require(packages and all(p['manifest']['schema_version'] == 'paper-program/2.0' for p in packages), 'v2 suite required')
    _require(_load(Path(path)/'validation.json').get('status') == 'passed', 'behavior-validated final candidate suite required')
    rules = [p['program_spec']['rule_id'] for p in packages]
    _require(len(set(rules)) == len(rules), 'suite contains duplicate rule IDs')
    return packages


def _source_hashes():
    base = Path(__file__).resolve().parents[1]
    paths = sorted(p for p in (base/'paper_compiler').rglob('*') if p.suffix in {'.py', '.json'})
    return {str(p.relative_to(base)): file_hash(p) for p in paths + [Path(__file__).resolve()]}


def _validate_result(value, packages):
    _require(isinstance(value, dict) and {'ir', 'analysis', 'report'} <= value.keys(), 'runner must return IR, analysis and report')
    ir, analysis, report = value['ir'], value['analysis'], value['report']
    validate_ir(ir); validate_analysis(ir, analysis)
    _require(report.get('schema_version') == 'paper-check/1.0' and report.get('paper_ir_sha256') == ir_hash(ir), 'stale corpus report')
    _require(report.get('document_id') == ir['document_id'] and bool(report.get('pipeline_version')), 'unversioned corpus report')
    expected = {p['program_spec']['rule_id']: p for p in packages}
    rows = report.get('rules', [])
    _require(len(rows) == len(expected) and {r['rule_id'] for r in rows} == set(expected), 'suite rule coverage mismatch')
    for rule in rows:
        package = expected[rule['rule_id']]
        _require(rule.get('status') in STATUSES and rule.get('program_version') == package['manifest']['version_id'] and
                 rule.get('model_version') == ir['model_version'], 'rule result version/status mismatch')
        targets = target_nodes(package, ir)
        _require(all(r.get('node_id') in targets and r.get('status') in STATUSES for r in rule['results']), 'invalid object result')
    return value


def _cost(before, after):
    if before is None or after is None: return None
    fields = ('spent_cny', 'committed_cny', 'requests', 'prompt_tokens', 'completion_tokens', 'uncertain_requests')
    return {'before': before, 'after': after, 'delta': {key:
        str(Decimal(str(after[key])) - Decimal(str(before[key]))) if key.endswith('_cny') else after[key] - before[key]
        for key in fields}, 'scope': 'shared ledger interval; concurrent requests may be included'}


def _write_terminal(folder, value):
    _immutable(folder/'checkpoint.json', value)
    return value


def _evidence_levels(ids, evidence):
    pending, seen, levels = list(ids), set(), set()
    while pending:
        identifier = pending.pop()
        if identifier in seen: continue
        seen.add(identifier); item = evidence.get(identifier)
        if not item: continue
        if item.get('status') == 'ok' and item.get('coverage') in {'full_text', 'abstract_only', 'truncated_full_text'}:
            levels.add(item['coverage'])
        pending.extend(item.get('source_evidence_ids', []))
        if item.get('content_id'): pending.append(item['content_id'])
    return levels


def _summarize(identity, checkpoints, root, packages):
    records = []; statuses = defaultdict(Counter); scopes = defaultdict(Counter)
    objects = {p['program_spec']['rule_id']: Counter() for p in packages}
    evidence_counts = Counter(); content_counts = Counter(); full_objects = 0; cost_totals = Counter(); stage_totals = defaultdict(Counter)
    for checkpoint in checkpoints:
        if checkpoint.get('cost'):
            for key, number in checkpoint['cost']['delta'].items(): cost_totals[key] += Decimal(str(number))
        if checkpoint['status'] == 'completed':
            path = root/'items'/checkpoint['id']/'result.json'
            value = _validate_result(_load(path), packages); ir, analysis, report = value['ir'], value['analysis'], value['report']
            for name, stage in value.get('stage_costs', {}).items():
                if stage:
                    for key, number in stage['delta'].items(): stage_totals[name][key] += Decimal(str(number))
            ev = {e['id']: e for e in report.get('evidence', [])}
            for item in ev.values():
                evidence_counts[item.get('kind', 'content' if 'coverage' in item else 'unspecified')] += 1
                if 'coverage' in item: content_counts[item['coverage']] += 1
            for scope, coverage in ir['coverage'].items(): scopes[scope][coverage.get('status', 'unknown')] += 1
            by_rule = {r['rule_id']: r for r in report['rules']}
            for package in packages:
                rule_id = package['program_spec']['rule_id']; rule = by_rule[rule_id]; counts = objects[rule_id]
                targets = target_nodes(package, ir); by_node = defaultdict(list)
                for row in rule['results']: by_node[row['node_id']].append(row)
                counts.update(targets=len(targets), reported=len(by_node), missing=len(targets)-len(by_node), diagnostics=len(rule['results']))
                for rows in by_node.values():
                    state = next(s for s in ('ERROR', 'VIOLATION', 'UNKNOWN', 'PASS', 'NOT_APPLICABLE') if any(r['status'] == s for r in rows))
                    counts['status_' + state] += 1
                    if state in {'PASS', 'VIOLATION'}: counts['conclusive'] += 1
                    levels = _evidence_levels([e for row in rows for e in row.get('evidence_ids', [])], ev)
                    for level in levels: counts[level] += 1
                    if 'full_text' in levels: full_objects += 1
                records.append({'paper_id': checkpoint['id'], 'input_sha256': checkpoint['input_sha256'],
                    'rule_id': rule_id, 'status': rule['status'], 'attempted': True, 'suite_version': identity['suite']['version_id'],
                    'program_version': rule['program_version'], 'model_version': rule['model_version'],
                    'pipeline_version': report['pipeline_version'], 'result_sha256': checkpoint['result_sha256'],
                    'result_path': str(path), 'object_targets': len(targets), 'objects_reported': len(by_node)})
                statuses[rule_id][rule['status']] += 1
        else:
            for package in packages:
                rule_id = package['program_spec']['rule_id']; objects[rule_id]['unmeasured_documents'] += 1
                records.append({'paper_id': checkpoint['id'], 'input_sha256': checkpoint['input_sha256'],
                    'rule_id': rule_id, 'status': 'ERROR', 'attempted': checkpoint['attempted'],
                    'error_type': checkpoint['error_type'], 'suite_version': identity['suite']['version_id'],
                    'program_version': package['manifest']['version_id'], 'model_version': package['model']['version']})
                statuses[rule_id]['ERROR'] += 1
    for counts in objects.values():
        for key in ('targets', 'reported', 'missing', 'conclusive', 'full_text', 'abstract_only', 'truncated_full_text', 'unmeasured_documents'):
            counts.setdefault(key, 0)
    expected = len(identity['items']) * len(packages)
    report = {'schema_version': VERSION, 'run_id': digest(identity), 'suite_version': identity['suite']['version_id'],
        'expected_terminal_records': expected, 'terminal_records': len(records), 'complete': len(records) == expected,
        'documents_completed': sum(c['status'] == 'completed' for c in checkpoints),
        'documents_failed': sum(c['status'] != 'completed' for c in checkpoints),
        'documents_pending': len(identity['items']) - len(checkpoints),
        'all_documents_executed': len(checkpoints) == len(identity['items']) and all(c['status'] == 'completed' for c in checkpoints),
        'budget_stopped': any(c.get('error_type') in {'BudgetExceeded', 'BudgetNotRun'} for c in checkpoints),
        'rule_status_counts': {k: dict(v) for k, v in statuses.items()}, 'objects': {k: dict(v) for k, v in objects.items()},
        'scope_coverage': {k: dict(v) for k, v in scopes.items()},
        'evidence': {'kinds': dict(evidence_counts), 'content_coverage': dict(content_counts), 'full_text_objects': full_objects},
        'cost': {'measured': bool(cost_totals), 'delta': {k: str(v) for k, v in cost_totals.items()},
                 'stages': {name: {key: str(number) for key, number in totals.items()} for name, totals in stage_totals.items()},
                 'scope': 'shared ledger intervals; concurrent requests may be included'},
        'accuracy_metrics': None, 'limitation': 'Unlabelled corpus statuses and coverage are not precision or recall.'}
    fd, temporary = tempfile.mkstemp(prefix='.records-', dir=root)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            for record in records: stream.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + '\n')
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, root/'records.jsonl')
    finally:
        if Path(temporary).exists(): Path(temporary).unlink()
    report['records_sha256'] = file_hash(root/'records.jsonl')
    write_json_atomic(root/'summary.json', report)
    return report


def run_corpus(inventory, suite, output_dir, *, runner, expected_documents=None):
    """Run a whole frozen suite once per source; recovery never silently repays an uncertain attempt."""
    import fcntl
    packages = _suite(suite); items = _inventory(inventory)
    _require(expected_documents is None or len(items) == expected_documents, 'unexpected corpus document count')
    inspect_inventory(inventory, verify_hashes=True)
    _require(isinstance(getattr(runner, 'fingerprint', None), dict), 'runner needs a frozen public fingerprint')
    identity = {'schema_version': VERSION, 'inventory_sha256': file_hash(inventory), 'items': items,
        'suite': _load(Path(suite)/'manifest.json'), 'suite_validation_sha256': file_hash(Path(suite)/'validation.json'),
        'sources': _source_hashes(), 'runner': runner.fingerprint}
    root = Path(output_dir).resolve(); root.mkdir(parents=True, exist_ok=True)
    with (root/'run.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('corpus output already running') from None
        _immutable(root/'frozen.json', identity)
        checkpoints = []; stopped = False; meter = getattr(runner, 'meter', lambda: None)
        for item in items:
            folder = root/'items'/item['id']; folder.mkdir(parents=True, exist_ok=True)
            checkpoint = folder/'checkpoint.json'; result = folder/'result.json'; started = folder/'started.json'
            ownership = {'id': item['id'], 'input_sha256': item['sha256'], 'run_id': digest(identity)}
            if checkpoint.exists():
                record = _load(checkpoint)
                _require(all(record.get(k) == v for k, v in ownership.items()), 'checkpoint ownership changed')
                if record['status'] == 'completed': _require(result.is_file() and file_hash(result) == record['result_sha256'], 'completed result hash changed')
            elif started.exists():
                attempt = _load(started)
                _require(all(attempt.get(k) == v for k, v in ownership.items()), 'started ownership changed')
                if result.exists():
                    value = _validate_result(_load(result), packages)
                    record = {**ownership, 'status': 'completed', 'attempted': True, 'result_sha256': file_hash(result), 'cost': value.get('cost')}
                else: record = {**ownership, 'status': 'error', 'attempted': True, 'error_type': 'InterruptedAttempt', 'cost': _cost(attempt.get('budget_before'), meter())}
                record = _write_terminal(folder, record)
            elif stopped:
                record = _write_terminal(folder, {**ownership, 'status': 'error', 'attempted': False, 'error_type': 'BudgetNotRun'})
            else:
                _require(not result.exists(), 'orphan result has no attempt ownership')
                before = meter(); _immutable(started, {**ownership, 'budget_before': before})
                try:
                    value = runner(Path(item['path']), folder)
                    _require(file_hash(item['path']) == item['sha256'], 'source changed during execution')
                    value = {**value, 'cost': _cost(before, meter())}
                    _immutable(result, value); _validate_result(value, packages)
                    record = {**ownership, 'status': 'completed', 'attempted': True, 'result_sha256': file_hash(result), 'cost': value['cost']}
                except Exception as error:
                    record = {**ownership, 'status': 'error', 'attempted': True, 'error_type': type(error).__name__, 'cost': _cost(before, meter())}
                record = _write_terminal(folder, record)
            checkpoints.append(record)
            stopped = stopped or record.get('error_type') in {'BudgetExceeded', 'BudgetNotRun'}
        return _summarize(identity, checkpoints, root, packages)



def summarize_run(output_dir, *, suite):
    """Rebuild derived reports from verified checkpoints without configuration or APIs."""
    import fcntl
    root = Path(output_dir).resolve(); packages = _suite(suite)
    with (root/'run.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('corpus output already running') from None
        identity = _load(root/'frozen.json')
        _require(identity['suite'] == _load(Path(suite)/'manifest.json') and
                 identity['suite_validation_sha256'] == file_hash(Path(suite)/'validation.json'), 'summary suite changed')
        checkpoints = []
        for item in identity['items']:
            folder = root/'items'/item['id']; checkpoint = folder/'checkpoint.json'
            if not checkpoint.exists(): continue
            record = _load(checkpoint)
            _require(record.get('id') == item['id'] and record.get('input_sha256') == item['sha256'] and
                     record.get('run_id') == digest(identity), 'checkpoint ownership changed')
            if record['status'] == 'completed':
                _require(file_hash(folder/'result.json') == record['result_sha256'], 'completed result hash changed')
            checkpoints.append(record)
        return _summarize(identity, checkpoints, root, packages)


def estimate_workload(inventory, *, suite=None, ir_paths=()):
    items = _inventory(inventory); packages = _suite(suite) if suite else []
    source_hashes = {i['sha256'] for i in items}; samples = []; seen = set()
    for path in ir_paths:
        ir = _load(path); validate_ir(ir)
        hashes = {s.get('sha256') for s in ir['source_artifacts']} | {file_hash(path)}
        matching = hashes & source_hashes
        if not matching or matching & seen: continue
        seen.update(matching)
        kinds = Counter(node['kind'] for node in ir['nodes'])
        requests = {r['name']: r for p in packages for r in p['program_spec']['analysis_requests'] if r['name'] in p['program_spec']['requires']}
        generated = sum(sum(node['kind'] in r['targets'] for node in ir['nodes']) for r in requests.values())
        # Two optional frontend/model calls, bibliography batches, generated target calls.
        bibliography = (kinds['BibliographyEntry'] + 1)//2
        samples.append({'ir_path': str(path), 'bibliography_entries': kinds['BibliographyEntry'], 'reference_uses': kinds['ReferenceUse'],
                        'generated_target_calls': generated, 'cold_call_opportunities': 2 + bibliography + generated,
                        'illustrative_one_request_per_entry_and_use': 2 + bibliography + kinds['BibliographyEntry'] + kinds['ReferenceUse']})
    count = len(items); ranges = {}
    if samples:
        for key in ('bibliography_entries', 'reference_uses', 'cold_call_opportunities', 'illustrative_one_request_per_entry_and_use'):
            ranges[key] = {'minimum': min(s[key] for s in samples)*count, 'maximum': max(s[key] for s in samples)*count}
    return {'schema_version': VERSION, 'corpus_documents': count, 'observed_ir_documents': len(samples), 'samples': samples,
        'sample_is_representative': False, 'conditional_extrapolation': ranges,
        'paid_call_range': {'minimum': 0, 'maximum': ranges.get('cold_call_opportunities', {}).get('maximum') if packages else None},
        'currency_estimate_cny': None, 'limitations': 'Conditional historical sample extrapolation is not a guaranteed upper bound; final suite, target counts, source lengths, cache hits and evidence availability are unknown. Actual currency requires a metered pilot on the same ledger.'}


def parser():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('command', choices=['inspect', 'estimate', 'run', 'summarize'])
    p.add_argument('--inventory', type=Path); p.add_argument('--suite', type=Path); p.add_argument('--out', type=Path, required=True)
    p.add_argument('--rule', action='append', default=[]); p.add_argument('--ir', type=Path, action='append', default=[])
    p.add_argument('--verify-hashes', action='store_true'); p.add_argument('--expected-documents', type=int, default=479)
    p.add_argument('--config', default='/data/apps/smart-degree-review/config/paper-model-huawei.env')
    p.add_argument('--ledger', type=Path, default=Path('/data/runtime/paper-compiler/budget.sqlite3'))
    p.add_argument('--cache', type=Path, default=Path('/data/runtime/paper-compiler')); p.add_argument('--budget', default='200')
    p.add_argument('--phase', default='final-corpus'); p.add_argument('--phase-budget', default='200'); p.add_argument('--evidence-snapshot')
    p.add_argument('--offline', action='store_true')
    p.add_argument('--publication-review', action='store_true')
    return p


def execute(args):
    if args.command == 'summarize':
        _require(args.suite is not None, '--suite is required')
        return summarize_run(args.out, suite=args.suite)
    _require(args.inventory is not None, '--inventory is required')
    if args.command == 'inspect':
        value = inspect_inventory(args.inventory, rule_ids=args.rule, verify_hashes=args.verify_hashes)
    elif args.command == 'estimate': value = estimate_workload(args.inventory, suite=args.suite, ir_paths=args.ir)
    else:
        _require(args.suite is not None, '--suite is required')
        _require(bool(args.evidence_snapshot), 'explicit frozen --evidence-snapshot is required')
        total = Decimal(args.budget)
        _require(total.is_finite() and 0 < total <= 400, 'cumulative budget limit must be positive and at most 400 CNY')
        phase = Decimal(args.phase_budget)
        _require(phase.is_finite() and 0 < phase <= 400, 'phase budget limit must be positive and at most 400 CNY')
        from paper_compiler.frontend import build_paper
        from paper_compiler.pipeline import detect
        from paper_compiler.llm import MaasClient, public_model_config
        from paper_compiler.budget import BudgetLedger
        from paper_compiler.evidence import EvidenceGateway
        from paper_compiler.program_analysis import analysis_execution_policy
        analysis_policy = analysis_execution_policy()
        packages = _suite(args.suite)
        if args.rule: _require(len(args.rule) == len(set(args.rule)) and set(args.rule) == {p['program_spec']['rule_id'] for p in packages}, 'declared final rule set does not match suite')
        if not args.offline: _require(args.ledger.is_file(), 'use the existing shared budget ledger; new ledgers are forbidden')
        ledger = None if args.offline else BudgetLedger(args.ledger, Decimal(args.budget))
        client = None if args.offline else MaasClient(args.config, ledger, args.cache/'model-cache', args.phase, Decimal(args.phase_budget), max_attempts=1, json_output=args.publication_review)
        gateway = None if args.offline else EvidenceGateway(args.cache/'public-evidence', snapshot_id=args.evidence_snapshot,
            proxy=os.environ.get('PAPER_COMPILER_PUBLIC_PROXY', 'http://127.0.0.1:18892'))
        def runner(path, folder):
            before = ledger.summary() if ledger else None
            ir = build_paper(path, client=client) if path.suffix.lower() == '.pdf' else _load(path)
            middle = ledger.summary() if ledger else None
            materialized, analysis, report = detect(ir, packages, client=client, gateway=gateway, cache_dir=args.cache)
            if args.publication_review:
                from paper_compiler.publication_gate import audit_positives
                reviewed = audit_positives(materialized, analysis, report, packages, client=client, gateway=gateway,
                    output_dir=folder/'publication')
                report['publication'] = {'public': reviewed['public'],
                    'artifact': str(Path(reviewed['internal']['output_dir'])/'result.json')}
            after = ledger.summary() if ledger else None
            return {'ir': materialized, 'analysis': analysis, 'report': report,
                    'stage_costs': {'frontend': _cost(before, middle), 'pipeline': _cost(middle, after)}}
        runner.fingerprint = {'semantic_model': public_model_config(client.config) if client else None,
            'evidence_snapshot': args.evidence_snapshot, 'providers': gateway.providers if gateway else [],
            'offline': args.offline, 'ledger': str(args.ledger.resolve()), 'cache': str(args.cache.resolve()),
            'budget': args.budget, 'phase': args.phase, 'phase_budget': args.phase_budget,
            'analysis_execution_policy': analysis_policy}
        if args.publication_review: runner.fingerprint['publication_review'] = True
        if ledger: runner.meter = ledger.summary
        return run_corpus(args.inventory, args.suite, args.out, runner=runner, expected_documents=args.expected_documents)
    write_json_atomic(args.out, value, exclusive=True)
    return value


def main(argv=None):
    try: value = execute(parser().parse_args(argv))
    except Exception as error:
        print(json.dumps({'status': 'error', 'error_type': type(error).__name__, 'message': 'Corpus operation failed; inspect frozen artifacts and the existing budget ledger.'})); return 1
    print(json.dumps(value, ensure_ascii=True)); return 0


if __name__ == '__main__': sys.exit(main())
