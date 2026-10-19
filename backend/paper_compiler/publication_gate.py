"""Read-only publication gate. NO_ALERT is not PASS or a benchmark success.

Inject the existing budgeted/pace-limited Guard client; this module never creates
clients, budgets, mutations, detector programs or runtime promotions. Only the
returned public projection is suitable for website output. Internal raw reports,
unresolved decisions and review receipts stay in the private output directory.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from . import online_loop
from .budget import BudgetExceeded
from .contracts import ir_hash, validate_analysis, validate_ir
from .online_loop import _call, _ground_judgments
from .program_analysis import _base_kind, _hash, _target_data
from .programs import target_nodes, verify_program
from .runtime_control import RuntimeFrozen, VersionConflict
from .storage import write_json_atomic

POLICY = "source-grounded-positive-publication/1.0"
REQUIREMENTS = (
    "Judge each supplied rule/source node independently. For each definite judgment "
    "quote BOTH the applicable normative basis text (use its basis ID as source_id) "
    "and the actual paper source. Explain the applicable obligation and its evidence. "
    "Check applicability and stated exceptions; do not infer missing conditions. "
    "Local absence requires complete_local_scope, full source quotes and search_scope. "
    "Different topic, absent mention, inaccessible cited content or retrieval miss "
    "cannot prove contradiction or nonexistence. Return UNKNOWN if not established. "
    "Do not infer detector outputs from target selection."
)
TASKS = ("publication-evidence-audit/1.0", "publication-evidence-review/1.0")


class _Client:
    """Preserve the supplied transport, ledger, cache and pacing without retry."""
    def __init__(self, client):
        self.client = client
        self.config = getattr(client, "config", {})
    def check(self):
        if self.client is None:
            raise RuntimeError("publication reviewer unavailable")
        check = getattr(self.client, "check", None)
        if check:
            check()
    def complete_json(self, *args):
        return self.client.complete_json(*args)


def _packet(ir, analysis, package, node, gateway, environment, content_cache):
    # Same source projection as online_loop._packet, restricted before retrieval
    # so unflagged targets do not trigger content requests.
    data, ready = _target_data(ir, analysis, node, gateway, environment, content_cache)
    metadata = {name: deepcopy(values[node["id"]]) for name, values in analysis["results"].items()
                if name in {"bibliography_fields", "external_work"} and node["id"] in values}
    for values in metadata.values():
        for fact in values.values():
            for eid in fact.get("evidence_ids", []):
                evidence = next((e for e in analysis["evidence"] if e["id"] == eid), None)
                if evidence and evidence.get("kind") == "controlled_catalog_scope":
                    data["sources"].append({"source_id": "evidence:" + eid, "origin": "external",
                        "content_id": eid, "work_id": "", "text": json.dumps(evidence, sort_keys=True),
                        "coverage": "complete_catalog", "complete": True})
    return {"rule_id": str(package["program_spec"]["rule_id"]), "node_id": node["id"],
            "rule_text": package["input"]["rule_text"], "basis": deepcopy(package["input"]["basis"]),
            "sources": data["sources"], "node": deepcopy(node), "metadata": metadata,
            "citation_context": data.get("citation_context"), "source_ready": ready}, data


def _scope_ids(ir, node, data):
    if _base_kind(ir, node["kind"]) == "ReferenceUse":
        return {data.get("citation_context", {}).get("node_id")}
    nodes = {n["id"]: n for n in ir["nodes"]}
    found, pending = set(), [node["id"]]
    while pending:
        key = pending.pop()
        if key not in found:
            found.add(key)
            pending.extend(nodes[key]["children"])
    return found


def audit_positives(ir, analysis, report, packages, *, client, gateway, output_dir,
                    evidence_environment=None, batch_size=8):
    """Return {public, internal}; publish only two source-grounded node violations.

    Corpus postprocessing can pass its saved ir/analysis/report plus loaded
    packages. Website callers must expose only result["public"], never internal.
    No scorer, new label, detector execution, online refinement or CAS is run.
    """
    if type(batch_size) is not int or not 1 <= batch_size <= 8:
        raise ValueError("publication batch_size must be 1..8")
    validate_ir(ir)
    validate_analysis(ir, analysis)
    if report.get("paper_ir_sha256") != ir_hash(ir):
        raise ValueError("stale publication report IR")
    if report.get("analysis_sha256") != _hash(analysis):
        raise ValueError("stale publication analysis")
    packages = list(packages)
    by_rule, targets = {}, {}
    for package in packages:
        verify_program(package)
        rid = str(package["program_spec"]["rule_id"])
        if rid in by_rule:
            raise ValueError("duplicate publication rule")
        by_rule[rid] = package
        targets[rid] = target_nodes(package, ir)
    positives = {}
    for rule in report.get("rules", []):
        rid = str(rule["rule_id"])
        if rid not in by_rule or rule.get("program_version") != by_rule[rid]["manifest"]["version_id"]:
            raise ValueError("stale publication program")
        for row in rule.get("results", []):
            if row.get("status") == "VIOLATION":
                key = (rid, row.get("node_id"))
                if key[1] not in targets[rid]:
                    raise ValueError("publication target outside program")
                positives.setdefault(key, []).append(deepcopy(row))
    binding = {"policy": POLICY, "requirements": REQUIREMENTS, "audit_policy": online_loop.AUDIT_POLICY,
        "ir": ir_hash(ir), "analysis": _hash(analysis), "report": _hash(report),
        "programs": [p["manifest"]["version_id"] for p in packages],
        "model": {k: getattr(client, "config", {}).get(k) for k in ("MAAS_MODEL", "MAAS_MODEL_VERSION")},
        "evidence_environment": evidence_environment, "snapshot": getattr(gateway, "snapshot_id", None),
        "online_source": hashlib.sha256(Path(online_loop.__file__).read_bytes()).hexdigest(),
        "publication_source": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "batch_size": batch_size}
    fingerprint = _hash(binding)
    folder = Path(output_dir) / ("publication-" + fingerprint)
    folder.mkdir(parents=True, exist_ok=True)
    result_path = folder / "result.json"
    if result_path.exists():
        return json.loads(result_path.read_text())
    for name, value in [("input.json", binding), ("original-report.json", report)]:
        path = folder / name
        if path.exists():
            if json.loads(path.read_text()) != value:
                raise ValueError("publication checkpoint changed")
        else:
            write_json_atomic(path, value, exclusive=True)
    work_analysis, content_cache = deepcopy(analysis), {}
    decisions, findings, stopped = [], [], None
    entries = sorted(positives)
    transport = _Client(client)
    for offset in range(0, len(entries), batch_size):
        keys = entries[offset:offset+batch_size]
        batch = folder / ("batch-%04d" % (offset // batch_size))
        batch.mkdir(exist_ok=True)
        views, items, reasons = {}, [], {}
        for key in keys:
            reasons[key] = []
            if stopped:
                reasons[key].append(stopped)
                continue
            try:
                item, data = _packet(ir, work_analysis, by_rule[key[0]], targets[key[0]][key[1]],
                                     gateway, evidence_environment, content_cache)
                items.append(item)
                views[key] = (data, by_rule[key[0]], targets[key[0]][key[1]])
            except Exception as error:
                reason = "source_preparation_failed:" + type(error).__name__
                reasons[key].append(reason)
                if isinstance(error, (BudgetExceeded, RuntimeFrozen, VersionConflict)):
                    stopped = reason
        packet = {"publication_requirements": REQUIREMENTS, "targets": items}
        judgments = []
        for task in TASKS:
            grounded = {}
            error_path = batch / (task.split("/")[0] + "-error.json")
            answer_path = batch / (task.split("/")[0] + ".json")
            input_path = batch / (task.split("/")[0] + "-input.json")
            error = None
            if stopped:
                error = {"reason": stopped, "stop": True}
            elif error_path.exists():
                error = json.loads(error_path.read_text())
            elif input_path.exists() and not answer_path.exists():
                error = {"reason": "previous_review_interrupted_or_uncertain", "stop": True}
            elif items:
                try:
                    answer = _call(transport, task, packet, batch)
                    # Ground independently per target: one malformed node cannot
                    # discard verifiable evidence for another node in its batch.
                    for key in views:
                        receipt_path = batch / (task.split("/")[0] + "-" + _hash(key)[:20] + "-grounding.json")
                        saved = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
                        if saved.get("error"):
                            reasons[key].append(saved["error"])
                            continue
                        receipts = {key: saved["receipt"]} if saved.get("receipt") else {}
                        try:
                            grounded.update(_ground_judgments(answer, {key: views[key]}, ir,
                                            client=transport, review_receipts=receipts))
                        except (BudgetExceeded, RuntimeFrozen, VersionConflict):
                            raise
                        except Exception as exc:
                            saved["error"] = "grounding_failed:" + type(exc).__name__
                            reasons[key].append(saved["error"])
                        if key in receipts:
                            saved["receipt"] = receipts[key]
                        write_json_atomic(receipt_path, saved)
                except Exception as exc:
                    error = {"reason": "review_failed:" + type(exc).__name__,
                             "stop": isinstance(exc, (BudgetExceeded, RuntimeFrozen, VersionConflict))}
            if error:
                if not error_path.exists():
                    write_json_atomic(error_path, error, exclusive=True)
                if error.get("stop"):
                    stopped = error["reason"]
                for key in keys:
                    reasons[key].append(error["reason"])
            judgments.append(grounded)
        for key in keys:
            reviews = [j.get(key) for j in judgments]
            normative_sets = []
            for i, review in enumerate(reviews):
                if not review:
                    reasons[key].append("review_%d_not_grounded" % (i+1))
                    normative_sets.append(set())
                    continue
                if review["status"] != "VIOLATION":
                    reasons[key].append("review_%d_not_violation" % (i+1))
                evidence = review["evidence"]
                norms = {e["basis_id"] for e in evidence if e.get("kind") == "normative_span"}
                normative_sets.append(norms)
                if not norms:
                    reasons[key].append("review_%d_missing_exact_normative_quote" % (i+1))
                scopes = _scope_ids(ir, views[key][2], views[key][0])
                if not any(e.get("origin") == "paper" and e.get("node_id") in scopes for e in evidence):
                    reasons[key].append("review_%d_missing_target_source_quote" % (i+1))
            if len(normative_sets) == 2 and not (normative_sets[0] & normative_sets[1]):
                reasons[key].append("reviews_lack_common_grounded_obligation")
            published = not reasons[key] and all(reviews)
            decision = {"rule_id": key[0], "node_id": key[1], "original_status": "VIOLATION",
                        "original_results": positives[key], "publication_status": "ALERT" if published else "NO_ALERT",
                        "proven_pass": False, "reasons": reasons[key], "reviews": reviews}
            decisions.append(decision)
            if published:
                findings.append({"rule_id": key[0], "node_id": key[1], "scope": "rule_node",
                    "status": "VIOLATION", "message": "Source and normative evidence support a rule violation.",
                    "review_reasons": [r["reason"] for r in reviews],
                    "evidence": [[{k: v for k, v in e.items() if k != "source_text"}
                                  for e in r["evidence"]] for r in reviews],
                    "verification": "two_independent_model_contexts; not human gold"})
    result = {"public": {"status": "ALERT" if findings else "NO_ALERT", "findings": findings},
              "internal": {"policy": POLICY, "input_sha256": fingerprint, "output_dir": str(folder.resolve()),
                "proposed_positive_nodes": len(entries), "accounted_positive_nodes": len(decisions),
                "proven_pass": False, "decisions": decisions, "stop_reason": stopped,
                "scope": "Proposed-positive publication review only; no recall or zero-FP guarantee."}}
    write_json_atomic(result_path, result, exclusive=True)
    return result
