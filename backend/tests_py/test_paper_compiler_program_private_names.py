"""Private-variable diagnostics preserve the existing pure Python policy."""
import pytest
from paper_compiler import program_worker as candidate

@pytest.mark.parametrize('code,name,line,column',[
    ("def detect(payload):\n    _hidden = 1\n    return []",'_hidden',2,5),
    ("def detect(payload):\n    return _cached",'_cached',2,12),
    ("def detect(payload):\n    if True:\n        vals = [v for v, _ in [(1,2)]]\n    return []",'_',3,26),
])
def test_private_name_diagnostic_identifies_exact_identifier_and_ast_location(code,name,line,column):
    with pytest.raises(ValueError) as caught:candidate.validate_code(code)
    message=str(caught.value)
    assert message.startswith('private names forbidden:')
    assert repr(name) in message
    assert f'line {line}, UTF-8 byte column {column}' in message

@pytest.mark.parametrize('entry',['detect','propose','analyze'])
def test_all_existing_entrypoints_report_private_identifier_location(entry):
    with pytest.raises(ValueError) as caught:candidate.validate_code(f'def {entry}(payload):\n    return _cache',entry)
    assert "'_cache' at line 2, UTF-8 byte column 12" in str(caught.value)

@pytest.mark.parametrize('code,accepted,reason',[
    ('def detect(payload):\n    return []',True,None),
    ('def detect(payload):\n    left, right = (1, 2)\n    return [left, right]',True,None),
    ("def detect(payload):\n    return {'_private_key': '__private_text'}",True,None),
    ('def detect(_payload):\n    return []',True,None),
    ('def detect(payload):\n    return payload.get("_private_key")',True,None),
    ('def detect(payload):\n    _private = 1\n    return []',False,'private names forbidden'),
    ('def detect(payload):\n    return _private',False,'private names forbidden'),
    ('def detect(payload):\n    return payload._private',False,'unsafe attribute'),
    ('def detect(payload):\n    return _helper()',False,'unsafe call'),
    ('def detect(payload):\n    import os\n    return []',False,'unsafe syntax'),
    ('def detect(payload):\n    def helper():\n        return []\n    return []',False,'nested functions forbidden'),
    ('def detect(payload):\n    return eval("1")',False,'unsafe call'),
    ('def detect(payload):\n    return 2 ** 100',False,'unbounded arithmetic'),
    ('def detect(payload):\n    while True:\n        pass',False,'unsafe syntax'),
    ('def detect(payload):\n    return []\ndef other(payload):\n    return []',False,'one entry function required'),
    ('def detect(payload, extra):\n    return []',False,'entry must accept exactly payload'),
    ('def detect(payload: dict):\n    return []',False,'annotations are not supported'),
])
def test_policy_acceptance_and_first_rejection_category_stay_unchanged(code,accepted,reason):
    for module in [candidate]:
        if accepted:
            assert module.validate_code(code) is not None
        else:
            with pytest.raises(ValueError) as caught:module.validate_code(code)
            assert str(caught.value).split(':',1)[0]==reason

@pytest.mark.parametrize('entry',['detect','propose','analyze'])
def test_valid_existing_entrypoints_remain_accepted(entry):
    code=f'def {entry}(payload):\n    return []'
    assert candidate.validate_code(code,entry) is not None
