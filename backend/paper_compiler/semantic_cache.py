"""Optional, short-lived reuse of exact campus semantic requests."""
import hashlib
import json
import os
from pathlib import Path
import time

from .storage import json_bytes, write_json_atomic


class SemanticResponseCache:
    TTL_SECONDS = 3600

    def __init__(self, root, endpoint, api_key, payload, *, response_contract=None):
        identity = {
            'protocol': 'semantic-response/1', 'endpoint': endpoint,
            'account': hashlib.sha256(api_key.encode()).hexdigest(),
            'model_version': os.environ.get('SJTU_API_MODEL_VERSION', ''),
            'payload': payload,
        }
        self.response_contract = response_contract
        if response_contract:
            identity['response_contract'] = response_contract
        self.key = hashlib.sha256(json_bytes(identity)).hexdigest()
        self.root = Path(root)
        self.path = self.root / (self.key + '.json')

    @staticmethod
    def reusable(result, response_contract=None):
        if not isinstance(result, dict):
            return False
        if response_contract == 'typo-discovery' and 'errors' not in result:
            return False
        if response_contract in ('typo-review', 'typo-fields'):
            if 'accepted' not in result:
                return False
            if response_contract == 'typo-review' and not set(result) <= {'accepted', 'reason'}:
                return False
            if response_contract == 'typo-fields' and result.get('accepted') is True and not all(
                    key in result for key in ('original', 'corrected')):
                return False
        # A provider/error envelope must never become a successful chunk cache.
        if any(key in result for key in ('error', 'error_type', 'technical_failure')):
            return False
        if 'errors' in result:
            return (set(result) == {'errors'} and isinstance(result['errors'], list)
                    and all(isinstance(row, dict) and all(
                        isinstance(row.get(key), str) and row[key].strip()
                        for key in ('original', 'corrected', 'context', 'reason'))
                            for row in result['errors']))
        if 'accepted' in result:
            return (type(result['accepted']) is bool
                    and set(result) <= {'accepted', 'original', 'corrected', 'reason'}
                    and isinstance(result.get('reason'), str) and bool(result['reason'].strip())
                    and (('original' not in result and 'corrected' not in result)
                         or all(isinstance(result.get(key), str) and result[key].strip()
                                for key in ('original', 'corrected'))))
        if 'outcome' in result:
            return result['outcome'] in ('consistent', 'inconsistent')
        return isinstance(result.get('findings'), list) and all(
            isinstance(item, dict) for item in result['findings'])

    def read(self):
        try:
            with self.path.open('rb') as stream:
                record = json.loads(stream.read(2 * 1024 * 1024 + 1))
            if (record['key'] == self.key and record['expires_at'] > time.time()
                    and self.reusable(record['result'], self.response_contract)):
                return record['result']
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def write(self, result):
        if not self.reusable(result, self.response_contract):
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
