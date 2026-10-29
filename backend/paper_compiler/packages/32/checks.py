def detect(payload):
    results = []
    basis = ['r32-existing-reference']
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
        if proof_ids and scope == 'serpapi:google_scholar':
            title = identity.get('title') or '该参考文献（题名未提取）'
            results.append(emit(
                node, 'UNKNOWN', f'未在 SerpAPI 中查到：{title}；当前仅作提示，不计入规则警告。',
                check_id='work_existence', basis=basis, evidence_ids=proof_ids,
                reasons=['serpapi_not_found'],
            ))
        elif proof_ids:
            results.append(emit(node, 'VIOLATION', '受控目录检索未找到该参考文献，按规则32判定引用不存在。', check_id='work_existence', basis=basis, evidence_ids=proof_ids))
        else:
            reason = exists.get('reason') or 'SerpAPI Scholar 检索失败或证据不足，暂不判定引用不存在。'
            results.append(emit(node, 'UNKNOWN', '参考文献存在性尚无充分证据。', check_id='work_existence', basis=basis, evidence_ids=ids if supported else [node['id']], reasons=[reason]))
    return results
