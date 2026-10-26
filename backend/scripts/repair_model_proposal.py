"""Repair suggestions use the existing model credential and cumulative ledger."""
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_compiler.budget import BudgetExceeded, BudgetLedger
from paper_compiler.llm import MaasClient, ModelError, load_config
from paper_compiler.storage import json_bytes

DEFAULT_LEDGER = Path('/data/runtime/paper-compiler/budget.sqlite3')
DEFAULT_CACHE_ROOT = Path('/data/runtime/paper-compiler/repair-model-cache')

def model_identity(config_path):
    config = load_config(config_path)
    return {'model': config['MAAS_MODEL'], 'modelVersion': config.get('MAAS_MODEL_VERSION', 'unknown'), 'provider': config.get('MODEL_PROVIDER', 'huawei_maas')}

def execute(messages, *, config_path, ledger, cache, transport=None):
    if not isinstance(messages, list) or len(messages) != 2:
        raise ValueError('expected system and user messages')
    if messages[0].get('role') != 'system' or messages[1].get('role') != 'user':
        raise ValueError('invalid message roles')
    client = MaasClient(config_path, ledger, cache, 'website', os.environ.get('PAPER_COMPILER_PHASE_BUDGET_CNY', '10'), transport=transport,
                        max_attempts=1, timeout=60, json_output=True, input_serialization='unicode-json/1.0')
    # A user-requested generation must never replay the model transport cache.
    data = {'request': json.loads(messages[1]['content']), 'generation': uuid.uuid4().hex}
    task = 'repair-suggestion/1.0'
    for attempt in range(2):
        try:
            answer = client.complete_json(task, messages[0]['content'], data, 1024)
            break
        except ModelError as error:
            if attempt or not str(error).endswith((': timeout', ': transport')):
                raise
    fingerprint = client.request_fingerprint(task, messages[0]['content'], data, 1024)
    key = hashlib.sha256(json_bytes(fingerprint)).hexdigest()
    usage = json.loads((Path(cache) / 'responses' / (key + '.json')).read_text())['usage']
    return {'answer': answer, **model_identity(config_path), 'usage': {
        'input_tokens': usage['prompt_tokens'], 'output_tokens': usage['completion_tokens'], 'attempts': attempt + 1}}

def main():
    campus_configured = all(
        os.environ.get(name, '').strip()
        for name in ('SJTU_API_KEY', 'SJTU_API_BASE_URL', 'SJTU_API_MODEL')
    )
    config = (
        ':env:' if campus_configured
        else os.environ.get('REPAIR_MODEL_CONFIG')
        or os.environ.get('SJTU_CONFIG_PATH')
        or os.environ.get('PAPER_COMPILER_CONFIG')
    )
    if not config:
        raise ValueError('model credential configuration missing')
    if sys.argv[1:] == ['--info']:
        return model_identity(config)
    raw = sys.stdin.buffer.read(131073)
    if len(raw) > 131072:
        raise ValueError('repair request too large')
    ledger = BudgetLedger(
        Path(os.environ.get('PAPER_COMPILER_LEDGER', DEFAULT_LEDGER)),
        os.environ.get('PAPER_COMPILER_BUDGET_CNY', '500'),
    )
    cache = Path(os.environ.get('PAPER_COMPILER_CACHE_ROOT', DEFAULT_CACHE_ROOT))
    return execute(json.loads(raw)['messages'], config_path=config, ledger=ledger, cache=cache)

if __name__ == '__main__':
    def interrupted(*_):
        raise TimeoutError('repair generation interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    try:
        output = main()
    except BudgetExceeded:
        output = {'status': 'error', 'http_status': 429, 'message': '修复建议预算已用尽，请联系管理员'}
    except (ModelError, TimeoutError):
        output = {'status': 'error', 'http_status': 502, 'message': '修复建议模型未完成请求，请稍后查看已保存建议'}
    except Exception:
        output = {'status': 'error', 'http_status': 503, 'message': '修复建议模型或费用账本配置不可用'}
    print(json.dumps(output, ensure_ascii=False))
    sys.exit(1 if output.get('status') == 'error' else 0)
