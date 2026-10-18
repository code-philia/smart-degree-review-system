import json,subprocess,sys
from pathlib import Path
import pymupdf
from test_paper_compiler_compiler import fixture
from paper_compiler.storage import write_json_atomic
SCRIPT=Path(__file__).parents[1]/'scripts/paper_compiler_cli.py'

def run(*args):return subprocess.run([sys.executable,str(SCRIPT),*map(str,args)],capture_output=True,text=True)

def test_cli_offline_build_and_existing_output_are_safe(tmp_path):
    pdf=tmp_path/'paper.pdf';doc=pymupdf.open();doc.new_page().insert_text((72,72),'Test paper');doc.save(pdf);doc.close()
    out=tmp_path/'paper.json';r=run('build','--pdf',pdf,'--out',out,'--offline')
    assert r.returncode==0,r.stderr+r.stdout
    assert json.loads(r.stdout)['status']=='completed' and out.exists()
    before=out.read_bytes();r=run('build','--pdf',pdf,'--out',out,'--offline')
    assert r.returncode==1 and out.read_bytes()==before

def test_cli_budget_does_not_require_api_credentials(tmp_path):
    r=run('budget','--ledger',tmp_path/'budget.sqlite','--budget','1000')
    assert r.returncode==0 and json.loads(r.stdout)['spent_cny']=='0.000000'

def test_invalid_cli_input_is_structured_error_without_traceback(tmp_path):
    r=run('check','--ir',tmp_path/'missing.json','--out',tmp_path/'report.json')
    assert r.returncode==1 and json.loads(r.stdout)['status']=='error'
    assert 'Traceback' not in r.stderr

def test_presentation_does_not_claim_synthetic_text_is_in_original_pdf(tmp_path):
    from paper_compiler.presentation import present
    ir,_=fixture(tmp_path);ir['layout']['pages']=[{'page_index':0,'width':100,'height':200,'rotation':0}]
    row={'node_id':'entry','status':'VIOLATION','provenance':[{'kind':'synthetic','ancestor_provenance':[{'kind':'source','page_index':0,'bbox':[10,20,30,40]}]}],'evidence_ids':[]}
    report={'rules':[{'results':[row]}],'evidence':[]}
    output=present(ir,report);assert output['rules'][0]['results'][0]['location'] is None
    assert output['rules'][0]['results'][0]['location_mode']=='synthetic'

def test_rotated_pdf_source_location_uses_display_dimensions(tmp_path):
    from paper_compiler.presentation import present
    ir,_=fixture(tmp_path);ir['layout']['pages']=[{'page_index':0,'width':100,'height':200,'rotation':90}]
    row={'node_id':'entry','status':'VIOLATION','provenance':[{'kind':'source','page_index':0,'bbox':[10,20,30,40]}],'evidence_ids':[]}
    output=present(ir,{'rules':[{'results':[row]}],'evidence':[]})
    box=output['rules'][0]['results'][0]['location']['bounding_rect']
    assert [box[k] for k in ['x1','y1','x2','y2','width','height']]==[160,10,180,30,200,100]


def test_derived_citation_location_follows_real_inputs_and_not_synthetic_inputs(tmp_path):
    from paper_compiler.presentation import present
    ir,_=fixture(tmp_path);ir['layout']['pages']=[{'page_index':0,'width':100,'height':200,'rotation':0}]
    row={'node_id':'entry','status':'VIOLATION','provenance':[{'kind':'derived','producer':'citation-parser','input_provenance':[{'kind':'source','page_index':0,'bbox':[10,20,30,40]}]}],'evidence_ids':[]}
    assert present(ir,{'rules':[{'results':[row]}],'evidence':[]})['rules'][0]['results'][0]['location']['page_number']==1
    row['provenance'][0]['input_provenance']=[{'kind':'synthetic','ancestor_provenance':[{'kind':'source','page_index':0,'bbox':[10,20,30,40]}]}]
    assert present(ir,{'rules':[{'results':[row]}],'evidence':[]})['rules'][0]['results'][0]['location'] is None

def test_cli_evaluate_runs_neutral_child_and_freezes_oracle(tmp_path):
    from paper_compiler.compiler import compile_rule
    from paper_compiler.registry import REGISTRY
    from paper_compiler.mutations import mutate
    from paper_compiler.contracts import ir_hash
    from test_paper_compiler_compiler import spec
    ir,_=fixture(tmp_path)
    class Model:
        def complete_json(self,*args):
            s=spec();s['requires']=[];s['checks'][0]['assert']={'op':'contains','args':[{'op':'field','path':'node.text'},{'op':'literal','value':'Hello'}]}
            return s
    package=tmp_path/'package';compile_rule('Text contains Hello',[],REGISTRY,Model(),package)
    mutant,oracle=mutate(ir,{'parent_sha256':ir_hash(ir),'operation':'replace_text','mutation_id':'opaque-id','node_id':'entry','start':0,'end':5,'old_text':'Hello','replacement':'Goodbye','rule_id':'test','target_check_id':'field-required','status':'VIOLATION','evidence_domain':'source_format','valid':True})
    for name,value in [('original',ir),('mutant',mutant),('oracle',oracle)]:write_json_atomic(tmp_path/(name+'.json'),value)
    m=tmp_path/'cases.json';write_json_atomic(m,{'version':'v1','cases':[{'id':'case1',**{name:str(tmp_path/(name+'.json')) for name in ['original','mutant','oracle']}}]})
    args=['evaluate','--manifest',m,'--out',tmp_path/'evaluation','--package',package,'--offline','--ledger',tmp_path/'ledger.sqlite','--cache',tmp_path/'cache','--evidence-snapshot','fixed']
    result=run(*args)
    assert result.returncode==0,result.stdout+result.stderr
    assert json.loads(result.stdout)['by_rule']['test']['detected']==1
    assert run(*args).returncode==0
    oracle['valid']=False;write_json_atomic(tmp_path/'oracle.json',oracle)
    assert run(*args).returncode==1

def test_presentation_uses_actual_semantic_quotes_instead_of_text_prefix(tmp_path):
    from paper_compiler.presentation import present
    ir,_=fixture(tmp_path)
    row={'node_id':'entry','status':'VIOLATION','provenance':[],'evidence_ids':['external'],'assessment':{'intent_quote':'Local purpose','evidence_quote':'Exact relevant passage','evidence_ids':['external'],'reason':'Explicit scope contradiction'}}
    report={'rules':[{'results':[row]}],'evidence':[{'id':'external','kind':'content','text':'Unrelated prefix','source_url':'https://example.org/article'}]}
    shown=present(ir,report)['rules'][0]['results'][0]['display_evidence']
    assert any(e['quote']=='Exact relevant passage' and e['url']=='https://example.org/article' for e in shown)
    assert any(e['quote']=='Local purpose' for e in shown)

def test_cli_check_retains_analysis_for_independent_audit(tmp_path):
    from paper_compiler.compiler import compile_rule
    from paper_compiler.registry import REGISTRY
    from test_paper_compiler_compiler import spec
    ir,_=fixture(tmp_path);ip=tmp_path/'input.json';write_json_atomic(ip,ir)
    class Model:
        def complete_json(self,*args):return spec()
    pkg=tmp_path/'pkg';compile_rule('Require title',[],REGISTRY,Model(),pkg)
    ap=tmp_path/'analysis.json'
    r=run('check','--ir',ip,'--out',tmp_path/'report.json','--analysis-out',ap,'--package',pkg,'--offline','--ledger',tmp_path/'ledger','--cache',tmp_path/'cache')
    assert r.returncode==0,r.stdout+r.stderr
    assert json.loads(ap.read_text())['paper_ir_sha256']

def test_package_import_is_not_shadowed_by_legacy_scripts_path():
    code="import sys;sys.path.insert(0,"+repr(str(SCRIPT.parents[1]))+");sys.path.insert(0,"+repr(str(SCRIPT.parent))+");import paper_compiler.analysis;print('loaded')"
    p=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True)
    assert p.returncode==0,p.stderr
