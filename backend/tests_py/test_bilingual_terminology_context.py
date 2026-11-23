"""Retrieval supplies source context, never a semantic verdict."""
import copy
import importlib.util
from pathlib import Path

import pytest


HELPER = Path(__file__).resolve().parents[1] / "scripts/bilingual_terminology_context.py"


def retrieve(ir, facts):
    assert HELPER.is_file(), "bounded terminology context helper is not implemented"
    spec = importlib.util.spec_from_file_location("context_under_test", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.retrieve_terminology_context(ir, facts)


def paper(rows, *, parent_kind="Body", page=9):
    nodes = [{"id": "paper", "kind": "Paper", "children": ["body"]},
             {"id": "body", "kind": parent_kind, "children": []}]
    lines = []
    for i, text in enumerate(rows):
        identifier = f"p{page}-l{i}"
        parts = text.split("\n")
        sources = []
        offset = 0
        for j, part in enumerate(parts):
            line_id = identifier + f"-{j}"
            box = [70, 100 + len(lines) * 14, 500, 112 + len(lines) * 14]
            lines.append({"id": line_id, "text": part, "bbox": box, "font_size": 12})
            sources.append({"kind": "source", "source_id": "pdf", "page_index": page,
                            "line_id": line_id, "bbox": box,
                            "text_offsets": [0, len(part)],
                            "node_text_start": offset, "node_text_end": offset + len(part)})
            offset += len(part) + 1
        node_id = f"n{i}"
        nodes[1]["children"].append(node_id)
        nodes.append({"id": node_id, "kind": "Paragraph", "text": text,
                      "children": [], "provenance": sources})
    return {"nodes": nodes, "layout": {"pages": [{"page_index": page, "height": 840, "lines": lines}]}}


FACTS = {"chinese_keywords": {"values": ["不定跳路径"]},
         "english_keywords": {"values": ["Recursive Path"]},
         "chinese_abstract": "本文研究不定跳路径和复杂约束的图查询优化。",
         "english_abstract": "We study variable length paths and graph query optimization."}


def test_retrieves_exact_quote_with_native_page_and_offsets_without_mutation():
    text = "称路径查询为递归路径查询（Recursive Path Query），其核心特征是递归定\n义，符合正则表达式结果的路径长度不定。"
    ir = paper([text, "无关的天文学观测定义了恒星温度和光谱分类。"])
    original = copy.deepcopy((ir, FACTS))
    result = retrieve(ir, FACTS)
    assert len(result) == 1
    found = result[0]
    assert found["quote"] == text
    assert found["page_number"] == 10
    assert ir["nodes"][2]["text"][found["node_text_start"]:found["node_text_end"]] == text
    assert found["node_id"] == "n0"
    assert found["line_ids"] == [p["line_id"] for p in ir["nodes"][2]["provenance"]]
    assert (ir, FACTS) == original
    found["provenance"][0]["bbox"][0] = 0
    assert (ir, FACTS) == original


@pytest.mark.parametrize("kind", ["ToC", "Bibliography", "BackMatter", "Declarations", "Acknowledgements"])
def test_excludes_nonsubstantive_ancestor_kinds(kind):
    ir = paper(["Recursive Path is defined as variable length paths."], parent_kind=kind)
    assert retrieve(ir, FACTS) == []


def test_does_not_retrieve_a_keyword_mention_without_explanatory_cues():
    ir = paper(["The experiments evaluate Recursive Path on five data sets."])
    assert retrieve(ir, FACTS) == []


def test_refuses_changed_live_text_or_unverifiable_source_provenance():
    ir = paper(["Recursive Path is defined as variable length paths."])
    ir["nodes"][2]["text"] = "Recursive Path is defined as fixed length paths."
    assert retrieve(ir, FACTS) == []
    del ir["nodes"][2]["provenance"]
    assert retrieve(ir, FACTS) == []


@pytest.mark.parametrize("source_id", ["ocr", "ocr-v1", None])
def test_matching_layout_text_does_not_make_nonnative_provenance_eligible(source_id):
    ir = paper(["Recursive Path is defined as variable length paths."])
    for source in ir["nodes"][2]["provenance"]:
        source["source_id"] = source_id
    original = copy.deepcopy(ir)
    assert retrieve(ir, FACTS) == []
    assert ir == original


def test_keeps_contradictory_definitions_as_quotes_without_equivalence_verdicts():
    ir = paper(["Recursive Path is defined as fixed length paths; it excludes variable length paths."])
    result = retrieve(ir, FACTS)
    assert len(result) == 1
    assert "fixed length paths" in result[0]["quote"]
    assert not ({"equivalent", "consistent", "match", "suppress", "outcome"} & result[0].keys())


def test_applies_span_and_character_bounds_deterministically():
    rows = [f"Recursive Path variant {i} is defined as " + "variable length paths, " * 80 + "." for i in range(20)]
    ir = paper(rows)
    first = retrieve(ir, FACTS)
    assert first == retrieve(ir, FACTS)
    assert 1 <= len(first) <= 6
    assert sum(len(item["quote"]) for item in first) <= 5000
    assert all(len(item["quote"]) <= 1000 for item in first)
    for item in first:
        node = next(n for n in ir["nodes"] if n["id"] == item["node_id"])
        assert item["quote"] == node["text"][item["node_text_start"]:item["node_text_end"]]


def test_recovers_source_body_context_when_ir_still_labels_body_as_abstract():
    text = "具体来说，本文首先设计轮次对齐的个性化信息提取模块：基于一种由剪枝启\n发的个性化参数选择的机制，从每轮训练中选出需要个性化的参数。"
    ir = paper([text], parent_kind="Abstract", page=25)
    ir["layout"]["pages"].insert(0, {"page_index": 20, "height": 840, "lines": [
        {"id": "chapter", "text": "第1章", "bbox": [70,100,200,120], "font_size": 18},
        {"id": "title", "text": "绪论", "bbox": [70,130,200,150], "font_size": 18}]})
    facts = {"chinese_abstract": "本文提出轮次对齐的个性化剪枝策略，提高每轮获取的个性化信息的质量。",
             "english_abstract": "We propose a round-aligned personalized parameter selection strategy.",
             "locations": {"english_abstract": {"page_number": 8}}}
    result = retrieve(ir, facts)
    assert len(result) == 1
    assert result[0]["quote"] == text
    assert result[0]["page_number"] == 26


def test_frontmatter_cannot_supply_body_context_without_source_chapter_evidence():
    assert retrieve(paper(["Recursive Path is defined as variable length paths."], parent_kind="Abstract"), FACTS) == []


def test_abstract_experiment_facts_without_terminology_cues_are_not_context():
    ir = paper(["Our variable length paths improve graph query optimization by 18.8 percent."])
    assert retrieve(ir, FACTS) == []


def test_a_specific_bilingual_definition_beats_many_keyword_summary_paragraphs():
    facts = copy.deepcopy(FACTS)
    facts["chinese_keywords"]["values"] += ["图数据库", "复杂约束", "查询优化"]
    summary = "本文的图数据库复杂约束查询优化方法对应不定跳路径，其实验结果良好。"
    target = "当正则表达式包含闭包时，称路径查询为递归路径查询（Recursive Path Query），其核心特征为路径长度不定。"
    ir = paper([summary + str(i) for i in range(10)] + [target])
    result = retrieve(ir, facts)
    assert any(item["quote"] == target for item in result)


def test_source_body_start_excludes_mislabeled_early_body_ancestors():
    ir = paper(["Recursive Path is defined as variable length paths."], page=2)
    ir["layout"]["pages"].append({"page_index": 8, "lines": [
        {"id": "chapter", "text": "第1 章", "bbox": [70,100,200,120]}]})
    assert retrieve(ir, FACTS) == []


def test_keyword_like_substrings_do_not_retrieve_unrelated_definitions():
    ir = paper(["Recursive Pathology is defined as a clinical tissue classification."])
    assert retrieve(ir, {"english_keywords": {"values": ["Recursive Path"]}}) == []


def test_word_boundaries_allow_wrapped_exact_terms():
    text = "Recursive\nPath is defined as variable length paths."
    result = retrieve(paper([text]), {"english_keywords": {"values": ["Recursive Path"]}})
    assert len(result) == 1
    assert result[0]["quote"] == text


@pytest.mark.parametrize("report_id,page_number,needle", [
    ("2031d853-70ff-4840-84a0-438ff81b0665", 27, "Recursive Path Query"),
    ("08f7f8cb-3d0f-432e-bc29-5f342e4d345b", 26, "由剪枝启"),
])
def test_original_native_theses_include_the_critical_definition(report_id, page_number, needle):
    path = Path("/data/runtime/smart-degree-review/paper-lint-reports") / (report_id + ".pdf")
    if not path.is_file():
        pytest.skip("original native thesis is available only on the research server")
    import sys
    sys.path.insert(0, str(HELPER.parents[1]))
    from paper_compiler.frontend import build_paper
    from scripts.paper_model_bilingual_rules import extract_bilingual_facts
    ir = build_paper(path, include_citations=False)
    result = retrieve(ir, extract_bilingual_facts(ir))
    assert any(item["page_number"] == page_number and needle in item["quote"] for item in result)
    by_id = {n["id"]: n for n in ir["nodes"]}
    source_lines = {(p["page_index"], line["id"]): line for p in ir["layout"]["pages"] for line in p["lines"]}
    for item in result:
        assert item["quote"] == by_id[item["node_id"]]["text"][item["node_text_start"]:item["node_text_end"]]
        for source in item["provenance"]:
            line = source_lines[source["page_index"], source["line_id"]]
            assert by_id[item["node_id"]]["text"][source["node_text_start"]:source["node_text_end"]] == line["text"][slice(*source["text_offsets"])]
