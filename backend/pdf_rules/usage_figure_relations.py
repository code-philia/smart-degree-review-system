"""Bind concrete visual relations to independent prose for rule 15.

Source attribution is optional. Every credit records actual physical fields
and separate ink spans; competing physical groups keep attribution ambiguous.
No parser data or earlier rule decisions are changed.
"""
import math
import re

from .numbering import normalize_label
from .usage_text_cache import normalize_text
from .usage_figure_evidence import prepare_figure_usage, _prepared
from .usage_scope import usage_scope_map, usage_epoch, is_body_usage_scope
from .usage_network_relations import (network_native_candidate, network_relation_proposals,
                                     read_mode_identity, read_mode_content_candidate)
from .usage_transaction_relations import (transaction_conflict_title,transaction_content_candidate,
                                         transaction_relation_proposals)
from .usage_roadmap_relations import roadmap_native_candidate,roadmap_relation_proposals
from .usage_cipher_relations import substitution_permutation_title,cipher_relation_proposals
from .usage_residual_raster_relations import residual_response_title,residual_raster_relation_proposals
from .usage_call_stage_relations import call_stage_native_candidate,call_stage_relation_proposals
from .usage_named_protocol_relations import named_protocol_native_candidate,named_protocol_relation_proposals
from .usage_chronology_relations import chronology_native_candidate,chronology_title_candidate,chronology_relation_proposals
from .usage_comparison_relations import comparison_native_candidate,comparison_title_candidate,comparison_relation_proposals
from .usage_chapter_plan_relations import chapter_plan_title_candidate,chapter_plan_content_candidate,chapter_plan_relation_proposals
from .usage_dual_axis_relations import dual_axis_native_candidate,dual_axis_content_candidate,dual_axis_relation_proposals


_PHASES = {
    'deprivation': r'\bsleep\s+deprivation\b|睡眠剥夺',
    'recovery': r'\bsleep\s+recovery\b|睡眠恢复',
    'normal': r'\b(?:normal|nomal)\s+sleep\b|正常睡眠',
}
_BANDS = {
    'delta': (r'\bdelta\b|δ', r'深度睡眠|慢波睡眠|\bsleep\b'),
    'theta': (r'\btheta\b|θ', r'困倦|浅睡眠|\bdrowsiness\b'),
    'alpha': (r'\balpha\b|α', r'放松|闭眼|静息|\brest(?:ful)?\b|reflective'),
    'beta': (r'\bbeta\b|β', r'思维活跃|信息处理活跃|认知任务|\bactive\b|\bbusy\b'),
    'gamma': (r'\bgamma\b|γ', r'高级认知|感觉整合|problem\s+solving|concentration'),
}
_TERMS = {
    'spatial': r'\bspatial\b|空间',
    'spectral': r'\bspectral\b|频谱|频域',
    'temporal': r'\btemporal\b|时间|时域',
    'attention': r'\battention\b|注意力',
    'encoder': r'\bencoder\b|编码器',
    'expert': r'\bexperts?\b|专家',
    'gate': r'\bgated?\b|门控',
    'concat': r'\bconcat(?:enation|enate)?\b|拼接',
    'weighted': r'\bweighted\b|加权',
    'fusion': r'\bfusion\b|融合',
    'classifier': r'\bclass(?:i)?fier\b|分类器|类别.{0,8}预测',
    'linear': r'\blinear\b|线性',
    'softmax': r'(?<![a-z0-9_])softmax(?![a-z0-9_])',
}
_CLASSES = {
    'happy': r'\bhappy\b|快乐', 'sad': r'\bsad\b|悲伤',
    'neutral': r'\bneutral\b|中性', 'fear': r'\bfear\b|恐惧',
}
_FIGURE = re.compile(r'(?:图|Figures?|Fig\.?)\s*([A-Z]?\d+(?:[.\-–]\d+)*)', re.I)
_WORDS = dict(zip(('one','two','three','four','five','six','seven','eight','nine','ten',
                  '一','二','两','三','四','五','六','七','八','九','十'),
                 (1,2,3,4,5,6,7,8,9,10,1,2,2,3,4,5,6,7,8,9,10)))
_QUANTITY = re.compile(r'(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|[一二两三四五六七八九十])\s*'
                       r'(hours?|hrs?|h\b|小时|weeks?|周)', re.I)
_OPERATIONS = re.compile(r'提取|编码|映射|预测|融合|加权|拼接|冻结|采样|补齐|切片|掩码|分类|采集|重构|'
                         r'\b(?:encod\w*|extract\w*|project\w*|fuse\w*|predict\w*|sampl\w*|mask\w*)\b', re.I)


def _text(value):
    value = re.sub(r'[\x00-\x08\x0b-\x1f]', '', normalize_text(value)).casefold()
    return re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])','',value)


def _has(value, pattern):
    return bool(re.search(pattern, _text(value), re.I))


def _literal(value, name):
    pattern = r'(?<![a-z0-9])'+re.escape(name.casefold())+r'(?![a-z0-9])' if name.isascii() else re.escape(name)
    return _has(value, pattern)


def _terms(value):
    return {name for name, pattern in _TERMS.items() if _has(value, pattern)}


def _units(value):
    answer = set()
    for amount, unit in _QUANTITY.findall(_text(value)):
        number = float(_WORDS[amount]) if amount in _WORDS else float(amount)
        answer.add(('week' if unit.startswith('week') or unit == '周' else 'hour', number))
    return answer


def _center(field, axis):
    return (field['bbox'][axis]+field['bbox'][axis+2])/2


def _fields(context, supplied):
    fields = {i: [dict(field) for field in values] for i, values in context['native_fields'].items()}
    for ordinal, additions in (supplied or {}).items():
        for field in additions:
            try:
                recognition, detection = field['confidence'], field['detection_confidence']
                if (isinstance(recognition, bool) or isinstance(detection, bool)
                        or not math.isfinite(recognition) or not math.isfinite(detection)
                        or not .90 <= recognition <= 1 or not .80 <= detection <= 1):
                    continue
                box = field['bbox']
                if len(box) != 4 or not all(math.isfinite(x) for x in box) or box[2] <= box[0] or box[3] <= box[1]:
                    continue
                valid = any(area['page_number'] == field['page_number']
                            and area['bbox'][0]-.01 <= box[0] < box[2] <= area['bbox'][2]+.01
                            and area['bbox'][1]-.01 <= box[1] < box[3] <= area['bbox'][3]+.01
                            for area in context['regions'].get(ordinal, []))
                if valid and field.get('text', '').strip():
                    fields.setdefault(ordinal, []).append(dict(field))
            except (KeyError, TypeError, ValueError):
                continue
    return fields


def _continuation_passages(context):
    """Keep the original two ink anchors of a genuinely unfinished paragraph."""
    document=context.get('_document')
    if document is None:return []
    scopes=context.get('usage_scopes') or usage_scope_map(document)
    pages={p.number:p for p in document.pages}
    paragraphs={}
    for rows in context['body_passages']:
        for row in rows:
            paragraphs.setdefault(row.page_number,{})[(row.bbox,row.text)]=row
    areas=[area for regions in context['regions'].values() for area in regions]
    answer=[]
    for number,rows in paragraphs.items():
        if number+1 not in paragraphs:continue
        before=max(rows.values(),key=lambda row:row.bbox[3])
        after=min(paragraphs[number+1].values(),key=lambda row:row.bbox[1])
        if (before.source!=after.source or before.source!='native' or before.bold or after.bold
                or not before.font_size or not after.font_size
                or abs(before.font_size-after.font_size)>before.font_size*.05
                or before.direction!=after.direction or before.direction!=(1.0,0.0)
                or before.bbox[3]<before.page_height*.78 or before.bbox[2]<before.page_width*.75
                or after.bbox[1]>after.page_height*.45
                or not re.search(r'[\u4e00-\u9fff]$',before.text.strip())
                or not re.match(r'[\u4e00-\u9fff]',after.text.strip())
                or not is_body_usage_scope(scopes,before) or not is_body_usage_scope(scopes,after)
                or usage_epoch(scopes,before)!=usage_epoch(scopes,after)):
            continue
        blocked=False
        for page in (pages[number],pages[number+1]):
            for row in page.lines:
                if row.bbox in (before.bbox,after.bbox):continue
                if not row.bold or not row.text.strip() or row.source!='native':continue
                if not page.height*.09<row.bbox[1]<page.height*.92:continue
                between=(row.bbox[1]>before.bbox[3] if page.number==number else row.bbox[3]<after.bbox[1])
                if not between or (page.number,row.bbox) in context['caption_keys']:continue
                if any(area['page_number']==page.number and area['bbox'][0]<=row.bbox[0]
                       and area['bbox'][1]<=row.bbox[1] and row.bbox[2]<=area['bbox'][2]
                       and row.bbox[3]<=area['bbox'][3] for area in areas):continue
                blocked=True;break
        if not blocked:answer.append(([before,after],before.text+' '+after.text))
    return answer


def _relation_epoch(context,line_or_label):
    row=getattr(line_or_label,'line',line_or_label);key=(row.page_number,row.bbox)
    for name in ('label_epochs','body_epochs'):
        if key in context.get(name,{}):return context[name][key]
    return usage_epoch(context['usage_scopes'],row)


def _near_passages(context, groups, ordinal, distance=6, continuations=None):
    target = groups[ordinal][0]
    answer = []
    scopes=context.get('usage_scopes') or usage_scope_map(context['_document'])
    epoch=_relation_epoch(context,target)
    chapters=context.get('chapters',{})
    chapter=chapters.get((target.line.page_number,epoch))
    passages=[(rows,' '.join(row.text for row in rows)) for rows in context['body_passages']]
    passages.extend(_continuation_passages(context) if continuations is None else continuations)
    for rows,value in passages:
        if not rows or min(abs(row.page_number-target.line.page_number) for row in rows) > distance:
            continue
        if epoch<0 or any(_relation_epoch(context,row)!=epoch for row in rows):continue
        if chapter is not None and any(chapters.get((row.page_number,epoch))!=chapter for row in rows):continue
        if chapter is None and any(abs(row.page_number-target.line.page_number)>min(distance,4) for row in rows):continue
        refs = {normalize_label(m.group(1)) for m in _FIGURE.finditer(normalize_text(value))}
        if refs and target.number not in refs:
            continue
        answer.append((rows, value))
    return answer


def _pick(passages, predicate):
    options = [rows for rows, value in passages if predicate(value)]
    return min(options, key=lambda rows: sum(len(row.text) for row in rows)) if options else []


def _cycle(fields, passages):
    repetitions = {}
    for field in fields:
        name = _text(field['text']).strip()
        if re.fullmatch(r'[a-z][a-z0-9_-]{2,}', name):
            repetitions.setdefault(name, []).append(field)
    if not any(_has(f['text'], r'hours?\s+of|time|时间') for f in fields):
        return []
    if not any(_has(f['text'], r'depth|深度') for f in fields):
        return []
    for name, nodes in repetitions.items():
        if len(nodes) < 3 or max(_center(f,0) for f in nodes)-min(_center(f,0) for f in nodes) < 60:
            continue
        rows = _pick(passages, lambda text: _literal(text, name)
                     and _has(text, r'交替|alternat') and _has(text, r'周期|重复|recur|repeat|cyclic')
                     and _has(text, r'由浅入深|深度加深|深浅|depth|deep'))
        if rows:
            return rows
    return []


def _bands(fields, passages):
    labels = {name: [f for f in fields if _has(f['text'], pattern)]
              for name,(pattern,_) in _BANDS.items()}
    if not all(labels.values()):
        return []
    centers = {name:_center(values[0],1) for name,values in labels.items()}
    if len({round(y/8) for y in centers.values()}) < 4:
        return []
    rows = []
    verified = 0
    for name,(identity,state) in _BANDS.items():
        nearby = [f for f in fields if abs(_center(f,1)-centers[name]) <
                  min((abs(y-centers[name]) for other,y in centers.items() if other != name), default=50)*.7]
        body = _pick(passages, lambda value: _has(value,identity) and _has(value,state)
                     and _has(value, r'频|hz|波|wave'))
        if not body:
            return []
        rows.extend(body)
        verified += any(_has(f['text'],state) for f in nearby)
    return rows if verified >= 3 else []


def _phase_nodes(fields):
    return {name:[f for f in fields if _has(f['text'], pattern) and not _units(f['text'])]
            for name,pattern in _PHASES.items()}


def _stage_units(fields, passages):
    nodes = _phase_nodes(fields)
    if not all(nodes.values()):
        return []
    centers = {name:_center(values[0],0) for name,values in nodes.items()}
    if max(centers.values())-min(centers.values()) < 60:
        return []
    expected = {name:set() for name in nodes}
    for field in fields:
        units = _units(field['text'])
        if not units:
            continue
        name = min(centers, key=lambda key: abs(_center(field,0)-centers[key]))
        expected[name].update(units)
    if not all(expected.values()):
        return []
    collections = [f for f in fields if _has(f['text'], r'data\s+collection|数据采集')]
    if len(collections) < 3:
        return []
    rows = []
    for name,pattern in _PHASES.items():
        found = []
        for ink, value in passages:
            text = _text(value)
            starts = list(re.finditer(pattern+r'\s*(?:状态|条件|state|condition)\s*(?:指|为|则|是|refer|is)', text, re.I))
            for start in starts:
                clause = re.split(r'[。;；]', text[start.start():], maxsplit=1)[0]
                if expected[name] <= _units(clause):
                    found = ink
                    break
            if found:
                break
        if not found:
            return []
        rows.extend(found)
    order = sorted(centers, key=centers.get)
    def ordered(value):
        if not _has(value, r'依次|先后|sequen|in\s+order') or not _has(value,r'每.{0,15}(?:采集|状态)|each.{0,20}collect'):
            return False
        text = _text(value)
        positions = [re.search(_PHASES[name], text).start() if re.search(_PHASES[name],text) else -1 for name in order]
        return min(positions) >= 0 and positions == sorted(positions)
    ordered_rows = _pick(passages, ordered)
    return rows+ordered_rows if ordered_rows else []


def _views(fields, passages):
    physical = _terms(' '.join(f['text'] for f in fields))
    if not {'spatial','spectral','temporal','attention','linear','softmax'} <= physical:
        return []
    dimensions = {name:[f for f in fields if _has(f['text'],_TERMS[name])]
                  for name in ('spatial','spectral','temporal')}
    if len({round(_center(values[0],1)/8) for values in dimensions.values()}) < 3:
        return []
    predicates = (
        lambda text: {'spatial','spectral','temporal'} <= _terms(text) and _has(text,r'视角|views?'),
        lambda text: {'attention','encoder'} <= _terms(text) and _has(text,r'每.{0,10}视角|each.{0,10}view'),
        lambda text: {'weighted','fusion'} <= _terms(text) and _has(text,r'视角|views?'),
        lambda text: {'linear','classifier','softmax'} <= _terms(text),
    )
    collected = [_pick(passages,predicate) for predicate in predicates]
    return [row for rows in collected for row in rows] if all(collected) else []


def _experts(fields, passages):
    physical = _terms(' '.join(f['text'] for f in fields))
    ids = {m.group(1) for f in fields for m in re.finditer(r'\bexpert\s*(\d+)\b', _text(f['text']))}
    if len(ids) < 3 or not {'gate','encoder','weighted','fusion','classifier'} <= physical:
        return []
    predicates = (
        lambda text: _has(text,r'脑电|\beeg\b') and _has(text,r'眼动|\beye\b')
                     and {'concat','expert'} <= _terms(text),
        lambda text: {'expert','gate','weighted'} <= _terms(text)
                     and _has(text,r'输出|权重|output|weight'),
        lambda text: 'expert' in _terms(text) and _has(text,r'并行|多个|多专家|parallel')
                     and _has(text,r'建模|决策|model|decision'),
        lambda text: 'expert' in _terms(text) and _has(text,r'加权求和|weighted\s+sum')
                     and _has(text,r'输出|预测|output|predict'),
    )
    collected = [_pick(passages,predicate) for predicate in predicates]
    return [row for rows in collected for row in rows] if all(collected) else []


def _matrix(fields, passages):
    phases = _phase_nodes(fields)
    if not all(phases.values()):
        return []
    classes = {name:[f for f in fields if _has(f['text'],pattern)] for name,pattern in _CLASSES.items()}
    if sum(bool(values) for values in classes.values()) < 3:
        return []
    # Repeated labels on both axes distinguish a matrix from a bar chart.
    if sum(len(values)>=2 for values in classes.values()) < 3:
        return []
    nodes = {name:values[0] for name,values in phases.items()}
    titles = sorted((_center(field,0),name) for name,field in nodes.items())
    rows = _pick(passages, lambda text: _has(text,r'混淆矩阵|confusion\s+matrix')
                 and all(_has(text,pattern) for pattern in _PHASES.values())
                 and sum(_has(text,pattern) for pattern in _CLASSES.values()) >= 3)
    if not rows:
        return []
    for ink,value in passages:
        for name,phase in _PHASES.items():
            for category,pattern in _CLASSES.items():
                for match in re.finditer(r'(\d+(?:\.\d+)?)\s*[%％]', _text(value)):
                    prefix = _text(value)[max(0,match.start()-100):match.start()]
                    phase_mentions=[(m.start(),key) for key,p in _PHASES.items() for m in re.finditer(p,prefix,re.I)]
                    class_mentions=[(m.start(),key) for key,p in _CLASSES.items() for m in re.finditer(p,prefix,re.I)]
                    if (not phase_mentions or max(phase_mentions)[1]!=name
                            or not class_mentions or max(class_mentions)[1]!=category
                            or not _has(prefix[max(phase_mentions)[0]:],r'准确|accuracy')):
                        continue
                    exact = [f for f in fields if re.fullmatch(re.escape(match.group(1))+r'%?',_text(f['text']).strip())]
                    for cell in exact:
                        x = _center(cell,0)
                        panel = min(titles,key=lambda item:abs(x-item[0]))[1]
                        row_labels = [f for f in classes[category] if abs(_center(f,1)-_center(cell,1)) <= 12
                                      and f['bbox'][2] <= cell['bbox'][0]+4]
                        column_labels = [f for f in classes[category] if abs(_center(f,0)-x) <= 12
                                         and f['bbox'][1] >= cell['bbox'][3]-4]
                        if panel == name and row_labels and column_labels:
                            return rows+ink
    return []


_MATCHERS = {'repeated_state_axes': _cycle, 'wave_band_facets': _bands,
             'stage_duration_collection': _stage_units, 'three_view_encoding': _views,
             'gated_expert_fusion': _experts, 'classified_matrix_value': _matrix}


def relation_axis_tiles(context,fields,regions):
    """Measure vertical label strips beside numeric panels, never guess labels."""
    answer={}
    for ordinal,areas in regions.items():
        actual=_fields(context,{ordinal:fields.get(ordinal,[])}).get(ordinal,[])
        phases=_phase_nodes(actual)
        if not all(phases.values()):continue
        headings=sorted({_center(values[0],0) for values in phases.values()})
        if len(headings)<3 or min(b-a for a,b in zip(headings,headings[1:]))<30:continue
        for area in areas:
            b=area['bbox']
            for n,center in enumerate(headings):
                numeric=[f for f in actual if f['page_number']==area['page_number']
                         and re.fullmatch(r'\d+(?:\.\d+)?%?',_text(f['text']).strip())
                         and min(headings,key=lambda x:abs(x-_center(f,0)))==center]
                if len(numeric)<9:continue
                left=b[0] if n==0 else (headings[n-1]+center)/2
                right=min(f['bbox'][0] for f in numeric)-1
                if not 5<=right-left<=40:continue
                answer.setdefault(ordinal,[]).append(dict(page_number=area['page_number'],bbox=[left,b[1],right,b[3]]))
    return answer


def figure_relation_native_candidates(index, groups, regions, native_fields):
    """Cheap physical-kind gate; do not prepare every document's body prose."""
    answer = set()
    for ordinal,areas in regions.items():
        fields = native_fields.get(ordinal,[])
        value = ' '.join(field['text'] for field in fields)
        physical = _terms(value)
        if (all(_phase_nodes(fields).values())
                or _has(areas[0]['title'],r'波形|waveform')
                or {'spatial','spectral','temporal'} <= physical
                or {'expert','gate'} <= physical
                or network_native_candidate(fields)
                or read_mode_identity(areas[0]['title'])
                or transaction_conflict_title(areas[0]['title'])
                or roadmap_native_candidate(areas[0]['title'],fields)
                or substitution_permutation_title(areas[0]['title'])
                or residual_response_title(areas[0]['title'])
                or call_stage_native_candidate(areas[0]['title'],fields)
                or named_protocol_native_candidate(areas[0]['title'],fields)
                or chronology_native_candidate(areas[0]['title'],fields)
                or chronology_title_candidate(areas[0]['title'])
                or comparison_title_candidate(areas[0]['title']) and comparison_native_candidate(areas[0]['title'],fields)
                or chapter_plan_title_candidate(areas[0]['title'])
                or dual_axis_native_candidate(areas[0]['title'],fields)
                or _has(value,r'depth|深度') and _has(value,r'hours?\s+of|时间')):
            answer.add(ordinal)
    return answer


def figure_relation_candidates(index, groups, prepared_context=None):
    """Bound OCR to unresolved visual types with concrete local prose candidates."""
    context = _prepared(index,groups,prepared_context)
    candidates = set()
    continuations = _continuation_passages(context)
    passages = {}
    for ordinal,areas in context['regions'].items():
        fields = context['native_fields'].get(ordinal,[])
        text = ' '.join(f['text'] for f in fields)
        title = areas[0]['title']
        nearby = passages[ordinal] = _near_passages(context,groups,ordinal,6,continuations)
        body = ' '.join(value for _,value in nearby)
        physical = _terms(text)
        if (any(matcher(fields,nearby) for matcher in (_cycle,_stage_units,_views,_experts))
                or read_mode_content_candidate(title,nearby)
                or transaction_content_candidate(title,nearby)
                or _has(title,r'波形|waveform') and sum(_has(body,p) for p,_ in _BANDS.values()) >= 4
                or all(_phase_nodes(fields).values()) and _has(body,r'混淆矩阵|confusion\s+matrix')
                or {'spatial','spectral','temporal'} <= physical
                or {'expert','gate'} <= physical):
            candidates.add(ordinal)
    candidates.update(ordinal for ordinal,kind,rows,physical in network_relation_proposals(
        context,groups,lambda ordinal:passages[ordinal]))
    candidates.update(ordinal for ordinal,kind,rows,physical in transaction_relation_proposals(
        context,groups,lambda ordinal:passages[ordinal]))
    candidates.update(ordinal for ordinal,kind,rows,physical in roadmap_relation_proposals(
        context,groups,lambda ordinal:passages[ordinal]))
    candidates.update(ordinal for ordinal,kind,rows,physical in cipher_relation_proposals(
        context,groups,lambda ordinal:passages[ordinal]))
    candidates.update(ordinal for ordinal,kind,rows,physical in residual_raster_relation_proposals(
        context,groups,lambda ordinal:passages[ordinal]))
    candidates.update(ordinal for ordinal,kind,rows,physical in call_stage_relation_proposals(
        context,groups,lambda ordinal:passages[ordinal]))
    candidates.update(ordinal for ordinal,kind,rows,physical in named_protocol_relation_proposals(
        context,groups,lambda ordinal:passages[ordinal]))
    candidates.update(ordinal for ordinal,kind,rows,physical in chronology_relation_proposals(
        context,groups,lambda ordinal:passages[ordinal]))
    candidates.update(ordinal for ordinal,kind,rows,physical in comparison_relation_proposals(
        context,groups,lambda ordinal:passages[ordinal]))
    candidates.update(ordinal for ordinal in context['regions'] if chapter_plan_content_candidate(context,groups,ordinal))
    candidates.update(ordinal for ordinal in context['regions'] if dual_axis_content_candidate(context,groups,ordinal,lambda i:passages[i]))
    return candidates


def figure_relation_evidence(index, groups, graphic_evidence=None, prepared_context=None):
    context = _prepared(index,groups,prepared_context)
    fields = _fields(context,graphic_evidence)
    proposed = []
    continuations = _continuation_passages(context)
    passages = {}
    topologies = {}
    for ordinal,areas in context['regions'].items():
        nearby = passages[ordinal] = _near_passages(context,groups,ordinal,6,continuations)
        for kind,matcher in _MATCHERS.items():
            rows = matcher(fields.get(ordinal,[]),nearby)
            if not rows:
                continue
            unique = {(row.page_number,row.bbox,row.text):row for row in rows}
            proposed.append((ordinal,kind,unique))
    relations=network_relation_proposals(context,groups,lambda ordinal:passages[ordinal],fields)
    relations.extend(transaction_relation_proposals(context,groups,lambda ordinal:passages[ordinal],fields))
    relations.extend(roadmap_relation_proposals(context,groups,lambda ordinal:passages[ordinal],fields))
    relations.extend(cipher_relation_proposals(context,groups,lambda ordinal:passages[ordinal]))
    relations.extend(residual_raster_relation_proposals(context,groups,lambda ordinal:passages[ordinal]))
    relations.extend(call_stage_relation_proposals(context,groups,lambda ordinal:passages[ordinal]))
    relations.extend(named_protocol_relation_proposals(context,groups,lambda ordinal:passages[ordinal],fields))
    relations.extend(chronology_relation_proposals(context,groups,lambda ordinal:passages[ordinal],fields))
    relations.extend(comparison_relation_proposals(context,groups,lambda ordinal:passages[ordinal],fields))
    relations.extend(chapter_plan_relation_proposals(context,groups,lambda ordinal:passages[ordinal],fields))
    relations.extend(dual_axis_relation_proposals(context,groups,lambda ordinal:passages[ordinal],fields))
    for ordinal,kind,rows,physical in relations:
        unique = {(row.page_number,row.bbox,row.text):row for row in rows}
        proposed.append((ordinal,kind,unique))
        topologies[ordinal,kind]=physical
    used = {}
    for ordinal,kind,ink in proposed:
        # Shared concrete body ink cannot be silently attributed to two
        # diagrams of the same relation type, even across different numbers.
        if any(other != ordinal and other_kind == kind and set(ink)&set(other_ink)
               for other,other_kind,other_ink in proposed):
            continue
        used.setdefault(ordinal,dict(evidence_kind=kind,
            group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text)
                   for l in groups[ordinal]],
            full_title=context['regions'][ordinal][0]['title'],
            graphic_regions=context['regions'][ordinal], graphic_fields=fields.get(ordinal,[]),
            body_evidence=[dict(page_number=row.page_number,bbox=list(row.bbox),text=row.text,source=row.source)
                           for row in ink.values()],
            uniqueness_reason='Concrete physical relation/value binds independent prose; no other physical group of this kind claims the same body ink.'))
        if (ordinal,kind) in topologies and used[ordinal]['evidence_kind']==kind:
            used[ordinal]['physical_topology']=topologies[ordinal,kind]
    return used
