"""TEST_ONLY integration: native checker/analysis, fake external client, sealed roles."""
import copy,importlib.util,json
from pathlib import Path

from paper_compiler.analysis import base_analysis,bind_references,ordering_facts
from paper_compiler.feedback_loop import evaluate_cases,run_feedback_loop
from paper_compiler.programs import build_program,check_programs
from paper_compiler.repair_context import attach_feedback_context
from paper_compiler.storage import write_json_atomic
from test_paper_compiler_feedback_loop import make_cases
from test_paper_compiler_programs import candidate

CODE="def detect(payload):\n    return [emit(n,'PASS','initial','text',['test']) for n in nodes(payload,'ReferenceUse')]"
TASK={'rule_id':'new-rule','rule_text':'A generic source rule','basis':[{'id':'test','text':'Generic source norm'}]}


def prepare(tmp_path):
    manifest=make_cases(tmp_path);value=json.loads(manifest.read_text())
    for case in value['cases']:
        case['target_node_id']='u';op=Path(case['oracle_path']);oracle=json.loads(op.read_text());oracle['target_node_id']='u';write_json_atomic(op,oracle)
    write_json_atomic(manifest,value)
    package=build_program({**candidate(CODE),'target_kinds':['ReferenceUse'],'requires':['citation_order']},rule_text=TASK['rule_text'],basis=TASK['basis'])
    return manifest,value['cases'],package


def run_detect(package,ir,*,rich,seen=None):
    materialized=copy.deepcopy(ir)
    materialized['coverage']['reference_uses']={'status':'partial','reason':'source citation extraction incomplete'}
    analysis=base_analysis(materialized);bind_references(materialized,analysis);ordering_facts(materialized,analysis)
    report=check_programs(materialized,analysis,[package])
    if seen is not None:seen.append((report,copy.deepcopy(report['rules'])))
    return attach_feedback_context(report,materialized,analysis) if rich else report


def test_failed_case_gets_both_real_analysis_slices_without_changing_gold_metrics(tmp_path):
    manifest,cases,package=prepare(tmp_path);feedback=[c for c in cases if c['split']=='feedback'];seen=[]
    plain=evaluate_cases(package,feedback,lambda p,ir:run_detect(p,ir,rich=False))
    rich=evaluate_cases(package,feedback,lambda p,ir:run_detect(p,ir,rich=True,seen=seen))
    assert rich['records']==plain['records'] and rich['metrics']==plain['metrics']
    assert len(rich['failures'])==len(plain['failures'])==1
    failure=rich['failures'][0]
    for side in ['analysis_original','analysis_mutant']:
        projected=failure[side]
        fact=projected['results']['citation_order']['u']['first_appearance_rank']
        assert fact=={'state':'unknown','reason':'incomplete citation extraction prevents ordinal judgment'}
        assert projected['ir_coverage']['reference_uses']['status']=='partial'
        assert projected['target_ids']==['u']
        assert 'rules' not in projected and 'oracle' not in json.dumps(projected)
    assert all(report['rules']==before for report,before in seen)
    assert all('analysis_original' not in row and 'analysis_mutant' not in row for row in rich['records'])
    assert all('analysis_original' not in row and 'analysis_mutant' not in row for row in plain['failures'])


def test_projection_occurs_only_on_failures_with_exact_target_scope(tmp_path,monkeypatch):
    import paper_compiler.feedback_loop as loop
    import paper_compiler.repair_context as context
    manifest,cases,package=prepare(tmp_path);calls=[];original=context.project_feedback_context
    def project(report,targets,requires=None):
        calls.append((list(targets),requires));return original(report,targets,requires)
    monkeypatch.setattr(context,'project_feedback_context',project)
    monkeypatch.setattr(loop,'project_feedback_context',project,raising=False)
    outcome=evaluate_cases(package,[c for c in cases if c['split']=='feedback'],lambda p,ir:run_detect(p,ir,rich=True))
    assert len(calls)==2*len(outcome['failures']) and all(targets==['u'] for targets,_ in calls)


def test_only_feedback_analysis_reaches_repair_no_validation_or_test_cases(tmp_path):
    manifest,cases,package=prepare(tmp_path)
    class Model:
        requests=[]
        def complete_json(self,task,instructions,data,max_tokens):
            self.requests.append(copy.deepcopy(data));return {**candidate(CODE),'target_kinds':['ReferenceUse'],'requires':['citation_order']}
    client=Model()
    outcome=run_feedback_loop(TASK,manifest,client=client,output_dir=tmp_path/'loop',max_rounds=2,
        initial_package=package,runner=lambda p,ir:run_detect(p,ir,rich=True))
    assert outcome['rounds_completed']==2 and len(client.requests)==1
    packet=client.requests[0]
    assert packet['feedback'][0]['analysis_original']['results']['citation_order']['u']['first_appearance_rank']['state']=='unknown'
    encoded=json.dumps(packet)
    assert 'validation-secret' not in encoded and 'test-secret' not in encoded
    assert 'validation_metrics' not in encoded and 'validation_score' not in encoded


def test_official_cli_runner_preserves_detect_analysis_and_task_environment(tmp_path,monkeypatch):
    import paper_compiler.budget as budget
    import paper_compiler.llm as llm
    import paper_compiler.evidence as evidence
    import paper_compiler.pipeline as pipeline
    import paper_compiler.study as study
    from test_paper_compiler_program_analysis import paper
    ir=paper(tmp_path);a=base_analysis(ir);ordering_facts(ir,a)
    report={'schema_version':'paper-check/1.0','paper_ir_sha256':a['paper_ir_sha256'],'rules':[{'rule_id':'generic','status':'UNKNOWN'}]}
    before=copy.deepcopy(report);environment={'domain':'controlled_catalog','catalog':[],'complete':True};captured=[]
    task={'rule_id':'generic','evidence_environment':'controlled_catalog'}
    taskpath=tmp_path/'tasks.json';resourcepath=tmp_path/'resources.json';manifest=tmp_path/'manifest.json'
    write_json_atomic(taskpath,[task]);write_json_atomic(resourcepath,{'evidence_environment':environment});write_json_atomic(manifest,{'TEST_ONLY':True})
    class Client:
        def __init__(self,*args,**kwargs):assert kwargs['max_attempts']==1
    class Gateway:
        providers=['TEST_ONLY']
        def __init__(self,*args,**kwargs):pass
    monkeypatch.setattr(budget,'BudgetLedger',lambda *args:object());monkeypatch.setattr(llm,'MaasClient',Client);monkeypatch.setattr(evidence,'EvidenceGateway',Gateway)
    def detect(value,packages,**kwargs):
        assert kwargs['evidence_environment']==environment
        return ir,a,report
    monkeypatch.setattr(pipeline,'detect',detect)
    def run(*args,**kwargs):
        captured.append(kwargs['runner']({'program_spec':{'rule_id':'generic'}},ir));return {'status':'completed'}
    monkeypatch.setattr(study,'run_study',run)
    path=Path(__file__).resolve().parents[1]/'scripts/run_paper_compiler_study.py'
    spec=importlib.util.spec_from_file_location('study_context_cli_test',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    args=module.parser().parse_args(['--tasks',str(taskpath),'--manifest',str(manifest),'--resources',str(resourcepath),'--out',str(tmp_path/'out')])
    assert module.execute(args)['status']=='completed'
    assert captured[0]['_feedback_context']['analysis'] is a and captured[0]['_feedback_context']['ir'] is ir
    assert captured[0]['rules'] is report['rules'] and report==before and '_feedback_context' not in report
