import copy
import importlib
import importlib.util

import pytest

from paper_compiler.model_runtime import base_model
from paper_compiler.programs import build_program
from paper_compiler.runtime_control import RuntimeControl
from test_paper_compiler_program_analysis import paper


OLD = "def detect(payload):\n    return [emit(n, 'PASS', 'Accepted') for n in nodes(payload, 'Paragraph')]\n"
FIX = "def detect(payload):\n    return [emit(n, 'PASS' if 'tree' in n['text'] else 'VIOLATION', 'Checked source') for n in nodes(payload, 'Paragraph')]\n"
BAD = "def detect(payload):\n    return [emit(n, 'VIOLATION', 'Always fails') for n in nodes(payload, 'Paragraph')]\n"


def candidate(code):
    return {'rule_id':'word','title':'Required source term','requires':[], 'target_kinds':['Paragraph'],
            'code':code,'analysis_requests':[],'model_patch':{}}


def package():
    return build_program(candidate(OLD),rule_text='A paragraph must use tree models.',
                         basis=[{'id':'project-term','text':'Use tree models in the method paragraph.'}],model=base_model())


def api():
    assert importlib.util.find_spec('paper_compiler.online_loop') is not None, 'online refinement orchestrator is missing'
    online_refine = importlib.import_module('paper_compiler.online_loop').online_refine
    # These fixtures exercise the original audit/CAS contract. New source-level
    # generation and its default policy have dedicated real-builder tests.
    def legacy_call(*args, resources=None, **kwargs):
        return online_refine(*args, resources={'online_mutation_validation': False, **(resources or {})}, **kwargs)
    return legacy_call


class Model:
    config={'MAAS_MODEL':'fake','MAAS_MODEL_VERSION':'online-v1'}
    def __init__(self, code=FIX, *, grounded=True, agree=True, on_synthesis=None):
        self.code=code;self.grounded=grounded;self.agree=agree;self.on_synthesis=on_synthesis;self.tasks=[]
    def complete_json(self,task,instructions,data,max_tokens):
        self.tasks.append(task)
        if task in {'online-evidence-audit/1.0','online-evidence-review/1.0'}:
            assert 'report' not in data and 'predictions' not in data and 'expected' not in data
            rows=[]
            for target in data['targets']:
                source=next(s for s in target['sources'] if s.get('node_id')==target['node_id'])
                status='PASS' if 'tree' in source['text'] else 'VIOLATION'
                if task.startswith('online-evidence-review') and not self.agree:status='UNKNOWN'
                rows.append({'rule_id':target['rule_id'],'node_id':target['node_id'],'status':status,
                    'reason':'The local source explicitly uses this method.', 'basis_ids':['project-term'],
                    'basis':'direct_observation','quotes':[{'source_id':source['source_id'],
                    'quote':source['text'] if self.grounded else 'Invented unsupported source'}]})
            return {'judgments':rows}
        assert task=='paper-program-synthesis/2.0'
        assert data['feedback'] and data['previous_candidate']['code']==OLD
        if self.on_synthesis:self.on_synthesis()
        return candidate(self.code)


def mutant(tmp_path):
    ir=paper(tmp_path)
    ir['nodes'][1]['text']='We apply wide models [1].'
    ir['nodes'][1]['provenance']=[{'kind':'synthetic','operation_id':'online-input',
                                'ancestor_provenance':ir['nodes'][1]['provenance']}]
    return ir


def call(tmp_path,ir,packages,model,control,**kwargs):
    return api()(ir,packages,client=model,gateway=None,cache_dir=tmp_path/'cache',
                 control=control,output_dir=tmp_path/'online',**kwargs)


def test_reliable_blind_feedback_changes_real_code_reexecutes_and_promotes(tmp_path):
    ir=mutant(tmp_path);old=package();control=RuntimeControl(tmp_path/'control');model=Model()
    result=call(tmp_path,ir,[old],model,control)
    assert result['packages'][0]['code']==FIX
    row=result['report']['rules'][0]['results'][0]
    assert row['node_id']=='p' and row['status']=='VIOLATION'
    assert result['runtime']['status']=='promoted'
    assert control.snapshot()['active_version']==result['runtime']['promoted_version']
    assert {'online-evidence-audit/1.0','online-evidence-review/1.0','paper-program-synthesis/2.0'}<=set(model.tasks)
    assert (tmp_path/'online').exists()


def test_freeze_allows_current_detection_but_blocks_audit_revision_and_promotion(tmp_path):
    control=RuntimeControl(tmp_path/'control');control.set_freeze(True);model=Model();old=package()
    result=call(tmp_path,mutant(tmp_path),[old],model,control)
    assert result['packages'][0]['code']==OLD and result['runtime']['status']=='frozen'
    assert model.tasks==[] and control.snapshot()['active_version'] is None
    assert result['report']['rules'][0]['results'][0]['status']=='PASS'


@pytest.mark.parametrize('grounded,agree',[(False,True),(True,False)])
def test_missing_evidence_or_disagreeing_review_keeps_old_program(tmp_path,grounded,agree):
    control=RuntimeControl(tmp_path/'control');model=Model(grounded=grounded,agree=agree)
    result=call(tmp_path,mutant(tmp_path),[package()],model,control)
    assert result['packages'][0]['code']==OLD
    assert result['runtime']['status']=='no_reliable_feedback'
    assert 'paper-program-synthesis/2.0' not in model.tasks and control.snapshot()['active_version'] is None


def test_correct_current_program_is_not_revised_without_an_evidenced_problem(tmp_path):
    control=RuntimeControl(tmp_path/'control');model=Model()
    result=call(tmp_path,paper(tmp_path),[package()],model,control)
    assert result['runtime']['status']=='no_reliable_feedback'
    assert result['packages'][0]['code']==OLD and 'paper-program-synthesis/2.0' not in model.tasks


def test_candidate_that_breaks_a_verified_regression_is_kept_inactive(tmp_path):
    control=RuntimeControl(tmp_path/'control');model=Model(BAD)
    control_ir=paper(tmp_path)
    resources={'regression_cases':[{'id':'known-control','verified':True,'origin':'online-regression',
                'ir':control_ir,'expected':[{'rule_id':'word','node_id':'p','status':'PASS'}]}]}
    result=call(tmp_path,mutant(tmp_path),[package()],model,control,resources=resources,max_rounds=1)
    assert result['packages'][0]['code']==OLD and control.snapshot()['active_version'] is None
    assert result['runtime']['status']=='candidate_rejected'
    assert result['runtime']['rounds'][0]['gate']['regressions']>0


def test_freeze_during_inflight_synthesis_prevents_candidate_activation(tmp_path):
    control=RuntimeControl(tmp_path/'control')
    model=Model(on_synthesis=lambda:control.set_freeze(True))
    result=call(tmp_path,mutant(tmp_path),[package()],model,control)
    assert result['runtime']['status']=='frozen' and result['packages'][0]['code']==OLD
    assert control.snapshot()['active_version'] is None


def test_generation_compare_and_swap_rejects_a_concurrent_state_change(tmp_path):
    control=RuntimeControl(tmp_path/'control')
    def race():
        other=RuntimeControl(tmp_path/'control')
        other.set_freeze(True);other.set_freeze(False)
    result=call(tmp_path,mutant(tmp_path),[package()],Model(on_synthesis=race),control)
    assert result['runtime']['status']=='version_conflict' and result['packages'][0]['code']==OLD
    assert control.snapshot()['generation']==2 and control.snapshot()['active_version'] is None


def test_formal_holdout_regression_labels_are_never_consumed(tmp_path):
    resources={'regression_cases':[{'id':'formal-test','verified':True,'split':'test','ir':paper(tmp_path),
        'expected':[{'rule_id':'word','node_id':'p','status':'VIOLATION'}]}]}
    model=Model();control=RuntimeControl(tmp_path/'control')
    with pytest.raises(ValueError,match='holdout|independent|formal'):
        call(tmp_path,mutant(tmp_path),[package()],model,control,resources=resources)
    assert model.tasks==[]


def test_no_reliable_feedback_does_not_mark_a_suite_behavior_validated(tmp_path):
    control=RuntimeControl(tmp_path/'control');model=Model(grounded=False)
    result=call(tmp_path,mutant(tmp_path),[package()],model,control)
    assert result['runtime']['status']=='no_reliable_feedback'
    assert result['runtime']['candidate_validation']=='not_run'
    assert result['runtime']['promotion_gate_passed'] is False
    assert not list((tmp_path/'online').rglob('validation.json'))


def test_frozen_detection_can_still_call_necessary_fixed_semantic_api(tmp_path):
    code="def detect(payload):\n    return [emit(n, 'PASS' if fact(payload,'method_fact',n['id'],'method')['state']=='observed' else 'UNKNOWN', 'Semantic observation') for n in nodes(payload,'Paragraph')]\n"
    entry=candidate(code);entry['requires']=['method_fact']
    entry['analysis_requests']=[{'name':'method_fact','targets':['Paragraph'],'fields':{'method':'string'},
                                'instructions':'Extract the source method.'}]
    generated=build_program(entry,rule_text='Read the source method.',basis=[],model=base_model())
    class SemanticModel(Model):
        def complete_json(self,task,instructions,data,max_tokens):
            self.tasks.append(task)
            assert task=='generated-analysis/2.0'
            return {'fields':{'method':{'state':'observed','value':'tree models',
                    'quotes':[{'source_id':'paper:p','quote':'tree models'}]}}}
    control=RuntimeControl(tmp_path/'control');control.set_freeze(True);model=SemanticModel()
    result=call(tmp_path,paper(tmp_path),[generated],model,control)
    assert result['runtime']['status']=='frozen'
    assert result['report']['rules'][0]['results'][0]['status']=='PASS'
    assert model.tasks==['generated-analysis/2.0']


def test_cas_conflict_keeps_report_version_distinct_from_the_new_active_version(tmp_path):
    from paper_compiler.pipeline import detect,save_suite
    control=RuntimeControl(tmp_path/'control');old=package()
    initial_path=tmp_path/'initial-suite'
    initial=save_suite([old],initial_path,validated=True,validation={'source_verified_control':True})
    control.promote(initial['version_id'],initial_path,None,expected_generation=0)
    changed=build_program(candidate(FIX),rule_text=old['input']['rule_text'],basis=old['input']['basis'],model=base_model())
    competitor_path=tmp_path/'competitor-suite'
    # Execute the concurrent candidate before declaring that test release valid.
    _,_,checked=detect(mutant(tmp_path),[changed],client=None,gateway=None,cache_dir=tmp_path/'competitor-cache')
    assert checked['rules'][0]['results'][0]['status']=='VIOLATION'
    competitor=save_suite([changed],competitor_path,validated=True,validation={'behavior_executed':True})
    def race():
        other=RuntimeControl(tmp_path/'control')
        other.promote(competitor['version_id'],competitor_path,initial['version_id'],expected_generation=1)
    result=call(tmp_path,mutant(tmp_path),[old],Model(on_synthesis=race),control)
    assert result['runtime']['status']=='version_conflict'
    assert result['report']['rules'][0]['results'][0]['status']=='PASS'
    assert result['runtime']['report_version']['suite_version']==initial['version_id']
    assert result['runtime']['report_version']['program_versions']==[old['manifest']['version_id']]
    assert result['runtime']['current_snapshot']['active_version']==competitor['version_id']
    assert result['runtime']['report_version']['suite_version']!=result['runtime']['current_snapshot']['active_version']


@pytest.mark.parametrize('basis,two_sides',[
    ('missing_detail',True),('topic_mismatch',True),('explicit_scope_contradiction',False),
])
def test_online_citation_violation_needs_positive_contradiction_and_both_sources(tmp_path,basis,two_sides):
    from test_paper_compiler_program_analysis import Gateway,Model as FactModel,grounded_reference
    code="def detect(payload):\n    return [emit(n,'PASS','Accepted') for n in nodes(payload,'ReferenceUse')]\n"
    entry=candidate(code);entry['target_kinds']=['ReferenceUse'];entry['requires']=['citation_facts']
    entry['analysis_requests']=[{'name':'citation_facts','targets':['ReferenceUse'],'fields':{'related':'boolean'},
                                'instructions':'Check the exact cited source contribution.'}]
    original=build_program(entry,rule_text='The cited source must support this specific use.',
                           basis=[{'id':'project-term','text':'Require source-supported citation purpose.'}],model=base_model())
    class AuditModel(Model):
        def __init__(self):super().__init__();self.facts=FactModel(grounded_reference)
        def complete_json(self,task,instructions,data,max_tokens):
            self.tasks.append(task)
            if task in {'bibliography-fields/1.1','generated-analysis/2.0'}:
                return self.facts.complete_json(task,instructions,data,max_tokens)
            assert task in {'online-evidence-audit/1.0','online-evidence-review/1.0'}
            target=data['targets'][0]
            source=next(s for s in target['sources'] if s.get('node_id')=='p')
            external=next(s for s in target['sources'] if s['origin']=='external')
            quotes=[{'source_id':source['source_id'],'quote':'We apply tree models'}]
            if two_sides:quotes.append({'source_id':external['source_id'],'quote':external['text']})
            return {'judgments':[{'rule_id':'word','node_id':'use','status':'VIOLATION',
                'reason':'The cited source explicitly excludes computational methods.', 'basis':basis,
                'basis_ids':['project-term'],'quotes':quotes}]}
    model=AuditModel();control=RuntimeControl(tmp_path/'control')
    gateway=Gateway(text='This work exclusively inventories coins and makes no computational contribution.')
    result=api()(paper(tmp_path),[original],client=model,gateway=gateway,cache_dir=tmp_path/'cache',
                 control=control,output_dir=tmp_path/'online')
    assert result['runtime']['status']=='no_reliable_feedback'
    assert 'paper-program-synthesis/2.0' not in model.tasks


def test_formal_origin_cannot_be_hidden_behind_a_feedback_split(tmp_path):
    resources={'regression_cases':[{'id':'hidden-formal-case','verified':True,'split':'feedback',
        'origin':'formal-independent-test','ir':paper(tmp_path),
        'expected':[{'rule_id':'word','node_id':'p','status':'VIOLATION'}]}]}
    model=Model();control=RuntimeControl(tmp_path/'control')
    with pytest.raises(ValueError,match='holdout|independent|formal'):
        call(tmp_path,mutant(tmp_path),[package()],model,control,resources=resources)
    assert model.tasks==[]


def test_invalid_generated_candidate_keeps_old_code_and_records_execution_failure(tmp_path):
    model=Model("def detect(payload):\n    return open('/private/data')\n")
    control=RuntimeControl(tmp_path/'control')
    result=call(tmp_path,mutant(tmp_path),[package()],model,control,max_rounds=1)
    assert result['runtime']['status']=='candidate_rejected'
    assert result['packages'][0]['code']==OLD and control.snapshot()['active_version'] is None
    assert result['runtime']['rounds'][0]['status']=='candidate_failed'
    assert result['runtime']['candidate_validation']=='not_run'


# Frozen source/input and response shape from the real resource-type API probe.
RESOURCE_TYPE_PROBE = {'ir': {'coverage': {'bibliography': {'reason': 'synthetic benchmark parent', 'status': 'partial'}}, 'document_id': 'constructed-46f40d112f277d65bee836d2', 'extensions': {'paper_model': {'base_version': 'paper-model/1.0', 'node_types': {}, 'schema_version': 'paper-model-definition/1.0', 'version': 'paper-model/1.0'}}, 'layout': {'pages': []}, 'metadata': {'construction_source_id': 'arxiv:1706.03762', 'context_origin': 'constructed', 'derivation': {'operation_id': 'online-resource-type-probe', 'parent_sha256': 'ddd6f21206f6d6fb77b5a82f3e7d0510420255d05df3339fab8e44ff82457a0c'}}, 'model_version': 'paper-model/1.0', 'nodes': [{'attrs': {}, 'children': ['context', 'bibliography'], 'id': 'paper', 'kind': 'Paper', 'provenance': [], 'text': None}, {'attrs': {}, 'children': ['context-citation-0'], 'id': 'context', 'kind': 'Paragraph', 'provenance': [{'kind': 'synthetic', 'operation_id': 'construct-46f40d112f277d65bee836d2'}], 'text': 'We use the Transformer architecture [1].'}, {'attrs': {}, 'children': ['entry-1'], 'id': 'bibliography', 'kind': 'Bibliography', 'provenance': [], 'text': None}, {'attrs': {'fields': {}, 'key': '1', 'resource_type': {'reason': 'source content changed; rederive type', 'state': 'unknown'}}, 'children': [], 'id': 'entry-1', 'kind': 'BibliographyEntry', 'provenance': [{'ancestor_provenance': [{'kind': 'synthetic', 'operation_id': 'construct-46f40d112f277d65bee836d2'}], 'kind': 'synthetic', 'operation_id': 'online-resource-type-probe'}], 'text': '[1] VASWANI A, SHAZEER N, PARMAR N, et al. Attention is all you need[D]//Advances in Neural Information Processing Systems. 2017: 5998-6008.'}, {'attrs': {'marker': '[1]', 'style': 'numeric'}, 'children': ['context-citation-0-use-0'], 'id': 'context-citation-0', 'kind': 'CitationGroup', 'provenance': [{'kind': 'synthetic', 'operation_id': 'construct-46f40d112f277d65bee836d2'}], 'text': '[1]'}, {'attrs': {'expected_kind': 'BibliographyEntry', 'namespace': 'bibliography', 'scope_id': 'bibliography', 'selector': {'kind': 'numeric', 'value': '1'}}, 'children': [], 'id': 'context-citation-0-use-0', 'kind': 'ReferenceUse', 'provenance': [{'kind': 'synthetic', 'operation_id': 'construct-46f40d112f277d65bee836d2'}], 'text': '[1]'}], 'profile': {}, 'revision': 'mutation-online-resource-type-probe', 'root_id': 'paper', 'schema_version': 'paper-ir/1.0', 'source_artifacts': [{'id': 'constructed-text', 'kind': 'text', 'path': '/data/results/paper-compiler/framework-20261019/smoke/parents/constructed-46f40d112f277d65bee836d2/constructed-source.txt', 'sha256': '1b73d65eca19bed483e5ea01fd646d14a569e7c67363d441800baa337093e1e7'}]}, 'basis': [{'id': 'gbt7714-2025:A', 'pdf_pages': [34, 35], 'review': 'transcribed normative summary checked against supplied page images', 'source_sha256': '24aeb9dcd3af0e2800995ec2c5c058c4cf05dd8b8e36097c0eecf6af367f5146', 'text': '文献类型代码：M图书，J期刊，N报纸，C会议录，D学位论文，R报告，S标准，P专利，EB网站/网页，A档案，CM地图，DS数据集，PP预印本，G汇编，CP计算机程序，DB数据库，Z其他。载体代码MT磁带、DK磁盘、CD光盘、OL联机网络、MM缩微资料。类型和载体标识置于方括号内，载体前用/。'}, {'id': 'gbt7714-2025:8.6', 'pdf_pages': [19, 20], 'review': 'transcribed normative summary checked against supplied page images', 'source_sha256': '24aeb9dcd3af0e2800995ec2c5c058c4cf05dd8b8e36097c0eecf6af367f5146', 'text': '一般会议录题名、类型标识必备，只有当被引资源是电子资源时，才要求载体和路径必备；责任者、会议名、会议年份、页码有则必备。会议录若以图书、图书析出、连续出版物及其析出形式出现，应按相应形式著录。一般形式为作者.题名[类型/载体]//会议名,会议年份:页码.路径.永久标识符。'}, {'id': 'gbt7714-2025:9.1-9.2', 'pdf_pages': [29, 30, 31], 'review': 'transcribed normative summary checked against supplied page images', 'source_sha256': '24aeb9dcd3af0e2800995ec2c5c058c4cf05dd8b8e36097c0eecf6af367f5146', 'text': '允许顺序编码制或著者-出版年制。顺序编码制按正文首次引用先后连续编号，序号放在[]内；脚注自动编号允许圈码。同处多引的各编号用逗号，连续序号用短横线；自动编号有例外，不能据PDF缺少生成信息直接否定例外。重复引用沿用首次编号，页码置于方括号外；自动脚注可重复著录及简写。参考文献表按文内编号依次排列。'}], 'audit': {'judgments': [{'basis': 'explicit_support', 'basis_ids': ['gbt7714-2025:A', 'gbt7714-2025:8.6'], 'node_id': 'entry-1', 'quotes': [{'quote': 'Attention is all you need[D]//Advances in Neural Information Processing Systems', 'source_id': 'paper:entry-1'}, {'quote': '文献类型代码：M图书，J期刊，N报纸，C会议录，D学位论文，R报告，S标准，P专利，EB网站/网页，A档案，CM地图，DS数据集，PP预印本，G汇编，CP计算机程序，DB数据库，Z其他。', 'source_id': 'gbt7714-2025:A'}, {'quote': '一般会议录题名、类型标识必备', 'source_id': 'gbt7714-2025:8.6'}], 'reason': 'The entry marks the work with type code [D], which GB/T 7714-2025 Appendix A reserves for dissertations (学位论文). The cited work is a conference paper published in Advances in Neural Information Processing Systems, so the type identifier should be [C] (会议录). The observed [D] is therefore an incorrect document-type identifier, i.e. a citation format error.', 'rule_id': '31', 'search_scope': [], 'status': 'VIOLATION'}, {'basis': 'direct_observation', 'basis_ids': ['gbt7714-2025:9.1-9.2'], 'node_id': 'context-citation-0', 'quotes': [{'quote': '[1]', 'source_id': 'paper:context-citation-0'}, {'quote': 'We use the Transformer architecture [1].', 'source_id': 'paper:context'}], 'reason': "The supplied sources for this node are only the in-text marker '[1]' and the sentence 'We use the Transformer architecture [1].' They are partial and do not include the full bibliography or the cited work's content. The numeric marker style is permitted by GB/T 7714-2025, and no positive contradiction with the citation-format rule is shown. Insufficient evidence to judge.", 'rule_id': '31', 'search_scope': [], 'status': 'UNKNOWN'}]}, 'review': {'judgments': [{'basis': 'explicit_support', 'basis_ids': ['gbt7714-2025:A', 'gbt7714-2025:8.6'], 'node_id': 'entry-1', 'quotes': [{'quote': 'Attention is all you need[D]//Advances in Neural Information Processing Systems', 'source_id': 'paper:entry-1'}, {'quote': '文献类型代码：M图书，J期刊，N报纸，C会议录，D学位论文，R报告，S标准，P专利，EB网站/网页，A档案，CM地图，DS数据集，PP预印本，G汇编，CP计算机程序，DB数据库，Z其他。', 'source_id': 'gbt7714-2025:A'}, {'quote': '一般会议录题名、类型标识必备', 'source_id': 'gbt7714-2025:8.6'}], 'reason': "The entry is a conference paper (NeurIPS proceedings) but is marked with type code [D], which GB/T 7714 Appendix A reserves for dissertations (学位论文). The correct type code for a conference paper is C (会议录). The entry also uses the '//' separator and conference-style formatting, confirming it is a conference paper, so the [D] type identifier is a citation format error.", 'rule_id': '31', 'search_scope': [], 'status': 'VIOLATION'}, {'basis': 'direct_observation', 'basis_ids': ['gbt7714-2025:9.1-9.2'], 'node_id': 'context-citation-0', 'quotes': [{'quote': '[1]', 'source_id': 'paper:context-citation-0'}, {'quote': 'We use the Transformer architecture [1].', 'source_id': 'paper:context'}], 'reason': "The citation group source is only the marker '[1]' with partial coverage, and the surrounding context 'We use the Transformer architecture [1].' does not provide enough information to determine whether the numeric citation format itself is erroneous. No explicit contradiction with the numeric citation rules is present in the supplied partial sources.", 'rule_id': '31', 'search_scope': [], 'status': 'UNKNOWN'}]}}


def resource_type_probe():
    from paper_compiler.analysis import base_analysis
    from paper_compiler.online_loop import _packet
    fixture=copy.deepcopy(RESOURCE_TYPE_PROBE)
    entry={'rule_id':'31','title':'Reference formatting','requires':[],
           'target_kinds':['BibliographyEntry','CitationGroup'],
           'code':"def detect(payload):\n    return []\n",'analysis_requests':[],'model_patch':{}}
    program=build_program(entry,rule_text='引用格式错误',basis=fixture['basis'],model=base_model())
    _,views=_packet(fixture['ir'],base_analysis(fixture['ir']),[program],None,None,limit=8)
    return fixture,views


def test_real_resource_type_probe_accepts_exact_normative_quotes_and_keeps_document_evidence():
    from paper_compiler.online_loop import _ground_judgments
    fixture,views=resource_type_probe()
    for answer in [fixture['audit'],fixture['review']]:
        verified=_ground_judgments(answer,views,fixture['ir'])
        assert set(verified)=={('31','entry-1')}
        row=verified[('31','entry-1')]
        assert row['status']=='VIOLATION'
        assert any(e['kind']=='source_span' and e.get('node_id')=='entry-1' for e in row['evidence'])
        norm=[e for e in row['evidence'] if e['kind']=='normative_span']
        assert {e['basis_id'] for e in norm}=={'gbt7714-2025:A','gbt7714-2025:8.6'}
        basis={b['id']:b['text'] for b in fixture['basis']}
        assert all(basis[e['basis_id']][e['start']:e['end']]==e['quote'] for e in norm)


@pytest.mark.parametrize('change',[
    lambda row:row['quotes'][1].update(quote='伪造的规范要求必须使用D'),
    lambda row:row['quotes'][1].update(source_id='gbt7714-2025:not-supplied'),
    lambda row:row['quotes'][0].update(quote='Invented paper entry text'),
    lambda row:row.update(quotes=row['quotes'][1:]),
])
def test_normative_quotes_cannot_hide_invalid_quotes_or_replace_paper_evidence(change):
    from paper_compiler.online_loop import _ground_judgments
    fixture,views=resource_type_probe()
    change(fixture['audit']['judgments'][0])
    assert ('31','entry-1') not in _ground_judgments(fixture['audit'],views,fixture['ir'])


def test_normative_quote_cannot_replace_cited_work_evidence_for_a_semantic_violation(tmp_path):
    from paper_compiler.online_loop import _ground_judgments
    ir=paper(tmp_path)
    entry=candidate(OLD);entry['target_kinds']=['ReferenceUse'];entry['requires']=['support_facts']
    entry['analysis_requests']=[{'name':'support_facts','targets':['ReferenceUse'],'fields':{'related':'boolean'},
                                'instructions':'Inspect this citation contribution with source evidence.'}]
    normative='The cited source must provide the claimed contribution.'
    program=build_program(entry,rule_text='Require the claimed citation contribution.',
                           basis=[{'id':'project-term','text':normative}],model=base_model())
    use=next(n for n in ir['nodes'] if n['id']=='use')
    external='This work exclusively inventories coins and makes no computational contribution.'
    data={'node':use,'citation_context':{'node_id':'p'},'sources':[
        {'source_id':'paper:p','origin':'paper','node_id':'p','text':ir['nodes'][1]['text'],
         'coverage':'partial','complete':False},
        {'source_id':'external:work1','origin':'external','content_id':'work1','work_id':'identified-work',
         'text':external,'coverage':'full_text','complete':True}]}
    row={'rule_id':'word','node_id':'use','status':'VIOLATION',
         'reason':'The cited source explicitly excludes computational contributions.',
         'basis':'explicit_scope_contradiction','basis_ids':['project-term'],
         'quotes':[{'source_id':'paper:p','quote':'We apply tree models'},
                   {'source_id':'project-term','quote':normative}]}
    views={('word','use'):(data,program,use)}
    assert _ground_judgments({'judgments':[row]},views,ir)=={}
    row['quotes'].append({'source_id':'external:work1','quote':external})
    verified=_ground_judgments({'judgments':[row]},views,ir)
    assert verified[('word','use')]['status']=='VIOLATION'
    assert {e.get('origin') for e in verified[('word','use')]['evidence'] if e['kind']!='normative_span'}=={'paper','external'}


def test_second_online_round_receives_actual_schema_error_and_failed_raw_candidate(tmp_path):
    class RepairsSchemaAfterFeedback(Model):
        def __init__(self):super().__init__();self.synthesis_inputs=[]
        def complete_json(self,task,instructions,data,max_tokens):
            if task!='paper-program-synthesis/2.0':
                return super().complete_json(task,instructions,data,max_tokens)
            self.tasks.append(task)
            self.synthesis_inputs.append(copy.deepcopy(data))
            errors=[row for row in data['feedback'] if row.get('error_type')=='ProgramError']
            if errors and any(row.get('failed_candidate',{}).get('analysis_requests_note') for row in errors):
                return candidate(FIX)
            return {**candidate(FIX),'analysis_requests_note':'This explanatory field is outside the exact contract.'}
    model=RepairsSchemaAfterFeedback();control=RuntimeControl(tmp_path/'control')
    result=call(tmp_path,mutant(tmp_path),[package()],model,control,max_rounds=2)
    assert result['runtime']['status']=='promoted'
    assert result['packages'][0]['code']==FIX
    assert result['report']['rules'][0]['results'][0]['status']=='VIOLATION'
    assert len(model.synthesis_inputs)==2
    feedback=model.synthesis_inputs[1]['feedback']
    assert any('independently_verified_online_difference' in row.get('failure_types',[]) for row in feedback)
    failure=next(row for row in feedback if row.get('error_type')=='ProgramError')
    assert failure['reason']=='candidate fields mismatch'
    assert failure['failed_candidate']['analysis_requests_note']=='This explanatory field is outside the exact contract.'
    assert failure['failed_candidate']['code']==FIX
    assert result['runtime']['rounds'][0]['status']=='candidate_failed'
    assert result['runtime']['rounds'][1]['status']=='evaluated'

def test_citation_auditor_cannot_lose_safeguards_when_program_omits_analysis(tmp_path):
    from paper_compiler.online_loop import _ground_judgments
    ir=paper(tmp_path)
    entry=candidate("def detect(payload):\n    return [emit(n,'PASS','Accepted') for n in nodes(payload,'ReferenceUse')]")
    entry['target_kinds']=['ReferenceUse']
    generated=build_program(entry,rule_text='The cited work must support this citation purpose.',
        basis=[{'id':'project-term','text':'Check citation purpose against the identified cited work.'}])
    node=next(n for n in ir['nodes'] if n['id']=='use')
    data={'node':node,'citation_context':{'node_id':'p'},'sources':[
        {'source_id':'paper:p','origin':'paper','node_id':'p','text':'We apply tree models [1].','complete':True}]}
    answer={'judgments':[{'rule_id':'word','node_id':'use','status':'VIOLATION',
        'reason':'A different topic.','basis_ids':['project-term'],'basis':'topic_mismatch',
        'quotes':[{'source_id':'paper:p','quote':'We apply tree models'}]}]}
    assert _ground_judgments(answer,{('word','use'):(data,generated,node)},ir)=={}
