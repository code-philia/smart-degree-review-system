#!/usr/bin/env python3
"""Explicit, metered entry point for the frozen joint/program-only study."""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tasks', type=Path, required=True)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--resources', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--config', default='/data/apps/smart-degree-review/config/paper-model-huawei.env')
    p.add_argument('--ledger', type=Path, default=Path('/data/runtime/paper-compiler/budget.sqlite3'))
    p.add_argument('--budget', default='200')
    p.add_argument('--cache', type=Path, default=Path('/data/runtime/paper-compiler'))
    p.add_argument('--paper-model', type=Path)
    p.add_argument('--max-rounds', type=int, default=5)
    return p


def execute(args):
    from paper_compiler.budget import BudgetLedger
    from paper_compiler.evidence import EvidenceGateway
    from paper_compiler.llm import MaasClient
    from paper_compiler.pipeline import detect
    from paper_compiler.programs import digest
    from paper_compiler.study import run_study
    from paper_compiler.program_analysis import analysis_execution_policy

    budget = Decimal(args.budget)
    if not budget.is_finite() or not 0 < budget <= 200:
        raise ValueError('study cumulative budget must be positive and at most 200 CNY')
    value = json.loads(args.tasks.read_text(encoding='utf-8'))
    tasks = value['tasks'] if isinstance(value, dict) else value
    resources = json.loads(args.resources.read_text(encoding='utf-8')) if args.resources else {}
    initial_model = json.loads(args.paper_model.read_text(encoding='utf-8')) if args.paper_model else None
    analysis_policy = analysis_execution_policy()
    ledger = BudgetLedger(args.ledger, budget)
    client = MaasClient(args.config, ledger, args.cache / 'model-cache', 'framework-20261019', budget, max_attempts=1)
    snapshot = resources.get('evidence_snapshot') or 'study-' + hashlib.sha256(args.manifest.read_bytes()).hexdigest()[:24]
    gateway = EvidenceGateway(args.cache / 'public-evidence', snapshot_id=snapshot,
        proxy=os.environ.get('PAPER_COMPILER_PUBLIC_PROXY', 'http://127.0.0.1:18892'))
    by_id = {str(task['rule_id']): task for task in tasks}

    def runner(package, ir):
        task = by_id[str(package['program_spec']['rule_id'])]
        environment = None
        if task.get('evidence_environment') == 'controlled_catalog':
            environment = resources.get('evidence_environment')
            if not isinstance(environment, dict) or environment.get('domain') != 'controlled_catalog':
                raise ValueError('task requires an explicit controlled catalog resource')
        return detect(ir, [package], client=client, gateway=gateway, cache_dir=args.cache,
                      evidence_environment=environment)[2]
    runner.study_fingerprint = digest({'evidence_snapshot': snapshot, 'resources': resources,
        'task_environments': {key: task.get('evidence_environment') for key, task in by_id.items()},
        'providers': gateway.providers, 'analysis_execution_policy': analysis_policy})
    return run_study(tasks, args.manifest, client=client, output_dir=args.out, runner=runner,
                     max_rounds=args.max_rounds, initial_model=initial_model)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = execute(args)
    except Exception as error:
        print(json.dumps({'status': 'error', 'error_type': type(error).__name__,
                          'message': 'Study operation failed; inspect saved artifacts and the existing budget ledger.'}))
        return 1
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    return 0 if result['status'] == 'completed' else 2


if __name__ == '__main__':
    sys.exit(main())
