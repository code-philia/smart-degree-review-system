"""Retrieve bounded native body quotes for interpreting bilingual terminology.

This module does not decide equivalence or abstract completeness. Its output is
source evidence for the caller to assess, including evidence that contradicts a
proposed translation. It performs no PDF, network, OCR, or model calls.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import math
import re
from typing import Any


_MAX_SPANS = 6
_MAX_QUOTE = 1000
_MAX_CHARACTERS = 5000
_CJK = re.compile(r"[\u3400-\u9fff]+")
_WORDS = re.compile(r"[a-z][a-z-]{2,}")
_CUES = re.compile(
    r"定义|称为|称作|称.{0,18}为|是指|即为|也称|又称|意味着|等价|对应|"
    r"启\s*发|表示|代表|核心(?:特征|思想)|"
    r"\b(?:defin(?:e[ds]?|ition)|refers?\s+to|called|means?|denotes?|namely|inspired)\b",
    re.I | re.S,
)
_EXCLUDED = {"ToC", "ToCEntry", "Bibliography", "BibliographyEntry", "BackMatter",
             "Declarations", "Declaration", "Acknowledgements", "Biography",
             "Appendix", "Figure", "Table", "Caption", "UnknownBlock"}
_ADMIN_TITLE = re.compile(r"声明|授权|答辩|致谢|简历|declaration|authorization|acknowledg", re.I)
_CHAPTER = re.compile(r"^(?:第[一二三四五六七八九十百\d]+章|chapter\s+\d+)(?:\s*[:：]?\s*[^.。]{1,65})?$", re.I)
_STOP = set("the and for with from this that these those using based method methods study studies our their into through which its are was were have has propose proposed paper work results information approach framework".split())


def _normalized(text: str) -> str:
    # Normalization is used only for retrieval. Returned quotes stay exact.
    return re.sub(r"\s+", "", text).casefold()


def _matches(term: str, text: str, compact: str) -> bool:
    if term not in compact:
        return False
    if not re.fullmatch(r"[a-z-]+", term):
        return True
    # Spaces/newlines may separate a phrase, but a technical keyword must not
    # match a longer unrelated English word (e.g. path versus pathology).
    pattern = r"(?<![a-z])" + r"\s*".join(re.escape(char) for char in term) + r"(?![a-z])"
    return bool(re.search(pattern, text, re.I))


def _query_terms(facts: dict[str, Any]) -> tuple[set[str], set[str]]:
    keywords: set[str] = set()
    abstract_terms: set[str] = set()
    for language in ("chinese", "english"):
        item = facts.get(language + "_keywords") or {}
        if isinstance(item, dict):
            values = item.get("values") or item.get("match_values") or []
            for value in values:
                term = _normalized(str(value))
                if 4 <= len(term) <= 120:
                    keywords.add(term)
        abstract = str(facts.get(language + "_abstract") or "")
        compact = re.sub(r"\s+", "", abstract)
        for run in _CJK.findall(compact):
            for width in (4, 6, 8):
                abstract_terms.update(run[i:i + width] for i in range(len(run) - width + 1))
        words = _WORDS.findall(abstract.casefold())
        for width in (2, 3, 4):
            for start in range(len(words) - width + 1):
                phrase = words[start:start + width]
                if phrase[0] not in _STOP and phrase[-1] not in _STOP:
                    abstract_terms.add("".join(phrase))
    return keywords, abstract_terms - keywords


def _body_start(pages: list[dict[str, Any]], facts: dict[str, Any]) -> int | None:
    """Recover source body onset when Paragraph ancestors stayed in Abstract.

    A full chapter heading (including a split chapter number/title) after the
    extracted front matter is independent evidence. ToC pages and dotted leader
    entries cannot provide it. This does not change the shared IR tree.
    """
    front = max((int(loc.get("page_number", 0)) - 1
                 for loc in (facts.get("locations") or {}).values() if isinstance(loc, dict)), default=-1)
    for page in sorted(pages, key=lambda item: item.get("page_index", 0)):
        if page.get("page_index", 0) <= front:
            continue
        lines = page.get("lines", [])
        if any(_normalized(str(line.get("text", ""))) in {"目录", "目次", "contents", "tableofcontents"}
               for line in lines):
            continue
        for line in lines:
            text = str(line.get("text", "")).strip()
            heading = re.sub(r"\s+", "", text) if text.startswith("第") else text
            if (_CHAPTER.fullmatch(heading)
                    and not re.search(r"\.{2,}|…|[。．]{2,}|[，,；;。]", text)):
                return int(page.get("page_index", 0))
    return None


def _source_runs(node: dict[str, Any], source_lines: dict, ignored: set[str]):
    """Yield exact live text ranges whose complete text has native provenance."""
    text = str(node.get("text") or "")
    run: list[dict[str, Any]] = []
    for source in sorted(node.get("provenance", []), key=lambda p: p.get("node_text_start", -1)):
        line = source_lines.get((source.get("page_index"), source.get("line_id")))
        start, end = source.get("node_text_start"), source.get("node_text_end")
        offsets = source.get("text_offsets") or []
        valid = (source.get("kind") == "source" and source.get("source_id") == "pdf"
                 and line and source.get("line_id") not in ignored
                 and isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text)
                 and len(offsets) == 2 and all(isinstance(n, int) for n in offsets)
                 and 0 <= offsets[0] < offsets[1] <= len(str(line.get("text", "")))
                 and text[start:end] == str(line.get("text", ""))[offsets[0]:offsets[1]])
        connected = (run and source.get("page_index") == run[-1].get("page_index")
                     and text[run[-1]["node_text_end"]:start] in {"", "\n", " "})
        if run and (not valid or not connected):
            yield run
            run = []
        if valid:
            run.append(source)
    if run:
        yield run


def retrieve_terminology_context(ir: dict[str, Any], facts: dict[str, Any]) -> list[dict[str, Any]]:
    """Return up to six exact native body quotes (at most 5,000 quote chars).

    Every item contains a physical ``page_number``, ``node_id``, exact half-open
    node text offsets, source ``line_ids`` and copied native ``provenance``.
    ``matched_terms`` reports lexical retrieval signals, not equivalent terms.
    Input objects are never modified and missing evidence produces no context.
    """
    keywords, abstract_terms = _query_terms(facts)
    if not (keywords or abstract_terms):
        return []
    nodes = ir.get("nodes", [])
    by_id = {node.get("id"): node for node in nodes}
    parents = {child: node.get("id") for node in nodes for child in node.get("children", [])}
    pages = ir.get("layout", {}).get("pages", [])
    source_lines = {(page.get("page_index"), line.get("id")): line
                    for page in pages for line in page.get("lines", []) if line.get("id")}
    ignored = {p.get("line_id") for node in nodes
               if node.get("attrs", {}).get("role") in {"running_header", "running_footer", "page_number"}
               for p in node.get("provenance", [])}
    body_start = _body_start(pages, facts)
    raw = []
    for node in nodes:
        if node.get("kind") != "Paragraph" or node.get("attrs", {}).get("role"):
            continue
        ancestors, seen = [], set()
        current = node.get("id")
        while current in parents and current not in seen:
            seen.add(current)
            current = parents[current]
            ancestors.append(by_id.get(current, {}))
        if any(a.get("kind") in _EXCLUDED for a in ancestors):
            continue
        if any(_ADMIN_TITLE.search(str(by_id.get(child, {}).get("text") or ""))
               for a in ancestors for child in a.get("children", [])
               if by_id.get(child, {}).get("kind") == "Heading"):
            continue
        under_body = any(a.get("kind") == "Body" for a in ancestors)
        for run in _source_runs(node, source_lines, ignored):
            page_index = run[0]["page_index"]
            if body_start is not None and page_index < body_start:
                continue
            if not under_body and body_start is None:
                continue
            start, end = run[0]["node_text_start"], run[-1]["node_text_end"]
            text = node["text"][start:end]
            for sentence in re.finditer(r".+?(?:[。！？!?]|\.(?=\s|$)|$)", text, re.S):
                sentence_text = sentence.group()
                cues = list(_CUES.finditer(sentence_text))
                if not cues:
                    continue
                cue = cues[0]
                # A long native paragraph may contain multiple definitions. Keep
                # bounded contiguous windows around their explanatory language.
                left = sentence.start() + max(0, cue.start() - 300)
                right = min(sentence.end(), left + _MAX_QUOTE)
                left = max(0, min(left, right - _MAX_QUOTE))
                if len(sentence_text) <= _MAX_QUOTE:
                    left, right = sentence.start(), sentence.end()
                while left < right and text[left].isspace():
                    left += 1
                quote = text[left:right]
                normal = _normalized(quote)
                matched_keywords = {term for term in keywords if _matches(term, quote, normal)}
                matched_abstract = {term for term in abstract_terms if _matches(term, quote, normal)}
                # One complete keyword or two independent abstract phrases are
                # needed. A shared short word alone cannot retrieve a passage.
                selected = []
                for term in sorted(matched_abstract, key=lambda t: (-len(t), t)):
                    if not any(term in earlier for earlier in selected):
                        selected.append(term)
                    if len(selected) == 12:
                        break
                if not matched_keywords and (len(selected) < 2 or sum(map(len, selected)) < 10):
                    continue
                raw.append({"node": node, "run": run, "start": start + left, "end": start + right,
                            "quote": quote, "keywords": matched_keywords, "abstract": selected,
                            "cues": len(list(_CUES.finditer(quote)))})
    if not raw:
        return []
    frequency = Counter(term for item in raw for term in set(item["abstract"]))
    for item in raw:
        lexical = sum(min(8, len(term) / 2) * math.log(1 + len(raw) / frequency[term])
                      for term in item["abstract"])
        # Prefer explanations of names to paragraphs merely containing many
        # topic keywords. Both supportive and contradictory definitions qualify.
        normal = _normalized(item["quote"])
        strong = bool(re.search(r"定义|称.{0,18}为|称作|是指|即为|也称|又称|意味着|"
                                r"defin|refers?\s+to|called|means?|denotes?|namely", item["quote"], re.I | re.S))
        inspired = bool(re.search(r"启\s*发|\binspired\b", item["quote"], re.I))
        bilingual = bool(_CJK.search(item["quote"]) and any(
            re.search(r"[a-z]", term) and term in normal for term in item["keywords"]))
        item["score"] = (min(20, 12 * len(item["keywords"])) + min(20, lexical)
                         + 30 * strong + 35 * inspired + 30 * bilingual)
    raw.sort(key=lambda item: (-item["score"], item["run"][0]["page_index"],
                               str(item["node"].get("id")), item["start"]))
    result, used = [], 0
    for item in raw:
        node_id = item["node"].get("id")
        if any(previous["node_id"] == node_id
               and previous["node_text_start"] < item["end"]
               and item["start"] < previous["node_text_end"] for previous in result):
            continue
        if used + len(item["quote"]) > _MAX_CHARACTERS:
            continue
        sources = [deepcopy(p) for p in item["run"]
                   if p["node_text_start"] < item["end"] and item["start"] < p["node_text_end"]]
        result.append({"quote": item["quote"], "page_number": sources[0]["page_index"] + 1,
                       "node_id": node_id, "node_text_start": item["start"], "node_text_end": item["end"],
                       "line_ids": [p["line_id"] for p in sources], "provenance": sources,
                       "matched_terms": sorted(item["keywords"]) + item["abstract"][:8],
                       "context_kind": "body_terminology_context"})
        used += len(item["quote"])
        if len(result) == _MAX_SPANS:
            break
    return result
