"""Fixed R32 semantic cases through the real sandbox/pipeline; no paid calls."""
import importlib
import importlib.util
import pytest
from paper_compiler.pipeline import detect
from paper_compiler.programs import run_program
from test_paper_compiler_program_analysis import paper, Model, Gateway, environment

def package():
    assert importlib.util.find_spec("paper_compiler.fixed_r32"), "fixed R32 asset missing"
    return importlib.import_module("paper_compiler.fixed_r32").build_r32_package()

def checked(tmp_path,env=None,model=None,gateway=None):
    pkg=package()
    ir,a,report=detect(paper(tmp_path),[pkg],client=model or Model(),gateway=gateway,
        cache_dir=tmp_path/"cache",evidence_environment=env)
    return pkg,ir,a,report["rules"][0]["results"][0]

def test_complete_finite_catalog_exclusion_is_scoped_violation(tmp_path):
    pkg,ir,a,row=checked(tmp_path,environment())
    assert row["status"]=="VIOLATION" and row["basis"]
    assert row["evidence_ids"]==a["results"]["external_work"]["entry"]["exists"]["evidence_ids"]
    assert "受控目录" in row["message"]
    assert pkg["program_spec"]["analysis_requests"]==[] and pkg["program_spec"]["model_patch"]=={}

@pytest.mark.parametrize("domain",["catalog","public"])
def test_actual_identity_with_wrong_doi_is_still_real(tmp_path,domain):
    pkg,ir,a,row=checked(tmp_path,environment("Tree Models for Lakes") if domain=="catalog" else None,
                       gateway=Gateway() if domain=="public" else None)
    assert row["status"]=="PASS"

def test_open_retrieval_miss_is_unknown_not_nonexistence(tmp_path):
    class Miss:
        providers=[]
        def lookup(self,query):return []
    pkg,ir,a,row=checked(tmp_path,gateway=Miss())
    assert row["status"]=="UNKNOWN" and row["reasons"]

@pytest.mark.parametrize("variant",["incomplete_catalog","incomplete_identity"])
def test_insufficient_domain_or_identity_never_violation(tmp_path,variant):
    env=environment()
    if variant=="incomplete_catalog":env["complete"]=False
    model=Model(missing_authors=variant=="incomplete_identity")
    assert checked(tmp_path,env,model)[3]["status"]=="UNKNOWN"

@pytest.mark.parametrize("variant",["missing_scope","incomplete_scope","wrong_query","wrong_scope"])
def test_false_fact_without_its_bound_complete_scope_is_unknown(tmp_path,variant):
    pkg,ir,a,row=checked(tmp_path,environment())
    item=a["results"]["external_work"]["entry"]["exists"]
    proof=next(e for e in a["evidence"] if e["id"] in item["evidence_ids"])
    if variant=="missing_scope":item["evidence_ids"]=["entry"]
    if variant=="incomplete_scope":proof["complete"]=False
    if variant=="wrong_query":proof["query"]["title"]="A different work"
    if variant=="wrong_scope":proof["search_scope"]="controlled_catalog:another"
    assert run_program(pkg,ir,a)[0]["status"]=="UNKNOWN"

def test_supplied_basis_and_shared_model_are_used_without_special_case_ids(tmp_path):
    from paper_compiler.model_runtime import base_model
    module=importlib.import_module("paper_compiler.fixed_r32") if importlib.util.find_spec("paper_compiler.fixed_r32") else None
    assert module is not None, "fixed R32 asset missing"
    model=base_model();basis=[{"id":"actual-rule","text":"References must identify existing works in the declared evidence domain."}]
    pkg=module.build_package(model=model,basis=basis,rule_text="Actual task.")
    ir,a,r=detect(paper(tmp_path),[pkg],client=Model(),gateway=None,
                  cache_dir=tmp_path/"cache",evidence_environment=environment())
    assert r["rules"][0]["results"][0]["basis"]==["actual-rule"]
    assert pkg["model"]==model and pkg["input"]["basis"]==basis
