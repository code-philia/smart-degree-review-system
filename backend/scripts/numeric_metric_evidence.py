"""Bounded native metric context and arithmetic; neither function issues verdicts.

Callers must bind expressions/variables to quoted sources and decide comparison,
rounding and coverage semantics. No metric-specific arithmetic is assumed here.
"""
from __future__ import annotations

import ast
from collections.abc import Mapping
from decimal import Decimal, DecimalException, localcontext
import re


VERSION = 'numeric-metric-evidence/1.0'
_ALIASES = (
    ('d-mae', 'distance matrix mean absolute error', '距离矩阵平均绝对误差'),
    ('mae', 'mean absolute error', '平均绝对误差'),
    ('sse', 'sum of squared errors', 'sum of squares error', '平方误差和', '误差平方和'),
    ('mse', 'mean squared error', '均方误差'),
    ('rmse', 'root mean squared error', '均方根误差'),
    ('gauc', 'grouped auc', '分组auc', '加权平均auc'),
    ('auc', 'area under the roc curve', '曲线下面积'),
    ('relaimpr', 'relative improvement', '相对提升', '相对增益'),
    ('accuracy', '准确率'), ('precision', '精确率', '查准率'),
    ('recall', '召回率', '查全率'), ('f1', 'f1-score', 'f1分数'),
)
_METRIC_SECTION = re.compile(r'指标|度量|评价标准|评估标准|metric|measurement|evaluation criteria', re.I)
_PRELIMINARY = re.compile(r'相关概念|预备知识|基础知识|理论基础|背景知识|基础概念|preliminar|background|foundations', re.I)
_EXPERIMENT = re.compile(r'实验|结果|消融|对比|experiment|result|ablation|comparison', re.I)
_DEFINITION = re.compile(r'定义|计算(?:公式|方式|方法)|公式|表示|衡量|反映|评估指标|评价指标|defined|definition|computed|calculated|formula|denot|measur', re.I)
_AVERAGE = re.compile(r'平均|均值|mean|average', re.I)
_NUMBER = re.compile(r'(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z')
_FORMULA_INTRO = re.compile(r'计算公式|公式定义|形式化定义|定义如下|formula|defined\s+(?:as|by)', re.I)
_NAMED_TOKEN = re.compile(r'(?<![A-Za-z0-9_-])[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*(?![A-Za-z0-9_-])')


def _key(value):
    return re.sub(r'\s+', '', str(value or '')).casefold()


def _term_match(text, term):
    # Retain word boundaries for short ASCII aliases (MAE must not match D-MAE).
    pattern = re.escape(term).replace(r'\ ', r'\s*')
    if re.fullmatch(r'[a-z]{1,5}', term):
        pattern = r'(?<![a-zA-Z-])' + pattern + r'(?![a-zA-Z])'
    return re.search(pattern, text, re.I)


def _terms(declaration):
    metric = str(declaration.get('metric') or '').strip()
    if not metric:
        return []
    terms = {metric}
    for group in _ALIASES:
        if any(_term_match(metric, term) for term in group):
            terms.update(group)
    return sorted(terms, key=lambda term: (-len(term), term))


def _matches(text, terms):
    blocked = []
    for group in _ALIASES:
        for other in group:
            if other not in terms and any(_key(term) in _key(other) for term in terms):
                found = _term_match(text, other)
                if found:
                    blocked.append(found.span())
    matches = [(term, _term_match(text, term)) for term in terms]
    return [(term, match) for term, match in matches if match and not any(
        lo < match.end() and match.start() < hi for lo, hi in blocked)]


def _path(sections, sid):
    path, seen = [], set()
    while sid in sections and sid not in seen:
        seen.add(sid)
        path.append(sections[sid])
        sid = sections[sid].get('parent_id')
    return path


def _under(sections, sid, ancestor):
    return any(s.get('section_id') == ancestor for s in _path(sections, sid))


def _conflict(declaration, block, path):
    for field in ('dataset', 'method', 'baseline', 'condition'):
        expected = declaration.get(field)
        if not isinstance(expected, str) or not expected.strip():
            continue
        expected_terms = {_key(t) for t in re.split(r'[，,；;、|/]+', expected) if _key(t)}
        for scope in [block, *path]:
            value = scope.get(field)
            if isinstance(value, str) and value.strip() and _key(value) not in expected_terms:
                return True
        if field == 'dataset':
            # Native titles can explicitly name dataset scopes without metadata.
            titles = ' '.join(str(s.get('title') or '') for s in path)
            named = re.findall(r'\b(?:data[- ]?set)[-_ ]+[A-Za-z0-9][\w.-]*|[A-Za-z0-9][\w.-]*(?=\s*数据集)', titles, re.I)
            if named and not any(_key(name) in expected_terms for name in named):
                return True
        if field == 'method':
            # Named sibling-method headings are native scope even when the
            # source model has no optional method metadata. Generic metric
            # headings and shared preliminary definitions remain eligible.
            metric_words = {word.casefold() for term in _terms(declaration)
                            for word in re.findall(r'[A-Za-z]+', term)}
            scope_names = {_key(name) for field in ('dataset', 'condition')
                           for name in _NAMED_TOKEN.findall(str(declaration.get(field) or ''))}
            scope_names.update({'iid', 'ood'})
            for scope in path:
                named = [name for name in _NAMED_TOKEN.findall(str(scope.get('title') or ''))
                         if name.casefold() not in metric_words and _key(name) not in scope_names and (
                             re.fullmatch(r'[A-Z]{2,}[A-Z0-9]*', name)
                             or re.search(r'[a-z0-9][A-Z]|[-_]|[A-Za-z]\d', name))]
                if named:
                    if any(_key(name) not in expected_terms for name in named):
                        return True
                    break  # The nearest explicitly named native method owns this definition.
    return False


def _scope_kind(declaration, mapping, sections, block):
    sid = block.get('section_id')
    path = _path(sections, sid)
    if not path or _conflict(declaration, block, path):
        return None
    chapter = mapping['chapter_id']
    experiments = mapping.get('experiment_section_ids') or []
    if _under(sections, sid, chapter):
        if any(_under(sections, sid, experiment) for experiment in experiments):
            return 'mapped_experiment'
        local_path = [scope for scope in path if scope.get('section_id') != chapter
                      and _under(sections, scope.get('section_id'), chapter)]
        if (sid != chapter and not any(_under(sections, experiment, sid) for experiment in experiments)
                and not any(_METRIC_SECTION.search(str(scope.get('title') or '')) for scope in local_path)):
            return None
        # Same chapter definitions may precede experiments. Do not enter another
        # experimental/method result subtree merely because a metric is present.
        for scope in path:
            scope_id = scope.get('section_id')
            if scope_id == chapter:
                break
            if _EXPERIMENT.search(str(scope.get('title') or '')) and not any(
                    _under(sections, experiment, scope_id) for experiment in experiments):
                return None
        return 'mapped_chapter_definition'
    # Shared definitions are admitted only from explicitly named preliminary
    # metric sections; a definition in another method chapter remains excluded.
    if (_METRIC_SECTION.search(str(path[0].get('title') or ''))
            and any(_PRELIMINARY.search(str(s.get('title') or '')) for s in path[1:])
            and not any(_EXPERIMENT.search(str(s.get('title') or '')) for s in path)):
        return 'shared_metric_definition'
    return None


def _evidence_kinds(block, path, matches):
    text = block['text']
    kinds = []
    if _DEFINITION.search(text) or (_METRIC_SECTION.search(str(path[0].get('title') or ''))
                                    and (':' in text or '：' in text)):
        kinds.append('metric_definition')
    if re.search(r'[=＝]|∑|∏|Σ|Õ|Í', text):
        kinds.append('metric_formula')
    metric_section = bool(_METRIC_SECTION.search(str(path[0].get('title') or '')))
    if (_AVERAGE.search(text) and (block.get('block_type') in {'Table', 'Caption'}
                                   or re.search(r'[|\t]|表\s*\d|Table\s*\d', text, re.I)
                                   or (metric_section and len(text) <= 200))):
        kinds.append('metric_header')
    # A bare result "MAE = 5" is not a metric formula/definition. An equation
    # must have symbolic operations or surrounding definition language.
    if (kinds == ['metric_formula'] and not metric_section
            and not re.search(r'[/÷×∑∏ΣÕÍ]|\b[a-zA-Z]+\s*[+*\-]', text)):
        kinds = []
    return kinds


def _quote(block, start, end, kinds, scope_kind, matched_terms):
    text = block['text']
    clipped, cursor = [], 0
    for source in block.get('provenance') or []:
        native_start, native_end = source.get('node_text_start'), source.get('node_text_end')
        if type(native_start) is not int or type(native_end) is not int or native_start >= native_end:
            return None
        length = native_end - native_start
        lo, hi = max(start, cursor), min(end, cursor + length)
        if lo < hi:
            span = {**source, 'node_text_start': native_start + lo - cursor,
                    'node_text_end': native_start + hi - cursor,
                    'quote_text_start': lo - start, 'quote_text_end': hi - start}
            offsets = source.get('text_offsets')
            if (isinstance(offsets, (list, tuple)) and len(offsets) == 2
                    and all(type(offset) is int for offset in offsets)
                    and offsets[1] - offsets[0] == length):
                span['text_offsets'] = [offsets[0] + lo - cursor, offsets[0] + hi - cursor]
            clipped.append(span)
        cursor += length + 1  # source_model joins native provenance slices by \n.
    if not clipped or cursor - 1 != len(text):
        return None
    return {**block, 'text': text[start:end], 'quote': text[start:end], 'provenance': clipped,
            'block_text_start': start, 'block_text_end': end,
            'evidence_kinds': kinds, 'scope_kind': scope_kind, 'matched_metric_terms': matched_terms,
            'context_version': VERSION}


def metric_context(declaration, mapping, model, *, max_items=8, max_chars=6000):
    """Return bounded, exact native metric definitions, formulas and headers.

    Offsets named ``block_text_*`` address the model block; each returned
    provenance span retains clipped original node offsets and native geometry.
    These snippets establish context only, never complete comparison coverage.
    """
    if type(max_items) is not int or type(max_chars) is not int or not 1 <= max_items <= 64 or not 1 <= max_chars <= 48000:
        raise ValueError('invalid metric context limits')
    sections = model.get('sections') or {}
    if not isinstance(mapping, dict) or mapping.get('chapter_id') not in sections:
        return []
    terms = _terms(declaration)
    if not terms:
        return []
    blocks = model.get('blocks') or []
    selected = {}
    scopes = [_scope_kind(declaration, mapping, sections, block) for block in blocks]
    for index, block in enumerate(blocks):
        if not scopes[index] or block.get('block_type') == 'Heading' or not isinstance(block.get('text'), str):
            continue
        matches = _matches(block['text'], terms)
        if not matches:
            continue
        kinds = _evidence_kinds(block, _path(sections, block['section_id']), matches)
        if kinds:
            priority = 20 + (40 if _FORMULA_INTRO.search(block['text']) else 0)
            priority += 10 if 'metric_formula' in kinds else 0
            selected[index] = (kinds, [term for term, _ in matches], min(m.start() for _, m in matches), priority)
    # Definition/formula layout frequently breaks into adjacent native nodes,
    # including the top of the next physical page. Keep six bounded neighbors;
    # never skip over a different section, missing page, or conflicting scope.
    for index, (kinds, terms_found, _, priority) in list(selected.items()):
        directions = (1,) if re.search(r'(?:如下|as follows)\s*[:：]?\s*$', blocks[index]['text'], re.I) else (1, -1)
        for direction in directions:
            previous = blocks[index]
            for step in range(1, 7):
                neighbor = index + direction * step
                if not 0 <= neighbor < len(blocks):
                    break
                block = blocks[neighbor]
                if (not scopes[neighbor] or block.get('section_id') != previous.get('section_id')
                        or type(block.get('page')) is not int or type(previous.get('page')) is not int
                        or not 0 <= direction * (block['page'] - previous['page']) <= 1
                        or block.get('block_type') == 'Heading'):
                    break
                text = str(block.get('text') or '')
                symbolic = (0 < len(text) <= 160 and not re.search(r'[\u3400-\u9fff]', text)
                            and bool(re.search(r'[\w=＝+*/÷×−∑∏ΣÕÍ()\ud800-\udfff]', text)))
                anaphoric = (step == 1 and direction == 1 and 'metric_header' in kinds
                             and bool(re.match(r'\s*(?:该指标|此指标|其计算|it\b|this metric\b)', text, re.I))
                             and bool(_DEFINITION.search(text)))
                if not symbolic and not anaphoric:
                    break
                # A named different metric/equation starts a new group even on
                # the same baseline/page; do not inherit its formula fragments.
                if (re.search(r'[=＝]|定义|defined', text, re.I)
                        and re.search(r'[A-Za-z][A-Za-z-]{1,}\s*[=＝]', text)
                        and not _matches(text, terms)):
                    break
                neighbor_priority = priority if direction == 1 else priority - 5
                value = (['metric_definition' if anaphoric else 'formula_continuation'], terms_found, 0, neighbor_priority)
                if neighbor not in selected or selected[neighbor][3] < neighbor_priority:
                    selected[neighbor] = value
                previous = block
    items, remaining = [], max_chars
    ranked = sorted(selected, key=lambda index: (-selected[index][3], index))[:max_items]
    for index in sorted(ranked):
        kinds, terms_found, anchor, _ = selected[index]
        if len(items) >= max_items or remaining <= 0:
            break
        block = blocks[index]
        length = len(block['text'])
        start = max(0, min(anchor - remaining // 3, length - remaining)) if length > remaining else 0
        end = min(length, start + remaining)
        item = _quote(block, start, end, kinds, scopes[index], terms_found)
        if item:
            items.append(item)
            remaining -= end - start
    return items


def experimental_context(declaration, mapping, model, *, max_items=8, max_chars=6000):
    """Keep exact setup paragraphs shared by the mapped experimental branch."""
    sections = model.get('sections') or {}
    chapter = mapping.get('chapter_id')
    experiments = mapping.get('experiment_section_ids') or []
    if chapter not in sections or not experiments:
        return []
    ancestors = {s['section_id'] for sid in experiments for s in _path(sections, sid)}
    setup_title = re.compile(r'实验(?:环境|设置|配置|平台)|测试环境|数据集(?:介绍|描述)?$|'
                             r'experimental?\s+(?:setup|settings|environment)|implementation details|datasets?$', re.I)
    selected, remaining = [], max_chars
    for block in model.get('blocks') or []:
        path = _path(sections, block.get('section_id'))
        setup = next((s for s in path if setup_title.search(str(s.get('title') or '').strip())), None)
        text = block.get('text')
        if (not setup or not _under(sections, block.get('section_id'), chapter)
                or (setup['section_id'] not in ancestors and setup.get('parent_id') not in ancestors)
                or block.get('block_type') != 'Paragraph' or not isinstance(text, str) or len(text) < 30):
            continue
        if _conflict(declaration, block, path[:path.index(setup) + 1]):
            continue
        if len(selected) >= max_items or remaining <= 0:
            break
        item = _quote(block, 0, min(len(text), remaining), ['experimental_setup'], 'mapped_experiment_setup', [])
        if item:
            selected.append(item)
            remaining -= len(item['text'])
    return selected


def _decimal(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError('arithmetic inputs must be numeric scalars')
    raw = str(value)
    if len(raw) > 2048:
        raise ValueError('numeric input too long')
    try:
        result = Decimal(raw)
    except (DecimalException, ValueError) as exc:
        raise ValueError('invalid decimal input') from exc
    if not result.is_finite() or (result and abs(result.adjusted()) > 1000):
        raise ValueError('nonfinite or excessive arithmetic input')
    return result


def evaluate_expression(expression, variables):
    """Evaluate only Decimal +, -, *, / and bounded integral powers.

    No Python code is compiled or executed. Unsupported syntax, nonfinite
    scalars, unknown names and invalid/oversized operations raise ValueError.
    Caller supplies a source-defined expression; no metric conventions apply.
    """
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 2048 or not isinstance(variables, Mapping):
        raise ValueError('invalid arithmetic expression or variables')
    try:
        tree = ast.parse(expression.strip(), mode='eval')
    except (SyntaxError, RecursionError, ValueError) as exc:
        raise ValueError('invalid arithmetic expression') from exc
    if sum(1 for _ in ast.walk(tree)) > 128:
        raise ValueError('arithmetic expression too complex')
    values = {name: _decimal(value) for name, value in variables.items()}
    source = expression.strip()

    def visit(node, depth=0):
        if depth > 32:
            raise ValueError('arithmetic expression too deep')
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            token = ast.get_source_segment(source, node) or ''
            if not _NUMBER.fullmatch(token):
                raise ValueError('unsupported numeric literal')
            result = _decimal(token)
        elif isinstance(node, ast.Name):
            if node.id not in values:
                raise ValueError('unknown arithmetic variable')
            result = values[node.id]
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand, depth + 1)
            result = value if isinstance(node.op, ast.UAdd) else -value
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            left, right = visit(node.left, depth + 1), visit(node.right, depth + 1)
            if isinstance(node.op, ast.Add):
                result = left + right
            elif isinstance(node.op, ast.Sub):
                result = left - right
            elif isinstance(node.op, ast.Mult):
                result = left * right
            elif isinstance(node.op, ast.Div):
                result = left / right
            else:
                if right != right.to_integral_value() or abs(right) > 100:
                    raise ValueError('unsupported exponent')
                result = left ** int(right)
        else:
            raise ValueError('unsupported arithmetic syntax')
        if not result.is_finite() or (result and abs(result.adjusted()) > 1000):
            raise ValueError('nonfinite or excessive arithmetic result')
        return result

    try:
        with localcontext() as context:
            context.prec = min(4096, max(80, 2 * (len(source) + sum(len(str(value)) for value in values.values()))))
            return visit(tree.body)
    except (DecimalException, ArithmeticError, RecursionError) as exc:
        raise ValueError('invalid arithmetic operation') from exc
