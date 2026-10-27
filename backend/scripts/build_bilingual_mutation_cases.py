"""Build 20 Paper Model fact mutations for each bilingual semantic rule."""
from __future__ import annotations
import argparse, copy, json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_model_bilingual_rules import extract_bilingual_facts, load_paper_model

ABSTRACT_CONTRADICTIONS = [
    "The English abstract instead studies blockchain consensus, not secure multi-party computation.",
    "The English abstract instead studies image classification, not matrix-ring and integer-ring protocols.",
    "The English abstract instead reports a public-data experiment rather than privacy-preserving training.",
    "The English abstract instead uses homomorphic encryption as its proposed method, not MPC.",
    "The English abstract instead proposes an attention mechanism, not a message authentication code scheme.",
    "The English abstract instead uses a single packing method, not DoublePack.",
    "The English abstract instead claims quadratic online communication, not constant communication.",
    "The English abstract instead assumes an honest majority throughout, not a dishonest-majority setting.",
    "The English abstract instead studies real-valued vectors, not integer rings Z2k.",
    "The English abstract instead applies the protocol to sentiment classification, not linear regression.",
    "The English abstract instead applies the protocol to database indexing, not deep neural network training.",
    "The English abstract instead reports exponential preprocessing overhead, not sublinear overhead.",
    "The English abstract instead studies elliptic-curve cryptography, not matrix rings.",
    "The English abstract instead focuses on energy efficiency, not security and privacy protection.",
    "The English abstract instead describes postprocessing optimization, not preprocessing optimization.",
    "The English abstract instead uses RSA key exchange, not RMFE.",
    "The English abstract instead claims that the protocol is insecure, contradicting the Chinese security conclusion.",
    "The English abstract instead reports no engineering evaluation, contradicting the Chinese experimental validation.",
    "The English abstract instead claims that the protocol is slower than all baselines, contradicting the Chinese performance result.",
    "The English abstract instead concludes that the work concerns natural-language translation, not privacy computing.",
]
KEYWORD_REPLACEMENTS = [
    "Stars", "Blockchain", "Sentiment Analysis", "Computer Vision", "Natural Language Processing",
    "Differential Privacy", "Federated Learning", "Quantum Computing", "Database Systems", "Robotics",
]
KEYWORD_REMOVALS = ["Rings", "Message Authentication Code", "Privacy-preserving Machine Learning", "Secure Multi-party Computation", "Re-verse Multiplication-Friendly Embedding"]
KEYWORD_ADDITIONS = ["Security", "Blockchain", "Robotics", "Computer Vision", "Natural Language Processing"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    base = extract_bilingual_facts(load_paper_model(args.source))
    if not base.get("english_abstract") or not base.get("english_keywords", {}).get("values"):
        raise ValueError("Paper Model 未提取到英文摘要或关键词")
    cases = []
    base_path = args.output / "00_consistent.json"
    base_path.write_text(json.dumps(base, ensure_ascii=False, indent=2))
    cases.append({"name": "00_consistent.json", "rule_id": "both", "expected": "passed", "mutation": {"type": "none"}, "review": "正常对照：中英文摘要和关键词语义一致", "path": str(base_path)})
    def write(name, rule_id, facts, mutation, review):
        path = args.output / name
        path.write_text(json.dumps(facts, ensure_ascii=False, indent=2))
        cases.append({"name": name, "rule_id": rule_id, "expected": "issues_found", "mutation": mutation, "review": review, "path": str(path)})
    for index, sentence in enumerate(ABSTRACT_CONTRADICTIONS, 1):
        facts = copy.deepcopy(base)
        contradiction = (sentence + " This is a different study from the Chinese abstract; none of the Chinese abstract's secure multi-party computation, matrix-ring, integer-ring, or privacy-preserving conclusions apply to the English study.")
        facts["english_abstract"] += "\n" + contradiction
        write(f"abstract_{index:02}.json", "bilingual_abstract_consistency_check", facts,
              {"type": "append", "field": "english_abstract", "value": contradiction},
              "英文摘要新增与中文摘要研究对象/方法/结果/结论相冲突的陈述")
    chinese_values = base["chinese_keywords"]["values"]
    english_values = base["english_keywords"]["values"]
    for index, replacement in enumerate(KEYWORD_REPLACEMENTS, 1):
        facts = copy.deepcopy(base)
        target_index = index % len(english_values)
        old = facts["english_keywords"]["values"][target_index]
        facts["english_keywords"]["values"][target_index] = replacement
        write(f"keywords_{index:02}.json", "bilingual_keywords_correspondence_check", facts,
              {"type": "replace", "field": f"english_keywords.values[{target_index}]", "old": old, "new": replacement},
              "保持关键词数量不变，但将一个英文关键词替换为无对应语义的词")
    for offset, removal in enumerate(KEYWORD_REMOVALS, 11):
        facts = copy.deepcopy(base)
        facts["english_keywords"]["values"] = [value for value in facts["english_keywords"]["values"] if value != removal]
        write(f"keywords_{offset:02}.json", "bilingual_keywords_correspondence_check", facts,
              {"type": "remove", "field": "english_keywords.values", "value": removal},
              "删除一个英文关键词，造成中英文关键词数量和对应关系缺失")
    for offset, addition in enumerate(KEYWORD_ADDITIONS, 16):
        facts = copy.deepcopy(base)
        facts["english_keywords"]["values"].append(addition)
        write(f"keywords_{offset:02}.json", "bilingual_keywords_correspondence_check", facts,
              {"type": "append", "field": "english_keywords.values", "value": addition},
              "新增一个中文关键词没有对应项的英文关键词")
    manifest = {"source": str(args.source), "paper_model_version": base.get("model_version"), "paper_ir_version": base.get("schema_version"), "base_facts": base, "cases": cases}
    (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps({"cases": len(cases), "abstract": 20, "keywords": 20, "output": str(args.output)}, ensure_ascii=False))
if __name__ == "__main__":
    main()
