import copy
import hashlib
import importlib
import importlib.util
from pathlib import Path

import pytest

from paper_compiler.contracts import ContractError, ir_hash, validate_analysis
from paper_compiler.model_runtime import base_model
from paper_compiler.registry import REGISTRY
from paper_compiler.runtime import _evidence_check


def api():
    assert importlib.util.find_spec('paper_compiler.program_analysis') is not None, 'generic program analysis is missing'
    return importlib.import_module('paper_compiler.program_analysis').analyze_programs


def paper(tmp_path):
    text = 'We apply tree models [1].\n[1] Smith J. Tree Models for Lakes. 2020. doi:10.1000/wrong\nUnrelated note.'
    source = tmp_path / 'paper.txt'
    source.write_text(text, encoding='utf-8')
    def node(nid,kind,value=None,children=(),attrs=None):
        start=text.find(value) if value else 0
        return {'id':nid,'kind':kind,'text':value,'children':list(children),'attrs':attrs or {},
                'provenance':[{'kind':'source','source_id':'src','char_start':start,'char_end':start+len(value)}] if value else []}
    return {'schema_version':'paper-ir/1.0','model_version':'paper-model/1.0','document_id':'doc','revision':'original',
            'root_id':'root','source_artifacts':[{'id':'src','kind':'text','path':str(source),
            'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}],
            'nodes':[node('root','Paper',children=['p','entry','note']),
                     node('p','Paragraph','We apply tree models [1].',children=['use']),
                     node('use','ReferenceUse','[1]',attrs={'namespace':'bibliography','expected_kind':'BibliographyEntry',
                          'selector':{'kind':'numeric','value':'1'}}),
                     node('entry','BibliographyEntry','[1] Smith J. Tree Models for Lakes. 2020. doi:10.1000/wrong',attrs={'key':'1'}),
                     node('note','Note','Unrelated note.')],
            'coverage':{},'profile':{},'layout':{'pages':[]},'extensions':{}}


def package(target='Paragraph',fields=None,instructions='Extract the supplied source facts.',version='cap-v1'):
    fields=fields or {'method':'string'}
    request={'name':'method_facts','targets':[target],'fields':fields,'instructions':instructions}
    registry=copy.deepcopy(REGISTRY)
    registry['capabilities']['method_facts']={'version':version,'targets':[target],'fields':fields,
                                              'implementation':'grounded_semantic_extraction'}
    return {'program_spec':{'requires':['method_facts'],'analysis_requests':[request]},
            'registry':registry,'model':base_model(),'manifest':{'version_id':'generation-'+version}}


class Model:
    def __init__(self, answer=None, *, missing_authors=False):
        self.answer=answer
        self.missing_authors=missing_authors
        self.config={'MAAS_MODEL':'fake','MAAS_MODEL_VERSION':'v1'}
        self.semantic_calls=0
        self.requests=[]

    def complete_json(self, task, instructions, data, max_tokens):
        self.requests.append((task,instructions,copy.deepcopy(data)))
        if task=='bibliography-fields/1.1':
            fields={'title':{'state':'observed','value':'Tree Models for Lakes','quote':'Tree Models for Lakes'},
                    'year':{'state':'observed','value':'2020','quote':'2020'},
                    'doi':{'state':'observed','value':'10.1000/wrong','quote':'10.1000/wrong'}}
            if not self.missing_authors:
                fields['authors']={'state':'observed','value':['Smith J'],'quote':'Smith J'}
            return {'entries':[{'id':entry['id'],'complete':True,'fields':copy.deepcopy(fields)} for entry in data['entries']]}
        assert task=='generated-analysis/2.0'
        self.semantic_calls+=1
        if callable(self.answer):return self.answer(data)
        if self.answer is not None:return copy.deepcopy(self.answer)
        source=next(s for s in data['sources'] if s['origin']=='paper' and 'We apply' in s['text'])
        return {'fields':{'method':{'state':'observed','value':'tree models',
                                  'quotes':[{'source_id':source['source_id'],'quote':'tree models'}]}}}


class Gateway:
    providers=['fake']
    snapshot_id='evidence-s1'
    def __init__(self, *, empty=False, text='Tree models estimate the lake measurements.'):
        self.empty=empty;self.text=text;self.lookups=0;self.contents=0
    def lookup(self,query):
        self.lookups+=1
        if self.empty:return []
        return [{'id':'record1','status':'ok','provider':'fake','coverage':'partial_index','work':{
            'title':'Tree Models for Lakes','authors':['John Smith'],'year':2020,'doi':'10.1000/correct'}}]
    def content(self,work):
        self.contents+=1
        return [{'id':'content1','status':'ok','level':'full_text','coverage':'full_text','text':self.text}]


def grounded_reference(data,value=True,basis='explicit_support',reason='The quoted source explicitly supports this use.'):
    paper=next(s for s in data['sources'] if s['origin']=='paper' and 'We apply' in s['text'])
    external=next(s for s in data['sources'] if s['origin']=='external')
    return {'fields':{'related':{'state':'observed','value':value,'basis':basis,'reason':reason,
            'quotes':[{'source_id':paper['source_id'],'quote':'We apply tree models'},
                      {'source_id':external['source_id'],'quote':external['text']}]}}}


def run(tmp_path,ir,packages,model=None,gateway=None,**kwargs):
    return api()(ir,packages,client=model,gateway=gateway,cache_dir=tmp_path/'cache',**kwargs)


def test_generated_fact_has_package_version_and_exact_source_evidence(tmp_path):
    ir=paper(tmp_path);before=copy.deepcopy(ir)
    result=run(tmp_path,ir,[package()],Model())
    fact=result['results']['method_facts']['p']['method']
    assert fact['state']=='observed' and fact['value']=='tree models' and fact['evidence_ids']
    evidence={e['id']:e for e in result['evidence']}
    assert evidence[fact['evidence_ids'][0]]['quote']=='tree models'
    assert evidence[fact['evidence_ids'][0]]['node_id']=='p'
    assert result['capability_versions']['method_facts']=='cap-v1'
    assert result['paper_ir_sha256']==ir_hash(ir) and ir==before
    validate_analysis(ir,result);_evidence_check(ir,result)


@pytest.mark.parametrize('item',[
    {'state':'observed','value':'fake','quotes':[{'source_id':'unknown','quote':'tree models'}]},
    {'state':'observed','value':'fake','quotes':[{'source_id':'paper:p','quote':'invented source words'}]},
    {'state':'observed','value':5,'quotes':[{'source_id':'paper:p','quote':'tree models'}]},
    {'state':'observed','value':'fake','quotes':[]},
    {'state':'confirmed_absent','search_scope':'paper:p','reason':'Not mentioned','quotes':[]},
    {'state':'not_applicable','reason':'Not applicable','quotes':[]},
    {'state':'unknown'},
])
def test_unverified_fields_remain_unknown(tmp_path,item):
    result=run(tmp_path,paper(tmp_path),[package()],Model({'fields':{'method':item}}))
    assert result['results']['method_facts']['p']['method']['state']=='unknown'


def test_no_client_never_invents_generated_facts(tmp_path):
    ir=paper(tmp_path)
    result=run(tmp_path,ir,[package()],None)
    assert result['results']['method_facts']['p']['method']['state']=='unknown'
    validate_analysis(ir,result)


def test_reference_request_automatically_gets_bound_work_and_citing_context(tmp_path):
    model=Model(grounded_reference);gateway=Gateway();ir=paper(tmp_path)
    result=run(tmp_path,ir,[package('ReferenceUse',{'related':'boolean'})],model,gateway)
    fact=result['results']['method_facts']['use']['related']
    assert fact['state']=='observed' and fact['value'] is True
    evidence={e['id']:e for e in result['evidence']}
    assert any(evidence[e].get('kind')=='source_span' for e in fact['evidence_ids'])
    assert any(evidence[e].get('origin')=='external' for e in fact['evidence_ids'])
    assert result['bindings'][0]['status']=='resolved'
    request=next(data for task,_,data in model.requests if task=='generated-analysis/2.0')
    assert request['citation_context']['text']=='We apply tree models [1].'
    assert gateway.contents==1
    validate_analysis(ir,result);_evidence_check(ir,result)


@pytest.mark.parametrize('basis,reason',[
    ('missing_detail','Full text does not mention tree models.'),
    ('topic_mismatch','The two papers discuss different domains.'),
    ('explicit_scope_contradiction','Full text never mentions this method.'),
])
def test_missing_detail_or_topic_difference_cannot_prove_a_false_semantic_fact(tmp_path,basis,reason):
    model=Model(lambda data:grounded_reference(data,False,basis,reason))
    result=run(tmp_path,paper(tmp_path),[package('ReferenceUse',{'related':'boolean'})],model,Gateway())
    assert result['results']['method_facts']['use']['related']['state']=='unknown'


def test_positive_source_contradiction_can_support_false_semantic_fact(tmp_path):
    from paper_compiler.conflict_review import TASK
    from paper_compiler_r33_test_fixtures import attributed_paper, attributed_reference
    from test_paper_compiler_conflict_witness import answered_wire
    class ReviewedModel(Model):
        def complete_json(self, task, instructions, data, max_tokens):
            if task == TASK:
                return answered_wire(data)
            return super().complete_json(task, instructions, data, max_tokens)
    model=ReviewedModel(lambda data:attributed_reference(data,False,'explicit_scope_contradiction',
                                            'The quoted source explicitly excludes computational methods.'))
    gateway=Gateway(text='This work exclusively inventories medieval coins and makes no computational contribution.')
    result=run(tmp_path,attributed_paper(tmp_path),[package('ReferenceUse',{'related':'boolean'})],model,gateway)
    fact=result['results']['method_facts']['use']['related']
    assert fact['state']=='observed' and fact['value'] is False


def test_open_search_miss_does_not_prove_nonexistence(tmp_path):
    ir=paper(tmp_path)
    result=run(tmp_path,ir,[package('ReferenceUse',{'related':'boolean'})],Model(),Gateway(empty=True))
    assert result['results']['external_work']['entry']['exists']['state']=='unknown'
    assert result['results']['method_facts']['use']['related']['state']=='unknown'


def environment(title='Another Complete Work'):
    return {'domain':'controlled_catalog','catalog':[{'id':'catalog1','title':title,
            'authors':['John Smith'],'year':2020,'doi':'10.1000/correct',
            'text':'Tree models estimate the lake measurements.'}]}


def test_complete_controlled_catalog_can_prove_nonexistence_with_scope_evidence(tmp_path):
    ir=paper(tmp_path);gateway=Gateway()
    result=run(tmp_path,ir,[package('ReferenceUse',{'related':'boolean'})],Model(),gateway,
               evidence_environment=environment())
    fact=result['results']['external_work']['entry']['exists']
    assert fact['state']=='observed' and fact['value'] is False and fact['evidence_ids']
    evidence={e['id']:e for e in result['evidence']}
    assert any(evidence[e].get('domain')=='controlled_catalog' and evidence[e].get('complete') is True
               for e in fact['evidence_ids'])
    assert fact['search_scope'].startswith('controlled_catalog:')
    assert gateway.lookups==0
    validate_analysis(ir,result)


def test_wrong_doi_does_not_erase_a_catalog_work_with_matching_identity(tmp_path):
    result=run(tmp_path,paper(tmp_path),[package('ReferenceUse',{'related':'boolean'})],
               Model(grounded_reference),Gateway(),evidence_environment=environment('Tree Models for Lakes'))
    fact=result['results']['external_work']['entry']['exists']
    assert fact['state']=='observed' and fact['value'] is True
    assert result['results']['method_facts']['use']['related']['value'] is True


def test_incomplete_identity_cannot_be_excluded_from_catalog(tmp_path):
    result=run(tmp_path,paper(tmp_path),[package('ReferenceUse',{'related':'boolean'})],
               Model(missing_authors=True),None,evidence_environment=environment())
    assert result['results']['external_work']['entry']['exists']['state']=='unknown'


def test_analysis_and_node_cache_reuse_unchanged_facts_across_ir_revisions(tmp_path):
    ir=paper(tmp_path);model=Model();packages=[package()]
    first=run(tmp_path,ir,packages,model)
    second=run(tmp_path,ir,packages,model)
    assert model.semantic_calls==1 and first==second
    changed=copy.deepcopy(ir);changed['revision']='new-variant'
    changed['nodes'][-1]['text']='Changed note.'
    third=run(tmp_path,changed,packages,model)
    assert model.semantic_calls==1
    assert third['paper_ir_sha256']==ir_hash(changed) and third['paper_ir_sha256']!=first['paper_ir_sha256']
    fact=third['results']['method_facts']['p']['method']
    assert fact['state']=='observed' and fact['value']=='tree models'
    validate_analysis(changed,third);_evidence_check(changed,third)


def test_changed_node_text_and_analysis_instructions_invalidate_node_cache(tmp_path):
    ir=paper(tmp_path);model=Model();packages=[package()]
    run(tmp_path,ir,packages,model)
    changed=copy.deepcopy(ir);changed['nodes'][1]['text']='We apply wide models [1].'
    run(tmp_path,changed,packages,model)
    assert model.semantic_calls==2
    changed_packages=[package(instructions='Extract the same source under a revised semantic definition.')]
    run(tmp_path,ir,changed_packages,model)
    assert model.semantic_calls==3


def test_changed_model_version_or_evidence_snapshot_invalidates_analysis_cache(tmp_path):
    ir=paper(tmp_path);model=Model();packages=[package()]
    run(tmp_path,ir,packages,model,snapshot_id='s1')
    model.config['MAAS_MODEL_VERSION']='v2'
    run(tmp_path,ir,packages,model,snapshot_id='s1')
    assert model.semantic_calls==2
    run(tmp_path,ir,packages,model,snapshot_id='s2')
    assert model.semantic_calls==3


def test_unknown_dependency_requires_a_generated_analysis_contract(tmp_path):
    broken=package();broken['program_spec']['analysis_requests']=[]
    with pytest.raises((ContractError,ValueError)):
        run(tmp_path,paper(tmp_path),[broken],Model())


@pytest.mark.parametrize('value,typ,valid', [
    (True,'boolean',True), (1.5,'number',True), (['tree'],'array',True),
    ({'name':'tree'},'object',True), ('tree','string',True),
    (True,'number',False), (float('nan'),'number',False),
    (float('inf'),'number',False), ('tree','array',False),
])
def test_generated_field_types_are_enforced_without_truthy_coercion(tmp_path,value,typ,valid):
    answer={'fields':{'value':{'state':'observed','value':value,
                             'quotes':[{'source_id':'paper:p','quote':'tree models'}]}}}
    result=run(tmp_path,paper(tmp_path),[package(fields={'value':typ})],Model(answer))
    fact=result['results']['method_facts']['p']['value']
    assert fact['state']==('observed' if valid else 'unknown')
    if valid:assert fact['value']==value


def test_confirmed_absence_needs_a_complete_scope_and_its_entire_source_quote(tmp_path):
    ir=paper(tmp_path)
    ir['coverage']['p']={'status':'complete','protocol':'source-text/1.0','evidence_ids':['p']}
    answer={'fields':{'method':{'state':'confirmed_absent','reason':'Field absent from this complete local extraction scope.',
                             'search_scope':['paper:p'],'quotes':[{'source_id':'paper:p','quote':ir['nodes'][1]['text']}]}}}
    result=run(tmp_path,ir,[package()],Model(answer))
    fact=result['results']['method_facts']['p']['method']
    assert fact['state']=='confirmed_absent' and fact['evidence_ids'] and fact['search_scope']==['paper:p']
    validate_analysis(ir,result)


def test_citation_marker_alone_is_not_a_quote_of_the_citation_purpose(tmp_path):
    def answer(data):
        item=grounded_reference(data)
        item['fields']['related']['quotes'][0]={'source_id':'paper:use','quote':'[1]'}
        return item
    result=run(tmp_path,paper(tmp_path),[package('ReferenceUse',{'related':'boolean'})],Model(answer),Gateway())
    assert result['results']['method_facts']['use']['related']['state']=='unknown'


def test_legal_missing_bibliography_text_remains_unknown_instead_of_crashing(tmp_path):
    ir=paper(tmp_path);ir['nodes'][3]['text']=None;ir['nodes'][3]['provenance']=[]
    result=run(tmp_path,ir,[package('ReferenceUse',{'related':'boolean'})],Model(),Gateway())
    assert result['results']['external_work']['entry']['exists']['state']=='unknown'
    assert result['results']['method_facts']['use']['related']['state']=='unknown'
    validate_analysis(ir,result)


def test_legal_missing_citation_marker_text_does_not_become_observed_empty_syntax(tmp_path):
    ir=paper(tmp_path)
    ir['nodes'][0]['children'].append('group')
    ir['nodes'].append({'id':'group','kind':'CitationGroup','text':None,'children':[],'attrs':{},'provenance':[]})
    builtin={'program_spec':{'requires':['citation_syntax'],'analysis_requests':[]},
             'registry':copy.deepcopy(REGISTRY),'model':base_model()}
    result=run(tmp_path,ir,[builtin],Model())
    assert all(fact['state']=='unknown' for fact in result['results']['citation_syntax']['group'].values())


def test_corrupt_node_cache_is_rejected_and_recomputed(tmp_path):
    import json
    ir=paper(tmp_path);model=Model();packages=[package()]
    run(tmp_path,ir,packages,model)
    node_path=next((tmp_path/'cache'/'generated-nodes').glob('*.json'))
    cached=json.loads(node_path.read_text())
    cached['facts']['method']['value']='tampered fact'
    node_path.write_text(json.dumps(cached))
    changed=copy.deepcopy(ir);changed['revision']='new-ir-instance'
    result=run(tmp_path,changed,packages,model)
    assert result['results']['method_facts']['p']['method']['value']=='tree models'
    assert model.semantic_calls==2


def test_changed_actual_external_body_invalidates_node_facts_across_mutants(tmp_path):
    ir=paper(tmp_path);model=Model(grounded_reference);gateway=Gateway()
    packages=[package('ReferenceUse',{'related':'boolean'})]
    run(tmp_path,ir,packages,model,gateway)
    changed=copy.deepcopy(ir);changed['revision']='next-mutant'
    gateway.text='Tree models estimate the lake measurements with a revised procedure.'
    result=run(tmp_path,changed,packages,model,gateway)
    assert model.semantic_calls==2
    fact=result['results']['method_facts']['use']['related']
    evidence={e['id']:e for e in result['evidence']}
    assert any('revised procedure' in evidence[e]['quote'] for e in fact['evidence_ids'])


def test_invalid_package_model_definition_is_rejected(tmp_path):
    broken=package();broken['model']['version']='forged-model-version'
    with pytest.raises(ContractError):
        run(tmp_path,paper(tmp_path),[broken],Model())

@pytest.mark.parametrize('name,typ,value', [('unrelated','boolean',True),('contradiction','boolean',True),('relation','string','unrelated')])
def test_citation_topic_mismatch_is_unknown_regardless_of_field_encoding(name,typ,value):
    from paper_compiler.program_analysis import _ground_fields
    data={'citation_context':{'node_id':'p'},'sources':[
        {'source_id':'paper:p','origin':'paper','node_id':'p','text':'We apply tree models.','complete':True},
        {'source_id':'external:work','origin':'external','content_id':'work','work_id':'identified','text':'An inventory of coins.','complete':True}]}
    raw={'fields':{name:{'state':'observed','value':value,'basis':'topic_mismatch',
        'reason':'The topics differ.','quotes':[{'source_id':s['source_id'],'quote':s['text']} for s in data['sources']]}}}
    facts,evidence=_ground_fields({'fields':{name:typ}},raw,data,True)
    assert facts[name]['state']=='unknown'
    assert not evidence

def test_grounded_citation_observations_materialize_purpose_and_work_evidence_graph(tmp_path):
    ir=paper(tmp_path)
    analysis=run(tmp_path,ir,[package('ReferenceUse',{'related':'boolean'})],
                 Model(grounded_reference),Gateway())
    intent=next(e for e in analysis['entities'] if e['kind']=='CitationIntent')
    assert intent['use_id']=='use' and intent['context']['node_id']=='p'
    assert intent['context']['text']=='We apply tree models [1].'
    fact=next(e for e in analysis['entities'] if e['kind']=='SemanticObservation')
    assert fact['capability']=='method_facts' and fact['field']=='related'
    assert fact['value'] is True and fact['evidence_ids']
    work=next(e for e in analysis['entities'] if e['kind']=='ExternalWork')
    assert any(e['type']=='supports' and e['from']==work['id'] and e['to']==fact['id'] for e in analysis['edges'])
    assert any(e['type']=='describes' and e['from']==fact['id'] and e['to']==intent['id'] for e in analysis['edges'])
    validate_analysis(ir,analysis)

def test_unknown_citation_facts_do_not_create_observed_semantic_graph_edges(tmp_path):
    ir=paper(tmp_path)
    analysis=run(tmp_path,ir,[package('ReferenceUse',{'related':'boolean'})],Model(),Gateway(empty=True))
    assert not any(e['kind']=='SemanticObservation' for e in analysis['entities'])
    assert not any(e['type'] in {'supports','contradicts'} for e in analysis['edges'])
