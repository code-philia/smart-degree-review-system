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
