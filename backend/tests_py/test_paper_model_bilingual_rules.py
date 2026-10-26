import sys

sys.path.insert(0, str(__file__).split("/backend/tests_py")[0] + "/backend")

from scripts.paper_model_bilingual_rules import extract_bilingual_facts


def _ir(lines):
    return {
        "layout": {
            "pages": [{
                "page_index": 0,
                "lines": [{"text": text, "bbox": bbox} for text, bbox in lines],
            }]
        },
        "nodes": [],
    }


def _english_values(lines):
    return extract_bilingual_facts(_ir(lines))["english_keywords"]["values"]


def test_keeps_real_hyphen_when_keyword_wraps():
    assert _english_values([
        ("Key words: Secure Multi-party Computation, Re-", [0, 0, 100, 10]),
        ("verse Multiplication-Friendly Embedding", [0, 20, 200, 30]),
    ])[-1] == "Re-verse Multiplication-Friendly Embedding"
    facts = extract_bilingual_facts(_ir([
        ("Key words: Secure Multi-party Computation, Re-", [0, 0, 100, 10]),
        ("verse Multiplication-Friendly Embedding", [0, 20, 200, 30]),
    ]))
    assert facts["english_keywords"]["match_values"][-1] == "Reverse Multiplication-Friendly Embedding"


def test_discards_overlapping_stray_text_layer():
    assert _english_values([
        ("Key words: Secure Multi-party Computation, Re-", [100, 20, 200, 30]),
        ("Stars", [70, 18, 95, 32]),
        ("verse Multiplication-Friendly Embedding", [0, 40, 200, 50]),
    ])[-1] == "Re-verse Multiplication-Friendly Embedding"


def test_preserves_other_hyphenated_keywords():
    assert _english_values([
        ("Key words: Privacy-preserving Machine Learning, Multi-", [0, 0, 200, 10]),
        ("party Computation", [0, 20, 200, 30]),
    ]) == ["Privacy-preserving Machine Learning", "Multi-party Computation"]
