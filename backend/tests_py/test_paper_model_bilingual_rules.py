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


def test_rejoins_out_of_order_keyword_fragments_on_the_same_physical_row():
    assert _english_values([
        ("Quantum Chemistry", [143.695, 676.941, 241.363, 692.949]),
        ("Key words: ", [85.039, 680.037, 143.695, 696.045]),
        (", Multimodal Large Language Models", [291.007, 680.037, 473.983, 696.045]),
        ("II", [301.727, 749.803, 307.721, 758.803]),
    ]) == ["Quantum Chemistry", "Multimodal Large Language Models"]


def test_reads_wrapped_values_after_a_standalone_keyword_label():
    assert _english_values([
        ("Key words:", [80, 100, 140, 112]),
        ("Federated Learning, Backdoor Attack", [80, 124, 320, 136]),
        ("II", [290, 780, 310, 792]),
    ]) == ["Federated Learning", "Backdoor Attack"]


def test_a_bare_keyword_label_is_not_a_nonempty_keyword_fact():
    ir = _ir([
        ("Key words: ", [80, 100, 140, 112]),
        ("II", [290, 780, 310, 792]),
    ])
    ir["nodes"] = [{"id": "p", "kind": "Paragraph", "text": "Key words: ", "children": []}]
    facts = extract_bilingual_facts(ir)
    assert facts["english_keywords"] is None


def test_abstracts_stop_before_keyword_rows_and_following_sections():
    facts = extract_bilingual_facts(_ir([
        ("摘要", [80, 80, 120, 92]),
        ("本文提出联邦学习方法。", [80, 104, 320, 116]),
        ("关键词：联邦学习，参数寻址", [80, 128, 320, 140]),
        ("I", [290, 780, 310, 792]),
        ("Abstract", [80, 820, 150, 832]),
        ("We propose a federated learning method.", [80, 844, 420, 856]),
        ("Key words: federated learning, stellar spectroscopy", [80, 868, 430, 880]),
        ("II", [290, 1580, 310, 1592]),
        ("目录", [80, 1620, 120, 1632]),
        ("第1章 绪论", [80, 1644, 320, 1656]),
    ]))
    assert facts["chinese_abstract"] == "本文提出联邦学习方法。"
    assert facts["english_abstract"] == "We propose a federated learning method."
