import copy
import pytest
from test_paper_compiler_compiler import fixture
from paper_compiler.analysis import base_analysis
from paper_compiler.mutations import mutate
from paper_compiler.contracts import ir_hash

CODE = """def detect(payload):
    output = []
    for node in nodes(payload, 'BibliographyEntry'):
        status = 'PASS' if node.get('text') == 'Hello' else 'VIOLATION'
        output.append(emit(node, status, 'Expected Hello', 'text', ['test']))
    return output
"""

def candidate(code=CODE):
    return {'rule_id':'new-rule','title':'A new natural language rule','requires':[],
            'target_kinds':['BibliographyEntry'],'code':code,'analysis_requests':[],'model_patch':{}}

def test_direct_python_program_detects_a_source_mutation(tmp_path):
    from paper_compiler.programs import build_program, run_program
    ir, a = fixture(tmp_path)
    p = build_program(candidate(), rule_text='The entry must be Hello',
                      basis=[{'id':'test','text':'The entry must be Hello'}])
    before = run_program(p, ir, a)
    changed, _ = mutate(ir, {'mutation_id':'source-edit','parent_sha256':ir_hash(ir),
        'operation':'replace_text','node_id':'entry','start':0,'end':5,'old_text':'Hello',
        'replacement':'Wrong','rule_id':'new-rule','status':'VIOLATION'})
    after = run_program(p, changed, base_analysis(changed))
    assert before[0]['status'] == 'PASS'
    assert after[0]['status'] == 'VIOLATION'
    assert after[0]['node_id'] == 'entry'
    assert after[0]['provenance'][0]['kind'] == 'synthetic'

@pytest.mark.parametrize('code',[
    "def detect(payload):\n    return open('/etc/passwd').read()",
    "import os\ndef detect(payload):\n    return []",
    "def detect(payload):\n    return payload.__class__",
    "def detect(payload):\n    while True:\n        pass",
    "def detect(payload):\n    return eval('1')",
])
def test_generated_program_cannot_access_host_or_run_unbounded_syntax(code):
    from paper_compiler.programs import build_program, ProgramError
    with pytest.raises(ProgramError):
        build_program(candidate(code),rule_text='rule',basis=[])

def test_program_package_rejects_tampering_and_roundtrips(tmp_path):
    from paper_compiler.programs import build_program, save_program, load_program, ProgramError
    p=build_program(candidate(),rule_text='rule',basis=[{'id':'test','text':'basis'}])
    save_program(p,tmp_path/'package')
    loaded=load_program(tmp_path/'package')
    assert loaded['manifest']['version_id']==p['manifest']['version_id']
    (tmp_path/'package'/'checks.py').write_text(CODE+'\n# changed')
    with pytest.raises(ProgramError,match='hash'):
        load_program(tmp_path/'package')

def test_program_receives_no_oracle_and_rejects_invalid_diagnostics(tmp_path):
    from paper_compiler.programs import build_program, run_program, ProgramError
    ir,a=fixture(tmp_path)
    bad=candidate("def detect(payload):\n    return [{'node_id':'does-not-exist','status':'PASS'}]")
    p=build_program(bad,rule_text='rule',basis=[])
    with pytest.raises(ProgramError):
        run_program(p,ir,a)
    leaking=copy.deepcopy(ir);leaking['extensions']['oracle']={'status':'PASS'}
    p=build_program(candidate(),rule_text='rule',basis=[{'id':'test','text':'basis'}])
    with pytest.raises(ValueError,match='leakage'):
        run_program(p,leaking,a)

def test_runtime_reports_unknown_for_an_empty_target_scope(tmp_path):
    from paper_compiler.programs import build_program, check_programs
    ir,a=fixture(tmp_path)
    p=build_program({**candidate('def detect(payload):\n    return []'),'target_kinds':['Figure']},
                    rule_text='rule',basis=[{'id':'test','text':'basis'}])
    report=check_programs(ir,a,[p])
    assert report['schema_version']=='paper-check/1.0'
    assert report['rules'][0]['status']=='UNKNOWN'

def test_runtime_rejects_stale_capability_versions_and_model(tmp_path):
    from paper_compiler.programs import build_program,run_program,ProgramError
    from paper_compiler.model_runtime import base_model,extend_model,apply_model
    ir,a=fixture(tmp_path)
    c=candidate();c['requires']=['bibliography_fields']
    p=build_program(c,rule_text='rule',basis=[{'id':'test','text':'basis'}])
    a['capability_versions']['bibliography_fields']='stale'
    with pytest.raises(ProgramError,match='capability'):
        run_program(p,ir,a)
    c=candidate()
    model=extend_model(base_model(),{'node_types':{'Method':{'base_kind':'Section','description':'methods','attrs':{}}}})
    p=build_program(c,rule_text='rule',basis=[{'id':'test','text':'basis'}],model=model)
    with pytest.raises(ProgramError,match='model'):
        run_program(p,ir,base_analysis(ir))

def test_manifest_cannot_spoof_model_or_capability_contract():
    from paper_compiler.programs import build_program,verify_program,ProgramError
    p=build_program(candidate(),rule_text='rule',basis=[])
    p['manifest']['model_version']='paper-model/spoofed'
    with pytest.raises(ProgramError,match='model'):
        verify_program(p)

def test_program_checks_declared_analysis_field_types_even_with_valid_versions(tmp_path):
    from paper_compiler.programs import build_program,run_program,ProgramError
    ir,a=fixture(tmp_path);c=candidate();c['requires']=['bibliography_fields']
    p=build_program(c,rule_text='rule',basis=[{'id':'test','text':'basis'}])
    a['capability_versions']=p['manifest']['capability_versions']
    a['results']['bibliography_fields']={'entry':{'title':{'state':'observed','value':True,'evidence_ids':[]}}}
    with pytest.raises(ProgramError,match='type'):
        run_program(p,ir,a)
