"""Synthetic pure workers and TEST_ONLY cases; no model or network calls."""
import json,subprocess,sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from paper_compiler import program_worker as worker, programs, feedback_loop as feedback
REPO=Path(worker.__file__).resolve().parents[2]
PREFIX=b'PAPER_PROGRAM_ERROR/1 '
DYNAMIC="def detect(payload):\n    pattern = payload['pattern']\n    return re_search(pattern, 'x')\n"
SIMPLE="def detect(payload):\n    return []\n"


def invoke(code,payload):
    return subprocess.run([sys.executable,str(Path(worker.__file__))],
        input=json.dumps({'code':code,'payload':payload}).encode(),capture_output=True,timeout=12)


def read_record(result):
    assert result.returncode==2 and result.stdout==b''
    last=result.stderr.rstrip(b'\n').rsplit(b'\n',1)[-1]
    assert last.startswith(PREFIX)
    return json.loads(last[len(PREFIX):])


def test_dynamic_regex_worker_last_line_is_bounded_json_after_native_logs():
    r=invoke(DYNAMIC,{'pattern':r'\u4e00','PRIVATE_PAYLOAD_SENTINEL':'never serialize payload'})
    record=read_record(r)
    assert set(record)=={'type','message','generated_lines'}
    assert record['type']=='Error' and 'invalid escape sequence' in record['message']
    assert record['generated_lines']==[3]
    assert 'PRIVATE_PAYLOAD_SENTINEL' not in r.stderr.decode(errors='replace')
    assert str(REPO) not in r.stderr.decode(errors='replace')


def test_worker_bounds_message_and_keeps_only_generated_lines():
    record=read_record(invoke("def detect(payload):\n    return payload['x'*2000]\n",{'unused':'payload sentinel'}))
    assert record['type']=='KeyError' and len(record['message'])==1000
    assert record['generated_lines']==[2]
    assert set(record)=={'type','message','generated_lines'}


def test_success_worker_output_remains_success():
    r=invoke(SIMPLE,{})
    assert r.returncode==0 and json.loads(r.stdout)==[] and r.stderr==b''


def test_host_preserves_only_valid_worker_record_from_dynamic_regex():
    with pytest.raises(programs.ProgramError) as caught:programs.execute_pure(DYNAMIC,{'pattern':r'\u4e00'})
    message=str(caught.value)
    assert 'Error' in message and 'invalid escape sequence' in message and '<paper-program>' in message and '3' in message
    assert 're2.cc' not in message and 'WARNING' not in message and str(REPO) not in message


def record_bytes(record=None):
    if record is None:record={'type':'ValueError','message':'safe native reason','generated_lines':[2]}
    return PREFIX+json.dumps(record,ensure_ascii=True).encode()+b'\n'


def test_host_ignores_native_prefix_and_never_forwards_it(monkeypatch):
    fake=SimpleNamespace(returncode=2,stdout=b'',stderr=b'SECRET_NATIVE_PREFIX\n'+record_bytes())
    monkeypatch.setattr(programs.subprocess,'run',lambda *a,**kw:fake)
    with pytest.raises(programs.ProgramError) as caught:programs.execute_pure(SIMPLE,{})
    assert 'safe native reason' in str(caught.value) and 'SECRET_NATIVE_PREFIX' not in str(caught.value)


@pytest.mark.parametrize('record',[
    {'type':'ValueError','message':'safe','generated_lines':[2],'payload':'SECRET'},
    {'type':['ValueError'],'message':'safe','generated_lines':[2]},
    {'type':'ValueError','message':1,'generated_lines':[2]},
    {'type':'ValueError','message':'x'*1001,'generated_lines':[2]},
    {'type':'ValueError','message':'safe','generated_lines':[True]},
    {'type':'ValueError','message':'safe','generated_lines':[0]},
    {'type':'ValueError','message':'safe','generated_lines':[-1]},
    {'type':'ValueError','message':'safe','generated_lines':[3]},
    {'type':'ValueError','message':'safe','generated_lines':[2]*9},
    {'type':'ValueError','message':'safe','generated_lines':'2'},
])
def test_invalid_worker_schema_or_bounds_keep_generic_fallback(monkeypatch,record):
    fake=SimpleNamespace(returncode=2,stdout=b'',stderr=record_bytes(record))
    monkeypatch.setattr(programs.subprocess,'run',lambda *a,**kw:fake)
    with pytest.raises(programs.ProgramError,match='^isolated program rejected$'):programs.execute_pure(SIMPLE,{})


@pytest.mark.parametrize('rc,stdout,stderr',[
    (-9,b'',record_bytes()),(1,b'',record_bytes()),
    (2,b'',b'unknown native failure\n'),(2,b'',PREFIX+b'{broken}\n'),
    (2,b'',record_bytes()+b'not the final record\n'),
    (2,b'',PREFIX+b'x'*17000+b'\n'),
    (2,b'x'*(8*1024*1024+1),record_bytes()),
])
def test_unknown_signal_malformed_or_oversized_output_keeps_generic_fallback(monkeypatch,rc,stdout,stderr):
    fake=SimpleNamespace(returncode=rc,stdout=stdout,stderr=stderr)
    monkeypatch.setattr(programs.subprocess,'run',lambda *a,**kw:fake)
    with pytest.raises(programs.ProgramError,match='^isolated program rejected$'):programs.execute_pure(SIMPLE,{})


@pytest.mark.parametrize('helper',['re_search','re_matches','re_findall'])
def test_invalid_literal_re2_pattern_is_rejected_at_compile_time_with_location(helper):
    code=f"def detect(payload):\n    return {helper}(r'\\u4e00', 'x')\n"
    with pytest.raises(ValueError) as caught:worker.validate_code(code)
    assert 'invalid RE2 literal pattern' in str(caught.value)
    assert 'line 2' in str(caught.value) and 'invalid escape sequence' in str(caught.value)


@pytest.mark.parametrize('helper',['re_search','re_matches','re_findall'])
def test_valid_literal_and_dynamic_pattern_validation_remain_accepted(helper):
    assert worker.validate_code(f"def detect(payload):\n    return {helper}(r'[A-Za-z]+', 'text')\n") is not None
    assert worker.validate_code(f"def detect(payload):\n    return {helper}(payload['pattern'], 'text')\n") is not None


def case(tmp_path):
    from test_paper_compiler_compiler import fixture
    ir,_=fixture(tmp_path)
    original=tmp_path/'TEST_ONLY-original.json';mutant=tmp_path/'TEST_ONLY-mutant.json';oracle=tmp_path/'TEST_ONLY-label.json'
    original.write_text(json.dumps(ir));mutant.write_text(json.dumps(ir));oracle.write_text(json.dumps({'valid':True,'status':'PASS','target_node_id':'entry'}))
    return {'id':'TEST_ONLY-feedback','parent_group':'TEST_ONLY','original_ir_path':str(original),'ir_path':str(mutant),'oracle_path':str(oracle),'target_node_id':'entry'}


def test_safe_program_error_reaches_actual_feedback_without_changing_error_metrics(tmp_path):
    package={'manifest':{'version_id':'TEST_ONLY'},'program_spec':{'rule_id':'synthetic'}}
    output=feedback.evaluate_cases(package,[case(tmp_path)],lambda p,ir:programs.execute_pure(DYNAMIC,{'pattern':r'\u4e00'}))
    assert output['records'][0]['before']==output['records'][0]['after']=='ERROR'
    assert output['metrics']['errors']==output['metrics']['strict_errors']==1
    for side in ['actual_original','actual_mutant']:
        diagnostic=output['failures'][0][side][0]
        assert diagnostic['error_type']=='ProgramError'
        assert 'invalid escape sequence' in diagnostic['reason'] and '<paper-program>' in diagnostic['reason']


@pytest.mark.parametrize('error',[ValueError('SECRET_CONFIG'),OSError('SECRET_NETWORK'),RuntimeError('SECRET_CLIENT')])
def test_non_program_error_message_is_not_transported_to_feedback(tmp_path,error):
    package={'manifest':{'version_id':'TEST_ONLY'},'program_spec':{'rule_id':'synthetic'}}
    def runner(*args):raise error
    output=feedback.evaluate_cases(package,[case(tmp_path)],runner)
    assert 'SECRET_' not in json.dumps(output)
    assert output['records'][0]['before']==output['records'][0]['after']=='ERROR'


def test_budget_exception_is_still_propagated(tmp_path):
    package={'manifest':{'version_id':'TEST_ONLY'},'program_spec':{'rule_id':'synthetic'}}
    def runner(*args):raise feedback.BudgetExceeded('TEST_ONLY')
    with pytest.raises(feedback.BudgetExceeded):feedback.evaluate_cases(package,[case(tmp_path)],runner)
