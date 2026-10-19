"""Fixed handwritten R33 over Paper IR and source-grounded semantic facts.

The optional model assesses citation meaning only; it never creates or repairs
this detector. Unknown evidence remains internal UNKNOWN and raises no alert.
"""
from copy import deepcopy
from .programs import build_program

RULE_TEXT = "引用应由已确认被引作品的内容支持其具体用途。方法借鉴、背景、定义、数据、比较、批评及反驳均可能相关；跨领域或结论不同不等于无关。正文引用语境和被引原文须有可追溯证据，只有正面语义矛盾才报警，证据不足不报警。"
DEFAULT_BASIS = [{"id": "r33-citation-support", "text": RULE_TEXT}]

CODE = 'def detect(payload):\n    output = []\n    evidence = {}\n    for item in payload.get("analysis", {}).get("evidence", []):\n        evidence[item.get("id")] = item\n    for use in nodes(payload, "ReferenceUse"):\n        observation = fact(payload, "fixed_citation_support_v1", use.get("id"), "relation")\n        ids = observation.get("evidence_ids", [])\n        if not isinstance(ids, list):\n            ids = []\n        has_paper = False\n        has_source = False\n        for evidence_id in ids:\n            item = evidence.get(evidence_id, {})\n            if item.get("kind") == "source_span" and item.get("origin") == "paper":\n                has_paper = True\n            if item.get("kind") == "external_span" and item.get("origin") == "external":\n                has_source = True\n        relation = observation.get("value")\n        basis = observation.get("basis")\n        reason = observation.get("reason", "")\n        grounded = observation.get("state") == "observed" and has_paper and has_source and isinstance(reason, str) and bool(reason.strip())\n        if grounded and relation == "contradicted" and basis == "explicit_scope_contradiction":\n            output.append(emit(use, "VIOLATION", "该引用所支持的具体陈述与已确认被引作品的内容存在正面矛盾。", "citation-claim-support", BASIS_IDS, ids, [reason]))\n        elif grounded and relation == "supported" and basis == "explicit_support":\n            output.append(emit(use, "PASS", "已确认被引作品的原文支持该次引用的实际用途。", "citation-claim-support", BASIS_IDS, ids, [reason]))\n        else:\n            output.append(emit(use, "UNKNOWN", "引用用途与被引内容尚无充分可追溯证据确认，暂不报警。", "citation-claim-support", BASIS_IDS, ids, ["insufficient_grounded_citation_support"]))\n    return output\n'

INSTRUCTIONS = "Assess ONE actual ReferenceUse and its bound, positively identified cited work. Extract a source-grounded relation, not program code. For field relation return state observed with value supported or contradicted only when BOTH the exact citing context and substantive exact cited-work text establish that relation. Return state unknown otherwise. Do not use any desired outcome, mutation label or case identity.\nFirst identify the concrete proposition and rhetorical purpose actually governed by THIS citation marker; consider the complete bound sentence/clause and all claims attributed to the source. In a grouped citation assess this cited work's contribution independently. Follow anaphoric continuations that explicitly refer back to the same cited work (for example this work, this framework, 该工作, 该框架, 该方法), including after a semicolon or after the target marker. A later citation marker does not by itself change the referent of an anaphoric claim. Use the full supplied paragraph to resolve that referent, and assess all propositions attributed to this same identified work; one supported initial clause does not excuse a later positively incompatible attribution. Require a clear referential link rather than assigning arbitrary nearby author claims to the cited work. A source supporting one sentence fragment cannot establish a contradictory added claim. Conversely do not attribute a nearby author's own new proposal, limitation or empirical criticism to the cited work merely because a citation occurs nearby.\nSupported means the cited work actually supports the concrete purpose: method borrowing/transfer, background, definition, data, comparison, criticism, rebuttal, motivation or extension can all be legitimate. Cross-disciplinary application, different conclusions, and criticism are not intrinsically irrelevant. Do not infer support merely from a purpose-category keyword or broad topical similarity.\nContradicted requires positive semantic incompatibility: a factual, quantitative, method/contribution or definition attribution expressly conflicts with what the identified source states, or a positively established exclusive scope rules out that precise attribution. Compare exact claims, numbers, quantifiers, direction, scope and attribution. Faithful translation or paraphrase is allowed. Explicit criticism/comparison/rebuttal does not require the source to agree with the citing author; it is supported when the source is accurately represented as the target of that discourse. A same-topic claim can be contradicted; topic differences, missing details, abstract-only omissions, inaccessible full text and failure to retrieve are never contradiction evidence.\nFor supported use basis explicit_support. For contradicted use basis explicit_scope_contradiction and a reason identifying the two positively incompatible statements and actual citation purpose; the runtime may independently verify this contradiction. If the supplied source coverage cannot resolve it, keep state unknown without claiming nonexistence or irrelevance. Observed relation must have nonempty reason and exact quotes from BOTH the current citing context (not just a citation marker/bibliography) and the relevant identified cited-work body. Use only supplied source_id and exact contiguous substrings, preserving original whitespace. Never invent a source, content, quote, code or source coordinates. Keep unsupported relation unknown even if a violation would be convenient.\nOutput the existing fields contract only: fields.relation={state,value?,basis?,reason,quotes:[{source_id,quote}]}. No detector code generation or modification is requested.\n"

ANALYSIS_REQUESTS = [{"name": "fixed_citation_support_v1", "targets": ["ReferenceUse"],
                      "fields": {"relation": "string"}, "instructions": INSTRUCTIONS}]


def build_r33_package(*, model=None, basis=None, rule_text=None):
    """Build unchanged fixed code under the caller's shared Paper Model/basis."""
    basis = deepcopy(DEFAULT_BASIS if basis is None else basis)
    if not isinstance(basis, list) or not basis or any(
            not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] or
            not isinstance(item.get("text"), str) or not item["text"].strip() for item in basis):
        raise ValueError("R33 requires explicit normative basis")
    if len({item["id"] for item in basis}) != len(basis):
        raise ValueError("duplicate R33 basis IDs")
    candidate = {"rule_id": "33", "title": "引用用途与已确认被引内容的支持核验",
                 "requires": ["fixed_citation_support_v1"], "target_kinds": ["ReferenceUse"],
                 "code": CODE.replace("BASIS_IDS", repr([item["id"] for item in basis])),
                 "analysis_requests": deepcopy(ANALYSIS_REQUESTS), "model_patch": {}}
    return build_program(candidate, rule_text=RULE_TEXT if rule_text is None else rule_text,
                         basis=basis, model=model)


build_package = build_r33_package
