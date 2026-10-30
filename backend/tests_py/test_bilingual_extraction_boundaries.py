import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.paper_model_bilingual_rules import extract_bilingual_facts
from paper_compiler.frontend import build_paper


def _page(index, rows):
    return {"page_index": index, "width": 600, "height": 840,
            "lines": [{"text": text, "bbox": box} for text, box in rows]}


def _facts(*pages):
    return extract_bilingual_facts({"nodes": [], "layout": {"pages": list(pages)}})


def test_keywords_do_not_cross_into_next_page_abstract():
    facts = _facts(
        _page(0, [("关键词：云计算；工作流调度；遗传编程", [80, 700, 500, 712]),
                  ("- II -", [280, 780, 320, 792])]),
        _page(1, [("Abstract", [250, 120, 350, 140]),
                  ("Cloud computing is a service paradigm.", [80, 180, 500, 192])]))
    assert facts["chinese_keywords"]["values"] == ["云计算", "工作流调度", "遗传编程"]


def test_chinese_wrapped_keyword_keeps_complete_word():
    facts = _facts(_page(0, [
        ("关键词：编译器测试，程序合成，程序", [80, 550, 500, 565]),
        ("特征", [80, 580, 104, 592]),
        ("II", [290, 780, 310, 792])]))
    assert facts["chinese_keywords"]["values"] == ["编译器测试", "程序合成", "程序特征"]


def test_keyword_continuation_wins_over_labeled_node_fragment():
    ir = {"nodes": [{"id": "p", "kind": "Paragraph", "text": "关键词：程序合成，程序"}],
          "layout": {"pages": [_page(0, [
              ("关键词：程序合成，程序", [80, 550, 500, 565]),
              ("特征", [80, 580, 104, 592]),
              ("II", [290, 780, 310, 792])])]}}
    assert extract_bilingual_facts(ir)["chinese_keywords"]["values"] == ["程序合成", "程序特征"]


def test_keywords_stop_before_classification_metadata():
    facts = _facts(_page(0, [
        ("Keywords: Large Language Mod-", [80, 190, 500, 202]),
        ("els; Knowledge Enhancement", [150, 210, 400, 222]),
        ("CLC code:", [80, 230, 150, 242]),
        ("TP311", [160, 230, 210, 242])]))
    assert facts["english_keywords"]["values"] == ["Large Language Mod-els", "Knowledge Enhancement"]
    assert facts["english_keywords"]["match_values"] == ["Large Language Models", "Knowledge Enhancement"]


def test_keywords_stop_at_separate_section_on_same_page():
    facts = _facts(_page(0, [
        ("Keywords: compiler testing", [80, 120, 400, 132]),
        ("1 Introduction", [80, 190, 250, 210]),
        ("This is body prose.", [80, 240, 500, 252])]))
    assert facts["english_keywords"]["values"] == ["compiler testing"]


def test_abstract_heading_in_toc_is_not_an_abstract():
    facts = _facts(
        _page(0, [("摘要", [80, 150, 110, 162]), ("ix", [490, 150, 505, 162]),
                  ("Abstract", [80, 180, 130, 192]), ("xi", [490, 180, 505, 192]),
                  ("第1章 绪论", [80, 220, 200, 232])]),
        _page(1, [("摘", [250, 120, 275, 144]), ("要", [320, 120, 345, 144]),
                  ("本文提出知识增强漏洞检测方法。", [80, 180, 500, 192]),
                  ("关键词：软件漏洞；知识增强", [80, 240, 500, 252])]),
        _page(2, [("Abstract", [250, 120, 350, 144]),
                  ("We propose knowledge-enhanced vulnerability detection.", [80, 180, 500, 192]),
                  ("Keywords: Software Vulnerability; Knowledge Enhancement", [80, 240, 500, 252])]))
    assert facts["chinese_abstract"] == "本文提出知识增强漏洞检测方法。"
    assert facts["english_abstract"] == "We propose knowledge-enhanced vulnerability detection."
    assert facts["locations"]["chinese_abstract"]["page_number"] == 2
    assert facts["locations"]["english_abstract"]["page_number"] == 3


def test_abstract_omits_repeated_headers_and_page_locators():
    facts = _facts(
        _page(0, [("University doctoral dissertation", [200, 60, 400, 72]),
                  ("Abstract", [250, 120, 350, 144]),
                  ("The method improves detection", [80, 180, 500, 192]),
                  ("第iii 页", [280, 780, 320, 792])]),
        _page(1, [("University doctoral dissertation", [200, 60, 400, 72]),
                  ("while reducing false positives.", [80, 120, 500, 132]),
                  ("Keywords: Detection; Knowledge", [80, 180, 500, 192])]))
    assert facts["english_abstract"] == "The method improves detection\nwhile reducing false positives."


def test_abstract_without_keywords_stops_before_contents():
    facts = _facts(_page(0, [
        ("Abstract", [250, 120, 350, 144]),
        ("A real abstract paragraph.", [80, 180, 500, 192]),
        ("Contents", [250, 300, 350, 324]),
        ("1 Introduction ........ 1", [80, 360, 500, 372])]))
    assert facts["english_abstract"] == "A real abstract paragraph."


def test_native_paper_model_skips_toc_abstract_entry(tmp_path):
    import pymupdf
    pdf = tmp_path / "paper.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=840)
        page.insert_text((80, 100), "Contents")
        page.insert_text((80, 150), "Abstract")
        page.insert_text((490, 150), "xi")
        page.insert_text((80, 200), "1 Introduction ........ 1")
        page = document.new_page(width=600, height=840)
        page.insert_text((250, 120), "Abstract", fontsize=22)
        page.insert_text((80, 180), "We propose a compiler testing method.")
        page.insert_text((80, 220), "Keywords: Compiler Testing; Program Synthesis")
        document.save(pdf)
    facts = extract_bilingual_facts(build_paper(pdf, include_citations=False))
    assert facts["english_abstract"] == "We propose a compiler testing method."
    assert facts["locations"]["english_abstract"]["page_number"] == 2

def test_numeric_result_line_remains_in_abstract():
    facts = _facts(_page(0, [
        ("Abstract", [250, 120, 350, 144]),
        ("Experiments on 80 mobile applications and", [80, 180, 500, 192]),
        ("160 design mock-ups demonstrate improved precision.", [80, 200, 500, 212]),
        ("Keywords: GUI Testing; Design Mock-ups", [80, 240, 500, 252])]))
    assert "160 design mock-ups demonstrate improved precision." in facts["english_abstract"]

def test_native_abstract_title_near_top_survives_repeated_continuation_header(tmp_path):
    import pymupdf
    pdf = tmp_path / "top-abstract.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=840)
        page.insert_text((250, 100), "Abstract", fontsize=22)
        page.insert_text((80, 180), "The first part is significant.", fontsize=12)
        page = document.new_page(width=600, height=840)
        page.insert_text((250, 70), "Abstract", fontsize=12)
        page.insert_text((80, 180), "A contradictory conclusion is important.", fontsize=12)
        page.insert_text((80, 240), "Keywords: Testing; Precision", fontsize=12)
        document.save(pdf)
    facts = extract_bilingual_facts(build_paper(pdf, include_citations=False))
    assert facts["english_abstract"] == (
        "The first part is significant.\nA contradictory conclusion is important.")
    assert facts["locations"]["english_abstract"]["page_number"] == 1

def test_native_running_header_before_title_metadata_does_not_start_abstract(tmp_path):
    import pymupdf
    pdf = tmp_path / "abstract-metadata.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=840)
        page.insert_text((250, 70), "Abstract", fontsize=12)
        page.insert_text((80, 130), "Research thesis title", fontsize=22)
        page.insert_text((80, 180), "Author and supervisor", fontsize=12)
        page.insert_text((250, 240), "Abstract", fontsize=22)
        page.insert_text((80, 300), "The actual abstract body.", fontsize=12)
        page.insert_text((80, 350), "Keywords: Testing; Precision", fontsize=12)
        page = document.new_page(width=600, height=840)
        page.insert_text((250, 70), "Abstract", fontsize=12)
        document.save(pdf)
    facts = extract_bilingual_facts(build_paper(pdf, include_citations=False))
    assert facts["english_abstract"] == "The actual abstract body."

def test_native_numeric_result_after_small_page_header_remains_in_abstract(tmp_path):
    import pymupdf
    pdf = tmp_path / "numeric-continuation.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=840)
        page.insert_text((180, 70), "University doctoral dissertation", fontsize=8)
        page.insert_text((250, 120), "Abstract", fontsize=22)
        page.insert_text((80, 180), "Experiments on 80 mobile applications and", fontsize=12)
        page = document.new_page(width=600, height=840)
        page.insert_text((180, 70), "University doctoral dissertation", fontsize=8)
        page.insert_text((80, 180), "160 design mock-ups demonstrate improved precision.", fontsize=12)
        page.insert_text((80, 240), "Keywords: Testing; Precision", fontsize=12)
        document.save(pdf)
    facts = extract_bilingual_facts(build_paper(pdf, include_citations=False))
    assert facts["english_abstract"] == (
        "Experiments on 80 mobile applications and\n160 design mock-ups demonstrate improved precision.")


def test_native_numbered_section_title_ends_abstract_without_keywords(tmp_path):
    import pymupdf
    pdf = tmp_path / "numbered-section.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=840)
        page.insert_text((250, 120), "Abstract", fontsize=22)
        page.insert_text((80, 180), "The abstract has a conclusion.", fontsize=12)
        page.insert_text((80, 240), "1 Introduction", fontsize=22)
        page.insert_text((80, 300), "The introduction body is separate.", fontsize=12)
        document.save(pdf)
    facts = extract_bilingual_facts(build_paper(pdf, include_citations=False))
    assert facts["english_abstract"] == "The abstract has a conclusion."
