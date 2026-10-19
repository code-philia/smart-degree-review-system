"""TEST ONLY financial CLI boundaries; no real ledger, configuration or model API."""
import importlib.util
from decimal import Decimal
from pathlib import Path
import pytest

def entry(name):
    p=Path(__file__).resolve().parents[1]/'scripts'/name
    spec=importlib.util.spec_from_file_location('TEST_ONLY_financial_'+name.replace('.','_'),p)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value

def study_fixture(tmp_path,monkeypatch):
    import paper_compiler.budget as budget
    import paper_compiler.llm as llm
    import paper_compiler.evidence as evidence
    import paper_compiler.study as study
    import paper_compiler.program_analysis as analysis
    module=entry('run_paper_compiler_study.py');tasks=tmp_path/'TEST_ONLY_tasks.json';tasks.write_text('[]')
    manifest=tmp_path/'TEST_ONLY_manifest.json';manifest.write_text('{}')
    args=module.parser().parse_args(['--tasks',str(tasks),'--manifest',str(manifest),'--out',str(tmp_path/'out')])
    seen={'ledger':[],'client':[],'run':[]}
    monkeypatch.setattr(budget,'BudgetLedger',lambda *a:seen['ledger'].append(a) or object())
    monkeypatch.setattr(llm,'MaasClient',lambda *a,**k:seen['client'].append((a,k)) or object())
    monkeypatch.setattr(evidence,'EvidenceGateway',lambda *a,**k:type('TEST_ONLY_Gateway',(),{'providers':['TEST_ONLY']})())
    monkeypatch.setattr(analysis,'analysis_execution_policy',lambda:{'TEST_ONLY':True})
    monkeypatch.setattr(study,'run_study',lambda *a,**k:seen['run'].append(k) or {'status':'completed'})
    return module,args,seen

def test_study_financial_cli_accepts400_total_with_independent200_phase(tmp_path,monkeypatch):
    module,args,seen=study_fixture(tmp_path,monkeypatch);args.budget='400';args.phase_budget='200'
    assert module.execute(args)['status']=='completed'
    assert seen['ledger'][0][1]==Decimal('400')
    assert seen['client'][0][0][3:5]==('framework-20261019',Decimal('200'))
    assert seen['client'][0][1]['max_attempts']==1
    assert seen['run'][0]['max_rounds']==5

def test_study_financial_cli_preserves_defaults_and_does_not_couple_phase(tmp_path,monkeypatch):
    module,args,seen=study_fixture(tmp_path,monkeypatch)
    assert args.budget=='200' and args.phase_budget=='200'
    module.execute(args);fp=seen['run'][-1]['runner'].study_fingerprint
    args.budget='400';args.phase_budget='25';module.execute(args)
    assert seen['client'][-1][0][4]==Decimal('25')
    assert seen['run'][-1]['runner'].study_fingerprint==fp

def test_study_financial_cli_exposes_explicit_phase_argument(tmp_path,monkeypatch):
    module,args,_=study_fixture(tmp_path,monkeypatch)
    parsed=module.parser().parse_args(['--tasks',str(args.tasks),'--manifest',str(args.manifest),'--out',str(args.out),'--budget','400','--phase-budget','200'])
    assert parsed.budget=='400' and parsed.phase_budget=='200'

@pytest.mark.parametrize('field,value',[('budget','401'),('budget','NaN'),('budget','0'),('phase_budget','401'),('phase_budget','NaN'),('phase_budget','0')])
def test_study_financial_cli_rejects_invalid_before_ledger(tmp_path,monkeypatch,field,value):
    module,args,seen=study_fixture(tmp_path,monkeypatch);setattr(args,field,value)
    with pytest.raises(ValueError):module.execute(args)
    assert seen['ledger']==[] and seen['client']==[]

def corpus_fixture(tmp_path,monkeypatch):
    import paper_compiler.program_analysis as analysis
    module=entry('paper_compiler_corpus.py');seen=[]
    args=module.parser().parse_args(['run','--inventory',str(tmp_path/'TEST_ONLY-inventory'),'--suite',str(tmp_path/'TEST_ONLY-suite'),'--out',str(tmp_path/'TEST_ONLY-out'),'--offline','--evidence-snapshot','TEST_ONLY'])
    monkeypatch.setattr(analysis,'analysis_execution_policy',lambda:{'TEST_ONLY':True})
    monkeypatch.setattr(module,'_suite',lambda p:[{'program_spec':{'rule_id':'TEST_ONLY'}}])
    monkeypatch.setattr(module,'run_corpus',lambda *a,**k:seen.append(k['runner'].fingerprint) or {'complete':False})
    return module,args,seen

def test_corpus_financial_cli_accepts400_total_and_preserves_phase_identity(tmp_path,monkeypatch):
    module,args,seen=corpus_fixture(tmp_path,monkeypatch);args.budget='400';args.phase_budget='25'
    module.execute(args)
    assert seen[0]['budget']=='400' and seen[0]['phase_budget']=='25'
    assert seen[0]['analysis_execution_policy']=={'TEST_ONLY':True}

@pytest.mark.parametrize('field,value',[('budget','401'),('budget','NaN'),('budget','0'),('phase_budget','401'),('phase_budget','NaN'),('phase_budget','0')])
def test_corpus_financial_cli_rejects_invalid_before_runner(tmp_path,monkeypatch,field,value):
    module,args,seen=corpus_fixture(tmp_path,monkeypatch);setattr(args,field,value)
    with pytest.raises(ValueError):module.execute(args)
    assert seen==[]
