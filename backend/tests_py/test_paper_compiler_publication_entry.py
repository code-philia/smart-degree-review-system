"""Actual CLI/corpus entry paths: fake review only, no API or label changes."""
import importlib.util
import json
from pathlib import Path
import pytest
from paper_compiler.programs import build_program,save_program
from paper_compiler.storage import write_json_atomic
from test_paper_compiler_compiler import fixture
from test_paper_compiler_programs import candidate


def entry(name):
    path=Path(__file__).parents[1]/'scripts'/name
    spec=importlib.util.spec_from_file_location('publication_entry_'+name.replace('.','_'),path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def fake_review(monkeypatch):
    from paper_compiler import publication_gate
    calls=[]
    def audit(ir,analysis,report,packages,**kwargs):
        calls.append((ir,analysis,report,packages,kwargs))
        folder=Path(kwargs['output_dir']);folder.mkdir(parents=True,exist_ok=True)
        result={'public':{'status':'NO_ALERT','findings':[]},'internal':{'output_dir':str(folder),
            'decisions':[{'reason':'PRIVATE_MISSING_FACT','proven_pass':False}]}}
        write_json_atomic(folder/'result.json',result)
        return result
    monkeypatch.setattr(publication_gate,'audit_positives',audit)
    return calls


@pytest.mark.parametrize('flag',['--online','--publication-review'])
def test_check_reviews_final_report_once_and_keeps_internal_review_private(tmp_path,monkeypatch,flag):
    module=entry('paper_compiler_cli.py');ir,_=fixture(tmp_path)
    ip=tmp_path/'ir.json';write_json_atomic(ip,ir)
    package=build_program({**candidate(),'rule_id':'31'},rule_text='The entry must be Hello',basis=[{'id':'test','text':'The entry must be Hello'}])
    pp=tmp_path/'program';save_program(package,pp)
    calls=fake_review(monkeypatch)
    out=tmp_path/'report.json'
    args=module.parser().parse_args(['check','--ir',str(ip),'--package',str(pp),'--out',str(out),'--offline',flag,
        '--stdout-report','--cache',str(tmp_path/'cache'),'--ledger',str(tmp_path/'budget'),'--control-root',str(tmp_path/'control')])
    public=module.execute(args);saved=json.loads(out.read_text())
    assert len(calls)==1
    assert public['publication']['public']=={'status':'NO_ALERT','findings':[]}
    assert 'PRIVATE_MISSING_FACT' not in json.dumps(public)
    assert 'PRIVATE_MISSING_FACT' in Path(saved['publication']['artifact']).read_text()
    assert saved['rules']==calls[0][2]['rules']
    assert calls[0][4]['client'] is None and calls[0][3][0]['manifest']['version_id']==package['manifest']['version_id']


def test_corpus_flag_reviews_detect_output_once_without_online_refinement(tmp_path,monkeypatch):
    module=entry('paper_compiler_corpus.py');ir,_=fixture(tmp_path)
    ip=tmp_path/'ir.json';write_json_atomic(ip,ir)
    package=build_program({**candidate(),'rule_id':'31'},rule_text='The entry must be Hello',basis=[{'id':'test','text':'The entry must be Hello'}])
    monkeypatch.setattr(module,'_suite',lambda path:[package])
    calls=fake_review(monkeypatch);captured={}
    def run(inventory,suite,out,*,runner,expected_documents):
        captured['fingerprint']=runner.fingerprint
        return runner(ip,tmp_path/'work')
    monkeypatch.setattr(module,'run_corpus',run)
    args=module.parser().parse_args(['run','--inventory',str(tmp_path/'inventory'),'--suite',str(tmp_path/'suite'),
        '--out',str(tmp_path/'out'),'--offline','--cache',str(tmp_path/'cache'),'--evidence-snapshot','fixed','--publication-review'])
    result=module.execute(args)
    assert len(calls)==1 and result['ir'] is calls[0][0] and result['analysis'] is calls[0][1]
    assert result['report']['publication']['public']['status']=='NO_ALERT'
    assert Path(result['report']['publication']['artifact']).is_file()
    assert captured['fingerprint']['publication_review'] is True
    assert result['report']['rules']==calls[0][2]['rules']
