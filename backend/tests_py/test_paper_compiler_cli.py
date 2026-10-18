import json,subprocess,sys
from pathlib import Path
import pymupdf
from test_paper_compiler_compiler import fixture
from paper_compiler.storage import write_json_atomic
SCRIPT=Path(__file__).parents[1]/'scripts/paper_compiler.py'

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
