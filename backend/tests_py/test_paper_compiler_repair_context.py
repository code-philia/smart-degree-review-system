"""Feedback-only projections of real analysis shapes; no checker/model/network."""
import copy,json
import pytest
from paper_compiler.analysis import base_analysis,bind_references,ordering_facts
from paper_compiler.contracts import ir_hash
from test_paper_compiler_program_analysis import paper


def api():
    from paper_compiler.repair_context import attach_feedback_context,project_feedback_context
    return attach_feedback_context,project_feedback_context


def context(tmp_path):
    ir=paper(tmp_path)
    ir['nodes'].extend([
        {'id':'other-entry','kind':'BibliographyEntry','text':'Other work','children':[],'attrs':{'key':'2'},'provenance':[]},
        {'id':'other-use','kind':'ReferenceUse','text':'[2]','children':[],'attrs':{'namespace':'bibliography','expected_kind':'BibliographyEntry','selector':{'kind':'numeric','value':'2'}},'provenance':[]}])
    ir['nodes'][0]['children'].extend(['other-entry','other-use'])
    ir['coverage']={'reference_uses':{'status':'partial','reason':'some citations unobserved'},
                    'bibliography':{'status':'partial'},'other-use':{'status':'complete'}}
    a=base_analysis(ir);bind_references(ir,a);ordering_facts(ir,a)
    a['results']['external_work']={
        'entry':{'exists':{'state':'observed','value':True,'reason':'identified joint source identity','evidence_ids':['identity-1']}},
        'other-entry':{'exists':{'state':'unknown','reason':'UNRELATED IDENTITY'}}}
    a['results']['semantic_use']={
        'use':{'related':{'state':'unknown','reason':'full text has insufficient scope','evidence_ids':['body-1']}},
        'other-use':{'related':{'state':'unknown','reason':'UNRELATED SEMANTIC'}}}
    a['capability_versions']['semantic_use']='semantic-v1'
    a['node_attributes']={'entry':{'resource_type':{'state':'observed','value':'journal','evidence_ids':['identity-1']}},
                          'other-entry':{'resource_type':{'state':'unknown','reason':'UNRELATED ATTRIBUTE'}}}
    a['coverage']={'entry':{'status':'partial','protocol':'bibliography-fields/1.1'},
                   'use':{'status':'partial','reason':'context partial'},'other-entry':{'status':'complete'},
                   'global':{'status':'partial','reason':'global analysis partial'}}
    a['evidence']=[{'id':'identity-1','kind':'identity','source_evidence_ids':['retrieval-1']},
                   {'id':'retrieval-1','kind':'retrieval','work_id':'work-1','quote':'verified identity'},
                   {'id':'body-1','kind':'source_span','node_id':'p','quote':'We apply tree models','content_id':'content-1'},
                   {'id':'content-1','status':'ok','coverage':'full_text','text':'Actual cited content','source_evidence_ids':['retrieval-1']},
                   {'id':'unrelated-evidence','quote':'UNRELATED EVIDENCE'}]
    a['entities']=[{'id':'work-1','kind':'ExternalWork','title':'Identified work','evidence_ids':['identity-1']},
                   {'id':'work-2','kind':'ExternalWork','title':'UNRELATED WORK'},
                   {'id':'intent-1','kind':'CitationIntent','use_id':'use','evidence_ids':['body-1']},
                   {'id':'obs-other','kind':'SemanticObservation','capability':'semantic_use','target_node_id':'other-use','value':'UNRELATED OBSERVATION'}]
    a['edges']=[{'type':'identifies','from':'entry','to':'work-1','evidence_ids':['identity-1']},
                {'type':'identifies','from':'other-entry','to':'work-2','evidence_ids':['unrelated-evidence']},
                {'type':'uses','from':'use','to':'intent-1','evidence_ids':['body-1']},
                {'type':'supports','from':'work-1','to':'obs-other','evidence_ids':['unrelated-evidence']}]
    report={'schema_version':'paper-check/1.0','paper_ir_sha256':ir_hash(ir),'rules':[{'rule_id':'generic','status':'UNKNOWN'}]}
    return report,ir,a


def test_attach_is_shallow_and_retains_references_without_copying_layout(tmp_path,monkeypatch):
    attach,project=api();report,ir,a=context(tmp_path)
    def forbidden(*args,**kwargs):raise AssertionError('attach must not deepcopy')
    monkeypatch.setattr(copy,'deepcopy',forbidden)
    attached=attach(report,ir,a)
    assert attached is not report and attached['rules'] is report['rules']
    assert '_feedback_context' not in report
    assert attached['_feedback_context']['analysis'] is a
    assert attached['_feedback_context']['ir'] is ir
    assert attached['_feedback_context']['paper_ir_sha256']==a['paper_ir_sha256']


def test_reference_projection_preserves_unknown_reason_partial_coverage_and_binding_identity(tmp_path):
    attach,project=api();report,ir,a=context(tmp_path)
    result=project(attach(report,ir,a),['use'])
    assert result['results']['citation_order']['use']['first_appearance_rank']=={
        'state':'unknown','reason':'incomplete citation extraction prevents ordinal judgment'}
    assert result['results']['external_work']['entry']==a['results']['external_work']['entry']
    assert result['results']['semantic_use']['use']==a['results']['semantic_use']['use']
    assert result['coverage']['entry']==a['coverage']['entry']
    assert result['coverage']['global']==a['coverage']['global']
    assert result['ir_coverage']['reference_uses']==ir['coverage']['reference_uses']
    assert result['model_version']==a['model_version'] and result['paper_ir_sha256']==a['paper_ir_sha256']
    assert result['capability_versions']['citation_order']==a['capability_versions']['citation_order']
    assert {n['id'] for n in result['nodes']}=={'use','entry'}
    assert result['node_attributes']=={'entry':a['node_attributes']['entry']}
    assert result['bindings']==[a['bindings'][0]]
    assert {e['id'] for e in result['evidence']}=={'identity-1','retrieval-1','body-1','content-1'}
    assert {e['id'] for e in result['entities']}=={'work-1','intent-1'}
    assert len(result['edges'])==2
    assert 'UNRELATED' not in json.dumps(result) and 'rules' not in result and 'layout' not in result


def test_target_subtree_and_explicit_capability_filter(tmp_path):
    attach,project=api();report,ir,a=context(tmp_path)
    result=project(attach(report,ir,a),['p'],requires=['citation_order'])
    assert {n['id'] for n in result['nodes']}=={'p','use','entry'}
    assert set(result['results'])=={'citation_order'}
    assert set(result['results']['citation_order'])=={'use'}
    assert set(result['capability_versions'])=={'citation_order'}
    assert 'other-use' not in result['ir_coverage']


def test_projection_is_independent_and_inputs_and_rules_are_unchanged(tmp_path):
    attach,project=api();report,ir,a=context(tmp_path)
    before=copy.deepcopy((report,ir,a));attached=attach(report,ir,a)
    result=project(attached,['use'])
    result['results']['external_work']['entry']['exists']['reason']='modified'
    result['nodes'][0]['attrs']['changed']=True
    result['evidence'][0]['changed']=True
    assert (report,ir,a)==before
    assert attached['rules'] is report['rules']


def test_absent_context_returns_none_and_empty_targets_do_not_broaden(tmp_path):
    attach,project=api();report,ir,a=context(tmp_path)
    assert project(report,['use']) is None
    result=project(attach(report,ir,a),[])
    assert result['results']=={} and result['nodes']==[] and result['bindings']==[] and result['evidence']==[]


def test_ambiguous_binding_does_not_disclose_candidate_bibliography_facts(tmp_path):
    attach,project=api();report,ir,a=context(tmp_path)
    a['bindings'][0]={'use_id':'use','status':'ambiguous','target_ids':['entry','other-entry']}
    result=project(attach(report,ir,a),['use'])
    assert {n['id'] for n in result['nodes']}=={'use'}
    assert 'external_work' not in result['results']
    assert result['bindings'][0]['status']=='ambiguous'


def test_projection_cannot_transport_oracle_shaped_values(tmp_path):
    attach,project=api();report,ir,a=context(tmp_path)
    a['results']['semantic_use']['use']['related']['value']={'oracle':'forbidden answer'}
    with pytest.raises(ValueError,match='leakage'):project(attach(report,ir,a),['use'])


def test_attach_rejects_hash_or_model_binding_mismatch(tmp_path):
    attach,project=api();report,ir,a=context(tmp_path)
    report['paper_ir_sha256']='wrong'
    with pytest.raises(ValueError,match='hash'):attach(report,ir,a)
    report['paper_ir_sha256']=a['paper_ir_sha256'];a['model_version']='wrong'
    with pytest.raises(ValueError,match='model'):attach(report,ir,a)


def test_confirmed_absence_and_all_native_fact_fields_are_retained(tmp_path):
    attach,project=api();report,ir,a=context(tmp_path)
    fact={'state':'confirmed_absent','search_scope':['entry'],'evidence_ids':['identity-1'],
          'reason':'confirmed only inside complete local entry','complete':True,'source_range':[0,12]}
    a['results']['bibliography_fields']={'entry':{'doi':fact}}
    result=project(attach(report,ir,a),['use'],requires=['bibliography_fields'])
    assert result['results']=={'bibliography_fields':{'entry':{'doi':fact}}}
    assert result['results']['bibliography_fields']['entry']['doi'] is not fact
    assert {e['id'] for e in result['evidence']}=={'identity-1','retrieval-1','body-1','content-1'}


def test_cached_report_without_private_references_falls_back_to_none(tmp_path):
    attach,project=api();report,ir,a=context(tmp_path)
    cached=json.loads(json.dumps(report))
    assert project(cached,['use']) is None


def test_projection_rejects_changed_model_binding_without_running_checker(tmp_path):
    attach,project=api();report,ir,a=context(tmp_path);attached=attach(report,ir,a)
    ir['model_version']='changed'
    with pytest.raises(ValueError,match='model'):project(attached,['use'])
