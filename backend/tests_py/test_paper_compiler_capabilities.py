from pathlib import Path
import pytest

from paper_compiler.capabilities import ensure_capabilities, run_capability, CapabilityError


REQUEST={'name':'word_count','description':'Count whitespace separated words in node.text. Empty text has zero words.',
    'targets':['Paragraph'],'fields':{'word_count':'number'},
    'validation_cases':[
        {'input':{'node':{'text':'alpha beta'},'facts':{}},'output':{'word_count':2}},
        {'input':{'node':{'text':''},'facts':{}},'output':{'word_count':0}},
        {'input':{'node':{'text':' alpha\n beta\tthird '},'facts':{}},'output':{'word_count':3}},
    ]}


class CandidateModel:
    def __init__(self,code):self.code=code
    def complete_json(self,task,instructions,data,max_tokens):
        assert 'validation_cases' not in data['request']
        return {'name':'word_count','targets':['Paragraph'],'fields':{'word_count':'number'},'code':self.code}


def test_generated_capability_is_independently_validated_then_registered(tmp_path):
    candidate=CandidateModel("def analyze(payload):\n    return {'word_count': len(payload['node']['text'].split())}\n")
    registry=ensure_capabilities([REQUEST],{'version':'initial','capabilities':{}},candidate,tmp_path/'capabilities')
    cap=registry['capabilities']['word_count']
    assert cap['version'] and cap['validation']['passed']==3
    assert run_capability(cap,{'node':{'text':'a b c d'},'facts':{}})=={'word_count':4}
    assert registry['version']!='initial'


def test_constant_fake_capability_is_not_registered(tmp_path):
    candidate=CandidateModel("def analyze(payload):\n    return {'word_count': 2}\n")
    with pytest.raises(CapabilityError,match='validation'):
        ensure_capabilities([REQUEST],{'version':'initial','capabilities':{}},candidate,tmp_path/'capabilities')
    assert not (tmp_path/'capabilities'/'registry.json').exists()


@pytest.mark.parametrize('code',[
    "def analyze(payload):\n    return {'word_count': len(open('/etc/passwd').read())}\n",
    "import os\ndef analyze(payload):\n    return {'word_count': os.system('true')}\n",
    "def analyze(payload):\n    return {'word_count': len(payload.__class__.__mro__)}\n",
    "def analyze(payload):\n    return {'word_count': __import__('socket').socket()}\n",
])
def test_candidate_cannot_access_files_shell_or_runtime_internals(tmp_path,code):
    with pytest.raises(CapabilityError):
        ensure_capabilities([REQUEST],{'version':'initial','capabilities':{}},CandidateModel(code),tmp_path/'capabilities')


def test_missing_independent_tests_blocks_capability_promotion(tmp_path):
    request={k:v for k,v in REQUEST.items() if k!='validation_cases'}
    with pytest.raises(CapabilityError,match='independent'):
        ensure_capabilities([request],{'version':'initial','capabilities':{}},CandidateModel(''),tmp_path/'capabilities')


def test_candidate_integrity_checked_again_before_execution(tmp_path):
    candidate=CandidateModel("def analyze(payload):\n    return {'word_count': len(payload['node']['text'].split())}\n")
    registry=ensure_capabilities([REQUEST],{'version':'initial','capabilities':{}},candidate,tmp_path/'capabilities')
    cap=registry['capabilities']['word_count']
    Path(cap['code_path']).write_text("def analyze(payload):\n    return {'word_count': 999}\n")
    with pytest.raises(CapabilityError,match='hash'):
        run_capability(cap,{'node':{'text':'a'},'facts':{}})


def test_safe_type_guard_is_supported(tmp_path):
    model=CandidateModel("def analyze(payload):\n    text = payload['node']['text']\n    if not isinstance(text, str):\n        text = str(text)\n    return {'word_count':len(text.split())}\n")
    registry=ensure_capabilities([REQUEST],{'version':'initial','capabilities':{}},model,tmp_path/'out')
    assert registry['capabilities']['word_count']['validation']['passed']==3


def test_recursive_candidate_is_rejected_before_execution():
    from paper_compiler.capability_worker import validate_code
    with pytest.raises(ValueError):validate_code('def analyze(payload):\n    return analyze(payload)\n')


def test_initial_generation_can_retry_but_failed_candidate_is_preserved(tmp_path):
    class Model:
        calls=0
        def complete_json(self,*args):
            self.calls+=1
            code="def analyze(payload):\n    return {'word_count': 9}\n" if self.calls==1 else "def analyze(payload):\n    return {'word_count':len(payload['node']['text'].split())}\n"
            return CandidateModel(code).complete_json(*args)
    model=Model();registry=ensure_capabilities([REQUEST],{'version':'initial','capabilities':{}},model,tmp_path/'out')
    assert model.calls==2 and registry['capabilities']['word_count']['validation']['passed']==3
    assert (tmp_path/'out/word_count/attempt-1/validation.json').exists()
