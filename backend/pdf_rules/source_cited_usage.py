"""Bind a borrowed visual to independent, source-cited content descriptions.

Bibliography membership is only a provenance constraint. A local physical
caption, a specific matching subject and concrete prose operations must also
agree. This module returns usage credits only; it never creates local numeric
references, changes labels, reads PDFs, or exempts every visual from a source.
"""
import re
from dataclasses import replace
from functools import lru_cache

from .model import DocumentIndex, Label
from .numbering import caption_match, normalize_label, normalize_text, toc_line_keys, is_toc_line
from .usage_paragraphs import usage_paragraphs

_CITE = re.compile(r'\[\s*(\d+(?:\s*[-–—,，、]\s*\d+)*)\s*\]')
_WORDS = re.compile(r'[A-Za-z][A-Za-z0-9_-]{2,}')
_GENERIC = {'figure', 'fig', 'table', 'overview', 'illustration', 'demonstration',
            'comparison', 'framework', 'model', 'models', 'method', 'methods',
            'the', 'and', 'with', 'from', 'for', 'into', 'its', 'input', 'output'}
_OPERATIONS = (
    r'使用|采用|\buses?\b', r'通过|\bthrough\b', r'定义|是指|\bdefines?\b',
    r'表示为|\brepresent(?:s|ed)?\b', r'计算|\bcomput(?:e|es|ing)\b',
    r'生成|\bgenerat(?:e|es|ing)\b', r'预测|\bpredict(?:s|ing)?\b',
    r'无需|\bwithout\b', r'降低|\breduc(?:e|es|ing)\b',
    r'作为|\bas\s+(?:a|the)\b', r'重采样|\bresampl(?:e|es|ing)\b',
    r'去噪|\bdenois(?:e|es|ing)\b', r'学习|\blearns?\b',
)
_HOOKS = ('计算', '扩散', '姿态', '价值函数', '奖励', '输入', '输出', '状态',
          '参数', '结构', '训练', '去噪', '重采样', '噪声', '延迟', '内存',
          'compute', 'diffusion', 'value', 'reward', 'input', 'output', 'state',
          'parameter', 'structure', 'training', 'denoise', 'sampling', 'latency', 'memory')

# Topic evidence is conjunctive. A method name and one common field cannot
# substitute for, for example, its training losses or its latency comparison.
# These are language aliases for content concepts, not method identifiers.
_TOPICS = (
    ('训练', 'training', 'train', 'trained'),
    ('损失', 'loss', 'losses'),
    ('消融', 'ablation', 'ablations'),
    ('实验', 'experiment', 'experiments', 'experimental'),
    ('时延', '延迟', 'latency', 'delay', 'delays'),
    ('内存', '存储', 'memory', 'storage'),
    ('扩散', 'diffusion'),
    ('多项式', 'multinomial'),
    ('离散', 'categorical', 'discrete'),
    ('准确率', '精度', 'accuracy', 'precision'),
    ('召回率', 'recall'),
    ('消耗', '开销', 'cost', 'costs', 'overhead'),
    ('输入', 'input', 'inputs'),
    ('输出', 'output', 'outputs'),
    ('状态', 'state', 'states'),
    ('参数', 'parameter', 'parameters'),
    ('结构', 'structure', 'structures', 'architecture', 'architectures'),
    ('姿态', 'pose', 'poses'),
    ('关节', 'joint', 'joints', 'articulated'),
    ('价值函数', 'value'),
    ('奖励', 'reward', 'rewards'),
    ('计算', 'compute', 'computes', 'computing', 'computation'),
    ('采样', 'sampling', 'sample', 'samples'),
    ('去噪', 'denoise', 'denoises', 'denoising'),
    ('噪声', 'noise'),
)
_TOPIC_FILLER = _GENERIC | {'of', 'in', 'on', 'at', 'to', 'by', 'a', 'an',
    'is', 'are', 'as', 'using', 'based', 'proposed', 'schematic', 'diagram',
    'diagrams', 'flow', 'chart', 'charts', 'definition', 'definitions'}
_CHINESE_FILLER = ('示意图', '流程图', '框架图', '方法对比', '模型结构',
                   '概览', '定义', '流程', '模型', '方法', '框架', '比较', '对比')


def _compact(text):
    return re.sub(r'\s+', '', normalize_text(text)).casefold()


def _citations(text):
    # Callers may mutate the returned set; cache only immutable parse results.
    return set(_citation_values(text))


@lru_cache(maxsize=32768)
def _citation_values(text):
    result = set()
    for match in _CITE.finditer(normalize_text(text)):
        for part in re.split(r'[,，、]', match.group(1)):
            endpoints = re.split(r'[-–—]', part)
            first = int(endpoints[0])
            last = int(endpoints[-1])
            # Malformed/huge numeric intervals cannot supply literature aliases.
            if 0 < first <= last and last-first <= 100:
                result.update(range(first, last+1))
    return frozenset(result)


def _key(line):
    return line.page_number, line.bbox


def _caption_rows(label, page, kind):
    """Follow actual styled PDF block rows, never neighbouring body prose."""
    initial = label.line
    anchors = [l for l in page.lines if l.bbox[1] >= initial.bbox[1]-1
               and l.bbox[3] <= initial.bbox[3]+1
               and (m := caption_match(normalize_text(l.text), kind))
               and normalize_label(m.group('number')) == label.number]
    first = min(anchors, key=lambda l: l.bbox[1]) if anchors else initial
    rows = [first]
    from .caption_context import body_font
    typical = body_font(page)
    ordered = sorted(page.lines, key=lambda l: (l.bbox[1], l.bbox[0]))
    for row in ordered:
        if row.bbox[1] <= first.bbox[1] or row in rows:
            continue
        previous = rows[-1]
        height = max(1, first.bbox[3]-first.bbox[1])
        if row.bbox[1]-previous.bbox[3] > max(15, height*1.5):
            break
        if caption_match(normalize_text(row.text), 'figure') or caption_match(normalize_text(row.text), 'table'):
            break
        if (first.block_id is None or row.block_id != first.block_id
                or row.source != first.source
                or (row.bold != first.bold and not (first.bold and typical
                    and first.font_size and first.font_size < typical*.95))
                or not first.font_size or not row.font_size
                or abs(row.font_size-first.font_size) > first.font_size*.1
                or abs(row.direction[0]) < .9):
            break
        aligned = abs(row.bbox[0]-first.bbox[0]) <= height*1.5
        centred = abs((row.bbox[0]+row.bbox[2]-first.bbox[0]-first.bbox[2])/2) <= height*1.5
        if not (aligned or centred):
            break
        rows.append(row)
    return rows


def _full_title(group, page, kind):
    rows = []
    for label in group:
        rows.extend(_caption_rows(label, page, kind))
    # Identity repair may retain only the canonical Chinese caption. Recover
    # its adjacent native translation from its own number and title typography.
    for line in page.lines:
        match = caption_match(normalize_text(line.text), kind)
        if not match or normalize_label(match.group('number')) != group[0].number:
            continue
        first = group[0].line
        opposite = line.text.lstrip().startswith(('图', '表')) != first.text.lstrip().startswith(('图', '表'))
        gap = max(first.bbox[1]-line.bbox[3], line.bbox[1]-max(r.bbox[3] for r in rows), 0)
        if (opposite and first.bold and line.bold and first.font_size and line.font_size
                and abs(first.font_size-line.font_size) <= first.font_size*.1 and gap <= 24):
            rows.extend(_caption_rows(Label(group[0].number, line, group[0].scope), page, kind))
    rows = sorted({_key(row): row for row in rows}.values(), key=lambda l: (l.bbox[1], l.bbox[0]))
    return ' '.join(row.text for row in rows), rows


def _primary_subjects(title):
    sentences = []
    for line in title.split('\n'):
        # The full text may include both languages; each typed caption opens a
        # primary subject. Source declarations terminate it and are not aliases.
        for match in re.finditer(r'(?:图|表|Figure|Table)\s*[A-Z]?\d+(?:[.\-]\d+)*', line, re.I):
            tail = line[match.end():]
            tail = re.split(r'[。.]|引自|摘自|改编自|转载自|Cited from|Taken from', tail, maxsplit=1, flags=re.I)[0]
            sentences.append(_CITE.sub('', tail))
    return sentences or [title]


def _subjects(title, kind):
    """Extract primary caption subjects, excluding source figure numbers."""
    primary = ' '.join(_primary_subjects(title))
    words = [w for w in _WORDS.findall(primary) if w.casefold() not in _GENERIC]
    proper = {w.casefold() for w in words if w[:1].isupper() or w.isupper()}
    phrases = {a.casefold()+' '+b.casefold() for a, b in zip(words, words[1:])
               if a.casefold() not in _GENERIC and b.casefold() not in _GENERIC}
    chinese = re.sub(r'（[^）]*）|\([^)]*\)', '', primary)
    chinese = re.sub(r'定义|示意图|概览|流程图|框架图|方法对比|计算流程|模型结构', '', chinese)
    runs = re.findall(r'[\u4e00-\u9fff]{6,}', chinese)
    return proper, phrases, runs


def _specific_subject(title, text, kind):
    proper, phrases, runs = _subjects(title, kind)
    lower = normalize_text(text).casefold()
    if proper:
        return any(re.search(r'(?<![a-z0-9_])'+re.escape(word)+r'(?![a-z0-9_])', lower) for word in proper)
    if any(re.search(r'\b'+re.escape(phrase).replace(r'\ ', r'\s+')+r'\b', lower) for phrase in phrases):
        return True
    body = _compact(text)
    return any(any(run[i:i+6] in body for i in range(len(run)-5)) for run in runs)


def _has_term(text, term):
    if term.isascii():
        return bool(re.search(r'(?<![a-z0-9_])'+re.escape(term)+r'(?![a-z0-9_])', text))
    return term in _compact(text)


def _source_clause_end(text, marker):
    stack = []
    for position, char in enumerate(text[:marker.start()]):
        if char == '(':
            stack.append(position)
        elif char == ')' and stack:
            stack.pop()
    enclosing_end = len(text)
    if stack:
        depth = 1
        for position in range(stack[-1] + 1, len(text)):
            if text[position] == '(':
                depth += 1
            elif text[position] == ')':
                depth -= 1
                if depth == 0:
                    enclosing_end = position + 1
                    break
    citation = _CITE.search(text, marker.end())
    if citation is None or citation.end() > enclosing_end:
        return enclosing_end
    clause_start = stack[-1] if stack else marker.end()
    depth = max(0, text[clause_start:citation.end()].count('(')
                - text[clause_start:citation.end()].count(')'))
    boundary_depth = 1 if stack else 0
    for position in range(citation.end(), enclosing_end):
        char = text[position]
        if char == '(':
            depth += 1
        elif char == ')':
            depth = max(0, depth - 1)
        elif depth == boundary_depth and char in '。；;!?！？':
            return position + 1
        elif depth == boundary_depth and char == '.':
            word = re.search(r'[a-z]+$', text[:position])
            initial = bool(word and len(word[0]) == 1)
            inside_token = (position > 0 and position + 1 < len(text)
                            and text[position - 1].isalnum()
                            and text[position + 1].isalnum())
            if not initial and not inside_token:
                return position + 1
    return enclosing_end


def _caption_content(title):
    """Remove source declarations while retaining later local caption text.

    A citation supplies a reliable end of the author/paper name, whose own
    abbreviations may contain periods. A completed source sentence can end
    inside parentheses; its later local description remains content evidence.
    An unbounded declaration remains conservative about its remaining text.
    """
    text = normalize_text(title).casefold()
    provenance = re.compile(
        r'引自|摘自|改编自|转载自|图源|表源|来源[:：]|'
        r'\bcited\s+from\b|\btaken\s+from\b|\bsource\s*:', re.I)
    parts = []
    cursor = 0
    while marker := provenance.search(text, cursor):
        parts.append(text[cursor:marker.start()])
        cursor = _source_clause_end(text, marker)
    parts.append(text[cursor:])
    return ' '.join(parts)


def _matching_topics(title, text):
    primary_parts = _primary_subjects(title)
    primary = normalize_text(' '.join(primary_parts)).casefold()
    body = normalize_text(text).casefold()
    # A later caption sentence can name the actual plotted quantity or
    # comparison. Keep those concept requirements even when the opening
    # sentence only names a model/framework; bibliographic provenance is
    # outside the local graphic's content description.
    content = _caption_content(title)
    for aliases in _TOPICS:
        # Measured quantities and experimental comparisons distinguish a
        # graphic from a generic architecture description. Mechanism details
        # in a later explanatory sentence can span several prose paragraphs;
        # they must not turn the already bound primary subject into an exact
        # wording requirement for one paragraph.
        distinctive_measure = aliases[0] in {
            '损失', '消融', '时延', '内存', '准确率', '召回率', '消耗'}
        if (any(_has_term(primary, alias) for alias in aliases)
                or distinctive_measure and any(_has_term(content, alias) for alias in aliases)):
            if not any(_has_term(body, alias) for alias in aliases):
                return False
    covered = {alias for aliases in _TOPICS for alias in aliases if alias.isascii()}
    # Retain unfamiliar English topic nouns too. The initial named subject and
    # uppercase identifiers can establish the model identity; additional nouns
    # still have to occur in its independent description. This is intentionally
    # conservative for unsupported synonyms rather than guessing correspondence.
    for part in primary_parts:
        words = [w for w in _WORDS.findall(part) if w.casefold() not in _TOPIC_FILLER]
        for position, word in enumerate(words):
            term = word.casefold()
            if term in covered or word.isupper() or (position == 0 and word[:1].isupper()):
                continue
            singular = term[:-1] if term.endswith('s') and not term.endswith('ss') else term
            if not (_has_term(body, term) or _has_term(body, singular)):
                return False
    # Unknown Chinese qualifiers remain exact content requirements too. Remove
    # known concepts only after checking their aliases, and visual-form words;
    # the remaining subject phrases cannot be replaced by a model name.
    residual = primary
    for aliases in _TOPICS:
        for alias in aliases:
            if not alias.isascii():
                residual = residual.replace(alias, ' ')
    for filler in _CHINESE_FILLER:
        residual = residual.replace(filler, ' ')
    residual = re.sub(r'[与和及的]', ' ', residual)
    if any(phrase not in _compact(body) for phrase in re.findall(r'[\u4e00-\u9fff]{2,}', residual)):
        return False
    return True


def _concrete_use(title, text, kind):
    if sum(bool(re.search(pattern, text, re.I)) for pattern in _OPERATIONS) < 2:
        return False
    if not _specific_subject(title, text, kind):
        return False
    if not _matching_topics(title, text):
        return False
    a, b = _compact(title), _compact(text)
    return any(_compact(hook) in a and _compact(hook) in b for hook in _HOOKS)


def _prose(lines, document):
    """Rejoin same-row native spans and an explicitly unfinished parenthesis.

    This preserves short term/citation fragments that are not standalone prose.
    Typography and geometry must agree; separated paragraphs are not concatenated.
    """
    rows = []
    for line, scope in sorted(lines, key=lambda item: (item[0].page_number,item[0].bbox[1],item[0].bbox[0])):
        if rows:
            previous, old_scope = rows[-1]
            centre = (line.bbox[1]+line.bbox[3])/2
            old_centre = (previous.bbox[1]+previous.bbox[3])/2
            if (scope == old_scope and line.page_number == previous.page_number
                    and line.source == previous.source and line.font_size and previous.font_size
                    and abs(line.font_size-previous.font_size) <= previous.font_size*.1
                    and abs(centre-old_centre) <= line.font_size*.4
                    and max(line.bbox[0]-previous.bbox[2],previous.bbox[0]-line.bbox[2],0) <= line.font_size*2):
                text = (line.text+' '+previous.text if line.bbox[0] < previous.bbox[0]
                        else previous.text+' '+line.text)
                rows[-1] = (replace(previous,text=text,
                    bbox=(min(previous.bbox[0],line.bbox[0]),min(previous.bbox[1],line.bbox[1]),
                          max(previous.bbox[2],line.bbox[2]),max(previous.bbox[3],line.bbox[3]))), scope)
                continue
        rows.append((line,scope))
    joined = []
    for line, scope in rows:
        if joined:
            previous, old_scope = joined[-1]
            text = normalize_text(previous.text)
            unfinished = text.count('(') > text.count(')')
            if (unfinished and ')' in normalize_text(line.text)
                    and scope == old_scope and line.page_number == previous.page_number
                    and line.source == previous.source and line.font_size and previous.font_size
                    and abs(line.font_size-previous.font_size) <= previous.font_size*.1
                    and 0 <= line.bbox[1]-previous.bbox[3] <= line.font_size*1.8
                    and abs(line.bbox[2]-previous.bbox[2]) <= line.font_size*2):
                joined[-1] = (replace(previous,text=previous.text+' '+line.text,
                    bbox=(min(previous.bbox[0],line.bbox[0]),previous.bbox[1],
                          max(previous.bbox[2],line.bbox[2]),line.bbox[3])), scope)
                continue
        joined.append((line,scope))
    return usage_paragraphs(joined,document)


def source_cited_groups(index: DocumentIndex, kind: str, groups: list[list[Label]]) -> set[int]:
    if kind not in {'figure', 'table'}:
        return set()
    pages = {p.number: p for p in index.document.pages}
    from .usage_scope import usage_scope_map, is_body_usage_scope, usage_epoch
    directories = toc_line_keys(index.document)
    scopes = usage_scope_map(index.document, directories)
    descriptors = []
    caption_keys = set()
    for other_kind, labels in (('figure', index.figures), ('table', index.tables)):
        for label in labels:
            page = pages.get(label.line.page_number)
            if page:
                _, rows = _full_title([label], page, other_kind)
                caption_keys.update(_key(row) for row in rows)
    for i, group in enumerate(groups):
        if not group or not is_body_usage_scope(scopes, group[0]):
            continue
        page = pages.get(group[0].line.page_number)
        if not page:
            continue
        title, rows = _full_title(group, page, kind)
        caption_keys.update(_key(row) for row in rows)
        citations = _citations(title)
        if citations:
            descriptors.append((i, group[0], title, citations))
    if not descriptors:
        return set()
    eligible = []
    for line in index.lines:
        page = pages[line.page_number]
        if (_key(line) in caption_keys or _key(line) in directories
                or is_toc_line(line.text) or not is_body_usage_scope(scopes, line)
                or line.bold or not line.text.strip()):
            continue
        # Actual raster extents own their text. Broad vector frames do not
        # establish that an independent body paragraph is graphic content.
        if any(box[0] <= line.bbox[0] and box[1] <= line.bbox[1]
               and line.bbox[2] <= box[2] and line.bbox[3] <= box[3]
               and box[3]-box[1] < page.height*.7 for box in (*page.images,*page.tables)):
            continue
        eligible.append((line, ('body', usage_epoch(scopes, line))))
    used = set()
    for line, (_, epoch) in _prose(eligible, index.document):
        citations = _citations(line.text)
        if not citations:
            continue
        candidates = [i for i, target, title, sources in descriptors
                      if abs(target.line.page_number-line.page_number) <= 1
                      and usage_epoch(scopes, target) == epoch
                      and sources & citations and _concrete_use(title, line.text, kind)]
        # A source-cited paragraph must distinguish physical objects, including
        # two same-name diagrams. Ambiguity supplies no usage credit.
        if len(candidates) == 1:
            used.add(candidates[0])
    return used
