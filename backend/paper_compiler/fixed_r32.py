"""Manually authored R32 over shared IR and builtin grounded identity facts.

Finite-catalog exclusion is a scoped assertion, never public-world nonexistence.
UNKNOWN is kept internally and must not become a benchmark PASS. No generation,
repair loop, label file, case identity or task-specific source title is used.
"""
from copy import deepcopy
from .programs import build_program

RULE_TEXT = "参考文献应指向真实存在的文献；规则32使用SerpAPI Google Scholar进行单一检索，成功检索且无匹配结果时判定引用不存在；接口失败不作不存在结论。"
DEFAULT_BASIS = [{"id": "r32-existing-reference", "text": RULE_TEXT}]

CODE = """def detect(payload):
    results = []
    basis = BASIS_IDS
    analysis = payload.get('analysis', {})
    evidence = {item['id']: item for item in analysis.get('evidence', [])}
    for node in nodes(payload, 'BibliographyEntry'):
        exists = fact(payload, 'external_work', node['id'], 'exists')
        ids = exists.get('evidence_ids', [])
        supported = isinstance(ids, list) and len(ids) > 0 and all(isinstance(eid, str) and eid in evidence for eid in ids)
        if exists.get('state') == 'observed' and exists.get('value') is True and supported:
            results.append(emit(node, 'PASS', '已有身份匹配证据支持该参考文献存在。', check_id='work_existence', basis=basis, evidence_ids=ids))
            continue
        proof_ids = []
        scope = exists.get('search_scope')
        complete_source = analysis.get('coverage', {}).get(node['id'], {}).get('status') == 'complete'
        identity = {}
        identity_complete = True
        for name in ['title', 'authors', 'year']:
            field = fact(payload, 'bibliography_fields', node['id'], name)
            if field.get('state') != 'observed' or not field.get('value'):
                identity_complete = False
            identity[name] = field.get('value')
        if exists.get('state') == 'observed' and exists.get('value') is False and supported and (scope == 'serpapi:google_scholar' or (complete_source and identity_complete and isinstance(scope, str) and scope.startswith('controlled_catalog:'))):
            for eid in ids:
                proof = evidence[eid]
                query = proof.get('query', {})
                if scope == 'serpapi:google_scholar' and proof.get('provider') == 'serpapi' and proof.get('engine') == 'google_scholar' and proof.get('status') == 'empty':
                    proof_ids.append(eid)
                elif proof.get('kind') == 'controlled_catalog_scope' and proof.get('domain') == 'controlled_catalog' and proof.get('complete') is True and proof.get('search_scope') == scope and proof.get('protocol') == 'complete-catalog-title-author-year/1.0' and isinstance(proof.get('catalog'), list) and isinstance(query, dict):
                    if all(query.get(name) == identity[name] for name in ['title', 'authors', 'year']):
                        proof_ids.append(eid)
        if proof_ids:
            results.append(emit(node, 'VIOLATION', 'SerpAPI Google Scholar 成功检索未找到该参考文献的匹配结果，按规则32判定引用不存在。', check_id='work_existence', basis=basis, evidence_ids=proof_ids))
        else:
            reason = exists.get('reason') or 'SerpAPI Scholar 检索失败或证据不足，暂不判定引用不存在。'
            results.append(emit(node, 'UNKNOWN', '参考文献存在性尚无充分证据。', check_id='work_existence', basis=basis, evidence_ids=ids if supported else [node['id']], reasons=[reason]))
    return results
"""


def build_r32_package(*, model=None, basis=None, rule_text=None):
    """Build the fixed asset under the caller's shared versioned paper model."""
    basis = deepcopy(DEFAULT_BASIS if basis is None else basis)
    if not isinstance(basis, list) or not basis or any(
            not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] or
            not isinstance(item.get("text"), str) or not item["text"].strip() for item in basis):
        raise ValueError("R32 requires explicit normative basis")
    if len({item["id"] for item in basis}) != len(basis):
        raise ValueError("duplicate R32 basis IDs")
    candidate = {"rule_id": "32", "title": "参考文献真实存在性",
                 "requires": ["bibliography_fields", "external_work"],
                 "target_kinds": ["BibliographyEntry"],
                 "code": CODE.replace("BASIS_IDS", repr([item["id"] for item in basis])),
                 "analysis_requests": [], "model_patch": {}}
    return build_program(candidate, rule_text=RULE_TEXT if rule_text is None else rule_text,
                         basis=basis, model=model)


build_package = build_r32_package
