"""Bind native network roles and original vector stages to independent prose.

The fusion diagrams share the same words. Their actual processing stages on
either side of the convergence distinguish input, feature and decision fusion.
Distillation diagrams instead require the two physically aligned representations
and their loss location. These facts are local observations, never verdicts.
"""
import re

from .usage_text_cache import normalize_text


def _text(value):
    value=normalize_text(value).casefold()
    return re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])','',value)


def _has(text,pattern):
    return bool(re.search(pattern,_text(text),re.I))


def _network_identity_in_text(name,text):
    # Keep spaces in prose: a following English word is not part of the name.
    # Native glyph splitting may insert separators within the printed name.
    identity=re.sub(r'[\s_-]+','',normalize_text(name)).casefold()
    if not identity:return False
    pattern=r'(?<![a-z0-9_])'+r'[\s_-]*'.join(re.escape(c) for c in identity)+r'(?![a-z0-9_])'
    return bool(re.search(pattern,_text(text)))


def _owned_network_passages(names,passages):
    """Do not let a comparison name own another model's operation clauses."""
    answer=[]
    predicate=r'(?=在|是|采用|使用|将|通过|先|由|对|的|可|仅|只|is\b|are\b|uses?\b|fuses?\b|encodes?\b|processes?\b|combines?\b)'
    subject=re.compile(r'(?<![A-Za-z0-9_])([A-Z][A-Za-z0-9_-]*[A-Z][A-Za-z0-9_-]*)(?:\s*(?:模型|网络|model\b|network\b))?\s*'
                       +predicate)
    plain_subject=re.compile(r'(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_-]{2,})\s*(?:模型|网络|model\b|network\b)\s*'+predicate,re.I)
    for rows,value in passages:
        if not all(_network_identity_in_text(name,value) for name in names):continue
        owned=[];owner=False
        for clause in re.split(r'(?<=[。！？；;，,])|(?<=[.!?])\s+',normalize_text(value)):
            subjects=subject.findall(clause)+plain_subject.findall(clause)
            # These are the paired physical roles of a distillation network,
            # rather than a competing named network.
            subjects=[s for s in subjects if s.casefold() not in {'teacher','student'}]
            if any(not any(_network_identity_in_text(name,s) for name in names) for s in subjects):
                if owned:answer.append((rows,''.join(owned)))
                owned=[];owner=False
                continue
            if any(_network_identity_in_text(name,clause) for name in names):owner=True
            if owner:owned.append(clause)
        if owned:answer.append((rows,''.join(owned)))
    return answer


def _center(field,axis):
    return (field['bbox'][axis]+field['bbox'][axis+2])/2


def _pick(passages,predicate):
    candidates=[rows for rows,value in passages if predicate(_text(value))]
    return min(candidates,key=lambda rows:sum(len(row.text) for row in rows)) if candidates else []


def _named(fields,pattern):
    return [f for f in fields if re.fullmatch(pattern,_text(f['text']).strip(),re.I)]


def network_native_candidate(fields):
    value=' '.join(f['text'] for f in fields if f.get('source')=='native')
    return (_has(value,r'\bfusion\b') and _has(value,r'\bmodality\s+[a-z0-9]+\b') and _has(value,r'\boutput\b')
            or all(_has(value,pattern) for pattern in (r'\bteacher\b',r'\bstudent\b',r'\binput\b',r'\bdistillation\b',r'\bloss\b')))


def read_mode_identity(title):
    value=normalize_text(title)
    if not _has(value,r'对齐增强|alignment[\s_-]*(?:enhancement|enhanced)'):return None
    match=re.search(r'\(([A-Z][A-Z0-9]{1,5})\)\s*(?:mode|模式)',value)
    return match.group(1) if match else None


def _read_mode_body(title,passages):
    """A named mode must encode each read, optionally interact, and retain it."""
    identity=read_mode_identity(title)
    if not identity:return None
    inputs=[]
    for rows,value in passages:
        text=_text(value)
        if not _network_identity_in_text(identity,value):continue
        if not all(_has(text,p) for p in (r'独立.{0,15}(?:通过|经过).{0,8}cnn.{0,15}(?:提取|编码)',
                                           r'可选.{0,30}(?:多读|注意力|交互)',r'读取维度',r'(?:多头|自)注意力')):continue
        shape=re.search(r'b\s*[×x]\s*t\s*[×x]\s*([a-z])\s*[×x]\s*d\s*_?\s*model',text)
        if shape and shape.group(1) not in {'b','t'}:inputs.append((rows,shape.group(1)))
    for first,count in inputs:
        end=max(row.page_number for row in first)
        for last,value in passages:
            if not all(end<=row.page_number<=end+1 for row in last):continue
            if last[0].page_number==end and last[0].bbox[1]<first[0].bbox[1]:continue
            text=_text(value)
            if not _has(text,r'保留.{0,20}完整.{0,10}'+count+r'\s*条.{0,15}(?:序列|特征)'):continue
            if not _has(text,r'展平.{0,15}输出'):continue
            shape=r'b\s*[×x]\s*\(\s*t\s*[·*×]\s*'+count+r'\s*\)\s*[×x]\s*d\s*_?\s*model'
            if re.search(shape,text):return [*first,*last],count
    return None


def read_mode_content_candidate(title,passages):
    return _read_mode_body(title,passages) is not None


def _distinct_ink(fields,pattern):
    """Merge repeated observations of the same glyph, keep separate glyphs."""
    answer=[]
    for field in _named(fields,pattern):
        for i,old in enumerate(answer):
            if (_text(field['text'])==_text(old['text'])
                    and abs(_center(field,0)-_center(old,0))<=2
                    and abs(_center(field,1)-_center(old,1))<=2):
                if field.get('confidence',1)>old.get('confidence',1):answer[i]=field
                break
        else:answer.append(field)
    return answer


def _stacked_role(fields,words):
    combined=_distinct_ink(fields,r'\s+'.join(map(re.escape,words)))
    choices=[combined] if len(combined)==1 else []
    columns=[_distinct_ink(fields,re.escape(word)) for word in words]
    import itertools
    for selected in itertools.product(*columns):
        if (max(_center(f,0) for f in selected)-min(_center(f,0) for f in selected)<=12
                and all(-3<=b['bbox'][1]-a['bbox'][3]<=max(a['bbox'][3]-a['bbox'][1],b['bbox'][3]-b['bbox'][1])*1.5
                        for a,b in zip(selected,selected[1:]))):choices.append(list(selected))
    if len(choices)!=1:return None
    members=choices[0]
    return dict(bbox=[min(f['bbox'][0] for f in members),min(f['bbox'][1] for f in members),
                      max(f['bbox'][2] for f in members),max(f['bbox'][3] for f in members)],fields=members)


def _read_mode(fields,area,document,passages):
    body=_read_mode_body(area['title'],passages)
    if body is None:return None
    from hashlib import sha256
    from pathlib import Path
    from .usage_graphic_ocr import _json,_valid_facts
    try:pdf_sha=sha256(Path(document.path).read_bytes()).hexdigest()
    except OSError:return None
    context=dict(pdf_sha=pdf_sha,page_number=area['page_number'],bbox=area['bbox'])
    context['region_identity']=sha256(_json(context)).hexdigest()
    native={(row.page_number,tuple(row.bbox),row.text) for page in document.pages for row in page.lines if row.source=='native'}
    actual=[f for f in fields if (f.get('source')=='native'
            and (f['page_number'],tuple(f['bbox']),f['text']) in native)
            or _valid_facts([f],context)]
    input_read=_stacked_role(actual,('input','reads'))
    cnn=_stacked_role(actual,('residual','cnn','blocks'))
    attention=_stacked_role(actual,('multi-head','attention'))
    merged=_stacked_role(actual,('merged','features'))
    first=_distinct_ink(actual,r'read\s*1')
    last=_distinct_ink(actual,r'read\s*'+re.escape(body[1]))
    if any(role is None for role in (input_read,cnn,attention,merged)) or len(first)!=1 or len(last)!=1:return None
    a,b=first[0],last[0]
    if abs(_center(a,1)-_center(b,1))>max(a['bbox'][3]-a['bbox'][1],b['bbox'][3]-b['bbox'][1])*1.5:return None
    if _center(b,0)-_center(a,0)<30:return None
    if not (_center(input_read,0)<_center(cnn,0)<a['bbox'][0]<b['bbox'][0]
            and merged['bbox'][3]<attention['bbox'][1]<min(a['bbox'][1],b['bbox'][1])
            and max(a['bbox'][3],b['bbox'][3])<_center(cnn,1)<input_read['bbox'][1]
            and _center(merged,0)<_center(attention,0)<a['bbox'][0]):return None
    physical=dict(input_read=input_read,independent_read_endpoints=[a,b],cnn=cnn,
                  attention=attention,merged=merged,
                  criterion='Original native or bound pixel roles and positions; independent named-mode encoding, optional interaction, and read-preserving flattening.')
    return 'independent_read_encoding_and_optional_interaction',body[0],physical


def _original_shapes(document,areas):
    """Read closed tapered polygons and connecting lines from actual PDF ink."""
    answer=[]
    try:
        import pymupdf
        with pymupdf.open(document.path) as pdf:
            for area in areas:
                number=area['page_number'];roi=area['bbox']
                if not 1<=number<=len(pdf):return []
                nodes={};segments=[]
                for drawing in pdf[number-1].get_drawings():
                    b=tuple(drawing['rect'])
                    if not (roi[0]-.5<=b[0]<b[2]<=roi[2]+.5 and roi[1]-.5<=b[1]<b[3]<=roi[3]+.5):continue
                    items=drawing.get('items',[])
                    for item in items:
                        if item[0]=='l':segments.append((tuple(item[1]),tuple(item[2])))
                    if len(items)!=4 or any(item[0]!='l' for item in items):continue
                    points=[tuple(item[1]) for item in items]
                    if any(abs(items[i][2].x-items[(i+1)%4][1].x)>.1 or abs(items[i][2].y-items[(i+1)%4][1].y)>.1 for i in range(4)):continue
                    if b[2]-b[0]<15 or b[3]-b[1]<10:continue
                    top=[x for x,y in points if abs(y-b[1])<.1]
                    bottom=[x for x,y in points if abs(y-b[3])<.1]
                    if len(top)!=2 or len(bottom)!=2:continue
                    tw=max(top)-min(top);bw=max(bottom)-min(bottom)
                    if not .25<=min(tw,bw)/max(tw,bw)<=.85:continue
                    if abs((sum(top)-sum(bottom))/2)>(b[2]-b[0])*.1:continue
                    nodes[tuple(round(v,1) for v in b)]=dict(bbox=list(b),expands_up=tw>bw)
                answer.append(dict(page_number=number,nodes=list(nodes.values()),segments=segments))
    except (OSError,RuntimeError,ValueError,ImportError):
        return []
    return answer


def _fusion(fields,shapes,passages):
    fusion=_named(fields,r'fusion');outputs=_named(fields,r'output')
    modals=_named(fields,r'modality\s+[a-z0-9]+')
    if len(fusion)!=1 or len(outputs)!=1 or len(modals)<3:return None
    if len({_text(f['text']) for f in modals})!=len(modals):return None
    if len({f['page_number'] for f in fields})!=1 or len(shapes)!=1:return None
    x=_center(fusion[0],0);y=_center(fusion[0],1)
    if not _center(outputs[0],1)<y<min(_center(f,1) for f in modals):return None
    if max(_center(f,1) for f in modals)-min(_center(f,1) for f in modals)>12:return None
    if abs(_center(outputs[0],0)-x)>20:return None
    centers=sorted(_center(f,0) for f in modals)
    if min(b-a for a,b in zip(centers,centers[1:]))<30:return None
    nodes=shapes[0]['nodes']
    above=[n for n in nodes if n['bbox'][3]<fusion[0]['bbox'][1]]
    below=[n for n in nodes if n['bbox'][1]>fusion[0]['bbox'][3]]
    if len(above)+len(below)!=len(nodes):return None
    top=min((n['bbox'][1] for n in below),default=min(f['bbox'][1] for f in modals))
    horizontal=[(min(a[0],b[0]),max(a[0],b[0]),(a[1]+b[1])/2) for a,b in shapes[0]['segments']
                if abs(a[1]-b[1])<.1 and fusion[0]['bbox'][3]<a[1]<top]
    if not any(any(abs(left-centers[0])<3 and abs(right-x)<3 and abs(by-ay)<.1 for left,right,by in horizontal)
               and any(abs(left-x)<3 and abs(right-centers[-1])<3 and abs(by-ay)<.1 for left,right,by in horizontal)
               for _,_,ay in horizontal):return None
    shared=all(abs((n['bbox'][0]+n['bbox'][2])/2-x)<15 for n in above)
    per_branch={cx:[n for n in below if abs((n['bbox'][0]+n['bbox'][2])/2-cx)<15] for cx in centers}
    early=lambda t: (_has(t,r'(原始|浅层).{0,70}(输入|数据).{0,25}(结合|拼接|融合|整合)')
                     and _has(t,r'(仅.{0,8}一|一个|单一|单个|single|one).{0,10}(编码器|encoder)')
                     and _has(t,r'(提取之前|输入层|先.{0,30}融合.{0,30}再.{0,10}编码)'))
    middle=lambda t: (_has(t,r'(各模态|各个模态|模态特异性|分别由).{0,120}(提取|编码器|extract|encoder)')
                      and _has(t,r'(特征空间.{0,12}(整合|融合)|特征.{0,20}(进行融合|被送入|融合后)|融合后的特征)')
                      and _has(t,r'(高级特征|中间特征|预测|联合表示|独特信息)'))
    late=lambda t: (_has(t,r'(解码器.{0,8}末端|各模态独立.{0,20}推理)')
                    and _has(t,r'(融合.{0,20}(预测结果|解码器的输出)|拼接.{0,20}解码器的输出|最终在决策层面整合)'))
    if shared and len(above)==2 and not below and sorted(above,key=lambda n:n['bbox'][1])[0]['expands_up'] and not sorted(above,key=lambda n:n['bbox'][1])[1]['expands_up']:
        kind='input_fusion_before_shared_encoding';rows=_pick(passages,early)
    elif shared and len(above)==1 and above[0]['expands_up'] and len(below)==len(modals) and all(len(n)==1 and not n[0]['expands_up'] for n in per_branch.values()):
        kind='independent_encoding_before_feature_fusion';rows=_pick(passages,middle)
    elif not above and len(below)==2*len(modals) and all(len(n)==2 and sorted(n,key=lambda q:q['bbox'][1])[0]['expands_up'] and not sorted(n,key=lambda q:q['bbox'][1])[1]['expands_up'] for n in per_branch.values()):
        kind='independent_predictions_before_decision_fusion';rows=_pick(passages,late)
    else:return None
    return (kind,rows,dict(modalities=modals,fusion=fusion[0],output=outputs[0],original_vector_stages=nodes)) if rows else None


def _distillation(fields,passages):
    teachers=_named(fields,r'teacher(?:\s+model)?');students=_named(fields,r'student(?:\s+model)?')
    inputs=_named(fields,r'input');distill=_named(fields,r'distillation');loss=_named(fields,r'loss')
    if any(len(values)!=1 for values in (teachers,students,inputs,distill,loss)):return None
    teacher,student=teachers[0],students[0];ly=(_center(distill[0],1)+_center(loss[0],1))/2
    ty,sy=_center(teacher,1),_center(student,1)
    if not ty<ly<sy or abs(_center(teacher,0)-_center(student,0))>100:return None
    if not _center(inputs[0],0)<min(teacher['bbox'][0],student['bbox'][0]):return None
    logits=_named(fields,r'logits');relations=_named(fields,r'relations')
    layers=_named(fields,r'layer\s*[-–]?\s*(?:\d+|n)')
    lx=(_center(distill[0],0)+_center(loss[0],0))/2
    teacher_student=lambda t:_has(t,r'教师|teacher') and _has(t,r'学生|student')
    if len(logits)==2 and not relations and not layers:
        if any(abs(_center(f,1)-ry)>12 for f,ry in zip(sorted(logits,key=lambda f:_center(f,1)),(ty,sy))):return None
        if not min(_center(f,0) for f in logits)>max(teacher['bbox'][2],student['bbox'][2]) or not lx>max(f['bbox'][2] for f in logits):return None
        identity=_pick(passages,lambda t:teacher_student(t) and _has(t,r'logit|逻辑输出') and _has(t,r'温度|temperature|softmax'))
        operation=_pick(passages,lambda t:teacher_student(t) and _has(t,r'软输出|软标签|soft\s+targets?') and _has(t,r'蒸馏损失|distillation\s+loss') and _has(t,r'kl|散度'))
        rows=identity+operation if identity and operation else []
        kind='paired_teacher_student_logit_distillation'
    elif len(logits)==2 and len(layers)>=6 and not relations:
        low=[f for f in layers if _center(f,1)>ly];high=[f for f in layers if _center(f,1)<ly]
        if len(low)!=len(high) or len(high)<3:return None
        high=sorted(high,key=lambda f:_center(f,0));low=sorted(low,key=lambda f:_center(f,0))
        if any(_text(a['text'])!=_text(b['text']) or abs(_center(a,0)-_center(b,0))>12 for a,b in zip(high,low)):return None
        if not _center(high[0],0)<lx<_center(high[-1],0)<min(_center(f,0) for f in logits):return None
        rows=_pick(passages,lambda t:teacher_student(t) and _has(t,r'中间.{0,5}特征') and _has(t,r'最小化.{0,30}差异') and _has(t,r'特征对齐|特征匹配'))
        kind='paired_intermediate_layer_feature_distillation'
    elif len(relations)==2 and not logits and not layers:
        ts=_named(fields,r't\s*(?:\d+|n)');ss=_named(fields,r's\s*(?:\d+|n)')
        if len(ts)<3 or len(ts)!=len(ss):return None
        if not all(abs(_center(f,1)-ty)<15 for f in ts) or not all(abs(_center(f,1)-sy)<15 for f in ss):return None
        upper,lower=sorted(relations,key=lambda f:_center(f,1))
        if not _center(upper,1)<ly<_center(lower,1):return None
        if not min(_center(upper,0),_center(lower,0))>max(_center(f,0) for f in ts+ss):return None
        rows=_pick(passages,lambda t:teacher_student(t) and _has(t,r'成对相似性|pairwise|层对之间') and _has(t,r'关系|相似性|relations') and _has(t,r'损失|内积|距离|角度|loss'))
        kind='paired_teacher_student_relation_distillation'
    else:return None
    return (kind,rows,dict(teacher=teacher,student=student,input=inputs[0],distillation=distill[0],loss=loss[0],representations=logits+layers+relations)) if rows else None


def network_relation_proposals(context,groups,nearby,observed_fields=None):
    from .usage_figure_evidence import _named_figure_identity
    proposals=[]
    for ordinal,areas in context['regions'].items():
        fields=[f for f in context['native_fields'].get(ordinal,[]) if f.get('source')=='native']
        if len(areas)==1 and read_mode_identity(areas[0]['title']):
            answer=_read_mode((observed_fields or {}).get(ordinal,fields),areas[0],context['_document'],nearby(ordinal))
            if answer:
                kind,rows,physical=answer
                proposals.append((ordinal,kind,rows,physical))
        if not network_native_candidate(fields):continue
        if len(areas)!=1:continue
        area=areas[0];roi=area['bbox']
        if any(f['page_number']!=area['page_number'] or not
               (roi[0]-.01<=f['bbox'][0]<f['bbox'][2]<=roi[2]+.01 and
                roi[1]-.01<=f['bbox'][1]<f['bbox'][3]<=roi[3]+.01) for f in fields):continue
        passages=nearby(ordinal)
        title=area['title']
        names=set(re.findall(r'(?<![A-Za-z0-9])[A-Z][A-Za-z0-9_-]*[A-Z][A-Za-z0-9_-]*(?![A-Za-z0-9])',title))
        identity=_named_figure_identity(title)
        if identity:names.add(identity)
        if names:passages=_owned_network_passages(names,passages)
        if not passages:continue
        if _named(fields,r'fusion'):
            answer=_fusion(fields,_original_shapes(context['_document'],areas),passages)
        else:answer=_distillation(fields,passages)
        if answer:
            kind,rows,physical=answer
            proposals.append((ordinal,kind,rows,physical))
    return proposals
