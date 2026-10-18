
import pytest
from test_paper_compiler_compiler import fixture

def test_format_source_predicate(tmp_path):
    from paper_compiler.experiment import format_recipe
    from paper_compiler.mutations import mutate
    ir,_=fixture(tmp_path);ir['nodes'][-1]['text']='[1] Smith. Title[J]. Journal, 2020.'
    changed,oracle=mutate(ir,format_recipe(ir,'entry','type-required'))
    assert '[J]' not in changed['nodes'][-1]['text']
    assert oracle['valid'] and oracle['status']=='VIOLATION'

def test_multiple_markers_do_not_make_valid_oracle(tmp_path):
    from paper_compiler.experiment import format_recipe
    ir,_=fixture(tmp_path);ir['nodes'][-1]['text']='One[J]. Two[M].'
    with pytest.raises(ValueError,match='marker'):format_recipe(ir,'entry','type-required')

def test_semantic_oracle_requires_quotes_and_exclusion():
    from paper_compiler.experiment import validate_semantic_oracle
    a={'original_supported':True,'replacement_excluded':True,'basis':'explicit_scope_contradiction','intent_quote':'claim','original_quote':'support','replacement_quote':'scope','alternatives_excluded':'methods excluded','reason':'incompatible object'}
    assert validate_semantic_oracle(a,'claim','support','scope')
    assert not validate_semantic_oracle({**a,'replacement_quote':'invented'},'claim','support','scope')
    assert not validate_semantic_oracle({**a,'basis':'missing_detail'},'claim','support','scope')

def test_identity_control_needs_verified_original(tmp_path):
    from paper_compiler.experiment import identity_recipe
    ir,a=fixture(tmp_path)
    with pytest.raises(ValueError,match='identity'):identity_recipe(ir,a,'entry','exists')
    a['results']['external_work']={'entry':{'exists':{'state':'observed','value':True,'evidence_ids':['record']}}}
    assert identity_recipe(ir,a,'entry','exists')['status']=='PASS'

def test_budget_stop_preserves_unassessed_parents(tmp_path,monkeypatch):
    import json,hashlib
    import paper_compiler.frontend as frontend
    import paper_compiler.runtime as runtime
    import paper_compiler.llm as llm
    import paper_compiler.experiment as experiment
    from paper_compiler.budget import BudgetExceeded
    config={'MAAS_MODEL':'test','MAAS_MODEL_VERSION':'frozen'}
    monkeypatch.setattr(llm,'load_config',lambda path:config)
    class Client:
        def __init__(self,*args):self.config=config
    monkeypatch.setattr(llm,'MaasClient',Client)
    monkeypatch.setattr(runtime,'load_package',lambda path:{'rule_ir':{'rule_id':str(path)},'manifest':{}})
    monkeypatch.setattr(experiment,'format_check',lambda package:'marker')
    calls=[]
    def build(path,client):calls.append(path);raise BudgetExceeded('authorized budget exhausted')
    monkeypatch.setattr(frontend,'build_paper',build)
    items=[]
    for i in range(3):
        pdf=tmp_path/(str(i)+'.pdf');pdf.write_bytes(str(i).encode())
        items.append({'id':'pdf-'+str(i),'path':str(pdf),'sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'duplicate':False})
    inv=tmp_path/'inventory.json';inv.write_text(json.dumps({'items':items}))
    replacement=tmp_path/'replacement.json';replacement.write_text(json.dumps({'identity':{'value':True,'work':{}},'content':[]}))
    settings={'config':'unused','ledger':str(tmp_path/'ledger.sqlite3'),'budget':'1','phase':'round','phase-budget':'1','cache':str(tmp_path/'cache'),'evidence-snapshot':'frozen','packages':['31','32','33']}
    result=experiment.run_round(inv,tmp_path/'round',settings,replacement,minimum=100,workers=1)
    assert len(calls)==1
    assert result['parents_attempted']==1 and result['unassessed_parents']==2
    assert result['stop_reason']=='budget_exhausted'

def test_child_budget_signal_is_not_lost_as_generic_detector_error(tmp_path,monkeypatch):
    import json
    from types import SimpleNamespace
    import paper_compiler.experiment as experiment
    from paper_compiler.budget import BudgetExceeded
    ir=tmp_path/'input.json';ir.write_text('{}')
    monkeypatch.setattr(experiment.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1,stdout=json.dumps({'status':'error','error_type':'BudgetExceeded'}),stderr=''))
    settings={key:'test' for key in ['config','ledger','budget','phase','phase-budget','cache','evidence-snapshot']}
    settings['packages']=[]
    with pytest.raises(BudgetExceeded):experiment.detector(ir,tmp_path/'detector',settings)
    assert (tmp_path/'detector/process.json').exists()
