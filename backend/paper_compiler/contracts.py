"""Structural validity is separate from the correctness of a paper's claims."""
import hashlib
import math
import re
from pathlib import Path

from .storage import json_bytes


class ContractError(ValueError):
    pass


SCHEMA_VERSION = 'paper-ir/1.0'
MODEL_VERSION = 'paper-model/1.0'
KINDS = set('Paper FrontMatter Body BackMatter TitlePage Title PersonMention Abstract Keywords Section Heading Paragraph List ListItem Figure FigurePanel Caption VisualLabel Table TableRow TableCell Equation MathExpression SymbolMention TermDefinition SymbolDefinition ReferenceUse CitationGroup Bibliography BibliographyEntry ReadingList Appendix Note ToC ToCEntry Index IndexEntry Declaration Acknowledgements Biography UnknownBlock'.split())
COMMON = {'role': (str, dict), 'lang': str, 'label': str, 'scope_id': str, 'extensions': dict}
ATTRS = {
    'Paper': {'title': str, 'authors': list},
    'Section': {'number': str, 'level': int}, 'Heading': {'number': str, 'level': int},
    'ReferenceUse': {'namespace': str, 'expected_kind': str, 'selector': dict, 'use_role': (str, dict)},
    'CitationGroup': {'style': (str, dict), 'marker': str, 'superscript': (bool, dict)},
    'BibliographyEntry': {'key': (str, dict), 'resource_type': (str, dict), 'fields': dict},
    'Bibliography': {'style': (str, dict), 'bibliography_kind': str},
    'Figure': {'visual_kind': str, 'asset': (str, dict)}, 'FigurePanel': {'asset': (str, dict)},
    'TableCell': {'row': int, 'column': int, 'rowspan': int, 'colspan': int, 'unit': (str, dict)},
    'TableRow': {'row': int}, 'Equation': {'expression': (str, dict)},
    'MathExpression': {'expression': (str, dict)}, 'SymbolMention': {'lexeme': str},
    'TermDefinition': {'lexeme': str}, 'SymbolDefinition': {'lexeme': str, 'unit': (str, dict)},
    'UnknownBlock': {'candidate_kinds': list, 'reason': str},
    'ToCEntry': {'printed_locator': str, 'selector': dict},
    'IndexEntry': {'printed_locator': str, 'selector': dict},
    'Abstract': {'abstract_kind': str},
}
ATTRIBUTE_ENUMS = {'BibliographyEntry': {'resource_type': [
    'book','book_chapter','journal_article','newspaper_article','conference','thesis',
    'report','standard','patent','webpage','archive','map','dataset','preprint',
    'collection','computer_program','database','other']}}

IR_KEYS = set('schema_version model_version document_id revision source_artifacts root_id nodes coverage profile layout metadata extensions'.split())
REQUIRED_IR = IR_KEYS - {'layout', 'metadata', 'extensions'}
FORBIDDEN = {'oracle', 'expected', 'expected_diagnostics', 'expected_status', 'mutation_target', 'target_rule', 'ground_truth', 'gold_label'}
STATES = {'observed', 'confirmed_absent', 'unknown', 'not_applicable'}
COVERAGE = {'complete', 'partial', 'failed', 'not_requested'}


def require(condition, message):
    if not condition:
        raise ContractError(message)


def reject_answers(value):
    if isinstance(value, dict):
        require(not FORBIDDEN.intersection(value), 'evaluation answer leakage')
        for child in value.values():
            reject_answers(child)
    elif isinstance(value, list):
        for child in value:
            reject_answers(child)


def _observations(value):
    if isinstance(value, dict):
        if 'state' in value:
            state = value['state']
            require(state in STATES, 'invalid observation state')
            if state == 'observed':
                require('value' in value and value['value'] is not None, 'observed requires value')
            elif state == 'confirmed_absent':
                require(bool(value.get('search_scope')) and bool(value.get('evidence_ids')), 'absence requires scope and evidence')
            else:
                require(bool(value.get('reason')), 'unknown or not_applicable requires reason')
        for child in value.values():
            _observations(child)
    elif isinstance(value, list):
        for child in value:
            _observations(child)


def serialize_ir(ir: dict) -> bytes:
    return json_bytes(ir)


def ir_hash(ir: dict) -> str:
    return hashlib.sha256(serialize_ir(ir)).hexdigest()


def _integer(value):
    return type(value) is int


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _span(span, sources, pages, source_texts):
    require(isinstance(span, dict), 'provenance must be an object')
    kind = span.get('kind')
    if kind == 'synthetic':
        require(bool(span.get('operation_id')), 'synthetic provenance requires operation_id')
        ancestors = span.get('ancestor_provenance', [])
        require(isinstance(ancestors, list), 'ancestor_provenance must be a list')
        for ancestor in ancestors:
            _span(ancestor, sources, pages, source_texts)
        require(not {'source_id', 'bbox', 'page_index'}.intersection(span), 'synthetic content must not impersonate source')
        return
    if kind == 'derived':
        require(bool(span.get('producer')) and bool(span.get('input_provenance')), 'derived provenance requires producer and inputs')
        for original in span['input_provenance']:
            _span(original, sources, pages, source_texts)
        return
    require(kind == 'source', 'unsupported runtime provenance kind')
    source_id = span.get('source_id')
    require(source_id in sources, 'unknown provenance source_id')
    has_chars = 'char_start' in span or 'char_end' in span
    has_page = 'page_index' in span or 'bbox' in span
    require(has_chars or has_page, 'source provenance needs a range')
    if has_chars:
        start, end = span.get('char_start'), span.get('char_end')
        require(_integer(start) and _integer(end) and 0 <= start <= end, 'invalid character range')
        if source_id in source_texts:
            require(end <= len(source_texts[source_id]), 'character range exceeds source')
    if has_page:
        index = span.get('page_index')
        require(_integer(index) and index >= 0 and index in pages, 'invalid page index')
        if 'page_count' in sources[source_id]:
            require(index < sources[source_id]['page_count'], 'page index exceeds source')
        require(span.get('coordinate_system') == 'unrotated_top_left_points', 'unknown coordinate system')
        box = span.get('bbox')
        require(isinstance(box, list) and len(box) == 4 and all(_number(x) for x in box), 'invalid bbox')
        page = pages[index]
        require(-.01 <= box[0] <= box[2] <= page['width'] + .01 and
                -.01 <= box[1] <= box[3] <= page['height'] + .01, 'bbox exceeds page')


def validate_ir(ir: dict, source_root: Path | None = None) -> None:
    require(isinstance(ir, dict), 'IR must be an object')
    reject_answers(ir)
    require(REQUIRED_IR <= ir.keys() and not ir.keys() - IR_KEYS, 'unknown or missing IR fields')
    require(ir['schema_version'] == SCHEMA_VERSION, 'unsupported schema version')
    require(ir['model_version'] == MODEL_VERSION, 'unsupported model version')
    for key in ['document_id', 'revision', 'root_id']:
        require(isinstance(ir[key], str) and bool(ir[key]), key + ' must be a nonempty string')
    require(isinstance(ir['profile'], dict) and isinstance(ir['coverage'], dict), 'profile/coverage must be objects')
    sources, source_texts = {}, {}
    require(isinstance(ir['source_artifacts'], list) and bool(ir['source_artifacts']), 'source_artifacts required')
    for source in ir['source_artifacts']:
        require(isinstance(source, dict), 'source must be an object')
        sid = source.get('id')
        require(isinstance(sid, str) and sid and sid not in sources, 'duplicate/invalid source id')
        require(source.get('kind') in {'pdf', 'text'}, 'unsupported source kind')
        require(isinstance(source.get('path'), str), 'source path required')
        require(isinstance(source.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', source['sha256']), 'invalid source hash')
        if 'page_count' in source:
            require(_integer(source['page_count']) and source['page_count'] >= 0, 'invalid source page_count')
        sources[sid] = source
        if source_root is not None:
            path = Path(source['path'])
            path = path if path.is_absolute() else Path(source_root) / path
            require(path.is_file(), 'source file missing')
            payload = path.read_bytes()
            require(hashlib.sha256(payload).hexdigest() == source['sha256'], 'source hash mismatch')
            if source['kind'] == 'text':
                try:
                    source_texts[sid] = payload.decode('utf-8')
                except UnicodeError as error:
                    raise ContractError('source text is not UTF-8') from error
    layout = ir.get('layout', {'pages': []})
    require(isinstance(layout, dict) and isinstance(layout.get('pages'), list), 'invalid layout')
    pages = {}
    for page in layout['pages']:
        require(isinstance(page, dict), 'page must be an object')
        index = page.get('page_index')
        require(_integer(index) and index >= 0 and index not in pages, 'invalid/duplicate layout page')
        require(all(_number(page.get(k)) and page[k] > 0 for k in ['width', 'height']), 'invalid page dimensions')
        require(page.get('rotation') in (0, 90, 180, 270), 'invalid page rotation')
        pages[index] = page
    require(isinstance(ir['nodes'], list), 'nodes must be a list')
    nodes = {}
    for node in ir['nodes']:
        require(isinstance(node, dict) and set(node) == {'id', 'kind', 'text', 'children', 'attrs', 'provenance'}, 'invalid node fields')
        nid = node['id']
        require(isinstance(nid, str) and nid and nid not in nodes, 'duplicate/invalid node id')
        require(node['kind'] in KINDS, 'unknown node kind')
        require(node['text'] is None or isinstance(node['text'], str), 'node text must be string or null')
        require(isinstance(node['children'], list) and all(isinstance(c, str) for c in node['children']), 'invalid children')
        require(len(set(node['children'])) == len(node['children']), 'duplicate children')
        require(isinstance(node['attrs'], dict), 'attrs must be an object')
        schema = {**COMMON, **ATTRS.get(node['kind'], {})}
        require(not node['attrs'].keys() - schema.keys(), 'unknown node attribute')
        for key, value in node['attrs'].items():
            require(isinstance(value, schema[key]) and not (schema[key] is int and isinstance(value, bool)), 'wrong attribute type: ' + key)
        selector = node['attrs'].get('selector')
        if selector is not None:
            require(isinstance(selector.get('kind'), str) and isinstance(selector.get('value'), str), 'invalid selector')
        _observations(node['attrs'])
        require(isinstance(node['provenance'], list), 'provenance must be a list')
        require(node['text'] is None or bool(node['provenance']), 'text without provenance')
        for span in node['provenance']:
            _span(span, sources, pages, source_texts)
        nodes[nid] = node
    require(ir['root_id'] in nodes and nodes[ir['root_id']]['kind'] == 'Paper', 'missing Paper root')
    parents = {nid: 0 for nid in nodes}
    for node in nodes.values():
        for child in node['children']:
            require(child in nodes, 'dangling child')
            parents[child] += 1
        scope = node['attrs'].get('scope_id')
        require(scope is None or scope in nodes, 'unknown scope')
    require(parents[ir['root_id']] == 0, 'root has a parent/cycle')
    require(all(count == 1 for nid, count in parents.items() if nid != ir['root_id']), 'non-root must have one parent')
    seen, queue = set(), [ir['root_id']]
    while queue:
        nid = queue.pop()
        require(nid not in seen, 'structure cycle')
        seen.add(nid)
        queue.extend(nodes[nid]['children'])
    require(len(seen) == len(nodes), 'unreachable nodes')
    for record in ir['coverage'].values():
        require(isinstance(record, dict) and record.get('status') in COVERAGE, 'invalid coverage')
        if record['status'] == 'complete':
            require(bool(record.get('protocol')) and bool(record.get('evidence_ids')), 'complete coverage requires protocol and evidence')


def validate_analysis(ir: dict, analysis: dict) -> None:
    require(isinstance(analysis, dict), 'analysis must be an object')
    reject_answers(analysis)
    require(analysis.get('paper_ir_sha256') == ir_hash(ir), 'stale analysis hash')
    require(analysis.get('schema_version') == 'paper-analysis/1.0', 'unsupported analysis schema')
    require(analysis.get('model_version') == ir['model_version'], 'analysis model version mismatch')
    for key in ['capability_versions', 'results', 'coverage']:
        require(isinstance(analysis.get(key), dict), 'analysis missing ' + key)
    nodes = {n['id']: n for n in ir['nodes']}
    entities = {}
    for entity in analysis.get('entities', []):
        require(isinstance(entity, dict) and isinstance(entity.get('id'), str), 'invalid semantic entity')
        require(entity['id'] not in entities and entity['id'] not in nodes, 'duplicate semantic entity')
        entities[entity['id']] = entity
    evidence = {}
    for item in analysis.get('evidence', []):
        require(isinstance(item, dict) and isinstance(item.get('id'), str), 'invalid evidence')
        require(item['id'] not in evidence, 'duplicate evidence id')
        evidence[item['id']] = item
    for binding in analysis.get('bindings', []):
        require(isinstance(binding, dict) and binding.get('use_id') in nodes, 'unknown binding use')
        use = nodes[binding['use_id']]
        require(use['kind'] == 'ReferenceUse', 'binding use must be ReferenceUse')
        require(binding.get('status') in {'resolved', 'unresolved', 'ambiguous'}, 'invalid binding status')
        targets = binding.get('target_ids')
        require(isinstance(targets, list) and all(t in nodes for t in targets), 'unknown binding target')
        if binding['status'] == 'resolved':
            require(bool(targets), 'resolved binding needs target')
            expected_kind = use['attrs'].get('expected_kind')
            require(all(nodes[t]['kind'] == expected_kind for t in targets), 'binding target type mismatch')
    endpoints = {**nodes, **entities}
    edge_types = {'identifies': ({'BibliographyEntry'}, {'ExternalWork'}),
                  'refers_to': ({'ReferenceUse'}, KINDS),
                  'relevant_to': ({'ExternalWork'}, {'CitationIntent'}),
                  'supports': (None, None), 'answers': (None, None), 'uses': (None, None),
                  'describes': (None, None), 'defines': (None, None), 'derived_from': (None, None),
                  'contradicts': (None, None), 'summarizes': (None, None), 'synthesizes': (None, None), 'backref': (None, None)}
    for edge in analysis.get('edges', []):
        require(isinstance(edge, dict) and edge.get('type') in edge_types, 'unknown edge type')
        require(edge.get('from') in endpoints and edge.get('to') in endpoints, 'unknown edge endpoint')
        left, right = edge_types[edge['type']]
        require(left is None or endpoints[edge['from']]['kind'] in left, 'edge source type mismatch')
        require(right is None or endpoints[edge['to']]['kind'] in right, 'edge target type mismatch')
        require(all(e in evidence for e in edge.get('evidence_ids', [])), 'unknown edge evidence')
    _observations(analysis['results'])
    def verify_observations(value):
        if isinstance(value,dict):
            if 'state' in value:
                require(all(e in evidence or e in nodes for e in value.get('evidence_ids',[])), 'unknown observation evidence')
            for child in value.values():verify_observations(child)
        elif isinstance(value,list):
            for child in value:verify_observations(child)
    verify_observations(analysis['results'])
    attributes=analysis.get('node_attributes',{})
    require(isinstance(attributes,dict),'resolved node attributes must be an object')
    for node_id,values in attributes.items():
        require(node_id in nodes and isinstance(values,dict),'unknown resolved attribute node')
        declared={**COMMON,**ATTRS.get(nodes[node_id]['kind'],{})}
        for name,observation in values.items():
            require(name in declared and isinstance(observation,dict) and 'state' in observation,'undeclared or untyped resolved attribute')
            if observation.get('state')=='observed':
                typ=declared[name]
                if isinstance(typ,tuple):typ=tuple(t for t in typ if t is not dict)
                value=observation.get('value')
                require(isinstance(value,typ) and not (typ is int and isinstance(value,bool)),'resolved attribute type mismatch')
                require(bool(observation.get('evidence_ids')),'resolved attribute requires evidence')
                source=nodes[node_id]['attrs'].get(name)
                if source is not None and not (isinstance(source,dict) and source.get('state') in {'unknown','not_applicable'}):
                    known=source.get('value') if isinstance(source,dict) and source.get('state')=='observed' else source
                    require(known==value,'resolved attribute conflicts with known source')
    _observations(attributes);verify_observations(attributes)
