"""Conservative statistical checks using native definitions and table coverage.

This guard can only retain a model's consistent result or downgrade it. It
cannot resolve a model conflict, supply missing measurements, or assume a
metric's arithmetic definition.
"""
from __future__ import annotations

from decimal import Decimal, DecimalException, ROUND_HALF_UP, localcontext
import re

from numeric_metric_evidence import metric_context


_AVERAGE = re.compile(r'平均|均值|\b(?:mean|average)\b', re.I)
_MAXIMUM = re.compile(r'最高|最大|\bmaximum\b', re.I)
_EXPLICIT_MAXIMUM = re.compile(r'最高|最大|最多|\b(?:maximum|maximal|up to)\b', re.I)
_RELATIVE = re.compile(r'relaimpr|relative\s*(?:improv|gain)|相对(?:提升|增益|改善)', re.I)
_IMPROVEMENT_ROW = re.compile(r'^(?:%?\s*improv(?:ement)?\.?|提升比例|相对提升(?:比例)?)$', re.I)
_NATIVE_MAXIMUM = re.compile(r'最高|最大|最多|高达|\b(?:maximum|maximal|up to|as high as)\b', re.I)
_NON_EXACT_PROSE_VALUE = re.compile(
    r'(?:不(?:超过|高于|低于|少于|多于|到|足|达(?:到)?|是|为)|未(?:达(?:到)?|超过)|没有达到|'
    r'至多|至少|小于|大于|低于|高于|少于|多于|[<>]=?|[≤≥≠]|'
    r'\b(?:at\s+(?:most|least)|(?:no\s+)?(?:more|less)\s+than|not\s+equal\s+to))'
    r'\s*(?:为|约|达到|about|approximately)?\s*$', re.I)
_POINTS = re.compile(r'百分点|percentage\s*points?|\bpp\b', re.I)
_NUMBER = re.compile(r'[-+−]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?')
_ALIASES = (
    ('gauc', 'grouped auc', '分组auc', '加权平均auc'),
    ('auc', 'area under the roc curve', '曲线下面积'),
    ('mae', 'mean absolute error', '平均绝对误差'),
    ('sse', 'sum of squared errors', '误差平方和', '平方误差和'),
    ('rmse', 'root mean squared error', '均方根误差'),
    ('mse', 'mean squared error', '均方误差'),
    ('accuracy', 'acc', '准确率'), ('precision', '精确率', '查准率'),
    ('recall', '召回率', '查全率'), ('f1', 'f1-score', 'f1分数'),
    ('ndcg', 'normalized discounted cumulative gain'),
    ('goodput', '有效吞吐量', '有效吞吐', 'effective throughput'),
    ('miss rate', 'missrate', '缺失率', '未命中率'),
    ('speedup', '加速比', '加速倍数', '查询速度提升', '查询加速比'),
)
_AVERAGE_GAP = '已定位相关数值，但引用原文未明确该指标的平均统计口径，需要核实统计范围。'
_MAXIMUM_GAP = '已定位某个实验数值，但引用原文不足以证明它是摘要所述范围内的最高值。'
_ROUNDING_GAP = '模型将不同数值视为近似，但引用证据不能按声明精度四舍五入得到该值，需要作者确认数值精度。'
_SUGGESTION = '请作者结合相应实验表格核实指标、基线和统计范围。'


def _key(value):
    return re.sub(r'\s+', '', str(value or '')).casefold()


def _has(text, term):
    pattern = re.escape(term).replace(r'\ ', r'\s*')
    if re.fullmatch(r'[a-z]{1,5}', term):
        pattern = r'(?<![A-Za-z-])' + pattern + r'(?![A-Za-z])'
    return bool(re.search(pattern, str(text), re.I))


def _metric_terms(declaration):
    metric = str(declaration.get('metric') or '')
    groups = [group for group in _ALIASES if any(_has(metric, term) for term in group)]
    result = set(term for group in groups for term in group) if groups else {metric}
    if declaration.get('unit') in ('倍', '×', 'x', 'times', 'fold') and re.search(r'性能(?:提升|加速)|speedup', metric, re.I):
        result.update(('speedup', '性能提升', '性能加速'))
    return result


def _relative(declaration):
    return (str(declaration.get('comparison') or '').strip().casefold().startswith('relative')
            or bool(_RELATIVE.search(str(declaration.get('metric') or ''))))


def _metric_match(text, declaration):
    terms = _metric_terms(declaration)
    return (any(term and _has(text, term) for term in terms)
            or ('recall' in terms and bool(re.search(r'(?<![A-Za-z])R@\d+', text, re.I)))
            or ('ndcg' in terms and bool(re.search(r'(?<![A-Za-z])N@\d+', text, re.I))))


def _named(text, expected):
    def compact(value):
        protected = re.sub(r'(?<=[A-Za-z0-9])\s+(?=[A-Za-z0-9])', '\x00', value)
        return re.sub(r'\s+', '', protected).replace('\x00', ' ').casefold()
    text, expected = compact(text), compact(expected)
    pattern = re.escape(expected).replace(r'\ ', r'\s+')
    if expected and expected[0].isascii() and expected[0].isalnum():
        pattern = r'(?<![A-Za-z0-9_-])' + pattern
    if expected and expected[-1].isascii() and expected[-1].isalnum():
        pattern += r'(?![A-Za-z0-9_-])'
    return bool(expected and re.search(pattern, text, re.I))


def _improvement_rows(table, declaration):
    if not _relative(declaration) or declaration.get('unit') not in ('%', '％'):
        return []
    return [index for index, row in enumerate(table.get('matrix') or [])
            if row and isinstance(row[0], str) and _IMPROVEMENT_ROW.fullmatch(row[0].strip())]


def _under(model, child, parent):
    seen = set()
    while child in model.get('sections', {}) and child not in seen:
        if child == parent:
            return True
        seen.add(child)
        child = model['sections'][child].get('parent_id')
    return False


def _mapping(row, model, mappings):
    if not model or not isinstance(mappings, list):
        return None
    found = [m for m in mappings if isinstance(m, dict) and m.get('declaration_id') == row['declaration_id']]
    if len(found) != 1:
        return None
    mapping = found[0]
    family = mapping.get('contribution_scope') or {}
    if family.get('version') == 'source-grounded-child-methods/1.0':
        chapters = family.get('chapter_ids') or []
        expanded = family.get('experiment_section_ids') or []
        if (not chapters or mapping.get('chapter_id') not in chapters
                or any(ch not in model['sections'] for ch in chapters)
                or any(not any(_under(model, sid, ch) for ch in chapters) for sid in expanded)):
            return None
        mapping = {**mapping, 'experiment_section_ids': list(dict.fromkeys(
            mapping['experiment_section_ids'] + expanded))}
    experiments = mapping.get('experiment_section_ids')
    if (mapping.get('chapter_id') not in model.get('sections', {}) or not isinstance(experiments, list)
            or not experiments or any(sid not in model['sections'] for sid in experiments)):
        return None
    return mapping


def _expected(declaration):
    text = str(declaration.get('number', '')).strip().replace('−', '-')
    if not _NUMBER.fullmatch(text):
        return None
    try:
        value = Decimal(text)
        return value if value.is_finite() and abs(value.adjusted()) <= 100 else None
    except DecimalException:
        return None


def _rounded(value, expected):
    try:
        with localcontext() as context:
            context.prec = 120
            return value.quantize(Decimal(1).scaleb(expected.as_tuple().exponent), rounding=ROUND_HALF_UP) == expected
    except DecimalException:
        return False


def _number_in_quote(row):
    expected = _expected(row['declaration'])
    if expected is None:
        return False
    for evidence in row.get('evidence', []):
        for token in _NUMBER.findall(str(evidence.get('quote') or '').replace('−', '-')):
            try:
                if _rounded(Decimal(token), expected):
                    return True
            except DecimalException:
                pass
    return False


def _defines_average(text, declaration):
    terms = _metric_terms(declaration)
    for part in re.split(r'[|;；]', text):
        for term in terms:
            if not term or not _has(part, term):
                continue
            pattern = re.escape(term).replace(r'\ ', r'\s*')
            first = re.search(pattern, part, re.I)
            contrast = re.search(r'与.{0,60}(?:不同|相比)|unlike|in contrast', part, re.I)
            if contrast and contrast.start() < first.start():
                continue
            if _AVERAGE.search(term):
                return True
            if re.search(r'(?:平均|均值|\bmean\b|\baverage\b)\s*' + pattern, part, re.I):
                return True
            if re.search(pattern + r'[^|;；。]{0,80}(?:均值|算术平均|平均值|\bmean\b|\baverage\b)', part, re.I):
                return True
    return False


def _average_support(row, model, mapping):
    # A definition supplies semantics only. A separate measured value must still
    # be in the already source-validated result evidence.
    if not mapping or not _number_in_quote(row):
        return None
    source = '\n'.join(e.get('quote') or '' for e in row.get('evidence') or [])
    if not any(_has(source, term) for term in _metric_terms(row['declaration']) if term):
        return None
    for evidence in row.get('evidence') or []:
        if evidence.get('section_id') and not any(_under(model, evidence['section_id'], sid)
                                                 for sid in mapping['experiment_section_ids']):
            return None
    context = metric_context(row['declaration'], mapping, model)
    items = [item for item in context if _defines_average(item['quote'], row['declaration'])
             and any(kind in item['evidence_kinds'] for kind in ('metric_definition', 'metric_header'))]
    if items:
        return {'kind': 'native_average_semantics', 'block_ids': [item['block_id'] for item in items],
                'pages': sorted({item['page'] for item in items})}
    return None


def _headers(table):
    paths = table.get('native_header_paths')
    if not isinstance(paths, list) or not paths:
        names = table.get('column_headers') or []
        return [' '.join(str(name or '').split()) for name in names]
    return [' / '.join(str(part) for part in path if part is not None) if isinstance(path, list) else '' for path in paths]


def _caption_metric_view(table, model, declaration):
    """Bind native caption continuation only below its actual source caption."""
    box = table.get('bbox')
    primary = [b for b in model.get('blocks') or [] if b.get('source_node_id') in (table.get('source_node_ids') or [])
               and b.get('page') == table.get('page') and b.get('section_id') == table.get('section_id')
               and _key(table.get('caption')) in _key(b.get('text'))]
    if not primary or not isinstance(box, list) or len(box) != 4:
        return table
    starts = [p['bbox'][1] for b in primary for p in b.get('provenance') or [] if isinstance(p.get('bbox'), list) and len(p['bbox']) == 4]
    if not starts or not 0 <= box[1] - min(starts) <= 180:
        return table
    sources = []
    for block in model.get('blocks') or []:
        if (not block.get('block_id') or not block.get('source_node_id')
                or block.get('page') != table['page'] or block.get('section_id') != table.get('section_id')):
            continue
        provenance = block.get('provenance') or []
        cursor = 0
        for source in provenance:
            bounds = source.get('bbox')
            start, end = source.get('node_text_start'), source.get('node_text_end')
            length = end - start if type(start) is int and type(end) is int else (len(block['text']) if len(provenance) == 1 else 0)
            if (length > 0 and isinstance(bounds, list) and len(bounds) == 4
                    and min(starts) - 1 <= bounds[1] and bounds[3] <= box[1] + 2
                    and max(0, min(bounds[2], box[2]) - max(bounds[0], box[0])) >= min(bounds[2]-bounds[0], box[2]-box[0]) * .3):
                sources.append({'block_id': block['block_id'], 'source_node_id': block['source_node_id'],
                                'page': block['page'], 'quote': block['text'][cursor:cursor+length],
                                'block_text_start': cursor, 'block_text_end': cursor+length,
                                'provenance': [source]})
            cursor += length + 1
    context = '\n'.join(source['quote'] for source in sources)
    if not _metric_match(context, declaration):
        return table
    other_metric = re.compile(r'latency|runtime|execution time|throughput|accuracy|precision|recall|ndcg|auc|mae|mse|speedup|延迟|时延|准确率|召回率', re.I)
    if any(other_metric.search(header) and not _metric_match(header, declaration) for header in _headers(table)):
        return table
    return {**table, '_native_metric_caption': context, '_native_metric_caption_sources': sources}


def _metric_columns(table, declaration):
    relative = _relative(declaration)
    row_oriented = bool(_improvement_rows(table, declaration))
    ratio = declaration.get('unit') in ('倍', '×', 'x', 'times', 'fold')
    matches = []
    for index, header in enumerate(_headers(table)):
        common_metric = (bool(table.get('_native_metric_caption')) and not re.search(
            r'基准程序|benchmark|operator|models?|methods?|数据集|dataset|名称|序号|^name$', header, re.I))
        if not _metric_match(header, declaration) and not common_metric:
            continue
        if relative and not row_oriented and (not _RELATIVE.search(header) or _POINTS.search(header)) and not (ratio and re.search(r'speedup', header, re.I)):
            continue
        if not relative and _RELATIVE.search(header):
            continue
        matches.append(index)
    method = declaration.get('method') or ''
    named = [index for index in matches if _named(_headers(table)[index], method)] if method else []
    if named:
        return named
    return matches


def _safe_table(table):
    matrix = table.get('matrix')
    columns = table.get('column_count')
    if (table.get('native_cells_grounded') is not True or not isinstance(matrix, list)
            or type(columns) is not int or columns < 2 or len(matrix) < 2
            or table.get('row_count') != len(matrix)
            or any(not isinstance(row, list) or len(row) != columns for row in matrix)
            or len(_headers(table)) != columns):
        return False
    raw = table.get('raw_matrix')
    if raw is not None and (not isinstance(raw, list) or len(raw) != len(matrix)
                            or any(not isinstance(row, list) or len(row) != columns for row in raw)
                            or any(_key(a) != _key(b) for row, original in zip(matrix, raw)
                                   for a, b in zip(row, original))):
        return False
    # Merged cells can be fully grounded by explicit native span relations.
    # Other limited relationships/continuations cannot prove completeness.
    allowed = {'merged_or_multilevel_header_cells'}
    if set(table.get('limitations') or []) - allowed or table.get('cross_page'):
        return False
    return True


def _header_count(table):
    paths = table.get('native_header_paths') or [[header] for header in _headers(table)]
    count = 0
    for row in table['matrix']:
        present = [(index, str(cell)) for index, cell in enumerate(row) if cell is not None and str(cell).strip()]
        if not present or not all(_key(cell) in {_key(part) for part in paths[index]} | {_key(' / '.join(paths[index]))} for index, cell in present):
            break
        count += 1
    return count


def _cell(table, row_index, column_index):
    value = table['matrix'][row_index][column_index]
    spanning = [span for span in table.get('native_spanning_cells') or []
                if span.get('role') == 'body' and row_index in (span.get('row_indices') or [])
                and column_index in (span.get('column_indices') or [])
                and span.get('grounding') == 'native_ruling_boundaries']
    values = {_key(span.get('text')): span.get('text') for span in spanning if span.get('text')}
    if value is not None and str(value).strip():
        if values and _key(value) not in values:
            return None
        return str(value)
    return str(next(iter(values.values()))) if len(values) == 1 else None


def _scope_columns(headers, field):
    patterns = {'dataset': r'data\s*set|数据集', 'method': r'^(?:models?|methods?|模型|方法)$',
                'baseline': r'^(?:baseline|基线|对照(?:模型|方法)?)$',
                'condition': r'condition|条件|角度|视角|split'}
    return [i for i, header in enumerate(headers) if re.search(patterns[field], header, re.I)]


def _scope_value_matches(expected, actual):
    return _key(actual) in {_key(term) for term in re.split(r'[，,；;、|]+', str(expected)) if _key(term)}


def _row_scope(table, row_index, declaration, support=None):
    headers = _headers(table)
    for field in ('dataset', 'method', 'baseline', 'condition'):
        if any(_cell(table, row_index, column) is None for column in _scope_columns(headers, field)):
            return None
    for field in ('dataset', 'method', 'baseline', 'condition'):
        expected = declaration.get(field)
        if not isinstance(expected, str) or not expected.strip():
            continue
        columns = _scope_columns(headers, field)
        explicit = table.get(field)
        if isinstance(explicit, str) and explicit.strip():
            if not _scope_value_matches(expected, explicit):
                return False
            continue
        if not columns:
            if field == 'condition' and re.fullmatch(
                    r'该(?:方案|方法|系统)|本(?:方案|方法|系统)|(?:this|our|the proposed)\s+(?:method|scheme|system)', expected.strip(), re.I):
                continue  # A native anaphoric reference, not a new batch/dataset condition.
            if support and support.get(field) == expected:
                continue
            if field == 'condition' and _key(_MAXIMUM.sub('', expected)) == _key(declaration.get('metric')):
                continue  # This field repeats the statistic, not a new setting.
            if field == 'condition' and re.fullmatch(
                    r'(?:公开|所有|全部|各个|多个)?数据集|(?:all|public|multiple)\s+data\s*sets?', expected.strip(), re.I):
                continue  # Explicitly broad data scope, bound by the mapping.
            return None
        values = [_cell(table, row_index, column) for column in columns]
        if any(value is None for value in values):
            return None
        if not any(_scope_value_matches(expected, value) for value in values):
            return False
    return True


def _measurement(value, header, declaration):
    if value is None:
        return None
    text = str(value).strip().replace('−', '-')
    if declaration.get('unit') in ('倍', '×', 'x', 'times', 'fold') and re.search(r'speedup', header, re.I):
        nested = re.fullmatch(r'[-+]?\d+(?:\.\d+)?\s*\(\s*([-+]?\d+(?:\.\d+)?)\s*[×x]\s*\)', text, re.I)
        if nested:
            return Decimal(nested[1])
    match = re.fullmatch(r'\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*([^\d]*)', text)
    if not match:
        return None
    unit = str(declaration.get('unit') or '').strip()
    suffix = match[2].strip()
    if unit in ('%', '％'):
        if '%' not in suffix and '％' not in suffix and '%' not in header and '％' not in header:
            return None
        if _POINTS.search(header + suffix):
            return None
        if suffix and suffix not in ('%', '％'):
            return None
    elif unit and _key(unit) not in _key(header + suffix):
        return None
    try:
        result = Decimal(match[1])
        return result if result.is_finite() else None
    except DecimalException:
        return None


def _table_scope_support(table, declaration, mapping, model):
    support, sources = {}, []
    columns = _metric_columns(table, declaration)
    method = declaration.get('method') or ''
    if method and columns and all(_named(_headers(table)[index], method) for index in columns):
        support['method'] = method
    if method and table.get('_native_metric_caption') and re.search(r'[\u3400-\u9fff]', method):
        parts = re.findall(r'[A-Za-z0-9]+|[\u3400-\u9fff]+', method)
        title = model['sections'].get(mapping['chapter_id'], {}).get('title') or ''
        if (len(parts) >= 3 and all(len(part) <= 5 for part in parts if part.isascii())
                and all(_key(part) in _key(title) for part in parts)):
            support['method'] = method
            sources.append({'chapter_id': mapping['chapter_id'], 'chapter_title': title,
                            'heading_node_id': model['sections'][mapping['chapter_id']].get('heading_node_id')})
    pattern = re.compile(r'(?:表|\bTable\s*)\s*(\d+\s*[.\-]\s*\d+)', re.I)
    caption = pattern.search(table.get('caption') or '')
    for reference in mapping.get('table_reference_scope') or []:
        if reference.get('table_id') != table.get('table_id') or not caption:
            continue
        block = next((b for b in model.get('blocks') or [] if b.get('block_id') == reference.get('block_id')), None)
        if (not block or reference.get('page') != block.get('page')
                or reference.get('section_id') != block.get('section_id')
                or not any(_under(model, block['section_id'], sid) for sid in mapping['experiment_section_ids'])
                or reference.get('quote') not in block.get('text', '')):
            continue
        cited = pattern.search(reference['quote'])
        if not cited or _key(cited[1]).replace('-', '.') != _key(caption[1]).replace('-', '.'):
            continue
        # The first source reference can introduce a table, while a later
        # paragraph states its named comparison. Both must cite this exact
        # table inside the already mapped experimental scope.
        for context in model.get('blocks') or []:
            if (not context.get('provenance') or not any(_under(model, context.get('section_id'), sid)
                                                       for sid in mapping['experiment_section_ids'])):
                continue
            for sentence in re.split(r'[。！？!?；;]', context.get('text') or ''):
                citations = pattern.finditer(sentence)
                if (not any(_key(match[1]).replace('-', '.') == _key(caption[1]).replace('-', '.') for match in citations)
                        or not re.search(r'对比|比较|compar|versus|\bvs\.?\b', sentence, re.I)):
                    continue
                admitted = False
                for field in ('method', 'baseline', 'condition'):
                    expected = declaration.get(field) or ''
                    name = re.sub(r'^(?:相较于|相比于|相比|相对(?:于)?|对比)', '', expected).strip()
                    if name and _named(sentence, name):
                        support[field] = expected
                        admitted = True
                if admitted:
                    sources.append({'block_id': context['block_id'], 'page': context['page'], 'quote': sentence})
    if support.get('baseline') and re.sub(r'^(?:相较于|相比于|相比|相对(?:于)?|对比)', '', declaration.get('condition') or '').strip() == declaration.get('baseline'):
        support['condition'] = declaration['condition']
    family = mapping.get('contribution_scope') or {}
    condition = declaration.get('condition') or ''
    stem = re.sub(r'^(?:面向|针对)', '', condition)
    stem = re.sub(r'的?相关方法$', '', stem)
    chapters = family.get('chapter_ids') or []
    if (family.get('version') == 'source-grounded-child-methods/1.0' and len(stem) >= 4 and chapters
            and all(stem in model['sections'][sid].get('title', '') for sid in chapters)):
        support['condition'] = condition
    if (_improvement_rows(table, declaration) and re.fullmatch(r'(?:代表性|各|所有|全部)?基线(?:方法|模型)?', declaration.get('baseline') or '')):
        start = _header_count(table)
        labels = {str(row[0]) for index, row in enumerate(table['matrix']) if index >= start and index not in _improvement_rows(table, declaration) and row and row[0]}
        if len(labels) >= 2:
            support['baseline'] = declaration['baseline']
    return support, sources


def _condition_in_prose(expected, clause, context):
    expected = expected.strip()
    if not expected:
        return True
    for marker, english in [('在线', 'online'), ('离线', 'offline')]:
        if marker in expected or re.search(r'\b' + english + r'\b', expected, re.I):
            negated = (r'(?:非|不(?:是|属于)?|未(?:在|处于)?)\s*' + marker
                       + r'|(?<![A-Za-z])(?:non|not)[\s-]+' + english + r'(?![A-Za-z])')
            if re.search(negated, context, re.I):
                return False
    for marker, opposite in [('在线', '离线'), ('离线', '在线')]:
        if marker in expected:
            if not (opposite not in clause and marker in context and (opposite not in context or marker in clause)):
                return False
            # Normalize only the category phrase. Explicit residual settings,
            # such as batch=64, still have to belong to this observation.
            expected = re.sub(marker + r'(?:服务)?(?:场景|模式|环境)?', '', expected)
    if re.search(r'\bonline\b', expected, re.I):
        if (re.search(r'\boffline\b|离线', context, re.I)
                or not re.search(r'\bonline\b|在线', context, re.I)):
            return False
        expected = re.sub(r'\bonline\b(?:\s+service)?(?:\s+(?:scenario|mode|setting))?', '', expected, flags=re.I)
    expected = expected.strip(' ，,；;')
    if not expected:
        return True
    if re.fullmatch(r'(?:公开|所有|全部|各个|多个)?数据集|(?:all|public|multiple)\s+data\s*sets?', expected, re.I):
        return True
    names = re.split(r'[，,；;]', expected)
    return all(_named(context, re.sub(r'^(?:相较于|相比于|相比|相对(?:于)?|对比)', '', name).strip())
               for name in names if name.strip())


def _prose_clause_context(clause, prefix, declaration):
    """Inherit only an explicit scope-only introduction in the same sentence."""
    if not prefix or _metric_match(prefix, declaration) or _NATIVE_MAXIMUM.search(prefix):
        return clause
    unit = declaration.get('unit') or ''
    suffix = r'(?:倍|[×x])' if unit in ('倍', '×', 'x', 'times', 'fold') else re.escape(unit)
    if suffix and re.search(r'\d\s*' + suffix, prefix, re.I):
        return clause
    starts = [match.start() for term in _metric_terms(declaration) if term
              for match in re.finditer(re.escape(term).replace(r'\ ', r'\s*'), clause, re.I)]
    if not starts:
        return clause
    def remainder(text):
        text = _key(text)
        values = [declaration.get(field) or '' for field in ('method', 'dataset', 'baseline')]
        values += re.split(r'[，,；;]', declaration.get('condition') or '')
        for value in sorted(values, key=len, reverse=True):
            if value:
                text = text.replace(_key(value), '')
        text = re.sub(r'(?:在线|离线)(?:服务)?(?:场景|模式|环境)?|\bonline\b(?:service)?(?:scenario|mode|setting)?', '', text)
        return re.sub(r'相较于|相比于|相比|相对于|相对|对比|以及|(?:在|于|时|下|的|其)|[\s，,：:；;]', '', text)
    # A different subject, an unexplained setting, or an earlier result cannot
    # silently lend the method/condition to the accepted numeric clause.
    if remainder(prefix) or remainder(clause[:min(starts)]):
        return clause
    return prefix + clause


def _prose_observation(block, declaration, *, maximum):
    text = block.get('text') or ''
    if len(text) > 6000:
        return None
    expected = _expected(declaration)
    if expected is None:
        return None
    clauses = []
    for sentence in re.split(r'[。！？!?；;]', text):
        clauses.extend((match[0], sentence[:match.start()]) for match in re.finditer(r'[^，,]+', sentence))
    for clause, prefix in clauses:
        if (maximum and not _NATIVE_MAXIMUM.search(clause)) or not _metric_match(clause, declaration):
            continue
        context = _prose_clause_context(clause, prefix, declaration)
        if any(declaration.get(field) and not _named(context, declaration[field])
               for field in ('method', 'dataset', 'baseline')):
            continue
        if not _condition_in_prose(declaration.get('condition') or '', clause, context):
            continue
        for part in re.split(r'[/／]', declaration.get('metric') or ''):
            if not _metric_match(clause, {**declaration, 'metric': part}):
                break
        else:
            unit = declaration.get('unit') or ''
            suffix = r'(?:倍|[×x])' if unit in ('倍', '×', 'x', 'times', 'fold') else re.escape(unit)
            if not suffix:
                continue
            for match in re.finditer(r'([-+]?\d+(?:\.\d+)?)\s*' + suffix, clause, re.I):
                if _NON_EXACT_PROSE_VALUE.search(clause[:match.start()]):
                    continue
                if _rounded(Decimal(match[1]), expected):
                    return {'block_id': block['block_id'], 'page': block['page'], 'section_id': block['section_id'],
                            'quote': context, 'value': match[1]}
    return None


def _prose_maximum_support(row, model, mapping):
    if not mapping:
        return None
    declaration = row['declaration']
    measured = []
    for evidence in row.get('evidence') or []:
        block = next((b for b in model.get('blocks') or [] if b.get('block_id') == evidence.get('block_id')), None)
        if (not block or evidence.get('page') != block.get('page') or not block.get('provenance')
                or evidence.get('quote') not in block.get('text', '')
                or not any(_under(model, block['section_id'], sid) for sid in mapping['experiment_section_ids'])):
            continue
        direct = _prose_observation(block, declaration, maximum=True)
        if direct:
            return {'kind': 'native_explicit_maximum', 'source': direct}
        observation = _prose_observation(block, declaration, maximum=False)
        if observation:
            measured.append(observation)
    # A chapter-local summary may supply only maximum semantics. Independent
    # selected experiment evidence must still supply this metric/value/unit.
    if not measured or not declaration.get('method'):
        return None
    for block in model.get('blocks') or []:
        section = model.get('sections', {}).get(block.get('section_id'), {})
        if (not re.search(r'本章小结|章节小结|\bchapter\s+summary\b', section.get('title') or '', re.I)
                or not _under(model, block['section_id'], mapping['chapter_id']) or not block.get('provenance')):
            continue
        summary = _prose_observation(block, declaration, maximum=True)
        if summary:
            return {'kind': 'native_chapter_summary_maximum', 'measurement': measured, 'summary': summary}
    return None


def _native_sources(table):
    cells = [cell for row in table.get('rows') or [] for cell in row.get('cells') or []]
    cells += table.get('native_spanning_cells') or []
    return [source for cell in cells for source in cell.get('native_spans') or []]


def _source_characters(sources):
    return {(source.get('block_index'), source.get('line_index'), source.get('span_index'), offset)
            for source in sources for offset in range(source.get('char_start', 0), source.get('char_end', 0))}


def _non_table_alternative(table, complete, model, mapping):
    """Classify an oversized text finder only when all extra source is prose.

    No source is removed from the model/verifier. Extra table/caption/unknown
    source, or any unaccounted row inside the closed native region, fails shut.
    """
    if (table.get('strategy') != 'text' or _safe_table(table)
            or table.get('page') != complete.get('page') or table.get('section_id') != complete.get('section_id')
            or not table.get('source_node_ids') or table['source_node_ids'] != complete.get('source_node_ids')
            or complete.get('strategy') != 'native_rules' or not _safe_table(complete)):
        return None
    box = complete.get('bbox')
    rules = complete.get('native_rulings') or []
    if (not isinstance(box, list) or len(box) != 4 or len(rules) < 3
            or abs(min(rule[1] for rule in rules) - box[1]) > 2
            or abs(max(rule[1] for rule in rules) - box[3]) > 2):
        return None
    known = _source_characters(_native_sources(complete))
    sources = _native_sources(table)
    all_characters = _source_characters(sources)
    if not known or len(known & all_characters) < len(known) * .5:
        return None
    extra = [source for source in sources if _source_characters([source]) - known]
    if not extra:
        return None
    owners = set()
    outside = set()
    chapters = (mapping.get('contribution_scope') or {}).get('chapter_ids') or [mapping['chapter_id']]
    for source in extra:
        bounds = source.get('bbox')
        if not isinstance(bounds, list) or len(bounds) != 4:
            return None
        if not (bounds[3] <= box[1] + .5 or bounds[1] >= box[3] - .5):
            return None
        options = []
        line_id = f'p{table["page"]-1}-b{source.get("block_index")}-l{source.get("line_index")}'
        for block in model.get('blocks') or []:
            if (block.get('page') != table['page'] or not block.get('block_id')
                    or not any(_under(model, block.get('section_id'), sid) for sid in chapters)):
                continue
            for provenance in block.get('provenance') or []:
                native = provenance.get('bbox')
                if (provenance.get('line_id') == line_id and isinstance(native, list) and len(native) == 4
                        and native[0]-2 <= bounds[0] <= bounds[2] <= native[2]+2
                        and native[1]-2 <= bounds[1] <= bounds[3] <= native[3]+2):
                    options.append(block)
                    break
        options = {block['block_id']: block for block in options}
        if len(options) != 1:
            return None
        block = next(iter(options.values()))
        kind, text = block.get('block_type'), block.get('text') or ''
        table_identity = re.compile(r'(?:表|\bTable\s*)\s*(\d+(?:\s*[.\-]\s*\d+)?)', re.I)
        known_identities = {_key(match[1]).replace('-', '.') for match in table_identity.finditer(complete.get('caption') or '')}
        if any(_key(match[1]).replace('-', '.') not in known_identities for match in table_identity.finditer(text)):
            return None
        same_caption = kind == 'Caption' and block.get('source_node_id') in complete['source_node_ids']
        section = model['sections'][block['section_id']]
        heading = ((kind == 'Heading' or block.get('source_node_id') in (section.get('heading_node_ids') or []))
                   and len(text) <= 120 and _key(text) in _key(section.get('title')))
        prose = (kind == 'Paragraph' and not block.get('table_id')
                 and (len(re.findall(r'[\u3400-\u9fff]', text)) >= 8 or len(re.findall(r'\b[A-Za-z]+\b', text)) >= 5)
                 and bool(re.search(r'[。！？，]|(?<!\d)[.!?](?!\d)|\b(?:the|this|these|results|analysis)\b', text, re.I)))
        if not (same_caption or heading or prose):
            return None
        owners.add(block['block_id'])
        if not any(_under(model, block.get('section_id'), sid) for sid in mapping['experiment_section_ids']):
            outside.add(block['block_id'])
    return {'table_id': table['table_id'], 'grounded_table_id': complete['table_id'],
            'extra_native_block_ids': sorted(owners), 'extra_source_characters': len(all_characters-known),
            'outside_experiment_native_block_ids': sorted(outside),
            'role': 'native_prose_outside_closed_table', 'source_preserved_for_verifier': True}


def _maximum_support(row, model, mapping):
    if not mapping:
        return None
    declaration = row['declaration']
    expected = _expected(declaration)
    if expected is None:
        return None
    selected = {(e.get('block_id'), e.get('page')) for e in row.get('evidence') or []}
    reference_sources = {}
    table_number = re.compile(r'(?:表|\bTable\s*)\s*(\d+\s*[.\-]\s*\d+)', re.I)
    for reference in mapping.get('table_reference_scope') or []:
        block = next((b for b in model.get('blocks') or [] if b.get('block_id') == reference.get('block_id')), None)
        native_table = next((t for t in model.get('tables') or [] if t.get('table_id') == reference.get('table_id')), None)
        cited = table_number.search(reference.get('quote') or '')
        caption = table_number.search((native_table or {}).get('caption') or '')
        if (not block or not native_table or not cited or not caption or not block.get('provenance')
                or _key(cited[1]).replace('-', '.') != _key(caption[1]).replace('-', '.')
                or reference.get('page') != block.get('page') or reference.get('section_id') != block.get('section_id')
                or not any(_under(model, block['section_id'], sid) for sid in mapping['experiment_section_ids'])):
            continue
        if any(e.get('block_id') == block['block_id'] and e.get('page') == block['page']
               and reference['quote'] in e.get('quote', '') and e['quote'] in block['text'] for e in row.get('evidence') or []):
            selected.add((native_table['table_id'], native_table['page']))
            reference_sources.setdefault(native_table['table_id'], []).append(block['block_id'])
    references = {ref['table_id'] for ref in mapping.get('table_reference_scope') or []}
    excluded_scope, views = [], []
    broad_baseline = bool(re.fullmatch(r'(?:代表性|各|所有|全部)?基线(?:方法|模型)?', declaration.get('baseline') or ''))
    ablation = re.compile(r'消融实验|消融分析|\bablation\b', re.I)
    for table in model.get('tables') or []:
        current, seen, boundary = table.get('section_id'), set(), None
        while current in model['sections'] and current not in seen:
            seen.add(current)
            section = model['sections'][current]
            if ablation.search(section.get('title') or ''):
                boundary = {'section_id': current, 'title': section['title']}
                break
            current = section.get('parent_id')
        if broad_baseline and boundary and not ablation.search(declaration.get('condition') or ''):
            excluded_scope.append({'table_id': table['table_id'], 'reason': 'native_ablation_scope_not_representative_baseline_class', **boundary})
            continue
        views.append(_caption_metric_view(table, model, declaration))
    tables = [table for table in views if (any(
        _under(model, table.get('section_id'), sid) for sid in mapping['experiment_section_ids'])
        or (table.get('table_id') in references and _under(model, table.get('section_id'), mapping['chapter_id'])))
        and _metric_columns(table, declaration)]
    from numeric_native_tables import preferred_table_alternatives
    tables = preferred_table_alternatives(tables)
    classified, comparisons = [], []
    for table in tables:
        role = next((role for complete in tables if complete is not table
                     for role in [_non_table_alternative(table, complete, model, mapping)] if role), None)
        if role:
            classified.append(role)
        else:
            comparisons.append(table)
    tables = comparisons
    if not any((table.get('table_id'), table.get('page')) in selected for table in tables):
        # Unselected known comparisons (including incomplete ones) cannot be
        # bypassed by a prose sentence repeating the claimed maximum.
        return None if tables else _prose_maximum_support(row, model, mapping)
    observations, used, selected_observations, covered_headers, upper_bounds, exact_values = [], [], [], [], [], []
    for table in tables:
        if not _safe_table(table):
            return None
        start = _header_count(table)
        if start <= 0 or start >= len(table['matrix']):
            return None
        headers, table_values = _headers(table), []
        relative_rows = _improvement_rows(table, declaration)
        support, sources = _table_scope_support(table, declaration, mapping, model)
        rows = relative_rows or range(start, len(table['matrix']))
        if relative_rows:
            # The native improvement row is the measured statistic; do not read
            # the preceding Recall/NDCG fractions as percentages. Missing native
            # result cells still make the purported complete comparison unclear.
            if any(_cell(table, ri, ci) is None for ri in range(start, len(table['matrix']))
                   for ci in _metric_columns(table, declaration)):
                return None
        for row_index in rows:
            in_scope = _row_scope(table, row_index, declaration, support)
            if in_scope is None:
                return None
            if not in_scope:
                continue
            for column in _metric_columns(table, declaration):
                cell = _cell(table, row_index, column)
                upper = re.fullmatch(r'\s*(?:<|≤|<=)\s*(.+)', cell or '')
                value = _measurement(upper[1] if upper else cell, headers[column], declaration)
                if value is None:
                    return None
                table_values.append(value)
                if upper:
                    upper_bounds.append({'table_id': table['table_id'], 'row_index': row_index,
                                         'column_index': column, 'quote': cell, 'upper_bound': str(value)})
                else:
                    exact_values.append(value)
                    if (table.get('table_id'), table.get('page')) in selected:
                        selected_observations.append(value)
                covered_headers.append(headers[column])
        if table_values:
            used.append({'table_id': table['table_id'], 'page': table['page'],
                         'rows_checked': len(table_values), 'metric_columns': _metric_columns(table, declaration),
                         'comparison_rows': list(relative_rows), 'scope_sources': sources,
                         'selected_reference_block_ids': reference_sources.get(table['table_id']) or [],
                         'metric_caption_sources': table.get('_native_metric_caption_sources') or []})
            observations.extend(table_values)
    if (not observations or not any(_rounded(value, expected) for value in selected_observations)
            or not _rounded(max(observations), expected)):
        return None
    common = [table.get('_native_metric_caption') or '' for table in tables]
    if any(not any(_metric_match(header, {**declaration, 'metric': part}) for header in covered_headers + common)
           for part in re.split(r'[/／]', declaration.get('metric') or '')):
        return None
    return {'kind': 'complete_native_maximum_comparison', 'tables': used,
            'comparison_count': len(observations), 'maximum': str(max(exact_values)),
            'comparison_upper_bound': str(max(observations)), 'upper_bound_cells': upper_bounds,
            'declared_precision': expected.as_tuple().exponent, 'non_table_alternatives': classified,
            'out_of_comparison_scope_tables': excluded_scope}


def _derived_ratio_support(row, model, mapping):
    """Recheck an explicit labeled latency ratio against one cited native row."""
    declaration = row['declaration']
    expected, method = _expected(declaration), declaration.get('method') or ''
    if (not mapping or expected is None or not method
            or declaration.get('unit') not in ('倍', '×', 'x', 'times', 'fold')
            or not re.search(r'加速|speedup|acceleration', declaration.get('metric') or '', re.I)):
        return None
    selected = {(e.get('block_id'), e.get('page')): e for e in row.get('evidence') or []}
    for table in model.get('tables') or []:
        evidence = selected.get((table.get('table_id'), table.get('page')))
        if (not evidence or not _safe_table(table)
                or not any(_under(model, table.get('section_id'), sid) for sid in mapping['experiment_section_ids'])):
            continue
        if any(declaration.get(field) and isinstance(table.get(field), str) and table[field].strip()
               and not _scope_value_matches(declaration[field], table[field])
               for field in ('dataset', 'method', 'baseline', 'condition')):
            continue
        view = _caption_metric_view(table, model, {'metric': 'latency'})
        caption = re.sub(r'(?<=[A-Za-z])-\s*(?=[A-Za-z])', '',
                         (view.get('_native_metric_caption') or '') + ' ' + (table.get('caption') or ''))
        if (not re.search(r'latency|runtime|execution time|时延|延迟|耗时', caption, re.I)
                or re.search(r'memory|accuracy|precision|recall|显存|内存|精度|准确率|召回', caption, re.I)):
            continue
        if re.search(r'attention|注意力', declaration.get('metric') or '', re.I) and not re.search(r'attention|注意力', caption, re.I):
            continue
        condition = declaration.get('condition') or ''
        phases = (r'prefill|预填充', r'decod(?:e|ing)|解码')
        if any(re.search(phase, condition, re.I) and re.search(other, caption, re.I)
               for phase, other in (phases, phases[::-1])):
            continue
        headers = _headers(table)
        denominators = [i for i, header in enumerate(headers) if _key(header) == _key(method)]
        if len(denominators) != 1 or headers.count(headers[denominators[0]]) != 1:
            continue
        denominator = denominators[0]
        for numerator, header in enumerate(headers):
            if (numerator == denominator or numerator == 0 or denominator == 0
                    or headers.count(header) != 1
                    or declaration.get('baseline') and _key(header) != _key(declaration['baseline'])):
                continue
            label = lambda text: re.escape(text).replace(r'\ ', r'\s*')
            expression = re.search(r'(?<![\d.])(' + _NUMBER.pattern + r')\s*/\s*(' + _NUMBER.pattern
                                   + r')\s*(?:≈|≃|~|=)\s*(' + _NUMBER.pattern + r')(?![\d.])', row['reason'], re.I)
            if not expression:
                continue
            prefix = row['reason'][:expression.start()]
            labels = re.search(r'(?<![A-Za-z0-9_-])' + label(header) + r'\s*/\s*'
                               + label(headers[denominator]) + r'\s*[=＝]\s*$', prefix, re.I)
            if not labels and (re.search(r'[A-Za-z][A-Za-z0-9_ -]*/\s*[A-Za-z][A-Za-z0-9_ -]*\s*[=＝]\s*$', prefix)
                               or not (_named(row['reason'], header) and _named(row['reason'], headers[denominator]))):
                continue
            operands = [Decimal(expression[i].replace('−', '-')) for i in (1, 2, 3)]
            if any(abs(value.adjusted()) > 100 for value in operands):
                continue
            for index in range(_header_count(table), len(table['matrix'])):
                if _row_scope(table, index, declaration) is False:
                    continue
                cells = [_cell(table, index, column) for column in (numerator, denominator)]
                row_label = _cell(table, index, 0)
                if (not row_label or not _named(declaration.get('condition') or declaration.get('text') or '', row_label)
                        or any(not value or not _NUMBER.fullmatch(value) for value in cells)
                        or [Decimal(value) for value in cells] != operands[:2]
                        or any(value <= 0 for value in operands[:2])
                        or any(value not in evidence.get('quote', '') for value in cells)):
                    continue
                with localcontext() as context:
                    context.prec = 120
                    value = operands[0] / operands[1]
                if not _rounded(value, operands[2]) or not _rounded(value, expected):
                    continue
                return {'kind': 'native_same_row_latency_ratio', 'table_id': table['table_id'], 'page': table['page'],
                        'numerator': {'row': index, 'column': numerator, 'header': header, 'value': cells[0]},
                        'denominator': {'row': index, 'column': denominator, 'header': headers[denominator], 'value': cells[1]},
                        'derived_value': str(value), 'declared_precision': expected.as_tuple().exponent,
                        'metric_caption': caption, 'metric_caption_sources': view.get('_native_metric_caption_sources') or []}
    return None


def conservative_guard(results, *, model=None, mappings=None):
    """Preserve legacy output absent context; admit only grounded semantics/coverage."""
    limitations = []
    for row in results:
        status = row['status']
        if status in ('inconclusive', 'execution_error'):
            continue
        reason, declaration = row['reason'], row['declaration']['text']
        if model is not None and mappings is not None:
            expected = _expected(row['declaration'])
            if expected is not None:
                clauses = re.split(r'[，,；;。]|且|而|同时|\band\b', declaration)
                target_clauses = [part for part in clauses if any(
                    Decimal(match.group().replace('−', '-')) == expected for match in _NUMBER.finditer(part))]
                if target_clauses:
                    declaration = ' '.join(target_clauses) + ' ' + str(row['declaration'].get('metric') or '')
        source = '\n'.join(e['quote'] for e in row['evidence'] if e.get('evidence_role') != 'experiment_context')
        gap = None
        mapping = _mapping(row, model, mappings)
        if status == 'consistent' and re.search(r'近似|舍入|四舍五入|概数|approximately|rounding', reason, re.I):
            values = [Decimal(v) for v in re.findall(r'\d+(?:\.\d+)?', str(row['declaration'].get('number', '')))]
            observed = [Decimal(v) for v in re.findall(r'(?<![\d.])\d+(?:\.\d+)?(?![\d.])', source)]
            if values and not all(any(v.quantize(Decimal(1).scaleb(expected.as_tuple().exponent), rounding=ROUND_HALF_UP) == expected for v in observed) for expected in values):
                proof = _derived_ratio_support(row, model, mapping)
                if proof:
                    row.setdefault('statistical_evidence', []).append(proof)
                else:
                    gap = _ROUNDING_GAP
        if gap:
            pass
        elif status == 'consistent' and _AVERAGE.search(declaration) and not _AVERAGE.search(source):
            proof = _average_support(row, model, mapping)
            if proof:
                row.setdefault('statistical_evidence', []).append(proof)
            else:
                gap = _AVERAGE_GAP
        if not gap and status == 'consistent' and _MAXIMUM.search(declaration):
            if model is not None and mappings is not None:
                proof = _maximum_support(row, model, mapping)
                if proof:
                    row.setdefault('statistical_evidence', []).append(proof)
                else:
                    gap = _MAXIMUM_GAP
            elif not _EXPLICIT_MAXIMUM.search(source):
                gap = _MAXIMUM_GAP
        if gap:
            row.update(model_status=status, model_reason=reason, status='inconclusive', reason=gap,
                       suggestion=row.get('suggestion') or _SUGGESTION)
            limitations.append({'declaration_id': row['declaration_id'], 'model_status': status, 'reason': gap})
    return limitations
