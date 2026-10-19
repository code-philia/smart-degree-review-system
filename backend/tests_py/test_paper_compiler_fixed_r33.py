import copy
import pytest
from test_paper_compiler_program_analysis import paper, Model, Gateway
from paper_compiler.model_runtime import base_model
from paper_compiler.pipeline import detect

def asset():
    from paper_compiler import fixed_r33
    return fixed_r33

class Semantic(Model):
 def __init__(self,relation='supported',basis='explicit_support',reason='The quoted source supports this actual citation use.',bad_quote=False):
  super().__init__();self.relation=relation;self.basis=basis;self.reason=reason;self.bad_quote=bad_quote
 def complete_json(self,task,instructions,data,max_tokens):
  if task=='bibliography-fields/1.1':return super().complete_json(task,instructions,data,max_tokens)
  assert task=='generated-analysis/2.0';self.semantic_calls+=1
  if self.relation=='unknown':return {'fields':{'relation':{'state':'unknown','reason':'The cited text cannot establish this precise claim.'}}}
  paper_source=next(s for s in data['sources'] if s.get('node_id')==data['citation_context']['node_id'])
  external=next(s for s in data['sources'] if s['origin']=='external')
  return {'fields':{'relation':{'state':'observed','value':self.relation,'basis':self.basis,'reason':self.reason,'quotes':[{'source_id':paper_source['source_id'],'quote':paper_source['text']},{'source_id':external['source_id'],'quote':'invented unavailable text' if self.bad_quote else external['text']}]}}}

def execute(tmp_path,model,gateway=None):
 m=asset();ir=paper(tmp_path);before=copy.deepcopy(ir);package=m.build_package(model=base_model())
 materialized,analysis,report=detect(ir,[package],client=model,gateway=gateway or Gateway(text='Tree models do not estimate lake measurements; they classify images.'),cache_dir=tmp_path/'cache')
 assert ir==before
 return report['rules'][0]['results'][0],analysis,package

def test_positive_contradiction_with_both_exact_sources_emits_violation(tmp_path,monkeypatch):
 monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE','1')
 row,a,p=execute(tmp_path,Semantic('contradicted','explicit_scope_contradiction','The citing statement attributes a capability the cited source expressly denies.'))
 assert row['status']=='VIOLATION' and row['node_id']=='use' and len(row['evidence_ids'])>=2
 ev={e['id']:e for e in a['evidence']};assert {ev[i]['origin'] for i in row['evidence_ids']}=={'paper','external'}

def test_grounded_background_or_comparison_support_has_real_pass_path(tmp_path,monkeypatch):
 monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE','1')
 row,_,_=execute(tmp_path,Semantic(reason='The source explicitly supports the background use even though the present application is different.'))
 assert row['status']=='PASS' and row['evidence_ids']

@pytest.mark.parametrize('model',[Semantic('unknown'),Semantic('contradicted','explicit_support'),Semantic('contradicted','explicit_scope_contradiction','Different topic alone suggests irrelevance.'),Semantic('contradicted','explicit_scope_contradiction',bad_quote=True)])
def test_uncertainty_role_mismatch_topic_only_or_bad_quote_never_alarms(tmp_path,monkeypatch,model):
 monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE','1')
 row,_,_=execute(tmp_path,model)
 assert row['status']=='UNKNOWN'

def test_unavailable_cited_content_does_not_call_semantics_or_alarm(tmp_path,monkeypatch):
 monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE','1');model=Semantic()
 row,_,_=execute(tmp_path,model,Gateway(empty=True));assert row['status']=='UNKNOWN' and model.semantic_calls==0

def test_fixed_package_roundtrip_and_prompt_does_not_generate_code(tmp_path):
 from paper_compiler.programs import save_program,load_program
 m=asset();p=m.build_package(model=base_model());save_program(p,tmp_path/'package');q=load_program(tmp_path/'package')
 assert q['manifest']==p['manifest'] and q['program_spec']['target_kinds']==['ReferenceUse']
 assert len(q['program_spec']['analysis_requests'])==1
 req=q['program_spec']['analysis_requests'][0]
 assert req['fields']=={'relation':'string'} and 'contradicted' in req['instructions'] and 'topic' in req['instructions']


def test_builder_uses_callers_shared_model_basis_and_rule_without_mutation():
    m=asset();basis=[{'id':'local-norm','text':'Citations must accurately support their attributed purpose.'}];before=copy.deepcopy(basis);model=base_model()
    p=m.build_r33_package(model=model,basis=basis,rule_text='Caller supplied general citation support rule.')
    assert m.build_package is m.build_r33_package
    assert p['input']['basis']==basis==before and p['model']==model
    assert p['input']['rule_text']=='Caller supplied general citation support rule.'
    assert "['local-norm']" in p['code'] and 'BASIS_IDS' not in p['code']
