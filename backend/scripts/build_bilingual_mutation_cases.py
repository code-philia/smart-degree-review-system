"""Build Paper Model fact mutations for bilingual semantic rules."""
from __future__ import annotations
import argparse, copy, json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_model_bilingual_rules import extract_bilingual_facts, load_paper_model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    base = extract_bilingual_facts(load_paper_model(args.source))
    cases = []
    def write(name, rule_id, expected, facts, mutation):
        path = args.output / name
        path.write_text(json.dumps(facts, ensure_ascii=False, indent=2))
        cases.append({"name": name, "rule_id": rule_id, "expected": expected, "mutation": mutation, "path": str(path)})
    write("00_consistent.json", "both", "passed", copy.deepcopy(base), {"type": "none"})
    abstract = copy.deepcopy(base)
    if "faster" not in abstract.get("english_abstract", ""):
        raise ValueError("Paper Model facts do not contain the abstract mutation token: faster")
    abstract["english_abstract"] = abstract["english_abstract"].replace("faster", "slower", 1)
    write("01_abstract_result_conflict.json", "bilingual_abstract_consistency_check", "issues_found", abstract, {"type": "replace", "field": "english_abstract", "old": "faster", "new": "slower"})
    keywords = copy.deepcopy(base)
    if "Rings" not in keywords.get("english_keywords", {}).get("values", []):
        raise ValueError("Paper Model facts do not contain the keyword mutation token: Rings")
    keywords["english_keywords"]["values"] = ["Stars" if value == "Rings" else value for value in keywords["english_keywords"]["values"]]
    write("02_keywords_semantic_mismatch.json", "bilingual_keywords_correspondence_check", "issues_found", keywords, {"type": "replace", "field": "english_keywords.values", "old": "Rings", "new": "Stars"})
    count = copy.deepcopy(base)
    count["english_keywords"]["values"] = [value for value in count["english_keywords"]["values"] if value != "Rings"]
    write("03_keywords_count_mismatch.json", "bilingual_keywords_correspondence_check", "issues_found", count, {"type": "remove", "field": "english_keywords.values", "value": "Rings"})
    (args.output / "manifest.json").write_text(json.dumps({"source": str(args.source), "paper_model_version": base.get("model_version"), "paper_ir_version": base.get("schema_version"), "cases": cases}, ensure_ascii=False, indent=2))
    print(json.dumps(cases, ensure_ascii=False))

if __name__ == "__main__":
    main()
