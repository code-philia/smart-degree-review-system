"""Layout projection must preserve isolation and every per-program guard."""
import copy
import hashlib
import sys

import pytest

from paper_compiler import programs
from paper_compiler.contracts import ir_hash
from paper_compiler.storage import json_bytes
from test_paper_compiler_compiler import fixture
from test_paper_compiler_programs import candidate


def inputs(tmp_path):
    ir,analysis=fixture(tmp_path)
    ir['layout']={'pages':[{'page_index':0,'width':100,'height':120,'rotation':0,
        'blocks':[{'type':'text','lines':[{'text':'discarded full layout '+str(i)+'x'*96}]} for i in range(3000)]}]}
    analysis['paper_ir_sha256']=ir_hash(ir)
    packages=[programs.build_program({**candidate(),'rule_id':'projection-'+str(i)},
        rule_text='The entry must be Hello',basis=[{'id':'test','text':'The entry must be Hello'}]) for i in range(3)]
    return ir,analysis,packages


def test_worker_bytes_unchanged_without_deepcopying_discarded_layout(tmp_path,monkeypatch):
    ir,analysis,packages=inputs(tmp_path)
    before=json_bytes({'ir':ir,'analysis':analysis,'packages':packages})
    legacy=copy.deepcopy(ir)
    legacy['layout']={'pages':[{k:v for k,v in page.items() if k in {'page_index','width','height','rotation'}}
                              for page in ir['layout']['pages']]}
    expected=[json_bytes({'code':p['code'],'payload':{'ir':legacy,'analysis':analysis},'entry':'detect'}) for p in packages]
    requests=[];actual_run=programs.subprocess.run;layout_copies=[]
    def capture(*args,**kwargs):
        requests.append(kwargs['input'])
        return actual_run(*args,**kwargs)
    monkeypatch.setattr(programs.subprocess,'run',capture)
    def profile(frame,event,arg):
        if event=='call' and frame.f_code.co_name=='deepcopy' and frame.f_code.co_filename.endswith('/copy.py') and frame.f_locals.get('x') is ir['layout']:
            layout_copies.append(True)
    sys.setprofile(profile)
    try:report=programs.check_programs(ir,analysis,packages)
    finally:sys.setprofile(None)
    assert requests==expected
    assert [hashlib.sha256(v).hexdigest() for v in requests]==[hashlib.sha256(v).hexdigest() for v in expected]
    assert len(report['rules'])==3 and all(r['results'][0]['status']=='PASS' for r in report['rules'])
    assert report['paper_ir_sha256']==ir_hash(ir)
    assert json_bytes({'ir':ir,'analysis':analysis,'packages':packages})==before
    assert layout_copies==[], 'complete layout was copied and immediately discarded'


@pytest.mark.parametrize('entrypoint',['run_program','check_programs'])
@pytest.mark.parametrize('defect,reason',[('invalid_ir','dangling child'),('stale_analysis','stale analysis hash'),('tampered_package','hash mismatch')])
def test_projection_retains_public_validation(tmp_path,entrypoint,defect,reason):
    ir,analysis,packages=inputs(tmp_path)
    if defect=='invalid_ir':ir['nodes'][0]['children'].append('does-not-exist')
    elif defect=='stale_analysis':analysis['paper_ir_sha256']='0'*64
    else:packages[0]['code']+=' '
    with pytest.raises(ValueError,match=reason):
        if entrypoint=='run_program':programs.run_program(packages[0],ir,analysis)
        else:programs.check_programs(ir,analysis,packages)


def test_generator_mutation_is_revalidated_between_programs(tmp_path):
    ir,analysis,packages=inputs(tmp_path)
    def changing_packages():
        yield packages[0]
        ir['extensions']['changed_between_programs']=True
        yield packages[1]
    with pytest.raises(ValueError,match='stale analysis hash'):
        programs.check_programs(ir,analysis,changing_packages())


def test_worker_cannot_mutate_host_ir_or_analysis(tmp_path):
    ir,analysis,_=inputs(tmp_path)
    package=programs.build_program(candidate("def detect(payload):\n    payload['ir']['nodes'][0]['attrs']['mutated'] = True\n    payload['analysis']['paper_ir_sha256'] = 'changed'\n    return []"),rule_text='Isolation',basis=[])
    before=json_bytes({'ir':ir,'analysis':analysis,'package':package})
    programs.run_program(package,ir,analysis)
    assert json_bytes({'ir':ir,'analysis':analysis,'package':package})==before
