"""Private, append-only records for the numeric rule; no credentials are serialized."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid


class NumericRunTrace:
    def __init__(self, ir, task_id=None, root=None):
        self.run_id = str(uuid.uuid4())
        configured = root or os.environ.get('PAPER_NUMERIC_RUNS_DIR')
        if not configured:
            reports = Path(os.environ.get('PAPER_LINT_REPORTS_DIR', str(Path(__file__).resolve().parents[1] / 'data' / 'paper-lint-reports')))
            configured = reports.parent / 'numeric-runs'
        Path(configured).mkdir(parents=True, mode=0o700, exist_ok=True)
        self.path = Path(configured) / self.run_id
        self.path.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.path.chmod(0o700)
        self.secrets = [v for k, v in os.environ.items() if any(s in k.upper() for s in ('API_KEY', 'TOKEN', 'PASSWORD', 'SECRET', 'AUTHORIZATION')) and len(v) > 5]
        self.sequence = 0
        self.call_number = 0
        self.started = time.monotonic()
        try:
            commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=Path(__file__).resolve().parents[2], text=True, timeout=5).strip()
            dirty = subprocess.run(['git', 'diff', '--quiet', 'HEAD', '--'], cwd=Path(__file__).resolve().parents[2], timeout=5).returncode != 0
        except (OSError, subprocess.SubprocessError):
            commit = os.environ.get('APP_COMMIT', 'unknown')
            dirty = None
        self.manifest = {'schema_version': 'numeric-run/1.0', 'run_id': self.run_id, 'task_id': task_id,
                         'code_commit': commit, 'working_tree_dirty': dirty, 'started_at': time.time(), 'model_version': ir.get('model_version'),
                         'paper_model_schema': ir.get('schema_version'), 'paper_model_revision': ir.get('revision'),
                         'pdf_sha256': next((a.get('sha256') for a in ir.get('source_artifacts', []) if a.get('kind') == 'pdf'), None),
                         'status': 'running', 'artifacts': []}
        self.manifest['implementation_sha256'] = {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                                                  for name in ('numeric_consistency.py', 'numeric_run_trace.py', 'run_bilingual_semantic_lint.py')}
        self.save('paper_model', ir)
        self.write('running.json', self.manifest)

    def clean(self, value):
        if isinstance(value, dict):
            return {k: self.clean(v) for k, v in value.items() if k.lower() not in {'authorization', 'api_key', 'password', 'secret', 'headers'}}
        if isinstance(value, list):
            return [self.clean(v) for v in value]
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, '[REDACTED]')
        return value

    def write(self, filename, data):
        raw = json.dumps(self.clean(data), ensure_ascii=False, allow_nan=False, indent=2).encode('utf-8')
        target = self.path / filename
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
        return hashlib.sha256(raw).hexdigest()

    def save(self, kind, data):
        self.sequence += 1
        name = f'{self.sequence:03d}-{kind}.json'
        digest = self.write(name, data)
        self.manifest['artifacts'].append({'kind': kind, 'file': name, 'sha256': digest})

    def __call__(self, kind, data):
        self.save(kind, data)

    def call(self, transport, messages):
        self.call_number += 1
        number = self.call_number
        started = time.monotonic()
        self.save('call_input', {'call_number': number, 'messages': messages})
        try:
            payload, usage = transport(messages, observer=self.save)
            self.save('call_result', {'call_number': number, 'parsed': payload, 'usage': usage, 'elapsed_seconds': time.monotonic()-started})
            return payload, usage
        except Exception as exc:
            self.save('call_error', {'call_number': number, 'type': type(exc).__name__, 'message': str(exc), 'elapsed_seconds': time.monotonic()-started})
            raise

    def finish(self, result):
        self.manifest.update(status=result['execution_status'], elapsed_seconds=time.monotonic()-self.started,
                             versions=result.get('params', {}).get('versions'), failure=result.get('params', {}).get('failure'))
        result['params']['trace'] = {'run_id': self.run_id, 'task_id': self.manifest['task_id'], 'schema_version': 'numeric-run/1.0'}
        self.save('report', result)
        self.write('manifest.json', self.manifest)
        return result


def load_replay(path):
    """Return recorded stage inputs and outputs, validating artifact hashes. No network."""
    path = Path(path)
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    artifacts = {}
    for item in manifest['artifacts']:
        target = (path / item['file']).resolve()
        if target.parent != path.resolve():
            raise ValueError('Unsafe trace artifact path')
        raw = target.read_bytes()
        if hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('Trace artifact hash mismatch')
        artifacts.setdefault(item['kind'], []).append(json.loads(raw))
    return manifest, artifacts
