"""Independent prose must use actual interface/field/parameter relations.

This consumes native physical cells and returns evidence only. It neither
reads files nor mutates indices, references, captions or other rule outputs.
"""
import re
from difflib import SequenceMatcher

from .usage_text_cache import normalize_text
from .source_cited_usage import _primary_subjects


def _norm(text):
    return re.sub(r'[\s._–—-]+','',normalize_text(text)).casefold()


def _present(alias,text):
    alias=normalize_text(alias).strip()
    if alias.isascii():
        return bool(re.search(r'(?<![A-Za-z0-9_])'+re.escape(alias)+r'(?![A-Za-z0-9_])',normalize_text(text),re.I))
    return _norm(alias) in _norm(text)


def _grid(cells):
    from .usage_table_evidence import _cell_rows
    rows=_cell_rows(cells)
    header=next((sorted(row,key=lambda l:l.bbox[0]) for row in rows if len(row)>=2),None)
    if not header:
        return None
    centers=[(l.bbox[0]+l.bbox[2])/2 for l in header]
    data=[[] for _ in header]
    bottom=max(l.bbox[3] for l in header)
    for cell in cells:
        if cell.bbox[1]<bottom-1:
            continue
        x=(cell.bbox[0]+cell.bbox[2])/2
        column=min(range(len(centers)),key=lambda i:abs(centers[i]-x))
        data[column].append(cell)
    return header,data


def _relation_rows(cells):
    grid=_grid(cells)
    if not grid:
        return []
    header,columns=grid
    anchors=sorted(columns[0],key=lambda l:l.bbox[1])
    result=[]
    for i,anchor in enumerate(anchors):
        # First-column entries identify rows; wrapping is retained in purpose
        # columns. Neighbouring row starts bound a real multi-line cell.
        top=anchor.bbox[1]-max(2,(anchor.font_size or 10)*.2)
        next_top=anchors[i+1].bbox[1]-2 if i+1<len(anchors) else float('inf')
        texts=[' '.join(l.text for l in sorted(column,key=lambda l:(l.bbox[1],l.bbox[0]))
                        if top<=l.bbox[1]<next_top) for column in columns[1:]]
        result.append({'name':anchor.text,'purposes':texts,'anchor':anchor})
    return result


def _content_phrases(source,body):
    a,b=_norm(source),_norm(body)
    a=re.sub(r'^(?:实现|提供|支持|生成|提取|转换|增强|划分|构建|控制|模拟|影响|表现)+','',a)
    phrases=[]
    def words(value):
        return {_norm(m[0]) for m in re.finditer(r'[A-Za-z][A-Za-z0-9_-]*',normalize_text(value))}
    shared_words=words(source)&words(body)
    for block in SequenceMatcher(None,a,b,autojunk=False).get_matching_blocks():
        text=a[block.a:block.a+block.size].strip('，,、。:：;；()（）')
        if len(text)>=4 and re.search(r'[\u4e00-\u9fffA-Za-z]',text):
            if (re.search(r'[A-Za-z]',text) and not re.search(r'[\u4e00-\u9fff]',text)
                    and not any(len(word)>=4 and word in text for word in shared_words)):
                continue
            if text not in ('标准化接口','静态分析','staticanalysis','提供接口','系统功能','数据处理'):
                phrases.append(text)
    return list(dict.fromkeys(phrases))


def _aliases(name):
    functions=re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\s*\([^)]*\)',name)
    if functions:
        return functions,True
    words=[w for w in re.findall(r'[A-Za-z][A-Za-z0-9_-]*',name)
           if len(w)>=3 and (w.isupper() or any(c.isupper() for c in w[1:]))]
    return words or [normalize_text(name).strip()],False


_PURPOSE_OPERATIONS=(r'增强|augment|enhanc',r'划分|分割|partition|splits?',
    r'转换|转化|convert|transform',r'归一化|标准化|normaliz',
    r'提取|extract',r'生成|generat|creat',r'分析|analys',r'存储|记录|stor|record')


def _purpose_agrees(source,claim):
    operations=[rx for rx in _PURPOSE_OPERATIONS if re.search(rx,source,re.I)]
    return not operations or any(re.search(rx,claim,re.I) for rx in operations)


def _interfaces(descriptor,text):
    if not re.search(r'接口|工具|interface|\btools?\b|components?',descriptor['title'],re.I):
        return None
    if not re.search(r'实现|提供|支持|生成|提取|转换|增强|划分|构建|\b(?:provid|creat|extract|transform|normaliz|partition|return|store)',text,re.I):
        return None
    pairs=[]
    rows=_relation_rows(descriptor['cells'])
    mentions=[]
    for ordinal,row in enumerate(rows):
        for alias in _aliases(row['name'])[0]:
            pattern=(r'(?<![A-Za-z0-9_])'+re.escape(alias)+r'(?![A-Za-z0-9_])') if alias.isascii() else re.escape(alias)
            mentions.extend((m.start(),m.end(),ordinal) for m in re.finditer(pattern,normalize_text(text),re.I))
    for ordinal,row in enumerate(rows):
        aliases,function=_aliases(row['name'])
        hits=[alias for alias in aliases if _present(alias,text)]
        if not hits:
            continue
        # Arguments are distinct from an interface's purpose/output column.
        purpose=row['purposes'][-1] if row['purposes'] else ''
        claims=[]
        for start,end,owner in mentions:
            if owner!=ordinal:continue
            next_starts=[a for a,_,other in mentions if other!=ordinal and a>=end]
            # The identifier's own spelling (augment_data/split_dataset) is
            # not evidence that its corresponding operation was described.
            claims.append(normalize_text(text)[end:min(next_starts) if next_starts else len(normalize_text(text))])
        phrases=list(dict.fromkeys(p for claim in claims if _purpose_agrees(purpose,claim)
                                   for p in _content_phrases(purpose,claim)))
        if phrases:
            pairs.append({'row':row['name'],'identifiers':hits,'purpose_phrases':phrases,
                          'purpose':purpose,'function':function})
    if len(pairs)>=2 or (len(pairs)==1 and not pairs[0]['function'] and len(pairs[0]['purpose_phrases'])>=2):
        return {'kind':'actual_interface_or_tool_purpose_relations','matched_fields':[p['row'] for p in pairs],
                'matched_values':[],'relations':pairs}
    return None


def _interface_title_agrees(descriptor,text):
    """Ordinary words in the English companion do not become model names."""
    title=descriptor['title']
    if not re.search(r'接口|\binterfaces?\b',title,re.I):return False
    companion=re.search(r'\bTable\s+\d+(?:[.\-–]\d+)*',title,re.I)
    if companion and re.search(r'[\u4e00-\u9fff]',title[:companion.start()]):
        ordinary=_SEMANTIC_TITLE_FILLER|{'acquisition','community','detection','generation','module','modules','table'}
        suffix=title[companion.end():]
        identities=re.findall(r'(?i:\b(?:on|using|within)\s+(?:the\s+)?)([A-Z][A-Za-z0-9_-]*)',suffix)
        words=[w for w in re.findall(r'[A-Za-z][A-Za-z0-9_-]*',suffix) if w.casefold() not in ordinary]
        title=title[:companion.start()]+' '+' '.join([*words,*identities])
    return _subject_agrees(title,text)


def _endpoint_main_use(index,descriptors,paragraphs,chapters,epochs,section):
    """A primary callable and its real input/output own an endpoint catalogue.

    Distinct return paragraphs must retain the same service namespaces and
    section. A framework name, endpoint spelling or generic request alone is
    insufficient; native contracts and all physical competitors are retained.
    """
    from .usage_table_evidence import _explicit_table_numbers,_table_pointer_agrees
    def position(p):return (p.page_number,p.bbox[1])
    def route_pattern(route):
        leaf=route.rsplit('/',1)[-1]
        return r'(?<![A-Za-z0-9_/])(?:'+re.escape(route)+r'(?![A-Za-z0-9_/])|'+re.escape(leaf)+r'\s*\()'
    def named_names(text):
        return {m[0] for m in re.finditer(r'\b[A-Z][A-Za-z0-9_]*\b',normalize_text(text))
                if (m[0].isupper() and len(m[0])>=3 or any(c.isupper() for c in m[0][1:]))
                and m[0] not in {'API','APIs','POST','GET','REST','RESTful'}}
    def title_agrees(d,text):
        title=re.sub(r'\b(?:apis?|online|inference)\b','',d['title'],flags=re.I)
        return _subject_agrees(title,text)
    def generated_return(text):
        return bool(re.search(r'(?:返回|返还|return|send)[^。.!?；;]{0,55}(?:生成|generat)[^。.!?；;]{0,24}(?:结果|token|results?|outputs?)|(?:生成|generat)[^。.!?；;]{0,35}(?:结果|token|results?|outputs?)[^。.!?；;]{0,30}(?:返回|return)',text,re.I))
    candidates=[]
    for d in descriptors:
        if not re.search(r'接口|\bapis?\b|\bendpoints?\b',d['title'],re.I):continue
        rows=d.get('_native_relation_rows') or _relation_rows(d['cells'])
        contracts=[r for r in rows if re.fullmatch(r'/(?:[A-Za-z_][A-Za-z0-9_]*/)*[A-Za-z_][A-Za-z0-9_]*',r['name'])
            and len(r['purposes'])>=2 and re.fullmatch(r'GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS',r['purposes'][0].strip())
            and re.search(r'推理|\binference\b',r['purposes'][-1],re.I)
            and re.search(r'接受|接收|accept|receiv',r['purposes'][-1],re.I)
            and re.search(r'请求|requests?',r['purposes'][-1],re.I)
            and generated_return(r['purposes'][-1])]
        if not contracts:continue
        for anchor in paragraphs:
            if epochs[id(anchor)]!=d['usage_epoch'] or not title_agrees(d,anchor.text):continue
            if (chapters.get(anchor.page_number)!=chapters.get(d['target'].line.page_number)
                    or section(anchor)!=section(d['target'].line)):continue
            if not _table_pointer_agrees(d,_explicit_table_numbers(anchor.text)):continue
            text=normalize_text(anchor.text)
            if re.search(r'(?:不|未)(?:用于|调用|触发|接收|返回)|(?:只|仅)接收[^。;；]{0,12}(?:日志|健康|状态)|\b(?:not\s+used|never\s+called)\b',text,re.I):continue
            primary=[]
            for row in contracts:
                rx=route_pattern(row['name'])
                if not re.search(r'(?:核心|主要|primary|core)[^。.!?；;]{0,65}'+rx,text,re.I):continue
                if not re.search(r'推理|\binference\b',text,re.I) or not re.search(r'请求|requests?',text,re.I):continue
                if not re.search(r'接收|接受|请求在进入|请求进入|请求接收|receiv|accept',text,re.I):continue
                methods=set(re.findall(r'(?<![A-Za-z0-9_])(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)(?![A-Za-z0-9_])',text))
                if methods and methods!={row['purposes'][0].strip()}:continue
                primary.append(row)
            if len(primary)!=1:continue
            row=primary[0];contexts=[]
            if not generated_return(text):
                namespaces=named_names(text)
                if not namespaces:continue
                possible=[]
                for output in paragraphs:
                    if position(output)<=position(anchor) or section(output)!=section(anchor) or epochs[id(output)]!=d['usage_epoch']:continue
                    if not namespaces<=named_names(output.text) or not generated_return(output.text):continue
                    if not _table_pointer_agrees(d,_explicit_table_numbers(output.text)):continue
                    between=[p for p in paragraphs if position(anchor)<position(p)<=position(output)]
                    # An intervening function or foreign target owns its output;
                    # a primary interface cannot borrow that separate workflow.
                    if any(re.search(r'\b[A-Za-z_][A-Za-z0-9_]*\s*\(',p.text)
                           or any(re.search(route_pattern(r['name']),p.text) for r in rows if r['name'].startswith('/'))
                           or not _table_pointer_agrees(d,_explicit_table_numbers(p.text)) for p in between):continue
                    possible.append(output)
                if not possible:continue
                contexts=[min(possible,key=position)]
            candidates.append((d,anchor,row,contexts))
    uses={}
    for d,anchor,row,contexts in candidates:
        if any(other['i']!=d['i'] and other_anchor is anchor for other,other_anchor,_,_ in candidates):continue
        target=d['target']
        uses.setdefault(d['i'],{
            'physical_key':{'number':target.number,'page':target.line.page_number,'caption_bbox':list(target.line.bbox),'scope':target.scope},
            'usage_epoch':d['usage_epoch'],'title':d['title'],
            'body':{'page':anchor.page_number,'bbox':list(anchor.bbox),'text':anchor.text},
            'body_context':[{'page':p.page_number,'bbox':list(p.bbox),'text':p.text} for p in contexts],
            'cell_evidence':[{'page':l.page_number,'bbox':list(l.bbox),'text':l.text} for l in d['cells']],
            'kind':'actual_primary_endpoint_and_owned_inference_input_output',
            'matched_fields':[row['name'],'inference requests -> generated results'],
            'matched_values':[row['purposes'][0]],
            'relations':[{'endpoint':row['name'],'native_purpose':row['purposes'][-1],'native_http_method':row['purposes'][0]}],
            'uniqueness_reason':'One physical native endpoint contract is independently designated core and owns both inference-request input and generated-result output; another endpoint, section or namespace cannot donate those roles.'})
    return uses


def _experiment_mean_gains(descriptors,paragraphs,chapters,epochs,section):
    """Named baselines, actual mean cells and one section own the comparison.

    Reported precision uses exact decimal quantization, never a similarity
    tolerance. A different physical experiment cannot lend the same numbers.
    """
    from decimal import Decimal,InvalidOperation,ROUND_HALF_UP
    from .usage_table_evidence import _explicit_table_numbers,_table_pointer_agrees
    candidates=[]
    for d in descriptors:
        if not re.search(r'精度|准确率|\baccuracy\b',d['title'],re.I):continue
        records=d.get('_axis_matrix') or _axis_numeric_matrix(d)
        mean=[r for r in records if re.fullmatch(r'mean|average|avg\.?|平均(?:值|精度|准确率)?',r['metric'],re.I)]
        owners={r['owner'] for r in mean}
        if len(owners)<3 or any(sum(r['owner']==owner for r in mean)!=1 for owner in owners):continue
        own=[r for r in mean if re.search(r'(?:^|[-_\s])ours?$',r['owner'],re.I)]
        if len(own)!=1:continue
        own=own[0]
        match=re.fullmatch(r'(.+)[-_]ours?',own['owner'],re.I)
        if not match:continue
        qualifier=match[1]
        baseline=[]
        for r in mean:
            if not r['owner'].startswith(qualifier+'-') and not r['owner'].startswith(qualifier+'_'):continue
            alias=r['owner'][len(qualifier)+1:]
            if re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',alias) and not re.fullmatch(r'ours?',alias,re.I):baseline.append((alias,r))
        if len(baseline)<2:continue
        fields={r['metric'] for r in records if r['owner']==own['owner'] and r not in mean}
        if len(fields)<2:continue
        try:own_value=Decimal(own['value'])
        except InvalidOperation:continue
        for body in paragraphs:
            if epochs[id(body)]!=d['usage_epoch'] or section(body)!=section(d['target'].line):continue
            if chapters.get(body.page_number)!=chapters.get(d['target'].line.page_number):continue
            if not _table_pointer_agrees(d,_explicit_table_numbers(body.text)):continue
            text=normalize_text(body.text)
            if not re.search(r'平均精度|平均准确率|mean\s+accuracy|average\s+accuracy',text,re.I):continue
            if not re.search(r'我们的方法|本文方法|所提方法|our\s+method|proposed\s+method',text,re.I):continue
            task_count=re.search(r'(\d+)\s*(?:种|个)\s*下游任务|(\d+)\s+downstream\s+tasks?',text,re.I)
            if not task_count or int(task_count[1] or task_count[2])!=len(fields):continue
            pairs=[]
            for alias,record in baseline:
                hits=list(re.finditer(r'(?<![A-Za-z0-9_])'+re.escape(alias)+r'(?![A-Za-z0-9_])',text,re.I))
                if len(hits)!=1:continue
                hit=hits[0]
                next_starts=[m.start() for other,_ in baseline if other!=alias
                    for m in re.finditer(r'(?<![A-Za-z0-9_])'+re.escape(other)+r'(?![A-Za-z0-9_])',text,re.I) if m.start()>hit.end()]
                claim=text[hit.end():min(next_starts) if next_starts else len(text)]
                claim=re.split(r'[。；;!?]',claim,maxsplit=1)[0]
                if not re.search(r'相比|相较|compared',text[max(0,hit.start()-25):hit.end()]+claim,re.I):continue
                direction=re.search(r'提升|提高|增加|improv|increas|gains?|下降|降低|decreas|drops?',claim,re.I)
                values=list(re.finditer(r'(?<![A-Za-z0-9_.])([+-]?\d+(?:\.\d+)?)(%?)(?![A-Za-z0-9_.])',claim))
                if not direction or len(values)!=1 or values[0][2]:continue
                value=values[0][1]
                try:
                    native=Decimal(record['value']);reported=Decimal(value)
                    difference=own_value-native
                    sign=-1 if re.search(r'下降|降低|decreas|drops?',direction[0],re.I) else 1
                    quantum=Decimal(1).scaleb(reported.as_tuple().exponent)
                    if difference*sign<=0 or abs(difference).quantize(quantum,rounding=ROUND_HALF_UP)!=reported:continue
                except InvalidOperation:continue
                pairs.append({'baseline_alias':alias,'baseline_cell':record,'our_mean_cell':own,
                              'exact_difference':str(difference),'reported_difference':value,
                              'reported_decimal_quantum':str(quantum),'body_claim':claim})
            if len(pairs)<2:continue
            # The preceding independent introduction supplies the model and
            # native shared row qualifier; it supplies no outcome numbers.
            introductions=[p for p in paragraphs if (p.page_number,p.bbox[3])<(body.page_number,body.bbox[1])
                and epochs[id(p)]==d['usage_epoch'] and section(p)==section(body)
                and _table_pointer_agrees(d,_explicit_table_numbers(p.text))
                and _present(qualifier,p.text)
                and all(_present(pair['baseline_alias'],p.text) for pair in pairs)
                and _subject_agrees(d['title'],p.text+' '+body.text)]
            if not introductions:continue
            intro=max(introductions,key=lambda p:(p.page_number,p.bbox[3]))
            candidates.append((d,body,intro,pairs))
    used={}
    for d,body,intro,pairs in candidates:
        if any(other['i']!=d['i'] and other_body is body for other,other_body,_,_ in candidates):continue
        target=d['target']
        used.setdefault(d['i'],{
            'physical_key':{'number':target.number,'page':target.line.page_number,'caption_bbox':list(target.line.bbox),'scope':target.scope},
            'usage_epoch':d['usage_epoch'],'title':d['title'],
            'body':{'page':body.page_number,'bbox':list(body.bbox),'text':body.text},
            'body_context':[{'page':intro.page_number,'bbox':list(intro.bbox),'text':intro.text}],
            'cell_evidence':[{'page':l.page_number,'bbox':list(l.bbox),'text':l.text} for l in d['cells']],
            'kind':'owned_task_mean_and_two_baseline_comparisons_in_one_experiment',
            'matched_fields':[pair['baseline_cell']['owner']+' / '+pair['baseline_cell']['metric'] for pair in pairs],
            'matched_values':[pairs[0]['our_mean_cell']['value'],*[pair['baseline_cell']['value'] for pair in pairs]],
            'relations':pairs,
            'uniqueness_reason':'The model introduction, printed common row qualifier, task count and two signed mean comparisons belong to this physical experiment section. Duplicate values in another experiment do not borrow its prose.'})
    return used


def _chronological_partition_uses(descriptors,paragraphs,chapters,epochs):
    """Bind a full chronological split to its printed dataset and interval.

    An independent global description can use this main purpose without
    restating every transition date. Its actual dataset introduction must
    retain the full source interval, and all compatible physical partitions
    compete. No date, role, identity or use is manufactured from the caption.
    """
    from datetime import date,timedelta
    from .usage_table_evidence import _explicit_table_numbers,_table_pointer_agrees
    roles=(r'训练集|\btrain(?:ing)?(?:\s+set)?\b',r'验证集|\bvalidation(?:\s+set)?\b',r'测试集|\btest(?:\s+set)?\b')
    def owner_present(owner,text):
        if owner.isascii():return _present(owner,text)
        return bool(re.search(r'(?:^|基于|使用|采用|对于|对|来自|关于|本|[，。;；、,])'+re.escape(_norm(owner))+
                              r'(?=\d|数据|的|[，。;；、,]|$)',_norm(text)))
    def dates(text):
        result=[]
        for match in re.finditer(r'(?<!\d)(\d{4})\s*(?:年|[-/.])\s*(\d{1,2})\s*(?:月|[-/.])\s*(\d{1,2})\s*日?(?!\d)',normalize_text(text)):
            try:result.append((match,date(*map(int,match.groups()))))
            except ValueError:continue
        return result
    partitions=[]
    for d in descriptors:
        if not re.search(r'数据集.*(?:划分|切分)|dataset.*(?:split|partition)',d['title'],re.I):continue
        grid=d.get('_catalogue_grid') or _grid(d['cells'])
        if not grid or len(grid[0])!=3:continue
        if not re.search(r'起始|开始|start',grid[0][1].text,re.I) or not re.search(r'结束|终止|end',grid[0][2].text,re.I):continue
        rows=d.get('_native_relation_rows') or _relation_rows(d['cells'])
        if len(rows)!=3 or any(not re.fullmatch(rx,row['name'],re.I) for rx,row in zip(roles,rows)):continue
        intervals=[]
        for row in rows:
            values=[dates(text) for text in row['purposes']]
            if len(values)!=2 or any(len(value)!=1 for value in values):intervals=[];break
            intervals.append((values[0][0][1],values[1][0][1]))
        if len(intervals)!=3 or any(a>b for a,b in intervals):continue
        if any(intervals[i][1]+timedelta(days=1)!=intervals[i+1][0] for i in range(2)):continue
        start,end=intervals[0][0],intervals[-1][1]
        target=d['target'].line
        contexts=[]
        for p in paragraphs:
            if epochs[id(p)]!=d['usage_epoch'] or chapters.get(p.page_number)!=chapters.get(target.page_number):continue
            if not (p.page_number==target.page_number-1 or p.page_number==target.page_number and p.bbox[3]<target.bbox[1]):continue
            if not _table_pointer_agrees(d,_explicit_table_numbers(p.text)):continue
            printed=dates(p.text)
            if len(printed)!=2 or [value for _,value in printed]!=[start,end]:continue
            text=normalize_text(p.text)
            tail=text[printed[-1][0].end():]
            chinese=re.match(r'\s*的?\s*([^,，。;；]+?)\s*数据',tail)
            if chinese:
                owner=re.sub(r'日频|月频|年频|周频','',chinese[1]).strip()
            else:
                english=re.search(r'([A-Za-z][A-Za-z0-9_-]*(?:\s+[A-Za-z][A-Za-z0-9_-]*){0,3})\s+(?:dataset|corpus)\b',text[:printed[0][0].start()],re.I)
                owner=re.sub(r'^(?:the|our|this)\s+','',english[1],flags=re.I) if english else ''
            if len(_norm(owner))>=3 and re.search(r'数据集|dataset|corpus',text,re.I):contexts.append((p,owner))
        context=max(contexts,key=lambda item:(item[0].page_number,item[0].bbox[3])) if contexts else None
        partitions.append((d,rows,intervals,context))
    candidates=[]
    for d,rows,intervals,context in partitions:
        if context is None:continue
        intro,owner=context;start,end=intervals[0][0],intervals[-1][1]
        for body in paragraphs:
            if epochs[id(body)]!=d['usage_epoch'] or not owner_present(owner,body.text):continue
            if not _table_pointer_agrees(d,_explicit_table_numbers(body.text)):continue
            text=normalize_text(body.text)
            if not re.search(r'按时间顺序|chronological|time[-\s]+ordered|temporally\s+ordered',text,re.I):continue
            if re.search(r'随机|不按时间|random|not\s+chronological',text,re.I):continue
            mentions=[re.search(rx,text,re.I) for rx in roles]
            if any(m is None for m in mentions) or [m.start() for m in mentions]!=sorted(m.start() for m in mentions):continue
            contradicts=False
            for role,(native_start,native_end) in zip(roles,intervals):
                for mention in re.finditer(role,text,re.I):
                    declared=re.match(r'\s*(?:为|覆盖|使用|从|自|covers?|starts?)?\s*(\d{4})(?:\s*[-–—]\s*(\d{4})(?!\d))?',text[mention.end():],re.I)
                    if declared and (not native_start.year<=int(declared[1])<=native_end.year
                         or declared[2] and (int(declared[1]),int(declared[2]))!=(native_start.year,native_end.year)):
                        contradicts=True
            if contradicts:continue
            stated_dates=dates(text)
            years=re.search(r'(?<!\d)(\d{4})\s*[-–—]\s*(\d{4})(?!\d)',text)
            if stated_dates:
                values=[value for _,value in stated_dates]
                if values!=[start,end] and values!=[value for interval in intervals for value in interval]:continue
            elif not years or (int(years[1]),int(years[2]))!=(start.year,end.year):continue
            compatible=[other for other,_,other_intervals,other_context in partitions
                if other['i']!=d['i'] and other['usage_epoch']==d['usage_epoch']
                and (other_intervals[0][0],other_intervals[-1][1])==(start,end)
                and (other_context is None or _norm(other_context[1])==_norm(owner))]
            if compatible:continue
            candidates.append((d,rows,intervals,intro,body,owner))
    used={}
    for d,rows,intervals,intro,body,owner in candidates:
        target=d['target']
        used.setdefault(d['i'],{
            'physical_key':{'number':target.number,'page':target.line.page_number,'caption_bbox':list(target.line.bbox),'scope':target.scope},
            'usage_epoch':d['usage_epoch'],'title':d['title'],
            'body':{'page':body.page_number,'bbox':list(body.bbox),'text':body.text},
            'body_context':[{'page':intro.page_number,'bbox':list(intro.bbox),'text':intro.text}],
            'cell_evidence':[{'page':l.page_number,'bbox':list(l.bbox),'text':l.text} for l in d['cells']],
            'kind':'actual_dataset_interval_and_chronological_partition_role_order',
            'matched_fields':[row['name'] for row in rows],
            'matched_values':[value.isoformat() for interval in intervals for value in interval],
            'relations':[{'dataset_owner':owner,'ordered_roles':[row['name'] for row in rows],
                          'native_intervals':[[a.isoformat(),b.isoformat()] for a,b in intervals]}],
            'uniqueness_reason':'Independent prose describes this dataset and overall source interval being split chronologically into the three printed roles. Another compatible physical partition, wrong interval, reordered role or different dataset cannot obtain this use.'})
    return used


def _interface_contract_rows(descriptor):
    """Read typed inputs from the native row, bounded between row centers.

    The earlier generic catalogue window starts at the middle of a tall row.
    It is adequate for the aligned purpose column but cannot own that row's
    first input lines. Never use the next method's inputs to prove an operation.
    """
    grid=descriptor.get('_catalogue_grid') or _grid(descriptor['cells'])
    if not grid:return []
    header,columns=grid
    if len(columns)<3:return []
    inputs=next((i for i,l in enumerate(header) if re.search(r'输入|参数|inputs?|parameters?',l.text,re.I)),None)
    if inputs is None:return []
    rows=[r for r in _relation_rows(descriptor['cells']) if _aliases(r['name'])[1]]
    centers=[(r['anchor'].bbox[1]+r['anchor'].bbox[3])/2 for r in rows]
    result=[]
    for i,row in enumerate(rows):
        top=(centers[i-1]+centers[i])/2 if i else max(l.bbox[3] for l in header)
        bottom=(centers[i]+centers[i+1])/2 if i+1<len(rows) else float('inf')
        own=[l for l in columns[inputs] if top<=(l.bbox[1]+l.bbox[3])/2<bottom]
        result.append({'name':row['name'],'purpose':row['purposes'][-1] if row['purposes'] else '',
                       'input_text':' '.join(l.text for l in own),
                       'input_ink':[{'page':l.page_number,'bbox':list(l.bbox),'text':l.text} for l in own]})
    return result


def _interface_domains(purpose):
    # The operation and modality supply typed roles; the remainder supplies
    # the particular acquired entity. A shared word such as data/API/image
    # cannot by itself identify the table's actual input or output object.
    value=_norm(purpose)
    value=re.sub(r'获取|采集|调用|拍摄|捕获|导出|网络|网页|网站|图像|图片|信息|数据|接口|中心|企业|内置|内部|执行|系统|来源',' ',value)
    chinese=[x for x in re.findall(r'[\u4e00-\u9fff]+',value) if len(x)>=2]
    ordinary={'acquire','acquires','acquisition','capture','captures','capturing','call','calls','retrieve','retrieves',
              'fetch','fetches','collect','collects','data','information','images','image','photos','photo',
              'pictures','picture','network','web','online','center','centre','source','sources','from','using','with',
              'interfaces','interface','api','internal','external','database','server','servers',
              'the','and','for','into','via','this','that','these','those','use','uses','used'}
    english=[x.casefold() for x in re.findall(r'[A-Za-z][A-Za-z0-9_-]*',normalize_text(purpose)) if len(x)>=3 and x.casefold() not in ordinary]
    return list(dict.fromkeys([*chinese,*english]))


def _acquisition_interface_pairs(descriptor,text):
    if not _interface_title_agrees(descriptor,text):return []
    if not re.search(r'采集|\bacquisition\b|\bcollect',descriptor['title'],re.I):return []
    pairs=[]
    for row in descriptor['_interface_rows']:
        purpose=normalize_text(row['purpose'])+' '+_norm(row['purpose']);role=None
        if re.search(r'接口|(?<![A-Za-z0-9_])api(?![A-Za-z0-9_])',purpose,re.I) and re.search(r'调用|获取|call|acquir|retriev',purpose,re.I):role='external_api_acquisition'
        elif re.search(r'图像|图片|images?|photos?|pictures?',purpose,re.I) and re.search(r'采集|拍摄|捕获|获取|captur|collect|acquir',purpose,re.I):role='camera_image_acquisition'
        if role is None:continue
        domains=_interface_domains(row['purpose'])
        if not domains:continue
        for clause in re.split(r'[。.!?；;]',normalize_text(text)):
            if re.search(r'(?:不|未|没有|无需|无须)(?:采用|使用|运行|调用|拍摄|采集|获取)|\b(?:not|never|without)\b',clause,re.I):continue
            hits=[x for x in domains if _present(x,clause)]
            if not hits:continue
            if not any(re.search(r'[\u4e00-\u9fff]',x) for x in domains) and len(hits)!=len(domains):continue
            if role=='external_api_acquisition':
                operation=bool(re.search(r'接口|(?<![A-Za-z0-9_])api(?![A-Za-z0-9_])',clause,re.I) and re.search(r'调用|获取|call|acquir|retriev|fetch',clause,re.I))
                if re.search(r'中心|cent(?:er|re)',purpose,re.I) and not re.search(r'中心|cent(?:er|re)',clause,re.I):operation=False
                function_role=r'api'
            else:
                operation=bool(re.search(r'图像|图片|images?|photos?|pictures?',clause,re.I) and re.search(r'拍摄|捕获|captur|photograph',clause,re.I))
                function_role=r'captur|camera|images?|photos?'
            functions=re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\s*\(',clause)
            own=_aliases(row['name'])[0]
            if any(re.search(function_role,f,re.I) and f not in own for f in functions):operation=False
            if operation:
                pairs.append({'field':row['name'],'role':role,'actual_purpose':row['purpose'],
                              'actual_entities':hits,'body_claim':clause.strip()})
                break
    return pairs


def _algorithm_interface_use(descriptor,text):
    if not _interface_title_agrees(descriptor,text):return None
    if re.search(r'(?:不|未|没有|无需|无须)(?:采用|使用|运行)|\b(?:not|never|without)\b',text,re.I):return None
    rows=descriptor['_interface_rows']
    initializers=[r for r in rows if re.search(r'初始化|initializ',r['purpose'],re.I)]
    detectors=[r for r in rows if re.search(r'社区检测|community\s*detection',normalize_text(r['purpose']),re.I)]
    for initializer in initializers:
        algorithm=re.sub(r'^\s*(?:初始化|initializ(?:e|es|ation|ing))\s*','',normalize_text(initializer['purpose']),flags=re.I).strip()
        if len(_norm(algorithm))<4 or not _present(algorithm,text):continue
        if not re.search(r'\bgraph\b|输入图数据',initializer['input_text'],re.I):continue
        for detector in detectors:
            if not re.search(r'\bgraph\b|输入图数据',detector['input_text'],re.I):continue
            relocation=bool(re.search(r'节点[^。.!?]{0,60}(?:归入|并入|合并)[^。.!?]{0,20}社区|'
                 r'nodes?[^.!?]{0,60}(?:assign|mov|merg)[^.!?]{0,40}communit',text,re.I))
            aggregation=bool(re.search(r'社区聚合|社区合并|communit(?:y|ies)\s*(?:aggregation|merg)',text,re.I))
            if not (relocation and aggregation):continue
            functions=re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\s*\(',text)
            if any(re.search(r'communit',f,re.I) and f not in _aliases(detector['name'])[0] for f in functions):continue
            return {'kind':'printed_algorithm_and_owned_graph_operating_purpose',
                    'matched_fields':[initializer['name'],detector['name']], 'matched_values':[algorithm],
                    'relations':[{'algorithm':algorithm,'initialize_row':initializer,'detect_row':detector,
                                  'body_operations':['nodes assigned to a community','community aggregation']} ]}
    return None


def _schema_columns(descriptor):
    grid=descriptor['_catalogue_grid'] if '_catalogue_grid' in descriptor else _grid(descriptor['cells'])
    if not grid:
        return None
    header,columns=grid
    field=next((i for i,l in enumerate(header) if re.search(r'字段|\bfield\b',l.text,re.I)),None)
    meaning=next((i for i,l in enumerate(header) if re.search(r'含义|meaning|description',l.text,re.I)),None)
    types=next((i for i,l in enumerate(header) if re.search(r'类型|\btype\b',l.text,re.I)),None)
    if field is None or meaning is None or types is None:
        return None
    result=[]
    for line in columns[field]:
        cy=(line.bbox[1]+line.bbox[3])/2
        meanings=[l for l in columns[meaning] if abs((l.bbox[1]+l.bbox[3])/2-cy)<=max(3,(line.font_size or 10)*.5)]
        if meanings:
            result.append({'field':line.text,'meaning':' '.join(l.text for l in meanings)})
    return result


def _schema(descriptor,text):
    fields=_schema_columns(descriptor)
    if not fields or not re.search(r'记录|存储|stores?|records?',text,re.I):
        return None
    prefix=re.split(r'[:：]',normalize_text(text),maxsplit=1)[0]
    prefix=re.sub(r'^\s*[（(]?\d+[）)]?\s*','',prefix).strip()
    named=bool(prefix and len(prefix)<60 and _norm(prefix) in _norm(' '.join(_primary_subjects(descriptor['title']))))
    pairs=[]
    if named:
        for field in fields:
            meaning=normalize_text(field['meaning'])
            aliases=[meaning,re.sub(r'(?i)\bid\b|编号|标识','',meaning).strip()]
            # ID fields specify an entity relation; the prose can use its
            # ordinary noun while the schema supplies the typed identifier.
            if re.search(r'id|编号|标识',meaning,re.I):
                aliases.append(re.sub(r'(?i)id|编号|标识','',meaning).replace('数据集','数据').strip())
            hits=[a for a in aliases if len(_norm(a))>=2 and _present(a,text)]
            if hits:
                pairs.append({'field':field['field'],'meaning':meaning,'body_terms':hits})
        if len({p['field'] for p in pairs})>=2:
            return {'kind':'named_schema_entity_and_fields','matched_fields':[p['field'] for p in pairs],
                    'matched_values':[],'relations':pairs,'requires_adjacent_introduction':True}
    # Stored result-to-document flow can distinguish schemas even when an
    # author's caption accidentally duplicates another schema's title.
    if re.search(r'基于[^。.!?]{0,35}结果[^。.!?]{0,35}(?:存储|记录)[^。.!?]{0,35}(?:报告|文章)|'
                 r'based[^.!?]{0,50}results?[^.!?]{0,50}(?:store|record)[^.!?]{0,50}(?:report|article|document)',text,re.I):
        inputs=[f for f in fields if re.search(r'结果.*(?:id|编号|标识)|result.*(?:id|identifier)',f['meaning']+' '+f['field'],re.I)]
        outputs=[]
        for field in fields:
            if not re.search(r'文章|报告|article|report|document',field['meaning'],re.I):
                continue
            topic=re.sub(r'文章|报告|结果|信息|article|report|document|result|information','',field['meaning'],flags=re.I).strip()
            if len(_norm(topic))>=2 and _present(topic,text):
                outputs.append(field)
        if inputs and outputs:
            return {'kind':'schema_result_input_and_distinct_document_output',
                    'matched_fields':[inputs[0]['field'],outputs[0]['field']], 'matched_values':[],
                    'relations':[{'input':inputs[0],'output':outputs[0]}],
                    'requires_adjacent_introduction':True}
    return None


_PROPERTIES=(('光泽|粗糙',r'光泽|粗糙感|sheen|gloss|roughness'),
             ('纹理|凹凸',r'纹理|凹凸|texture|bump'),
             ('颜色|色彩',r'颜色|色彩|colour|color'),
             ('反射|金属',r'反射|金属|reflect|metal'))

_SEMANTIC_TITLE_FILLER={'data','building','interface','interfaces','tool','tools',
    'component','components','material','materials','parameter','parameters',
    'effect','effects','influence','garment','garments','schema','entity','entities',
    'field','fields','information','archive','management','function','functions',
    'purpose','purposes','description','descriptions','key','configuration',
    'configurations','implementation','training','encoder','encoders','core',
    'deployment','scaling','criteria','monitoring','metric','metrics','llm',
    'traditional','active','learning','binary','feedback','new','detailed',
    'architecture','specifications','specification','multidimensional','multi-dimensional',
    'extraction','dynamic','narrative','graph','construction',
    'overview','used','status','characteristics','characteristic','classification',
    'flow','features','dimensions','dimension','extracted','eye','movement',
    'evidence','return','forms','form','investigators','investigator',
    'investigation','different','notations','notation','formulas','formula','segmentation',
    'comprehensive','open-set','filtering','measured','unified','all','parallel',
    'collaborative','structure','structures','struc','ture','protection','via','digital','transmission',
    'defense','optimisation','optimization','stages','paths','results','along','across','recognition','aggregation',
    'impact','internal','signal','signals','strategy','strategies','hallucination','mitigation','reward','unsupervised',
    'knowledge','context','quality','under','retrieval','gnn','long','text','understanding','aggregate','symbol','symbols',
    'social','propagation','simulation'}


def _subject_agrees(title,text):
    from .usage_table_evidence import _title_agrees,_TOPICS
    # Title-case ordinary schema/interface nouns are not named data sets.
    # Preserve every remaining name and the existing topic constraints.
    primary=' '.join(_primary_subjects(title))
    primary=re.split(r'需要特别说明(?:的是)?|注[：:]|\bNote\s*:',primary,maxsplit=1,flags=re.I)[0]
    topic_patterns=[(a,b+r'|移除|去除|\bremove[ds]?\b' if a==r'ablation|消融' else b) for a,b in _TOPICS]
    if any(re.search(a,primary,re.I) and not re.search(b,text,re.I) for a,b in topic_patterns):return False
    identities=[m[1] for m in re.finditer(r'(?i:\b(?:on|using|within)\s+(?:the\s+)?)([A-Z][A-Za-z0-9_-]*)',primary)]
    # "on Hallucination Detection Performance" names an experimental
    # topic, not a dataset named Hallucination. An ordinary-word dataset
    # such as "on Overview" still retains its explicit identity.
    identities=[value for value in identities if not (value.casefold()=='hallucination' and
                re.search(r'\bon\s+Hallucination\s+(?:Detection|Mitigation)\s+Performance\b',primary,re.I))]
    if re.search(r'移除|去除|\bremove[ds]?\b',text,re.I):primary=re.sub(r'\bablation\b|消融','',primary,flags=re.I)
    # A coordinated percentile panel list is a native measurement axis,
    # not multiple named datasets that prose must mention simultaneously.
    primary=re.sub(r'\bTop[-\s]*\d+\s*%','',primary,flags=re.I)
    primary=re.sub(r'([A-Za-z]{2,})-\s+([a-z])',r'\1\2',primary)
    primary=re.sub(r'(?i)distinct[-\s]*n\b(?![-\s]*grams\b)','Distinct',primary)
    primary=re.sub(r'\bdifferent\s+(?:experimental\s+)?methods\b','',primary,flags=re.I)
    primary=re.sub(r'[A-Za-z][A-Za-z0-9_-]*',lambda m:'' if m[0].casefold() in _SEMANTIC_TITLE_FILLER else m[0],primary)
    return _title_agrees(primary+' '+' '.join(identities),text)


def _named_values(text):
    names=[]
    for match in re.finditer(r'(?:\d+[A-Z]|[A-Z][A-Za-z\d_-]*)(?:\s+[A-Z][A-Za-z\d_-]*)*',text):
        name=match[0].strip();names.append(name)
        parts=name.split();prefix=[]
        if parts and re.fullmatch(r'\d+[A-Z]+',parts[0]):prefix=[parts.pop(0)]
        # Derive a native phrase's conventional short form from its own words,
        # retaining a dimension prefix and every following word's initial.
        if len(parts)>=2 and all(len(p)>=3 for p in parts):
            abbreviation=parts[0][:2]+''.join(p[0] for p in parts[1:])
            names.append(' '.join([*prefix,abbreviation]))
    return list(dict.fromkeys(n for n in names if len(_norm(n))>=3))


def _catalogue_properties(descriptor,text):
    """Named native descriptive rows own their fields and separate properties.

    This is a catalogue/definition path, not an untyped bag of numbers. A
    performance matrix cannot qualify through a shared method name. Each
    property is taken from the real named row, and owner windows cannot borrow
    another row's descriptions. Explicit conflicting shapes/counts veto it.
    """
    if re.search(r'配置|configuration|settings?|architecture|specifications?',descriptor['title'],re.I):return None
    grid=descriptor['_catalogue_grid'] if '_catalogue_grid' in descriptor else _grid(descriptor['cells'])
    if not grid:return None
    headers=[normalize_text(l.text) for l in grid[0]]
    if any(re.fullmatch(r'符号|Symbols?|Notation',h.strip(),re.I) for h in headers):return None
    if not any(re.search(r'描述|说明|含义|特点|特征|优势|优点|局限|限制|范围|规约|返回|description|meaning|characteristic|features?|properties|range|forms?',h,re.I)
               for h in headers[1:]):return None
    if any(re.search(r'accuracy|recall|precision|F1|IoU|准确率|精确率|召回率',h,re.I) for h in headers):return None
    rows=descriptor['_native_relation_rows'] if '_native_relation_rows' in descriptor else _relation_rows(descriptor['cells'])
    def aliases(row):
        name=normalize_text(row['name']).strip()
        stem=re.sub(r'\s*[（(][^）)]*[）)]\s*$','',name).strip()
        return list(dict.fromkeys([name,stem])) if len(_norm(stem))>=3 else [name]
    pairs=[]
    for owner,name,claim in _body_windows(rows,text,aliases,sentence_bound=False):
        row=rows[owner];source=' ; '.join(row['purposes'])
        if not re.search(r'[A-Za-z]{3}|[\u4e00-\u9fff]{2}',name):continue
        if re.search(r'不包含|不具备|不是|不用于|does\s+not|not\s+(?:contain|include|have|use)',claim,re.I):continue
        def shapes(value):
            return {tuple(re.findall(r'\d+',m[0])) for m in re.finditer(r'\d+\s*[×x]\s*\d+(?:\s*[×x]\s*\d+)?',value)}
        actual_shapes=shapes(source)
        if actual_shapes and shapes(claim)-actual_shapes:continue
        def classes(value):
            return {int(m[1]) for m in re.finditer(r'(\d+)\s*(?:个\s*)?(?:细粒度\s*)?(?:类别|classes?\b)',value,re.I)}
        actual_classes=classes(source)
        if actual_classes and classes(claim)-actual_classes:continue
        # Distinct native clauses/columns are independent properties. A long
        # matching sentence contributes only one property, however many
        # overlapping substrings it contains.
        properties=[]
        for ci,value in enumerate(row['purposes']):
            pieces=re.split(r'[;；、，,]|(?:^|\s)\d+[.、]\s*|[•●]',normalize_text(value))
            for piece in pieces:
                phrases=_content_phrases(piece,claim)
                # A three-character descriptive noun is a real property
                # when its named row owns the prose. Acronyms in descriptive
                # cells (rather than owner names) can distinguish a location
                # or protocol attribute, but never supply a value on their own.
                a,b=_norm(piece),_norm(claim)
                phrases.extend(a[m.a:m.a+m.size] for m in SequenceMatcher(None,a,b,autojunk=False).get_matching_blocks()
                               if m.size==3 and re.fullmatch(r'[\u4e00-\u9fff]{3}',a[m.a:m.a+m.size])
                               and not re.search(r'[的与和及为于]$',a[m.a:m.a+m.size]))
                phrases.extend(token for token in re.findall(r'(?<![A-Za-z0-9])[A-Z0-9][A-Z0-9_-]{2,}(?![A-Za-z0-9])',piece)
                               if _present(token,claim))
                phrases=[p for p in phrases if p not in {'文本内容','图像数据','输入数据','数据集','系统信息','配置参数'}]
                if phrases:properties.append({'column':headers[ci+1] if ci+1<len(headers) else str(ci),
                                              'actual_property':piece.strip(),'body_phrases':phrases})
        # A schema's actual field identifiers alone are insufficient. At
        # least two distinct identifiers and two actual meanings are used.
        fields=[]
        for ci,h in enumerate(headers[1:]):
            if re.search(r'字段|\bfields?\b',h,re.I) and ci<len(row['purposes']):
                fields=[a for a in re.findall(r'[A-Za-z_][A-Za-z0-9_]*',row['purposes'][ci]) if _present(a,claim)]
                if len(set(fields))<2:properties=[]
        independent=[];seen=set()
        for prop in properties:
            tokens={_norm(p) for p in prop['body_phrases']}
            if tokens-seen:independent.append(prop);seen.update(tokens)
        properties=independent
        if len(properties)>=2 and any(re.search(r'[\u4e00-\u9fff]{3}',p) or len(_norm(p))>=5
                                      for prop in properties for p in prop['body_phrases']):
            pairs.append({'row':row['name'],'body_name':name,'body_claim':claim,
                          'properties':properties,'actual_fields':fields})
    if not pairs:return None
    return {'kind':'actual_named_catalogue_fields_and_distinct_properties',
            'matched_fields':[p['row'] for p in pairs],'matched_values':[], 'relations':pairs}


_MEASUREMENT_ALIASES=(
    (r'F1',('F1','F1 score','F1分数')),
    (r'IoU|交并比',('IoU','交并比')),
    (r'precision|精确率',('precision','精确率')),
    (r'recall|召回率',('recall','召回率')),
    (r'FPS|帧率',('FPS','帧率')),
    (r'Mean\s*\(ms\)|帧时',('帧时','frame time')),
)


def _numeric_row_matrix(descriptor):
    """Real native row labels and x-owned measurements; retain header levels."""
    from .usage_table_evidence import _cell_rows,_NUMBER,_GENERIC
    rows=_cell_rows(descriptor['cells']);data=[]
    ordinary=_GENERIC|_SEMANTIC_TITLE_FILLER|{'metric','metrics','指标','方法','模型','参数','优化阶段'}
    for cells in rows:
        numbers=[l for l in cells if _NUMBER.fullmatch(normalize_text(l.text).strip())]
        if not numbers:continue
        left=min(l.bbox[0] for l in numbers)
        owners=[l for l in cells if l.bbox[2]<left-8 and len(l.text)<80 and
                re.search(r'[A-Za-z][A-Za-z0-9_-]+|[\u4e00-\u9fff]{2}',l.text) and
                _norm(l.text) not in ordinary and not re.search(r'^(?:ASR|CACC|F1|IoU|EM|EX)\s*[↑↓]?$',l.text,re.I)]
        if not owners:continue
        owner=min(owners,key=lambda l:l.bbox[0])
        data.append({'name':normalize_text(owner.text).strip(),'anchor':owner,'numbers':numbers})
    if len(data)<2:return []
    top=min(r['anchor'].bbox[1] for r in data)
    headings=[sorted(r,key=lambda l:l.bbox[0]) for r in rows if max(l.bbox[3] for l in r)<top+1]
    for row in data:
        entries=[]
        for cell in row['numbers']:
            x=(cell.bbox[0]+cell.bbox[2])/2
            levels=[]
            for heading in headings:
                words=[l for l in heading if l.bbox[0]>row['anchor'].bbox[2]+4 and
                       re.search(r'[A-Za-z\u4e00-\u9fff]',l.text)]
                if not words:continue
                centers=[(l.bbox[0]+l.bbox[2])/2 for l in words]
                nearest=min(range(len(words)),key=lambda i:abs(x-centers[i]))
                # A multi-level parent occupies the band between its sibling
                # centers. The leaf level must be close to the value column.
                left=(centers[nearest-1]+centers[nearest])/2 if nearest else words[nearest].bbox[0]-60
                right=(centers[nearest]+centers[nearest+1])/2 if nearest+1<len(words) else words[nearest].bbox[2]+60
                if left<=x<=right:levels.append(normalize_text(words[nearest].text).strip(' ↑↓'))
            if levels:entries.append({'headers':list(dict.fromkeys(levels)),'value':normalize_text(cell.text).strip(),
                                      'bbox':list(cell.bbox)})
        row['entries']=entries
    return data


def _row_aliases(row):
    name=normalize_text(row['name']).strip()
    name=re.sub(r'^\s*\d+[.)、]\s*','',name)
    names=[name,re.sub(r'\s*[（(].*?[）)]\s*','',name).strip()]
    names.extend(re.findall(r'[（(]([^）)]+)[）)]',name))
    if re.search(r'^(?:ours?|propos\w*|本文方法|所提方法)\b',name,re.I):
        names.extend(['本文方法','所提方法','本文提出的方法','ours','our method','proposed method'])
    return list(dict.fromkeys(n for n in names if len(_norm(n))>=2))


def _axis_numeric_matrix(descriptor):
    """Keep native row qualifiers, checked stages and transposed method axes.

    The values always retain their original ink box.  A vertically merged
    categorical cell owns the band halfway to its actual neighbouring cells;
    it is never carried forward into an unrelated table or another panel.
    """
    from .usage_table_evidence import _cell_rows,_NUMBER
    source=descriptor['cells'];rows=_cell_rows(source)
    measured=[r for r in rows if sum(bool(_NUMBER.fullmatch(normalize_text(l.text).strip())) for l in r)>=2]
    data=[]
    for row in measured:
        labels=[l for l in row if not _NUMBER.fullmatch(normalize_text(l.text).strip()) and re.search(r'[A-Za-z\u4e00-\u9fff]',l.text)]
        values=[normalize_text(l.text).strip() for l in sorted(row,key=lambda l:l.bbox[0]) if _NUMBER.fullmatch(normalize_text(l.text).strip())]
        # A numeric n-gram header (1,2,3,...) beside sibling stage headings
        # is a leaf axis, rather than the first measured model row.
        ordinal_header=len(labels)>=2 and values==[str(j) for j in range(1,len(values)+1)]
        if labels and not ordinal_header:data.append(row)
    if len(data)<2:return []
    top=min(l.bbox[1] for r in data for l in r)
    header_rows=[]
    for row in rows:
        labels=[normalize_text(l.text).strip() for l in row]
        indices=[t for t in labels if t.isdigit()]
        ordinal=bool(indices) and any(re.search(r'distinct[-\s]*n',l.text,re.I) for l in source) and indices==[str(j) for j in range(1,len(indices)+1)]
        if (len(row)>=2 and not any(re.search(r'^[+-]?\d+(?:\.\d+)?\s*(?:[BMGT]|GB|MB|KB)\b',t,re.I) for t in labels)
                and (not any(_NUMBER.fullmatch(t) for t in labels) or ordinal)
                and all(len(t)<80 and not re.search(r'^[注]|[。;；]',t) for t in labels)):
            header_rows.append(sorted(row,key=lambda l:l.bbox[0]))
    headings=[r for r in header_rows if max(l.bbox[3] for l in r)<top+1]
    if not headings:return []
    number_left=min(l.bbox[0] for r in data for l in r if _NUMBER.fullmatch(normalize_text(l.text).strip()))
    metric_heading=next((l for r in headings for l in r if re.fullmatch(r'指标|metric',l.text.strip(),re.I)),None)
    transposed=bool(metric_heading and any(re.fullmatch(r'(?:ASR|CACC|F1|IoU|AUC|WER|CER|Accuracy)\s*[↑↓]?',l.text.strip(),re.I)
                                          for r in data for l in r if l.bbox[2]<number_left))
    axes={}
    if transposed:
        # The real leading header positions specify independent categorical
        # dimensions; center-cell ink stays within that dimension's column.
        for header in [l for r in headings for l in r if l.bbox[2]<number_left and l is not metric_heading]:
            x=(header.bbox[0]+header.bbox[2])/2
            labels=[l for l in source if l.bbox[1]>=top-1 and l.bbox[2]<number_left and
                    abs((l.bbox[0]+l.bbox[2])/2-x)<max(16,header.bbox[2]-header.bbox[0]) and
                    not re.search(r'[。;；]|^注',l.text) and len(l.text)<50]
            if labels:axes[header.text]=sorted(labels,key=lambda l:(l.bbox[1]+l.bbox[3])/2)
    result=[]
    for native in data:
        numbers=[l for l in native if _NUMBER.fullmatch(normalize_text(l.text).strip())]
        left=min(l.bbox[0] for l in numbers)
        leading=[l for l in native if l.bbox[2]<left-5 and re.search(r'[A-Za-z\u4e00-\u9fff]',l.text)]
        if not leading:continue
        owner=min(leading,key=lambda l:l.bbox[0]);cy=(owner.bbox[1]+owner.bbox[3])/2
        local_headings=[h for h in header_rows if max(l.bbox[3] for l in h)<min(l.bbox[1] for l in native)+1]
        panels=[h for h in local_headings if len(h)>=3 and abs(h[0].bbox[0]-owner.bbox[0])<=15]
        if panels:
            panel_top=max(min(l.bbox[1] for l in h) for h in panels)
            local_headings=[h for h in local_headings if min(l.bbox[1] for l in h)>=panel_top-1]
        qualifiers=[];flags=[]
        sections=[]
        for cell in source:
            if cell.bbox[3]>=owner.bbox[1]+1:continue
            section=re.fullmatch(r'\s*([^=：:]{2,30})\s*[=：:]\s*(\d+)\s*',normalize_text(cell.text))
            if section:sections.append((cell,section[1].strip(),section[2]))
        section_fact=None
        if sections:
            cell,param,value=max(sections,key=lambda item:item[0].bbox[3])
            section_fact={'name':param,'value':value,'text':cell.text,'bbox':list(cell.bbox)}
        if transposed:
            metric=normalize_text(owner.text).strip(' ↑↓')
            for axis,labels in axes.items():
                nearest=min(range(len(labels)),key=lambda j:abs(cy-(labels[j].bbox[1]+labels[j].bbox[3])/2))
                centers=[(l.bbox[1]+l.bbox[3])/2 for l in labels]
                low=(centers[nearest-1]+centers[nearest])/2 if nearest else top-20
                high=(centers[nearest]+centers[nearest+1])/2 if nearest+1<len(labels) else max(l.bbox[3] for r in data for l in r)+20
                if low<=cy<=high:qualifiers.append((axis,normalize_text(labels[nearest].text).strip()))
        else:
            metric=None
            for checked in native:
                value=normalize_text(checked.text).strip()
                if not re.fullmatch(r'[✓✔√–—\-]',value):continue
                candidates=[l for r in headings for l in r if l.bbox[0]>owner.bbox[2]+2 and l.bbox[2]<left-2]
                if not candidates:continue
                header=min(candidates,key=lambda l:abs((l.bbox[0]+l.bbox[2]-checked.bbox[0]-checked.bbox[2])/2))
                if abs((header.bbox[0]+header.bbox[2]-checked.bbox[0]-checked.bbox[2])/2)<max(25,header.bbox[2]-header.bbox[0]):
                    flags.append((normalize_text(header.text).strip(),value in {'✓','✔','√'}))
        for cell in numbers:
            x=(cell.bbox[0]+cell.bbox[2])/2;levels=[]
            for heading in local_headings:
                words=[l for l in heading if l.bbox[0]>owner.bbox[2]+4 and l.bbox[0]>=left-65]
                if not words:continue
                centers=[(l.bbox[0]+l.bbox[2])/2 for l in words];nearest=min(range(len(words)),key=lambda j:abs(x-centers[j]))
                lo=(centers[nearest-1]+centers[nearest])/2 if nearest else words[nearest].bbox[0]-50
                hi=(centers[nearest]+centers[nearest+1])/2 if nearest+1<len(words) else words[nearest].bbox[2]+50
                if lo<=x<=hi:levels.append(normalize_text(words[nearest].text).strip(' ↑↓'))
            if not levels:continue
            if transposed:
                result.append({'owner':levels[-1],'metric':metric,'qualifiers':qualifiers,'stages':[],
                               'value':normalize_text(cell.text).strip(),'bbox':list(cell.bbox)})
            else:
                if len(levels)>1 and re.fullmatch(r'\d+',levels[-1]) and re.search(r'distinct[-\s]*n',levels[-2],re.I):
                    levels[-2:]=[re.sub(r'n$',levels[-1],levels[-2],flags=re.I)]
                result.append({'owner':normalize_text(owner.text).strip(),'metric':levels[-1],
                               'qualifiers':[('column',p) for p in levels[:-1]]+([('section',section_fact['name']+'='+section_fact['value'])] if section_fact else []),'stages':flags,
                               'value':normalize_text(cell.text).strip(),'bbox':list(cell.bbox),'section':section_fact})
    return result


def _matrix_owner_aliases(owner,records,text):
    stem=re.sub(r'^\s*\d+[.)、]\s*','',owner)
    stem=re.sub(r'\s*\[[\d,\s-]+\]\s*$','',stem).strip()
    aliases=[owner,stem]
    acronym=re.match(r'^([A-Z][A-Z0-9_-]{1,})\s+[\u4e00-\u9fff]',stem)
    if acronym:aliases.append(acronym[1])
    scale=re.fullmatch(r'(.+?)[\s_-]*(\d+(?:\.\d+)?[BM])',owner,re.I)
    if scale and _norm(scale[1]) in _norm(text):
        aliases.append(scale[2])
    return list(dict.fromkeys(a for a in aliases if len(_norm(a))>=2))


def _qualitative_metric_contrasts(descriptor,text):
    """Native relative orders plus a concrete complete-connectivity result.

    No exact number is claimed to have appeared in the body.  Several named
    rows and distinct measurement columns must independently agree, and the
    fully connected result has its own source value and native field.
    """
    from .usage_table_evidence import _numbers,_explicit_table_numbers
    if _explicit_table_numbers(text):return None
    if re.search(r'配置|configuration|settings?|architecture',descriptor['title'],re.I):return None
    records=descriptor.get('_axis_matrix') or _axis_numeric_matrix(descriptor)
    records=[r for r in records if not r['qualifiers'] and not r['stages']]
    owners=list(dict.fromkeys(r['owner'] for r in records))
    fields=list(dict.fromkeys(r['metric'] for r in records))
    if len(owners)<3 or len(fields)<4:return None
    matrix={(r['owner'],r['metric']):r for r in records}
    if len(matrix)!=len(records):return None
    if not all((o,f) in matrix and len(_numbers(matrix[(o,f)]['value']))==1 for o in owners for f in fields):return None
    windows=_body_windows([{'name':o} for o in owners],text,
                          lambda row:_matrix_owner_aliases(row['name'],records,text),sentence_bound=False)
    anchor=[]
    for ordinal,name,claim in windows:
        owner=owners[ordinal]
        if not re.search(r'表现良好|performs?\s+well',claim,re.I):continue
        stated=[f for f in fields if _present(f,claim)]
        if len(stated)<4:continue
        if not all(len(_numbers(matrix[(owner,f)]['value']))==1 and
                   _numbers(matrix[(owner,f)]['value'])[0][0]==max(_numbers(matrix[(o,f)]['value'])[0][0] for o in owners)
                   for f in stated if all((o,f) in matrix and len(_numbers(matrix[(o,f)]['value']))==1 for o in owners)):
            continue
        complete=[r for r in records if r['owner']==owner and re.search(r'连通性|connectivity',r['metric'],re.I)
                  and len(_numbers(r['value']))==1 and _numbers(r['value'])[0][0]==1
                  and all(0<=_numbers(matrix[(o,r['metric'])]['value'])[0][0]<=1 for o in owners)]
        own_complete=[c for i,_,c in windows if i==ordinal and re.search(r'完整连通|fully\s+connected',c,re.I)
                      and not re.search(r'未|不|not\s+fully|partially',c,re.I)]
        if len(complete)!=1 or not own_complete:continue
        lows=[]
        for i,other_name,other_claim in windows:
            other=owners[i]
            if other==owner:continue
            for field in stated:
                match=re.search(re.escape(field),other_claim,re.I)
                if not match:continue
                piece=re.split(r'[。;；!?]',other_claim[match.end():],maxsplit=1)[0]
                prefix=other_claim[:match.start()]
                immediate=bool(re.search(r'\blow\s+$|较低的\s*$',prefix,re.I))
                vocabulary='|'.join(re.escape(f) for f in fields)
                after_other=[m.start() for f in fields if f!=field for m in re.finditer(re.escape(f),piece,re.I)]
                local=piece[:min(after_other)] if after_other else piece
                own_low=bool(re.search(r'^.{0,35}?(?:较低|low\b)',local,re.I))
                collective=bool(re.match(r'^(?:\s*(?:与|和|及|、|and)\s*(?:'+vocabulary+r'))+\s*(?:均|都|are)?\s*(?:较低|low\b)',piece,re.I))
                if not (immediate or own_low or collective):continue
                a=_numbers(matrix[(other,field)]['value']);b=_numbers(matrix[(owner,field)]['value'])
                if len(a)==len(b)==1 and a[0][0]<b[0][0]:
                    lows.append({'owner':other,'field':field,'actual_cell':matrix[(other,field)],
                                 'comparison_cell':matrix[(owner,field)],'body_claim':other_claim,
                                 'claimed_relation':'lower than the contrasted good-result row'})
        unique={(p['owner'],p['field']):p for p in lows}
        if len(unique)>=4 and len({o for o,_ in unique})>=2 and len({f for _,f in unique})>=3:
            anchor.append({'owner':owner,'good_metric_claim':claim,'relative_metric_relations':list(unique.values()),
                           'complete_connectivity_cell':complete[0],'complete_connectivity_claims':own_complete})
    anchor=list({item['owner']:item for item in anchor}.values())
    if len(anchor)!=1:return None
    relations=anchor[0]['relative_metric_relations']
    return {'kind':'native_relative_metric_orders_and_complete_connectivity',
            'matched_fields':list(dict.fromkeys(p['field'] for p in relations)),
            'matched_values':[],'relations':anchor}


def _named_dataset_properties(descriptor,text):
    """Shared native table counts and ordered power-law attributes.

    This is a typed data-description relation. The two source dataset names,
    count unit, shared count and independently ordered distribution parameter
    must all agree; a dimension or a training rate cannot supply the latter.
    """
    from .usage_table_evidence import _numbers,_explicit_table_numbers
    if _explicit_table_numbers(text):return None
    if re.search(r'配置|configuration|settings?|architecture',descriptor['title'],re.I):return None
    records=descriptor.get('_axis_matrix') or _axis_numeric_matrix(descriptor)
    counts=[r for r in records if re.fullmatch(r'表数|table\s*count',r['metric'],re.I) and not r['qualifiers']]
    skews=[r for r in records if re.fullmatch(r'偏度|skewness',r['metric'],re.I) and not r['qualifiers']]
    if len(counts)<2 or len(skews)<2:return None
    owners=list(dict.fromkeys(r['owner'] for r in counts));normalized=normalize_text(text)
    pairs=[]
    for first in owners:
        for second in owners:
            if first==second:continue
            a=_matrix_owner_aliases(first,records,text);b=_matrix_owner_aliases(second,records,text)
            for left in a:
                for right in b:
                    names=re.search(re.escape(left)+r'\s*(?:和|与|、|and)\s*'+re.escape(right),normalized,re.I)
                    if not names:continue
                    tail=normalized[names.end():]
                    # A later repetition of a named dataset starts a new
                    # claim, even when it repeats this same pair.
                    stops=[m.start() for o in owners for alias in _matrix_owner_aliases(o,records,text)
                           for m in re.finditer(re.escape(alias),tail,re.I)]
                    if stops:tail=tail[:min(stops)]
                    shared=re.search(r'(?:均|都|both)[^。!?;；]{0,12}(?:包含|含有|contain|have)[^\d。!?;；]{0,8}(\d+)\s*(?:个\s*)?(?:嵌入向量\s*)?(?:表|tables?)',tail,re.I)
                    distribution=re.search(r'分别[^。!?;；]{0,18}(?:α|alpha)\s*=\s*(\d+(?:\.\d+)?)\s*(?:和|与|、|and)\s*(\d+(?:\.\d+)?)[^。!?;；]{0,15}(?:幂律分布|power[- ]law)',tail,re.I)
                    if not shared or not distribution:continue
                    value=int(shared[1]);skew_values=[_numbers(distribution[1])[0][0],_numbers(distribution[2])[0][0]]
                    native=[]
                    for owner,skew in zip([first,second],skew_values):
                        count=[r for r in counts if r['owner']==owner];attribute=[r for r in skews if r['owner']==owner]
                        if (len(count)!=1 or len(attribute)!=1 or len(_numbers(count[0]['value']))!=1
                                or len(_numbers(attribute[0]['value']))!=1 or _numbers(count[0]['value'])[0][0]!=value
                                or _numbers(attribute[0]['value'])[0][0]!=skew):native=[];break
                        native.append({'owner':owner,'table_count_cell':count[0],'power_law_skew_cell':attribute[0]})
                    if len(native)==2:pairs.append({'ordered_owners':[first,second],'native_properties':native,
                                                  'shared_count_claim':shared[0],'ordered_distribution_claim':distribution[0],
                                                  'body_claim':names[0]+tail})
    if len(pairs)!=1:return None
    return {'kind':'named_dataset_shared_count_and_ordered_distribution_properties',
            'matched_fields':['table count','power-law distribution parameter'],
            'matched_values':[r[k]['value'] for r in pairs[0]['native_properties'] for k in ['table_count_cell','power_law_skew_cell']],
            'relations':pairs}


def _native_phase_mentions(records,text):
    numerals={'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
    number=lambda value:int(value) if value.isdigit() else numerals.get(value)
    mentions=[]
    for record in records:
        owner=record['owner'];suffix=re.search(r'[（(]\s*(\d+)\s*(?:阶段|stages?)\s*[）)]',owner,re.I)
        stem=re.sub(r'\s*[（(][^）)]+[）)]\s*','',owner).strip() if suffix else owner
        pattern=r'(?<![A-Za-z0-9_.-])'+re.escape(stem)+r'(?![A-Za-z0-9_.-])'
        for match in re.finditer(pattern,text,re.I):
            if suffix:
                prefix=text[max(0,match.start()-30):match.start()]
                phase=re.search(r'(\d+|[一二两三四五六七八九十])\s*(?:阶段(?:压缩)?(?:的)?|[- ]stages?)\s*$',prefix,re.I)
                if not phase or number(phase[1])!=int(suffix[1]):continue
            mentions.append((match.start(),match.end(),owner))
    return sorted(set(mentions))


def _native_formula_properties(descriptor,text):
    from .usage_table_evidence import _explicit_table_numbers
    if _explicit_table_numbers(text):return None
    grid=descriptor.get('_catalogue_grid') or _grid(descriptor['cells'])
    if not grid:return None
    header,columns=grid
    metric=next((i for i,h in enumerate(header) if re.search(r'^指标$|^Metrics?$',h.text,re.I)),None)
    formula=next((i for i,h in enumerate(header) if re.search(r'公式|formulas?',h.text,re.I)),None)
    if metric is None or formula is None or metric==formula:return None
    anchors=sorted(columns[metric],key=lambda l:l.bbox[1]);native=[]
    centers=[(l.bbox[1]+l.bbox[3])/2 for l in anchors]
    for i,label in enumerate(anchors):
        name=normalize_text(label.text).strip()
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{1,15}',name):continue
        top=(centers[i-1]+centers[i])/2 if i else max(h.bbox[3] for h in header)
        bottom=(centers[i]+centers[i+1])/2 if i+1<len(anchors) else float('inf')
        ink=[l for l in columns[formula] if top<=(l.bbox[1]+l.bbox[3])/2<bottom]
        expression=' '.join(normalize_text(l.text) for l in ink)
        if re.search(r'\blog\s*\(',expression,re.I):native.append({'metric':name,'formula':expression,
            'formula_cells':[{'text':l.text,'bbox':list(l.bbox)} for l in ink]})
    contracts=[]
    for first in native:
        for second in native:
            if first is second:continue
            pattern=r'(?<![A-Za-z0-9_])'+re.escape(first['metric'])+r'\s*(?:与|和|、|and\b)\s*'+re.escape(second['metric'])+r'(?![A-Za-z0-9_])'
            for names in re.finditer(pattern,text,re.I):
                tail=re.split(r'[。!?]',text[names.end():names.end()+150])[0]
                if (re.search(r'对数尺度|logarithmic\s+scale|log[- ]scale',tail,re.I)
                        and re.search(r'计算|calculat|comput',tail,re.I)
                        and re.search(r'降低|鲁棒|robust|reduc',tail,re.I)):
                    contracts.append({'native_metrics':[first,second],'body_claim':names[0]+tail})
    if not contracts:return None
    return {'kind':'native_named_formulas_and_independent_computational_property',
            'matched_fields':[r['metric'] for r in contracts[0]['native_metrics']],
            'matched_values':[],'relations':contracts}


def _native_ablation_endpoints(descriptor,text):
    from .usage_table_evidence import _explicit_table_numbers,_numbers
    if _explicit_table_numbers(text) or not re.search(r'消融|ablation',descriptor['title'],re.I):return None
    records=descriptor.get('_axis_matrix') or _axis_numeric_matrix(descriptor)
    complete=list(dict.fromkeys(r['owner'] for r in records if re.search(r'[（(]\s*Full\s*[）)]|完整',r['owner'],re.I)))
    if len(complete)!=1:return None
    variants=list(dict.fromkeys(r['owner'] for r in records if re.match(r'w/o\s+',r['owner'],re.I)))
    for owner in variants:
        component=re.sub(r'^w/o\s+','',owner,flags=re.I)
        action=re.search(r'(?:移除|去除|\bremove[ds]?\s+)\s*'+re.escape(component)+r'(?![A-Za-z0-9_])',text,re.I)
        if not action:continue
        claim=re.split(r'[。!?;；]',text[action.end():],maxsplit=1)[0]
        for native in [r for r in records if r['owner']==owner and not r['stages']]:
            metric=next((aliases for pattern,aliases in _MEASUREMENT_ALIASES if re.search(pattern,native['metric'],re.I)),[native['metric']])
            if not any(_present(alias,claim) for alias in metric):continue
            axes=True
            for _,axis in native['qualifiers']:
                top=re.fullmatch(r'Top\s*(\d+)\s*%',axis,re.I)
                if top:
                    if not re.search(r'\bTop[-\s]*'+top[1]+r'\s*%',claim,re.I):axes=False
                elif not _present(axis,claim):axes=False
            if not axes:continue
            base=[r for r in records if r['owner']==complete[0] and r['metric']==native['metric'] and r['qualifiers']==native['qualifiers'] and r['stages']==native['stages']]
            if len(base)!=1:continue
            chain=re.search(r'(?:从|from)\s*([+-]?\d+(?:\.\d+)?\s*%?)\s*[^。!?;；]{0,14}?(?:暴跌至|下降至|降低至|降至|跌至|to)\s*([+-]?\d+(?:\.\d+)?\s*%?)',claim,re.I)
            if not chain:continue
            first,last=_numbers(chain[1]),_numbers(chain[2]);a,b=_numbers(base[0]['value']),_numbers(native['value'])
            if any(len(v)!=1 for v in [first,last,a,b]) or first[0][:2]!=a[0][:2] or last[0][:2]!=b[0][:2] or a[0][0]<=b[0][0]:continue
            return {'kind':'native_removed_component_metric_endpoints',
                    'matched_fields':[native['metric'],*[a for _,a in native['qualifiers']]],
                    'matched_values':[chain[1],chain[2]],'relations':[{'native_complete_cell':base[0],
                        'native_removed_component_cell':native,'body_component_removal':action[0],'body_chain':chain[0]}]}
    return None


def _native_parameter_trends(descriptor,text):
    from .usage_table_evidence import _explicit_table_numbers,_cell_rows
    if not re.search(r'accuracy|准确率',descriptor['title'],re.I):return None
    # Exact multi-row relations may uniquely identify an unnumbered sweep;
    # an explicitly different dataset or model-group identity vetoes it.
    identities=re.findall(r'(?:在\s*|\b(?:on|from|in)\s+)([A-Z][A-Za-z0-9_-]*)\s*(?:数据集|dataset)',text)
    identities+=re.findall(r'(?:使用\s*|\busing\s+)([A-Z][A-Za-z0-9_-]*)\s*(?:模型组|model\s+group)',text)
    if any(_norm(name) not in _norm(descriptor['title']) for name in identities):return None
    rows=_cell_rows(descriptor['cells']);headers=[]
    for ink in rows:
        values=[]
        for l in ink:
            setting=re.fullmatch(r'\s*([A-Za-zα-ωΑ-Ω][′\']?)\s*=\s*(\d+)\s*',normalize_text(l.text))
            if setting:values.append((l,setting[1].replace("'",'′'),int(setting[2])))
        if len(values)>=3 and len({v[1] for v in values})==1:headers.append(sorted(values,key=lambda v:v[0].bbox[0]))
    if len(headers)!=1:return None
    headings=headers[0];variable=headings[0][1];settings=[h[2] for h in headings]
    if settings!=sorted(settings) or len(set(settings))!=len(settings):return None
    matrix=[]
    for ink in rows:
        if min(l.bbox[1] for l in ink)<=max(h[0].bbox[3] for h in headings):continue
        owners=[l for l in ink if l.bbox[2]<min(h[0].bbox[0] for h in headings)-4 and re.search(r'[A-Za-z]',l.text)]
        if len(owners)!=1:continue
        actual=[]
        for heading,_,setting in headings:
            center=(heading.bbox[0]+heading.bbox[2])/2
            cells=[l for l in ink if abs((l.bbox[0]+l.bbox[2])/2-center)<max(22,heading.bbox[2]-heading.bbox[0])]
            measurements=[(l,re.fullmatch(r'\s*(\d+(?:\.\d+)?)(?:\s*±\s*\d+(?:\.\d+)?)?\s*',normalize_text(l.text))) for l in cells]
            measurements=[(l,m) for l,m in measurements if m]
            if len(measurements)!=1:actual=[];break
            l,m=measurements[0];actual.append({'setting':setting,'value':float(m[1]),'native_text':l.text,'bbox':list(l.bbox)})
        if len(actual)==len(headings):matrix.append({'owner':owners[0].text,'measurements':actual})
    if len(matrix)<3:return None
    normalized=normalize_text(text).replace("'",'′');contracts=[]
    mentions=[]
    for row in matrix:
        for m in re.finditer(r'(?<![A-Za-z0-9_])'+re.escape(row['owner'])+r'(?![A-Za-z0-9_])',normalized):mentions.append((m.start(),m.end(),row))
    mentions.sort(key=lambda m:m[0])
    if re.search(r'本地训练轮数|local\s+training\s+epochs?',descriptor['title'],re.I) and re.search(r'本地训练轮数|local\s+training\s+epochs?',normalized,re.I):
        down=[];steady=[]
        for i,(a,b,row) in enumerate(mentions):
            tail=re.split(r'[。!?]',normalized[b:mentions[i+1][0] if i+1<len(mentions) else len(normalized)],maxsplit=1)[0]
            score=[m['value'] for m in row['measurements']]
            decreasing=all(x>y for x,y in zip(score,score[1:]));holding=all(x<=y for x,y in zip(score,score[1:]))
            if re.search(r'准确率下降|accuracy\s+(?:falls?|decreases?)',tail,re.I) and decreasing:down.append(row)
            if re.search(r'保持[^。!?]{0,12}性能|maintain[^。!?]{0,12}performance',tail,re.I) and holding:steady.append(row)
            if i and re.fullmatch(r'\s*(?:和|与|and)\s*',normalized[mentions[i-1][1]:a],re.I) and re.search(r'准确率下降|accuracy\s+(?:falls?|decreases?)',tail,re.I):
                other=mentions[i-1][2];other_values=[m['value'] for m in other['measurements']]
                if decreasing and all(x>y for x,y in zip(other_values,other_values[1:])):down.extend([other,row])
        down=list({r['owner']:r for r in down}.values());steady=list({r['owner']:r for r in steady}.values())
        if len(down)>=2 and steady and not ({r['owner'] for r in down}&{r['owner'] for r in steady}):
            return {'kind':'native_parameter_sweep_owned_declining_and_maintained_methods',
                    'matched_fields':[variable,'accuracy trend'],'matched_values':[],
                    'relations':[{'native_axis_settings':settings,'declining_native_rows':down,'maintained_native_rows':steady,'body_claim':text}]}
    optimum=re.search(re.escape(variable)+r'\s*=\s*(\d+)[^。!?]{0,20}?(?:最佳性能|best\s+performance)',normalized,re.I)
    exception=re.search(r'除了[^。!?]*|except[^。!?]*',normalized,re.I)
    if not optimum or not exception or not re.search(r'大多数方法|most\s+methods',normalized,re.I):return None
    selected=int(optimum[1])
    if selected not in settings:return None
    exceptions=[r for r in matrix if _present(r['owner'],exception[0])]
    if not exceptions:return None
    named=re.findall(r'[A-Z][A-Za-z0-9_-]{2,}',exception[0])
    if any(not any(_norm(name)==_norm(r['owner']) for r in exceptions) for name in named):return None
    def unique_peak(row):
        values=[m['value'] for m in row['measurements']];maximum=max(values)
        return values.count(maximum)==1 and settings[values.index(maximum)]==selected
    rest=[r for r in matrix if r not in exceptions]
    peaks=[r for r in rest if unique_peak(r)]
    # "Most" is a quantified claim, not "every other row". Check a strict
    # majority of all native methods and retain any unnamed counterexamples
    # in the evidence; every explicitly named exception must still agree.
    if len(peaks)<3 or len(peaks)*2<=len(matrix) or any(unique_peak(r) for r in exceptions):return None
    return {'kind':'native_parameter_optimum_and_every_named_exception',
            'matched_fields':[variable,'accuracy optimum'],'matched_values':[],
            'relations':[{'native_axis_settings':settings,'claimed_optimum':selected,'native_peak_rows':peaks,
                          'native_exception_rows':exceptions,'native_unmentioned_exceptions':[r for r in rest if r not in peaks],
                          'native_method_count':len(matrix),'body_claim':text}]}


def _native_feature_statistics(descriptor,text):
    """Feature extraction owns typed fields, rather than a shared topic name."""
    from .usage_table_evidence import _explicit_table_numbers
    if _explicit_table_numbers(text) or not re.search(r'特征|features?',descriptor['title'],re.I):return None
    grid=descriptor.get('_catalogue_grid') or _grid(descriptor['cells'])
    if not grid or not any(re.search(r'具体特征|描述|description',h.text,re.I) for h in grid[0][1:]):return None
    if re.search(r'不统计|不提取|不包括|不包含|not\s+(?:extract|include|measure)',text,re.I):return None
    if not re.search(r'作为[^。!?]{0,20}特征|用于|用来|刻画|反映|提取|extract|used?\s+(?:for|as)',text,re.I):return None
    rows=descriptor.get('_native_relation_rows') or _relation_rows(descriptor['cells'])
    field_types=(('duration',r'持续时间|存活时间|flow\s+duration'),
                 ('packet count',r'总(?:数据)?包数|数据包数|包数|packet\s+count'),
                 ('byte count',r'总字节数|字节数|byte\s+count'),
                 ('packet length',r'(?:数据)?包(?:长(?:度)?|长度)|packet\s+(?:length|size)'),
                 ('interarrival time',r'包到达时间间隔|(?:数据)?包间隔时间|interarrival\s+time'))
    relations=[]
    if (re.search(r'流|flow',descriptor['title'],re.I) and
            re.search(r'作为\s*(?:数据|会话)?流(?:级别)?(?:的)?特征|extract[^。!?]{0,15}(?:data|session)\s+flow\s+features',text,re.I)):
        for name,pattern in field_types:
            own=[r for r in rows if re.search(pattern,' '.join(r['purposes']),re.I)]
            body=list(re.finditer(pattern,text,re.I))
            if len(own)==1 and body:relations.append({'field':name,'native_category':own[0]['name'],
                'native_description':' '.join(own[0]['purposes']),'body_fields':[m[0] for m in body]})
        if len(relations)>=3:return {'kind':'native_flow_feature_fields_with_independent_extraction',
            'matched_fields':[r['field'] for r in relations],'matched_values':[],'relations':relations}
    def bands(value):
        return [tuple(map(float,m.groups())) for m in re.finditer(r'(\d+(?:\.\d+)?)\s*[-–—]\s*(\d+(?:\.\d+)?)\s*Hz',value,re.I)]
    for row in rows:
        source=' '.join(row['purposes'])
        if not re.search(r'瞳孔|pupil',row['name'],re.I):continue
        owner=re.search(r'瞳孔(?:相关特征|直径)?|pupil(?:\s+diameter)?',text,re.I)
        if not owner:continue
        claim=text[owner.start():]
        # Another actual feature category starts a new owner; its attributes
        # cannot supply a missing statistic to this pupil claim.
        stop=re.search(r'注视|扫视|眨眼|fixation|saccade|blink',claim,re.I)
        if stop:claim=claim[:stop.start()]
        statistics=(('mean',r'平均值|均值|\bmean\b'),('standard deviation',r'标准差|standard\s+deviation'),
                    ('differential entropy',r'差分熵|differential\s+entropy'))
        actual=[name for name,pattern in statistics if re.search(pattern,source,re.I) and re.search(pattern,claim,re.I)]
        source_bands=bands(source);body_bands=bands(claim)
        if len(actual)==3 and len(source_bands)>=3 and source_bands==body_bands:
            return {'kind':'native_feature_owner_statistics_and_frequency_bands',
                'matched_fields':[row['name'],*actual],'matched_values':[],
                'relations':[{'native_owner':row['name'],'native_description':source,
                              'statistics':actual,'native_frequency_bands':source_bands,'body_claim':claim}]}
    return None


def _native_variant_rank_results(descriptor,text):
    """A named model/configuration owns a complete native ranking contract."""
    from .usage_table_evidence import _numbers,_explicit_table_numbers
    if _explicit_table_numbers(text):return None
    title=descriptor['title']
    if not re.search(r'性能|结果|performance|results?',title,re.I):return None
    code=r'代码补全|code\s+completion';longtext=r'长文本理解|long\s+text\s+understanding'
    if re.search(code,title,re.I) and not re.search(code,text,re.I):return None
    if re.search(longtext,title,re.I):
        if re.search(code,text,re.I):return None
        if not (re.search(longtext,text,re.I) or re.search(r'综合性能[^。!?]{0,50}数据集[^。!?]{0,20}平均|综合性能[^。!?]{0,20}平均[^。!?]{0,20}数据集',text,re.I)):return None
    records=descriptor.get('_axis_matrix') or _axis_numeric_matrix(descriptor)
    records=[r for r in records if r.get('section') and re.search(r'缓存|cache',r['section']['name'],re.I)
             and len(r['qualifiers'])==1 and r['qualifiers'][0][0]=='section']
    if not records:return None
    normalized=re.sub(r'(?<=[A-Za-z])-\s+(?=[A-Za-z])','',normalize_text(text))
    cache_matches=list(re.finditer(r'(?:缓存(?:大小|容量)|cache\s*(?:size|capacity))\s*(?:为|is|of|=|:)?\s*(\d+)(?!\d)',normalized,re.I))
    evidence=[]
    for si,setting in enumerate(cache_matches):
        value=setting[1];segment=normalized[setting.end():cache_matches[si+1].start() if si+1<len(cache_matches) else len(normalized)]
        configured=[r for r in records if r['section']['value']==value]
        fields=list(dict.fromkeys(r['metric'] for r in configured));field_mentions=[]
        for field in fields:
            for m in re.finditer(re.escape(field),segment,re.I):field_mentions.append((m.start(),m.end(),field))
        field_mentions.sort()
        for fi,(start,end,field) in enumerate(field_mentions):
            body=segment[end:field_mentions[fi+1][0] if fi+1<len(field_mentions) else len(segment)]
            native=[r for r in configured if r['metric']==field]
            mentions=_native_phase_mentions(native,body)
            named=list(dict.fromkeys(owner for _,_,owner in mentions))
            families={re.sub(r'\s*[（(][^）)]+[）)]\s*','',o).strip() for o in named}
            if len(named)<4 or len(families)<3:continue
            matrix={owner:[r for r in native if r['owner']==owner] for owner in named}
            if any(len(rs)!=1 or len(_numbers(rs[0]['value']))!=1 for rs in matrix.values()):continue
            scores={owner:_numbers(rs[0]['value'])[0][0] for owner,rs in matrix.items()}
            high=max(scores.values());low=min(scores.values());contracts=[]
            for mi,(a,b,owner) in enumerate(mentions):
                tail=body[b:mentions[mi+1][0] if mi+1<len(mentions) else len(body)]
                if re.search(r'最低|lowest',tail,re.I) and scores[owner]==low:
                    contracts.append({'relation':'lowest','owners':[owner],'body_claim':tail})
                if re.search(r'最高|居首|highest',tail,re.I) and not re.search(r'并列|tied',tail,re.I) and scores[owner]==high:
                    contracts.append({'relation':'highest','owners':[owner],'body_claim':tail})
                if re.search(r'稍低|略低|slightly\s+lower',tail,re.I) and not re.search(r'依次|respectively',tail,re.I) and scores[owner]<high:
                    contracts.append({'relation':'lower than the explicit highest group','owners':[owner],'body_claim':tail})
                if mi==0:continue
                previous=mentions[mi-1];gap=body[previous[1]:a]
                if not re.match(r'^\s*(?:与|和|and\b)',gap,re.I):continue
                pair=[previous[2],owner]
                if len(set(pair))!=2:continue
                if re.search(r'并列最高|tied[^。!?]{0,20}highest',tail,re.I) and scores[pair[0]]==scores[pair[1]]==high:
                    contracts.append({'relation':'tied highest','owners':pair,'body_claim':gap+body[a:b]+tail})
                if re.search(r'依次略低|successively\s+lower',tail,re.I) and high>scores[pair[0]]>scores[pair[1]]:
                    contracts.append({'relation':'ordered below the explicit highest row','owners':pair,'body_claim':gap+body[a:b]+tail})
            top=[c for c in contracts if c['relation'] in {'highest','tied highest'}]
            bottom=[c for c in contracts if c['relation']=='lowest']
            relative=[c for c in contracts if c['relation'] in {'lower than the explicit highest group','ordered below the explicit highest row'}]
            covered={o for c in contracts for o in c['owners']}
            if not top or not bottom or not relative or covered!=set(named):continue
            evidence.append({'model_field':field,'native_configuration':configured[0]['section'],
                             'native_rows':[matrix[o][0] for o in named],
                             'ranking_contracts':contracts,'body_claim':body})
    if not evidence:return None
    return {'kind':'native_model_configuration_and_distinct_variant_rank_contract',
            'matched_fields':[p['model_field']+' / '+p['native_configuration']['text'] for p in evidence],
            'matched_values':[],'relations':evidence}


def _ordered_column_pairs(descriptor,text):
    """Repeated source leaves (e.g. Large) retain explicit split order."""
    from .usage_table_evidence import _numbers,_explicit_table_numbers
    if _explicit_table_numbers(text):return None
    if re.search(r'配置|configuration|settings?|architecture|specifications?',descriptor['title'],re.I):return None
    records=descriptor.get('_axis_matrix') or _axis_numeric_matrix(descriptor)
    owners=list(dict.fromkeys(r['owner'] for r in records));pairs=[]
    for ordinal,name,claim in _body_windows([{'name':o} for o in owners],text,
            lambda row:_matrix_owner_aliases(row['name'],records,text),sentence_bound=False):
        owner=owners[ordinal]
        values=_numbers(re.split(r'[;；。!?]',claim,maxsplit=1)[0])
        if len(values)!=2:continue
        for leaf in dict.fromkeys(r['metric'] for r in records if r['owner']==owner):
            if not _present(leaf,text):continue
            columns=sorted((r for r in records if r['owner']==owner and r['metric']==leaf
                            and len(r['qualifiers'])==1 and not r['stages']),key=lambda r:r['bbox'][0])
            if len(columns)!=2 or columns[0]['qualifiers']==columns[1]['qualifiers']:continue
            # Both native split names must occur in this order before the
            # measurement array; unspecified arrays cannot inherit columns.
            names=[r['qualifiers'][0][1] for r in columns]
            pattern=re.escape(names[0])+r'\s*(?:和|与|、|and|,)\s*'+re.escape(names[1])
            position=normalize_text(text).find(claim)
            if position<0:continue
            prefix=normalize_text(text)[:position]
            if not re.search(pattern,prefix,re.I):continue
            actual=[_numbers(r['value']) for r in columns]
            if any(len(a)!=1 for a in actual) or [a[0][0] for a in actual]!=[v[0] for v in values]:continue
            pairs.append({'owner':owner,'body_name':name,'leaf':leaf,'ordered_columns':names,
                          'cells':columns,'body_claim':claim})
    if not pairs:return None
    return {'kind':'actual_owner_and_ordered_source_split_values',
            'matched_fields':[p['owner']+' / '+p['leaf']+' / '+' / '.join(p['ordered_columns']) for p in pairs],
            'matched_values':[r['value'] for p in pairs for r in p['cells']],'relations':pairs}


def _relative_delta_values(descriptor,text):
    """A relative source column is owned by its printed baseline and sign."""
    from .usage_table_evidence import _numbers,_explicit_table_numbers
    if _explicit_table_numbers(text):return None
    if re.search(r'配置|configuration|settings?|architecture|specifications?',descriptor['title'],re.I):return None
    records=descriptor.get('_axis_matrix') or _axis_numeric_matrix(descriptor)
    deltas=[r for r in records if re.fullmatch(r'[Δ𝛥δ]|delta|差值',r['metric'],re.I)]
    if not deltas:return None
    owners=list(dict.fromkeys(r['owner'] for r in records))
    footnotes=[l.text for l in descriptor['cells'] if re.search(r'相对|基准|relative\s+to',l.text,re.I) and
               re.search(r'[Δ𝛥δ]|delta',l.text,re.I)]
    baseline=[]
    for owner in owners:
        if any(any(_present(a,f) for a in _row_aliases({'name':owner})) for f in footnotes):baseline.append(owner)
    if len(baseline)!=1:return None
    reference=baseline[0];reference_aliases=_row_aliases({'name':reference})
    our_reference=bool(re.search(r'本文|our\s+method|this\s+work',' '.join(footnotes)+' '+reference,re.I))
    explicit_reference=any(_present(a,text) for a in reference_aliases)
    generic_reference=our_reference and re.search(r'本文方法|本文采用|our\s+method',text,re.I)
    if not explicit_reference and not generic_reference:return None
    pairs=[]
    for owner in owners:
        source=sorted((r for r in deltas if r['owner']==owner),key=lambda r:r['bbox'][0])
        if len(source)!=2 or any(len(r['qualifiers'])!=1 for r in source):continue
        parent_names=[r['qualifiers'][0][1] for r in source]
        if parent_names[0]==parent_names[1]:continue
        for alias in _matrix_owner_aliases(owner,records,text):
            hit=re.search(re.escape(alias),normalize_text(text),re.I)
            if not hit:continue
            claim=re.split(r'[。;；!?]',normalize_text(text)[hit.end():],maxsplit=1)[0]
            if not re.search(r'分别|respectively',claim,re.I):continue
            fields={r['metric'] for r in records if r['owner']==owner and r['metric'] not in {'Δ','𝛥','δ'}}
            field=next((f for f in fields if _present(f,claim)),None)
            if field is None:continue
            declared=bool(re.search(r'两个数据集|two\s+datasets?',claim,re.I))
            if not declared and not re.search(re.escape(parent_names[0])+r'[^。;；!?]{0,20}'+re.escape(parent_names[1]),claim,re.I):continue
            direction=re.search(r'下降|降低|falls?|decreas|drops?|提升|上升|rises?|increas',claim,re.I)
            if not direction:continue
            values=_numbers(claim[direction.end():])
            if len(values)!=2:continue
            sign=-1 if re.search(r'下降|降低|falls?|decreas|drops?',direction[0],re.I) else 1
            actual=[_numbers(r['value']) for r in source]
            if any(len(v)!=1 for v in actual) or [v[0][0] for v in actual]!=[sign*v[0] for v in values]:continue
            # An explicitly named different comparator contradicts the
            # native reference even when the printed difference matches.
            other_owners=[o for o in owners if o not in {owner,reference}]
            if any(_present(a,claim) for o in other_owners for a in _row_aliases({'name':o})):continue
            if not all(any(r['owner']==owner and r['metric']==field and r['qualifiers']==delta['qualifiers'] for r in records) for delta in source):continue
            pairs.append({'owner':owner,'baseline':reference,'metric':field,'ordered_datasets':parent_names,
                          'delta_cells':source,'native_reference_note':footnotes,'body_claim':claim})
    if pairs:
        return {'kind':'actual_relative_metric_differences_and_native_reference',
                'matched_fields':[p['owner']+' / '+p['metric'] for p in pairs],
                'matched_values':[r['value'] for p in pairs for r in p['delta_cells']],'relations':pairs}
    # A comparison against one named variant also has to describe that
    # variant in its own prose window. Names or the difference alone cannot
    # resolve Attention versus Hidden, or another native suffix.
    concepts=((r'^hidden$',r'隐藏|hidden'),(r'^attention$',r'注意力|attention'))
    normalized=normalize_text(text)
    for owner in owners:
        variant=re.search(r'[（(]([^）)]+)[）)]',owner)
        if not variant:continue
        stem=re.sub(r'\s*[（(][^）)]+[）)]\s*','',owner).strip()
        variant_rx=next((rx for native,rx in concepts if re.fullmatch(native,variant[1].strip(),re.I)),None)
        if variant_rx is None:variant_rx=re.escape(variant[1].strip())
        # The suffix's description must follow the source owner and stop
        # at the named baseline; baseline features cannot donate it.
        source_claims=[]
        for m in re.finditer(re.escape(stem),normalized,re.I):
            claim=normalized[m.end():]
            stops=[n.start() for a in reference_aliases for n in re.finditer(re.escape(a),claim,re.I)]
            if stops:claim=claim[:min(stops)]
            source_claims.append(claim)
        if not any(re.search(variant_rx,c,re.I) for c in source_claims):continue
        for delta in [r for r in deltas if r['owner']==owner and len(r['qualifiers'])==1]:
            dataset=delta['qualifiers'][0][1]
            if not _present(dataset,normalized):continue
            # The comparative sentence supplies the source, target, data
            # set and positive gain, all before a sentence boundary.
            for sentence in re.split(r'[。;；!?]',re.sub(r'^\s*\d+[.、]\s+','',normalized)):
                if not (_present(stem,sentence) and any(_present(a,sentence) for a in reference_aliases)
                        and _present(dataset,sentence) and re.search(r'相比|相较|compared',sentence,re.I)):
                    continue
                gain=re.search(r'优势|提升|gains?|improv|advantage',sentence,re.I)
                if not gain:continue
                numbers=_numbers(sentence)
                actual=_numbers(delta['value'])
                if len(numbers)!=1 or len(actual)!=1 or actual[0][0]>=0 or numbers[0][0]!=-actual[0][0]:continue
                native=[r for r in records if r['owner']==owner and r['qualifiers']==delta['qualifiers'] and r not in deltas]
                checked=[]
                for cell in native:
                    target=[r for r in records if r['owner']==reference and r['qualifiers']==cell['qualifiers'] and r['metric']==cell['metric']]
                    a=_numbers(cell['value']);b=_numbers(target[0]['value']) if len(target)==1 else []
                    if len(a)==len(b)==1 and b[0][0]-a[0][0]==numbers[0][0]:checked.append((cell,target[0]))
                if len(checked)!=1:continue
                return {'kind':'native_variant_owned_relative_gain_to_printed_baseline',
                        'matched_fields':[owner+' / '+dataset+' / '+checked[0][0]['metric']],
                        'matched_values':[checked[0][0]['value'],checked[0][1]['value'],delta['value']],
                        'relations':[{'owner':owner,'baseline':reference,'source_cell':checked[0][0],
                                      'baseline_cell':checked[0][1],'delta_cell':delta,
                                      'source_variant_claims':source_claims,'body_claim':sentence,'native_reference_note':footnotes}]}
    return None


def _stages_agree(record,claim):
    stages=record['stages']
    if not stages:return True
    active=[name for name,on in stages if on]
    if len(active)==1:
        return bool(re.search(r'纯|仅|only|sole',claim,re.I) and _present(active[0],claim))
    # A later cumulative configuration needs its distinctive added stages.
    return all(_present(name,claim) for name in active[1:]) and not re.search(r'纯|仅|only|sole',claim,re.I)


def _axis_numeric_values(descriptor,text):
    from .usage_table_evidence import _numbers,_explicit_table_numbers
    if _explicit_table_numbers(text):return None
    if re.search(r'配置|configuration|settings?|architecture|specifications?',descriptor['title'],re.I):return None
    records=descriptor.get('_axis_matrix') or _axis_numeric_matrix(descriptor)
    if not records:return None
    owners=list(dict.fromkeys(r['owner'] for r in records));pairs=[]
    normalized=normalize_text(text)
    # Respectively arrays are accepted only as a complete ordered mapping.
    # A reversed owner list is contradictory, even if its last owner could
    # otherwise borrow the first value of each coordinated measurement.
    for clause in re.split(r'[;；。!?]',normalized):
        if not re.search(r'分别|respectively',clause,re.I):continue
        for metric in dict.fromkeys(r['metric'] for r in records):
            mm=re.search(re.escape(metric).replace(r'\ ',r'\s*'),clause,re.I)
            if not mm:continue
            named=[]
            for owner in owners:
                for alias in _matrix_owner_aliases(owner,records,normalized):
                    for m in re.finditer(re.escape(alias).replace(r'\ ',r'\s*'),clause[:mm.start()],re.I):
                        named.append((m.start(),owner))
            ordered=list(dict.fromkeys(owner for _,owner in sorted(named)))
            if len(ordered)<2:continue
            tail=clause[mm.end():]
            stops=[m.start() for other in owners if other not in ordered
                   for alias in _matrix_owner_aliases(other,records,normalized)
                   for m in re.finditer(re.escape(alias).replace(r'\ ',r'\s*'),tail,re.I)]
            if stops:tail=tail[:min(stops)]
            values=_numbers(tail)
            if len(values)!=len(ordered):continue
            matched=[]
            for owner,value in zip(ordered,values):
                def qualifier_agrees(axis,value):
                    alternatives={q for r in records for a,q in r['qualifiers'] if a==axis}
                    if any(_present(q,clause) for q in alternatives):return _present(value,clause)
                    prefix=normalized.split(';')[0].split('；')[0]
                    return _present(value,prefix)
                possible=[r for r in records if r['owner']==owner and r['metric']==metric and
                          all(qualifier_agrees(a,q) for a,q in r['qualifiers']) and
                          _stages_agree(r,clause) and len(_numbers(r['value']))==1 and _numbers(r['value'])[0][0]==value[0]]
                if len(possible)!=1:matched=[];break
                matched.append(possible[0])
            if matched:pairs.extend(dict(r,body_claim=clause) for r in matched)
    # Scalar claims require their own owner, exact metric and fully resolved
    # stage.  A short scale alias is derived only from its printed family.
    row_specs=[{'name':owner} for owner in owners]
    aliases=lambda row:_matrix_owner_aliases(row['name'],records,normalized)
    for ordinal,name,claim in _body_windows(row_specs,normalized,aliases,sentence_bound=False):
        owner=owners[ordinal]
        for metric in dict.fromkeys(r['metric'] for r in records if r['owner']==owner):
            mm=re.search(re.escape(metric).replace(r'\ ',r'\s*'),claim,re.I)
            if not mm:
                # "X's Distinct-1 is highest (...), while Y is lowest (...)"
                # continues that precise field, rather than switching to a
                # different numerical attribute somewhere in the paragraph.
                position=normalized.find(name)
                prefix=normalized[max(0,position-130):position]
                if not (re.search(r'最高|最低|highest|lowest',claim,re.I) and _present(metric,prefix)):continue
            after=re.split(r'[;；。!?]',claim[mm.end():] if mm else claim,maxsplit=1)[0]
            values=_numbers(after)
            if len(values)!=1:continue
            possible=[r for r in records if r['owner']==owner and r['metric']==metric and
                      all(_present(q,claim) for _,q in r['qualifiers']) and _stages_agree(r,normalized) and
                      len(_numbers(r['value']))==1 and _numbers(r['value'])[0][0]==values[0][0]]
            if len(possible)==1:pairs.append(dict(possible[0],body_name=name,body_claim=claim))
    unique={(p['owner'],p['metric'],tuple(p['qualifiers']),tuple(p['stages'])):p for p in pairs}
    if len(unique)<2:return None
    return {'kind':'native_matrix_axes_and_independently_owned_values',
            'matched_fields':[p['owner']+' / '+p['metric'] for p in unique.values()],
            'matched_values':[p['value'] for p in unique.values()],'relations':list(unique.values())}


def _owned_numeric_values(descriptor,text):
    """Two real row/metric cells, with an explicit row owner for each value."""
    from .usage_table_evidence import _NUMBER,_numbers,_explicit_table_numbers
    # This supplementary numerical path is for unnumbered content use.
    # Printed table pointers retain the existing direct-reference paths.
    if _explicit_table_numbers(text):return None
    if re.search(r'配置|configuration|settings?|architecture|specifications?',descriptor['title'],re.I):return None
    rows=descriptor['_numeric_matrix'] if '_numeric_matrix' in descriptor else _numeric_row_matrix(descriptor)
    if not rows:return None
    pairs=[]
    for owner,name,claim in _body_windows(rows,text,_row_aliases,sentence_bound=False):
        row=rows[owner]
        for entry in row['entries']:
            if not entry['headers']:continue
            leaf=entry['headers'][-1];aliases=[leaf]
            if not re.search(r'F1|IoU|precision|recall|FPS|Mean\s*\(ms\)|\b(?:EM|EX|VES|FPR95|AUC|ASR|WER|CER)\b|Distinct|accuracy|准确率|精确率|召回率|交并比|帧率|帧时',
                             ' '.join(entry['headers']),re.I):continue
            for pattern,equivalents in _MEASUREMENT_ALIASES:
                if re.search(pattern,leaf,re.I):aliases.extend(equivalents)
            header_hits=[a for a in aliases if _present(a,claim)]
            if not header_hits:continue
            # A repeated leaf such as EX is owned by its source dataset band.
            # Restrict the claim to the actual named band before considering
            # its metric; another dataset in the paragraph cannot supply it.
            scoped=claim
            parents=entry['headers'][:-1]
            if parents:
                for parent in parents:
                    if not _present(parent,text):scoped='';break
                    if _present(parent,claim):
                        start=_norm(claim).find(_norm(parent))
                        # Retain ordinary source character positions for
                        # numerical parsing, rather than normalized offsets.
                        m=re.search(re.escape(parent).replace(r'\ ',r'\s*'),claim,re.I)
                        if m:
                            scoped=claim[m.end():]
                            others={h for r in rows for e in r['entries'] for h in e['headers'][:-1] if h!=parent}
                            stops=[m.start() for h in others for m in re.finditer(re.escape(h).replace(r'\ ',r'\s*'),scoped,re.I)]
                            if stops:scoped=scoped[:min(stops)]
            if not scoped:continue
            field_pattern='|'.join(re.escape(a).replace(r'\ ',r'\s*') for a in aliases)
            metric=re.search(r'(?:'+field_pattern+r')',scoped,re.I)
            if not metric:continue
            after=scoped[metric.end():]
            other_leaves={h for r in rows for e in r['entries'] for h in e['headers'][-1:] if h!=leaf}
            stops=[m.start() for h in other_leaves for m in re.finditer(re.escape(h).replace(r'\ ',r'\s*'),after,re.I)]
            if stops:after=after[:min(stops)]
            end=re.search(r'[;；。!?]',after)
            if end:after=after[:end.start()]
            values=_numbers(after)
            if not values:continue
            actual=_numbers(entry['value'])
            if len(actual)!=1:continue
            # A from-to comparison attributes the resulting value to this
            # current named row; an earlier baseline is not its own cell.
            change=re.search(r'从|由|from',after,re.I) and re.search(r'至|到|to\b',after,re.I)
            # A coordinated array may start after the last printed owner.
            # Its first number is not that owner's own measurement.  Only
            # the already-supported explicit from-to relation determines
            # which endpoint belongs to this row; other arrays are unclear.
            if len(values)>1 and not change:continue
            chosen=values[-1] if change else values[0]
            source_value,source_percent,_=actual[0]
            value,percent,_=chosen
            if value!=source_value:continue
            if source_percent and not percent:continue
            pairs.append({'row':row['name'],'body_name':name,'headers':entry['headers'],
                          'actual_value':entry['value'],'cell_bbox':entry['bbox'],'body_claim':scoped})
    unique={(p['row'],tuple(p['headers'])):p for p in pairs}
    if len(unique)<2:return None
    return {'kind':'actual_named_row_metric_and_value_relations','matched_fields':[' / '.join(p['headers']) for p in unique.values()],
            'matched_values':[p['actual_value'] for p in unique.values()],'relations':list(unique.values())}


def _parallel_prompt_contract(descriptor,text):
    title=descriptor['title'];source=' '.join(l.text for l in descriptor['cells'])
    if not re.search(r'并联|parallel',title,re.I) or not re.search(r'prompt|提示',title,re.I):return None
    if re.search(r'prior.?stage|前一阶段|先前阶段|上一步.*分析|特征分析结果',source,re.I):return None
    if not (re.search(r'待检测文本|input\s+text',source,re.I) and
            re.search(r'判断|decision',source,re.I) and re.search(r'依据|解释|explanation',source,re.I) and
            re.search(r'Human|人类',source,re.I) and re.search(r'LLM|语言模型',source,re.I)):return None
    requirements=(r'并联|parallel',r'多个.*模型|多模型|multiple.*models?',
                  r'同一[^。;；!?]{0,15}(?:文本|输入)|same\s+(?:input\s+)?text',
                  r'各自|独立|independent',r'来源判断|判别结论|source\s+(?:decision|judg)',
                  r'解释|依据|explanation',r'融合|汇聚|汇总|fusion|aggregat')
    if not all(re.search(rx,text,re.I) for rx in requirements):return None
    return {'kind':'parallel_shared_input_and_independent_prompt_output_contract',
            'matched_fields':['same input text','independent source decision','explanation','fused outputs'],
            'matched_values':[],'relations':[{'actual_prompt':source,'body_contract':text}]}


def _named_metric_change(descriptor,text):
    """The printed source/target relation binds both ends of one metric change."""
    from .usage_table_evidence import _numbers,_explicit_table_numbers
    if _explicit_table_numbers(text):return None
    if re.search(r'配置|configuration|settings?|architecture',descriptor['title'],re.I):return None
    rows=descriptor['_numeric_matrix'] if '_numeric_matrix' in descriptor else _numeric_row_matrix(descriptor)
    if not rows:return None
    named=[]
    for ordinal,row in enumerate(rows):
        for alias in _row_aliases(row):
            pattern=re.escape(alias).replace(r'\ ',r'\s*')
            if alias.isascii():pattern=r'(?<![A-Za-z0-9_.-])'+pattern+r'(?![A-Za-z0-9_.-])'
            named.extend((m.start(),m.end(),ordinal,alias) for m in re.finditer(pattern,normalize_text(text),re.I))
    normalized=normalize_text(text)
    for comparison in re.finditer(r'相较(?:于)?|相比(?:于)?|compared\s+(?:with|to)|relative\s+to',normalized,re.I):
        before=[m for m in named if m[1]<=comparison.start()]
        after=[m for m in named if m[0]>=comparison.end()]
        if not before or not after:continue
        target=max(before,key=lambda m:m[1]);source=min(after,key=lambda m:m[0])
        if target[2]==source[2]:continue
        stop=min([m[0] for m in named if m[0]>=source[1] and m[2] not in {target[2],source[2]}] or [len(normalized)])
        claim=normalized[source[1]:stop]
        for actual in rows[source[2]]['entries']:
            others=[e for e in rows[target[2]]['entries'] if e['headers']==actual['headers']]
            if len(others)!=1 or len(actual['headers'])!=1:continue
            aliases=[actual['headers'][-1]]
            for pattern,equivalents in _MEASUREMENT_ALIASES:
                if re.search(pattern,aliases[0],re.I):aliases.extend(equivalents)
            if not any(re.search(p,aliases[0],re.I) for p,_ in _MEASUREMENT_ALIASES):continue
            for alias in aliases:
                metric=re.search(re.escape(alias).replace(r'\ ',r'\s*'),claim,re.I)
                if not metric:continue
                chain=re.search(r'(?:由|从|from)\s*([+-]?\d+(?:\.\d+)?%?)[^。;；!?]{0,30}?(?:下降至|提升至|降低至|增至|降至|升至|至|到|to)\s*([+-]?\d+(?:\.\d+)?%?)',
                                claim[metric.end():],re.I)
                if not chain:continue
                first,last=_numbers(chain[1]),_numbers(chain[2]);a,b=_numbers(actual['value']),_numbers(others[0]['value'])
                if len(first)!=1 or len(last)!=1 or len(a)!=1 or len(b)!=1:continue
                if (first[0][:2],last[0][:2])!=(a[0][:2],b[0][:2]):continue
                return {'kind':'named_source_target_metric_change_with_real_end_values',
                        'matched_fields':actual['headers'],'matched_values':[actual['value'],others[0]['value']],
                        'relations':[{'source_row':rows[source[2]]['name'],'target_row':rows[target[2]]['name'],
                                      'source_cell':actual,'target_cell':others[0],'body_chain':chain[0]}]}
    return None


def _native_symbol_definitions(descriptor,text):
    grid=descriptor['_catalogue_grid'] if '_catalogue_grid' in descriptor else _grid(descriptor['cells'])
    if not grid:return []
    headers,columns=grid
    symbol=next((i for i,l in enumerate(headers) if re.fullmatch(r'符号|Symbols?|Notation',normalize_text(l.text).strip(),re.I)),None)
    meaning=next((i for i,l in enumerate(headers) if re.search(r'说明|含义|meaning|description',l.text,re.I)),None)
    if symbol is None or meaning is None or symbol==meaning:return []
    native=[]
    anchors=sorted(columns[symbol],key=lambda l:l.bbox[1])
    for ordinal,line in enumerate(anchors):
        name=normalize_text(line.text).strip()
        if not name or len(name)>40:continue
        top=line.bbox[1]-max(3,line.bbox[3]-line.bbox[1]);stop=(anchors[ordinal+1].bbox[1]-2 if ordinal+1<len(anchors) else float('inf'))
        description=' '.join(l.text for l in columns[meaning] if top<=l.bbox[1]<stop)
        # Source rows with superscript/subscript ink retain an overlapping
        # native first-column metric label alongside the actual symbol.
        label=' '.join(l.text for l in columns[0] if symbol!=0 and
                       abs((l.bbox[1]+l.bbox[3]-line.bbox[1]-line.bbox[3])/2)<max(8,line.bbox[3]-line.bbox[1]))
        if description:native.append({'name':name,'label':label,'description':description,'bbox':list(line.bbox)})
    pairs=[]
    for owner,name,claim in _body_windows(native,text,lambda row:[row['name']],sentence_bound=False):
        if not re.search(r'指|定义|表示|用于|计算|denot|represent|means?|defined|refers?',claim,re.I):continue
        row=native[owner]
        source=row['description']+' '+row['label']
        meanings=_content_phrases(source,claim)
        # A preceding independent definition label can identify the same
        # metric; its following clause must still define the symbol.
        if not meanings and row['label']:
            start=normalize_text(text).find(name)
            prefix=normalize_text(text)[max(0,start-45):start]
            meanings=_content_phrases(row['label'],prefix)
        if meanings:pairs.append({'field':row['name'],'actual_label':row['label'],
                                  'actual_meaning':row['description'],'body_meaning_phrases':meanings,
                                  'body_claim':claim,'symbol_bbox':row['bbox']})
    normalized=normalize_text(text)
    for row in native:
        name=re.sub(r'\s+','',normalize_text(row['name']))
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,8}|[α-ωΑ-Ω]',name):continue
        pattern=r'(?<![A-Za-z0-9_])'+re.escape(name)+r'(?![A-Za-z0-9_])'
        for mention in re.finditer(pattern,normalized):
            before=normalized[max(0,mention.start()-65):mention.start()]
            before=re.split(r'[。;；!?]',before)[-1]
            after=re.split(r'[。;；!?]',normalized[mention.end():mention.end()+90])[0]
            forward=re.match(r'\s*(?:表示|指|为|denotes?\b|represents?\b|means?\b)',after,re.I)
            backward=re.search(r'(?:为|记为|denoted\s+by|denoted\s+as)\s*$',before,re.I)
            if not forward and not backward:continue
            claim=after if forward else before
            source=row['description']
            meanings=_content_phrases(source,claim)
            concepts=((r'子载波(?:的)?数量',r'子载波(?:的)?数量'),
                      (r'(?:数字)?调制(?:的)?阶数',r'调制(?:的)?阶数'),
                      (r'比特(?:位宽|宽度)',r'比特(?:位宽|宽度)'),
                      (r'量化(?:比例)?系数',r'量化(?:比例)?系数'))
            meanings.extend(a for a,b in concepts if re.search(a,source,re.I) and re.search(b,claim,re.I))
            if meanings and not any(p['field']==row['name'] for p in pairs):
                pairs.append({'field':row['name'],'actual_label':row['label'],
                              'actual_meaning':source,'body_meaning_phrases':meanings,
                              'body_claim':before+mention[0]+after,'symbol_bbox':row['bbox']})
    return pairs


def _ontology_role_relations(descriptor,text):
    grid=descriptor['_catalogue_grid'] if '_catalogue_grid' in descriptor else _grid(descriptor['cells'])
    if not grid:return None
    headers=[normalize_text(l.text).strip() for l in grid[0]]
    if headers!=['Class','Property/Relation','Type','Range']:return None
    verbs=((r'^hosts?(?=[A-Z_])',r'搭载|承载|host'),
           (r'^has(?=[A-Z_])',r'提供|具有|具备|可供|offers?|provid|has\b'),
           (r'^(?:includes?|contains?)(?=[A-Z_])',r'包含|包括|包括|includ|contain'))
    rows=descriptor['_native_relation_rows'] if '_native_relation_rows' in descriptor else _relation_rows(descriptor['cells'])
    normalized=re.sub(r'([a-z])-\s+([a-z])',r'\1\2',normalize_text(text))
    pairs=[]
    for row in rows:
        if len(row['purposes'])!=3:continue
        prop,kind,range_name=row['purposes']
        if kind.strip()!='Object':continue
        operation=next((body for source,body in verbs if re.search(source,prop)),None)
        if not operation:continue
        owner=row['name'];range_name=range_name.strip()
        a=r'(?<![A-Za-z0-9_.-])'+re.escape(owner)+r'(?![A-Za-z0-9_.-])'
        b=r'(?<![A-Za-z0-9_.-])'+re.escape(range_name)+r'(?![A-Za-z0-9_.-])'
        for first in re.finditer(a,normalized):
            end=re.search(b,normalized[first.end():first.end()+180])
            if not end:continue
            clause=normalized[first.end():first.end()+end.start()]
            # A different named provider between the source class and its
            # range owns the relation; it cannot donate a verb to this row.
            intervening=re.findall(r'(?<![A-Za-z0-9_-])[A-Z][A-Za-z0-9_-]{2,}(?![A-Za-z0-9_-])',clause)
            if any(word!=owner and not re.fullmatch(r'Hosts?|Provides?|Offers?|Includes?|Contains?',word,re.I)
                   for word in intervening):continue
            if re.search(operation,clause,re.I) and not re.search(r'不包含|不包括|不提供|不搭载|not\b',clause,re.I):
                pairs.append({'class':owner,'actual_property':prop,'actual_range':range_name,'body_relation':clause});break
    if len({(p['class'],p['actual_property'],p['actual_range']) for p in pairs})<2:return None
    return {'kind':'actual_directed_class_property_range_relations','matched_fields':[p['actual_property'] for p in pairs],
            'matched_values':[p['actual_range'] for p in pairs],'relations':pairs}


def _body_windows(rows,text,aliases,*,sentence_bound=True):
    normalized=re.sub(r'([a-z])-\s+([a-z])',r'\1\2',normalize_text(text));mentions=[]
    for ordinal,row in enumerate(rows):
        for name in aliases(row):
            pattern=re.escape(name).replace(r'\ ',r'\s*')
            if name.isascii():pattern=r'(?<![A-Za-z0-9_.-])'+pattern+r'(?![A-Za-z0-9_.-])'
            mentions.extend((m.start(),m.end(),ordinal,name) for m in re.finditer(pattern,normalized,re.I))
    out=[]
    for start,end,owner,name in mentions:
        following=[a for a,_,other,_ in mentions if other!=owner and a>=end]
        stop=min(following) if following else len(normalized)
        boundary=re.search(r'[。;；!?]|(?<!\d)\.(?!\d)',normalized[end:stop]) if sentence_bound else None
        if boundary:stop=end+boundary.start()
        out.append((owner,name,normalized[end:stop]))
    return out


_CONFIG_ROLES=((r'视觉|影像|图像|vision|image',r'视觉|影像|图像|MRI|vision|image'),
               (r'文本|语言|text|language',r'文本|语言|text|language'),
               (r'编码|encoder',r'编码|encod'),(r'PEFT',r'PEFT'),
               (r'语音|speech',r'语音|speech'),(r'训练|train',r'训练|train'))


def _setting_agrees(source,claim):
    shape=re.compile(r'\d+(?:[×x]\d+){1,3}')
    source_shapes={m[0] for m in shape.finditer(_norm(source))}
    if any(m[0] not in source_shapes for m in shape.finditer(_norm(claim))):return False
    setting=re.compile(r'([A-Za-z][A-Za-z_]+)\s*(?:=|为|is)\s*(\d+(?:\.\d+)?)',re.I)
    settings={m[1].casefold():m[2] for m in setting.finditer(normalize_text(source))}
    return all(m[1].casefold() not in settings or settings[m[1].casefold()]==m[2]
               for m in setting.finditer(normalize_text(claim)))


def _configuration(descriptor,text):
    if not re.search(r'配置|configuration|settings?',descriptor['title'],re.I):return None
    rows=_relation_rows(descriptor['cells']);pairs=[]
    for owner,name,claim in _body_windows(rows,text,lambda row:_named_values(' '.join(row['purposes']))):
        row=rows[owner];value=' '.join(row['purposes'])
        roles=[body_rx for source_rx,body_rx in _CONFIG_ROLES if re.search(source_rx,row['name'],re.I)]
        if not roles:continue
        if not _setting_agrees(value,claim):return None
        if not all(re.search(rx,claim,re.I) for rx in roles):continue
        if not re.search(r'编码|使用|采用|输入|学习|训练|encode|uses?|input|learn|train',claim,re.I):continue
        pairs.append({'field':row['name'],'actual_setting':value,'body_name':name,'body_claim':claim})
    unique={p['field']:p for p in pairs}
    if len(unique)<2:return None
    return {'kind':'actual_named_configuration_and_distinct_roles','matched_fields':list(unique),
            'matched_values':[p['body_name'] for p in unique.values()], 'relations':list(unique.values())}


def _configuration_row_relations(descriptor,text):
    """Named alternatives must own actual field values or specific properties.

    A name's embedded numbers never supply a parameter. Numeric claims follow
    the real column header, including coordinated headers with a shared value.
    Properties come from the actual descriptive cell in that same named row.
    """
    if not re.search(r'配置|configuration|settings?',descriptor['title'],re.I):return None
    phases=(r'预填充|prefill',r'解码|decode|decoding')
    for ordinal,phase in enumerate(phases):
        if (re.search(phase,descriptor['title'],re.I) and
                re.search(phases[1-ordinal],text,re.I) and not re.search(phase,text,re.I)):return None
    grid=_grid(descriptor['cells'])
    if not grid:return None
    header,_=grid
    rows=_relation_rows(descriptor['cells'])
    if len(header)<3:return None
    fields=[normalize_text(l.text).strip() for l in header[1:]]
    field_patterns=[re.escape(field).replace(r'\ ',r'\s*') for field in fields]
    joined='|'.join(field_patterns)
    numeric=re.compile(r'^([+-]?\d+(?:\.\d+)?)([A-Za-z%]*)$')
    pairs=[]
    for owner,name,claim in _body_windows(rows,text,lambda row:[normalize_text(row['name']).strip()]):
        row=rows[owner]
        if not re.search(r'[A-Za-z]{3}|[\u4e00-\u9fff]{2}',name):continue
        numeric_fields=[];property_fields=[]
        for field,pattern,value in zip(fields,field_patterns,row['purposes']):
            source_value=numeric.fullmatch(normalize_text(value).replace(' ',''))
            if source_value:
                amount,unit=source_value.groups()
                assigned=re.compile(pattern+r'(?:\s*(?:与|和|、|and)\s*(?:'+joined+r'))*'
                    r'\s*(?:均为|均是|both\s+(?:are|of)|=|为|is|of|are)?\s*'
                    r'([+-]?\d+(?:\.\d+)?)([A-Za-z%]*)(?![\d.])',re.I)
                values=[(m[1],m[2],m[0]) for m in assigned.finditer(claim)]
                # A real unit such as B ties a parameter-scale statement to
                # this cell even when prose puts "parameters" after its value.
                if unit:
                    values.extend((m[1],m[2],m[0]) for m in re.finditer(
                        r'(?<![A-Za-z\d.])([+-]?\d+(?:\.\d+)?)('+re.escape(unit)+r')(?![A-Za-z\d.])',claim,re.I))
                if any(a!=amount or u.casefold()!=unit.casefold() for a,u,_ in values):return None
                if values:numeric_fields.append({'field':field,'actual_value':value,'body_claims':[v[2] for v in values]})
            elif re.search(r'特点|说明|描述|特性|characteristic|description|propert|features?',field,re.I):
                phrases=_content_phrases(value,claim)
                positive=[]
                normalized=_norm(claim)
                for phrase in phrases:
                    start=normalized.find(phrase)
                    before=normalized[max(0,start-12):start]
                    if not re.search(r'不是|不具备|没有|缺乏|without|not|lack',before,re.I):positive.append(phrase)
                if positive:property_fields.append({'field':field,'actual_properties':value,'body_phrases':positive})
        # Two field-value relations or one specific descriptive property per
        # named alternative; a single loosely mentioned alternative is not
        # sufficient to choose a catalogue/configuration table.
        if len(numeric_fields)>=2 or property_fields:
            pairs.append({'configuration':row['name'],'body_name':name,
                          'numeric_fields':numeric_fields,'property_fields':property_fields,'body_claim':claim})
    unique={p['configuration']:p for p in pairs}
    if len(unique)<2:return None
    return {'kind':'actual_named_configuration_row_relations','matched_fields':list(unique),
            'matched_values':[v['actual_value'] for p in unique.values() for v in p['numeric_fields']],
            'relations':list(unique.values())}


def _configuration_descriptive_relations(descriptor,text):
    """A named method owns at least two actual descriptive configuration cells."""
    if not re.search(r'配置|configuration|settings?',descriptor['title'],re.I):return None
    grid=_grid(descriptor['cells'])
    if not grid or len(grid[0])<3:return None
    headers=[l.text for l in grid[0][1:]];rows=_relation_rows(descriptor['cells'])
    if not re.search(r'输入|上下文|推理|input|context|reason', ' '.join(headers),re.I):return None
    for owner,name,claim in _body_windows(rows,text,lambda row:_named_values(row['name']),sentence_bound=False):
        pairs=[]
        for ci,(field,value) in enumerate(zip(headers,rows[owner]['purposes'])):
            if not value.strip():continue
            for other in rows:
                foreign=other['purposes'][ci] if len(other['purposes'])>ci else ''
                if len(_norm(foreign))>=4 and _norm(foreign)!=_norm(value) and _present(foreign,claim) and not _present(value,claim):
                    return None
            phrases=_content_phrases(value,claim)
            if any(re.search(r'不(?:使用|采用|引入)|不用|without|not\s+us',
                             _norm(claim)[max(0,_norm(claim).find(p)-12):_norm(claim).find(p)],re.I) for p in phrases):return None
            if re.search(r'输入粒度|input\s+granularity',field,re.I):
                granularity=((r'^全文$',r'全文|完整[^。.!?]{0,18}(?:文本|文档)|full\s+(?:text|document)'),
                             (r'^单句$',r'单句|独立[^。.!?]{0,8}句子|sentence[- ]level'),
                             (r'^语义块$',r'语义块|文本块|语义划分|semantic\s+chunks?'))
                phrases += [m[0] for source_rx,body_rx in granularity if re.search(source_rx,value)
                            for m in re.finditer(body_rx,claim,re.I)]
            if phrases:pairs.append({'field':field,'actual_value':value,'body_phrases':list(dict.fromkeys(phrases))})
        if len(pairs)>=2:
            return {'kind':'actual_method_owned_descriptive_configuration','matched_fields':[p['field'] for p in pairs],
                    'matched_values':[name],'relations':[{'method':rows[owner]['name'],'body_name':name,'attributes':pairs,'body_claim':claim}]}
    return None


def _exact_identifier(name,text):
    return bool(re.search(r'(?<![A-Za-z0-9_.-])'+re.escape(name)+r'(?![A-Za-z0-9_.-])',normalize_text(text),re.I))


def _typed_configuration_parameters(descriptor,text):
    from .usage_table_evidence import _explicit_table_numbers
    if _explicit_table_numbers(text) or not re.search(r'配置|设置|configuration|settings?',descriptor['title'],re.I):return None
    grid=descriptor.get('_catalogue_grid') or _grid(descriptor['cells'])
    if not grid or len(grid[0])!=2 or not re.search(r'参数|设置|parameters?|settings?',grid[0][0].text,re.I):return None
    rows=descriptor.get('_native_relation_rows') or _relation_rows(descriptor['cells'])
    def aliases(row):
        name=normalize_text(row['name']).strip()
        names=[name]
        chinese=re.match(r'[\u4e00-\u9fff/ ]+',name)
        if chinese:names.append(chinese[0].strip())
        names +=[n.removeprefix('数字风洞') for n in names if n.startswith('数字风洞')]
        names +=[n.replace('最小','最低',1) for n in names if n.startswith('最小')]
        return list(dict.fromkeys(n for n in names if len(_norm(n))>=4))
    def parse(value):
        value=normalize_text(value)
        interval=re.search(r'[\[(]\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*[\])]\s*(mm|cm|m|ms|s)\b',value,re.I)
        if interval:return ('interval',tuple(float(interval[i]) for i in [1,2]),interval[3].lower(),interval[0])
        scalar=re.search(r'(?<![\d.])([+-]?\d+(?:\.\d+)?)\s*(m\s*s\s*[-^]?\s*1|m\s*/\s*s|mm|cm|ms|m|s|GPU\s*小时|h)(?![A-Za-z])',value,re.I)
        if not scalar:return None
        unit=re.sub(r'\s+','',scalar[2]).lower()
        if unit in ['ms-1','ms1','m/s','ms^1']:unit='m/s'
        return ('scalar',(float(scalar[1]),),unit,scalar[0])
    pairs=[]
    for owner,name,claim in _body_windows(rows,text,aliases):
        actual=parse(' '.join(rows[owner]['purposes']))
        if not actual:continue
        body=parse(claim)
        if not body:continue
        if body[:3]!=actual[:3]:return None
        pairs.append({'field':rows[owner]['name'],'native_value':' '.join(rows[owner]['purposes']),
                      'typed_values':actual[1],'unit':actual[2],'body_claim':name+claim,'body_value':body[3]})
    unique={p['field']:p for p in pairs}
    if len(unique)<3:return None
    return {'kind':'native_parameter_owned_physical_units_and_ranges',
            'matched_fields':list(unique),'matched_values':[p['body_value'] for p in unique.values()],
            'relations':list(unique.values())}


def _native_training_panels(descriptor,text):
    from .usage_table_evidence import _explicit_table_numbers
    if _explicit_table_numbers(text) or not re.search(r'训练.*参数|training\s+parameters?',descriptor['title'],re.I):return None
    grid=descriptor.get('_catalogue_grid') or _grid(descriptor['cells'])
    if not grid or len(grid[0])!=2 or not re.search(r'参数|Parameter',grid[0][0].text,re.I):return None
    rows=descriptor.get('_native_relation_rows') or _relation_rows(descriptor['cells'])
    from .usage_table_evidence import _cell_rows
    headings=[]
    for ink in _cell_rows(descriptor['cells']):
        if len(ink)!=1:continue
        line=ink[0];name=normalize_text(line.text).strip()
        if abs(line.bbox[0]-grid[0][0].bbox[0])>10:continue
        role=('semi-supervised' if re.fullmatch(r'(?:[A-Za-z-]+\s+){0,3}Semi[- ]supervised\s+learning',name,re.I) else
              'segmentation' if re.fullmatch(r'Segmentation\s+training',name,re.I) else None)
        if role:headings.append((line,role))
    headings.sort(key=lambda h:h[0].bbox[1]);panels=[]
    for ordinal,(line,role) in enumerate(headings):
        bottom=headings[ordinal+1][0].bbox[1] if ordinal+1<len(headings) else float('inf')
        panels.append({'role':role,'name':line.text,'rows':[r for r in rows if line.bbox[3]<=r['anchor'].bbox[1]<bottom]})
    if len(panels)!=2 or {p['role'] for p in panels}!={'segmentation','semi-supervised'}:return None
    normalized=re.sub(r'(\d{1,3}),(\d{3})(?!\d)',r'\1\2',normalize_text(text))
    normalized=re.sub(r'(?<=[A-Za-z])-\s+(?=[A-Za-z])','',normalized)
    ordinary=re.search(r'\bsegmentation\s+model\b',normalized,re.I)
    semi=re.search(r'\bsemi[- ]supervised\b[^。!?]{0,65}?\b(?:segmentation|learning)\b',normalized,re.I)
    if not ordinary or not semi or ordinary.start()>=semi.start():return None
    if not re.search(r'train[^。!?]{0,25}separately|separately[^。!?]{0,25}train',normalized[semi.start():semi.end()+90],re.I):return None
    portions={'segmentation':normalized[ordinary.start():semi.start()],
              'semi-supervised':normalized[semi.start():]}
    patterns=((r'^Training\s+epochs?$',r'(\d+)\s*epochs?\b'),
              (r'^Iterations?$',r'(\d+)\s*iterations?\b'),
              (r'^Batch\s+size$',r'\bbatch\s+size\s*(?:of|=|:)?\s*(\d+)'),
              (r'^EMA\s+decay$',r'\bEMA\s+decay\s*\(?\s*(\d+(?:\.\d+)?)'),
              (r'^Early\s+stopping$',r'\bpatience\s*(?:of|=|:)?\s*(\d+)'))
    proof=[]
    for panel in panels:
        claim=portions[panel['role']];matched=[]
        for row in panel['rows']:
            field=normalize_text(row['name']).strip();source=' '.join(row['purposes'])
            if re.fullmatch(r'Optimizer',field,re.I):
                if _exact_identifier(source.strip(),claim):matched.append({'field':field,'native_value':source,'body_value':source.strip()})
                continue
            for native_rx,body_rx in patterns:
                if not re.search(native_rx,field,re.I):continue
                source_numbers=re.findall(r'\d+(?:\.\d+)?',re.sub(r'(\d{1,3}),(\d{3})(?!\d)',r'\1\2',source))
                if len(source_numbers)!=1:continue
                values=list(re.finditer(body_rx,claim,re.I))
                if any(float(m[1])!=float(source_numbers[0]) for m in values):return None
                if values:matched.append({'field':field,'native_value':source,'body_claims':[m[0] for m in values]})
        if len(matched)<3:return None
        proof.append({'native_panel':panel['name'],'role':panel['role'],'field_relations':matched,'body_claim':claim})
    return {'kind':'native_training_phase_owned_configuration_fields',
            'matched_fields':[p['native_panel']+'/'+r['field'] for p in proof for r in p['field_relations']],
            'matched_values':[],'relations':proof}


def _step_token_contract(descriptor,text):
    from .usage_table_evidence import _explicit_table_numbers
    if _explicit_table_numbers(text) or not re.search(r'tokens?',descriptor['title'],re.I):return None
    grid=descriptor.get('_catalogue_grid') or _grid(descriptor['cells'])
    if not grid or len(grid[0])!=4:return None
    headers,columns=grid
    if (not re.search(r'步骤|steps?',headers[0].text,re.I) or
            not re.search(r'输入.*token|input.*token',headers[1].text,re.I) or
            not re.search(r'输出.*token|output.*token',headers[2].text,re.I)) :return None
    def compact(value):return re.sub(r'\d{1,3}(?:\s+\d{3})+',lambda m:re.sub(r'\s+','',m[0]),normalize_text(value))
    rows=_relation_rows(descriptor['cells']);step_rows=[r for r in rows if re.fullmatch(r'\d+',r['name'].strip())]
    if len(step_rows)<3:return None
    step_rows.sort(key=lambda r:int(r['name']));first,last=step_rows[0],step_rows[-1]
    values=[]
    for row in step_rows:
        row_values=[]
        for cell in row['purposes']:
            numbers=re.findall(r'\d+',compact(cell))
            if len(numbers)!=1:break
            row_values.append(int(numbers[0]))
        if len(row_values)!=3 or row_values[0]+row_values[1]!=row_values[2]:return None
        values.append(row_values)
    normalized=compact(text)
    boundary=re.search(r'第\s*(\d+)\s*步\s*(?:到|至)\s*第\s*(\d+)\s*步',normalized)
    if not boundary or [int(boundary[1]),int(boundary[2])]!=[int(first['name']),int(last['name'])]:return None
    claims=[]
    for ci,(field,start,end,direction) in enumerate([('input',values[0][0],values[-1][0],r'增长|增加|increase'),
                                                   ('output',values[0][1],values[-1][1],r'下降|减少|decrease')]):
        rx=r'(?:输入|input)' if ci==0 else r'(?:输出|output)'
        claim=re.search(rx+r'\s*tokens?[^。!?;；]{0,20}?(?:从|from)[^\d。!?]{0,8}(\d+)[^。!?;；]{0,12}?(?:到|至|to)\s*(?:约|about\s+|approximately\s+)?\s*(\d+)',normalized,re.I)
        if not claim or [int(claim[1]),int(claim[2])]!=[start,end] or not re.search(direction,claim[0],re.I):return None
        actual=[r[ci] for r in values]
        if ci==0 and actual!=sorted(actual) or ci==1 and actual!=sorted(actual,reverse=True):return None
        claims.append({'channel':field,
                       'native_first_row':{'name':first['name'],'values':first['purposes'],'bbox':list(first['anchor'].bbox)},
                       'native_last_row':{'name':last['name'],'values':last['purposes'],'bbox':list(last['anchor'].bbox)},
                       'body_claim':claim[0]})
    aggregates=[r for r in rows if re.search(r'总计|合计|total',r['name'],re.I)]
    if len(aggregates)!=1:return None
    amounts=[re.findall(r'\d+',compact(v)) for v in aggregates[0]['purposes']]
    if len(amounts)!=3 or any(len(a)!=1 for a in amounts):return None
    totals=[int(a[0]) for a in amounts]
    if totals!=[sum(row[i] for row in values) for i in range(3)]:return None
    budget=re.search(r'(?:总\s*token|total\s+tokens?)[^\d。!?]{0,15}(\d+)',normalized,re.I)
    if not budget or int(budget[1])!=totals[2]:return None
    return {'kind':'native_step_channel_endpoints_and_aggregate_budget',
            'matched_fields':['input tokens','output tokens','aggregate token budget'],
            'matched_values':[str(values[0][0]),str(values[-1][0]),str(values[0][1]),str(values[-1][1]),str(totals[2])],
            'relations':claims,'native_aggregate_row':{'name':aggregates[0]['name'],'values':aggregates[0]['purposes'],
                'bbox':list(aggregates[0]['anchor'].bbox)},'body_total_claim':budget[0]}


def _hardware_configuration(descriptor,text):
    """Native instance/capacity or device/topology relations, with typed units."""
    if not re.search(r'配置|实验环境|configuration|experimental\s+(?:setup|environment)|settings?',descriptor['title'],re.I):return None
    rows=_relation_rows(descriptor['cells'])
    instance=next((r for r in rows if re.search(r'实例类型|instance\s+type',r['name'],re.I)),None)
    if instance and instance['purposes']:
        identifiers=re.findall(r'[A-Za-z][A-Za-z0-9_.-]*',instance['purposes'][0])
        identifiers=[n for n in identifiers if any(c.isdigit() for c in n)]
        for name in identifiers:
            if not _exact_identifier(name,text):continue
            position=re.search(re.escape(name),normalize_text(text),re.I).end()
            claim=re.split(r'[。!?]|(?<!\d)\.(?!\d)',normalize_text(text)[position:],maxsplit=1)[0]
            pairs=[]
            for row in rows:
                if not row['purposes']:continue
                value=re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(vCPUs?|GB)\s*',row['purposes'][0],re.I)
                if not value:continue
                amount,unit=value.groups()
                if unit.casefold().startswith('vcpu') and not re.search(r'CPU|核心|cores?',row['name'],re.I):continue
                if unit.casefold()=='gb' and not re.search(r'内存|memory|RAM',row['name'],re.I):continue
                body_unit=r'(?:虚拟)?CPU|vCPUs?' if unit.casefold().startswith('vcpu') else r'GB'
                matches=list(re.finditer(r'(?<![A-Za-z0-9_.-])(\d+(?:\.\d+)?)\s*(?:个\s*)?\s*(?:'+body_unit+r')(?![A-Za-z])',claim,re.I))
                if any(m[1]!=amount for m in matches):return None
                if matches:pairs.append({'field':row['name'],'actual_value':row['purposes'][0],'body_claims':[m[0] for m in matches]})
            if len(pairs)>=2:
                return {'kind':'actual_instance_and_typed_hardware_capacities','matched_fields':[instance['name'],*[p['field'] for p in pairs]],
                        'matched_values':[name],'relations':pairs}
    device=next((r for r in rows if re.search(r'GPU.*节点|GPU\s+nodes?',r['name'],re.I)),None)
    network=next((r for r in rows if re.search(r'网络|network',r['name'],re.I)),None)
    if not device or not network:return None
    value=' '.join(device['purposes'])
    structure=re.search(r'(\d+)\s*(?:个)?节点[，,、\s]*(?:每(?:个)?节点)\s*(\d+)\s*张?\s*([A-Za-z][A-Za-z0-9_.-]*)\s+GPU',normalize_text(value))
    if not structure:return None
    nodes,per_node,name=structure.groups()
    pattern=r'(?<!\d)(\d+)\s*(?:个)?节点[，,、\s]*(?:每(?:个)?节点)\s*(\d+)\s*张?\s*'+re.escape(name)+r'(?![A-Za-z0-9_.-])\s+GPU'
    actual=list(re.finditer(pattern,normalize_text(text),re.I))
    if not actual or any(m[1]!=nodes or m[2]!=per_node for m in actual):return None
    def topology(value):
        return {m[1]:m[2] for m in re.finditer(r'节点(间|内)\s*([^，,；;。]+)',normalize_text(value))}
    source=topology(' '.join(network['purposes']));body=topology(text)
    if set(source)!=set(('间','内')) or not all(_norm(v) in _norm(body.get(role,'')) for role,v in source.items()):return None
    return {'kind':'actual_device_node_counts_and_owned_network_topology','matched_fields':[device['name'],network['name']],
            'matched_values':[name],'relations':[{'device':name,'nodes':nodes,'devices_per_node':per_node,'body_claims':[m[0] for m in actual]},
                                               {'network_topology':source,'body_topology':body}]}


def _feature_purpose_relations(descriptor,text):
    """One native schema attribute owns its own independent functional prose."""
    grid=_grid(descriptor['cells'])
    if not grid:return []
    header,columns=grid
    feature=next((i for i,l in enumerate(header) if re.search(r'特征属性|feature\s+attribute',l.text,re.I)),None)
    purpose=next((i for i,l in enumerate(header) if re.search(r'描述.*作用|description.*purpose',l.text,re.I)),None)
    if feature is None or purpose is None:return []
    if not re.search(r'用于|用来|作为|控制|驱动|used?\s+(?:for|to)|controls?',text,re.I):return []
    anchors=sorted((l for l in columns[feature] if not normalize_text(l.text).strip().startswith(('(', '（'))),key=lambda l:l.bbox[1])
    rows=[]
    for i,line in enumerate(anchors):
        name=normalize_text(line.text).strip()
        if len(_norm(name))<3:continue
        top=line.bbox[1]-max(2,(line.font_size or 10)*.2)
        stop=anchors[i+1].bbox[1]-2 if i+1<len(anchors) else float('inf')
        meaning=' '.join(l.text for l in columns[purpose] if top<=l.bbox[1]<stop)
        rows.append({'name':name,'purpose':meaning})
    result=[]
    windows=_body_windows(rows,text,lambda row:[row['name']])
    functional=r'用于|用来|作为|控制|驱动|used?\s+(?:for|to)|controls?'
    def ranges(value):
        return {(float(m[1]),float(m[2])) for m in re.finditer(
            r'\[\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*\]',
            normalize_text(value).replace('−','-'))}
    spans=_body_windows(rows,text,lambda row:[row['name']],sentence_bound=False)
    contradicted={owner for owner,_,claim in spans if ranges(rows[owner]['purpose'])
                  and ranges(claim)-ranges(rows[owner]['purpose'])}
    # A field's functional claim ends at another native attribute or a
    # sentence boundary. Co-occurrence elsewhere in the paragraph cannot
    # borrow another attribute's purpose or a separate processor's use.
    for owner,name,claim in windows:
        if owner in contradicted or not re.search(functional,claim,re.I):continue
        phrases=_content_phrases(rows[owner]['purpose'],claim)
        if phrases and not re.search(r'不用于|不用|not\s+used',claim,re.I):
            result.append({'field':name,'actual_purpose':rows[owner]['purpose'],
                           'body_phrases':phrases,'body_claim':claim})
    # A definition can span sentences before the author separately repeats
    # the same attribute as the subject of its use. Require that real native
    # range, its actual descriptive content and an attribute-owned functional
    # sentence; another processor's subsequent use does not supply the latter.
    for owner,name,claim in spans:
        source_ranges=ranges(rows[owner]['purpose'])
        if owner in contradicted or not source_ranges or not source_ranges.intersection(ranges(claim)):continue
        phrases=_content_phrases(rows[owner]['purpose'],claim)
        own_function=[c for o,_,c in windows if o==owner and re.search(functional,c,re.I)
                      and not re.search(r'不用于|不用|not\s+used',c,re.I)]
        if phrases and own_function:
            result.append({'field':name,'actual_purpose':rows[owner]['purpose'],
                           'body_phrases':phrases,'body_claim':claim,
                           'actual_range':[list(v) for v in sorted(source_ranges)],
                           'functional_claims':own_function})
    return result


def _comparison_attributes(descriptor,text):
    if not re.search(r'对比|comparison|compare',descriptor['title'],re.I):return None
    grid=_grid(descriptor['cells'])
    if not grid:return None
    header,_=grid
    rows=_relation_rows(descriptor['cells'])
    if len(rows)<2 or len(header)<3:return None
    columns=[{'name':heading.text,'values':[{'field':r['name'],'value':r['purposes'][i-1]}
        for r in rows if len(r['purposes'])>=i]} for i,heading in enumerate(header[1:],1)]
    from .usage_table_evidence import _GENERIC
    ordinary=(_SEMANTIC_TITLE_FILLER|_GENERIC|{'approach','publication','input','modality',
        'paradigm','world','protocol','support','end','denotes','whether','employs'})
    def alternatives(row):
        return [name for name in _named_values(row['name'])
                if any(word.casefold() not in ordinary for word in re.findall(r'[A-Za-z][A-Za-z0-9_-]*',name))]
    oppositions=((r'最小化|minimi',r'最大化|maximi'),
                 (r'二值|binary|yes\s*/\s*no',r'全量标签|full[- ]label|k[- ]way'),
                 (r'动态.*成本|秩感知|rank',r'统一成本|uniform\s+cost|cost\s*\(x\)\s*=\s*1'))
    oppositions=(*oppositions,*[(b,a) for a,b in oppositions])
    for owner,name,claim in _body_windows(columns,text,alternatives,sentence_bound=False):
        pairs=[]
        for field in columns[owner]['values']:
            if any(re.search(expected,field['value'],re.I) and re.search(other,claim,re.I)
                   and not re.search(expected,claim,re.I) for expected,other in oppositions):return None
            phrases=_content_phrases(field['value'],claim)
            if phrases:pairs.append({'field':field['field'],'actual_value':field['value'],'body_phrases':phrases})
        if len({p['field'] for p in pairs})>=2:
            return {'kind':'actual_named_comparison_column_attributes',
                    'matched_fields':[p['field'] for p in pairs], 'matched_values':[name],
                    'relations':[{'column':columns[owner]['name'],'attributes':pairs,'body_claim':claim}]}
    return None


def _architecture_profile(descriptor,text):
    if not re.search(r'配置|架构|architecture|configuration|specification',descriptor['title'],re.I):return None
    from .usage_table_evidence import _cell_rows
    header=None
    for row in _cell_rows(descriptor['cells']):
        named=[l for l in row if re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*(?:\s+[A-Z][A-Za-z0-9_-]*)*',normalize_text(l.text).strip())
               and any(c.isupper() for c in l.text)
               and _norm(l.text) not in _SEMANTIC_TITLE_FILLER]
        if len(named)>=2:header=sorted(named,key=lambda l:l.bbox[0]);break
    if not header:return None
    centers=[(l.bbox[0]+l.bbox[2])/2 for l in header]
    profiles=[]
    for i,heading in enumerate(header):
        left=(centers[i-1]+centers[i])/2 if i else heading.bbox[0]-3
        right=(centers[i]+centers[i+1])/2 if i+1<len(header) else max(l.bbox[2] for l in descriptor['cells'])+3
        cells=sorted((l for l in descriptor['cells'] if l.bbox[1]>heading.bbox[3] and
                      left<=(l.bbox[0]+l.bbox[2])/2<=right),key=lambda l:(l.bbox[1],l.bbox[0]))
        counts=[int(m[1]) for l in cells for m in re.finditer(r'×\s*(\d+)\b',normalize_text(l.text))]
        dimensions=[int(m[1]) for l in cells for m in re.finditer(
            r'(?:dim|channels?|通道|Conv[A-Za-z]*)\s*[（(]?\s*(\d+)\b',normalize_text(l.text),re.I)]
        if len(counts)<3 or not dimensions:continue
        full=normalize_text(heading.text).strip();aliases=[full]
        split=re.fullmatch(r'(.+?)[-_/]([A-Za-z][A-Za-z0-9_]*)',full)
        if (split and len(split[2])>=3 and
                re.search(re.escape(split[1])+r'[^。.!?]{0,30}(?:模型变体|模型配置|variants?|configurations?)',text,re.I)):
            aliases.append(split[2])
        profiles.append({'name':full,'aliases':aliases,'channel':dimensions[0],'repeats':counts})
    mentions=[];normalized=normalize_text(text)
    for owner,profile in enumerate(profiles):
        for name in profile['aliases']:
            pattern=r'(?<![A-Za-z0-9_.-])'+re.escape(name)+r'(?![A-Za-z0-9_.-])'
            for m in re.finditer(pattern,normalized,re.I):
                if name!=profile['name'] and re.search(r'[A-Za-z][A-Za-z_-]*\s+$',normalized[max(0,m.start()-30):m.start()]):continue
                mentions.append((m.start(),m.end(),owner,name))
    pairs=[]
    for start,end,owner,name in mentions:
        following=[a for a,_,other,_ in mentions if other!=owner and a>=end]
        stop=min(following) if following else len(normalized)
        claim=normalized[end:stop]
        channel=re.search(r'(?:通道数|channels?|channel\s+width|embedding\s+dimension)\s*(?:[A-Za-z]\s*)?(?:[:：=]\s*)?(\d+)\b',claim,re.I)
        repeat=re.search(r'(?:层数|depths?|layers?(?:\s+counts?)?)\s*[:：=]?\s*[\[{(]([\d\s,，]+)[\]})]',claim,re.I)
        if not channel or not repeat:continue
        values=[int(v) for v in re.findall(r'\d+',repeat[1])];profile=profiles[owner]
        if int(channel[1])!=profile['channel'] or values!=profile['repeats']:return None
        pairs.append({'variant':profile['name'],'body_name':name,'actual_channel':profile['channel'],
                      'actual_ordered_repeats':profile['repeats'],'body_claim':claim})
    if not pairs:return None
    return {'kind':'actual_architecture_variant_channel_and_ordered_layers',
            'matched_fields':['initial channels','ordered stage repeats'],
            'matched_values':[p['variant'] for p in pairs],'relations':pairs}


def _component_metrics(descriptor,text):
    if not re.search(r'组件|部署|component|deploy',descriptor['title'],re.I):return None
    grid=_grid(descriptor['cells'])
    if not grid or not re.search(r'扩缩|监控|指标|scal|monitor|metric',grid[0][-1].text,re.I):return None
    rows=_relation_rows(descriptor['cells']);pairs=[]
    for owner,name,claim in _body_windows(rows,text,lambda row:[normalize_text(row['name']).strip()],sentence_bound=False):
        row=rows[owner]
        if len(row['purposes'])<2:continue
        scale=re.search(r'增加|增减|缩减|减少|扩展|扩容|扩缩|scal|increas|reduc',claim,re.I)
        if not scale:continue
        after=claim[scale.end():]
        last=name.split()[-1]
        # Metrics before a subsequent component name cannot be attributed to
        # that next component's replicas through a bag of shared words.
        if not re.search(r'副本|replica|instance',after,re.I):continue
        if not (_present(name,after) or _present(last,after) or re.search(r'其副本|its\s+replica',after,re.I)):continue
        if any(len(alias.split())>1 and alias.split()[-1].casefold()==last.casefold()
               and _norm(alias)!=_norm(name) for alias in _named_values(after)):
            continue
        metrics=[]
        for metric in re.split(r'[，,、/]|\b(?:and|or)\b|[与和]',row['purposes'][-1],flags=re.I):
            phrases=_content_phrases(metric,claim)
            if phrases:metrics.append({'actual_metric':metric,'body_phrases':phrases})
        if len({_norm(m['actual_metric']) for m in metrics})<2:continue
        pairs.append({'component':row['name'],'actual_duties':row['purposes'][0],
                      'metrics':metrics,'body_claim':claim})
    if not pairs:return None
    return {'kind':'actual_component_metrics_and_replica_control','matched_fields':[p['component'] for p in pairs],
            'matched_values':[],'relations':pairs}


def _materials(descriptor,text):
    if not re.search(r'材质|material',descriptor['title'],re.I):
        return None
    rows=_relation_rows(descriptor['cells']);pairs=[]
    shared=bool(re.search(r'参数(?:的)?协同|共同调整|combined\s+parameters|jointly\s+adjust',text,re.I))
    matched=[r for r in rows if _present(r['name'],text)]
    for row in matched:
        source=' '.join(row['purposes'])
        start=_norm(text).find(_norm(row['name']));end=len(_norm(text))
        later=[_norm(text).find(_norm(r['name']),start+len(_norm(row['name']))) for r in matched if r is not row]
        later=[i for i in later if i>=0]
        if later:end=min(later)
        claim=_norm(text)[start:end]
        direct=_content_phrases(source,claim)
        if direct and re.search(r'模拟|影响|控制|增强|表现|affect|control|enhanc|modulat',claim,re.I):
            pairs.append({'row':row['name'],'purpose':source,'body_phrases':direct});continue
        if not shared:
            continue
        # A collective parameter workflow must still describe actual object
        # properties from each row, rather than a bag of material nouns.
        for source_rx,body_rx in _PROPERTIES:
            if not re.search(source_rx,source,re.I):continue
            for match in re.finditer(r'(?:^|[，,、；;。]|例如|如|或|与)([\u4e00-\u9fff]{2,8}?)的('+body_rx+r')',text,re.I):
                obj=match[1]
                if len(obj)>=2 and _norm(obj) in _norm(source):
                    pairs.append({'row':row['name'],'purpose':source,'object':obj,'property':match[2]});break
            else:continue
            break
    unique={p['row']:p for p in pairs}
    if len(unique)>=2:
        return {'kind':'actual_material_parameter_object_property_relations','matched_fields':list(unique),
                'matched_values':[],'relations':list(unique.values())}
    return None


def _foreign_native_model(descriptor,text):
    """A printed model/framework identity must belong to this physical table."""
    names=re.findall(r'(?:使用|采用|\busing\s+)(?:了)?\s*([A-Z][A-Za-z0-9_.-]*)\s*(?:模型|方法|框架|软件|model(?:\s+group)?\b|method\b|framework\b|software\b)',text)
    if not names:return False
    owners=descriptor['title']+' '+' '.join(r['name'] for r in _relation_rows(descriptor['cells']))
    return any(not _present(name,owners) for name in names)


def _quality_panel_winner(descriptor,text):
    """Use one named dataset/panel across both native correlation stages."""
    from .usage_table_evidence import _cell_rows,_NUMBER
    if _foreign_native_model(descriptor,text):return None
    dataset=re.search(r'\bon\s+(?:the\s+)?([A-Za-z][A-Za-z0-9_-]*)\s+dataset',descriptor['title'],re.I)
    if not dataset or not _present(dataset[1],text):return None
    if not all(re.search(rx,text,re.I) for rx in [r'zero[- ]shot',r'fine[- ]tuning',r'\bSRCC\b',r'\bPLCC\b']):return None
    cells=descriptor['cells'];rows=_cell_rows(cells)
    panels=[r[0] for r in rows if len(r)==1 and re.fullmatch(r'[A-Za-z ]+Quality',r[0].text.strip(),re.I)]
    selected=[p for p in panels if _present(p.text,text)]
    if len(selected)!=1:return None
    panel=selected[0];top=min(p.bbox[1] for p in panels)
    metrics=sorted((l for l in cells if l.bbox[3]<top and re.fullmatch(r'SRCC|PLCC',l.text.strip(),re.I)),key=lambda l:l.bbox[0])
    if [l.text.strip().upper() for l in metrics]!=['SRCC','PLCC','SRCC','PLCC']:return None
    stages=[l for l in cells if l.bbox[3]<top and re.fullmatch(r'Zero[- ]shot|Fine[- ]tuning',l.text.strip(),re.I)]
    stages=sorted(stages,key=lambda l:l.bbox[0])
    if len(stages)!=2 or not re.fullmatch(r'Zero[- ]shot',stages[0].text.strip(),re.I):return None
    centers=[(l.bbox[0]+l.bbox[2])/2 for l in metrics]
    if any(abs((s.bbox[0]+s.bbox[2])/2-sum(centers[2*i:2*i+2])/2)>32 for i,s in enumerate(stages)):return None
    end=min((p.bbox[1] for p in panels if p.bbox[1]>panel.bbox[3]),default=float('inf'))
    native=[];winner=[]
    for row in rows:
        if not panel.bbox[3]<min(l.bbox[1] for l in row)<end:continue
        measured=[l for l in row if _NUMBER.fullmatch(normalize_text(l.text).strip())]
        if len(measured)!=4:continue
        measured=sorted(measured,key=lambda l:l.bbox[0])
        if any(abs((l.bbox[0]+l.bbox[2])/2-x)>20 for l,x in zip(measured,centers)):continue
        labels=[l for l in row if l.bbox[2]<measured[0].bbox[0]-4 and re.search(r'[A-Za-z]',l.text)]
        if not labels:continue
        owner=min(labels,key=lambda l:l.bbox[0]);values=[float(l.text.strip()) for l in measured]
        if any(a>=b for a,b in zip(values[:2],values[2:])):return None
        item={'owner':owner.text,'values':values,'native_cells':[{'text':l.text,'bbox':list(l.bbox)} for l in measured]}
        native.append(item)
        proposed=re.fullmatch(r'\s*([A-Za-z][A-Za-z0-9_-]*)\s*\((?:proposed|ours?)\)\s*',owner.text,re.I)
        if proposed:winner.append((item,proposed[1]))
    if len(native)<4 or len(winner)!=1:return None
    best,name=winner[0]
    if not _present(name,descriptor['title']) or not re.search(r'(?<![A-Za-z0-9_])'+re.escape(name)+r'(?![A-Za-z0-9_])[^.!?]{0,65}(?:best\s+performance|outperforms?)',text,re.I):return None
    if any(a<=b for r in native if r is not best for a,b in zip(best['values'],r['values'])):return None
    return {'kind':'actual_named_quality_panel_dataset_and_two_stage_native_winner',
            'matched_fields':[dataset[1],panel.text,name,'Zero-shot','Fine-tuning','SRCC','PLCC'],
            'matched_values':[],'relations':[{'native_dataset':dataset[1],'native_panel':panel.text,
                'native_stage_metrics':[l.text for l in metrics],'native_rows':native,'winner':name}]}


def _parameter_panel_optimum(descriptor,text):
    """A declared parameter owns a controlled native panel and every dataset."""
    from .usage_table_evidence import _cell_rows,_NUMBER
    if _foreign_native_model(descriptor,text):return None
    import unicodedata
    canonical=lambda s:unicodedata.normalize('NFKC',normalize_text(s))
    title=canonical(descriptor['title']);body=canonical(text)
    if not re.search(r'消融|ablation',title,re.I):return None
    grid=descriptor.get('_catalogue_grid') or _grid(descriptor['cells'])
    if not grid:return None
    header,_=grid;specs=[]
    for i,h in enumerate(header):
        name=canonical(h.text).strip()
        if not re.fullmatch(r'[A-Za-zα-ωΑ-Ω]',name):continue
        spec=re.search(re.escape(name)+r'\s*[（(]([^）)]+)[）)]',title)
        if spec:specs.append((i,name,spec[1]))
    if not specs:return None
    last=max(i for i,_,_ in specs)
    outcomes=[i for i,h in enumerate(header) if i>last and re.search(r'[A-Za-z]',h.text)
              and not re.fullmatch(r'average|avg\.?|mean',h.text.strip(),re.I)]
    if len(outcomes)<3:return None
    foreign=re.findall(r'(?:在\s*|\b(?:on|from|in)\s+)([A-Z][A-Za-z0-9_-]*)\s*(?:数据集|dataset)',body)
    if any(not any(_norm(v)==_norm(header[i].text) for i in outcomes) for v in foreign):return None
    rows=_cell_rows(descriptor['cells'])
    panels=[r[0] for r in rows if len(r)==1 and re.search(r'消融|ablation',r[0].text,re.I)]
    contracts=[]
    for column,variable,meaning in specs:
        claim=re.search(re.escape(variable)+r'\s*=\s*(\d+(?:\.\d+)?)([^。.!?]{0,100})',body)
        if not claim or not re.search(r'最优|最佳|optimal|best',claim[2],re.I):continue
        dataset_count=re.search(r'(\d+)\s*个(?:实验|测试)?数据集',claim[2])
        if not dataset_count or int(dataset_count[1])!=len(outcomes):continue
        candidates=[p for p in panels if _content_phrases(canonical(p.text),meaning)]
        if len(candidates)!=1:continue
        p=candidates[0];end=min((other.bbox[1] for other in panels if other.bbox[1]>p.bbox[3]),default=float('inf'))
        native=[]
        for row in rows:
            if not p.bbox[3]<min(l.bbox[1] for l in row)<end or len(row)!=len(header):continue
            ink=sorted(row,key=lambda l:l.bbox[0])
            if not all(_NUMBER.fullmatch(canonical(l.text).strip()) for l in ink):continue
            native.append({'values':[float(canonical(l.text).strip()) for l in ink],
                           'cells':[{'text':l.text,'bbox':list(l.bbox)} for l in ink]})
        if len(native)<3 or len({r['values'][column] for r in native})!=len(native):continue
        if any(len({r['values'][i] for r in native})!=1 for i in range(last+1) if i!=column):continue
        selected=[r for r in native if r['values'][column]==float(claim[1])]
        if len(selected)!=1:continue
        selected=selected[0]
        if any(selected['values'][i]<=other['values'][i] for other in native if other is not selected for i in outcomes):continue
        contracts.append({'parameter':variable,'meaning':meaning,'selected_value':float(claim[1]),
                          'native_dataset_columns':[header[i].text for i in outcomes],
                          'source_panel':p.text,'native_rows':native})
    if len(contracts)!=1:return None
    return {'kind':'actual_controlled_parameter_panel_and_all_dataset_optimum',
            'matched_fields':[contracts[0]['parameter'],*contracts[0]['native_dataset_columns']],
            'matched_values':[],'relations':contracts}


def _stage_filter_endpoints(descriptor,text):
    """A stage-removal baseline and its retained pipeline own the metric change."""
    if _foreign_native_model(descriptor,text):return None
    if not re.search(r'过滤|filter',descriptor['title'],re.I):return None
    grid=descriptor.get('_catalogue_grid') or _grid(descriptor['cells'])
    if not grid or len(grid[0])!=2:return None
    metric=grid[0][1].text.strip()
    if not re.fullmatch(r'FPR\d+',metric,re.I) or not _present(metric,text):return None
    counts={'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'two':2,'three':3,'four':4,'five':5}
    def stage(value):
        m=re.search(r'(\d+|[一二三四五两]|two|three|four|five)[-\s]*(?:阶段|stages?)',value,re.I)
        if not m:return None
        return int(m[1]) if m[1].isdigit() else counts.get(m[1].casefold())
    rows=_relation_rows(descriptor['cells']);removed=[];retained=[]
    for row in rows:
        count=stage(row['name'])
        if not count or not re.search(r'过滤|filter',row['name'],re.I) or not row['purposes']:continue
        measured=re.fullmatch(r'\s*(\d+(?:\.\d+)?)%\s*',row['purposes'][0])
        if not measured:continue
        item={'owner':row['name'],'stage_count':count,'value':float(measured[1])}
        (removed if re.search(r'^\s*(?:无|without\b|no\b)',row['name'],re.I) else retained).append(item)
    if len(removed)!=1 or len(retained)!=1 or removed[0]['stage_count']!=retained[0]['stage_count']:return None
    operation=re.search(r'(?:\d+|[一二三四五两]|two|three|four|five)[-\s]*(?:阶段|stages?)[^。.!?]{0,20}(?:过滤|filter)',text,re.I)
    if not operation or stage(operation[0])!=retained[0]['stage_count']:return None
    change=re.search(re.escape(metric)+r'\s*(?:从|from)\s*(\d+(?:\.\d+)?)%\s*(?:降低|下降|减少|decreas\w*|reduc\w*)\s*(?:至|到|to)\s*(\d+(?:\.\d+)?)%',text,re.I)
    if not change or [float(change[1]),float(change[2])]!=[removed[0]['value'],retained[0]['value']]:return None
    if removed[0]['value']<=retained[0]['value']:return None
    return {'kind':'actual_filter_stage_removal_and_owned_metric_endpoints',
            'matched_fields':[metric,removed[0]['owner'],retained[0]['owner']],
            'matched_values':[change[1],change[2]],'relations':[{'metric':metric,'baseline':removed[0],'retained_pipeline':retained[0]}]}


def _query_capacity_outputs(descriptor,text):
    from .usage_table_evidence import _cell_rows,_NUMBER
    if _foreign_native_model(descriptor,text):return None
    if not re.search(r'查询|queries|query',descriptor['title'],re.I) or not re.search(r'查询|queries|query',text,re.I):return None
    tokens=[t for t in re.findall(r'[A-Za-z][A-Za-z0-9_-]*',descriptor['title'])
            if t.casefold() not in _SEMANTIC_TITLE_FILLER and t.casefold() not in
            {'table','performance','comparison','between','different','numbers','number','of','queries','query'} and not t.isdigit()]
    if tokens and not all(_present(t,text) for t in tokens):return None
    rows=_cell_rows(descriptor['cells']);heads=[]
    for row in rows:
        ordered=sorted(row,key=lambda l:l.bbox[0]);numeric=[l.text.strip() for l in ordered[:-1]]
        if (len(ordered)>=4 and all(v.isdigit() for v in numeric)
                and numeric==[str(i) for i in range(1,len(numeric)+1)]
                and re.search(r'平均长度|average\s+length',ordered[-1].text,re.I)):
            heads.append(ordered)
    if len(heads)!=1:return None
    head=heads[0];native=[]
    for row in rows:
        ink=sorted(row,key=lambda l:l.bbox[0])
        if min(l.bbox[1] for l in ink)<=max(l.bbox[3] for l in head):continue
        if len(ink)!=len(head)+1 or not ink[0].text.strip().isdigit():continue
        if not all(_NUMBER.fullmatch(l.text.strip()) for l in ink):continue
        native.append({'setting':int(ink[0].text),'values':[float(l.text.strip()) for l in ink[1:]],
                       'native_cells':[{'text':l.text,'bbox':list(l.bbox)} for l in ink]})
    if len(native)<3 or len({r['setting'] for r in native})!=len(native):return None
    declaration=re.search(r'([A-Za-zα-ωΑ-Ω])\s*∈\s*\{([\d\s,，]+)\}',normalize_text(text))
    if not declaration:return None
    settings=[int(v) for v in re.findall(r'\d+',declaration[2])]
    if set(settings)!={r['setting'] for r in native}:return None
    # Search all settings: the author can discuss smaller capacity first.
    bests=[m for m in re.finditer(r'(?:当|when)\s*'+re.escape(declaration[1])+r'\s*=\s*(\d+)\s*时?([^。.!?]{1,220})',normalize_text(text),re.I)
           if re.search(r'成功率|success',m[2],re.I) and re.search(r'完成长度|average\s+length|sequence\s+length',m[2],re.I)
           and re.search(r'最佳|最优|best|optimal',m[2],re.I)]
    if len(bests)!=1:return None
    selected=next((r for r in native if r['setting']==int(bests[0][1])),None)
    if not selected or any(a<=b for other in native if other is not selected for a,b in zip(selected['values'],other['values'])):return None
    return {'kind':'actual_query_capacity_settings_and_success_length_optimum',
            'matched_fields':[declaration[1],'task completed in a row',head[-1].text],
            'matched_values':[],'relations':[{'native_settings':settings,'selected_setting':selected['setting'],'native_rows':native}]}


def _threshold_variant_relations(descriptor,text):
    """All measured thresholds own both capacity ordering and stricter accuracy."""
    if _foreign_native_model(descriptor,text):return None
    if not re.search(r'角度|方向|orientation|accuracy|准确率',descriptor['title'],re.I):return None
    identities=re.findall(r'(?:在\s*|\b(?:on|from|in)\s+)([A-Z][A-Za-z0-9_-]*)\s*(?:数据集|dataset)',text)
    if any(_norm(name) not in _norm(descriptor['title']) for name in identities):return None
    grid=descriptor.get('_catalogue_grid') or _grid(descriptor['cells'])
    if not grid:return None
    header,_=grid;angles=[]
    for i,l in enumerate(header[1:]):
        m=re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*[°◦]\s*',normalize_text(l.text))
        if m:angles.append((i,float(m[1]),l.text))
    if len(angles)<3 or [a[1] for a in angles]!=sorted((a[1] for a in angles),reverse=True):return None
    rows=_relation_rows(descriptor['cells']);actual=[]
    for row in rows:
        values=[]
        for column,_,_ in angles:
            if column>=len(row['purposes']):return None
            m=re.fullmatch(r'\s*(\d+(?:\.\d+)?)%?\s*',row['purposes'][column])
            if not m:return None
            values.append(float(m[1]))
        if any(a<=b for a,b in zip(values,values[1:])):return None
        actual.append({'owner':row['name'],'threshold_values':values})
    if len(actual)!=3 or not all(_present(r['owner'],text) for r in actual):return None
    compared=re.search(r'(.{1,120}?)(?:相比|比较于|compared\s+(?:with|to))\s*([^。.!?]{1,100})',text,re.I)
    if not compared:return None
    low=[r for r in actual if _present(r['owner'],compared[2])]
    high=[r for r in actual if _present(r['owner'],compared[1])]
    if len(low)!=1 or len(high)!=2:return None
    if not re.search(r'各(?:个)?(?:角度)?阈值|all\s+(?:angle\s+)?thresholds',compared[2],re.I) or not re.search(r'提升|优于|better|improv',compared[2],re.I):return None
    if any(a<=b for row in high for a,b in zip(row['threshold_values'],low[0]['threshold_values'])):return None
    normalized=normalize_text(text).replace('◦','°')
    sweep=re.search(r'角度阈值从\s*(\d+(?:\.\d+)?)°[^。.!?]{0,30}(?:收紧|降低|减小)[^。.!?]{0,12}(\d+(?:\.\d+)?)°',normalized)
    if not sweep or [float(sweep[1]),float(sweep[2])]!=[angles[0][1],angles[-1][1]]:return None
    if not re.search(r'所有模型[^。.!?]{0,20}准确率[^。.!?]{0,15}下降',text):return None
    return {'kind':'actual_native_threshold_grid_and_variant_accuracy_orders',
            'matched_fields':[r['owner'] for r in actual]+[a[2] for a in angles],
            'matched_values':[],'relations':[{'native_thresholds':[a[1] for a in angles],
                'native_rows':actual,'lower_variant':low[0]['owner'],'higher_variants':[r['owner'] for r in high]}]}


def _replacement_metric_relations(descriptor,text):
    """Two metric rows independently rank the same native replacement inputs."""
    if _foreign_native_model(descriptor,text):return None
    if not re.search(r'替换|replacement',descriptor['title'],re.I):return None
    identities=re.findall(r'(?:在\s*|\b(?:on|from|in)\s+)([A-Z][A-Za-z0-9_-]*)\s*(?:数据集|dataset)',text)
    if any(_norm(name) not in _norm(descriptor['title']) for name in identities):return None
    grid=descriptor.get('_catalogue_grid') or _grid(descriptor['cells'])
    if not grid:return None
    header,_=grid
    meanings=[(r'目标|target',r'目标|target'),(r'图片|图像|image',r'图片|图像|image'),
              (r'布局|layout',r'布局(?:信息)?|layout'),(r'历史|history',r'历史(?:动作)?|history')]
    owners=[]
    for native,body in meanings:
        matches=[i for i,l in enumerate(header[1:]) if re.fullmatch(native,normalize_text(l.text).strip(),re.I)]
        if len(matches)!=1 or not re.search(body,text,re.I):return None
        owners.append(matches[0])
    rows=_relation_rows(descriptor['cells']);metrics=[]
    for native,body in [(r'Detection|检测(?:准确率)?',r'检测准确率|detection\s+accuracy'),
                        (r'Action|动作(?:预测)?',r'动作预测|action\s+prediction')]:
        candidates=[r for r in rows if re.fullmatch(native,r['name'],re.I)]
        if len(candidates)!=1 or not re.search(body,text,re.I):return None
        row=candidates[0];values=[]
        for i in owners:
            if i>=len(row['purposes']):return None
            value=re.fullmatch(r'\s*(\d+(?:\.\d+)?)%?\s*',row['purposes'][i])
            if not value:return None
            values.append(float(value[1]))
        if min(values[:2])<=max(values[2:]):return None
        metrics.append({'metric':row['name'],'owners':[header[i+1].text for i in owners],
                        'native_values':values})
    # Each ordered relation is expressed in its own metric context. Merely
    # listing the same input nouns or saying accuracy changes is insufficient.
    detection=re.search(r'(?:错误)?(?:图像|图片)[^。.!?]{0,35}(?:错误)?目标[^。.!?]{0,65}检测准确率[^。.!?]{0,15}较高[^。.!?]{0,25}布局[^。.!?]{0,25}历史[^。.!?]{0,30}(?:难度更大|较低)',text)
    action=re.search(r'动作预测[^。.!?]{0,30}布局[^。.!?]{0,20}历史[^。.!?]{0,45}(?:准确率|性能)[^。.!?]{0,20}(?:下降|损失)[^。.!?]{0,10}(?:幅度更大|更大)',text)
    if not detection or not action:return None
    return {'kind':'actual_replacement_inputs_and_independent_metric_orders',
            'matched_fields':[header[i+1].text for i in owners]+[m['metric'] for m in metrics],
            'matched_values':[],'relations':metrics}


def _service_catalogue_relations(descriptor,text):
    """Distinct native application-column names own distinct service purposes."""
    if not re.search(r'基准测试|工作负载|benchmarks?|workloads?',descriptor['title'],re.I):return None
    if not re.search(r'使用|采用|\b(?:use[ds]?|evaluat\w*)\b',text,re.I):return None
    if re.search(r'(?:不|未|没有)\s*(?:使用|采用)|does?\s+not\s+(?:use|evaluate)|not\s+used',text,re.I):return None
    grid=descriptor.get('_catalogue_grid') or _grid(descriptor['cells'])
    if not grid:return None
    header,_=grid
    app=next((i for i,h in enumerate(header) if re.search(r'应用|applications?|services?',h.text,re.I)),None)
    description=next((i for i,h in enumerate(header) if re.search(r'描述|description|purpose',h.text,re.I)),None)
    if app is None or description is None or app==description or app==0:return None
    # A conventional shortened suffix is derived from this caption, never
    # from a paper/model list. Competing full names still compete physically.
    title=descriptor['title']
    title=re.sub(r'\b(?:Evaluated|compute|benchmarks?|online|real-world|applications?|services?|workloads?)\b','',title,flags=re.I)
    for word in re.findall(r'(?<![A-Za-z0-9])[A-Z][A-Za-z0-9]*-[A-Za-z]{4,}(?![A-Za-z0-9])',title):
        stem,suffix=word.rsplit('-',1);short=stem+'-'+suffix[0]
        if _present(short,text):title=title.replace(word,short)
    if not _subject_agrees(title,text):return None
    rows=descriptor.get('_native_relation_rows') or _relation_rows(descriptor['cells']);named=[]
    for row in rows:
        if max(app,description)-1>=len(row['purposes']):continue
        name=normalize_text(row['purposes'][app-1]).strip();purpose=row['purposes'][description-1]
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{2,}',name):continue
        if not re.search(r'[\u4e00-\u9fff]{3}|[A-Za-z]{4}',purpose):continue
        named.append((name,purpose,row['name']))
    if len(named)<3:return None
    # Enumeration/punctuation boundaries preserve preposed purposes such as
    # "面向内存缓存的 Memcached" without borrowing another named service.
    segments=re.split(r'[，,;；。!?]|[（(]\s*\d+(?:\s*&\s*\d+)?\s*[）)]',normalize_text(text))
    matches={}
    def translated(value):return re.sub(r'(?<![A-Za-z])Web(?![A-Za-z])','网页',normalize_text(value),flags=re.I)
    for segment in segments:
        owners=[r for r in named if _present(r[0],segment)]
        if len(owners)!=1:continue
        name,purpose,abbreviation=owners[0]
        claim=re.sub(re.escape(name),'',segment,flags=re.I)
        phrases=_content_phrases(translated(purpose),translated(claim))
        a,b=_norm(translated(purpose)),_norm(translated(claim))
        phrases.extend(a[m.a:m.a+m.size] for m in SequenceMatcher(None,a,b,autojunk=False).get_matching_blocks()
                       if m.size==3 and re.fullmatch(r'[\u4e00-\u9fff]{3}',a[m.a:m.a+m.size]))
        phrases=[p for p in phrases if p not in {'系统','服务','应用','服务器','基准测试','测试应用'}]
        if phrases:matches[name]={'application':name,'abbreviation':abbreviation,'native_purpose':purpose,
                                'body_claim':segment.strip(),'purpose_phrases':sorted(set(phrases))}
    if len(matches)<3 or len({p for r in matches.values() for p in r['purpose_phrases']})<2:return None
    return {'kind':'native_application_names_and_three_owned_service_purposes',
            'matched_fields':list(matches),'matched_values':[],'relations':list(matches.values()),
            'caption_subject_view':title}


def _symbolic_lower_signatures(lines):
    """Exact native Ω expressions, retaining elevated encoded glyph geometry."""
    signatures=[]
    for line in lines:
        value=normalize_text(line.text)
        for match in re.finditer(r'Ω\s*\(',value):
            # Complete a physically inline expression from its real right
            # fragments. No adjacent equation or later prose supplies terms.
            center=(line.bbox[1]+line.bbox[3])/2;font=line.font_size or 10
            right=[l for l in lines if l is not line and l.bbox[0]>=line.bbox[2]-.5
                   and abs((l.bbox[1]+l.bbox[3])/2-center)<=font*.5]
            expression=value[match.end():]+' '.join(normalize_text(l.text) for l in sorted(right,key=lambda l:l.bbox[0]))
            depth=1;end=None
            for i,char in enumerate(expression):
                depth+=(char=='(')-(char==')')
                if depth==0:end=i;break
            if end is None:continue
            inner=re.sub(r'\s+','',expression[:end]);marker=None
            if inner.startswith('√'):
                marker='√';inner=inner[1:]
            else:
                # Some embedded math fonts expose the radical as an isolated
                # "p". Preserve that actual glyph and its elevated placement;
                # a literal baseline variable p never qualifies as a marker.
                markers=[l for l in lines if normalize_text(l.text).strip() in {'p','√'}
                         and line.bbox[2]-.5<=l.bbox[0]<=line.bbox[2]+font*.5
                         and .25*font<=line.bbox[1]-l.bbox[1]<=1.3*font]
                if len(markers)==1:marker='elevated:'+normalize_text(markers[0].text).strip()
            if not marker:continue
            if inner.startswith('(') and inner.endswith(')'):
                depth=0;whole=True
                for i,char in enumerate(inner):
                    depth+=(char=='(')-(char==')')
                    if depth==0 and i<len(inner)-1:whole=False;break
                if whole:inner=inner[1:-1]
            if (not re.fullmatch(r'[A-Za-z0-9+*/^(),.]+',inner)
                    or not re.search(r'[A-Za-z]',inner)):continue
            signatures.append({'operator':'Ω','observed_root_marker':marker,'expression':inner,
                               'printed_relation':'>=' if re.search(r'(?:≥|>=)\s*$',value[:match.start()]) else None,
                               'operator_line':{'text':line.text,'bbox':list(line.bbox)},
                               'inline_fragments':[{'text':l.text,'bbox':list(l.bbox)} for l in right]})
    return signatures


def _formal_native_lower_bound(descriptor,paragraph,page):
    text=normalize_text(paragraph.text)
    if not re.match(r'^\s*(?:定理|Theorem)\s*[0-9]+(?:\.[0-9]+)*',text,re.I):return None
    problem=re.search(r'(?:部分|完全)可观测[^，。；;]{2,30}?(?:问题|博弈)',descriptor['title'])
    if not problem or not _present(problem[0],text):return None
    grid=descriptor.get('_catalogue_grid') or _grid(descriptor['cells'])
    if not grid:return None
    header,columns=grid
    bound=next((i for i,h in enumerate(header) if re.search(r'懊悔界|regret\s*bound',h.text,re.I)),None)
    setting=next((i for i,h in enumerate(header) if re.search(r'设定|settings?',h.text,re.I)),None)
    if bound is None or setting is None or bound==0 or setting==0:return None
    anchors=sorted(columns[0],key=lambda l:(l.bbox[1]+l.bbox[3])/2);centers=[(l.bbox[1]+l.bbox[3])/2 for l in anchors]
    body_lines=[l for l in page.lines if l.source=='native' and
                paragraph.bbox[1]-.5<=l.bbox[1] and l.bbox[3]<=paragraph.bbox[3]+.5]
    body=[claim for claim in _symbolic_lower_signatures(body_lines) if claim['printed_relation']=='>=']
    if not body:return None
    matched=[]
    for i,label in enumerate(anchors):
        if not re.fullmatch(r'下界\s*[（(](?:本文|本章)[）)]|Lower\s*bound(?:\s*[（(](?:ours|this\s*work)[）)])?',normalize_text(label.text).strip(),re.I):continue
        top=(centers[i-1]+centers[i])/2 if i else max(l.bbox[3] for l in header)
        bottom=(centers[i]+centers[i+1])/2 if i+1<len(anchors) else centers[i]+(label.font_size or 10)*1.5
        formula=[l for l in columns[bound] if top<=(l.bbox[1]+l.bbox[3])/2<bottom]
        native=_symbolic_lower_signatures(formula)
        aligned=[l for l in columns[setting] if l.font_size and l.font_size>=(label.font_size or 10)*.95
                 and abs((l.bbox[1]+l.bbox[3])/2-centers[i])<=(label.font_size or 10)*.6]
        if not aligned and i:
            # A setting printed centrally between two result baselines is a
            # real merged-column label, unlike a label aligned to only its
            # preceding result or a smaller-font table footnote.
            aligned=[l for l in columns[setting] if l.font_size and l.font_size>=(label.font_size or 10)*.95
                     and abs((l.bbox[1]+l.bbox[3])/2-(centers[i-1]+centers[i])/2)<=l.font_size*.3]
        if len(aligned)!=1:continue
        setting_text=normalize_text(aligned[0].text)
        types=[rx for rx in [r'线性|(?<!\w)linear\b',r'表格(?:式|型)|\btabular\b'] if re.search(rx,setting_text,re.I)]
        if len(types)!=1 or not re.search(types[0],text,re.I):continue
        if re.search(r'线性|\blinear\b',setting_text,re.I) and re.search(r'非线性|\bnon[- ]?linear\b',text,re.I):continue
        for source in native:
            if any((source['operator'],source['observed_root_marker'],source['expression'])==
                   (claim['operator'],claim['observed_root_marker'],claim['expression']) for claim in body):
                matched.append({'native_row':label.text,'native_setting':setting_text,'native_bound':source,
                                'body_bound':next(claim for claim in body if claim['observed_root_marker']==source['observed_root_marker'] and claim['expression']==source['expression']),
                                'problem_identity':problem[0]})
    if len(matched)!=1:return None
    return {'kind':'native_formal_lower_bound_operator_expression_and_problem_setting',
            'matched_fields':[matched[0]['native_row'],matched[0]['native_setting'],problem[0]],
            'matched_values':[],'relations':matched}


def _adjacent_introduction(descriptor,paragraph,descriptors,pages):
    target=descriptor['target'];page=pages[target.line.page_number]
    if target.line.page_number==paragraph.page_number:
        if not 0<=target.line.bbox[1]-paragraph.bbox[3]<=64:return False
    elif (target.line.page_number!=paragraph.page_number+1 or
          paragraph.bbox[3]<pages[paragraph.page_number].height*.65 or target.line.bbox[1]>page.height*.22):
        return False
    a=(paragraph.page_number,paragraph.bbox[3]);b=(target.line.page_number,target.line.bbox[1])
    return not any(a<(d['target'].line.page_number,d['target'].line.bbox[1])<b for d in descriptors
                   if d is not descriptor and d['usage_epoch']==descriptor['usage_epoch'])


def _relation_negative(text):
    return bool(re.search(r'不(?:负责|使用|采用|用于|包含|集中|匹配)|并不|并未|没有使用|不会写入|另一基线|does\s+not|not\s+(?:use|match|concentrat)',text,re.I))


def _printed_name(name):
    return re.sub(r'\s*\[[0-9,， -]+\]\s*','',normalize_text(name)).strip()


def _method_core_use(descriptor,text):
    """An independently named method uses its own distinctive native mechanism."""
    grid=descriptor.get('_catalogue_grid') or _grid(descriptor['cells'])
    if not grid:return None
    headers=[normalize_text(l.text) for l in grid[0]]
    columns=[i for i,h in enumerate(headers[1:]) if re.search(r'核心思路|工作原理|机制|core\s+(?:idea|mechanism)|principle',h,re.I)]
    if not columns:return None
    if not _subject_agrees(descriptor['title'],text):return None
    rows=descriptor.get('_native_relation_rows') or _relation_rows(descriptor['cells'])
    aliases=lambda r:[_printed_name(r['name'])]
    pairs=[]
    for owner,name,claim in _body_windows(rows,text,aliases,sentence_bound=True):
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*(?:\s+[A-Za-z][A-Za-z0-9_-]*)*',name):continue
        if _relation_negative(claim) or not re.search(r'通过|利用|进行|建模|uses?|using|models?|through',claim,re.I):continue
        for column in columns:
            if column>=len(rows[owner]['purposes']):continue
            source=rows[owner]['purposes'][column]
            # A specific Chinese mechanism, rather than a common English
            # model/optimizer word, must itself be operated in the named claim.
            phrases=[p for p in _content_phrases(source,claim) if re.fullmatch(r'[\u4e00-\u9fff]{5,}',p)]
            if not phrases:continue
            entities=(r'视频|\bvideo\b',r'文本|\btext\b',r'图像|\bimages?\b',r'语音|\bspeech\b',r'点云|point\s+cloud')
            if any(re.search(rx,source,re.I) and not re.search(rx,claim,re.I) for rx in entities):continue
            topics=(r'训练|training',r'损失|loss',r'消融|ablation')
            if any(re.search(rx,source,re.I) and not re.search(rx,claim,re.I) for rx in topics):continue
            pairs.append({'owner':name,'native_mechanism':source,'body_claim':claim,'owned_mechanism_phrases':phrases})
    if pairs:return {'kind':'named_native_method_and_distinctive_operated_mechanism',
                     'matched_fields':[p['owner'] for p in pairs],'matched_values':[],'relations':pairs}
    return None


def _storage_output_flow(descriptor,text):
    """A native output buffer owns computed results flowing out of that buffer."""
    # The typed row itself supplies the architecture's operational purpose;
    # caption identities, including named datasets, still have to agree.
    grid=descriptor.get('_catalogue_grid') or _grid(descriptor['cells'])
    if not grid:return None
    headers=[l.text for l in grid[0]]
    if not re.search(r'存储|缓存|缓冲|storage|memory|buffer',' '.join(headers)+' '+descriptor['title'],re.I):return None
    if not any(re.search(r'功能|描述|function|description|purpose',h,re.I) for h in headers[1:]):return None
    subject=re.sub(r'架构|存储|memory|storage|architecture','',descriptor['title'],flags=re.I)
    if not _subject_agrees(subject,text):return None
    pairs=[]
    rows=descriptor.get('_native_relation_rows') or _relation_rows(descriptor['cells'])
    for row in rows:
        native=' '.join(row['purposes'])
        if not (re.search(r'输出|output',native,re.I) and re.search(r'结果|results?',native,re.I)):continue
        name=_printed_name(row['name']);stem=re.sub(r'\s*(?:Buffer|Cache)\s*$','',name,flags=re.I).strip()
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',stem):continue
        for sentence in re.split(r'[。；;!?]',normalize_text(text)):
            if _relation_negative(sentence):continue
            flow=re.search(r'(?:计算结果|运算结果|computed\s+results?)\s*(?:从|from)\s*'+re.escape(stem)+
                           r'(?![A-Za-z0-9_])\s*(?:Buffer|Cache)?\s*(?:写回|写出|输出至|write\s+back\s+to)\s*(?:至|到)?\s*([A-Za-z][A-Za-z0-9_/]*)',sentence,re.I)
            if not flow or flow[1].casefold()==stem.casefold():continue
            pairs.append({'owner':name,'native_output_role':native,'destination':flow[1],'body_claim':sentence.strip()})
    if len(pairs)==1:return {'kind':'native_computed_result_output_and_directed_writeback',
                            'matched_fields':[pairs[0]['owner']],'matched_values':[],'relations':pairs}
    return None


def _baseline_field_policy_use(descriptor,text):
    """Concrete measured hash fields become constants of an exact live check."""
    grid=descriptor.get('_catalogue_grid') or _grid(descriptor['cells'])
    if not grid:return None
    headers=' '.join(l.text for l in grid[0])
    if not (re.search(r'基线|baseline',headers,re.I) and re.search(r'哈希|hash|SHA[- ]?\d+',headers,re.I)):return None
    if not _subject_agrees(descriptor['title'],text):return None
    normalized=normalize_text(text)
    if _relation_negative(normalized):return None
    if not (re.search(r'实验|实测|measured|experimental',normalized,re.I)
            and re.search(r'完整哈希字符串|full\s+hash\s+strings?',normalized,re.I)
            and re.search(r'常量|constants?',normalized,re.I)
            and re.search(r'写入|write|written',normalized,re.I)
            and re.search(r'策略|policy|policies',normalized,re.I)
            and re.search(r'按位比对|bit(?:wise)?\s+compar',normalized,re.I)
            and re.search(r'完全吻合|exact(?:ly)?\s+match',normalized,re.I)):return None
    anchors=[]
    for l in descriptor['cells']:
        m=re.fullmatch(r'([A-Za-z][A-Za-z0-9_]*)\[(\d+)\]',normalize_text(l.text).strip())
        if m:anchors.append((l,m[1],int(m[2])))
    stems={stem for _,stem,_ in anchors}
    if len(stems)!=1:return None
    stem=next(iter(stems));pattern=re.escape(stem)
    declarations=list(re.finditer(pattern+r'\[(\d+)\]\s*(?:至|到|through|to)\s*'+pattern+r'\[(\d+)\]',normalized,re.I))
    if len(declarations)!=1:return None
    a,b=map(int,declarations[0].groups())
    if not 1<=b-a<=32:return None
    actual={ordinal:l for l,name,ordinal in anchors if name==stem}
    if not set(range(a,b+1))<=set(actual):return None
    # The live field is the same printed identifier. A policy for another
    # register family cannot donate an otherwise identical baseline workflow.
    live=re.search(r'实时接收到的\s*([A-Za-z][A-Za-z0-9_]*)\s*字段|live\s+([A-Za-z][A-Za-z0-9_]*)\s+fields?',normalized,re.I)
    if not live or (live[1] or live[2]).casefold()!=stem.casefold():return None
    pairs=[]
    for ordinal in range(a,b+1):
        anchor=actual[ordinal];cy=(anchor.bbox[1]+anchor.bbox[3])/2
        nearby=[l for l in descriptor['cells'] if l.bbox[0]>anchor.bbox[2]+4 and
                abs((l.bbox[1]+l.bbox[3])/2-cy)<=max(2,(anchor.font_size or 10)*.6)]
        hashes=[(l,m[0]) for l in nearby for m in re.finditer(r'(?<![A-Za-z0-9])[0-9a-f]{6,}(?:…|\.\.\.)?(?![A-Za-z0-9])',l.text,re.I)
                if re.search(r'[1-9a-f]',m[0],re.I)]
        if len(hashes)!=1:return None
        cell,value=hashes[0]
        pairs.append({'field':anchor.text,'printed_baseline_hash':value,'hash_cell':{'text':cell.text,'bbox':list(cell.bbox)},
                      'use':'The measured field is mapped to a baseline constant and compared bitwise with the live same field.'})
    return {'kind':'owned_indexed_measured_hash_baseline_and_exact_live_policy_check',
            'matched_fields':[p['field'] for p in pairs],'matched_values':[p['printed_baseline_hash'] for p in pairs],'relations':pairs}


def _range_axis(text):
    value=normalize_text(text).strip()
    m=re.fullmatch(r'(\d+)\s*[-–—至]\s*(\d+)',value)
    if m:return ('range',int(m[1]),int(m[2]))
    m=re.fullmatch(r'(\d+)\s*(?:\+|或更多|及以上|以上|or\s+more)',value,re.I)
    if m:return ('open',int(m[1]))
    if re.fullmatch(r'(?:数量)?未知|unknown',value,re.I):return ('unknown',)
    return None


def _distribution_range_use(descriptor,text):
    """Printed quantity bins and two named rows own the claimed main mass."""
    if not re.search(r'分布|distribution',descriptor['title'],re.I):return None
    if not _subject_agrees(descriptor['title'],text):return None
    # Numeric range headers contain no letters. They are still real owned
    # column ink, and must not disappear into the nearest textual header.
    from .usage_table_evidence import _cell_rows
    native_rows=_cell_rows(descriptor['cells'])
    measured=[r for r in native_rows if sum(bool(re.fullmatch(r'\d+',l.text.strip())) for l in r)>=3]
    if not measured:return None
    top=min(l.bbox[1] for r in measured for l in r)
    fields=sorted((l for l in descriptor['cells'] if l.bbox[3]<top+1 and _range_axis(l.text) is not None),key=lambda l:l.bbox[0])
    if len(fields)<3:return None
    rows=[]
    for native in measured:
        values=sorted((l for l in native if re.fullmatch(r'\d+',l.text.strip())),key=lambda l:l.bbox[0])
        if len(values)!=len(fields):continue
        left=values[0].bbox[0]
        owners=[l for l in native if l.bbox[2]<left-8 and re.search(r'[A-Za-z\u4e00-\u9fff]',l.text)]
        if len(owners)!=1:continue
        entries=[]
        for value,field in zip(values,fields):
            if abs((value.bbox[0]+value.bbox[2]-field.bbox[0]-field.bbox[2])/2)>max(15,field.bbox[2]-field.bbox[0]):break
            entries.append({'headers':[field.text],'value':value.text,'bbox':list(value.bbox)})
        if len(entries)==len(fields):rows.append({'name':owners[0].text,'entries':entries})
    if len(rows)<3:return None
    bins=[]
    for entry in rows[0]['entries']:
        axis=_range_axis(entry['headers'][-1])
        if axis is None:return None
        bins.append(axis)
    if len(bins)<3 or len(set(bins))!=len(bins):return None
    normalized=normalize_text(text)
    declaration=re.search(r'按\s*([^:：。;；]{5,100}?)\s*等区间',normalized)
    if not declaration:return None
    printed=[_range_axis(x.strip()) for x in re.split(r'[、,，]',declaration[1])]
    actual_bins=[b for b in bins if b[0]!='unknown']
    if printed!=actual_bins:return None
    names=[r['name'] for r in rows]
    for m in re.finditer(r'(?:更)?集中在\s*(\d+\s*[-–—至]\s*\d+)',normalized):
        start=max([0,*[n.end() for n in re.finditer(r'[:：,，;；。]',normalized[:m.start()])]])
        claim=normalized[start:m.end()]
        if _relation_negative(claim):continue
        mentions=[]
        for name in sorted(names,key=len,reverse=True):
            for hit in re.finditer(re.escape(name),claim):
                if not any(hit.start()<b and hit.end()>a for a,b,_ in mentions):mentions.append((hit.start(),hit.end(),name))
        mentions.sort();owners=[name for _,_,name in mentions]
        if len(set(owners))<2:continue
        axis=_range_axis(m[1]);column=bins.index(axis) if axis in bins else -1
        if column<0:continue
        pairs=[]
        from decimal import Decimal,InvalidOperation
        for name in owners:
            row=next(r for r in rows if r['name']==name)
            if len(row['entries'])!=len(bins):break
            try:values=[Decimal(e['value']) for e in row['entries']]
            except InvalidOperation:break
            if any(v<0 or v!=int(v) for v in values) or values.count(max(values))!=1 or values[column]!=max(values):break
            owned_windows=[claim[end:mentions[j+1][0] if j+1<len(mentions) else len(claim)]
                           for j,(_,end,owner) in enumerate(mentions) if owner==name]
            declared=[Decimal(m[1]) for window in owned_windows
                      for m in re.finditer(r'(\d+)\s*(?:条|个|samples?|prompts?)',window,re.I)]
            if declared and any(value!=values[column] for value in declared):break
            pairs.append({'owner':name,'quantity_bin':row['entries'][column]['headers'][-1],
                          'owned_main_count':row['entries'][column],'other_owned_counts':[e for i,e in enumerate(row['entries']) if i!=column],
                          'body_claim':claim})
        if len(pairs)!=len(owners):continue
        return {'kind':'native_quantity_axes_and_two_owned_main_distributions',
                'matched_fields':[p['owner']+' / '+p['quantity_bin'] for p in pairs],
                'matched_values':[p['owned_main_count']['value'] for p in pairs],'relations':pairs}
    return None


def _mean_std_panels(descriptor):
    """Native mean/std pairs retain their method, setting and column geometry."""
    from .usage_table_evidence import _cell_rows
    rows=_cell_rows(descriptor['cells']);header=next((sorted(r,key=lambda l:l.bbox[0]) for r in rows if len(r)>=4),None)
    if not header or not re.search(r'设置|setting|condition',header[0].text,re.I):return []
    if not re.search(r'方法|method|model',header[1].text,re.I):return []
    if not re.search(r'均值\s*[/／]\s*标准差|mean\s*[/／]\s*(?:standard\s+deviation|std)',descriptor['title'],re.I):return []
    fields=header[2:];results=[]
    pair_pattern=r'([+-]?\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)'
    for row in rows:
        values=[l for l in row if re.fullmatch(pair_pattern,normalize_text(l.text).strip())]
        if len(values)!=len(fields):continue
        left=min(l.bbox[0] for l in values)
        owners=[l for l in row if header[1].bbox[0]-5<=l.bbox[0]<left and
                re.search(r'[A-Za-z\u4e00-\u9fff]',l.text) and not re.fullmatch(r'\[[0-9,， -]+\]',l.text.strip())]
        if len(owners)!=1:continue
        owner=owners[0]
        groups=sorted((l for l in descriptor['cells'] if l.bbox[0]<header[1].bbox[0]-8
                       and l.bbox[1]>header[0].bbox[3]+1 and re.search(r'[A-Za-z\u4e00-\u9fff]',l.text)),key=lambda l:l.bbox[1])
        if len(groups)<2:continue
        cy=(owner.bbox[1]+owner.bbox[3])/2;centers=[(l.bbox[1]+l.bbox[3])/2 for l in groups]
        gi=min(range(len(groups)),key=lambda i:abs(cy-centers[i]))
        low=(centers[gi-1]+centers[gi])/2 if gi else header[0].bbox[3]
        high=(centers[gi]+centers[gi+1])/2 if gi+1<len(groups) else max(l.bbox[3] for l in descriptor['cells'])+1
        if not low<=cy<=high:continue
        entries=[]
        for cell,field in zip(sorted(values,key=lambda l:l.bbox[0]),fields):
            x=(cell.bbox[0]+cell.bbox[2])/2;fx=(field.bbox[0]+field.bbox[2])/2
            if abs(x-fx)>max(20,field.bbox[2]-field.bbox[0]):break
            match=re.fullmatch(pair_pattern,normalize_text(cell.text).strip())
            entries.append({'field':field.text,'mean':match[1],'std':match[2],'text':cell.text,'bbox':list(cell.bbox)})
        if len(entries)==len(fields):results.append({'owner':_printed_name(owner.text),'setting':groups[gi].text,'entries':entries})
    return results


def _grouped_mean_gains(descriptors,paragraphs,chapters,epochs,section):
    """Exact ordered mean differences across independently owned settings."""
    from decimal import Decimal
    from .usage_table_evidence import _explicit_table_numbers,_table_pointer_agrees
    candidates=[]
    for d in descriptors:
        records=_mean_std_panels(d)
        settings=list(dict.fromkeys(r['setting'] for r in records));names=list(dict.fromkeys(r['owner'] for r in records))
        if len(settings)<2:continue
        for body in paragraphs:
            if epochs[id(body)]!=d['usage_epoch'] or chapters.get(body.page_number)!=chapters.get(d['target'].line.page_number):continue
            if section(body)!=section(d['target'].line) or not _table_pointer_agrees(d,_explicit_table_numbers(body.text)):continue
            text=normalize_text(body.text)
            if _relation_negative(text) or not re.search(r'准确率|accuracy',text,re.I):continue
            baseline=[]
            for name in names:
                aliases=[re.sub(r'\s*[（(].*?[）)]\s*','',name).strip()]
                aliases.extend(re.findall(r'[（(]([A-Za-z][A-Za-z0-9_-]*)[）)]',name))
                if any(re.search(r'(?:与|versus|against|compared\s+(?:with|to))[^。;；]{0,15}'+re.escape(a)+r'(?![A-Za-z0-9_])',text,re.I) for a in aliases):baseline.append(name)
            if len(baseline)!=1:continue
            reference=baseline[0];plain_reference=re.sub(r'\s*[（(].*?[）)]\s*','',reference).strip()
            supports=[]
            for owner in names:
                if owner==reference:continue
                aliases=[re.sub(r'\s*[（(].*?[）)]\s*','',owner).strip()]
                aliases.extend(re.findall(r'[（(]([A-Za-z][A-Za-z0-9_-]*)[）)]',owner))
                remainder=aliases[0].replace(plain_reference,'').strip()
                if len(_norm(remainder))>=4:aliases.append(remainder)
                contexts=[p for p in paragraphs if epochs[id(p)]==d['usage_epoch'] and section(p)==section(body)
                          and p.page_number==body.page_number and abs(p.bbox[1]-body.bbox[3])<=80
                          and not _relation_negative(p.text) and not re.search(r'另一个|另一(?:模型|方法)|another\s+(?:model|method)',p.text,re.I)
                          and _table_pointer_agrees(d,_explicit_table_numbers(p.text)) and any(_present(a,p.text) for a in aliases)]
                if not contexts and not any(_present(a,text) for a in aliases):continue
                if not _subject_agrees(d['title'],text+' '+' '.join(p.text for p in contexts)):continue
                pairs=[]
                for setting in settings:
                    hit=re.search(r'(?:在\s*|\bin\s+)'+re.escape(setting)+r'(?:实验|条件)?',text,re.I)
                    if not hit:break
                    if re.search(r'另一|其他|other',text[max(0,hit.start()-8):hit.end()],re.I):break
                    following=[m.start() for s in settings if s!=setting for m in re.finditer(re.escape(s),text) if m.start()>hit.end()]
                    claim=text[hit.end():min(following) if following else len(text)]
                    claim=re.split(r'[。;；!?]',claim,maxsplit=1)[0]
                    direction=re.search(r'分别(?:提升|提高|增加)了|respectively\s+(?:improv|increas)',claim,re.I)
                    if not direction:break
                    reports=re.findall(r'(?<![A-Za-z0-9_.])([+-]?\d+(?:\.\d+)?)\s*%',claim[direction.end():])
                    source=[r for r in records if r['owner']==owner and r['setting']==setting]
                    base=[r for r in records if r['owner']==reference and r['setting']==setting]
                    if len(source)!=1 or len(base)!=1:break
                    source=source[0];base=base[0]
                    if len(reports)!=len(source['entries']) or len(reports)<2:break
                    before=claim[:direction.start()];positions=[before.find(e['field']) for e in source['entries']]
                    if min(positions)<0 or positions!=sorted(set(positions)):break
                    checked=[]
                    for reported,a,b in zip(reports,source['entries'],base['entries']):
                        if a['field']!=b['field'] or Decimal(reported)<=0 or Decimal(a['mean'])-Decimal(b['mean'])!=Decimal(reported):break
                        checked.append({'owner':owner,'baseline':reference,'setting':setting,'field':a['field'],
                                        'our_mean_cell':a,'baseline_mean_cell':b,'reported_gain':reported,'body_claim':claim})
                    if len(checked)!=len(reports):break
                    pairs.extend(checked)
                else:
                    if pairs:supports.append((owner,pairs,contexts))
            if len(supports)==1:candidates.append((d,body,*supports[0]))
    used={}
    for d,body,owner,pairs,contexts in candidates:
        if any(other['i']!=d['i'] and other_body is body for other,other_body,*_ in candidates):continue
        target=d['target']
        used.setdefault(d['i'],{'physical_key':{'number':target.number,'page':target.line.page_number,'caption_bbox':list(target.line.bbox),'scope':target.scope},
             'usage_epoch':d['usage_epoch'],'title':d['title'],'body':{'page':body.page_number,'bbox':list(body.bbox),'text':body.text},
             'body_context':[{'page':p.page_number,'bbox':list(p.bbox),'text':p.text} for p in contexts],
             'cell_evidence':[{'page':l.page_number,'bbox':list(l.bbox),'text':l.text} for l in d['cells']],
             'kind':'owned_multisetting_ordered_exact_mean_gains',
             'matched_fields':[owner+' / '+p['setting']+' / '+p['field'] for p in pairs],
             'matched_values':[v for p in pairs for v in (p['our_mean_cell']['mean'],p['baseline_mean_cell']['mean'])],
             'relations':pairs,'uniqueness_reason':'One named native method and baseline own every exact ordered mean difference across the printed settings; native standard deviations never supply gains.'})
    return used


def _main_use_rejected(text):
    """A positive main-purpose claim cannot be supplied by another owner."""
    return bool(re.search(r'并未|并不|不能|不用于|未采用|另一(?:个|篇|项|种)?(?:研究|方法|模型|数据集)|'
                          r'另一个|其他研究|另一篇论文|\b(?:does\s+not|not\s+use|another\s+(?:study|model|dataset))\b',text,re.I))


def _main_use_contexts(index,descriptor,paragraph,paragraphs,chapters,epochs,section):
    """Nearby native prose within the same manuscript and actual section."""
    from .usage_table_evidence import _explicit_table_numbers,_table_pointer_agrees
    location=(paragraph.page_number,paragraph.bbox[3]);pn=descriptor['target'].line.page_number
    values=[]
    for p in paragraphs:
        if (epochs[id(p)]!=descriptor['usage_epoch'] or p.page_number not in {paragraph.page_number-1,paragraph.page_number}
                or (p.page_number,p.bbox[3])>location or section(p)!=section(paragraph)
                or chapters.get(p.page_number)!=chapters.get(pn)
                or not _table_pointer_agrees(descriptor,_explicit_table_numbers(p.text))):continue
        # Caption/cell ink never supplies its own independent use. Inputs are
        # already body-only, but keep this boundary for direct helper callers.
        if any(l.page_number==p.page_number and min(l.bbox[2],p.bbox[2])>max(l.bbox[0],p.bbox[0])
               and min(l.bbox[3],p.bbox[3])>max(l.bbox[1],p.bbox[1]) for l in descriptor['cells']):continue
        if len(_norm(p.text))<25:continue
        values.append(p)
    return sorted(values,key=lambda p:(p.page_number,p.bbox[1]))


def _weighted_independent_stage_use(descriptor,body,contexts):
    """Native zero/positive weights own their separately routed trainable stages."""
    if not re.search(r'权重|weights?',descriptor['title'],re.I) or not re.search(r'训练|train',descriptor['title'],re.I):return None
    if _main_use_rejected(body.text):return None
    text=normalize_text(body.text)
    if not (re.search(r'梯度|gradients?',text,re.I) and re.search(r'独立优化|independent.*optimi',text,re.I)
            and re.search(r'控制权重|controll?ing.*weights?',text,re.I)):return None
    grid=_grid(descriptor['cells'])
    if not grid:return None
    heads,columns=grid
    weight=next((i for i,l in enumerate(heads) if re.search(r'权重|weights?',l.text,re.I)),None)
    mode=next((i for i,l in enumerate(heads) if re.search(r'训练|training',l.text,re.I)),None)
    if weight is None or mode is None or weight==mode:return None
    configs=[];variables=set();stages=set();stage_owners={}
    for line in columns[weight]:
        conditions=re.findall(r'[λ𝜆]\s*([A-Za-z][A-Za-z0-9_]*)\s*(>|=)\s*0',normalize_text(line.text))
        if len(conditions)!=2 or len({v.casefold() for v,_ in conditions})!=2:return None
        peers=[l for l in columns[mode] if abs((l.bbox[1]+l.bbox[3]-line.bbox[1]-line.bbox[3])/2)<5]
        if len(peers)!=1:return None
        phrase=normalize_text(peers[0].text)
        active=re.findall(r'训练\s*([A-Za-z][A-Za-z0-9_-]*)',phrase)
        if re.search(r'同时训练',phrase):
            active+=re.findall(r'和\s*([A-Za-z][A-Za-z0-9_-]*)',phrase)
        frozen=re.findall(r'冻结\s*([A-Za-z][A-Za-z0-9_-]*)',phrase)
        if not active:return None
        for stage,owner in re.findall(r'(?:训练|冻结|和)\s*([A-Za-z][A-Za-z0-9_-]*)\s+([A-Za-z][A-Za-z0-9_-]*)',phrase):
            stage_owners.setdefault(stage,set()).add(owner)
        variables.update(v.casefold() for v,_ in conditions);stages.update(active+frozen)
        configs.append(dict(conditions={v.casefold():op for v,op in conditions},active=set(active),frozen=set(frozen),
                            native_weight=line.text,native_mode=peers[0].text))
    if len(configs)!=3 or len(variables)!=2 or len(stages)!=2:return None
    if set(stage_owners)!=stages or any(len(owners)!=1 for owners in stage_owners.values()):return None
    native_owners={next(iter(owners)) for owners in stage_owners.values()}
    if len(native_owners)!=1:return None
    model_owner=next(iter(native_owners))
    if not _subject_agrees(descriptor['title'],model_owner):return None
    context=' '.join(p.text for p in contexts)
    if _main_use_rejected(context) or not _subject_agrees(descriptor['title'],context):return None
    stage_adapters={}
    for stage in stages:
        matches=set(re.findall(r'([A-Za-z][A-Za-z0-9_]*)\s*对应\s*'+re.escape(stage)+r'\s+'+re.escape(model_owner)+r'\b',context,re.I))
        if len(matches)!=1:return None
        adapter=next(iter(matches))
        route=re.search(re.escape(stage)+r'\s*损失[^。;；]{0,35}?梯度仅流经\s*([A-Za-z][A-Za-z0-9_]*)\s*的参数',text,re.I)
        if not route or route[1].casefold()!=adapter.casefold():return None
        stage_adapters[stage]=adapter
    if len({a.casefold() for a in stage_adapters.values()})!=2:return None
    variable_stages={}
    for variable in variables:
        owners=[stage for stage,adapter in stage_adapters.items() if re.search(
            re.escape(adapter)+r'\s*(?:adapter|适配器)?\s*[,，]\s*将\s*'+re.escape(variable)+r'\s*序列',context,re.I)]
        if len(owners)!=1:return None
        variable_stages[variable]=owners[0]
    if len(set(variable_stages.values()))!=2:return None
    combinations=set()
    for config in configs:
        active={variable_stages[v] for v,op in config['conditions'].items() if op=='>'}
        frozen={variable_stages[v] for v,op in config['conditions'].items() if op=='='}
        if active!=config['active'] or frozen!=config['frozen']:return None
        combinations.add(tuple(sorted(config['conditions'].items())))
    if len(combinations)!=3:return None
    return dict(kind='native_weight_conditions_and_independent_gradient_routing',matched_fields=sorted(stages),matched_values=[],
                relations=[dict(model=model_owner,weight_variable=v,stage=stage,adapter=stage_adapters[stage]) for v,stage in variable_stages.items()],
                native_training_configurations=[dict(c,active=sorted(c['active']),frozen=sorted(c['frozen'])) for c in configs])


def _annotation_cost_use(descriptor,paragraph):
    """Two native rows own the accuracy/sample-cost tradeoff in a new sentence."""
    from decimal import Decimal
    from .usage_table_evidence import _numbers
    from .usage_paragraphs import span_anchor
    from dataclasses import replace
    rows=descriptor['_numeric_matrix'] if '_numeric_matrix' in descriptor else _numeric_row_matrix(descriptor)
    if len(rows)!=2 or not re.search(r'数据集|dataset',descriptor['title'],re.I) or _main_use_rejected(paragraph.text):return None
    row_values=[]
    for row in rows:
        accuracy=[e for e in row['entries'] if re.search(r'交并比|IoU|准确率|accuracy', ' '.join(e['headers']),re.I)]
        sizes=[e for e in row['entries'] if re.search(r'数据集大小|数据集规模|dataset\s*(?:size|scale)|samples?', ' '.join(e['headers']),re.I)]
        if len(accuracy)!=1 or len(sizes)!=1:return None
        a,b=_numbers(accuracy[0]['value']),_numbers(sizes[0]['value'])
        if len(a)!=1 or len(b)!=1 or a[0][1] or b[0][1]:return None
        row_values.append((row,a[0][0],b[0][0],accuracy[0],sizes[0]))
    higher=max(row_values,key=lambda x:x[1]);lower=min(row_values,key=lambda x:x[1])
    if not (higher[1]>lower[1]>0 and higher[2]>lower[2]>0):return None
    # The preceding F1/IoU result still belongs to its own performance table.
    # Keep all explicit pointers in the original paragraph as a veto; only a
    # genuine new cost statement can supply this table's extra dimension.
    start=re.search(r'虽然\s*'+re.escape(higher[0]['name']).replace(r'\ ',r'\s*'),paragraph.text,re.I)
    if not start:return None
    native=replace(span_anchor(paragraph,start.start(),len(paragraph.text)),
                   text=paragraph.text[start.start():],text_regions=(),reference_regions=())
    claim=native.text
    identity_title=re.sub(r'\b(?:size|scale)\b','',descriptor['title'],flags=re.I)
    if _main_use_rejected(claim) or not _subject_agrees(identity_title,claim):return None
    high=re.search(r'虽然\s*'+re.escape(higher[0]['name']).replace(r'\ ',r'\s*')+r'[^。]{0,65}领先[,，]\s*但其训练需要耗费大量人力进行标注',claim,re.I)
    aliases=[re.escape(a).replace(r'\ ',r'\s*') for a in _row_aliases(lower[0])]
    small=re.search(r'(?:'+'|'.join(aliases)+r')\s*仅利用少量[^。]{0,60}样本[^。]{0,65}接近全监督的精度',claim,re.I)
    cost=re.search(r'不到\s*([0-9]+(?:\.[0-9]+)?)\s*%\s*的精度折损换取了标注成本的[^。]{0,20}降低',claim)
    if not (high and small and cost):return None
    if not ((higher[1]-lower[1])/higher[1]*100<Decimal(cost[1])):return None
    if re.search(r'数千张',claim) and not 1000<=higher[2]<10000:return None
    return native,dict(kind='owned_accuracy_and_annotation_sample_cost_tradeoff',
                       matched_fields=[higher[0]['name'],lower[0]['name'],'交并比','数据集大小'],matched_values=[],
                       relations=[dict(row=r[0]['name'],accuracy_cell=r[3],sample_count_cell=r[4]) for r in (higher,lower)],
                       body_relative_loss_upper_bound=cost[1],
                       body_span=dict(start=start.start(),end=len(paragraph.text),source_paragraph=paragraph.text))


_CODE_COMPOSITION_ALIASES={'normal':('正常代码',),'unused':('未使用代码',),'unreachable':('不可达代码',)}


def _dataset_composition_use(descriptor,body,contexts):
    """A named corpus owns both its native language axis and all code labels."""
    from .usage_table_evidence import _cell_rows
    if not re.search(r'数据集|dataset',descriptor['title'],re.I) or _main_use_rejected(body.text):return None
    subjects=list(dict.fromkeys(word for subject in _primary_subjects(descriptor['title'])
        for word in re.findall(r'[A-Za-z][A-Za-z0-9_-]*',subject)
        if word.casefold() not in _SEMANTIC_TITLE_FILLER|{'table','dataset','statistics','information'}
        and (word.isupper() or any(c.isupper() for c in word[1:]))))
    if not subjects or not all(_present(s,body.text) for s in subjects):return None
    if not re.search(r'构建|构成|整合|包含|build|compos|contain',body.text,re.I):return None
    if not re.search(r'每个样本[^。]{0,30}(?:分类标签|类别)|each\s+sample[^.]{0,50}(?:label|class)',body.text,re.I):return None
    rows=_cell_rows(descriptor['cells'])
    if not rows:return None
    headings=sorted(rows[0],key=lambda l:l.bbox[0])
    languages=[normalize_text(l.text).strip() for l in headings if re.fullmatch(r'[A-Za-z][A-Za-z+#-]+',l.text.strip()) and l.text.strip().casefold()!='total']
    if len(languages)<2:return None
    labels=[]
    for row in rows[1:]:
        label=normalize_text(min(row,key=lambda l:l.bbox[0]).text).strip().casefold()
        if label=='total':continue
        if label not in _CODE_COMPOSITION_ALIASES:return None
        labels.append(label)
    if set(labels)!=set(_CODE_COMPOSITION_ALIASES) or len(labels)!=3:return None
    if not all(any(_present(a,body.text) for a in _CODE_COMPOSITION_ALIASES[label]) for label in labels):return None
    language_supports=[]
    for p in contexts:
        if _main_use_rejected(p.text):return None
        # An explicitly named other corpus cannot donate an unowned axis.
        owners=re.findall(r'([A-Z][A-Za-z0-9_-]*)\s*(?:数据集|dataset)',p.text,re.I)
        if any(not any(_norm(owner)==_norm(s) for s in subjects) for owner in owners):return None
        if (all(_present(language,p.text) for language in languages) and re.search(r'代码',p.text)
                and re.search(r'标注|annotat',p.text,re.I)):
            language_supports.append(p)
    if len(language_supports)!=1:return None
    return dict(kind='named_dataset_native_language_and_complete_code_category_axes',
                matched_fields=[*languages,*labels],matched_values=[],
                relations=[dict(native_category=label,body_category=[a for a in _CODE_COMPOSITION_ALIASES[label] if _present(a,body.text)]) for label in labels],
                axis_body=dict(page=language_supports[0].page_number,bbox=list(language_supports[0].bbox),text=language_supports[0].text))


def _independent_primary_relations(index,descriptors,paragraphs,chapters,epochs,section):
    """Additional main uses compete across every physical table, never alarms."""
    from .usage_table_evidence import _explicit_table_numbers,_table_pointer_agrees
    candidates=[]
    for d in descriptors:
        if not (re.search(r'数据集|dataset',d['title'],re.I) or
                re.search(r'权重|weights?',d['title'],re.I) and re.search(r'训练|train',d['title'],re.I)):continue
        pn=d['target'].line.page_number
        for p in paragraphs:
            if (epochs[id(p)]!=d['usage_epoch'] or abs(p.page_number-pn)>1
                    or chapters.get(pn) is None or chapters.get(pn)!=chapters.get(p.page_number)
                    or section(p)!=section(d['target'].line)
                    or not _table_pointer_agrees(d,_explicit_table_numbers(p.text))):continue
            contexts=_main_use_contexts(index,d,p,paragraphs,chapters,epochs,section)
            if p not in contexts:continue
            # Another physical table between support and target introduces a
            # new owner even if its words happen to resemble this table.
            contexts=[q for q in contexts if not any(q is not p and
                (q.page_number,q.bbox[3])<(other['target'].line.page_number,other['target'].line.bbox[1])<(p.page_number,p.bbox[1])
                for other in descriptors if other['i']!=d['i'])]
            match=_weighted_independent_stage_use(d,p,contexts) or _dataset_composition_use(d,p,contexts)
            native=p
            if not match:
                tradeoff=_annotation_cost_use(d,p)
                if tradeoff:native,match=tradeoff;contexts=[p]
            if match:candidates.append((d,native,contexts,match))
    used={}
    for d,body,contexts,match in candidates:
        ink=(body.page_number,tuple(body.bbox),body.text)
        if any(other['i']!=d['i'] and (other_body.page_number,tuple(other_body.bbox),other_body.text)==ink
               for other,other_body,_,_ in candidates):continue
        target=d['target']
        used.setdefault(d['i'],dict(physical_key=dict(number=target.number,page=target.line.page_number,
            caption_bbox=list(target.line.bbox),scope=target.scope),usage_epoch=d['usage_epoch'],title=d['title'],
            body=dict(page=body.page_number,bbox=list(body.bbox),text=body.text),
            body_context=[dict(page=p.page_number,bbox=list(p.bbox),text=p.text) for p in contexts if p is not body],
            cell_evidence=[dict(page=l.page_number,bbox=list(l.bbox),text=l.text) for l in d['cells']],
            uniqueness_reason='Independent same-section prose owns the particular native axes and directional main relation; all physical tables compete for this exact body ink.',**match))
    return used


def _named_missingness_use(descriptor,text):
    """Named native rows own the complete observed-value deletion protocol."""
    from .usage_table_evidence import _cell_rows
    from .usage_paragraphs import span_anchor
    if not re.search(r'数据集|datasets?',descriptor['title'],re.I) or _main_use_rejected(text):return None
    identities=[m[1] for m in re.finditer(r'(?i:\b(?:on|using|within)\s+(?:the\s+)?)([A-Z][A-Za-z0-9_-]*)',descriptor['title'])]
    identity_title=re.sub(r'[A-Za-z][A-Za-z0-9_-]*',
        lambda match:'' if match[0].casefold() in {'statistical','summaries','chapter'} else match[0],
        descriptor['title'])+' '+' '.join(identities)
    if not _subject_agrees(identity_title,text):return None
    cells=descriptor['cells'];headers=[l for l in cells if re.fullmatch(r'缺失(?:比例|率)|missing(?:ness)?\s*(?:ratio|rate)',normalize_text(l.text),re.I)]
    if len(headers)!=1:return None
    header=headers[0];center=(header.bbox[0]+header.bbox[2])/2
    siblings=[l for l in cells if abs(l.bbox[1]-header.bbox[1])<max(2,(header.font_size or 10)*.3) and l is not header]
    left=max(((l.bbox[0]+l.bbox[2])/2+center)/2 for l in siblings if l.bbox[2]<header.bbox[0]) if any(l.bbox[2]<header.bbox[0] for l in siblings) else header.bbox[0]-15
    right=min(((l.bbox[0]+l.bbox[2])/2+center)/2 for l in siblings if l.bbox[0]>header.bbox[2]) if any(l.bbox[0]>header.bbox[2] for l in siblings) else header.bbox[2]+25
    rows=[]
    for row in _cell_rows(cells):
        owner=min(row,key=lambda l:l.bbox[0])
        name=normalize_text(owner.text).strip()
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{2,}',name) or owner.bbox[2]>=left:continue
        values=[];ink=[]
        for l in row:
            for m in re.finditer(r'(\d+(?:\.\d+)?)\s*%',normalize_text(l.text)):
                native=span_anchor(l,m.start(),m.end());x=(native.bbox[0]+native.bbox[2])/2
                if left<=x<=right:
                    values.append(m[1]);ink.append(dict(page=l.page_number,bbox=list(native.bbox),text=m[0]))
        if len(values)>=2 and len(values)==len(set(values)):rows.append(dict(name=name,values=values,ink=ink))
    normalized=normalize_text(text)
    protocol=re.search(r'[^。!?;；]*随机删除[^。!?;；]*观测值[^。!?;；]*构造缺失数据',normalized)
    if protocol is None:return None
    claim=protocol[0];owners=[r for r in rows if _present(r['name'],claim)]
    if len(owners)<2:return None
    rates=re.findall(r'(\d+(?:\.\d+)?)\s*%',claim)
    if len(rates)<2 or any(r['values']!=rates for r in owners):return None
    # Names present elsewhere in the paragraph cannot furnish this claim.
    named=re.search(r'(?<![A-Za-z0-9_])'+re.escape(owners[0]['name'])+r'\s*(?:和|与|、|and)\s*'+re.escape(owners[1]['name'])+r'\s*数据集',claim,re.I)
    if len(owners)!=2 or named is None:return None
    return dict(kind='named_native_dataset_observed_value_missingness_protocol',
        matched_fields=[r['name']+' / '+header.text for r in owners],matched_values=rates,
        relations=[dict(owner=r['name'],field=header.text,values=r['values'],native_ink=r['ink'],body_claim=claim) for r in owners],
        _claim_span=(protocol.start(),protocol.end()))


def _stage_runtime_use(descriptor,text):
    """A named mean and independently discussed stages own real time columns."""
    from decimal import Decimal
    from .usage_table_evidence import _cell_rows
    if (_main_use_rejected(text) or not _subject_agrees(descriptor['title'],text)
            or not re.search(r'阶段.*(?:时间|开销)|(?:stage|phase).*time',descriptor['title'],re.I)):return None
    rows=_cell_rows(descriptor['cells']);heads=[]
    for l in descriptor['cells']:
        m=re.fullmatch(r'([A-Za-z][A-Za-z0-9_-]*)\s*\(\s*s\s*\)',normalize_text(l.text),re.I)
        if m:heads.append((m[1],l))
    if len(heads)!=3 or len({name.casefold() for name,_ in heads})!=3:return None
    heads.sort(key=lambda item:item[1].bbox[0]);centers=[(l.bbox[0]+l.bbox[2])/2 for _,l in heads]
    if max(l.bbox[1] for _,l in heads)-min(l.bbox[1] for _,l in heads)>3:return None
    bounds=[centers[0]-(centers[1]-centers[0])/2]+[(a+b)/2 for a,b in zip(centers,centers[1:])]+[centers[-1]+(centers[-1]-centers[-2])/2]
    measured=[]
    for row in rows:
        if min(l.bbox[1] for l in row)<=max(l.bbox[3] for _,l in heads):continue
        labels=[l for l in row if l.bbox[2]<bounds[0] and re.search(r'[A-Za-z\u4e00-\u9fff]',l.text)]
        if len(labels)!=1:continue
        values={}
        for l in row:
            value=re.fullmatch(r'(<|≤)?\s*([+-]?\d+(?:\.\d+)?)',normalize_text(l.text))
            if value is None:continue
            x=(l.bbox[0]+l.bbox[2])/2
            for i,(name,_) in enumerate(heads):
                if bounds[i]<=x<bounds[i+1]:
                    if name in values:return None
                    values[name]=dict(value=Decimal(value[2]),upper_bound=bool(value[1]),line=l)
        if len(values)==3:measured.append((labels[0].text,values))
    means=[v for name,v in measured if re.fullmatch(r'平均值|均值|mean|average',normalize_text(name),re.I)]
    if len(measured)<2 or len(means)!=1:return None
    normalized=normalize_text(text)
    dominant=re.search(r'主要集中在预处理阶段\s*\(\s*([A-Za-z][A-Za-z0-9_-]*)\s*\)',normalized)
    encoding=re.search(r'表示编码阶段\s*\(\s*([A-Za-z][A-Za-z0-9_-]*)\s*\)[^。!?]*平均编码时间(?:约)?为\s*(\d+(?:\.\d+)?)\s*秒',normalized)
    negligible=re.search(r'预测阶段\s*\(\s*([A-Za-z][A-Za-z0-9_-]*)\s*\)\s*开销可以忽略',normalized)
    if not dominant or not encoding or not negligible:return None
    names={name.casefold():name for name,_ in heads}
    mentioned=[m[1].casefold() for m in [dominant,encoding,negligible]]
    if len(set(mentioned))!=3 or set(mentioned)!=set(names):return None
    a,b,c=[names[name] for name in mentioned];mean=means[0]
    if mean[b]['upper_bound'] or mean[b]['value']!=Decimal(encoding[2]):return None
    if any(v[a]['upper_bound'] or v[a]['value']<=v[b]['value']+v[c]['value']
           or v[b]['upper_bound'] or not v[c]['upper_bound'] or v[c]['value']>=v[b]['value'] for _,v in measured):return None
    def cell(entry):
        l=entry['line'];return dict(page=l.page_number,bbox=list(l.bbox),text=l.text)
    return dict(kind='native_mean_and_directional_three_stage_runtime_use',matched_fields=[a,b,c,'mean'],matched_values=[encoding[2]],
        relations=[dict(field=b,statistic='mean',value=encoding[2],native_ink=cell(mean[b]),body_claim=encoding[0]),
                   dict(dominant=a,negligible=c,rows=[dict(statistic=n,cells={key:cell(value) for key,value in v.items()}) for n,v in measured],
                        body_claims=[dominant[0],negligible[0]])],_claim_span=(0,negligible.end()))


def _taxonomy_activation_use(descriptor,body,contexts):
    """Initial-space native categories are used to construct and filter that space."""
    if not re.search(r'初始.*空间|initial\s+space',descriptor['title'],re.I):return None
    if _main_use_rejected(body.text):return None
    classification=[p for p in contexts if p is not body and re.search(r'模块对参数进行分类',p.text)
                    and re.search(r'据此将参数划分',p.text) and not _main_use_rejected(p.text)]
    if len(classification)!=1:return None
    native=classification[0];text=normalize_text(native.text);claim=normalize_text(body.text)
    if not _subject_agrees(descriptor['title'],text+' '+claim):return None
    tool=re.search(r'([A-Za-z][A-Za-z0-9_-]*)\s*据此将参数划分',text)
    if tool is None or not _present(tool[1],claim):return None
    introductions=[p for p in contexts if p is not native and p is not body and
                   re.search(re.escape(tool[1])+r'\s*首先[^。.!?]{0,100}(?:解析|构建)',p.text,re.I)]
    if len(introductions)!=1:return None
    fields=[]
    for l in descriptor['cells']:
        name=normalize_text(l.text).strip()
        if re.fullmatch(r'[A-Za-z][A-Za-z0-9]*\.[A-Za-z][A-Za-z0-9]*\.?',name):fields.append((name,l))
    if len(fields)<4:return None
    groups={name.split('.')[0].casefold() for name,_ in fields}
    if len(groups)<2:return None
    pairs=[]
    for name,l in fields:
        if _present(name,text):pairs.append(dict(field=name,body_field=name,cell=l));continue
        if not name.endswith('.'):continue
        prefix=name[:-1]
        if len(prefix.split('.')[-1])<4:continue
        mentions=set(re.findall(r'(?<![A-Za-z0-9_])'+re.escape(prefix)+r'[A-Za-z0-9]+(?![A-Za-z0-9_])',text,re.I))
        if len(mentions)==1:pairs.append(dict(field=name,body_field=mentions.pop(),cell=l))
    if len(pairs)<4 or len({p['field'].split('.')[0].casefold() for p in pairs})<2:return None
    # Every category explicitly declared by this construction must own a
    # native heading. Remaining matching categories cannot mask a changed
    # compiler/collector category or borrow it from another physical table.
    declared={_norm(m[1]) for m in re.finditer(r'(?<![A-Za-z0-9_.])([A-Z][A-Za-z0-9]*\.[A-Za-z][A-Za-z0-9]*)(?![A-Za-z0-9_])',text)}
    if not declared or declared!={_norm(p['body_field']) for p in pairs}:return None
    activation=re.search(r'所有\s*([A-Za-z][A-Za-z0-9]*\.[A-Za-z][A-Za-z0-9]*)\s*模块下的参数仅在\s*([-+A-Za-z0-9:]+)\s*启用时才具备调优意义',claim)
    exclusion=re.search(r'根据当前激活的触发参数,\s*自动排除所有未启用类别的关联参数',claim)
    if not activation or not exclusion:return None
    owned=[p for p in pairs if _norm(p['body_field'])==_norm(activation[1])]
    if len(owned)!=1:return None
    from .usage_table_evidence import _cell_rows
    rows=_cell_rows(descriptor['cells'])
    # Category names must actually head measured counts, not appear as prose
    # in a neighboring table or unrelated notes.
    count_rows=[r for r in rows if any(re.fullmatch(r'数量|count|number',normalize_text(l.text),re.I) for l in r)]
    if len(count_rows)!=1:return None
    for pair in pairs:
        l=pair['cell'];x=(l.bbox[0]+l.bbox[2])/2
        values=[v for v in count_rows[0] if re.fullmatch(r'\d+',v.text.strip()) and abs((v.bbox[0]+v.bbox[2])/2-x)<=max(18,(l.bbox[2]-l.bbox[0])/2)]
        if len(values)!=1:return None
        pair['count_cell']=values[0]
    evidence=[dict(field=p['field'],body_field=p['body_field'],native_ink=dict(page=p['cell'].page_number,bbox=list(p['cell'].bbox),text=p['cell'].text),
                   native_count=dict(page=p['count_cell'].page_number,bbox=list(p['count_cell'].bbox),text=p['count_cell'].text)) for p in pairs]
    return dict(kind='native_initial_space_category_construction_and_activation_filter',matched_fields=[p['field'] for p in pairs],matched_values=[],
        relations=evidence+[dict(owner=tool[1],category=owned[0]['field'],trigger=activation[2],activation_claim=activation[0],exclusion_claim=exclusion[0])],
        _contexts=[introductions[0],native])


def _additional_native_main_uses(index,descriptors,paragraphs,chapters,epochs,section):
    from .usage_table_evidence import _explicit_table_numbers,_table_pointer_agrees
    from .usage_paragraphs import span_anchor
    from dataclasses import replace
    candidates=[]
    for d in descriptors:
        pn=d['target'].line.page_number
        for p in paragraphs:
            if (epochs[id(p)]!=d['usage_epoch'] or abs(p.page_number-pn)>1 or
                    chapters.get(pn) is None or chapters.get(pn)!=chapters.get(p.page_number) or
                    not _table_pointer_agrees(d,_explicit_table_numbers(p.text))):continue
            contexts=_main_use_contexts(index,d,p,paragraphs,chapters,epochs,section)
            if p not in contexts:continue
            match=_named_missingness_use(d,p.text) or _stage_runtime_use(d,p.text) or _taxonomy_activation_use(d,p,contexts)
            if not match:continue
            match=dict(match);support=match.pop('_contexts',[]);body=p
            start,end=match.pop('_claim_span',(0,len(p.text)))
            if (start,end)!=(0,len(p.text)):
                body=replace(span_anchor(p,start,end),text=p.text[start:end])
                match['body_span']=dict(start=start,end=end,source_paragraph=p.text)
            candidates.append((d,body,support,match))
    used={}
    for d,body,contexts,match in candidates:
        ink=(body.page_number,tuple(body.bbox),body.text)
        if any(other['i']!=d['i'] and (other_body.page_number,tuple(other_body.bbox),other_body.text)==ink for other,other_body,_,_ in candidates):continue
        target=d['target']
        used.setdefault(d['i'],dict(physical_key=dict(number=target.number,page=target.line.page_number,caption_bbox=list(target.line.bbox),scope=target.scope),
            usage_epoch=d['usage_epoch'],title=d['title'],body=dict(page=body.page_number,bbox=list(body.bbox),text=body.text),
            body_context=[dict(page=q.page_number,bbox=list(q.bbox),text=q.text) for q in contexts],
            cell_evidence=[dict(page=l.page_number,bbox=list(l.bbox),text=l.text) for l in d['cells']],
            uniqueness_reason='This independent native main-use clause owns the specific fields, operations and directions; all physical tables compete before credit.',**match))
    return used


def _native_claim(text):
    # Native English line wrapping can split an ordinary word. This usage
    # view does not change the stored source text or any printed numbers.
    text=re.sub(r'(?<=[A-Za-z])-\s+(?=[a-z])','',normalize_text(text))
    return re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])','',text)


def _source_use_rejected(text):
    return _main_use_rejected(text) or bool(re.search(
        r'\b(?:another|other)\s+(?:paper|framework|network)|\bnot\s+(?:the\s+)?(?:architecture|accuracy)|'
        r'\bneither\b|并非|没有(?:采用|使用|生成)|未(?:使用|提出|构建)',text,re.I))


def _dual_storage_comparison(index,descriptor,body,contexts):
    """Both physically separate bandwidth/energy comparisons need real use."""
    from decimal import Decimal
    from .usage_table_evidence import _cell_rows,_inside
    if not (re.search(r'带宽|bandwidth',descriptor['title'],re.I)
            and re.search(r'功耗|能耗|energy|power',descriptor['title'],re.I)):return None
    page=next((p for p in index.document.pages if p.number==descriptor['target'].line.page_number),None)
    if page is None or not descriptor.get('caption_rows'):return None
    top=min(l.bbox[1] for l in descriptor['caption_rows']);bottom=max(l.bbox[3] for l in descriptor['caption_rows'])
    boxes=[b for b in page.tables if b[3]-b[1]<page.height*.7 and (0<=b[1]-bottom<=30 or 0<=top-b[3]<=30)]
    cells=[l for l in descriptor['cells'] if l.source=='native' and any(_inside(l,b) for b in boxes)]
    if not cells:return None
    panels={}
    for row in _cell_rows(cells):
        for cell in row:
            m=re.fullmatch(r'([\d.]+)\s*(TB/s|GB/s|pJ|nJ)',normalize_text(cell.text),re.I)
            if m is None:continue
            # Names and values must be siblings in the actual source row;
            # another panel or nearby graphic cannot lend its owner.
            names=[l for l in row if l.bbox[2]<=cell.bbox[0]+1 and
                   re.search(r'SRAM|缓存|总线|计算|加法|memory|cache|bus|comput|add',l.text,re.I)]
            if not names:continue
            name=max(names,key=lambda l:l.bbox[2])
            if not any(_inside(name,b) and _inside(cell,b) for b in boxes):continue
            kind='bandwidth' if '/' in m[2] else 'energy'
            scale=Decimal(1) if m[2].casefold() in {'tb/s','pj'} else (Decimal('.001') if kind=='bandwidth' else Decimal(1000))
            panels.setdefault(kind,[]).append(dict(name=name.text,value=Decimal(m[1])*scale,ink=cell,owner=name))
    if set(panels)!={'bandwidth','energy'}:return None
    relations=[]
    for kind,rows in panels.items():
        compute=[r for r in rows if re.search(r'计算|加法|comput|add',r['name'],re.I)]
        moving=[r for r in rows if re.search(r'缓存|总线|互联|cache|bus|interconnect',r['name'],re.I)]
        if len(compute)!=1 or len(moving)<2:return None
        if kind=='bandwidth' and not all(r['value']<compute[0]['value'] for r in moving):return None
        if kind=='energy' and not all(r['value']>compute[0]['value'] for r in moving):return None
        relations.append(dict(axis=kind,compute=compute[0],moving=moving))
    bandwidth=[p for p in contexts if not _source_use_rejected(p.text) and
        re.search(r'存储[^。!?]*带宽[^。!?]*(?:落后于|低于)[^。!?]*计算|memory[^.!?]*bandwidth[^.!?]*(?:lower|lags)[^.!?]*comput',_native_claim(p.text),re.I)]
    energy=[p for p in contexts if not _source_use_rejected(p.text) and
        re.search(r'(?:数据传输|数据搬移)[^。!?]*(?:比|高于)[^。!?]*(?:算术|计算|运算)[^。!?]*(?:更多|高|大).*能量|data\s+(?:transfer|movement)[^.!?]*more\s+energy[^.!?]*arithmetic',_native_claim(p.text),re.I)]
    if len(bandwidth)!=1 or len(energy)!=1 or body is not energy[0]:return None
    def ink(l):return dict(page=l.page_number,bbox=list(l.bbox),text=l.text)
    return dict(kind='native_dual_storage_bandwidth_and_movement_energy_relations',matched_fields=['bandwidth','energy'],matched_values=[],
        relations=[dict(axis=r['axis'],compute=dict(name=r['compute']['name'],value=str(r['compute']['value']),native_ink=ink(r['compute']['ink'])),
            movement=[dict(name=v['name'],value=str(v['value']),native_ink=ink(v['ink'])) for v in r['moving']]) for r in relations],_contexts=[bandwidth[0]],_cell_support=cells)


def _stage_metric_comparison(descriptor,body,contexts):
    """Independent stages, quality axes and particular native metric meanings."""
    if not re.search(r'阶段.*指标|stages?.*metrics?|metrics?.*stages?',descriptor['title'],re.I):return None
    claim=_norm(body.text)
    if _source_use_rejected(body.text) or not ('文本质量指标' in claim and '动作质量指标' in claim and '评估划分' in claim):return None
    metric_rows=[l for l in descriptor['cells'] if not re.search(r'Generation|_in_|生成阶段',normalize_text(l.text),re.I)]
    names=set()
    for l in metric_rows:
        names.update(m[0] for m in re.finditer(r'\b[A-Za-z][A-Za-z0-9_]*\b',normalize_text(l.text)) if len(m[0])>=3)
    # The introduced metrics need to occur both in the native table and in
    # independent definitions. A shared metric name alone supplies no use.
    introduced=sorted(n for n in names if _present(n,body.text))
    if len(introduced)<4:return None
    axis_headers=[(normalize_text(l.text),l.bbox[1]) for l in descriptor['cells'] if re.search(r'Generation_in_(?:Text|Motion)',normalize_text(l.text),re.I)]
    if len(axis_headers)!=2:return None
    axis_headers.sort(key=lambda x:x[1])
    def axis(line):
        prior=[name for name,y in axis_headers if y<line.bbox[1]]
        return prior[-1].rsplit('_',1)[-1].casefold() if prior else None
    definitions=[];axis_metrics={}
    for name in introduced:
        native_axes={axis(l) for l in metric_rows if _present(name,l.text)}
        if len(native_axes)!=1:return None
        native_axis=native_axes.pop();axis_metrics.setdefault(native_axis,[]).append(name)
        owners=[p for p in contexts if p is not body and _present(name,p.text)
                and re.search(r'(?<![A-Za-z0-9_])'+re.escape(name)+r'\s*[。.,]\s*该指标',_native_claim(p.text),re.I)
                and re.search(r'指标[^。.!?]*(?:评估|衡量|关注|旨在)|用于(?:评估|衡量)',_native_claim(p.text))
                and not _source_use_rejected(p.text)
                and (re.search(r'生成文本|评估文本|text',_native_claim(p.text),re.I) if native_axis=='text' else
                     re.search(r'生成的专家动作|生成的优化动作|优化动作中|generated\s+motion',_native_claim(p.text),re.I))]
        if not owners:return None
        definitions.append((name,owners[0]))
    if set(axis_metrics)!={'text','motion'} or any(len(v)<2 for v in axis_metrics.values()):return None
    stage_lines=[l for l in descriptor['cells'] if re.search(r'生成.*Generation',normalize_text(l.text),re.I)]
    stages=[]
    for l in stage_lines:
        native=re.match(r'([^（(]+)[（(]',normalize_text(l.text))
        if native:stages.append((native[1].strip(),l))
    if len(stages)<3:return None
    def stage_outputs(p):
        text=_native_claim(p.text);positions=[(text.find(name),name,l) for name,l in stages]
        if any(start<0 for start,_,_ in positions):return False
        positions.sort()
        for i,(start,name,l) in enumerate(positions):
            claim=text[start+len(name):positions[i+1][0] if i+1<len(positions) else len(text)]
            rx=r'生成(?:文本|[^，,。!?;；]{0,20}文本)' if axis(l)=='text' else r'生成(?:(?!文本|指令)[^，,。!?;；]){0,12}动作'
            if not re.search(rx,claim):return False
        return True
    stage_support=[p for p in contexts if p is not body and stage_outputs(p) and not _source_use_rejected(p.text)]
    if len(stage_support)!=1:return None
    # Native motion/text metric panels must be distinct. Their named fields
    # are also defined under the corresponding quality axis in the body.
    fields=' '.join(normalize_text(l.text) for l in descriptor['cells'])
    if not re.search(r'Generation_in_Text',fields,re.I) or not re.search(r'Generation_in_Motion',fields,re.I):return None
    return dict(kind='native_stages_quality_axes_and_defined_metrics',matched_fields=[n for n,_ in stages]+introduced,matched_values=[],
        relations=[dict(metric=n,definition=p.text) for n,p in definitions],_contexts=[stage_support[0]]+list({id(p):p for _,p in definitions}.values()))


def _scaled_count(value):
    from decimal import Decimal
    m=re.fullmatch(r'(\d+(?:\.\d+)?)\s*([KkMm万]?)',normalize_text(value).strip())
    if m is None:return None
    return Decimal(m[1])*{'':1,'k':1000,'m':1000000,'万':10000}[m[2].casefold()]


def _dataset_count_comparison(descriptor,body):
    """Owned frames/boxes and two directional same-column count ratios."""
    from decimal import Decimal,ROUND_HALF_UP
    from .usage_table_evidence import _cell_rows
    if not re.search(r'数据集.*(?:统计|对比)|statistical\s+comparison.*datasets?',descriptor['title'],re.I):return None
    text=_native_claim(body.text)
    if _source_use_rejected(text):return None
    frames=re.search(r'(\d+(?:\.\d+)?)\s*(万?)\s*帧',text)
    boxes=re.search(r'(\d+(?:\.\d+)?)\s*(万?)\s*个三维物体包围框',text)
    comparative=re.search(r'(?:相比|比较)[^。!?]*本章所提的?数据集[^。!?]*近距离[^。!?]*分别多达\s*(\d+)\s*倍和\s*(\d+)\s*倍',text)
    if not frames or not boxes or not comparative:return None
    cells=descriptor['cells'];rows=_cell_rows(cells)
    own=[r for r in rows if any(re.search(r'\(?本章\)?|\(?ours\)?',l.text,re.I) for l in r)]
    if len(own)!=1:return None
    owner=min(own[0],key=lambda l:l.bbox[0]);headers=[l for l in cells if l.bbox[3]<min(v.bbox[1] for v in own[0])-1]
    identity=re.sub(r'\(?本章\)?|\(?ours\)?','',normalize_text(owner.text),flags=re.I).strip()
    if not identity or not _present(identity,descriptor['title']):return None
    count_owners=re.findall(r'(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_-]*)\s*(?:数据集|dataset\b)',text[:comparative.start()],re.I)
    if any(_norm(name)!=_norm(identity) for name in count_owners):return None
    frame_heads=[l for l in headers if re.fullmatch(r'帧数|frames?',normalize_text(l.text),re.I)]
    total_heads=[l for l in headers if re.search(r'总和|total',l.text,re.I)]
    near_heads=[l for l in headers if re.search(r'≤\s*\d+\s*米|≤\s*\d+\s*m',normalize_text(l.text),re.I)]
    if any(len(h)!=1 for h in (frame_heads,total_heads,near_heads)):return None
    def column(row,head):
        x=(head.bbox[0]+head.bbox[2])/2
        values=[l for l in row if abs((l.bbox[0]+l.bbox[2])/2-x)<=max(10,(head.bbox[2]-head.bbox[0])/2) and _scaled_count(l.text) is not None]
        return values[0] if len(values)==1 else None
    frame=column(own[0],frame_heads[0]);total=column(own[0],total_heads[0]);near=column(own[0],near_heads[0])
    if any(l is None for l in (frame,total,near)):return None
    if _scaled_count(frame.text)!=_scaled_count(frames[1]+frames[2]) or _scaled_count(total.text)!=_scaled_count(boxes[1]+boxes[2]):return None
    baselines=[]
    for row in rows:
        if row is own[0] or len(row)<3:continue
        name=min(row,key=lambda l:l.bbox[0]);alias=re.sub(r'\[[\d, -]+\]','',normalize_text(name.text)).strip()
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9 ]*',alias):continue
        match=re.search(r'(?<![A-Za-z0-9_])'+re.escape(alias)+r'(?![A-Za-z0-9_])',comparative[0],re.I)
        value=column(row,near_heads[0])
        if match and value is not None and _scaled_count(value.text)>0:baselines.append((match.start(),alias,value))
    if len(baselines)!=2:return None
    baselines.sort();ratios=[]
    for (_,name,cell),printed in zip(baselines,comparative.groups()):
        ratio=_scaled_count(near.text)/_scaled_count(cell.text)
        # Printed integer precision is respected, including its trailing
        # significant zero; arbitrary relative tolerances are never used.
        quantum=Decimal(1).scaleb(len(printed)-len(printed.rstrip('0')))
        if ratio<=1 or ratio.quantize(quantum,rounding=ROUND_HALF_UP)!=Decimal(printed):return None
        ratios.append(dict(baseline=name,own_value=near.text,baseline_value=cell.text,reported_ratio=printed,printed_quantum=str(quantum),actual_ratio=str(ratio)))
    return dict(kind='owned_native_dataset_counts_and_ordered_near_range_comparisons',matched_fields=[owner.text,'frames','3D boxes total','near-range 3D boxes'],
                matched_values=[frame.text,total.text,near.text],relations=ratios)


def _named_dataset_accuracy(descriptor,body):
    """A named row owns the dataset, metric and exact reported result."""
    from decimal import Decimal
    grid=_grid(descriptor['cells'])
    if not grid or _source_use_rejected(body.text):return None
    heads,_=grid;rows=_relation_rows(descriptor['cells']);text=_native_claim(body.text)
    if len(heads)<3 or not re.search(r'framework|模型|方法',heads[0].text,re.I):return None
    aliases=[]
    for row in rows:
        name=re.sub(r'\[[\d, -]+\]','',normalize_text(row['name'])).strip()
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9 ]*',name):continue
        rx=r'(?<![A-Za-z0-9_])'+r'\s*'.join(map(re.escape,re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+',name)))+r'(?![A-Za-z0-9_])'
        for match in re.finditer(rx,text,re.I):aliases.append((match.start(),match.end(),row,name))
    # A full source row name owns its span. A shorter native name inside
    # that same span cannot borrow the longer model's reported result.
    owned=[]
    for alias in sorted(aliases,key=lambda a:(-(a[1]-a[0]),a[0])):
        if not any(alias[0]<other[1] and other[0]<alias[1] for other in owned):owned.append(alias)
    aliases=owned
    matches=[]
    for start,end,row,name in sorted(aliases,key=lambda a:a[0]):
        stop=min([a for a,b,_,_ in aliases if a>=end]+[len(text)])
        claim=text[start:stop]
        if not re.search(r'\b(?:achieve|achieving|obtains?|reports?|yields?)\b',claim,re.I):continue
        for head,value in zip(heads[1:],row['purposes']):
            accuracy=re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*%\s*',value)
            dataset=normalize_text(head.text).strip()
            if not accuracy or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*',dataset):continue
            reported=re.search(r'(\d+(?:\.\d+)?)\s*%\s*accuracy\s+on\s+'+re.escape(dataset)+r'\b',claim,re.I)
            if reported and Decimal(reported[1])==Decimal(accuracy[1]):
                reporters=list(re.finditer(r'\b([A-Z][A-Za-z0-9_-]*(?:\s+[A-Z][A-Za-z0-9_-]*)*)\s+'
                    r'(?:(?:can|could|will|would|may)\s+)?(?:achieves?|achieving|obtains?|reports?|yields?)\b',claim[:reported.start()]))
                reporter=reporters[-1][1] if reporters else None
                if reporter and reporter.casefold() not in {'it','this','they','we'} and _norm(reporter)!=_norm(name):continue
                matches.append(dict(owner=name,dataset=dataset,metric='accuracy',value=accuracy[1],body_claim=claim,
                                    explicit_reporter=reporter))
    return dict(kind='named_native_model_dataset_exact_accuracy_use',matched_fields=[p['owner']+' / '+p['dataset']+' / accuracy' for p in matches],
                matched_values=[p['value'] for p in matches],relations=matches) if matches else None


def _ordered_network_layers(descriptor,body):
    """A layer table is used by the network's independently ordered design."""
    if not re.search(r'layers?.*(?:network|model)|网络.*层',descriptor['title'],re.I):return None
    text=_native_claim(body.text)
    if _source_use_rejected(text):return None
    architecture=re.search(r'\barchitecture\s+consists\s+of\s+([^.!?]+)',text,re.I)
    if architecture is None:return None
    rows=_relation_rows(descriptor['cells']);sequence=[];inks=[];pool_types=[]
    types={'flatten':'flatten','dense':'dense','activation':'activation','relu':'activation',
           'softmax':'softmax','conv1d':'convolution','conv2d':'convolution','conv3d':'convolution',
           'batchnormalization':'normalization','averagepooling1d':'pooling','averagepooling2d':'pooling','averagepooling3d':'pooling'}
    for row in rows:
        native=re.fullmatch(r'[^()]+\(([^()]+)\)',normalize_text(row['name']).strip())
        if native is None or _norm(native[1]) not in types:return None
        sequence.append(types[_norm(native[1])]);inks.append(row['anchor'])
        if types[_norm(native[1])]=='pooling':pool_types.append('average' if _norm(native[1]).startswith('average') else 'max')
    if len(sequence)<5 or sequence[0] not in {'flatten','convolution'} or sequence[-1]!='softmax':return None
    claim=architecture[1]
    pair=re.search(r'\btwo\s+dense\s+layers\s+separated\s+by\s+an?\s+activation\s+function',claim,re.I)
    if pair:
        if not re.search(r'\bflatten\s+layer\s+at\s+the\s+input',claim,re.I) or not re.search(r'\bsoftmax\s+layer\s+at\s+the\s+output',claim,re.I):return None
        claimed=['flatten','dense','activation','dense','softmax']
    else:
        terms=r'convolutional\s+layer|activation\s+function|batch\s+normalization\s+layer|flatten\s+layer|dense\s+layer|softmax\s+layer|(?:max|average)\s+pooling\s+layer'
        claimed=[{'convolutional layer':'convolution','activation function':'activation','batch normalization layer':'normalization',
                  'flatten layer':'flatten','dense layer':'dense','softmax layer':'softmax','max pooling layer':'pooling','average pooling layer':'pooling'}[re.sub(r'\s+',' ',m[0]).casefold()] for m in re.finditer(terms,claim,re.I)]
        if not re.search(r'followed\s+by|finally|for\s+the\s+output',claim,re.I):return None
    # Pooling is an auxiliary cell when the independent design omits it;
    # convolution/normalization/activation ordering always remains exact.
    declared_pooling=[m[1].casefold() for m in re.finditer(r'\b(max|average)\s+pooling\s+layer',claim,re.I)]
    if declared_pooling and declared_pooling!=pool_types:return None
    primary=list(sequence) if declared_pooling else [name for name in sequence if name!='pooling']
    if claimed!=primary:return None
    return dict(kind='native_network_layer_primary_order_and_input_output_use',matched_fields=sequence,matched_values=[],
        relations=[dict(native_sequence=sequence,claimed_primary_sequence=claimed,body_claim=architecture[0],
                        native_ink=[dict(page=l.page_number,bbox=list(l.bbox),text=l.text) for l in inks])])


def _complete_native_main_uses(index,descriptors,paragraphs,chapters,epochs,section):
    from .usage_table_evidence import _explicit_table_numbers,_table_pointer_agrees
    candidates=[]
    for d in descriptors:
        pn=d['target'].line.page_number
        contexts=[p for p in paragraphs if epochs[id(p)]==d['usage_epoch'] and abs(p.page_number-pn)<=2
                  and chapters.get(pn) is not None and chapters.get(pn)==chapters.get(p.page_number)
                  and _table_pointer_agrees(d,_explicit_table_numbers(p.text))
                  and not any(l.page_number==p.page_number and min(l.bbox[2],p.bbox[2])>max(l.bbox[0],p.bbox[0])
                              and min(l.bbox[3],p.bbox[3])>max(l.bbox[1],p.bbox[1]) for l in (*d['cells'],*d.get('caption_rows',[])))]
        for p in contexts:
            if _source_use_rejected(p.text):continue
            match=(_dual_storage_comparison(index,d,p,contexts) or _stage_metric_comparison(d,p,contexts)
                   or _dataset_count_comparison(d,p) or _named_dataset_accuracy(d,p))
            if not match and section(p)==section(d['target'].line):match=_ordered_network_layers(d,p)
            if match:
                match=dict(match);support=match.pop('_contexts',[]);cells=match.pop('_cell_support',d['cells']);candidates.append((d,p,support,match,cells))
    used={}
    for d,body,contexts,match,cells in candidates:
        ink=(body.page_number,body.bbox,body.text)
        if any(other['i']!=d['i'] and (p.page_number,p.bbox,p.text)==ink for other,p,_,_,_ in candidates):continue
        target=d['target'];used.setdefault(d['i'],dict(physical_key=dict(number=target.number,page=target.line.page_number,caption_bbox=list(target.line.bbox),scope=target.scope),
            usage_epoch=d['usage_epoch'],title=d['title'],body=dict(page=body.page_number,bbox=list(body.bbox),text=body.text),
            body_context=[dict(page=p.page_number,bbox=list(p.bbox),text=p.text) for p in contexts],
            cell_evidence=[dict(page=l.page_number,bbox=list(l.bbox),text=l.text) for l in cells],
            uniqueness_reason='Independent original prose owns the particular native count, directional comparison, stage metrics or ordered layer design; every physical descriptor competes for the same ink.',**match))
    return used


def semantic_table_evidence(index,descriptors,paragraphs,chapters,paragraph_epochs):
    from .usage_table_evidence import _explicit_table_numbers, _table_pointer_agrees
    from .usage_paragraphs import span_anchor
    from dataclasses import replace
    # Preserve a prior independent experiment only when native prose opens a
    # genuinely new experimental purpose before its later printed pointer.
    # A trailing pointer attached to the result itself still owns that result.
    windows=[];epochs=dict(paragraph_epochs)
    for p in paragraphs:
        windows.append(p)
        if not _explicit_table_numbers(p.text):continue
        for transition in re.finditer(r'(?<=[。.!?])\s*(?:在真实(?:应用|使用)场景中|(?:为|为了)评估|(?:为|为了)验证|To\s+(?:evaluate|assess|verify)\b)',p.text,re.I):
            before=p.text[:transition.start()];after=p.text[transition.start():]
            if not _explicit_table_numbers(after) or not before.strip():continue
            # The transition must occur before the first pointer of its new
            # purpose; earlier foreign pointers remain part of the old claim.
            native=span_anchor(p,0,transition.start())
            prefix=replace(native,text=before)
            windows.append(prefix);epochs[id(prefix)]=paragraph_epochs[id(p)]
            break
    paragraphs=windows;paragraph_epochs=epochs
    pages={p.number:p for p in index.document.pages};used={};feature_supports={};interface_supports={}
    interface_headings=sorted((l.page_number,l.bbox[1]) for l in index.document.lines
        if l.bold and (l.font_size or 0)>=11 and re.match(r'^\s*\d+(?:\.\d+)+\s*(?:[^\d.].*)?$',normalize_text(l.text)))
    def interface_section(paragraph):
        location=(paragraph.page_number,paragraph.bbox[1])
        return next((heading for heading in reversed(interface_headings) if heading<location),None)
    formal_contexts={};formal_windows=[]
    for ordinal,p in enumerate(paragraphs):
        if not re.match(r'^\s*(?:定理|Theorem)\s*[0-9]+(?:\.[0-9]+)*',normalize_text(p.text),re.I):continue
        if re.search(r'[。.!?]\s*$',p.text):continue
        parts=[p];bottom=p.bbox[3]
        for following in paragraphs[ordinal+1:]:
            if (following.page_number!=p.page_number or paragraph_epochs[id(following)]!=paragraph_epochs[id(p)]
                    or following.bbox[1]-bottom>16 or following.bbox[1]-p.bbox[1]>100):break
            if re.match(r'^\s*(?:定理|引理|Theorem|Lemma)\s*[0-9]',following.text,re.I):break
            if any(l.bold and l.text.strip() and bottom+.5<l.bbox[1]<following.bbox[1]-.5 for l in pages[p.page_number].lines):break
            parts.append(following);bottom=max(bottom,following.bbox[3])
            if re.search(r'[。.!?]\s*$',following.text):break
        if len(parts)<2:continue
        # Isolated elevated symbols remain source fragments, while their
        # placement cannot interrupt a split Chinese problem declaration.
        prose=' '.join(x.text for x in parts if normalize_text(x.text).strip() not in {'p','√'})
        if 'Ω' not in normalize_text(prose):continue
        box=(min(x.bbox[0] for x in parts),min(x.bbox[1] for x in parts),max(x.bbox[2] for x in parts),max(x.bbox[3] for x in parts))
        joined=replace(p,text=prose,bbox=box,text_regions=(),reference_regions=())
        formal_windows.append(joined);formal_contexts[id(joined)]=parts;paragraph_epochs[id(joined)]=paragraph_epochs[id(p)]
    paragraphs=[*paragraphs,*formal_windows]
    # Derived native geometry is invocation-local. Do not recalculate the
    # same physical matrix for every prose paragraph or attach decisions to
    # the original index/document/cells.
    descriptors=[dict(d,_catalogue_grid=_grid(d['cells']),
                      _native_relation_rows=_relation_rows(d['cells']),
                      _numeric_matrix=_numeric_row_matrix(d),
                      _axis_matrix=_axis_numeric_matrix(d)) for d in descriptors]
    for descriptor in descriptors:descriptor['_interface_rows']=_interface_contract_rows(descriptor)
    signatures={}
    for d in descriptors:
        signature=(d['usage_epoch'],_norm(' '.join(_primary_subjects(d['title']))),tuple(sorted(_norm(l.text) for l in d['cells'])))
        signatures.setdefault(signature,[]).append(d['i'])
    ambiguous={i for values in signatures.values() if len(values)>1 for i in values}
    for paragraph_ordinal,paragraph in enumerate(paragraphs):
        epoch=paragraph_epochs[id(paragraph)]
        paragraph_numbers=_explicit_table_numbers(paragraph.text)
        native_context=[]
        if paragraph_ordinal:
            previous=paragraphs[paragraph_ordinal-1]
            if (previous.page_number==paragraph.page_number and paragraph_epochs[id(previous)]==epoch
                    and 0<=paragraph.bbox[1]-previous.bbox[3]<=28
                    and not _explicit_table_numbers(previous.text)
                    and not any(l.bold and l.text.strip() and previous.bbox[3]-1<=l.bbox[1]<paragraph.bbox[1]
                                for l in pages[paragraph.page_number].lines)
                    and not any(label.line.page_number==paragraph.page_number and
                                previous.bbox[3]-1<=label.line.bbox[1]<paragraph.bbox[1]
                                for label in [*index.tables,*index.figures])):
                native_context=[previous]
        profile_context=[]
        if re.match(r'^\s*[•●\-]\s*',paragraph.text):
            current=paragraph
            for previous in reversed(paragraphs[:paragraph_ordinal]):
                if (previous.page_number!=paragraph.page_number or
                        paragraph_epochs[id(previous)]!=epoch or
                        not 0<=current.bbox[1]-previous.bbox[3]<=28):break
                if any(l.bold and l.text.strip() and previous.bbox[3]-1<=l.bbox[1]<current.bbox[1]
                       for l in pages[paragraph.page_number].lines):
                    profile_context=[];break
                if any(label.line.page_number==paragraph.page_number and
                       previous.bbox[3]-1<=label.line.bbox[1]<current.bbox[1]
                       for label in [*index.tables,*index.figures]):
                    profile_context=[];break
                profile_context.insert(0,previous)
                if re.search(r'模型变体|variants?',previous.text,re.I) and re.search(r'[:：]\s*$',previous.text):break
                if not re.match(r'^\s*[•●\-]\s*',previous.text):
                    profile_context=[];break
                current=previous
            else:profile_context=[]
        matches=[]
        for descriptor in descriptors:
            pn=descriptor['target'].line.page_number
            if descriptor['usage_epoch']!=epoch or descriptor['i'] in ambiguous or (abs(pn-paragraph.page_number)>1 and
                 not (chapters.get(pn) is not None and chapters.get(pn)==chapters.get(paragraph.page_number))):
                continue
            if not _table_pointer_agrees(descriptor,paragraph_numbers):
                continue
            # Actual row relations do not transfer between caption subjects
            # such as different named data sets or software implementations.
            match=None;contexts=[]
            if id(paragraph) not in formal_contexts:
                purpose_pairs=_acquisition_interface_pairs(descriptor,paragraph.text)
                if purpose_pairs:
                    interface_supports.setdefault((descriptor['i'],interface_section(paragraph)),[]).append((paragraph,purpose_pairs))
                match=_algorithm_interface_use(descriptor,paragraph.text)
            if id(paragraph) in formal_contexts:
                if _subject_agrees(descriptor['title'],paragraph.text):
                    match=_formal_native_lower_bound(descriptor,paragraph,pages[paragraph.page_number])
                    if match:contexts=formal_contexts[id(paragraph)]
            elif _subject_agrees(descriptor['title'],paragraph.text):
                features=_feature_purpose_relations(descriptor,paragraph.text)
                if features:feature_supports.setdefault(descriptor['i'],[]).append((paragraph,features))
                definitions=_native_symbol_definitions(descriptor,paragraph.text)
                if definitions:feature_supports.setdefault(descriptor['i'],[]).append((paragraph,definitions))
                match=match or (_interfaces(descriptor,paragraph.text) or _schema(descriptor,paragraph.text)
                       or _materials(descriptor,paragraph.text) or _configuration(descriptor,paragraph.text)
                       or _configuration_row_relations(descriptor,paragraph.text)
                       or _configuration_descriptive_relations(descriptor,paragraph.text)
                       or _hardware_configuration(descriptor,paragraph.text)
                       or _typed_configuration_parameters(descriptor,paragraph.text)
                       or _step_token_contract(descriptor,paragraph.text)
                       or _native_training_panels(descriptor,paragraph.text)
                       or _comparison_attributes(descriptor,paragraph.text) or _architecture_profile(descriptor,paragraph.text)
                       or _component_metrics(descriptor,paragraph.text) or _catalogue_properties(descriptor,paragraph.text)
                       or _owned_numeric_values(descriptor,paragraph.text) or _named_metric_change(descriptor,paragraph.text)
                       or _axis_numeric_values(descriptor,paragraph.text)
                       or _ordered_column_pairs(descriptor,paragraph.text)
                       or _relative_delta_values(descriptor,paragraph.text)
                       or _qualitative_metric_contrasts(descriptor,paragraph.text)
                       or _named_dataset_properties(descriptor,paragraph.text)
                       or _native_variant_rank_results(descriptor,paragraph.text)
                       or _native_feature_statistics(descriptor,paragraph.text)
                       or _native_formula_properties(descriptor,paragraph.text)
                       or _native_ablation_endpoints(descriptor,paragraph.text)
                       or _native_parameter_trends(descriptor,paragraph.text)
                       or _replacement_metric_relations(descriptor,paragraph.text)
                       or _threshold_variant_relations(descriptor,paragraph.text)
                       or _query_capacity_outputs(descriptor,paragraph.text)
                       or _stage_filter_endpoints(descriptor,paragraph.text)
                       or _parameter_panel_optimum(descriptor,paragraph.text)
                       or _quality_panel_winner(descriptor,paragraph.text)
                       or _formal_native_lower_bound(descriptor,paragraph,pages[paragraph.page_number])
                       or _service_catalogue_relations(descriptor,paragraph.text)
                       or _parallel_prompt_contract(descriptor,paragraph.text) or _ontology_role_relations(descriptor,paragraph.text))
            if not match and id(paragraph) not in formal_contexts and not _subject_agrees(descriptor['title'],paragraph.text):
                match=_service_catalogue_relations(descriptor,paragraph.text)
                match=(_native_parameter_trends(descriptor,paragraph.text)
                       or _replacement_metric_relations(descriptor,paragraph.text)
                       or _threshold_variant_relations(descriptor,paragraph.text)) if not match else match
                match=match or _parameter_panel_optimum(descriptor,paragraph.text)
                match=match or _quality_panel_winner(descriptor,paragraph.text)
                features=_native_feature_statistics(descriptor,paragraph.text)
                # A nearby dataset introduction may qualify a following
                # independent feature definition. Only the definition supplies
                # statistical use; the introductory name supplies identity.
                foreign_dataset=any(_norm(m[1]) not in _norm(' '.join(_primary_subjects(descriptor['title'])))
                    for m in re.finditer(r'(?:在\s*|\b(?:on|from|in)\s+)([A-Z][A-Za-z0-9_-]*)\s*(?:数据集|dataset)',paragraph.text))
                if (features and not foreign_dataset and paragraph.page_number==pn
                        and paragraph.bbox[1]>descriptor['target'].line.bbox[3]):
                    before=(pn,descriptor['target'].line.bbox[1])
                    eligible=[p for p in paragraphs if paragraph_epochs[id(p)]==epoch
                        and ((p.page_number==pn and p.bbox[3]<before[1]) or
                             (p.page_number==pn-1 and p.bbox[3]>=pages[p.page_number].height*.75
                              and before[1]<=pages[pn].height*.33))
                        and not _explicit_table_numbers(p.text) and _subject_agrees(descriptor['title'],p.text)]
                    for intro in reversed(eligible):
                        after=(intro.page_number,intro.bbox[3])
                        if any(after<(label.line.page_number,label.line.bbox[1])<before
                               for label in [*index.tables,*index.figures]):continue
                        match=features;contexts=[intro];break
            if not match and id(paragraph) not in formal_contexts and paragraph_ordinal:
                previous=paragraphs[paragraph_ordinal-1]
                if (previous.page_number+1==paragraph.page_number and paragraph_epochs[id(previous)]==epoch
                        and previous.bbox[3]>=pages[previous.page_number].height*.75
                        and paragraph.bbox[1]<=pages[paragraph.page_number].height*.22
                        and chapters.get(previous.page_number)==chapters.get(paragraph.page_number)
                        and not re.search(r'[。.!?；;:]\s*$',previous.text)
                        and not any(l.bold and l.font_size and l.font_size>=11 and l.text.strip()
                                    and l.bbox[1]<paragraph.bbox[1] and not re.match(r'^\s*(?:第\s*\d+\s*章|Chapter\s*\d+)',l.text,re.I)
                                    for l in pages[paragraph.page_number].lines)):
                    text=previous.text+' '+paragraph.text
                    if _table_pointer_agrees(descriptor,_explicit_table_numbers(text)):
                        match=_service_catalogue_relations(descriptor,text)
                        if match:contexts=[previous]
            if not match and id(paragraph) not in formal_contexts and profile_context:
                profile_text=' '.join(p.text for p in [*profile_context,paragraph])
                if (_table_pointer_agrees(descriptor,_explicit_table_numbers(profile_text))
                        and _subject_agrees(descriptor['title'],profile_text)):
                    match=_architecture_profile(descriptor,profile_text)
                    if match:contexts=profile_context
            if not match and id(paragraph) not in formal_contexts and native_context:
                native_text=' '.join(p.text for p in [*native_context,paragraph])
                if _table_pointer_agrees(descriptor,_explicit_table_numbers(native_text)) and _subject_agrees(descriptor['title'],native_text):
                    match=_axis_numeric_values(descriptor,native_text)
                    if match:contexts=native_context
            if not match and id(paragraph) not in formal_contexts:
                match=(_method_core_use(descriptor,paragraph.text) or _storage_output_flow(descriptor,paragraph.text)
                       or _baseline_field_policy_use(descriptor,paragraph.text) or _distribution_range_use(descriptor,paragraph.text))
            if match and (not match.get('requires_adjacent_introduction') or
                          _adjacent_introduction(descriptor,paragraph,descriptors,pages)):
                matches.append((descriptor,match,contexts))
        if len(matches)!=1:continue
        descriptor,match,contexts=matches[0];target=descriptor['target']
        used.setdefault(descriptor['i'],{
            'physical_key':{'number':target.number,'page':target.line.page_number,'caption_bbox':list(target.line.bbox),'scope':target.scope},
            'usage_epoch':epoch,
            'title':descriptor['title'],'body':{'page':paragraph.page_number,'bbox':list(paragraph.bbox),'text':paragraph.text},
            'body_context':[{'page':p.page_number,'bbox':list(p.bbox),'text':p.text} for p in contexts],
            'cell_evidence':[{'page':l.page_number,'bbox':list(l.bbox),'text':l.text} for l in descriptor['cells']],
            'uniqueness_reason':'One physical table has these actual row/field relations in independent prose; identical physical definitions remain ambiguous.',
            **match})
    interface_candidates={key:items for key,items in interface_supports.items()
        if len({pair['field'] for _,pairs in items for pair in pairs})>=2
        and len({pair['role'] for _,pairs in items for pair in pairs})>=2}
    interface_keys={key:{(id(p),pair['role']) for p,pairs in items for pair in pairs}
                    for key,items in interface_candidates.items()}
    for (ordinal,section),items in interface_candidates.items():
        owned=interface_keys[(ordinal,section)]
        if any(len(owned&other)>=2 for (other_ordinal,_),other in interface_keys.items() if other_ordinal!=ordinal):continue
        descriptor=next(d for d in descriptors if d['i']==ordinal);target=descriptor['target']
        paragraph=items[0][0];pairs={pair['field']:pair for _,relations in items for pair in relations}
        used.setdefault(ordinal,{
            'physical_key':{'number':target.number,'page':target.line.page_number,'caption_bbox':list(target.line.bbox),'scope':target.scope},
            'usage_epoch':descriptor['usage_epoch'],'title':descriptor['title'],
            'body':{'page':paragraph.page_number,'bbox':list(paragraph.bbox),'text':paragraph.text},
            'body_context':[{'page':p.page_number,'bbox':list(p.bbox),'text':p.text} for p,_ in items[1:]],
            'cell_evidence':[{'page':l.page_number,'bbox':list(l.bbox),'text':l.text} for l in descriptor['cells']],
            'kind':'typed_interface_operations_and_distinct_acquired_entities',
            'matched_fields':list(pairs),'matched_values':[], 'relations':list(pairs.values()),
            'uniqueness_reason':'At least two native interface rows have different typed operations and their particular entities used in independent prose within one section; competing physical contracts cannot share those role supports.'})
    candidates={i:items for i,items in feature_supports.items()
                if len({_norm(pair['field']) for _,pairs in items for pair in pairs})>=2}
    support_keys={i:{(id(p),_norm(pair['field'])) for p,pairs in items for pair in pairs}
                  for i,items in candidates.items()}
    for ordinal,items in candidates.items():
        if any(len(support_keys[ordinal]&other)>=2 for i,other in support_keys.items() if i!=ordinal):continue
        descriptor=next(d for d in descriptors if d['i']==ordinal);target=descriptor['target']
        paragraph=items[0][0];pairs={_norm(pair['field']):pair for _,relations in items for pair in relations}
        definitions=all('actual_meaning' in pair for pair in pairs.values())
        used.setdefault(ordinal,{
            'physical_key':{'number':target.number,'page':target.line.page_number,'caption_bbox':list(target.line.bbox),'scope':target.scope},
            'usage_epoch':descriptor['usage_epoch'],'title':descriptor['title'],
            'body':{'page':paragraph.page_number,'bbox':list(paragraph.bbox),'text':paragraph.text},
            'body_context':[{'page':p.page_number,'bbox':list(p.bbox),'text':p.text} for p,_ in items[1:]],
            'cell_evidence':[{'page':l.page_number,'bbox':list(l.bbox),'text':l.text} for l in descriptor['cells']],
            'kind':('actual_native_symbols_and_independent_definition_relations' if definitions else
                    'actual_schema_attributes_and_independent_functional_purposes'),
            'matched_fields':[p['field'] for p in pairs.values()],'matched_values':[],
            'relations':list(pairs.values()),
            'uniqueness_reason':'At least two distinct native schema attributes own functional body prose in the same manuscript; another table cannot own the same support pairs.'})
    for ordinal,evidence in _endpoint_main_use(index,descriptors,paragraphs,chapters,paragraph_epochs,interface_section).items():
        used.setdefault(ordinal,evidence)
    for ordinal,evidence in _experiment_mean_gains(descriptors,paragraphs,chapters,paragraph_epochs,interface_section).items():
        used.setdefault(ordinal,evidence)
    for ordinal,evidence in _chronological_partition_uses(descriptors,paragraphs,chapters,paragraph_epochs).items():
        used.setdefault(ordinal,evidence)
    for ordinal,evidence in _grouped_mean_gains(descriptors,paragraphs,chapters,paragraph_epochs,interface_section).items():
        used.setdefault(ordinal,evidence)
    for ordinal,evidence in _independent_primary_relations(index,descriptors,paragraphs,chapters,paragraph_epochs,interface_section).items():
        used.setdefault(ordinal,evidence)
    for ordinal,evidence in _additional_native_main_uses(index,descriptors,paragraphs,chapters,paragraph_epochs,interface_section).items():
        used.setdefault(ordinal,evidence)
    for ordinal,evidence in _complete_native_main_uses(index,descriptors,paragraphs,chapters,paragraph_epochs,interface_section).items():
        used.setdefault(ordinal,evidence)
    return used
