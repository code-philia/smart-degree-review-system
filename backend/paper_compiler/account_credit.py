"""Account-scoped token receipts; caller identity is established by the Node worker.

All values are integer nanoyuan. No prompts, API keys or source text are stored.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

POLICY = json.loads((Path(__file__).resolve().parents[2] / 'shared/paper-lint-credit-policy.json').read_text())
_RULE = ContextVar('paper_lint_credit_rule', default=None)
_INSUFFICIENT = '可用额度不足，无法继续模型检测；您仍可使用不消耗额度的规则。'


class CreditError(RuntimeError):
    code = 'PAPER_LINT_CREDIT'


class RequestNotSentError(CreditError):
    """A billing preflight rejected the request before its transport callback."""
    request_not_sent = True


def _now():
    return datetime.now(timezone.utc).isoformat()


def _integer(value):
    if type(value) is not int or not 0 <= value <= 2**53-1:
        raise ValueError('invalid token count')
    return value


def usage_nano(usage, rates=None):
    if not isinstance(usage, dict):
        raise ValueError('missing usage')
    rates = rates or POLICY
    prompt = _integer(usage.get('prompt_tokens'))
    output = _integer(usage.get('completion_tokens'))
    if 'total_tokens' in usage and _integer(usage['total_tokens']) != prompt + output:
        raise ValueError('inconsistent total tokens')
    details = usage.get('prompt_tokens_details')
    if details is not None and not isinstance(details, dict):
        raise ValueError('invalid cache details')
    hit = usage.get('prompt_cache_hit_tokens', (details or {}).get('cached_tokens'))
    miss = usage.get('prompt_cache_miss_tokens')
    if hit is None:
        hit = prompt - _integer(miss) if miss is not None else 0
    hit = _integer(hit)
    if hit > prompt or (miss is not None and _integer(miss) + hit != prompt):
        raise ValueError('inconsistent cache tokens')
    if details and details.get('cached_tokens') is not None and _integer(details['cached_tokens']) != hit:
        raise ValueError('conflicting cache details')
    amount = ((prompt-hit)*rates['ordinary_input_nano_per_token']
              + hit*rates['cached_input_nano_per_token'] + output*rates['output_nano_per_token'])
    return amount, prompt, hit, output


@contextmanager
def billing_rule(rule_id):
    token = _RULE.set(rule_id)
    try:
        yield
    finally:
        _RULE.reset(token)


class AccountCredit:
    def __init__(self, database_file, operation_id):
        self.path = Path(database_file).resolve(strict=True)
        self.operation_id = operation_id

    @contextmanager
    def _transaction(self):
        db = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def reserve(self, rule_id, payload, *, call_id=None):
        if rule_id not in POLICY['estimated_cny'] or payload.get('model') not in POLICY['models']:
            raise CreditError('模型检测额度配置无效，请联系管理员。')
        output = payload.get('max_completion_tokens', payload.get('max_tokens'))
        if type(output) is not int or not 1 <= output <= 65536:
            raise CreditError('模型检测额度配置无效，请联系管理员。')
        # Escaped input bytes plus framing are an upper bound, not a fixed fee.
        input_bound = len(json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode()) + 1024
        reserved = input_bound*POLICY['ordinary_input_nano_per_token'] + output*POLICY['output_nano_per_token']
        call_id = call_id or uuid4().hex
        with self._transaction() as db:
            op = db.execute('''SELECT o.*,j.status AS job_status,j.attempts,j.cancelled_at,j.selected_rule_ids_json
                FROM paper_lint_credit_operations o JOIN paper_lint_jobs j ON j.id=o.job_id
                WHERE o.id=? AND j.user_id=o.user_id''', [self.operation_id]).fetchone()
            if (not op or op['state'] != 'active' or op['job_status'] != 'running' or op['cancelled_at']
                    or op['job_attempt'] != op['attempts'] or rule_id not in json.loads(op['selected_rule_ids_json'])):
                raise CreditError('当前检测任务已停止，无法继续调用模型。')
            existing = db.execute('SELECT * FROM paper_lint_credit_calls WHERE id=?', [call_id]).fetchone()
            if existing:
                if (existing['operation_id'],existing['rule_id'],existing['model'],existing['input_bound'],existing['output_bound']) != (
                        self.operation_id,rule_id,payload['model'],input_bound,output):
                    raise CreditError('Invalid credit call identity')
                return call_id
            changed = db.execute('''UPDATE paper_lint_credit_accounts SET reserved_nano=reserved_nano+?
                WHERE user_id=? AND granted_nano-spent_nano-reserved_nano>=?''', [reserved,op['user_id'],reserved])
            if changed.rowcount != 1:
                raise CreditError(_INSUFFICIENT)
            now = _now()
            db.execute('''INSERT INTO paper_lint_credit_calls
                (id,operation_id,rule_id,model,rate_version,rates_json,input_bound,output_bound,reserved_nano,status,worker_pid,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,'reserved',?,?,?)''', [call_id,self.operation_id,rule_id,payload['model'],
                POLICY['version'],json.dumps(POLICY),input_bound,output,reserved,os.getpid(),now,now])
        return call_id

    def settle(self, call_id, response):
        usage = response.get('usage') if isinstance(response, dict) else None
        with self._transaction() as db:
            call = db.execute('''SELECT c.*,o.user_id FROM paper_lint_credit_calls c
                JOIN paper_lint_credit_operations o ON o.id=c.operation_id WHERE c.id=? AND c.operation_id=?''',
                [call_id,self.operation_id]).fetchone()
            if not call:
                raise CreditError('Invalid credit call identity')
            if call['status'] != 'reserved':
                return call['charged_nano']
            amount = prompt = cached = output = None
            status, failure = 'settled', None
            try:
                amount,prompt,cached,output = usage_nano(usage,json.loads(call['rates_json']))
                if amount > call['reserved_nano'] or prompt > call['input_bound'] or output > call['output_bound']:
                    raise ValueError('usage exceeds reserved request bounds')
            except ValueError:
                amount = 0
                status,failure = ('unknown','missing_usage') if usage is None else ('invalid_usage','invalid_usage')
            db.execute('''UPDATE paper_lint_credit_accounts SET reserved_nano=reserved_nano-?,spent_nano=spent_nano+? WHERE user_id=?''',
                       [call['reserved_nano'],amount,call['user_id']])
            db.execute('''UPDATE paper_lint_credit_calls SET status=?,charged_nano=?,input_tokens=?,cached_tokens=?,output_tokens=?,
                usage_json=?,failure_code=?,updated_at=? WHERE id=? AND status='reserved' ''',
                [status,amount,prompt,cached,output,json.dumps(usage,ensure_ascii=True),failure,_now(),call_id])
            return amount

    def failed(self, call_id, error):
        status_code = getattr(error,'code',getattr(error,'status',None))
        known_rejected = isinstance(status_code,int) and 400 <= status_code < 500
        with self._transaction() as db:
            call = db.execute('''SELECT c.*,o.user_id FROM paper_lint_credit_calls c JOIN paper_lint_credit_operations o
                ON o.id=c.operation_id WHERE c.id=? AND c.operation_id=? AND c.status='reserved' ''',[call_id,self.operation_id]).fetchone()
            if not call:
                return
            db.execute('UPDATE paper_lint_credit_accounts SET reserved_nano=reserved_nano-? WHERE user_id=?', [call['reserved_nano'],call['user_id']])
            db.execute('UPDATE paper_lint_credit_calls SET status=?,failure_code=?,updated_at=? WHERE id=?',
                ['released' if known_rejected else 'unknown',f'http_{status_code}' if isinstance(status_code,int) else type(error).__name__,_now(),call_id])


def bill_model_request(payload, send, *, rule_id=None):
    context = os.environ.get('PAPER_LINT_CREDIT_CONTEXT','').strip()
    if not context or str(payload.get('model','')).lower().startswith('qwen'):
        return send()
    try:
        value = json.loads(context)
        if set(value) != {'database_file','operation_id'} or not all(isinstance(v,str) and v for v in value.values()):
            raise ValueError('invalid credit context')
        credit = AccountCredit(value['database_file'],value['operation_id'])
    except (ValueError,KeyError,OSError,TypeError) as error:
        raise RequestNotSentError('模型检测额度配置无效，请联系管理员。') from error
    try:
        call_id = credit.reserve(rule_id or _RULE.get(),payload)
    except CreditError as error:
        raise RequestNotSentError(str(error)) from error
    try:
        raw = send()
    except BaseException as error:
        credit.failed(call_id,error)
        raise
    try:
        response = json.loads(raw) if isinstance(raw,(str,bytes,bytearray)) else raw
    except (ValueError,UnicodeError):
        response = None
    credit.settle(call_id,response)
    return raw
