"""Behavioral tests for source mutations, sealed labels and resumable construction."""
import copy
import hashlib
import importlib
import json
from pathlib import Path

import pytest

from paper_compiler.budget import BudgetExceeded
from paper_compiler.citations import attach_citations
from paper_compiler.contracts import ir_hash, validate_ir, validate_analysis
from test_paper_compiler_contracts import analysis


RESOURCES = {"sources": [{"id": "evidence-s1", "text": "The method uses gradients."}],
             "controlled_catalog": [{"id": "work-1", "title": "Known source"}],
             "citation_seeds": []}


def builder():
    assert importlib.util.find_spec("paper_compiler.benchmark_builder") is not None, "benchmark builder is not implemented"
    return importlib.import_module("paper_compiler.benchmark_builder")


def parent(tmp_path, index=0):
    folder = tmp_path / ("parent-" + str(index)); folder.mkdir()
    paragraph = "Alpha " + str(index) + " [1]"
    entry = "[1] Source " + str(index) + "[J]. 2020."
    text = paragraph + "\n" + entry
    source = folder / "source.txt"; source.write_text(text)
    ir = {"schema_version": "paper-ir/1.0", "model_version": "paper-model/1.0",
          "document_id": "parent-" + str(index), "revision": "original", "root_id": "root",
          "source_artifacts": [{"id": "src", "kind": "text", "path": str(source),
                                "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}],
          "nodes": [{"id": "root", "kind": "Paper", "text": None, "children": ["p", "entry"], "attrs": {}, "provenance": []},
                    {"id": "p", "kind": "Paragraph", "text": paragraph, "children": [], "attrs": {},
                     "provenance": [{"kind": "source", "source_id": "src", "char_start": 0, "char_end": len(paragraph)}]},
                    {"id": "entry", "kind": "BibliographyEntry", "text": entry, "children": [], "attrs": {"key": "1"},
                     "provenance": [{"kind": "source", "source_id": "src", "char_start": len(paragraph)+1, "char_end": len(text)}]}],
          "profile": {}, "coverage": {"bibliography": {"status": "partial", "reason": "fixture"}},
          "layout": {"pages": []}, "metadata": {}, "extensions": {}}
    attach_citations(ir); validate_ir(ir, folder)
    path = folder / "ir.json"; path.write_text(json.dumps(ir))
    return path


def task(rule_id="generic"):
    return {"rule_id": rule_id, "rule_text": "The citation must serve its stated purpose.",
            "basis": [{"id": "b1", "text": "Use evidence for the stated purpose."}],
            "target_kinds": ["BibliographyEntry"], "generation_guidance": "Cover different edits."}


def proposal(parent_data, replacement, claimed="VIOLATION"):
    node = next(n for n in parent_data["nodes"] if n["id"] == "entry")
    return {"parent_id": parent_data["parent_id"], "node_id": "entry", "start": 0,
            "end": len(node["text"]), "old_text": node["text"], "replacement": replacement,
            "claimed_status": claimed, "target_node_id": "entry", "context_origin": "real",
            "evidence_domain": "controlled_catalog", "source_ids": ["evidence-s1"]}


class ExternalModel:
    """Only replaces the external model; IR, mutation and persistence stay real."""
    def __init__(self, mode="normal"):
        self.mode = mode
        self.requests = []

    def complete_json(self, call_task, instructions, data, max_tokens):
        self.requests.append((call_task, copy.deepcopy(data)))
        if call_task == "benchmark-proposals/2.0":
            proposals = []
            for p in data["parents"]:
                rid = data["task"]["rule_id"]
                proposals.extend([proposal(p, "[1] Wrong " + rid + "[J]. 2020.", "VIOLATION"),
                                  proposal(p, "[1] Proper " + rid + "[J]. 2020.", "PASS")])
            if self.mode == "duplicate": proposals += copy.deepcopy(proposals)
            return {"proposals": proposals}
        assert call_task in {"benchmark-label/2.0", "benchmark-review/2.0"}
        assert "claimed_status" not in json.dumps(data)
        assert "detector" not in data and "prediction" not in data
        if self.mode == "budget" and call_task == "benchmark-review/2.0":
            raise BudgetExceeded("test budget exhausted")
        status = "VIOLATION" if "Wrong" in data["mutated_node"]["text"] else "PASS"
        if self.mode == "conflict" and call_task == "benchmark-review/2.0":
            status = "PASS" if status == "VIOLATION" else "VIOLATION"
        quote = "invented quote" if self.mode == "bad_quote" else "The method uses gradients."
        return {"valid": True, "original_compliant": self.mode != "bad_original", "status": status, "reason": "Source comparison.",
                "quotes": [{"source_id": "evidence-s1", "quote": quote},
                           {"source_id":"original-node","quote":data["original_node"]["text"]},
                           {"source_id":"mutated-node","quote":data["mutated_node"]["text"]}], "basis_ids": ["b1"]}


def run(tmp_path, paths, model=None, tasks=None, negatives=1, controls=1, output="out", batches=1):
    return builder().build_benchmark(tasks or [task()], paths, client=model or ExternalModel(),
        output_dir=tmp_path/output, resources=RESOURCES, negatives_per_rule=negatives,
        controls_per_rule=controls, seed=31, max_proposal_batches=batches)


def test_changes_real_ir_seals_labels_and_does_not_trust_claim(tmp_path):
    path = parent(tmp_path); before = path.read_bytes(); ir = json.loads(before)
    result = run(tmp_path, [path]); manifest = json.loads(Path(result["manifest_path"]).read_text())
    assert manifest["status"] == "complete" and len(manifest["cases"]) == 2
    statuses = set()
    for case in manifest["cases"]:
        changed = json.loads(Path(case["ir_path"]).read_text()); validate_ir(changed, path.parent)
        sealed = json.loads(Path(case["oracle_path"]).read_text()); statuses.add(sealed["status"])
        assert ir_hash(changed) != ir_hash(ir)
        assert next(n for n in changed["nodes"] if n["id"] == "entry")["provenance"][0]["kind"] == "synthetic"
        assert "claimed_status" not in json.dumps(changed) and "VIOLATION" not in json.dumps(changed)
        with pytest.raises(ValueError, match="stale"): validate_analysis(changed, analysis(ir))
        assert sealed["valid"] is True and sealed["label"]["status"] == sealed["review"]["status"]
    assert statuses == {"VIOLATION", "PASS"} and path.read_bytes() == before
    assert hashlib.sha256(Path(result["manifest_path"]).read_bytes()).hexdigest() == result["frozen_manifest_sha256"]
    assert manifest["label_provenance"]["type"] == "model_assisted"


@pytest.mark.parametrize("mode,reason", [("conflict", "disagree"), ("bad_quote", "quote")])
def test_rejects_conflicting_or_unlocatable_labels(tmp_path, mode, reason):
    result = run(tmp_path, [parent(tmp_path)], ExternalModel(mode))
    manifest = json.loads(Path(result["manifest_path"]).read_text())
    assert manifest["status"] == "incomplete" and manifest["cases"] == []
    assert manifest["summary"]["generic"]["violations"] == 0
    rejected = json.loads((tmp_path/"out"/"rejections.json").read_text())
    assert any(reason in r["reason"] for r in rejected)


def test_same_source_edit_is_counted_only_once(tmp_path):
    result = run(tmp_path, [parent(tmp_path)], ExternalModel("duplicate"), negatives=2)
    manifest = json.loads(Path(result["manifest_path"]).read_text())
    assert manifest["status"] == "incomplete" and len(manifest["cases"]) == 2
    assert manifest["summary"]["generic"]["violations"] == 1
    assert manifest["summary"]["generic"]["missing_violations"] == 1


def test_shared_group_split_is_fixed_across_rules_and_input_order(tmp_path):
    paths = [parent(tmp_path, i) for i in range(10)]
    first = run(tmp_path, paths, tasks=[task("a"), task("b")], negatives=10, controls=10)
    second = run(tmp_path, list(reversed(paths)), tasks=[task("a"), task("b")], negatives=10, controls=10, output="other")
    m1=json.loads(Path(first["manifest_path"]).read_text()); m2=json.loads(Path(second["manifest_path"]).read_text())
    assert m1["groups"] == m2["groups"]
    group_splits = {}
    for case in m1["cases"]: group_splits.setdefault(case["parent_group"], set()).add(case["split"])
    assert len(group_splits) == 10 and all(len(s) == 1 for s in group_splits.values())
    assert {s:sum(v == {s} for v in group_splits.values()) for s in ["feedback","validation","test"]} == {"feedback":6,"validation":2,"test":2}
    assert len(m1["cases"]) == 40


def test_budget_stop_resumes_saved_label_without_requesting_it_again(tmp_path):
    path = parent(tmp_path)
    partial = run(tmp_path, [path], ExternalModel("budget"))
    manifest = json.loads(Path(partial["manifest_path"]).read_text())
    assert manifest["status"] == "incomplete" and manifest["stop_reason"] == "budget_exhausted"
    model = ExternalModel(); result = run(tmp_path, [path], model)
    assert json.loads(Path(result["manifest_path"]).read_text())["status"] == "complete"
    assert sum(t == "benchmark-proposals/2.0" for t, _ in model.requests) == 0
    assert sum(t == "benchmark-label/2.0" for t, _ in model.requests) == 1
    assert len(list((tmp_path/"out"/"calls").glob("*.json"))) >= 5


def test_complete_freeze_is_reused_and_changed_inputs_are_rejected(tmp_path):
    path=parent(tmp_path); result=run(tmp_path,[path]); frozen=Path(result["manifest_path"]).read_bytes()
    model=ExternalModel(); again=run(tmp_path,[path],model)
    assert model.requests == [] and Path(again["manifest_path"]).read_bytes() == frozen
    with pytest.raises(ValueError, match="configuration|frozen"):
        run(tmp_path,[path],tasks=[{**task(),"rule_text":"Changed task"}])
    assert Path(result["manifest_path"]).read_bytes() == frozen


def test_constructed_parent_is_valid_synthetic_ir_without_fake_pdf_location(tmp_path):
    path=builder().construct_ir("A gradient optimizer is used [1].", ["[1] Real work[J]. 2020."],
        output_dir=tmp_path/"constructed", source_id="real-work-1")
    ir=json.loads(Path(path).read_text()); validate_ir(ir,Path(path).parent)
    assert ir["metadata"]["context_origin"] == "constructed"
    assert all(s["kind"] == "text" for s in ir["source_artifacts"])
    assert all(p["kind"] == "synthetic" and "bbox" not in p and "page_index" not in p
               for n in ir["nodes"] for p in n["provenance"])
    assert any(n["kind"] == "ReferenceUse" for n in ir["nodes"])



def test_unverified_original_does_not_count_as_a_valid_mutant(tmp_path):
    result = run(tmp_path, [parent(tmp_path)], ExternalModel("bad_original"))
    manifest = json.loads(Path(result["manifest_path"]).read_text())
    assert manifest["cases"] == [] and manifest["summary"]["generic"]["missing_controls"] == 1


def test_alternate_ir_ids_of_same_source_stay_grouped_and_edits_deduplicated(tmp_path):
    path=parent(tmp_path); alias=path.parent/"alias.json"
    ir=json.loads(path.read_text()); ir["document_id"]="alias-parent"; alias.write_text(json.dumps(ir))
    result=run(tmp_path,[path,alias],negatives=2,controls=2)
    manifest=json.loads(Path(result["manifest_path"]).read_text())
    assert len(manifest["groups"]) == 1
    assert len(manifest["cases"]) == 2 and manifest["status"] == "incomplete"


def test_mutated_frozen_case_is_rejected_without_new_model_calls(tmp_path):
    path=parent(tmp_path); result=run(tmp_path,[path])
    manifest=json.loads(Path(result["manifest_path"]).read_text()); changed=Path(manifest["cases"][0]["ir_path"])
    payload=json.loads(changed.read_text()); payload["revision"]="tampered"; changed.write_text(json.dumps(payload))
    model=ExternalModel()
    with pytest.raises(ValueError,match="integrity"):
        run(tmp_path,[path],model)
    assert model.requests == []


def test_proposal_cannot_relabel_constructed_context_as_real_pdf(tmp_path):
    path=builder().construct_ir("A method is used [1].",["[1] Source[J]. 2020."],
        output_dir=tmp_path/"constructed",source_id="evidence-s1")
    class WrongOrigin(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            if call_task == "benchmark-proposals/2.0":
                p=data["parents"][0]; node=next(n for n in p["nodes"] if n["kind"]=="BibliographyEntry")
                return {"proposals":[{"parent_id":p["parent_id"],"node_id":node["id"],"start":0,
                    "end":len(node["text"]),"old_text":node["text"],"replacement":"[1] Wrong[J]. 2020.",
                    "claimed_status":"VIOLATION","target_node_id":node["id"],"context_origin":"real",
                    "evidence_domain":"source"}]}
            raise AssertionError("Invalid provenance must be rejected before labeling")
    result=run(tmp_path,[path],WrongOrigin()); manifest=json.loads(Path(result["manifest_path"]).read_text())
    assert manifest["cases"] == []
    assert "context_origin" in json.loads((tmp_path/"out"/"rejections.json").read_text())[0]["reason"]


def test_same_paper_in_source_bundle_cannot_leak_across_parent_groups(tmp_path):
    paths=[parent(tmp_path,i) for i in range(5)]
    # A multi-artifact IR and another parser IR share the same underlying source.
    ir=json.loads(paths[1].read_text()); shared=json.loads(paths[0].read_text())["source_artifacts"][0]
    ir["source_artifacts"].append({**shared,"id":"shared-original"})
    paths[1].write_text(json.dumps(ir))
    result=run(tmp_path,paths,negatives=5,controls=5)
    manifest=json.loads(Path(result["manifest_path"]).read_text())
    groups=[group for group in manifest["groups"].values() if "parent-0" in group["parent_ids"]]
    assert "parent-1" in groups[0]["parent_ids"]



@pytest.mark.parametrize("bad", [{"status": []}, {"quotes":[{"source_id":[],"quote":"x"}]}, {"basis_ids":[{}]}])
def test_malformed_label_is_retained_and_excluded_without_aborting(tmp_path,bad):
    class Malformed(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            result=super().complete_json(call_task,instructions,data,max_tokens)
            if call_task == "benchmark-label/2.0": result.update(copy.deepcopy(bad))
            return result
    result=run(tmp_path,[parent(tmp_path)],Malformed())
    manifest=json.loads(Path(result["manifest_path"]).read_text())
    assert manifest["cases"] == [] and manifest["status"] == "incomplete"
    assert len(list((tmp_path/"out"/"calls").glob("*.json"))) == 5



class ManyEdits(ExternalModel):
    def __init__(self,only_first=False):
        super().__init__(); self.only_first=only_first

    def complete_json(self,call_task,instructions,data,max_tokens):
        if call_task == "benchmark-proposals/2.0":
            proposals=[]
            for p in data["parents"][:1] if self.only_first else data["parents"]:
                for i in range(20): proposals.append(proposal(p,"[1] Wrong variant "+str(i)+"[J]. 2020."))
                for i in range(6): proposals.append(proposal(p,"[1] Proper variant "+str(i)+"[J]. 2020.","PASS"))
            return {"proposals":proposals}
        return super().complete_json(call_task,instructions,data,max_tokens)


def test_default_quotas_enforce_sixty_twenty_twenty_for_each_class(tmp_path):
    paths=[parent(tmp_path,i) for i in range(10)]
    result=run(tmp_path,paths,ManyEdits(),negatives=100,controls=30)
    manifest=json.loads(Path(result["manifest_path"]).read_text())
    assert manifest["status"] == "complete"
    splits=manifest["summary"]["generic"]["splits"]
    assert [splits[s]["violations"] for s in ["feedback","validation","test"]] == [60,20,20]
    assert [splits[s]["controls"] for s in ["feedback","validation","test"]] == [18,6,6]


def test_total_quota_cannot_hide_empty_holdout_sets(tmp_path):
    paths=[parent(tmp_path,i) for i in range(3)]
    result=run(tmp_path,paths,ManyEdits(only_first=True),negatives=5,controls=5)
    manifest=json.loads(Path(result["manifest_path"]).read_text())
    assert manifest["status"] == "incomplete"
    assert manifest["summary"]["generic"]["violations"] < 5
    assert manifest["summary"]["generic"]["controls"] < 5
    assert any(v["missing_violations"] for v in manifest["summary"]["generic"]["split_deficits"].values())



def test_omitted_source_selection_does_not_send_unrelated_full_library_to_labelers(tmp_path):
    class LocalEvidence(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            if call_task == "benchmark-proposals/2.0":
                result=super().complete_json(call_task,instructions,data,max_tokens)
                for p in result["proposals"]:
                    p.pop("source_ids"); p["evidence_domain"]="source_format"
                return result
            assert all(s["id"] != "unrelated" for s in data["sources"])
            assert data["controlled_catalog"] == []
            result=super().complete_json(call_task,instructions,data,max_tokens)
            result["quotes"]=[{"source_id":"original-node","quote":data["original_node"]["text"]},
                              {"source_id":"mutated-node","quote":data["mutated_node"]["text"]}]
            return result
    resources={**RESOURCES,"sources":[*RESOURCES["sources"],{"id":"unrelated","text":"Unrelated long full text."*1000}]}
    result=builder().build_benchmark([task()],[parent(tmp_path)],client=LocalEvidence(),output_dir=tmp_path/"out",
        resources=resources,negatives_per_rule=1,controls_per_rule=1,max_proposal_batches=1)
    assert json.loads(Path(result["manifest_path"]).read_text())["status"] == "complete"



def test_structural_rejections_feed_the_next_proposal_batch(tmp_path):
    class CorrectsNoOp(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            result=super().complete_json(call_task,instructions,data,max_tokens)
            if call_task == "benchmark-proposals/2.0":
                if data["batch"]==0:
                    for p in result["proposals"]: p["replacement"]=p["old_text"]
                else:
                    assert any("change source" in r["reason"] for r in data.get("proposal_feedback",[]))
            return result
    result=run(tmp_path,[parent(tmp_path)],CorrectsNoOp(),batches=2)
    assert json.loads(Path(result["manifest_path"]).read_text())["status"] == "complete"


def test_unique_exact_old_text_resolves_model_character_count_errors(tmp_path):
    class BadOffsets(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            result=super().complete_json(call_task,instructions,data,max_tokens)
            if call_task == "benchmark-proposals/2.0":
                for p in result["proposals"]: p["start"]=999; p["end"]=9999
            return result
    result=run(tmp_path,[parent(tmp_path)],BadOffsets())
    manifest=json.loads(Path(result["manifest_path"]).read_text())
    assert manifest["status"] == "complete" and len(manifest["cases"]) == 2
    for case in manifest["cases"]:
        oracle=json.loads(Path(case["oracle_path"]).read_text())
        assert oracle["source_edit"]["start"] == 0 and oracle["source_edit"]["old_text"].startswith("[1]")
        assert oracle["proposal_span"]["resolved_from_unique_quote"] is True


def test_ambiguous_quote_anchor_with_wrong_offsets_is_excluded(tmp_path):
    class Ambiguous(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            result=super().complete_json(call_task,instructions,data,max_tokens)
            if call_task == "benchmark-proposals/2.0":
                for p in result["proposals"]:p.update(start=999,end=999,old_text="0",replacement="1")
            return result
    # The entry's year 2020 contains two occurrences of the proposed anchor.
    result=run(tmp_path,[parent(tmp_path)],Ambiguous())
    manifest=json.loads(Path(result["manifest_path"]).read_text())
    assert manifest["cases"] == []
    assert any("ambiguous" in r["reason"] for r in json.loads((tmp_path/"out"/"rejections.json").read_text()))



def test_proposal_resources_follow_local_citation_seed_instead_of_whole_library(tmp_path):
    class Scoped(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            if call_task == "benchmark-proposals/2.0":
                assert [s["id"] for s in data["resources"]["sources"]] == ["evidence-s1"]
                assert "evidence_environment" not in data["resources"]
            return super().complete_json(call_task,instructions,data,max_tokens)
    path=parent(tmp_path)
    resources={**RESOURCES,"sources":[*RESOURCES["sources"],{"id":"irrelevant","text":"Large unrelated source"}],
               "citation_seeds":[{"parent_id":"parent-0","edit_node_id":"entry","target_node_id":"entry","source_ids":["evidence-s1"]}],
               "evidence_environment":{"private_runtime_adapter":"not needed for proposals"}}
    result=builder().build_benchmark([task()],[path],client=Scoped(),output_dir=tmp_path/"out",resources=resources,
        negatives_per_rule=1,controls_per_rule=1,max_proposal_batches=1)
    assert json.loads(Path(result["manifest_path"]).read_text())["status"] == "complete"



def test_label_and_review_run_concurrently_in_separate_contexts(tmp_path):
    import threading
    class Concurrent(ExternalModel):
        def __init__(self):
            super().__init__();self.barrier=threading.Barrier(2);self.thread_ids=set()
        def complete_json(self,call_task,instructions,data,max_tokens):
            if call_task != "benchmark-proposals/2.0":
                self.thread_ids.add(threading.get_ident())
                if call_task == "benchmark-label/2.0": data["label_sentinel"]="private label context"
                else: assert "label_sentinel" not in data
                self.barrier.wait(timeout=2)
            return super().complete_json(call_task,instructions,data,max_tokens)
    model=Concurrent(); result=run(tmp_path,[parent(tmp_path)],model)
    assert json.loads(Path(result["manifest_path"]).read_text())["status"] == "complete"
    assert len(model.thread_ids) >= 2


def test_concurrent_budget_stop_preserves_finished_independent_label(tmp_path):
    import threading
    class BudgetAtReview(ExternalModel):
        def __init__(self):super().__init__();self.barrier=threading.Barrier(2)
        def complete_json(self,call_task,instructions,data,max_tokens):
            if call_task != "benchmark-proposals/2.0":
                self.barrier.wait(timeout=2)
                if call_task == "benchmark-review/2.0":raise BudgetExceeded("review exhausted")
            return super().complete_json(call_task,instructions,data,max_tokens)
    path=parent(tmp_path); result=run(tmp_path,[path],BudgetAtReview())
    manifest=json.loads(Path(result["manifest_path"]).read_text())
    assert manifest["status"] == "incomplete" and manifest["cases"] == []
    model=ExternalModel();run(tmp_path,[path],model)
    assert sum(t=="benchmark-label/2.0" for t,_ in model.requests)==1



def test_task_origin_policy_filters_generator_and_rejects_forbidden_parent(tmp_path):
    real=parent(tmp_path); synthetic=builder().construct_ir("A cited method [1].",["[1] Source[J]. 2020."],
        output_dir=tmp_path/"constructed",source_id="evidence-s1")
    ir=json.loads(synthetic.read_text()); entry=next(n for n in ir["nodes"] if n["kind"]=="BibliographyEntry")
    forbidden={"parent_id":ir["document_id"],"node_id":entry["id"],"target_node_id":entry["id"],
               "start":0,"end":len(entry["text"]),"old_text":entry["text"],"replacement":"[1] Wrong[J]. 2020.",
               "claimed_status":"VIOLATION","context_origin":"constructed","evidence_domain":"source_format","source_ids":["evidence-s1"]}
    class OriginPolicy(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            if call_task == "benchmark-proposals/2.0":
                assert all(p["context_origin"]=="real" for p in data["parents"])
                result=super().complete_json(call_task,instructions,data,max_tokens)
                result["proposals"].insert(0,forbidden);return result
            return super().complete_json(call_task,instructions,data,max_tokens)
    result=run(tmp_path,[real,synthetic],OriginPolicy(),tasks=[{**task(),"allowed_context_origins":["real"]}])
    manifest=json.loads(Path(result["manifest_path"]).read_text())
    assert len(manifest["groups"])==2 and all(c["context_origin"]=="real" for c in manifest["cases"])
    assert any("not allowed" in r["reason"] for r in json.loads((tmp_path/"out"/"rejections.json").read_text()))



def test_pre_excluded_smoke_edit_is_not_counted_in_formal_cases(tmp_path):
    path=parent(tmp_path); warm=run(tmp_path,[path],output="smoke")
    manifest=json.loads(Path(warm["manifest_path"]).read_text())
    oracles=[json.loads(Path(c["oracle_path"]).read_text()) for c in manifest["cases"]]
    violation=next(o for o in oracles if o["status"]=="VIOLATION")
    resources={**RESOURCES,"excluded_edits":[{"parent_group":violation["parent_group"],"source_edit":violation["source_edit"],"origin":"smoke"}]}
    result=builder().build_benchmark([task()],[path],client=ExternalModel(),output_dir=tmp_path/"formal",resources=resources,
        negatives_per_rule=1,controls_per_rule=1,max_proposal_batches=1)
    formal=json.loads(Path(result["manifest_path"]).read_text())
    assert formal["status"]=="incomplete" and formal["summary"]["generic"]["violations"]==0
    assert formal["summary"]["generic"]["controls"]==1



def test_data_policy_restricts_edits_to_evidence_linked_candidate_nodes(tmp_path):
    path=parent(tmp_path);original=json.loads(path.read_text());paragraph=next(n for n in original["nodes"] if n["id"]=="p")
    class Restricted(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            if call_task == "benchmark-proposals/2.0":
                assert [n["id"] for n in data["parents"][0]["nodes"]]==["entry"]
                result=super().complete_json(call_task,instructions,data,max_tokens)
                bad=proposal(data["parents"][0],"Wrong source [1]");bad.update(node_id="p",target_node_id="p",old_text=paragraph["text"],end=len(paragraph["text"]))
                result["proposals"].insert(0,bad)
                unseeded_target=proposal(data["parents"][0],"Wrong alternate source")
                unseeded_target["target_node_id"]="p"
                result["proposals"].insert(0,unseeded_target);return result
            return super().complete_json(call_task,instructions,data,max_tokens)
    resources={**RESOURCES,"citation_seeds":[{"parent_id":"parent-0","edit_node_id":"entry","target_node_id":"entry","source_ids":["evidence-s1"]}]}
    policy={**task(),"target_kinds":["BibliographyEntry","Paragraph"],"restrict_to_citation_seeds":True}
    result=builder().build_benchmark([policy],[path],client=Restricted(),output_dir=tmp_path/"out",resources=resources,
        negatives_per_rule=1,controls_per_rule=1,max_proposal_batches=1)
    manifest=json.loads(Path(result["manifest_path"]).read_text())
    assert all(c["target_node_id"]=="entry" for c in manifest["cases"])
    assert sum("candidate" in r["reason"] for r in json.loads((tmp_path/"out"/"rejections.json").read_text()))==2


def test_evidence_policy_always_supplies_original_source(tmp_path):
    path=parent(tmp_path)
    class OriginalEvidence(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            if call_task == "benchmark-proposals/2.0":
                result=super().complete_json(call_task,instructions,data,max_tokens)
                for p in result["proposals"]: p["source_ids"]=["alternate"]
                return result
            assert "evidence-s1" in {s["id"] for s in data["sources"]}
            return super().complete_json(call_task,instructions,data,max_tokens)
    resources={**RESOURCES,"sources":[*RESOURCES["sources"],{"id":"alternate","text":"Another real source."}],
        "citation_seeds":[{"parent_id":"parent-0","edit_node_id":"entry","target_node_id":"entry","source_ids":["evidence-s1"]}]}
    result=builder().build_benchmark([{**task(),"restrict_to_citation_seeds":True}],[path],client=OriginalEvidence(),
        output_dir=tmp_path/"out",resources=resources,negatives_per_rule=1,controls_per_rule=1,max_proposal_batches=1)
    assert result["summary"]["generic"]["violations"]==1


def test_declared_roles_require_both_local_changes_and_basis_not_just_normative_quotes(tmp_path):
    class RoleModel(ExternalModel):
        def __init__(self,local):super().__init__();self.local=local
        def complete_json(self,call_task,instructions,data,max_tokens):
            answer=super().complete_json(call_task,instructions,data,max_tokens)
            if call_task != "benchmark-proposals/2.0":
                answer["quotes"]=[{"source_id":"b1","quote":"Use evidence for the stated purpose."}]
                if self.local:
                    answer["quotes"] += [{"source_id":name,"quote":data[key]["text"]} for name,key in
                        [("original-node","original_node"),("mutated-node","mutated_node")]]
            return answer
    policy={**task(),"required_source_roles":["original_local","mutated_local","basis"],"semantic_requirements":{"min_quote_content_chars":6}}
    path=parent(tmp_path)
    rejected=run(tmp_path,[path],RoleModel(False),tasks=[policy],output="rejected")
    assert rejected["summary"]["generic"]["violations"]==0
    assert any("role" in x["reason"] for x in json.loads((tmp_path/"rejected/rejections.json").read_text()))
    accepted=run(tmp_path,[path],RoleModel(True),tasks=[policy],output="accepted")
    assert accepted["summary"]["generic"]["violations"]==1
    case=json.loads(Path(accepted["manifest_path"]).read_text())["cases"][0]
    oracle=json.loads(Path(case["oracle_path"]).read_text())
    assert oracle["evidence_requirements"]["required"]==policy["required_source_roles"]


def test_local_role_quote_must_cover_actual_edit_and_have_prose_content(tmp_path):
    class UnchangedQuote(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            answer=super().complete_json(call_task,instructions,data,max_tokens)
            if call_task == "benchmark-proposals/2.0":
                for p in answer["proposals"]:p.update(old_text="2020",replacement="2021",start=None,end=None)
            else:
                answer["quotes"]=[{"source_id":"original-node","quote":"Source"},{"source_id":"mutated-node","quote":"Source"}]
            return answer
    policy={**task(),"required_source_roles":["original_local","mutated_local"],"semantic_requirements":{"min_quote_content_chars":3}}
    result=run(tmp_path,[parent(tmp_path)],UnchangedQuote(),tasks=[policy])
    assert result["summary"]["generic"]["controls"]==0
    assert any("role" in x["reason"] for x in json.loads((tmp_path/"out/rejections.json").read_text()))


def test_bound_citation_roles_use_actual_context_and_confirmed_work_and_reject_marker_only(tmp_path):
    path=parent(tmp_path)
    class BoundModel(ExternalModel):
        def __init__(self,marker=False):super().__init__();self.marker=marker
        def complete_json(self,call_task,instructions,data,max_tokens):
            if call_task == "benchmark-proposals/2.0":
                node=next(n for n in data["parents"][0]["nodes"] if n["id"]=="p")
                return {"proposals":[{"parent_id":"parent-0","node_id":"p","old_text":"Alpha","replacement":"Wrong","start":0,"end":5,
                    "target_node_id":"p-citation-0-use-0","claimed_status":"VIOLATION","context_origin":"real","evidence_domain":"open_full_text","source_ids":["evidence-s1"]}]}
            assert data["original_reference_entries"][0]["id"]=="entry"
            assert data["mutated_reference_entries"][0]["id"]=="entry"
            assert data["evidence_requirements"]["sources"]["original_cited_work_content"]==[{"source_id":"evidence-s1"}]
            answer=super().complete_json(call_task,instructions,data,max_tokens)
            answer["quotes"] = [q for q in answer["quotes"] if q["source_id"] not in ["original-node","mutated-node"]]
            answer["quotes"] += [{"source_id":"original-node","quote":"[1]" if self.marker else data["original_node"]["text"]},
                {"source_id":"mutated-node","quote":"[1]" if self.marker else data["mutated_node"]["text"]}]
            return answer
    resources={**RESOURCES,"sources":[{**RESOURCES["sources"][0],"roles":["cited_work_content"]}],"citation_seeds":[{"parent_id":"parent-0","edit_node_id":"p","target_node_id":"p-citation-0-use-0","bibliography_entry":"[1] Source 0[J]. 2020.","source_ids":["evidence-s1"],"work":{"id":"work-1"}}]}
    policy={**task(),"target_kinds":["ReferenceUse"],"required_source_roles":["original_local","mutated_local","original_cited_work_content","mutated_cited_work_content"],
        "semantic_requirements":{"require_bound_citation_context":True,"preserve_reference_bindings":True,"min_quote_content_chars":4}}
    for marker in [False,True]:
        result=builder().build_benchmark([policy],[path],client=BoundModel(marker),output_dir=tmp_path/str(marker),resources=resources,
            negatives_per_rule=1,controls_per_rule=0,max_proposal_batches=1)
        assert result["summary"]["generic"]["violations"]==(0 if marker else 1)


def test_bound_context_policy_rejects_unconfirmed_changed_work_before_model_labeling(tmp_path):
    path=parent(tmp_path)
    class ChangedBinding(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            assert call_task == "benchmark-proposals/2.0"
            node=next(n for n in data["parents"][0]["nodes"] if n["id"]=="p")
            return {"proposals":[{"parent_id":"parent-0","node_id":"p","old_text":"[1]","replacement":"[2]","start":None,"end":None,
                "target_node_id":"p-citation-0-use-0","claimed_status":"VIOLATION","context_origin":"real","evidence_domain":"open_full_text","source_ids":["evidence-s1"]}]}
    policy={**task(),"target_kinds":["ReferenceUse"],"semantic_requirements":{"require_bound_citation_context":True,"preserve_reference_bindings":True}}
    result=run(tmp_path,[path],ChangedBinding(),tasks=[policy])
    assert result["summary"]["generic"]["violations"]==0
    assert any("bind" in x["reason"] for x in json.loads((tmp_path/"out/rejections.json").read_text()))


def test_proposal_excerpts_are_bounded_without_truncating_label_work_evidence(tmp_path):
    text="The method uses gradients."+" Actual cached body detail."*400
    class ExcerptModel(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            if call_task == "benchmark-proposals/2.0":
                assert next(s["text"] for s in data["resources"]["sources"] if s["id"]=="evidence-s1")==text[:40]
            else:
                assert next(s["text"] for s in data["sources"] if s["id"]=="evidence-s1")==text
            return super().complete_json(call_task,instructions,data,max_tokens)
    resources={**RESOURCES,"sources":[{"id":"evidence-s1","text":text}],"citation_seeds":[{"parent_id":"parent-0","edit_node_id":"entry","target_node_id":"entry","source_ids":["evidence-s1"]}]}
    result=builder().build_benchmark([{**task(),"proposal_source_char_limit":40}],[parent(tmp_path)],client=ExcerptModel(),
        output_dir=tmp_path/"out",resources=resources,negatives_per_rule=1,controls_per_rule=1,max_proposal_batches=1)
    assert result["summary"]["generic"]["violations"]==1


def test_preexcluded_edit_is_rejected_before_expensive_ir_mutation(tmp_path,monkeypatch):
    path=parent(tmp_path);warm=run(tmp_path,[path],output="smoke")
    cases=json.loads(Path(warm["manifest_path"]).read_text())["cases"]
    negative=next(json.loads(Path(c["oracle_path"]).read_text()) for c in cases if json.loads(Path(c["oracle_path"]).read_text())["status"]=="VIOLATION")
    resources={**RESOURCES,"excluded_edits":[{"parent_group":negative["parent_group"],"source_edit":negative["source_edit"]}]}
    original=builder().mutate;calls=[]
    def counted(*args,**kwargs):calls.append(1);return original(*args,**kwargs)
    monkeypatch.setattr(builder(),"mutate",counted)
    result=builder().build_benchmark([task()],[path],client=ExternalModel(),output_dir=tmp_path/"formal",resources=resources,
        negatives_per_rule=1,controls_per_rule=1,max_proposal_batches=1)
    assert result["summary"]["generic"]["controls"]==1
    assert len(calls)==1


def test_unconfigured_unfamiliar_task_cannot_accept_norm_only_labels(tmp_path):
    class NormOnly(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            answer=super().complete_json(call_task,instructions,data,max_tokens)
            if call_task != "benchmark-proposals/2.0":answer["quotes"]=[{"source_id":"b1","quote":"Use evidence for the stated purpose."}]
            return answer
    unfamiliar=task("unseen-future-rule")
    assert "required_source_roles" not in unfamiliar and "semantic_requirements" not in unfamiliar
    result=run(tmp_path,[parent(tmp_path)],NormOnly(),tasks=[unfamiliar])
    assert result["summary"]["unseen-future-rule"]["violations"]==0
    assert result["summary"]["unseen-future-rule"]["controls"]==0


def test_completed_legacy_snapshot_is_rechecked_against_baseline_local_evidence(tmp_path):
    path=parent(tmp_path);result=run(tmp_path,[path]);mp=Path(result["manifest_path"]);manifest=json.loads(mp.read_text())
    # A self-consistent historical snapshot, rather than a corrupt artifact.
    for case in manifest["cases"]:
        op=Path(case["oracle_path"]);oracle=json.loads(op.read_text());oracle.pop("evidence_requirements",None)
        for side in ["label","review"]:oracle[side]["quotes"]=[{"source_id":"b1","quote":"Use evidence for the stated purpose."}]
        op.write_text(json.dumps(oracle));manifest["artifact_sha256"][str(op)]=hashlib.sha256(op.read_bytes()).hexdigest()
    mp.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match="evidence|role"):
        run(tmp_path,[path])


def test_full_node_replacement_cannot_quote_only_unchanged_surroundings(tmp_path):
    class WideReplacement(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            answer=super().complete_json(call_task,instructions,data,max_tokens)
            if call_task == "benchmark-proposals/2.0":
                for p in answer["proposals"]:p["replacement"]=p["old_text"].replace("2020","2021")
            else:answer["quotes"]=[{"source_id":"original-node","quote":"Source"},{"source_id":"mutated-node","quote":"Source"}]
            return answer
    result=run(tmp_path,[parent(tmp_path)],WideReplacement())
    assert result["summary"]["generic"]["controls"]==0


def test_generic_resource_sampling_filters_origins_edit_kinds_and_engine_boundaries(tmp_path):
    real=parent(tmp_path);constructed=builder().construct_ir("Constructed method [1].",["[1] A source[J]. 2020."],output_dir=tmp_path/"constructed",source_id="evidence-s1")
    original=json.loads(real.read_text());entry=next(n for n in original["nodes"] if n["id"]=="entry")
    class BodyOnly(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            if call_task == "benchmark-proposals/2.0":
                assert len(data["parents"])==1 and data["parents"][0]["context_origin"]=="real"
                assert [n["id"] for n in data["parents"][0]["nodes"]]==["p"]
                n=data["parents"][0]["nodes"][0]
                good={"parent_id":"parent-0","node_id":"p","old_text":n["text"],"replacement":"Wrong method [1]","start":0,"end":len(n["text"]),"target_node_id":"p","claimed_status":"VIOLATION","context_origin":"real","evidence_domain":"source_format","source_ids":["evidence-s1"]}
                bad={**good,"node_id":"entry","old_text":entry["text"],"replacement":"Wrong source[J]","end":len(entry["text"]),"target_node_id":"entry"}
                return {"proposals":[bad,good]}
            return super().complete_json(call_task,instructions,data,max_tokens)
    resources={**RESOURCES,"candidate_sampling":{"context_origins":["real"],"edit_kinds":["Paragraph"],"require_descendant_kinds":["ReferenceUse"]}}
    result=builder().build_benchmark([{**task(),"target_kinds":["Paragraph","BibliographyEntry"]}],[real,constructed],client=BodyOnly(),output_dir=tmp_path/"out",resources=resources,negatives_per_rule=1,controls_per_rule=0,max_proposal_batches=1)
    assert result["summary"]["generic"]["violations"]==1
    assert any("sampling" in r["reason"] for r in json.loads((tmp_path/"out/rejections.json").read_text()))


def test_generic_sampling_omits_paragraphs_without_requested_citation_descendants(tmp_path):
    cited=parent(tmp_path);plain=builder().construct_ir("A paragraph without any citation.",[],output_dir=tmp_path/"plain",source_id="evidence-s1")
    records=builder()._load_parents([cited,plain]);groups=builder()._groups(records,31)
    for record in records.values():record["split"]=groups[record["group"]]["split"]
    views=builder()._proposal_parents(records,{**task(),"target_kinds":["Paragraph"]},0,{"candidate_sampling":{"edit_kinds":["Paragraph"],"require_descendant_kinds":["ReferenceUse"]}})
    assert all(p["parent_id"]=="parent-0" for p in views)


def test_resume_reuses_strictly_revalidated_case_checkpoint_without_relabeling(tmp_path):
    class StopAfterOne(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            if call_task=="benchmark-review/2.0" and "Proper" in data["mutated_node"]["text"]:raise BudgetExceeded("stopped after first case")
            return super().complete_json(call_task,instructions,data,max_tokens)
    path=parent(tmp_path);first=run(tmp_path,[path],StopAfterOne());manifest=json.loads(Path(first["manifest_path"]).read_text());assert len(manifest["cases"])==1
    op=Path(manifest["cases"][0]["oracle_path"]);before=op.read_bytes()
    # Accepted immutable IR/oracle checkpoints remain usable independently of a
    # missing transient call cache; the two raw judgments must stay unchanged.
    for f in (tmp_path/"out/calls").glob('*.json'):f.unlink()
    class RemainingOnly(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            if call_task!="benchmark-proposals/2.0":assert "Wrong" not in data["mutated_node"]["text"]
            return super().complete_json(call_task,instructions,data,max_tokens)
    result=run(tmp_path,[path],RemainingOnly());assert json.loads(Path(result["manifest_path"]).read_text())["status"]=="complete"
    assert op.read_bytes()==before


def test_invalid_provider_output_consumes_failed_batch_and_resume_does_not_retry_it(tmp_path):
    from paper_compiler.llm import ModelError
    class InvalidFirst(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            if call_task=="benchmark-proposals/2.0" and data["batch"]==0:raise ModelError("model request failed after bounded attempts: invalid_output")
            return super().complete_json(call_task,instructions,data,max_tokens)
    path=parent(tmp_path);first=run(tmp_path,[path],InvalidFirst(),batches=1)
    assert json.loads(Path(first["manifest_path"]).read_text())["status"]=="incomplete"
    assert any("invalid_output" in r["reason"] for r in json.loads((tmp_path/"out/rejections.json").read_text()))
    class NeverRetryFailed(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            if call_task=="benchmark-proposals/2.0":assert data["batch"]==1
            return super().complete_json(call_task,instructions,data,max_tokens)
    result=run(tmp_path,[path],NeverRetryFailed(),batches=2)
    assert json.loads(Path(result["manifest_path"]).read_text())["status"]=="complete"


def test_transport_failure_still_stops_instead_of_silently_skipping_batches(tmp_path):
    from paper_compiler.llm import ModelError
    class Transport(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            raise ModelError("model request failed after bounded attempts: transport")
    with pytest.raises(ModelError,match="transport"):run(tmp_path,[parent(tmp_path)],Transport(),batches=2)


def test_blind_oracles_receive_rule_contract_without_mutator_or_expected_status_data(tmp_path):
    class Blind(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            if call_task=="benchmark-proposals/2.0":assert data["task"]["generation_guidance"]=="mutator secret"
            else:
                assert "generation_guidance" not in data["task"] and "expected_status" not in data["task"] and "quota" not in data["task"]
                assert "PASS" in data["label_contract"]["valid"]
            return super().complete_json(call_task,instructions,data,max_tokens)
    policy={**task(),"generation_guidance":"mutator secret","expected_status":"VIOLATION","quota":100}
    result=run(tmp_path,[parent(tmp_path)],Blind(),tasks=[policy]);assert result["summary"]["generic"]["controls"]==1


def test_consistent_pass_label_cannot_reclassify_a_claimed_violation_as_control(tmp_path):
    class Mismatch(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            answer=super().complete_json(call_task,instructions,data,max_tokens)
            if call_task=="benchmark-proposals/2.0":
                for p in answer["proposals"]:p["claimed_status"]="PASS" if "Wrong" in p["replacement"] else "VIOLATION"
            return answer
    result=run(tmp_path,[parent(tmp_path)],Mismatch())
    assert result["summary"]["generic"]["violations"]==0 and result["summary"]["generic"]["controls"]==0
    assert sum("status mismatch" in r["reason"] for r in json.loads((tmp_path/"out/rejections.json").read_text()))==2



def test_prior_api_accepted_candidates_are_blindly_revalidated_without_old_labels(tmp_path):
    path=parent(tmp_path);first=run(tmp_path,[path],output="history")
    old=json.loads(Path(first["manifest_path"]).read_text());raw={Path(c["oracle_path"]):Path(c["oracle_path"]).read_bytes() for c in old["cases"]}
    record=next(f for f in (tmp_path/"history/calls").glob("*.json") if json.loads(f.read_text())["request"]["task"]=="benchmark-proposals/2.0")
    generated=json.loads(record.read_text())["result"]["proposals"]
    resources={**RESOURCES,"revalidation_candidates":[{"proposal":p,"generation_record_path":str(record),"generation_record_sha256":hashlib.sha256(record.read_bytes()).hexdigest(),"proposal_index":i} for i,p in enumerate(generated)]}
    class FreshJudges(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            assert call_task != "benchmark-proposals/2.0"
            assert "revalidation_candidates" not in data and "generation_record_path" not in json.dumps(data)
            assert data["label_contract"]["protocol"]=="benchmark-oracle/2.2"
            return super().complete_json(call_task,instructions,data,max_tokens)
    model=FreshJudges();result=builder().build_benchmark([task()],[path],client=model,output_dir=tmp_path/"fresh",resources=resources,negatives_per_rule=1,controls_per_rule=1,max_proposal_batches=1)
    assert result["summary"]["generic"]["violations"]==1 and result["summary"]["generic"]["controls"]==1
    assert len(model.requests)==4 and all(p.read_bytes()==payload for p,payload in raw.items())
    assert list((tmp_path/"fresh/revalidation-batches").glob("*.json"))


def test_revalidation_candidate_must_exactly_match_its_prior_api_generation_record(tmp_path):
    path=parent(tmp_path);record=tmp_path/"generation.json"
    p=proposal({"parent_id":"parent-0","nodes":[{"id":"entry","text":"[1] Source 0[J]. 2020."}]},"[1] Wrong source[J]. 2020.")
    record.write_text(json.dumps({"request":{"task":"benchmark-proposals/2.0"},"result":{"proposals":[p]}}))
    forged={**p,"replacement":"[1] Wrong invented content[J]. 2020."}
    resources={**RESOURCES,"revalidation_candidates":[{"proposal":forged,"generation_record_path":str(record),"generation_record_sha256":hashlib.sha256(record.read_bytes()).hexdigest(),"proposal_index":0}]}
    with pytest.raises(ValueError,match="generation|provenance"):
        builder().build_benchmark([task()],[path],client=ExternalModel(),output_dir=tmp_path/"out",resources=resources,negatives_per_rule=1,controls_per_rule=0,max_proposal_batches=1)



def test_oracles_receive_complete_catalog_once_when_exact_source_already_contains_it(tmp_path):
    records=builder()._load_parents([parent(tmp_path)]);groups=builder()._groups(records,31)
    for r in records.values():r["split"]=groups[r["group"]]["split"]
    resources=copy.deepcopy(RESOURCES);resources["sources"].append({"id":"full-catalog","text":json.dumps(resources["controlled_catalog"]),"coverage":"complete_controlled_catalog"})
    view=builder()._proposal_parents(records,task(),0,resources)[0]
    p=proposal(view,"[1] Wrong citation[J]. 2020.");p["source_ids"].append("full-catalog")
    data=builder()._candidate(task(),p,records,resources)[5]
    assert data["controlled_catalog"]==[]
    assert json.loads(next(s["text"] for s in data["sources"] if s["id"]=="full-catalog"))==RESOURCES["controlled_catalog"]



def test_rule_basis_projection_excludes_explicit_mutation_admission_without_mutating_inputs():
    from paper_compiler.task_inputs import project_rule_basis
    original={"basis":[{"id":"norm","text":"A cited work must exist."},{"id":"admission","text":"Generate a distinct invented identity.","purpose":"mutation_admission"},"Legacy normative text"]}
    projected=project_rule_basis(original)
    assert projected==[{"id":"norm","text":"A cited work must exist."},"Legacy normative text"]
    projected[0]["text"]="changed"
    assert original["basis"][0]["text"]=="A cited work must exist."
    assert project_rule_basis({"basis":"Legacy rule basis"})=="Legacy rule basis"


def test_rule_basis_projection_rejects_unknown_purposes_instead_of_silently_exposing_them():
    from paper_compiler.task_inputs import project_rule_basis
    with pytest.raises(ValueError,match="purpose"):
        project_rule_basis({"basis":[{"id":"x","text":"secret construction recipe","purpose":"mutator_typo"}]})



def test_blind_oracle_projects_truth_basis_and_applies_exact_status_conditional_admission(tmp_path):
    admission="Violation candidates must change identity. PASS controls retain confirmed identity."
    boundary=admission.index("PASS controls")
    policy={**task(),"basis":task()["basis"]+[{"id":"construction","text":admission,"purpose":"mutation_admission"}]}
    resources=copy.deepcopy(RESOURCES);resources["sources"].append({"id":"construction","text":admission})
    resources["oracle_policy"]={"conditional_admission":[{"basis_id":"construction","status":"VIOLATION","source_span":[0,boundary]},{"basis_id":"construction","status":"PASS","source_span":[boundary,len(admission)]}]}
    class Conditional(ExternalModel):
        def complete_json(self,call_task,instructions,data,max_tokens):
            if call_task=="benchmark-proposals/2.0":assert data["task"]["basis"][-1]["purpose"]=="mutation_admission"
            else:
                assert data["label_contract"]["protocol"]=="benchmark-oracle/2.2"
                assert data["task"]["basis"]==task()["basis"]
                assert not any(source["id"]=="construction" for source in data["sources"])
                conditions=data["admission_policy"]["conditions"]
                assert {condition["status"] for condition in conditions}=={"VIOLATION","PASS"}
                for condition in conditions:
                    a,b=condition["source_span"];assert condition["text"]==admission[a:b]
                assert "actual status" in data["admission_policy"]["precedence"]
            return super().complete_json(call_task,instructions,data,max_tokens)
    result=builder().build_benchmark([policy],[parent(tmp_path)],client=Conditional(),output_dir=tmp_path/"out",resources=resources,negatives_per_rule=1,controls_per_rule=1,max_proposal_batches=1)
    assert result["summary"]["generic"]["controls"]==1


@pytest.mark.parametrize("span,status", [([-1,8],"VIOLATION"),([0,1000],"VIOLATION"),([0,8],"EXPECTED")])
def test_invalid_conditional_admission_provenance_fails_before_paid_calls(tmp_path,span,status):
    policy={**task(),"basis":task()["basis"]+[{"id":"construction","text":"Admission policy text.","purpose":"mutation_admission"}]}
    resources={**RESOURCES,"oracle_policy":{"conditional_admission":[{"basis_id":"construction","status":status,"source_span":span}]}}
    model=ExternalModel()
    with pytest.raises(ValueError,match="admission|span|status"):
        builder().build_benchmark([policy],[parent(tmp_path)],client=model,output_dir=tmp_path/"out",resources=resources,negatives_per_rule=1,controls_per_rule=1,max_proposal_batches=1)
    assert model.requests==[]



def test_oracle_catalog_entry_duplicates_are_projected_to_complete_catalog_source(tmp_path):
    records=builder()._load_parents([parent(tmp_path)]);groups=builder()._groups(records,31)
    for r in records.values():r["split"]=groups[r["group"]]["split"]
    resources=copy.deepcopy(RESOURCES)
    resources["sources"] += [{"id":"full-catalog","text":json.dumps(resources["controlled_catalog"]),"coverage":"complete_controlled_catalog","roles":["controlled_catalog"]},{"id":"individual-record","text":json.dumps(resources["controlled_catalog"][0]),"coverage":"controlled_catalog_entry","roles":[]}]
    view=builder()._proposal_parents(records,task(),0,resources)[0];p=proposal(view,"[1] Wrong citation[J]. 2020.");p["source_ids"] += ["full-catalog","individual-record"]
    data=builder()._candidate(task(),p,records,resources)[5]
    assert not any(source["id"]=="individual-record" for source in data["sources"])
    assert any(source["id"]=="full-catalog" for source in data["sources"])


@pytest.mark.parametrize("filled_class", ["VIOLATION", "PASS"])
@pytest.mark.parametrize("hypothetical_truth", ["VIOLATION", "PASS", "UNKNOWN"])
def test_full_split_class_is_sampling_exclusion_before_any_oracle_and_feedback_is_explicit(
        tmp_path, filled_class, hypothetical_truth):
    class QuotaModel(ExternalModel):
        def __init__(self):
            super().__init__(); self.original_proposals = None; self.following_feedback = None

        def complete_json(self, call_task, instructions, data, max_tokens):
            if call_task == "benchmark-proposals/2.0":
                self.requests.append((call_task, copy.deepcopy(data)))
                if data["batch"]:
                    self.following_feedback = copy.deepcopy(data["proposal_feedback"])
                    return {"proposals": []}
                p = data["parents"][0]
                first_word = "Wrong" if filled_class == "VIOLATION" else "Proper"
                other = "PASS" if filled_class == "VIOLATION" else "VIOLATION"
                other_word = "Proper" if other == "PASS" else "Wrong"
                full = proposal(p, first_word + " fullslot", filled_class)
                full.update(start=None, end=None, old_text="Source 0")
                self.original_proposals = [
                    proposal(p, "[1] " + first_word + " first[J]. 2020.", filled_class),
                    full,
                    proposal(p, "[1] " + other_word + " remaining[J]. 2020.", other),
                ]
                return {"proposals": copy.deepcopy(self.original_proposals)}
            result = super().complete_json(call_task, instructions, data, max_tokens)
            if "fullslot" in data["mutated_node"]["text"]:
                result["status"] = hypothetical_truth
            return result

    model = QuotaModel()
    negatives, controls = (2, 1) if filled_class == "VIOLATION" else (1, 2)
    result = run(tmp_path, [parent(tmp_path)], model, tasks=[task("unfamiliar-928")],
                 negatives=negatives, controls=controls, batches=2)
    judges = [(name, data) for name, data in model.requests if name != "benchmark-proposals/2.0"]
    assert len(judges) == 4
    assert not any("fullslot" in data["mutated_node"]["text"] for _, data in judges)
    assert result["summary"]["unfamiliar-928"]["violations"] == 1
    assert result["summary"]["unfamiliar-928"]["controls"] == 1
    rejected = json.loads((tmp_path/"out/rejections.json").read_text())
    record = next(r for r in rejected if r["reason"] == "quota_full_before_oracle")
    assert record["proposal"] == model.original_proposals[1]
    assert record["proposal"]["start"] is None and record["proposal"]["end"] is None
    assert record["source_edit"] == {"node_id": "entry", "start": 4, "end": 12,
                                       "old_text": "Source 0", "replacement": model.original_proposals[1]["replacement"]}
    assert record["disposition"] == "sampling_exclusion"
    assert record["semantic_judgment_performed"] is False and record["label_generated"] is False
    assert record["sampling_class"] == filled_class
    assert record["quota_current"] == record["quota_target"] == 1
    assert not {"label", "review", "valid", "status", "oracle_path"}.intersection(record)
    feedback = next(r for r in model.following_feedback if r["reason"] == "quota_full_before_oracle")
    assert feedback["proposal"] == model.original_proposals[1]
    assert feedback["semantic_judgment_performed"] is False and feedback["label_generated"] is False
    assert feedback["disposition"] == "sampling_exclusion" and feedback["split"] == record["split"]
    assert "not semantically judged" in feedback["explanation"]
    generated = next(json.loads(path.read_text())["result"]["proposals"]
                     for path in (tmp_path/"out/calls").glob("*.json")
                     if json.loads(path.read_text())["request"]["task"] == "benchmark-proposals/2.0"
                     and json.loads(path.read_text())["request"]["data"]["batch"] == 0)
    assert generated == model.original_proposals
