"""An independently explained authorization-duration chart with two ratio axes.

Only original native numbers and original same-ROI vector vertices bind data.
Strict pixel fields can identify axis words, never invent plotted values.  The
caption supplies candidate metadata, not a result or usage statement.
"""
import hashlib
import json
import math
import re
from decimal import Decimal

from .usage_text_cache import normalize_text
from .numbering import normalize_label
from .usage_scope import usage_scope_identity

_NUM = re.compile(r'^\d+(?:\.\d+)?$')
_FIG = re.compile(r'(?:图|Figures?|Fig\.?)\s*([A-Z]?\d+(?:[.\-–]\d+)*)',re.I)
_BAD_ROLES = {'caption','figure_caption','table_caption','header','footer','toc','reference'}
_DENIED = re.compile(r'(?:并非|并不|并未|没有|未|不会|不能|不)(?:发生|显著|急剧|迅速|逐步|再|会|能)?(?:下降|降低|降至|增加|上升|达到|达到了|保持在)|(?:不|未)(?:解释|描述|对应)(?:本|该|此)?图')
_FOREIGN = re.compile(r'另一篇论文|其他论文|外文献|another\s+paper|(?:their|its)\s+(?:figure|chart)|来自.{0,12}(?:文献|论文)',re.I)
_FRAME = re.compile(r'(\d+|one|two|three|four|five|six|seven|eight|nine|ten|[一二两三四五六七八九十])\s*(?:个\s*)?(?:帧|frames?\b)',re.I)
_WORDS = dict(zip(('one','two','three','four','five','six','seven','eight','nine','ten','一','二','两','三','四','五','六','七','八','九','十'),(1,2,3,4,5,6,7,8,9,10,1,2,2,3,4,5,6,7,8,9,10)))
_UNAUTH = re.compile(r'未经授权|无令牌|no\s*[-–]?\s*token|unauthori[sz]ed',re.I)
_EFFECT = re.compile(r'有效性|效果度量|effectiveness|\bE\s*eff\b',re.I)
_ACCURACY = re.compile(r'准确率|准确性|准确度|accuracy',re.I)
_OWNER = re.compile(r'([A-Za-z][A-Za-z0-9_-]*)\s*(?:框架|模型|方法|网络|(?:framework|model|method|network)\b)',re.I)
_CHINESE_OWNER = re.compile(r'(?:^|[。；，,;\n])\s*(?:在|对|本文采用|本章采用)?([\u4e00-\u9fff]{2,12})(?:框架|模型|方法|网络)(?=的|在|采用|使用|表现|给出|报告|实现|研究|进行)')
_BARE_OWNER = re.compile(r'(?:^|[。；;\n])\s*([A-Za-z][A-Za-z0-9_-]{2,})\s*(?:采用|使用|研究|进行|实现|uses?\b|achieves?\b|shows?\b)',re.I)


def _text(value):
    value=normalize_text(value)
    return re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])','',value)


def _compact(value):return re.sub(r'\s+','',_text(value)).casefold()
def _center(field,axis):return (field['bbox'][axis]+field['bbox'][axis+2])/2

def _inside(box,area,tolerance=.01):
    return len(box)==4 and all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in box) and area[0]-tolerance<=box[0]<box[2]<=area[2]+tolerance and area[1]-tolerance<=box[1]<box[3]<=area[3]+tolerance


def dual_axis_title_candidate(title):
    value=_text(title)
    return bool(re.search(r'授权.{0,15}(?:时间片|时长)|(?:authoriz\w*|time\s+slice).{0,35}(?:duration|performance)|duration.{0,35}authoriz',value,re.I))


def _layout(fields):
    native=[f for f in fields if f.get('source')=='native' and _NUM.fullmatch(f.get('text','').strip())]
    if len(native)<12 or len({f['page_number'] for f in native})!=1:return None
    integers=[f for f in native if re.fullmatch(r'\d+',f['text'].strip())]
    rows=[]
    for f in integers:
        row=sorted((g for g in integers if abs(_center(f,1)-_center(g,1))<=1),key=lambda g:_center(g,0))
        values=[int(g['text']) for g in row]
        if len(row)>=3 and len(set(values))==len(values) and all(b>a for a,b in zip(values,values[1:])):rows.append(row)
    if not rows:return None
    row=max(rows,key=len);xs=[_center(f,0) for f in row]
    candidates=[]
    for side in ('left','right'):
        pool=[f for f in native if (f['bbox'][2]<xs[0]-3 if side=='left' else f['bbox'][0]>xs[-1]+3) and f['bbox'][3]<row[0]['bbox'][1]+4 and '.' in f['text']]
        columns=[]
        for f in pool:
            column=sorted((g for g in pool if abs(_center(g,0)-_center(f,0))<=1),key=lambda g:_center(g,1))
            vals=[float(g['text']) for g in column]
            if len(column)>=3 and all(0<=v<=1 for v in vals) and all(b<a for a,b in zip(vals,vals[1:])):columns.append(column)
        if not columns:return None
        column=max(columns,key=len);a,b=column[0],column[-1]
        slope=(_center(b,1)-_center(a,1))/(float(b['text'])-float(a['text']));intercept=_center(a,1)-slope*float(a['text'])
        if slope>=0 or any(abs(_center(f,1)-(intercept+slope*float(f['text'])))>1 for f in column):return None
        candidates.append(dict(side=side,x=_center(a,0),slope=slope,intercept=intercept,ticks=column))
    return dict(x_fields=row,x_values=[int(f['text']) for f in row],x_centers=xs,axes=candidates)


def dual_axis_native_candidate(title,fields):
    return dual_axis_title_candidate(title) and _layout(fields) is not None


def _native_fields(context,ordinal,fields):
    document=context.get('_document');areas=context['regions'].get(ordinal,[])
    if document is None or len(areas)!=1:return []
    area=areas[0];page=next((p for p in document.pages if p.number==area['page_number']),None)
    if page is None:return []
    original={(row.text,tuple(row.bbox)) for row in page.lines if row.source=='native'}
    return [dict(f) for f in fields if f.get('source')=='native' and f.get('page_number')==page.number and _inside(f.get('bbox',()),area['bbox']) and (f.get('text'),tuple(f['bbox'])) in original]


def _observed_fields(context,ordinal,fields,digest):
    area=context['regions'][ordinal][0]
    physical=dict(pdf_sha=digest,page_number=area['page_number'],bbox=list(area['bbox']))
    identity=hashlib.sha256(json.dumps(physical,ensure_ascii=True,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    native=_native_fields(context,ordinal,fields);answer=list(native)
    for f in fields:
        if f.get('source')!='usage_graphic_ocr_cpu':continue
        try:
            if (f.get('pdf_sha')!=digest or f.get('region_identity')!=identity or f.get('page_number')!=area['page_number'] or not _inside(f['bbox'],area['bbox'])):continue
            confidence=f['confidence'];detection=f['detection_confidence']
            if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in (confidence,detection)):continue
            if not .90<=confidence<=1 or not .80<=detection<=1:continue
            if f.get('text','').strip():answer.append(dict(f))
        except (KeyError,TypeError,ValueError):continue
    return answer


def _metric(value):
    if _UNAUTH.search(value) and _ACCURACY.search(value):return 'unauthorized_accuracy'
    if _EFFECT.search(value):return 'effectiveness'
    return None


def _physical(context,ordinal,fields,pdf,digest):
    areas=context['regions'].get(ordinal,[])
    if len(areas)!=1:return None
    area=areas[0];actual=_observed_fields(context,ordinal,fields,digest);native=[f for f in actual if f['source']=='native'];layout=_layout(native)
    if layout is None:return None
    # The actual x-axis must name a count of authorization frames, not seconds.
    xlabels=[f for f in actual if re.search(r'授权.{0,12}帧数|authoriz\w*.{0,20}frames?',_compact(f['text']),re.I) and f['bbox'][1]>=min(g['bbox'][1] for g in layout['x_fields']) and layout['x_centers'][0]<_center(f,0)<layout['x_centers'][-1]]
    if not xlabels:return None
    for axis in layout['axes']:
        words=[f for f in actual if (f['bbox'][2]<axis['x'] if axis['side']=='left' else f['bbox'][0]>axis['x']) and min(g['bbox'][1] for g in axis['ticks'])<=_center(f,1)<=max(g['bbox'][3] for g in axis['ticks']) and _metric(f['text'])]
        identities={_metric(f['text']) for f in words}
        if len(identities)!=1:return None
        axis['metric']=next(iter(identities));axis['word_fields']=words
    if {a['metric'] for a in layout['axes']}!={'unauthorized_accuracy','effectiveness'}:return None
    page=pdf[area['page_number']-1];page.set_rotation(0)
    paths=[]
    for drawing in page.get_drawings():
        color=drawing.get('color');items=drawing['items']
        rectangle=list(drawing['rect'])
        if not color or 's' not in drawing.get('type','') or not _inside(rectangle,area['bbox']):continue
        # A complete changing stroke across the observed x domain is main
        # chart content even if gray or curved.  It cannot silently disappear
        # while two other series supply the known relationship. Horizontal
        # grids and compact glyph/legend strokes do not meet this geometry.
        span=(abs(rectangle[0]-layout['x_centers'][0])<=1
              and abs(rectangle[2]-layout['x_centers'][-1])<=1
              and rectangle[3]-rectangle[1]>2)
        if not span:continue
        if max(color)-min(color)<.2:return None
        if len(items)!=len(layout['x_values'])-1 or any(item[0]!='l' for item in items):return None
        vertices=[list(items[0][1])]+[list(item[2]) for item in items]
        if any(list(a[2])!=list(b[1]) for a,b in zip(items,items[1:])):return None
        if any(abs(point[0]-x)>1 for point,x in zip(vertices,layout['x_centers'])):return None
        paths.append(dict(color=list(color),vertices=vertices,dashes=drawing.get('dashes'),rect=list(drawing['rect'])))
    if len(paths)!=2 or paths[0]['color']==paths[1]['color']:return None
    data=[f for f in native if re.fullmatch(r'\d+\.\d{2,6}',f['text'].strip()) and layout['x_centers'][0]-2<=_center(f,0)<=layout['x_centers'][-1]+2]
    bound=[]
    for path in paths:
        options=[]
        for axis in layout['axes']:
            values=[];labels=[]
            for point in path['vertices']:
                labels_here=[f for f in data if abs(_center(f,0)-point[0])<=1 and abs(_center(f,1)-point[1])<=15 and abs(axis['intercept']+axis['slope']*float(f['text'])-point[1])<=1]
                if len(labels_here)!=1:break
                f=labels_here[0];values.append(float(f['text']));labels.append(f)
            else:options.append(dict(metric=axis['metric'],axis=axis['side'],values=values,native_data_labels=labels,axis_words=axis['word_fields'],axis_ticks=axis['ticks'],vector_path=path))
        if len(options)!=1:return None
        bound.append(options[0])
    if {entry['metric'] for entry in bound}!={'unauthorized_accuracy','effectiveness'}:return None
    return dict(kind='same_x_dual_ratio_series',page_number=area['page_number'],bbox=list(area['bbox']),pdf_sha=digest,x_values=layout['x_values'],x_fields=layout['x_fields'],x_axis_words=xlabels,series=bound)


def _owner(name):
    name=re.sub(r'^(?:本文|本章|本节|本研究|我们)(?:采用|使用|研究|在|对)?','',name)
    return re.sub(r'^(?:在|对|通过)','',name).casefold()


def _owners(value):
    return {_owner(m.group(1)) for m in list(_OWNER.finditer(value))+list(_CHINESE_OWNER.finditer(value))+list(_BARE_OWNER.finditer(value)) if _owner(m.group(1)) not in {'本','该','这种','上述','此','our','this'}}


def _independent(context,groups,ordinal,nearby):
    document=context.get('_document');scopes=context.get('usage_scopes') or context.get('usage_scope_map');target=groups[ordinal][0]
    if document is None or scopes is None:return []
    state=usage_scope_identity(scopes,target)
    if state[0]!='body' or state[1]<0:return []
    chapter=context.get('chapters',{}).get((target.line.page_number,state[1]));areas=[a for values in context['regions'].values() for a in values];eligible={}
    def safe(row):
        if row.source!='native' or row.role in _BAD_ROLES or row.bold or usage_scope_identity(scopes,row)!=state:return False
        if re.fullmatch(r'\s*[（(]\d+[）)]\s*[^。；，,;]{1,28}',row.text):return False
        if abs(row.page_number-target.line.page_number)>2:return False
        if chapter is not None and context['chapters'].get((row.page_number,state[1]))!=chapter:return False
        if (row.page_number,row.bbox) in context.get('caption_keys',set()) or not row.page_height*.09<row.bbox[1]<row.bbox[3]<row.page_height*.92:return False
        return not any(a['page_number']==row.page_number and _inside(row.bbox,a['bbox'],1) for a in areas)
    for anchors,value in nearby(ordinal):
        for anchor in anchors:
            if not safe(anchor):continue
            page=next((p for p in document.pages if p.number==anchor.page_number),None)
            if page is None:continue
            originals=[row for row in page.lines if safe(row) and _inside(row.bbox,anchor.bbox,1) and _compact(row.text) in _compact(anchor.text)]
            blocks={r.block_id for r in originals if r.block_id is not None}
            for row in page.lines:
                if safe(row) and (row in originals or row.block_id is not None and row.block_id in blocks):eligible[row.page_number,row.bbox,row.text]=row
    ordered=sorted(eligible.values(),key=lambda row:(row.page_number,row.bbox[1],row.bbox[0]));paragraphs=[]
    for row in ordered:
        if not paragraphs:
            paragraphs.append([row]);continue
        prev=paragraphs[-1][-1]
        same=(row.page_number==prev.page_number and 0<row.bbox[1]-prev.bbox[1]<=32
              and row.bbox[0]-prev.bbox[0]<1.5*row.font_size)
        continuation=(row.page_number==prev.page_number+1 and prev.bbox[3]>=prev.page_height*.78
                      and prev.bbox[2]>=prev.page_width*.75 and row.bbox[1]<=row.page_height*.45
                      and re.search(r'[\u4e00-\u9fff]$',prev.text.strip()) and re.match(r'[\u4e00-\u9fff]',row.text.strip()))
        if same or continuation:paragraphs[-1].append(row)
        else:paragraphs.append([row])
    answer=[]
    for rows in paragraphs:
        value=''.join(row.text for row in rows)
        refs={normalize_label(m.group(1)) for m in _FIG.finditer(_text(value))}
        if refs-{normalize_label(target.number)} or _DENIED.search(_compact(value)) or _FOREIGN.search(_text(value)):continue
        answer.append((rows,_text(value)))
    return answer


def _amount(value):return _WORDS.get(value.casefold(),int(value) if value.isdigit() else None)


def _configuration(value,xvalues):
    compact=_compact(value)
    if not re.search(r'授权(?:时间片|帧数)',compact) or not re.search(r'总帧数不变|totalframes?.{0,8}(?:fixed|constant)',compact):return False
    transition=re.search(r'(?:授权帧数|authorizedframes?).{0,8}从?'+str(xvalues[-1])+r'(?:帧|frames?).{0,18}(?:减少至|降至|to)'+str(xvalues[0])+r'(?:帧|frames?)',compact,re.I)
    if not transition:return False
    parts=re.search(r'(?:包含|containing)(\d+)(?:帧|frames?).{0,30}(?:前|first)(\d+)(?:帧|frames?).{0,20}授权.{0,25}(?:剩余|remaining)的?(\d+)(?:帧|frames?)',compact,re.I)
    return bool(parts and int(parts[1])==int(parts[2])+int(parts[3]) and int(parts[2])==xvalues[-1])


def _slots(value):
    value=_text(value);compact=_compact(value);slots=[]
    for match in re.finditer(r'(?<![\d.])(\d+(?:\.\d+)?)(%)?',compact):
        raw=match[1];percent=bool(match[2]);v=float(raw)
        if not percent and (v>1 or '.' not in raw):continue
        if not percent and re.match(r'(?:毫秒|秒|帧|个|次|ms\b|seconds?\b|frames?\b)',compact[match.end():],re.I):continue
        prefix=compact[:match.start()];window=prefix[max(prefix.rfind('。'),prefix.rfind('；'),prefix.rfind(';'))+1:]
        counts=list(_FRAME.finditer(window))
        if not counts:continue
        count=counts[-1];x=_amount(count[1])
        if x is None:continue
        metric_mentions=[]
        for m in _UNAUTH.finditer(prefix):metric_mentions.append((m.start(),'unauthorized_accuracy'))
        for m in _EFFECT.finditer(prefix):metric_mentions.append((m.start(),'effectiveness'))
        if not metric_mentions:continue
        metric=max(metric_mentions)[1]
        if metric=='unauthorized_accuracy' and not _ACCURACY.search(prefix[max(0,match.start()-160):]):continue
        if not re.search(r'保持在|降至|达到(?:了)?|最大值|remains?|falls?to|reaches?',window[count.end():],re.I):continue
        slots.append(dict(metric=metric,x=x,body_value=str(Decimal(raw)/100 if percent else Decimal(raw)),body_printed=raw+('%' if percent else ''),sentence=window+match.group()))
    return slots


def _body(context,groups,ordinal,nearby,xvalues,physical=None):
    paragraphs=_independent(context,groups,ordinal,nearby)
    if not paragraphs:return None
    # The local experiment's frame partition and varied endpoints are defined
    # independently, and are not borrowed from the figure caption.
    selected=[(rows,value) for rows,value in paragraphs if re.search(r'授权(?:时间片|帧数)',_compact(value)) and re.search(r'包含\d+帧|授权帧数|authorizedframes?',_compact(value),re.I) and '%' not in value]
    config_text=' '.join(value for rows,value in selected)
    if not _configuration(config_text,xvalues):return None
    owners=_owners(config_text)
    if len(owners)!=1:return None
    owner=next(iter(owners));proof=[r for rows,value in selected for r in rows]
    results=[]
    for rows,value in paragraphs:
        if not _UNAUTH.search(value) and not _EFFECT.search(value):continue
        if _owners(value)-{owner}:continue
        for slot in _slots(value):results.append((slot,rows,value))
    if physical is None:
        required={('unauthorized_accuracy',xvalues[0]),('unauthorized_accuracy',xvalues[-1]),('effectiveness',xvalues[-1])}
        if not required<={(s['metric'],s['x']) for s,_,_ in results}:return None
        return dict(rows=proof,owner=owner,slots=[s for s,_,_ in results])
    required=[]
    series={s['metric']:s for s in physical['series']}
    if (series['unauthorized_accuracy']['values'][-1]>=series['unauthorized_accuracy']['values'][0]
            or series['effectiveness']['values'][-1]<=series['effectiveness']['values'][0]):return None
    for metric,x in [('unauthorized_accuracy',xvalues[0]),('unauthorized_accuracy',xvalues[-1]),('effectiveness',xvalues[-1])]:
        pos=xvalues.index(x);observed=series[metric]['native_data_labels'][pos]['text'];exact=Decimal(observed);precision=Decimal(1).scaleb(exact.as_tuple().exponent)/2
        candidates=[(s,rows,text) for s,rows,text in results if s['metric']==metric and s['x']==x and abs(Decimal(s['body_value'])-exact)<=precision]
        if len({s['body_value'] for s,rows,text in candidates})!=1:return None
        s,rows,text=candidates[0]
        if metric=='unauthorized_accuracy' and not re.search(r'准确(?:性|率|度).{0,14}(?:急剧|显著)?(?:下降|降低)|accuracy.{0,20}(?:falls?|decreases?)',_compact(text),re.I):return None
        if metric=='effectiveness' and not re.search(r'(?:效果度量|有效性).{0,30}(?:迅速|显著)?(?:增加|上升)|effectiveness.{0,35}increases?',_compact(text),re.I):return None
        required.append(dict(**s,graphic_value=float(exact),graphic_printed=observed,body=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text) for r in rows]));proof.extend(rows)
    return dict(rows=list({(r.page_number,r.bbox,r.text):r for r in proof}.values()),owner=owner,slots=required)


def dual_axis_content_candidate(context,groups,ordinal,nearby):
    areas=context.get('regions',{}).get(ordinal,[])
    if len(areas)!=1 or not dual_axis_title_candidate(areas[0]['title']):return False
    layout=_layout(_native_fields(context,ordinal,context['native_fields'].get(ordinal,[])))
    return bool(layout and _body(context,groups,ordinal,nearby,layout['x_values']))


def dual_axis_relation_proposals(context,groups,nearby,fields=None):
    actual=context.get('native_fields',{}) if fields is None else fields;document=context.get('_document');answer=[]
    if document is None:return []
    candidates=[i for i in context.get('regions',{}) if dual_axis_content_candidate(context,groups,i,nearby)]
    if not candidates:return []
    import pymupdf
    raw=document.path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    with pymupdf.open(stream=raw,filetype='pdf') as pdf:
        for ordinal in candidates:
            areas=context['regions'][ordinal];state=usage_scope_identity(context['usage_scopes'],groups[ordinal][0])
            if any(other!=ordinal and usage_scope_identity(context['usage_scopes'],groups[other][0])==state and any(a['page_number']==b['page_number'] and min(a['bbox'][2],b['bbox'][2])>max(a['bbox'][0],b['bbox'][0]) and min(a['bbox'][3],b['bbox'][3])>max(a['bbox'][1],b['bbox'][1]) for a in areas for b in otherareas) for other,otherareas in context['regions'].items()):continue
            physical=_physical(context,ordinal,actual.get(ordinal,[]),pdf,digest)
            if physical is None:continue
            body=_body(context,groups,ordinal,nearby,physical['x_values'],physical)
            if body is None:continue
            physical['independent_slots']=body['slots'];physical['declared_experiment_owner']=body['owner']
            answer.append((ordinal,'dual_axis_owned_numeric_relationship',body['rows'],physical))
    return [item for item in answer if not any(other[0]!=item[0] and {(r.page_number,r.bbox,r.text) for r in item[2]}&{(r.page_number,r.bbox,r.text) for r in other[2]} for other in answer)]
