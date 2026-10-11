"""Bind native table use from field definitions or exact reported relative gain.

This helper adds only physical indirect credits to a copied index. It neither
corrects literal numbers nor removes titles. Native cells must have an exclusive
observed table owner; shared numbers/topics and tied candidates give no credit.
No paths, document IDs, result files, or external decision lists are consulted.
"""
import re
from dataclasses import replace
from decimal import Decimal, ROUND_HALF_UP
from .reference_identity_repair import (_usage_owner,_usage_title,_contained,_key,
    _is_body,_directory_keys,_scope_map,_semantic_contexts,_semantic_text,_add_indirect)
from .model import DocumentIndex


def _compact(text):
    return re.sub(r'\s+','',_semantic_text(text)).casefold()


def _cells(page,box):
    rows=[]
    for line in sorted((l for l in page.lines if _contained(l,box)),key=lambda l:(l.bbox[1],l.bbox[0])):
        y=(line.bbox[1]+line.bbox[3])/2
        row=next((r for r in reversed(rows) if abs(r[0]-y)<=max(2,(line.bbox[3]-line.bbox[1])*.3)),None)
        if row is None:rows.append([y,[line]])
        else:row[1].append(line)
    return [sorted(ls,key=lambda l:l.bbox[0]) for y,ls in rows]


def _observed_owner(target,pages,objects):
    owner=_usage_owner(target,'table',pages,objects)
    if owner is None:return None
    page=pages[target.line.page_number]
    # Images/graphics alone cannot supply column/row evidence for this helper.
    boxes=list(page.tables)+[o.bbox for o in objects if o.page_number==page.number and o.kind=='table']
    if not any(all(abs(a-b)<=2 for a,b in zip(owner,box)) for box in boxes):return None
    return owner


def _meaning(text):
    t=_compact(text);result=set()
    if re.search(r'粗粒度|coarse(?:grain)?',t):result.add('coarse')
    if re.search(r'细粒度|fine(?:grain)?',t):result.add('fine')
    if re.search(r'(?:transformer|堆叠|网络).{0,12}(?:层数|层|深度)|(?:layer|stack).{0,12}(?:count|depth|number)|层数',t):result.add('layers')
    if re.search(r'(?:特征|向量|模型).{0,10}维度|(?:feature|vector|model).{0,12}dimension',t):result.add('dimension')
    if re.search(r'(?:注意力|attention).{0,18}(?:头数|头|heads?)',t):result.add('heads')
    return result


def _dictionary(rows):
    if not rows:return None
    header=rows[0]
    labels=[_compact(l.text) for l in header]
    if not any(v in {'参数名','parameter','parametername'} for v in labels):return None
    if not any(v in {'类型','type'} for v in labels):return None
    desc=next((l for l in header if _compact(l.text) in {'说明','描述','含义','description','meaning'}),None)
    default=next((l for l in header if _compact(l.text) in {'默认值','default','defaultvalue'}),None)
    if desc is None or default is None:return None
    records=[]
    for row in rows[1:]:
        if len(row)<4:continue
        name=_compact(row[0].text)
        if not re.fullmatch(r'[a-z][a-z0-9_]{2,}',name):continue
        if _compact(row[1].text) not in {'int','float','bool','str','integer','boolean','string'}:continue
        description=' '.join(l.text for l in row if l.bbox[0]>=desc.bbox[0]-3)
        defaults=[l.text for l in row if abs(l.bbox[0]-default.bbox[0])<=8]
        if len(defaults)!=1:continue
        sense=_meaning(description)
        if len(sense)==1:records.append(dict(name=name,sense=next(iter(sense)),default=defaults[0],description=description))
    if len({r['name'] for r in records})!=len(records):return None
    return records if len(records)>=4 else None


def _dictionary_proof(text,records):
    t=_compact(text)
    if not re.search(r'初始化|配置|参数|initializ|configuration|parameters?',t):return None
    mentions=sorted((m.start(),m.end(),r) for r in records for m in re.finditer(r'(?<![a-z0-9_])'+re.escape(r['name'])+r'(?![a-z0-9_])',t))
    if len({r['name'] for a,b,r in mentions})<4:return None
    mapped={};bad=False
    # "A and B ... respectively coarse and fine" is positional evidence.
    for pos,(start,end,r) in enumerate(mentions[:-1]):
        ns,ne,nr=mentions[pos+1]
        between=t[end:ns]
        after=t[ne:mentions[pos+2][0] if pos+2<len(mentions) else len(t)]
        if not re.fullmatch(r'[、,，和与及&and()（）\s]*',between):continue
        pair=re.match(r'[^。；;]{0,20}?分别(?:用于|表示|控制|定义|对应)?(?P<a>[^。；;和与及]{1,35})(?:和|与|及)(?P<b>[^。；;]{1,45})',after)
        if not pair:continue
        sa=_meaning(pair.group('a'));sb=_meaning(pair.group('b'))
        if sa!={r['sense']} or sb!={nr['sense']}:bad=True
        else:mapped[r['name']]=r;mapped[nr['name']]=nr
    for pos,(start,end,r) in enumerate(mentions):
        if r['name'] in mapped:continue
        tail=t[end:mentions[pos+1][0] if pos+1<len(mentions) else len(t)]
        tail=re.split(r'[。；;，,]',tail)[0]
        senses=_meaning(tail)
        if r['sense'] in senses:mapped[r['name']]=r
        elif senses:bad=True
    if bad or len(mapped)<4 or len({r['sense'] for r in mapped.values()})<3:return None
    # A numeric default defines a different configuration. Require its own
    # explicit assignment rather than borrow it from another field.
    for r in mapped.values():
        default=_compact(r['default'])
        if default not in {'-','—','–','none','null'}:
            if not re.search(re.escape(r['name'])+r'(?:为|=|等于|issetto)'+re.escape(default)+r'(?![0-9.])',t):return None
    return dict(kind='ordered_parameter_definitions',fields=[dict(identifier=r['name'],meaning=r['sense'],table_description=r['description'],default=r['default']) for r in mapped.values()])


_METRIC=re.compile(r'(?<![a-z0-9])(?:ndcg@\d+|dcg@\d+|mrr(?:@\d+)?|map(?:@\d+)?|bleu(?:-?\d+)?|rouge-[12l]|rmse|mae|accuracy|f1|auc)(?![a-z0-9])',re.I)
_NUM=re.compile(r'^\s*\d+(?:\.\d+)?\s*$')


def _quantitative(rows,title):
    metrics=set(_METRIC.findall(_semantic_text(title).casefold()))
    if len(metrics)!=1:return None
    for row in rows:
        average=[l for l in row if _compact(l.text) in {'average','avg','mean','平均','均值'}]
        if len(average)!=1 or len(row)<3:continue
        avg=average[0];cols=[l for l in row if l is not avg and l.text.strip()]
        if any(_NUM.fullmatch(l.text) for l in cols):continue
        # Dataset headings are actual distinct physical columns, not a bag of
        # values. The empty method heading is allowed at the far left.
        cols=[l for l in cols if _compact(l.text) not in {'方法','算法','模型','method','model','algorithm'}]
        if len(cols)<2 or len({_compact(l.text) for l in cols})!=len(cols):continue
        columns=cols+[avg];columns.sort(key=lambda l:l.bbox[0])
        centers=[(l.bbox[0]+l.bbox[2])/2 for l in columns]
        if any(b-a<8 for a,b in zip(centers,centers[1:])):continue
        records={}
        for r in rows:
            if r[0].bbox[1]<=row[0].bbox[1]:continue
            numeric=[l for l in r if _NUM.fullmatch(_semantic_text(l.text))]
            if len(numeric)!=len(columns):continue
            numeric.sort(key=lambda l:l.bbox[0])
            if any(abs((l.bbox[0]+l.bbox[2])/2-c)>max(8,min(abs(c-z) for z in centers if z!=c)*.3) for l,c in zip(numeric,centers)):continue
            prefix=' '.join(l.text for l in r if l.bbox[2]<=numeric[0].bbox[0]+2)
            name=_compact(prefix)
            role='baseline' if re.fullmatch(r'baseline|基准(?:算法|方法|模型)?',name) else 'proposed' if re.fullmatch(r'our(?:method|model|algorithm)|ours|本文(?:方法|模型|算法)|所提(?:方法|模型|算法)',name) else None
            if role is None:continue
            if role in records:return None
            values=[Decimal(_semantic_text(l.text).strip()) for l in numeric]
            ap=columns.index(avg);datasets=[v for p,v in enumerate(values) if p!=ap];mean=sum(datasets)/Decimal(len(datasets))
            resolution=Decimal(1).scaleb(values[ap].as_tuple().exponent)
            if mean.quantize(resolution,rounding=ROUND_HALF_UP)!=values[ap]:continue
            records[role]=dict(label=prefix,average=values[ap],dataset_values=datasets)
        if set(records)=={'baseline','proposed'}:
            return dict(metric=next(iter(metrics)),dataset_count=len(cols),columns=[l.text for l in columns],records=records)
    return None


def _relative_proof(text,signature):
    t=_compact(text);metric=re.escape(signature['metric'])
    # Subject, comparison, dataset count, metric, unit, and gain all belong to
    # one clause. A comparator mention or another metric's percent cannot pay
    # for a result attributed to the target table.
    own=r'本文(?:所)?(?:提出|所提)?(?:方法|算法|模型)'
    compare=r'(?:相较于?|相比于?)基准(?:算法|方法|模型)[,，]?'
    count=r'(?P<count>\d+|两|二|三|四|五|六|七|八|九|十)'
    gain=r'(?P<value>\d+(?:\.\d+)?)%'
    pattern=compare+own+r'在'+count+r'个数据集上(?:的)?平均'+metric+r'(?:分数|得分|指标)?(?:提高了?|提升了?|增加了?)'+gain
    english=r'compared(?:with|to)(?:the)?baseline[,，]?our(?:proposed)?(?:method|algorithm|model)(?:on|across)(?P<english>\d+)datasets?(?:the)?(?:average|mean)'+metric+r'(?:score)?(?:improv(?:es?|ed)?by|increas(?:es?|ed)?by)'+gain
    matches=list(re.finditer(pattern,t))+list(re.finditer(english,t))
    for match in matches:
        raw=match.groupdict().get('count') or match.groupdict().get('english')
        n=int(raw) if raw.isdigit() else {'两':2,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}[raw]
        if n!=signature['dataset_count']:continue
        reported=Decimal(match.group('value'))
        # Coarse rounded integer/one-decimal gains are not exclusive numerical
        # identity. Keep those cases undecided instead of widening tolerance.
        if reported.as_tuple().exponent>-2:continue
        base=signature['records']['baseline']['average'];own=signature['records']['proposed']['average']
        if base<=0 or own<=base:continue
        relative=(own-base)/base*100;resolution=Decimal(1).scaleb(reported.as_tuple().exponent)
        if relative.quantize(resolution,rounding=ROUND_HALF_UP)!=reported:continue
        return dict(kind='relative_average_gain',metric=signature['metric'],dataset_count=n,columns=signature['columns'],baseline_average=str(base),proposed_average=str(own),reported_percent=str(reported),computed_percent=str(relative),formula='(proposed_average-baseline_average)/baseline_average*100',baseline_dataset_values=[str(v) for v in signature['records']['baseline']['dataset_values']],proposed_dataset_values=[str(v) for v in signature['records']['proposed']['dataset_values']])
    return None


def _excluded_context(text):
    return bool(re.search(r'文献\s*\[|引自|摘自|et\s+al\.?\s*\[|未(?:报告|采用|使用)|并未|没有采用|not\s+(?:used|reported|adopted)',_semantic_text(text),re.I))


def _chapter_barrier(document,line,target,sources):
    from .caption_context import body_font
    points=[(source['page'],source['bbox'][1]) for source in sources]+[(line.page_number,line.bbox[1]),(target.line.page_number,target.line.bbox[1])]
    low,high=min(points),max(points)
    for page in document.pages:
        if page.number<low[0] or page.number>high[0]:continue
        typical=body_font(page)
        for native in page.lines:
            if native.role in {'header','footer'} or not native.font_size or native.font_size<14:continue
            if not (native.bold or typical and native.font_size>=typical*1.2):continue
            if not re.match(r'^(?:第[一二三四五六七八九十百0-9]+章|chapter[0-9]+)',_compact(native.text)):continue
            if low<(page.number,native.bbox[1])<high:return True
    return False


def repair_parameter_table_references(index,layout_objects=(),*,evidence=None):
    """Return a copied index with exclusive native table-use bindings only."""
    out=replace(index,**{name:list(getattr(index,name)) for name in DocumentIndex.__dataclass_fields__ if name!='document'})
    out.indirect_reference_targets={key:set(value) for key,value in getattr(index,'indirect_reference_targets',{}).items()}
    objects=tuple(layout_objects);pages={p.number:p for p in index.document.pages};directories=_directory_keys(index.document)
    scopes,nonbody=_scope_map(index.document,directories)
    captions={_key(t.line) for t in (*index.figures,*index.tables,*index.appendices)}
    candidates=[]
    for target in index.tables:
        owner=_observed_owner(target,pages,objects)
        if owner is None:continue
        rows=_cells(pages[target.line.page_number],owner)
        title=_usage_title(target,'table',objects,pages)
        dictionary=_dictionary(rows);quantitative=_quantitative(rows,title)
        if dictionary is not None or quantitative is not None:candidates.append((target,owner,dictionary,quantitative))
    def inside_caption(line):
        return any(o.kind.endswith('_caption') and o.page_number==line.page_number and _contained(line,o.bbox) for o in objects)
    body=[(l,scopes.get(_key(l),'body')) for l in index.document.lines if _key(l) not in nonbody and _is_body(l,captions,directories,pages) and not inside_caption(l) and not any(t.line.page_number==l.page_number and _contained(l,b) for t,b,d,q in candidates)]
    for line,scope,sources in _semantic_contexts(body,index.document):
        if _excluded_context(line.text):continue
        choices={}
        for target,owner,dictionary,quantitative in candidates:
            if scope!=target.scope or _chapter_barrier(index.document,line,target,sources):continue
            proof=_dictionary_proof(line.text,dictionary) if dictionary else None
            if proof is None and quantitative:proof=_relative_proof(line.text,quantitative)
            if proof is None:continue
            key=(target.scope,target.line.page_number,tuple(owner),target.number)
            choices.setdefault(key,[]).append((target,proof))
        # Do not pick the nearest table when two independent tables prove the
        # same facts; proximity does not establish which one was discussed.
        if len(choices)!=1:continue
        entries=next(iter(choices.values()))
        if abs(entries[0][0].line.page_number-line.page_number)>1:continue
        for target,proof in entries:
            before=len(evidence) if evidence is not None else 0
            criterion='独占原表字段逐一定义及分别顺序' if proof['kind']=='ordered_parameter_definitions' else '独占原表指标/数据集列/基准与所提行/均值的精确相对增幅；不改正文原番号'
            _add_indirect(out,'table',target,line,scope,evidence,criterion)
            if evidence is not None and len(evidence)>before:
                evidence[-1]['parameter_table_proof']=proof;evidence[-1]['body_sources']=sources
    return out
