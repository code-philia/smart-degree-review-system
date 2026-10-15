"""Bind every named branch of a physical research plan to its own prose."""
import re
from .numbering import normalize_label
from .usage_text_cache import normalize_text


def _text(value):
    return re.sub(r'\s+','',normalize_text(value)).casefold()


def _cx(field):return (field['bbox'][0]+field['bbox'][2])/2
def _cy(field):return (field['bbox'][1]+field['bbox'][3])/2


def _layout(title,fields):
    if not re.search(r'研究内容|主要研究|研究框架|research.*(?:overview|framework)|whole.*framework',title,re.I):return None
    anchors=[f for f in fields if re.fullmatch(r'实现方案|模型方案|方法方案|models?|methods?',_text(f['text']),re.I)]
    tasks=[f for f in fields if re.fullmatch(r'(?:下游)?任务|tasks?',_text(f['text']),re.I)]
    if len(anchors)!=1 or len(tasks)!=1:return None
    header,task_header=anchors[0],tasks[0]
    if not 25<_cy(task_header)-_cy(header)<200:return None
    aliases=sorted([f for f in fields if f['page_number']==header['page_number']
                    and _cx(f)>header['bbox'][2]+10 and abs(_cy(f)-_cy(header))<=18
                    and re.fullmatch(r'[A-Za-z][A-Za-z0-9²³_-]{2,}',normalize_text(f['text']).strip())],key=_cx)
    if len(aliases)<2 or len({_text(f['text']) for f in aliases})!=len(aliases):return None
    if any(_cx(b)-_cx(a)<30 for a,b in zip(aliases,aliases[1:])):return None
    branches=[]
    for i,alias in enumerate(aliases):
        left=header['bbox'][2]+10 if i==0 else (_cx(aliases[i-1])+_cx(alias))/2
        right=float('inf') if i==len(aliases)-1 else (_cx(alias)+_cx(aliases[i+1]))/2
        output=[f for f in fields if f['page_number']==alias['page_number']
                and left<_cx(f)<right and abs(_cy(f)-_cy(task_header))<=12
                and len(_text(f['text']))>=4]
        if len(output)!=1:return None
        methods=[f for f in fields if f['page_number']==alias['page_number']
                 and left<_cx(f)<right and alias['bbox'][3]<f['bbox'][1]<output[0]['bbox'][1]-5
                 and re.search(r'机制|模块|框架|投影器|algorithm|module|mechanism',f['text'],re.I)]
        if not methods:return None
        branches.append(dict(name=normalize_text(alias['text']).strip(),name_bbox=alias['bbox'],
                             task=output[0]['text'],task_bbox=output[0]['bbox'],
                             methods=[dict(text=f['text'],bbox=f['bbox']) for f in methods]))
    return dict(branches=branches,scheme_anchor=header,task_anchor=task_header)


def roadmap_native_candidate(title,fields):
    return _layout(title,fields) is not None or _module_layout(title,fields) is not None


def _wrapped_fields(fields):
    """Join only consecutive, centered lines of the same physical native box."""
    answer=[]
    for field in sorted(fields,key=lambda f:(f['page_number'],f['bbox'][1],f['bbox'][0])):
        row=dict(field,bbox=list(field['bbox']))
        previous=[old for old in answer if old['page_number']==row['page_number']
                  and old.get('source')==row.get('source')=='native'
                  and -.15*min(old['bbox'][3]-old['bbox'][1],row['bbox'][3]-row['bbox'][1])
                      <=row['bbox'][1]-old['bbox'][3]<=5
                  and abs(_cx(old)-_cx(row))<=5
                  and max(old['bbox'][0],row['bbox'][0])<min(old['bbox'][2],row['bbox'][2])]
        if len(previous)!=1:
            answer.append(row);continue
        old=previous[0];old['text']+=row['text']
        old['bbox']=[min(old['bbox'][0],row['bbox'][0]),old['bbox'][1],
                     max(old['bbox'][2],row['bbox'][2]),row['bbox'][3]]
    return answer


def _module_layout(title,fields):
    if not re.search(r'研究内容|主要研究|研究框架|research.*(?:overview|framework)|whole.*framework',title,re.I):return None
    actual=_wrapped_fields(fields)
    anchors=[f for f in actual if _text(f['text']) in {'研究方法','实现方法','研究方案'}]
    if len(anchors)!=1:return None
    anchor=anchors[0]
    methods=[f for f in actual if f['page_number']==anchor['page_number']
             and f['bbox'][0]>anchor['bbox'][2]+10 and abs(_cy(f)-_cy(anchor))<=14
             and re.fullmatch(r'[\u4e00-\u9fff]{6,}(?:模块|机制)',_text(f['text']))]
    if len(methods)<2:return None
    aliases=sorted([f for f in actual if f['page_number']==anchor['page_number']
                    and f['bbox'][1]>max(m['bbox'][3] for m in methods)+10
                    and 15<_cy(f)-_cy(anchor)<100
                    and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{2,}',normalize_text(f['text']).strip())],key=_cx)
    if len(aliases)<2 or len({_text(f['text']) for f in aliases})!=len(aliases):return None
    if max(_cy(f) for f in aliases)-min(_cy(f) for f in aliases)>8:return None
    if any(_cx(b)-_cx(a)<40 for a,b in zip(aliases,aliases[1:])):return None
    # Each column must remain centered on its own model. Midpoint partitioning
    # alone could absorb an unrelated extra module at the edge of a diagram.
    branches=[];claimed=[]
    for i,alias in enumerate(aliases):
        left=anchor['bbox'][2]+10 if i==0 else (_cx(aliases[i-1])+_cx(alias))/2
        right=float('inf') if i==len(aliases)-1 else (_cx(alias)+_cx(aliases[i+1]))/2
        owned=sorted([m for m in methods if left<_cx(m)<right],key=_cx)
        if not owned or abs(sum(_cx(m) for m in owned)/len(owned)-_cx(alias))>12:return None
        claimed.extend(owned)
        branches.append(dict(name=normalize_text(alias['text']).strip(),name_bbox=alias['bbox'],
                             methods=[dict(text=m['text'],bbox=m['bbox']) for m in owned]))
    if len(claimed)!=len(methods):return None
    return dict(branches=branches,method_anchor=anchor)


def _qualified_method_use(text,method):
    value=_text(method['text']);compact=_text(text)
    patterns=[re.escape(value)]
    # A Chinese qualifier may expand a fixed method name (e.g. shared and
    # private representations); preserve all original characters in order.
    for cut in range(2,len(value)-5):
        patterns.append(re.escape(value[:cut])+r'[\u4e00-\u9fff]{1,8}'+re.escape(value[cut:]))
    for pattern in patterns:
        for match in re.finditer(pattern,compact):
            clause=re.split(r'[。；;]',compact[match.end():])[0][:190]
            if not re.match(r'(?:中|里|内|方面|上)',clause):continue
            if re.search(r'未使用|不使用|未采用|不采用|没有采用|没有使用|无需使用|不需要使用',clause):continue
            if re.search(r'映射|构建|重构|发现|挖掘|最大化|最小化|解耦|聚焦|缓解|查询|聚合|增强',clause):return True
    return False


def _module_branch_rows(branch,peers,passages):
    patterns={name:re.compile(r'(?<![A-Za-z0-9_-])'+re.escape(name)+r'(?![A-Za-z0-9_-])',re.I) for name in peers}
    for rows,value in passages:
        text=normalize_text(value)
        matches=sorted((m.start(),m.end(),name) for name,p in patterns.items() for m in p.finditer(text))
        for start,end,name in matches:
            if name!=branch['name']:continue
            prefix=re.split(r'[。；;]',text[:start])[-1][-90:]
            if any(p.search(prefix) for n,p in patterns.items() if n!=name):continue
            limit=min((a for a,b,n in matches if a>start and n!=name),default=len(text))
            window=prefix+text[start:limit]
            if _denied_operation(window) or _foreign_subject(window,name):continue
            if re.search(r'未采用|未使用|不使用|不采用|没有采用|没有使用|无需采用|\b(?:not|never|without)\b',window,re.I):continue
            if all(_qualified_method_use(window,method) for method in branch['methods']):return rows
    return []


def _owned_passages(ordinal,groups,nearby):
    numbers={label.number for label in groups[ordinal]}
    answer=[]
    for rows,value in nearby(ordinal):
        text=normalize_text(value)
        references={normalize_label(m.group(1)) for m in re.finditer(
            r'(?:图|Figures?|Fig\.?)\s*([A-Z]?\d+(?:[.\-–]\d+)*)',text,re.I)}
        if references-numbers:continue
        # An explicit denial introducing the entire following list must not
        # disappear when a later name starts a shorter model window.
        if re.match(r'^\s*[^。；;]{0,25}(?:不使用|未使用|不采用|未采用)[^。；;]{0,35}[:：]',text):continue
        answer.append((rows,value))
    return answer


def _method_keys(branch):
    for field in branch['methods']:
        value=_text(field['text'])
        yield value
        value=re.sub(r'^(?:基于|面向)','',value)
        value=re.sub(r'(?:机制|模块|框架|投影器)$','',value)
        if len(value)>=4:yield value


def _foreign_subject(window,name):
    statements=re.finditer(r'(?:^|[。；;])\s*(?:(?:具体而言|例如|此外|其中|同时|另外)[，,]\s*)?'
                           r'([A-Za-z][A-Za-z0-9²³_-]{2,})\s*(?:模型|网络|方案)?\s*'
                           r'(?:使用|采用|通过|利用|包含|设计|提出|实现|将)',window,re.I)
    return any(match.group(1).casefold()!=name.casefold() for match in statements)


def _denied_operation(window):
    return bool(re.search(r'未采用|未使用|不使用|不采用|没有采用|没有使用|无需采用|'
                          r'(?:不|未)(?:讨论|介绍|解释|说明)|\b(?:not|never|without)\b',window,re.I))


def _concrete_branch_operation(window,branch):
    compact=_text(window)
    for key in sorted(set(_method_keys(branch)),key=len,reverse=True):compact=compact.replace(key,'')
    compact=compact.replace(_text(branch['task']),'')
    return bool(re.search(r'嵌入|融合|过滤|捕捉|生成|输入|输出|重建|最小化|最大化|映射|'
                          r'提取|编码|解耦|建模|采集|聚合|交互|预测|修补',compact))


def _branch_rows(branch,peers,passages):
    patterns={name:re.compile(r'(?<![A-Za-z0-9_-])'+re.escape(name)+r'(?![A-Za-z0-9_-])',re.I) for name in peers}
    for rows,value in passages:
        text=normalize_text(value)
        matches=sorted((m.start(),m.end(),name) for name,p in patterns.items() for m in p.finditer(text))
        for start,end,name in matches:
            if name!=branch['name']:continue
            next_start=min((a for a,b,n in matches if a>start),default=len(text))
            prefix=re.split(r'[。；;]',text[:start])[-1][-90:]
            if any(p.search(prefix) for n,p in patterns.items() if n!=name):continue
            window=prefix+text[start:next_start]
            if _denied_operation(window) or _foreign_subject(window,name):continue
            if re.search(r'未采用|未使用|不使用|不采用|没有采用|无需采用|\b(?:not|never|without)\b',window,re.I):continue
            compact=_text(window)
            if _text(branch['task']) not in compact:continue
            if not any(key in compact for key in _method_keys(branch)):continue
            if not _concrete_branch_operation(window,branch):continue
            if not re.search(r'提出|设计|实现|包含|采用|使用|利用|构建|\b(?:propos\w*|design\w*|implement\w*|us\w*|contain\w*)\b',window,re.I):continue
            return rows
    return []


def roadmap_relation_proposals(context,groups,nearby,fields=None):
    actual=context['native_fields'] if fields is None else fields
    answer=[]
    for ordinal,areas in context['regions'].items():
        topology=_layout(areas[0]['title'],actual.get(ordinal,[]))
        if topology is None:continue
        names=[branch['name'] for branch in topology['branches']]
        passages=_owned_passages(ordinal,groups,nearby)
        witnesses=[_branch_rows(branch,names,passages) for branch in topology['branches']]
        if not all(witnesses):continue
        rows=list({(row.page_number,row.bbox,row.text):row for own in witnesses for row in own}.values())
        answer.append((ordinal,'named_research_plan_branches',rows,topology))
    for ordinal,areas in context['regions'].items():
        topology=_module_layout(areas[0]['title'],actual.get(ordinal,[]))
        if topology is None:continue
        names=[branch['name'] for branch in topology['branches']]
        passages=_owned_passages(ordinal,groups,nearby)
        witnesses=[_module_branch_rows(branch,names,passages) for branch in topology['branches']]
        if not all(witnesses):continue
        rows=list({(row.page_number,row.bbox,row.text):row for own in witnesses for row in own}.values())
        answer.append((ordinal,'named_research_module_branches',rows,topology))
    return answer
