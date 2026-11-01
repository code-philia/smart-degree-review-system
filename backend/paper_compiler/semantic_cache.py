"""Optional, short-lived reuse of exact campus semantic requests."""
import hashlib
import json
import os
from pathlib import Path
import time

from .storage import json_bytes, write_json_atomic


class SemanticResponseCache:
    TTL_SECONDS = 3600

    def __init__(self, root, endpoint, api_key, payload):
        identity = {
            'protocol': 'semantic-response/1', 'endpoint': endpoint,
            'account': hashlib.sha256(api_key.encode()).hexdigest(),
            'model_version': os.environ.get('SJTU_API_MODEL_VERSION', ''),
            'payload': payload,
        }
        self.key = hashlib.sha256(json_bytes(identity)).hexdigest()
        self.root = Path(root)
        self.path = self.root / (self.key + '.json')

    @staticmethod
    def reusable(result):
        if not isinstance(result, dict):
            return False
        if 'outcome' in result:
            return result['outcome'] in ('consistent', 'inconsistent')
        return isinstance(result.get('findings'), list) and all(
            isinstance(item, dict) for item in result['findings'])

    def read(self):
        try:
            with self.path.open('rb') as stream:
                record = json.loads(stream.read(2 * 1024 * 1024 + 1))
            if (record['key'] == self.key and record['expires_at'] > time.time()
                    and self.reusable(record['result'])):
                return record['result']
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def write(self, result):
        if not self.reusable(result):
            return
        try:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            write_json_atomic(self.path, {
                'key': self.key, 'expires_at': time.time() + self.TTL_SECONDS,
                'result': result,
            })
        except (OSError, ValueError, TypeError):
            # Cache availability must never change whether a check can run.
            pass
