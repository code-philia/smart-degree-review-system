import copy
import json
from pathlib import Path
import pytest

from test_paper_compiler_contracts import paper, analysis
from paper_compiler.compiler import compile_rule, validate_rule_ir, generate_code, CompilationError
from paper_compiler.expressions import interpret_rule, run_generated

REGISTRY={'version':'registry/1','capabilities':{
    'bibliography_fields':{'version':'1','targets':['BibliographyEntry'],'fields':{'title':'string','year':'number'}}}}


def fixture(tmp_path):
    ir=paper(tmp_path)
    ir['nodes'][0]['children'].append('entry')
    ir['nodes'].append({'id':'entry','kind':'BibliographyEntry','text':'Hello','children':[],
        'attrs':{'key':'1'},'provenance':[{'kind':'source','source_id':'src','char_start':0,'char_end':5}]})
    a=analysis(ir)
    a['evidence']=[{'id':'e1','kind':'source','node_id':'entry'}]
    a['results']={'bibliography_fields':{'entry':{'title':{'state':'observed','value':'Hello','evidence_ids':['e1']},
        'year':{'state':'confirmed_absent','search_scope':'entry','evidence_ids':['e1']}}}}
    return ir,a


def spec(field='title'):
    return {'rule_id':'test','title':'Required bibliography field','requires':['bibliography_fields'],
        'checks':[{'id':'field-required','target_kind':'BibliographyEntry','when':{'op':'literal','value':True},
            'assert':{'op':'present','args':[{'op':'field','path':'facts.bibliography_fields.'+field}]},
            'basis':['test-project-requirement'],'message':'Required field is missing'}],
        'on_missing':'UNKNOWN'}


def rule(field='title'):
    return {'schema_version':'rule-ir/1.0',**spec(field),'registry_version':'registry/1'}


class RuleModel:
    def complete_json(self,task,instructions,data,max_tokens):
        return spec('year' if 'year' in data['rule_text'] else 'title')


def test_natural_language_variation_changes_generated_behavior(tmp_path):
    ir,a=fixture(tmp_path)
    first=compile_rule('Require title',[],REGISTRY,RuleModel(),tmp_path/'title')
    second=compile_rule('Require year',[],REGISTRY,RuleModel(),tmp_path/'year')
    assert interpret_rule(first['rule_ir'],ir,a)[0]['status']=='PASS'
    assert interpret_rule(second['rule_ir'],ir,a)[0]['status']=='VIOLATION'
    assert first['manifest']['rule_text_sha256']!=second['manifest']['rule_text_sha256']
    assert (tmp_path/'title'/'checks.py').is_file()
    assert json.loads((tmp_path/'title'/'rulespec.json').read_text())['requires']==['bibliography_fields']


@pytest.mark.parametrize('change',[
    lambda r:r['checks'][0]['assert'].update(op='eval'),
    lambda r:r['checks'][0]['assert']['args'][0].update(path='facts.bibliography_fields.typo'),
    lambda r:r['checks'][0].update(target_kind='CitationUse'),
    lambda r:r.update(on_missing='PASS'),
    lambda r:r['checks'][0].update(when={'op':'literal','value':'truthy-string'}),
    lambda r:r['checks'][0]['assert'].update(op='matches',args=[{'op':'literal','value':123},{'op':'literal','value':'x'}]),
    lambda r:r['checks'][0]['assert'].update(op='field',path='node.__class__'),
])
def test_compiler_rejects_type_errors_unknown_fields_and_unsafe_operations(change):
    r=rule();change(r)
    with pytest.raises(CompilationError):validate_rule_ir(r,REGISTRY)


def test_unknown_is_not_a_violation_and_confirmed_absence_is(tmp_path):
    ir,a=fixture(tmp_path)
    a['results']['bibliography_fields']['entry']['title']={'state':'unknown','reason':'OCR unreadable'}
    assert interpret_rule(rule(),ir,a)[0]['status']=='UNKNOWN'
    assert interpret_rule(rule('year'),ir,a)[0]['status']=='VIOLATION'


def test_generated_backend_matches_interpreter_for_nested_boolean_rules(tmp_path):
    ir,a=fixture(tmp_path)
    r=rule()
    r['checks'][0]['assert']={'op':'all','args':[
        {'op':'matches','args':[{'op':'field','path':'node.text'},{'op':'literal','value':'^Hello$'}]},
        {'op':'any','args':[{'op':'present','args':[{'op':'field','path':'facts.bibliography_fields.title'}]},
                           {'op':'present','args':[{'op':'field','path':'facts.bibliography_fields.year'}]}]}]}
    validate_rule_ir(r,REGISTRY)
    assert run_generated(generate_code(r),ir,a)==interpret_rule(r,ir,a)
    assert run_generated(generate_code(r),ir,a)[0]['status']=='PASS'
    a['results']['bibliography_fields']['entry']['title']={'state':'unknown','reason':'missing extraction'}
    assert run_generated(generate_code(r),ir,a)==interpret_rule(r,ir,a)
    assert run_generated(generate_code(r),ir,a)[0]['status']=='UNKNOWN'


def test_literal_code_in_rule_message_is_encoded_not_executed(tmp_path):
    ir,a=fixture(tmp_path)
    r=rule('year');r['checks'][0]['message']="'); __import__('os').system('touch /tmp/pwned'); #"
    outputs=run_generated(generate_code(r),ir,a)
    assert outputs[0]['message']==r['checks'][0]['message']
    assert outputs[0]['status']=='VIOLATION'


def test_absent_targets_with_incomplete_coverage_are_unknown(tmp_path):
    ir=paper(tmp_path);a=analysis(ir)
    assert interpret_rule(rule(),ir,a)[0]['status']=='UNKNOWN'


def test_stale_analysis_cannot_be_checked(tmp_path):
    ir,a=fixture(tmp_path)
    ir['nodes'][1]['text']='Changed'
    with pytest.raises(ValueError,match='stale'):interpret_rule(rule(),ir,a)


def test_missing_capability_cannot_be_replaced_with_pass(tmp_path):
    with pytest.raises(CompilationError,match='capability'):
        compile_rule('Require title',[],{'version':'empty','capabilities':{}},RuleModel(),tmp_path/'out')


def test_compilation_dispatches_missing_capability_to_validated_builder(tmp_path):
    from test_paper_compiler_capabilities import REQUEST
    class PipelineModel:
        def complete_json(self,task,instructions,data,max_tokens):
            if task.startswith('capability-builder'):
                return {'name':'word_count','targets':['Paragraph'],'fields':{'word_count':'number'},
                    'code':"def analyze(payload):\n    return {'word_count': len(payload['node']['text'].split())}\n"}
            return {'rule_id':'new','title':'Paragraph length','requires':['word_count'],'on_missing':'UNKNOWN',
                'checks':[{'id':'enough-words','target_kind':'Paragraph','when':{'op':'literal','value':True},
                    'assert':{'op':'gt','args':[{'op':'field','path':'facts.word_count.word_count'},{'op':'literal','value':1}]},
                    'basis':['project'],'message':'Too few words'}]}
    compiled=compile_rule('Paragraph must contain more than one word',[],{'version':'empty','capabilities':{}},
        PipelineModel(),tmp_path/'package',capability_requests=[REQUEST])
    assert 'word_count' in compiled['manifest']['capability_versions']
    assert (tmp_path/'package'/'capabilities'/'registry.json').is_file()


def test_compiler_rejects_inverted_predicate_and_retries_with_independent_cases(tmp_path):
    ir,a=fixture(tmp_path)
    class InvertedThenCorrect:
        calls=0
        def complete_json(self,task,instructions,data,max_tokens):
            assert 'validation_cases' not in data
            self.calls+=1
            candidate=spec()
            if self.calls==1:candidate['checks'][0]['assert']={'op':'not','args':[candidate['checks'][0]['assert']]}
            return candidate
    model=InvertedThenCorrect()
    p=compile_rule('Require title',[],REGISTRY,model,tmp_path/'out',validation_cases=[{'id':'title-present','ir':ir,'analysis':a,'status':'PASS'}])
    assert model.calls==2 and p['manifest']['validation']['passed']==1
    assert (tmp_path/'out/compile-attempt-1.json').is_file()


def test_compiler_rule_identifier_is_preserved(tmp_path):
    with pytest.raises(CompilationError,match='rule_id'):
        compile_rule('Require title',[],REGISTRY,RuleModel(),tmp_path/'out',expected_rule_id='31')


def test_code_generation_is_stable_across_json_key_order():
    r=rule();assert generate_code(r)==generate_code(json.loads(json.dumps(r,sort_keys=True)))


def test_partitioned_compilation_merges_real_candidates_and_checks_final_semantics(tmp_path):
    from paper_compiler.compiler import compile_partitioned_rule
    from paper_compiler.runtime import load_package
    ir,a=fixture(tmp_path)
    class Parts:
        def complete_json(self,task,instructions,data,max_tokens):
            return spec(data['basis'][0]['id'])
    package=compile_partitioned_rule('Require title and year',[{'id':'title','text':'Require title'},{'id':'year','text':'Require year'}],
        REGISTRY,Parts(),tmp_path/'parts',expected_rule_id='test',validation_cases=[{'id':'missing-year','ir':ir,'analysis':a,'status':'VIOLATION'}])
    assert len(package['rule_ir']['checks'])==2
    assert len({c['id'] for c in package['rule_ir']['checks']})==2
    assert load_package(tmp_path/'parts')['manifest']['validation']['passed']==1
    assert len(package['manifest']['partition_manifests'])==2


def test_partitioned_candidate_not_activated_when_combined_semantics_fail(tmp_path):
    from paper_compiler.compiler import compile_partitioned_rule
    ir,a=fixture(tmp_path)
    with pytest.raises(CompilationError,match='combined'):
        compile_partitioned_rule('Require title',[{'id':'title','text':'Required title'}],REGISTRY,RuleModel(),tmp_path/'parts',
            validation_cases=[{'id':'incorrect','ir':ir,'analysis':a,'status':'VIOLATION'}])
    assert not (tmp_path/'parts/manifest.json').exists()


def test_sequence_order_primitive_preserves_unknown_and_has_typed_arguments(tmp_path):
    from paper_compiler.expressions import apply_op,literal
    r=rule();r['checks'][0]['assert']={'op':'precedes','args':[{'op':'literal','value':['place','publisher','year']},{'op':'literal','value':'publisher'},{'op':'literal','value':'year'}]}
    validate_rule_ir(r,REGISTRY);ir,a=fixture(tmp_path)
    assert run_generated(generate_code(r),ir,a)[0]['status']=='PASS'
    assert apply_op('precedes',[literal(['year']),literal('publisher'),literal('year')]).state=='unknown'


def test_literal_argument_syntax_is_canonicalized_without_guessing_field_paths(tmp_path):
    class LiteralModel:
        def complete_json(self,*args):
            s=spec();s['checks'][0]['assert']={'op':'matches','args':[{'op':'field','path':'node.text'},'Hello']};return s
    p=compile_rule('Require Hello',[],REGISTRY,LiteralModel(),tmp_path/'out')
    ir,a=fixture(tmp_path)
    assert p['rule_ir']['checks'][0]['assert']['args'][1]=={'op':'literal','value':'Hello'}
    assert run_generated(p['code'],ir,a)[0]['status']=='PASS'


def test_observation_wrapped_node_attributes_keep_their_declared_scalar_type(tmp_path):
    r=rule();r['checks'][0]['when']={'op':'equals','args':[{'op':'field','path':'node.attrs.resource_type'},{'op':'literal','value':'journal_article'}]}
    validate_rule_ir(r,REGISTRY)
    ir,a=fixture(tmp_path);entry=next(n for n in ir['nodes'] if n['id']=='entry')
    entry['attrs']['resource_type']={'state':'unknown','reason':'not classified'}
    from paper_compiler.contracts import ir_hash
    a['paper_ir_sha256']=ir_hash(ir)
    assert interpret_rule(r,ir,a)[0]['status']=='UNKNOWN'


def test_compiler_infers_declared_capabilities_from_typed_field_references(tmp_path):
    class Model:
        def complete_json(self,*args):s=spec();s['requires']=[];return s
    result=compile_rule('Require title',[],REGISTRY,Model(),tmp_path/'out')
    assert result['rule_ir']['requires']==['bibliography_fields']
    assert 'bibliography_fields' in result['manifest']['capability_versions']


def test_partition_clause_rejects_false_positive_before_merging(tmp_path):
    from paper_compiler.compiler import compile_partitioned_rule
    ir,a=fixture(tmp_path)
    class Model:
        calls=0
        def complete_json(self,*args):
            self.calls+=1;s=spec()
            if self.calls==1:s['checks'][0]['assert']={'op':'not','args':[s['checks'][0]['assert']]}
            return s
    m=Model();p=compile_partitioned_rule('Require title',[{'id':'title','text':'Title required'}],REGISTRY,m,tmp_path/'out',validation_cases=[{'id':'positive','ir':ir,'analysis':a,'status':'PASS'}])
    assert m.calls==2 and p['manifest']['validation']['passed']==1


def test_group_free_ambiguous_regex_is_bounded_in_runtime(tmp_path):
    import subprocess,sys,os
    code="from paper_compiler.expressions import apply_op,literal; print(apply_op('matches',[literal('a'*60+'!'),literal('a+'*20+'$')]).value)"
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=1,env={**os.environ,'PYTHONPATH':str(Path(__file__).parents[1])})
    assert result.returncode==0 and result.stdout.strip()=='False'

@pytest.mark.parametrize('operation,value',[('equals','J'),('equals','conference_proceedings'),('in',['journal_article','J'])])
def test_resource_type_enum_rejects_codes_or_invented_names(operation,value):
    r=rule()
    r['checks'][0]['when']={'op':operation,'args':[{'op':'field','path':'node.attrs.resource_type'},{'op':'literal','value':value}]}
    with pytest.raises(CompilationError,match='enum'):
        validate_rule_ir(r,REGISTRY)

def test_resource_type_enum_accepts_advertised_values():
    r=rule()
    r['checks'][0]['when']={'op':'equals','args':[{'op':'field','path':'node.attrs.resource_type'},{'op':'literal','value':'journal_article'}]}
    validate_rule_ir(r,REGISTRY)

def test_field_sequence_cannot_be_used_as_a_character_sequence():
    from paper_compiler.registry import REGISTRY as actual_registry
    r=rule();r['registry_version']=actual_registry['version'];r['requires']=['bibliography_shape']
    r['checks'][0]['assert']={'op':'precedes','args':[{'op':'field','path':'facts.bibliography_shape.field_sequence'},{'op':'literal','value':'/'},{'op':'literal','value':'OL'}]}
    with pytest.raises(CompilationError,match='sequence'):
        validate_rule_ir(r,actual_registry)

def test_body_citation_false_positive_is_rejected_by_withheld_controls(tmp_path):
    from paper_compiler.validation import compiler_controls
    from paper_compiler.registry import REGISTRY as actual_registry
    class BadModel:
        def complete_json(self,*args):
            s=spec();s['rule_id']='31';s['requires']=['bibliography_fields','citation_syntax']
            s['checks'].append({'id':'bad-comma-required','target_kind':'CitationGroup','when':{'op':'equals','args':[{'op':'field','path':'facts.citation_syntax.system'},{'op':'literal','value':'numeric'}]},'assert':{'op':'contains','args':[{'op':'field','path':'facts.citation_syntax.separators'},{'op':'literal','value':','}]},'basis':[],'message':'Missing comma'})
            return s
    cases=[c for c in compiler_controls('31') if c['status']=='PASS']
    with pytest.raises(CompilationError,match='independent behavior'):
        compile_rule('Citation format',[],actual_registry,BadModel(),tmp_path/'out',validation_cases=cases,max_attempts=1)

def test_physical_line_wrap_is_equivalent_for_lexical_punctuation():
    from paper_compiler.expressions import apply_op,literal
    for text in ['[1] A title[J/OL]. https://example.org','[1] A title[J/OL].\nhttps://example.org']:
        assert apply_op('matches',[literal(text),literal('.*/[A-Z]{2}.*')]).value is True

def test_field_order_template_must_guard_each_optional_field():
    from paper_compiler.registry import REGISTRY as actual_registry
    r=rule();r['registry_version']=actual_registry['version'];r['requires']=['bibliography_shape','bibliography_fields']
    r['checks'][0]['assert']={'op':'precedes','args':[{'op':'field','path':'facts.bibliography_shape.field_sequence'},{'op':'literal','value':'year'},{'op':'literal','value':'pages'}]}
    with pytest.raises(CompilationError,match='applicability guards'):validate_rule_ir(r,actual_registry)

def test_semantic_failure_names_candidate_checks_without_leaking_test_inputs(tmp_path):
    ir,a=fixture(tmp_path)
    class Retry:
        calls=0
        def complete_json(self,task,instructions,data,max_tokens):
            self.calls+=1
            candidate=spec()
            if self.calls==1:candidate['checks'][0]['assert']={'op':'not','args':[candidate['checks'][0]['assert']]}
            else:
                assert candidate['checks'][0]['id'] in data['previous_failure']
                assert data['previous_candidate']['checks'][0]['assert']['op']=='not'
                assert 'Hello' not in data['previous_failure']
                assert 'ir' not in data and 'analysis' not in data
            return candidate
    model=Retry()
    compile_rule('Require title',[],REGISTRY,model,tmp_path/'out',validation_cases=[{'id':'independent-positive','ir':ir,'analysis':a,'status':'PASS'}])
    assert model.calls==2

def test_regex_parenthesis_characters_inside_character_classes_are_not_groups():
    from paper_compiler.compiler import _pattern
    from paper_compiler.expressions import apply_op,literal
    pattern=r'.*\([^()]*,[^()]*\).*'
    _pattern(pattern)
    assert apply_op('matches',[literal('(Smith, 2020)'),literal(pattern)]).value is True
    assert apply_op('matches',[literal('Smith (2020)'),literal(pattern)]).value is False
    with pytest.raises(CompilationError):_pattern(r'(a+)+')

def test_partitioned_rule_has_separate_bounded_union_limit(tmp_path):
    from paper_compiler.compiler import compile_partitioned_rule
    import copy
    ir,a=fixture(tmp_path)
    class ManyChecks:
        def complete_json(self,*args):
            candidate=spec();original=candidate['checks'][0]
            candidate['checks']=[{**copy.deepcopy(original),'id':'check-'+str(i)} for i in range(100)]
            return candidate
    package=compile_partitioned_rule('Require title',[{'id':'one','text':'Title'},{'id':'two','text':'Also title'}],REGISTRY,ManyChecks(),tmp_path/'out',validation_cases=[{'id':'valid','ir':ir,'analysis':a,'status':'PASS'}])
    assert len(package['rule_ir']['checks'])==200
    oversized=copy.deepcopy(package['rule_ir'])
    oversized['checks']=[{**oversized['checks'][0],'id':str(i)} for i in range(513)]
    with pytest.raises(CompilationError,match='checks'):validate_rule_ir(oversized,REGISTRY)
