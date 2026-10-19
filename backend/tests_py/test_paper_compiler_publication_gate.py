"""Publication decisions, never classifier labels. No paid API calls."""
import copy
import importlib
import importlib.util
import json
import pytest
from paper_compiler.budget import BudgetExceeded
from paper_compiler.pipeline import detect
from test_paper_compiler_online_loop import package
from test_paper_compiler_program_analysis import paper

def api():
    assert importlib.util.find_spec("paper_compiler.publication_gate"), "publication gate is missing"
    return importlib.import_module("paper_compiler.publication_gate").audit_positives

class Reviewer:
    config={"MAAS_MODEL":"fake","MAAS_MODEL_VERSION":"v1"}
    def __init__(self, mode="valid"):
        self.mode=mode;self.calls=[]
    def complete_json(self,task,instructions,data,max_tokens):
        self.calls.append((task,copy.deepcopy(data)))
        if self.mode=="budget": raise BudgetExceeded("phase exhausted")
        if self.mode=="error": raise ValueError("provider invalid response")
        assert "predictions" not in data and "report" not in data
        rows=[]
        for target in data["targets"]:
            assert "code" not in target and "expected" not in target and "status" not in target
            source=next(s for s in target["sources"] if s.get("node_id")==target["node_id"])
            norm=target["basis"][0]
            quotes=[{"source_id":source["source_id"],"quote":source["text"]}]
            if self.mode!="no_norm":
                quotes.append({"source_id":norm["id"],"quote":norm["text"] if self.mode!="fake_norm" else "invented standard"})
            if self.mode=="fake_source":quotes[0]["quote"]="not in source"
            rows.append({"rule_id":target["rule_id"],"node_id":target["node_id"],
                "status":"PASS" if self.mode=="disagree" and "review" in task else "VIOLATION",
                "reason":"The source does not meet the quoted obligation.","basis_ids":[norm["id"]],
                "basis":"direct_observation","quotes":quotes})
        return {"judgments":rows}

def fixture(tmp_path,count=1):
    ir=paper(tmp_path);pkg=package()
    if count>1:
        for n in range(count-1):
            node=copy.deepcopy(ir["nodes"][1]);node["id"]="p"+str(n);node["children"]=[]
            ir["nodes"].append(node);ir["nodes"][0]["children"].append(node["id"])
    ir,analysis,report=detect(ir,[pkg],client=None,gateway=None,cache_dir=tmp_path/"detect")
    for row in report["rules"][0]["results"]:row["status"]="VIOLATION"
    return ir,analysis,report,[pkg]

def run(tmp_path,model=None,count=1,**kwargs):
    ir,analysis,report,packages=fixture(tmp_path,count)
    return api()(ir,analysis,report,packages,client=model or Reviewer(),gateway=None,output_dir=tmp_path/"audit",**kwargs)

def test_merges_checks_and_publishes_only_independent_node_claim(tmp_path):
    ir,a,report,packages=fixture(tmp_path)
    report["rules"][0]["results"].append({**report["rules"][0]["results"][0],"check_id":"another"})
    before=copy.deepcopy(report);model=Reviewer()
    out=api()(ir,a,report,packages,client=model,gateway=None,output_dir=tmp_path/"audit")
    assert report==before and len(out["public"]["findings"])==1
    finding=out["public"]["findings"][0]
    assert finding["scope"]=="rule_node" and "check_id" not in finding
    assert out["internal"]["proposed_positive_nodes"]==1
    assert len(model.calls)==2 and model.calls[0][0]!=model.calls[1][0]
    assert out["internal"]["decisions"][0]["original_results"]==report["rules"][0]["results"]

@pytest.mark.parametrize("mode",["no_norm","fake_norm","fake_source","disagree"])
def test_missing_or_disagreeing_evidence_is_no_alert_never_proven_pass(tmp_path,mode):
    out=run(tmp_path,Reviewer(mode))
    assert out["public"]=={"status":"NO_ALERT","findings":[]}
    row=out["internal"]["decisions"][0]
    assert row["publication_status"]=="NO_ALERT" and row["proven_pass"] is False and row["reasons"]

def test_all_positives_beyond_online_sample_limit_and_small_batches(tmp_path):
    model=Reviewer();out=run(tmp_path,model,count=11,batch_size=3)
    assert len(out["public"]["findings"])==11 and out["internal"]["accounted_positive_nodes"]==11
    assert len(model.calls)==8 and max(len(d["targets"]) for _,d in model.calls)<=3

@pytest.mark.parametrize("mode",["error","budget"])
def test_failure_checkpoint_prevents_implicit_paid_retry(tmp_path,mode):
    ir,a,r,p=fixture(tmp_path);client=Reviewer(mode)
    kwargs=dict(client=client,gateway=None,output_dir=tmp_path/"audit")
    first=api()(ir,a,r,p,**kwargs);calls=len(client.calls)
    second=api()(ir,a,r,p,**kwargs)
    assert first==second and len(client.calls)==calls
    assert first["public"]["status"]=="NO_ALERT"
    assert first["internal"]["decisions"][0]["reasons"]
    if mode=="budget":assert calls==1

def test_no_proposed_positives_never_calls_model(tmp_path):
    ir,a,r,p=fixture(tmp_path)
    r["rules"][0]["results"][0]["status"]="UNKNOWN";client=Reviewer()
    out=api()(ir,a,r,p,client=client,gateway=None,output_dir=tmp_path/"audit")
    assert out["public"]=={"status":"NO_ALERT","findings":[]} and not client.calls
    assert out["internal"]["proven_pass"] is False

def test_stale_analysis_is_rejected_before_model(tmp_path):
    ir,a,r,p=fixture(tmp_path);a["coverage"]["new"]={"status":"complete"};model=Reviewer()
    with pytest.raises(ValueError,match="analysis"):
        api()(ir,a,r,p,client=model,gateway=None,output_dir=tmp_path/"audit")
    assert not model.calls

def test_valid_cache_reuse_and_changed_sources_are_bound(tmp_path):
    ir,a,r,p=fixture(tmp_path);client=Reviewer()
    first=api()(ir,a,r,p,client=client,gateway=None,output_dir=tmp_path/"audit")
    second=api()(ir,a,r,p,client=client,gateway=None,output_dir=tmp_path/"audit")
    assert first==second and len(client.calls)==2
    r=copy.deepcopy(r);r["rules"][0]["results"][0]["message"]="different raw diagnostic"
    third=api()(ir,a,r,p,client=client,gateway=None,output_dir=tmp_path/"audit")
    assert third["internal"]["input_sha256"]!=first["internal"]["input_sha256"]

def test_reference_without_external_content_cannot_publish(tmp_path):
    from paper_compiler.programs import build_program
    from paper_compiler.model_runtime import base_model
    ir=paper(tmp_path)
    pkg=build_program({"rule_id":"ref","title":"semantic","requires":[],"target_kinds":["ReferenceUse"],
        "code":"def detect(payload):\n    return [emit(n, 'VIOLATION', 'claim') for n in nodes(payload, 'ReferenceUse')]\n",
        "analysis_requests":[],"model_patch":{}},rule_text="Citation must support its actual purpose.",
        basis=[{"id":"norm","text":"Cited content must support the actual citing assertion."}],model=base_model())
    ir,a,r=detect(ir,[pkg],client=None,gateway=None,cache_dir=tmp_path/"detect")
    out=api()(ir,a,r,[pkg],client=Reviewer(),gateway=None,output_dir=tmp_path/"audit")
    assert out["public"]["status"]=="NO_ALERT"


def test_source_budget_stop_covers_all_remaining_nodes_without_retry(tmp_path,monkeypatch):
    gate=importlib.import_module("paper_compiler.publication_gate")
    attempted=[]
    def exhausted(*args,**kwargs):
        attempted.append(1)
        raise BudgetExceeded("public content budget")
    monkeypatch.setattr(gate,"_packet",exhausted)
    out=run(tmp_path,Reviewer(),count=5,batch_size=2)
    assert len(attempted)==1
    assert out["internal"]["accounted_positive_nodes"]==5
    assert out["internal"]["stop_reason"]
    assert out["public"]["status"]=="NO_ALERT"

def test_interrupted_request_is_not_reissued(tmp_path):
    class Interrupted(Reviewer):
        def complete_json(self,*args,**kwargs):
            self.calls.append(args)
            raise KeyboardInterrupt()
    ir,a,r,p=fixture(tmp_path);client=Interrupted()
    with pytest.raises(KeyboardInterrupt):
        api()(ir,a,r,p,client=client,gateway=None,output_dir=tmp_path/"audit")
    retry=Reviewer()
    out=api()(ir,a,r,p,client=retry,gateway=None,output_dir=tmp_path/"audit")
    assert not retry.calls and out["public"]["status"]=="NO_ALERT"
    assert out["internal"]["stop_reason"]=="previous_review_interrupted_or_uncertain"
