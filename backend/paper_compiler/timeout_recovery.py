"""Bounded timeout recovery; every retry still uses the caller's quota/billing path."""
from contextvars import ContextVar
import re
import time
from urllib.error import URLError
import uuid

from .semantic_cache import SemanticResponseCache

_ATTEMPT = ContextVar('semantic_transport_attempt', default=None)


class ProviderReadTimeout(TimeoutError):
    def __init__(self, message=''):
        super().__init__(message or 'API response read timed out')


class ReadTimeoutExhausted(ProviderReadTimeout):
    """Only a provider read timeout that exhausted its one retry may split."""


def current_attempt():
    return _ATTEMPT.get()


def new_retry_state():
    return {'request_id':uuid.uuid4().hex,'attempt':0,'timeout_retries':0,'reason':None}


def is_socket_timeout(error):
    seen=set()
    while isinstance(error, URLError) and id(error) not in seen:
        seen.add(id(error));error=error.reason
    return isinstance(error, TimeoutError)


def is_read_timeout(error):
    return isinstance(error, ProviderReadTimeout)


def read_timeout_retry(call, *, state, remaining_time=None, observer=None):
    while True:
        if remaining_time is not None:remaining_time()
        state['attempt']+=1
        token=_ATTEMPT.set({key:state[key] for key in ('request_id','attempt','reason')})
        try:
            return call()
        except Exception as error:
            if not is_read_timeout(error):raise
            if state['timeout_retries']>=1:
                exhausted=ReadTimeoutExhausted(str(error))
                if hasattr(error,'known_model_usage'):exhausted.known_model_usage=error.known_model_usage
                raise exhausted from error
            if remaining_time is not None:remaining_time()
            state['timeout_retries']+=1;state['reason']='read_timeout'
            if observer:observer('request_timeout',{'attempt':state['attempt'],'will_retry':True})
        finally:
            _ATTEMPT.reset(token)
        # This delay does not replace either quota queue. A retry enters both
        # queues again, with its own transport receipt and conservative budget.
        delay=1.0
        if remaining_time is not None:delay=min(delay,max(0,remaining_time()))
        time.sleep(delay)


def sentence_windows(text):
    ends=[match.end() for match in re.finditer(r'[。！？；]+[”’」』"]*|[.!?;]+(?=\s|$)|\n{2,}',text)
          if 0<match.end()<len(text)]
    if not ends:return []
    cut=min(ends,key=lambda value:(abs(2*value-len(text)),-value))
    previous=max([0]+[value for value in ends if value<cut])
    # Retain the preceding complete sentence as context in the right child,
    # unless that would merely send the complete original input again.
    right=previous if previous>0 else cut
    return [(0,cut),(right,len(text))]


def _add_usage(total, usage):
    for key in total:
        value=(usage or {}).get(key,0)
        if type(value) is int and value>=0:total[key]+=value


def recover_typo_chunk(text, ask):
    """Split only a discovery input that exhausted its bounded timeout retry.

    Children are not recursively split. Candidate offsets remain relative to
    the original chunk; a failed child cannot turn the other child's coverage
    into a clean or complete result.
    """
    try:
        payload,usage=ask(text)
        return payload,usage,None,False
    except Exception as error:
        if not isinstance(error,ReadTimeoutExhausted):raise
        windows=sentence_windows(text)
        if not windows:raise
        total={'input_tokens':0,'output_tokens':0}
        _add_usage(total,getattr(error,'known_model_usage',{}))
    rows=[];failure=None
    for position,(start,end) in enumerate(windows):
        try:
            payload,usage=ask(text[start:end])
            _add_usage(total,usage)
            if not SemanticResponseCache.reusable(payload,'typo-discovery'):
                raise ValueError('invalid recovered typo discovery response')
            rows.extend({**row,'_recovery_span':(start,end),
                         '_recovery_owned_span':(0 if position==0 else windows[0][1],end)}
                        for row in payload['errors'][:20])
        except Exception as error:
            _add_usage(total,getattr(error,'known_model_usage',{}))
            failure=failure or error
    return {'errors':rows},total,failure,True
