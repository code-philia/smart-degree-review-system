"""Run numeric review on read-only PDFs; save private evaluation outputs, not application DBs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_bilingual_semantic_lint as runtime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--index', type=int, choices=[1, 2], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    pdf = sorted(args.input_dir.glob('*.pdf'))[args.index-1]
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ['PAPER_NUMERIC_RUNS_DIR'] = str(args.output / 'runs')
    started = time.monotonic()
    result = runtime.run(pdf, [runtime.NUMERIC_RULE], run_id='real-paper-' + str(uuid.uuid4()))
    require_unchanged = hashlib.sha256(pdf.read_bytes()).hexdigest() == digest
    if not require_unchanged:
        raise RuntimeError('Input PDF changed during review')
    run = result['rule_runs'][0]
    output = {'source': {'filename': pdf.name, 'sha256': digest}, 'elapsed_seconds': time.monotonic()-started, 'result': result}
    (args.output / 'review.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'filename': pdf.name, 'elapsed_seconds': output['elapsed_seconds'],
        'execution_status': run['execution_status'], 'outcome': run['outcome'], 'message': run.get('message'),
        'failure': run['params'].get('failure'), 'usage': run['model_usage'], 'trace': run['params'].get('trace'),
        'preconditions': run['params'].get('preconditions'), 'declarations': run['params'].get('declarations'),
        'results': [{'id': row['declaration_id'], 'status': row['status'], 'reason': row['reason'],
                     'evidence': row.get('evidence_quote'), 'page': row.get('evidence_page')} for row in run['params'].get('numeric_results', [])]}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
