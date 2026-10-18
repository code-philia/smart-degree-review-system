"""Online cases use real mutations/pipelines and fake external APIs only."""
import copy
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import uuid

import pytest

from paper_compiler.citations import attach_citations
from paper_compiler.contracts import ir_hash, validate_ir
from paper_compiler.model_runtime import base_model
from paper_compiler.pipeline import detect
from paper_compiler.programs import build_program
from paper_compiler.runtime_control import RuntimeControl
from test_paper_compiler_online_loop import OLD, FIX, candidate

MEMO = "def detect(payload):\n    return [emit(n, 'VIOLATION' if n['id']=='bad' else 'PASS', 'Memorized input') for n in nodes(payload,'Paragraph')]\n"


def document(tmp_path, *, bad=False):
    texts=[('p','Paragraph','We apply tree models [1].'),
           ('entry','BibliographyEntry','[1] Smith J. Tree Models for Lakes. 2020.')]
    if bad:texts.insert(1,('bad','Paragraph','We apply wide models.'))
    text='\n'.join(value for _,_,value in texts)
    source=tmp_path/'paper.txt';source.write_text(text)
    nodes=[{'id':'root','kind':'Paper','text':None,'children':[n for n,_,_ in texts],'attrs':{},'provenance':[]}]
    offset=0
    for nid,kind,value in texts:
        nodes.append({'id':nid,'kind':kind,'text':value,'children':[],
            'attrs':{'key':'1'} if kind=='BibliographyEntry' else {},
            'provenance':[{'kind':'source','source_id':'src','char_start':offset,'char_end':offset+len(value)}]})
        offset+=len(value)+1
    ir={'schema_version':'paper-ir/1.0','model_version':'paper-model/1.0','document_id':'online-paper',
        'revision':'original','root_id':'root','source_artifacts':[{'id':'src','kind':'text',
            'path':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}],
        'nodes':nodes,'profile':{},'coverage':{},'layout':{'pages':[]},'metadata':{},'extensions':{}}
    attach_citations(ir);validate_ir(ir,tmp_path);return ir


def package():
    return build_program(candidate(OLD),rule_text='Every method paragraph must use tree models.',
        basis=[{'id':'project-term','text':'Use tree models in every method paragraph.'}],model=base_model())


def local_api():
    assert importlib.util.find_spec('paper_compiler.online_mutants') is not None, 'online mutation validation is missing'
    return importlib.import_module('paper_compiler.online_mutants').build_online_cases


class Model:
    config={'MAAS_MODEL':'fake','MAAS_MODEL_VERSION':'online-mutants-v1'}
    def __init__(self, code=FIX, *, mode='normal', on_proposals=None):
        self.code=code;self.mode=mode;self.on_proposals=on_proposals;self.requests=[]
    def complete_json(self,task,instructions,data,max_tokens):
        self.requests.append((task,copy.deepcopy(data)))
        if task.startswith('online-evidence-'):
            rows=[]
            for target in data['targets']:
                source=next(s for s in target['sources'] if s.get('node_id')==target['node_id'])
                rows.append({'rule_id':target['rule_id'],'node_id':target['node_id'],
                    'status':'PASS' if 'tree' in source['text'] else 'VIOLATION',
                    'basis':'direct_observation','reason':'The exact local source determines compliance.',
                    'basis_ids':['project-term'],'quotes':[{'source_id':source['source_id'],'quote':source['text']}]})
            return {'judgments':rows}
        if task=='benchmark-proposals/2.0':
            if self.on_proposals:self.on_proposals()
            result=[]
            for parent in data['parents']:
                node=next(n for n in parent['nodes'] if n['id']=='p')
                target=next(t for t in parent['targets'] if t['kind']==data['task']['target_kinds'][0])
                for replacement,status in [('We apply wide models [1].','VIOLATION'),
                                           ('We apply these tree models [1].','PASS')]:
                    result.append({'parent_id':parent['parent_id'],'node_id':node['id'],
                        'start':0,'end':len(node['text']),'old_text':node['text'],'replacement':replacement,
                        'claimed_status':status,'target_node_id':target['id'],
                        'context_origin':parent['context_origin'],'evidence_domain':'local_source','source_ids':[]})
            return {'proposals':result}
        if task in {'benchmark-label/2.0','benchmark-review/2.0'}:
            def keys(value):
                if isinstance(value,dict):
                    return set(value).union(*(keys(v) for v in value.values()))
                if isinstance(value,list):return set().union(*(keys(v) for v in value))
                return set()
            assert not keys(data)&{'claimed_status','expected','prediction','detector','previous_candidate','code'}
            from paper_compiler.benchmark_builder import ORACLE_PROTOCOL
            assert data['label_contract']['protocol']==ORACLE_PROTOCOL
            status='PASS' if 'tree' in data['mutated_node']['text'] else 'VIOLATION'
            if self.mode=='unknown':status='UNKNOWN'
            if self.mode=='misclaimed':status='PASS'
            return {'valid':True,'original_compliant':True,'status':status,
                'reason':'Independent exact original and changed local source comparison.',
                'quotes':[{'source_id':s['id'],'quote':s['text']} for s in data['sources']],
                'basis_ids':['project-term']}
        assert task=='paper-program-synthesis/2.0'
        assert any(row.get('case_id') for row in data['feedback']), 'local failures must reach synthesis'
        return candidate(self.code)


def build(tmp_path, ir, model=None):
    pkg=package();materialized,analysis,_=detect(ir,[pkg],client=None,gateway=None,cache_dir=tmp_path/'cache')
    return local_api()(materialized,[pkg],analysis,client=model or Model(),gateway=None,
        output_dir=tmp_path/'local-cases')


def online(tmp_path,ir,model=None,control=None,resources=None,max_rounds=1):
    from paper_compiler.online_loop import online_refine
    return online_refine(ir,[package()],client=model or Model(),gateway=None,cache_dir=tmp_path/'cache',
        control=control or RuntimeControl(tmp_path/'control'),output_dir=tmp_path/'online',
        resources=resources,max_rounds=max_rounds)


def test_local_cases_change_real_ir_and_keep_original_ir_and_source_bytes_immutable(tmp_path):
    ir=document(tmp_path);before=copy.deepcopy(ir);source=Path(ir['source_artifacts'][0]['path']);payload=source.read_bytes()
    model=Model();result=build(tmp_path,ir,model)
    assert result['status']=='complete' and len(result['cases'])==2
    assert ir==before and source.read_bytes()==payload
    assert {c['expected'][0]['status'] for c in result['cases']}=={'VIOLATION','PASS'}
    for case in result['cases']:
        assert case['origin']=='online-regression' and case['split']=='feedback' and case['verified'] is True
        validate_ir(case['ir'],tmp_path)
        changed=next(n for n in case['ir']['nodes'] if n['id']=='p')
        assert changed['text']!=before['nodes'][1]['text'] and changed['provenance'][0]['kind']=='synthetic'
        assert '"expected":' not in json.dumps(case['ir'])
        copied=Path(case['ir']['source_artifacts'][0]['path'])
        assert copied!=source and copied.is_relative_to(tmp_path/'local-cases') and copied.read_bytes()==payload
    assert sum(t=='benchmark-proposals/2.0' for t,_ in model.requests)==1
    assert sum(t=='benchmark-label/2.0' for t,_ in model.requests)==2
    assert sum(t=='benchmark-review/2.0' for t,_ in model.requests)==2


def test_changed_compliant_control_is_valid_but_misclaimed_violation_is_never_reclassified(tmp_path):
    result=build(tmp_path,document(tmp_path),Model(mode='misclaimed'))
    assert result['status']=='incomplete'
    assert result['summary']['word']['violations']==0
    assert result['summary']['word']['controls']==1
    assert result['summary']['word']['missing_violations']==1
    assert any('mismatch' in row['reason'] for row in result['rejections'])


def test_unknown_independent_labels_preserve_old_suite_and_expose_missing_local_classes(tmp_path):
    result=online(tmp_path,document(tmp_path,bad=True),Model(mode='unknown'))
    assert result['runtime']['status']=='mutation_validation_incomplete'
    assert result['packages'][0]['code']==OLD
    assert result['runtime']['local_mutation_validation']['summary']['word']['missing_violations']==1
    assert result['runtime']['local_mutation_validation']['summary']['word']['missing_controls']==1
    assert not result['runtime']['rounds']


def test_default_unfrozen_feedback_generates_local_cases_and_persists_controls_in_version_history(tmp_path):
    ir=document(tmp_path,bad=True);control=RuntimeControl(tmp_path/'control');model=Model()
    result=online(tmp_path,ir,model,control)
    assert result['runtime']['status']=='promoted'
    assert result['runtime']['local_mutation_validation']['case_count']==2
    assert result['runtime']['rounds'][0]['gate']['verified_local_controls']==1
    manifest=Path(result['runtime']['candidate_path'])
    inventory=json.loads((manifest/'online-regressions.json').read_text())
    local=[c for c in inventory if c.get('validation_role') in {'local-mutant','local-control'}]
    assert len(local)==2 and all(c['origin']=='online-regression' and c['split']=='feedback' for c in local)
    assert any(c['validation_role']=='local-control' and c['expected'][0]['status']=='PASS' for c in local)
    assert control.snapshot()['active_version']==result['runtime']['promoted_version']


def test_local_cases_reject_candidate_that_only_memorizes_the_current_input(tmp_path):
    result=online(tmp_path,document(tmp_path,bad=True),Model(MEMO))
    assert result['runtime']['status']=='candidate_rejected' and result['packages'][0]['code']==OLD
    gate=result['runtime']['rounds'][0]['gate']
    assert gate['input_improvements']==1 and gate['regressions']>0
    assert gate['local_mutation_improvements']==0


def test_repaired_local_counterexample_can_promote_without_an_original_input_error(tmp_path):
    result=online(tmp_path,document(tmp_path),resources={'online_mutation_validation':{'when':'always'}})
    assert result['runtime']['status']=='promoted'
    gate=result['runtime']['rounds'][0]['gate']
    assert gate['input_improvements']==0 and gate['local_mutation_improvements']==1 and gate['passed']
    assert result['report']['rules'][0]['results'][0]['status']=='PASS'


def test_correct_input_default_does_not_force_mutation_or_revision(tmp_path):
    model=Model();result=online(tmp_path,document(tmp_path),model)
    assert result['runtime']['status']=='no_reliable_feedback'
    assert {task for task,_ in model.requests}=={'online-evidence-audit/1.0','online-evidence-review/1.0'}
    assert result['packages'][0]['code']==OLD


def test_frozen_input_never_calls_local_generation_or_promotes(tmp_path):
    control=RuntimeControl(tmp_path/'control');control.set_freeze(True);model=Model()
    result=online(tmp_path,document(tmp_path,bad=True),model,control,
        resources={'online_mutation_validation':{'when':'always'}})
    assert result['runtime']['status']=='frozen' and result['packages'][0]['code']==OLD
    assert model.requests==[] and control.snapshot()['active_version'] is None


def test_freeze_during_local_proposal_blocks_independent_labels_and_activation(tmp_path):
    control=RuntimeControl(tmp_path/'control');model=Model(on_proposals=lambda:control.set_freeze(True))
    result=online(tmp_path,document(tmp_path,bad=True),model,control)
    assert result['runtime']['status']=='frozen' and result['packages'][0]['code']==OLD
    assert 'benchmark-proposals/2.0' in [t for t,_ in model.requests]
    assert not any(t in {'benchmark-label/2.0','benchmark-review/2.0','paper-program-synthesis/2.0'} for t,_ in model.requests)
    assert control.snapshot()['active_version'] is None


def test_changed_parent_generation_during_local_proposal_keeps_original_report(tmp_path):
    control=RuntimeControl(tmp_path/'control')
    def race():control.set_freeze(True);control.set_freeze(False)
    result=online(tmp_path,document(tmp_path,bad=True),Model(on_proposals=race),control)
    assert result['runtime']['status']=='version_conflict' and result['packages'][0]['code']==OLD
    assert result['runtime']['report_version']['program_versions']==[package()['manifest']['version_id']]
    assert control.snapshot()['active_version'] is None


def test_local_generation_uses_persistent_scope_budget_and_cannot_reset_on_resume(tmp_path):
    from paper_compiler.budget import BudgetLedger
    from paper_compiler.request_limits import bounded_client
    ledger=BudgetLedger(tmp_path/'ledger.db','200')
    class Metered(Model):
        def __init__(self):super().__init__();self.ledger=ledger;self.max_attempts=1
        def complete_json(self,*args):
            rid=uuid.uuid4().hex;self.ledger.reserve(rid,'.1','framework-20261019','200')
            result=super().complete_json(*args);self.ledger.settle(rid,{},'.1');return result
    raw=Metered();client=bounded_client(raw,'online-task',max_cost_cny='.35')
    ir=document(tmp_path,bad=True);control=RuntimeControl(tmp_path/'control')
    first=online(tmp_path,ir,client,control)
    assert first['runtime']['status']=='budget_limit' and first['packages'][0]['code']==OLD
    before=ledger.summary()
    second=online(tmp_path,ir,bounded_client(raw,'online-task',max_cost_cny='.35'),control)
    assert second['runtime']['status']=='budget_limit'
    assert ledger.summary()==before and ledger.summary()['spent_cny']=='0.300000'
    assert control.snapshot()['active_version'] is None


def test_source_hash_mismatch_cannot_create_verified_local_cases(tmp_path):
    ir=document(tmp_path);Path(ir['source_artifacts'][0]['path']).write_text('Changed source bytes')
    with pytest.raises(ValueError,match='source|hash'):
        build(tmp_path,ir)


def test_second_round_receives_actual_local_candidate_error_and_can_repair_it(tmp_path):
    class Repair(Model):
        def complete_json(self,task,instructions,data,max_tokens):
            if task=='paper-program-synthesis/2.0':
                self.requests.append((task,copy.deepcopy(data)))
                earlier=[t for t,_ in self.requests].count(task)
                if earlier==1:return candidate(MEMO)
                assert any(f.get('case_id') and f.get('candidate_status')=='PASS' and f.get('expected')=='VIOLATION' for f in data['feedback'])
                return candidate(FIX)
            return super().complete_json(task,instructions,data,max_tokens)
    result=online(tmp_path,document(tmp_path,bad=True),Repair(),max_rounds=2)
    assert result['runtime']['status']=='promoted' and len(result['runtime']['rounds'])==2
    assert not result['runtime']['rounds'][0]['gate']['passed']
    assert result['runtime']['rounds'][1]['gate']['passed']


def semantic_package():
    value=candidate("def detect(payload):\n    return [emit(n,'PASS','Accepted') for n in nodes(payload,'ReferenceUse')]\n")
    value['target_kinds']=['ReferenceUse'];value['requires']=['bibliography_fields','external_work']
    return build_program(value,rule_text='Citations must positively support their actual stated use.',
        basis=[{'id':'project-term','text':'Use only positively supported methods; explicit exclusion proves misuse.'}],model=base_model())


class SemanticModel(Model):
    def complete_json(self,task,instructions,data,max_tokens):
        answer=super().complete_json(task,instructions,data,max_tokens)
        if task in {'benchmark-label/2.0','benchmark-review/2.0'}:
            required=data['evidence_requirements']['required']
            assert {'original_local','mutated_local','original_cited_work_content','mutated_cited_work_content'}<=set(required)
            assert data['original_confirmed_work_bindings'] and data['mutated_confirmed_work_bindings']
            answer.update(original_basis='explicit_support',
                          original_reason='The original cited method is expressly supported in the identified source.',
                          basis='explicit_support' if answer['status']=='PASS' else 'explicit_scope_contradiction',
                          reason='The identified source expressly supports this use.' if answer['status']=='PASS' else
                                 'The identified source explicitly excludes this changed method use.')
            if self.mode=='original_unproved':answer['original_basis']='topic_mismatch'
            if self.mode=='control_unproved' and answer['status']=='PASS':answer.pop('basis')
            if self.mode=='bad_negative_basis' and answer['status']=='VIOLATION':answer['basis']='topic_mismatch'
            if self.mode=='review_unproved' and task=='benchmark-review/2.0':answer.pop('original_reason')
        return answer


def semantic_build(tmp_path,model,*,body=None,identified=True):
    from test_paper_compiler_program_analysis import Gateway,Model as Facts
    ir=document(tmp_path);pkg=semantic_package()
    gateway=Gateway(empty=not identified,text=body or 'Tree models estimate lakes. This method explicitly excludes wide models.')
    materialized,analysis,_=detect(ir,[pkg],client=Facts(),gateway=gateway,cache_dir=tmp_path/'semantic-cache')
    return local_api()(materialized,[pkg],analysis,client=model,gateway=gateway,output_dir=tmp_path/'semantic-local')


def test_citation_local_cases_ground_original_and_changed_context_with_identified_work_content(tmp_path):
    model=SemanticModel();result=semantic_build(tmp_path,model)
    assert result['status']=='complete' and len(result['cases'])==2
    for case in result['cases']:
        assert case['label_evidence']['label']['original_basis']=='explicit_support'
        assert case['label_evidence']['review']['original_basis']=='explicit_support'
        assert case['label_evidence']['label']['basis']==('explicit_support' if case['validation_role']=='local-control' else 'explicit_scope_contradiction')


@pytest.mark.parametrize('mode', ['original_unproved','control_unproved','bad_negative_basis','review_unproved'])
def test_semantic_case_needs_two_independent_positive_support_or_contradiction_observations(tmp_path,mode):
    result=semantic_build(tmp_path,SemanticModel(mode=mode))
    assert result['status']=='incomplete'
    assert result['rejections']
    assert any('citation' in row['reason'] for row in result['rejections'])


def test_topic_body_without_explicit_contradiction_cannot_validate_semantic_negative(tmp_path):
    result=semantic_build(tmp_path,SemanticModel(),body='A catalog of coins describes historical measurements.')
    assert result['status']=='incomplete'
    assert result['summary']['word']['missing_violations']==1
    assert result['summary']['word']['violations']==0


def test_missing_identified_cited_work_content_is_unknown_before_any_mutation_request(tmp_path):
    model=SemanticModel();result=semantic_build(tmp_path,model,identified=False)
    assert result['status']=='incomplete' and result['cases']==[]
    assert result['summary']['word']['missing_controls']==1
    assert any('identified' in row['reason'] for row in result['rejections'])
    assert model.requests==[]


def test_new_local_cases_do_not_evict_inherited_controls_before_candidate_gate(tmp_path):
    controls_folder=tmp_path/'controls-source';controls_folder.mkdir()
    control_ir=document(controls_folder)
    controls=[]
    for index in range(32):
        frozen=copy.deepcopy(control_ir);frozen['revision']='protected-'+str(index)
        controls.append({'id':'protected-'+str(index),'verified':True,'origin':'online-regression','ir':frozen,
                         'expected':[{'rule_id':'word','node_id':'p','status':'PASS'}]})
    code="def detect(payload):\n    return [emit(n, 'VIOLATION' if payload['ir']['revision']=='protected-0' else ('PASS' if 'tree' in n['text'] else 'VIOLATION'), 'Checked source') for n in nodes(payload,'Paragraph')]\n"
    result=online(tmp_path,document(tmp_path,bad=True),Model(code),resources={'regression_cases':controls})
    assert result['runtime']['status']=='candidate_rejected'
    gate=result['runtime']['rounds'][0]['gate']
    assert gate['verified_regression_cases']==34 and gate['regressions']>=1


def test_already_correct_local_cases_do_not_force_a_revision_or_claim_candidate_validation(tmp_path):
    from paper_compiler.online_loop import online_refine
    ir=document(tmp_path);old=package()
    fixed=build_program(candidate(FIX),rule_text=old['input']['rule_text'],basis=old['input']['basis'],model=base_model())
    model=Model();control=RuntimeControl(tmp_path/'control')
    result=online_refine(ir,[fixed],client=model,gateway=None,cache_dir=tmp_path/'cache',
        control=control,output_dir=tmp_path/'online',resources={'online_mutation_validation':{'when':'always'}})
    assert result['runtime']['status']=='no_reliable_feedback'
    assert result['runtime']['local_mutation_validation']['status']=='complete'
    assert result['runtime']['candidate_validation']=='not_run'
    assert 'paper-program-synthesis/2.0' not in [t for t,_ in model.requests]
    assert result['packages'][0]['code']==FIX and control.snapshot()['active_version'] is None


def test_frozen_local_case_tampering_is_rejected_without_relabeling(tmp_path):
    ir=document(tmp_path);first=build(tmp_path,ir)
    path=Path(first['builder_manifest_path']);manifest=json.loads(path.read_text())
    case_path=Path(manifest['cases'][0]['ir_path']);value=json.loads(case_path.read_text());value['revision']='tampered'
    case_path.write_text(json.dumps(value))
    model=Model()
    with pytest.raises(ValueError,match='integrity|hash'):
        build(tmp_path,ir,model)
    assert model.requests==[]


def test_unfamiliar_rule_identity_uses_the_same_generic_mutation_path(tmp_path):
    ir=document(tmp_path);raw=candidate(OLD);raw['rule_id']='unfamiliar-normative-903'
    pkg=build_program(raw,rule_text='Every method paragraph must use tree models.',
        basis=[{'id':'project-term','text':'Use tree models in method paragraphs.'}],model=base_model())
    materialized,analysis,_=detect(ir,[pkg],client=None,gateway=None,cache_dir=tmp_path/'cache')
    result=local_api()(materialized,[pkg],analysis,client=Model(),gateway=None,output_dir=tmp_path/'local')
    assert result['status']=='complete'
    assert {c['expected'][0]['rule_id'] for c in result['cases']}=={'unfamiliar-normative-903'}
