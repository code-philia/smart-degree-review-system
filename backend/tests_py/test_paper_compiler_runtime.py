import copy,hashlib,json
from pathlib import Path
import pytest
from paper_compiler.runtime import check,load_package
from paper_compiler.compiler import compile_rule
from paper_compiler.storage import write_json_atomic
from test_paper_compiler_compiler import fixture,RuleModel,REGISTRY


def package(tmp_path):return compile_rule('Require title',[],REGISTRY,RuleModel(),tmp_path/'pkg')

def test_incomplete_document_coverage_cannot_be_clean(tmp_path):
    ir,a=fixture(tmp_path);p=package(tmp_path);a['capability_versions']={'bibliography_fields':'1'}
    report=check(ir,a,[p])
    assert report['rules'][0]['status']=='UNKNOWN'
    assert report['rules'][0]['results'][0]['status']=='PASS'


def test_a_localized_violation_survives_partial_coverage(tmp_path):
    ir,a=fixture(tmp_path);p=package(tmp_path);a['capability_versions']={'bibliography_fields':'1'}
    a['results']['bibliography_fields']['entry']['title']={'state':'confirmed_absent','search_scope':'entry','evidence_ids':['e1']}
    report=check(ir,a,[p]);assert report['rules'][0]['status']=='VIOLATION'
    assert report['rules'][0]['results'][0]['node_id']=='entry'


def test_wrong_capability_version_and_type_do_not_produce_pass(tmp_path):
    ir,a=fixture(tmp_path);p=package(tmp_path)
    a['capability_versions']={'bibliography_fields':'stale'}
    with pytest.raises(ValueError,match='version'):check(ir,a,[p])


def test_modified_generated_code_is_rejected(tmp_path):
    package(tmp_path);p=tmp_path/'pkg/checks.py';p.write_text(p.read_text()+'# modified\n')
    with pytest.raises(ValueError,match='hash'):load_package(tmp_path/'pkg')


def test_saved_package_has_traceable_inputs_and_round_trips(tmp_path):
    expected=package(tmp_path);actual=load_package(tmp_path/'pkg')
    assert actual['rule_ir']==expected['rule_ir'] and actual['code']==expected['code']


def test_invalid_source_evidence_quote_is_rejected(tmp_path):
    ir,a=fixture(tmp_path);p=package(tmp_path);a['capability_versions']={'bibliography_fields':'1'}
    a['evidence'][0]={'id':'e1','kind':'source_span','node_id':'entry','start':0,'end':5,'quote':'False'}
    with pytest.raises(ValueError,match='quote'):check(ir,a,[p])


def test_wrong_fact_type_is_rejected_before_rule_evaluation(tmp_path):
    ir,a=fixture(tmp_path);p=package(tmp_path);a['capability_versions']={'bibliography_fields':'1'}
    a['results']['bibliography_fields']['entry']['title']['value']=False
    with pytest.raises(ValueError,match='type'):check(ir,a,[p])
