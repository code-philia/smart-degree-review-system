import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "run_rule_regression.py"
spec = importlib.util.spec_from_file_location("rule_regression", SCRIPT)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


def test_typo_contract_requires_pairs_rejects_false_positives_and_duplicates():
    case = {"engine": "typo", "must_find": [{"text": "布署", "suggestion": "部署"}],
            "must_not_find": ["降低至"], "no_duplicate_locations": True}
    result = {"findings": [{"message": "疑似错别字：布署", "suggestion": "部署",
                            "location": {"page_number": 2, "bounding_rect": {"x1": 1, "y1": 2, "x2": 3, "y2": 4}}}]}
    assert mod.evaluate_case(case, result) == []
    result["findings"].append({"message": "疑似错别字：降低至", "suggestion": "降低到",
                               "location": {"page_number": 2, "bounding_rect": {"x1": 1, "y1": 2, "x2": 3, "y2": 4}}})
    failures = mod.evaluate_case(case, result)
    assert any("unexpected" in item for item in failures)


def test_fast_local_contract_uses_rule_token():
    case = {"engine": "fast_local", "rule": 38, "must_find": ["第2章方法"], "min_findings": 1}
    result = {"rules": {"38": {"findings": [{"token": "第2章方法"}]}}}
    assert mod.evaluate_case(case, result) == []
