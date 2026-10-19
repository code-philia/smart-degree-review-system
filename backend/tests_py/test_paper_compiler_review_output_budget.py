"""Single-attempt output headroom for independent review; fake transport only."""
import hashlib
import json
from decimal import Decimal
import pytest
from paper_compiler import conflict_review as review, llm
from paper_compiler.budget import BudgetLedger
from paper_compiler.storage import json_bytes
from test_paper_compiler_complete_work_support import sample, ScopeReviewer
from test_paper_compiler_llm import config, response


def test_review_wire_budget_is_recorded_and_receipt_binds_policy_and_actual_budget(monkeypatch):
    request, raw, data = sample()
    client = ScopeReviewer()
    proofs, first, reason = review.resolve_review(request, raw, data, client=client)
    assert proofs and reason is None
    assert first["max_tokens"] == client.token_limits[-1] == 24000
    assert first["policy"] == "positive-conflict-witness/2.3"
    assert review.COMPLETE_WORK_POLICY == "complete-work-attribution-witness/2.3"
    old_policy = dict(first, policy="positive-conflict-witness/2.2")
    review.resolve_review(request, raw, data, client=client, receipt=old_policy)
    assert len(client.calls) == 2
    monkeypatch.setattr(review, "THINKING_REVIEW_MAX_TOKENS", 12000)
    _, smaller, _ = review.resolve_review(request, raw, data, client=client, receipt=first)
    assert len(client.calls) == 3 and client.token_limits[-1] == 12000
    assert smaller["input_hash"] != first["input_hash"]


@pytest.mark.parametrize("task", [review.TASK, "grounded-observations-flat/1.0"])
def test_only_semantic_tasks_accept_24000_and_reservation_matches_actual_payload(tmp_path, task):
    sent = []
    ledger = BudgetLedger(tmp_path / "budget.db", Decimal("10"))
    client = llm.MaasClient(config(tmp_path), ledger, tmp_path / "cache", "review-test", "5",
        transport=lambda *args: sent.append(args[2]) or response(),
        max_attempts=1, json_output=True, semantic_thinking=True)
    first = client.request_fingerprint(task, "JSON", {}, 12000)
    expanded = client.request_fingerprint(task, "JSON", {}, 24000)
    assert hashlib.sha256(json_bytes(first)).hexdigest() != hashlib.sha256(json_bytes(expanded)).hexdigest()
    for checked_task, limit in [("generated-analysis/2.0", 16384), ("generated-analysis-batch/1.0", 16384), (task, 24000)]:
        with pytest.raises(ValueError, match="max_tokens"):
            client.request_fingerprint(checked_task, "JSON", {}, limit + 1)
    client.complete_json(task, "JSON", {}, 24000)
    assert len(sent) == 1 and sent[0]["max_completion_tokens"] == 24000
    attempt = json.loads(next((tmp_path / "cache/attempts").glob("*.json")).read_text())
    reserved = (Decimal(len(json_bytes(sent[0])) + 1024) * llm.INPUT_PER_MILLION
                + Decimal(24000) * llm.OUTPUT_PER_MILLION) / 1_000_000
    assert Decimal(attempt["reserved_cny"]) == reserved
    assert ledger.summary()["requests"] == 1


def test_truncated_review_stays_invalid_billed_and_never_retried(tmp_path):
    sent = []
    ledger = BudgetLedger(tmp_path / "budget.db", Decimal("10"))
    reply = response("", finish="length", usage={"prompt_tokens": 100, "completion_tokens": 24000})
    client = llm.MaasClient(config(tmp_path), ledger, tmp_path / "cache", "review-test", "5",
        transport=lambda *args: sent.append(args[2]) or reply,
        max_attempts=1, json_output=True, semantic_thinking=True)
    with pytest.raises(llm.ModelError, match="invalid_output"):
        client.complete_json(review.TASK, "JSON", {}, 24000)
    assert len(sent) == ledger.summary()["requests"] == 1
    assert ledger.summary()["completion_tokens"] == 24000
    assert not list((tmp_path / "cache/responses").glob("*.json"))
    attempt = json.loads(next((tmp_path / "cache/attempts").glob("*.json")).read_text())
    assert attempt["status"] == "invalid_output"
    assert attempt["finish_reason"] == "length" and attempt["output_content"] == ""


def test_flat_reference_budget_covers_one_or_two_targets_and_invalidates_old_unknowns(tmp_path, monkeypatch):
    from paper_compiler import program_analysis as runtime
    from test_paper_compiler_program_analysis import Model, Gateway, package
    from test_paper_compiler_program_analysis_batch import paper

    class FlatBudgetModel(Model):
        semantic_thinking = True
        json_output = True
        def __init__(self):
            super().__init__()
            self.batches = []
        def complete_json(self, task, instructions, data, max_tokens):
            if task == "bibliography-fields/1.1":
                return super().complete_json(task, instructions, data, max_tokens)
            assert task == "grounded-observations-flat/1.0"
            self.batches.append((len(data["nodes"]), max_tokens))
            return {"observations": [
                {"node_id": item["node"]["id"], "field": "related", "state": "unknown",
                 "reason": "No semantic evidence supplied by the fake model.", "quote_span_ids": []}
                for item in data["nodes"]]}

    monkeypatch.setenv("PAPER_COMPILER_ANALYSIS_BATCH_SIZE", "8")
    ir = paper(tmp_path, 5)
    model = FlatBudgetModel()
    pkg = package("ReferenceUse", {"related": "boolean"})
    first = runtime.analyze_programs(ir, [pkg], client=model, gateway=Gateway(), cache_dir=tmp_path / "cache")
    assert model.batches == [(2, 24000), (2, 24000), (1, 24000)]
    assert first["policy"]["thinking_reference_max_tokens"] == 24000
    monkeypatch.setattr(runtime, "THINKING_REFERENCE_MAX_TOKENS", 12000)
    second = runtime.analyze_programs(ir, [pkg], client=model, gateway=Gateway(), cache_dir=tmp_path / "cache")
    assert model.batches[3:] == [(2, 12000), (2, 12000), (1, 12000)]
    assert second["policy"]["thinking_reference_max_tokens"] == 12000
