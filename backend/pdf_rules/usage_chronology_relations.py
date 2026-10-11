"""Pure usage evidence for complete, physically ordered technical chronologies."""
import math,re,unicodedata
from dataclasses import replace
from .caption_context import body_font
from .numbering import normalize_label
from .usage_scope import usage_scope_identity
from .usage_paragraphs import span_anchor

_TITLE=re.compile(r'发展历程|演进(?:过程|历程|路线)|发展(?:历史|过程)|development\s+history|evolution(?:ary)?\s+(?:process|history)|technical\s+timeline',re.I)
_FIGURE=re.compile(r'(?:图|Figures?|Fig\.?)\s*([A-Z]?\d+(?:[.\-–]\d+)*)',re.I)
_BAD={'header','footer','toc','reference','figure_caption','table_caption','heading','equation','code'}
_DENIED=re.compile(r'(?:未|不|没有|无需|并非)(?:采用|使用|实现|定义|讨论|解释|介绍|说明|属于|对应)|\b(?:not|never)\b',re.I)
_FOREIGN=re.compile(r'(?:另一|其他|其它|不同)(?:个|种|套)?(?:模型|方法|协议|系统|图|对象|时间线|流程|架构)|不属于本文|并非本图',re.I)
_OPERATIONS=re.compile(r'处理|映射|捕捉|建模|建立|训练|微调|识别|生成|转换|计算|推出|引入|实现|协商|加密|发布|标准化|访问(?!计数器)|记录|分配|迁移|抵御|集成|提取|解析|恢复|\b(?:process|map|train|encode|generate|encrypt|negotiate|migrate|allocate)\b',re.I)
_LIST_ONLY=re.compile(r'(?:仅|只)(?:列出|列举|罗列)(?:名称|名字|年代|标签)|\bonly\s+(?:lists?|names?|years?)\b',re.I)
_OWNERS=re.compile(r'(?:仅|只)(?:针对|对)\s*([A-Za-z][A-Za-z0-9_-]{2,})\s*(?:模型|方法|协议|系统|架构)|\b(?:only|solely)\s+(?:for|in)\s+([A-Za-z][A-Za-z0-9_-]{2,})\s+(?:model|method|protocol|system|architecture)\b',re.I)
_PROGRESS=re.compile(r'发展|演进|早期|随后|之后|开始|引入|发布|如今|近年来|兴起|新兴|未来|世纪|年代|至今|evol|develop|early|later|subsequent|introduced',re.I)
# Bilingual operation vocabulary, not object/model names or paper exceptions.
_CONCEPTS={
 'statistics':r'统计|概率|词频|n[- ]gram|probabil|statistic',
 'neural':r'神经网络|neural\s*networks?',
 'dense':r'稠密|dense',
 'sequence':r'时序|循环神经|\brnns?\b|sequential|recurrent',
 'transformer':r'transformer|自注意力|多头注意力',
 'rules':r'人工规则|语法规则|规则方法|rule[- ]based|grammar\s*rule',
 'parsing':r'语法解析|parsing\s*tree|解析器',
 'pretrained':r'预训练|pre[- ]train',
 'large_language':r'大型?语言模型|large\s*language\s*models?|\bllms?\b',
 'encoder_decoder':r'encoder[- ]decoder|seq2seq|序列到序列|编码.{0,4}解码',
 'schema':r'schema\s*link|模式链接|数据库模式.{0,15}语义关联',
 'context':r'in[- ]context|上下文(?:学习|建模)',
 'finetune':r'微调|fine[- ]tun',
 'unified_address':r'统一虚拟(?:寻址|地址)|\buva\b|unified\s*virtual\s*address',
 'single_pointer':r'单指针|相同(?:的)?指针|同一(?:个)?指针|same\s*pointer',
 'demand_paging':r'按需(?:页)?迁移|缺页异常|demand.{0,12}pag',
 'access_counter':r'访问计数器|access.{0,8}counter',
}
_PRIMARY={'statistics','neural','rules','pretrained','large_language'}

def _text(value):return unicodedata.normalize('NFKC',value).casefold()
def _compact(value):return re.sub(r'\s+|[“”"‘’]','',_text(value))
def _concepts(value):return {k for k,p in _CONCEPTS.items() if re.search(p,_text(value))}
def _center(field,axis=0):return (field['bbox'][axis]+field['bbox'][axis+2])/2
def _inside(box,area,tolerance=.5):return area[0]-tolerance<=box[0]<box[2]<=area[2]+tolerance and area[1]-tolerance<=box[1]<box[3]<=area[3]+tolerance
def _literal(name,value):return bool(re.search(r'(?<![a-z0-9_])'+re.escape(name)+r'(?![a-z0-9_])',_text(value)))

def _ink(row):
    if row.source!='native' or not row.font_size or row.font_size<=0 or row.direction[0]<.9 or abs(row.direction[1])>.05:return False
    covered={i for start,end,box in row.text_regions if box[2]>box[0] and box[3]>box[1] for i in range(start,end)}
    return all(i in covered for i,c in enumerate(row.text) if not c.isspace())

def chronology_title_candidate(title):return bool(_TITLE.search(title))

def _time_label(text):
    value=_compact(text)
    if re.fullmatch(r'(?:19|20)\d{2}(?:年)?',value):return int(value[:4]),None
    match=re.fullmatch(r'(\d{2})世纪(\d{2})年代(中期|末|末期|初期)?',value)
    if match:
        century,decade,part=match.groups();start=(int(century)-1)*100+int(decade)
        return (start+4,start+7) if part=='中期' else (start+7,start+10) if part in {'末','末期'} else (start,start+10)
    if re.fullmatch(r'早期(?:基础)?阶段|现代|early|modern',value):return None,None
    return None

def _join(fields):
    ordered=sorted(fields,key=lambda f:(f['bbox'][1],f['bbox'][0]));answer=[]
    for field in ordered:
        if answer:
            prev=answer[-1];a,b=prev['bbox'],field['bbox'];height=max(a[3]-a[1],b[3]-b[1])
            horizontal=min(a[2],b[2])-max(a[0],b[0])
            if (-height*.15<=b[1]-a[3]<=height*.6 and horizontal>min(a[2]-a[0],b[2]-b[0])*.6
                    and abs(_center(prev)-_center(field))<=max(5,(a[2]-a[0])*.15)):
                answer[-1]={**prev,'text':prev['text']+field['text'],'bbox':[min(a[0],b[0]),a[1],max(a[2],b[2]),b[3]]};continue
        answer.append(dict(field))
    return answer

def _layout(title,fields):
    if not chronology_title_candidate(title) or len(fields)<6:return None
    unique={(_compact(f['text']),tuple(round(x,1) for x in f['bbox'])):f for f in fields}
    fields=list(unique.values());times=sorted((f for f in fields if _time_label(f['text']) is not None),key=_center)
    content=[f for f in fields if _time_label(f['text']) is None]
    if not content:return None
    top=min(f['bbox'][1] for f in content);height=min(f['bbox'][3]-f['bbox'][1] for f in content)
    band=[f for f in content if f['bbox'][1]-top<=height*1.2]
    headers=[]
    for field in sorted(band,key=_center):
        if headers and abs(_center(field)-_center(headers[-1][0]))<8:headers[-1].append(field)
        else:headers.append([field])
    if times and len(headers)!=len(times):
        # Sloped evolution layouts: each printed axis mark owns one column.
        columns=[[] for _ in times]
        for field in content:columns[min(range(len(times)),key=lambda i:abs(_center(field)-_center(times[i])))].append(field)
        if any(not column for column in columns):return None
        headers=[[min(column,key=lambda f:f['bbox'][1])] for column in columns]
    if not 3<=len(headers)<=6:return None
    nodes=[]
    for header in headers:
        joined=_join(header);name='、'.join(f['text'].strip('、') for f in joined)
        if not name or re.search(r'[:：]|^\d|应用|架构',name):return None
        nodes.append(dict(name=name,header_fields=header,center=sum(_center(f) for f in header)/len(header)))
    if any(b['center']-a['center']<25 for a,b in zip(nodes,nodes[1:])):return None
    if times and len(times)!=len(nodes):return None
    numeric=[_time_label(f['text'])[0] for f in times]
    concrete=[year for year in numeric if year is not None]
    if concrete!=sorted(set(concrete)):return None
    used_header={id(f) for header in headers for f in header}
    for i,node in enumerate(nodes):
        column=[f for f in content if id(f) not in used_header and min(range(len(nodes)),key=lambda j:abs(_center(f)-nodes[j]['center']))==i]
        node['details']=_join(column);node['primary']=sorted(_concepts(node['name'])&_PRIMARY)
        names=[]
        if not node['primary']:
            for part in re.split(r'[、,]',node['name']):
                english=re.findall(r'[a-z][a-z0-9_-]{2,}',_text(part))
                if english:names.extend(english)
                elif part.strip():names.append(_compact(part))
        node['names']=names
        mechanisms=_concepts(' '.join(f['text'] for f in node['details']))-set(node['primary'])
        # Generic topic words are not a concrete mechanism for a named stage.
        node['mechanisms']=sorted(mechanisms-(_PRIMARY if names else set()))
        node['time']=dict(text=times[i]['text'],bbox=list(times[i]['bbox']),period=_time_label(times[i]['text'])) if times else None
        if not names and not node['primary']:return None
    if not times and any(not n['mechanisms'] for n in nodes):return None
    return dict(kind='ordered_technical_history',title=title,stages=nodes,fields=fields)

def chronology_native_candidate(title,fields):return _layout(title,[f for f in fields if f.get('source')=='native']) is not None

def _axis(context,target,topology):
    if any(n['time'] is not None for n in topology['stages']):return True
    document=context.get('_document');scopes=context.get('usage_scopes') or context.get('usage_scope_map')
    if document is None:return True
    page=next((p for p in document.pages if p.number==target.line.page_number),None)
    if page is None:return True
    nodes=topology['stages'];top=min(f['bbox'][1] for n in nodes for f in n['header_fields'])
    bands=[]
    for row in page.lines:
        if (not re.fullmatch(r'(?:19|20)\d{2}(?:年)?',row.text.strip()) or not _ink(row)
                or not 0<top-row.bbox[3]<60 or row.role in _BAD
                or usage_scope_identity(scopes,row)!=usage_scope_identity(scopes,target)):continue
        if min(abs((row.bbox[0]+row.bbox[2])/2-n['center']) for n in nodes)>12:continue
        found=next((b for b in bands if abs(b[0]-(row.bbox[1]+row.bbox[3])/2)<5),None)
        if found:found[1].append(row)
        else:bands.append(((row.bbox[1]+row.bbox[3])/2,[row]))
    if not bands:return True
    rows=max(bands,key=lambda b:b[0])[1]
    if len(rows)!=len(nodes):return False
    rows.sort(key=lambda r:(r.bbox[0]+r.bbox[2])/2);years=[int(r.text[:4]) for r in rows]
    if years!=sorted(set(years)):return False
    for node,row in zip(nodes,rows):node['time']=dict(text=row.text,bbox=list(row.bbox),period=(int(row.text[:4]),None),native_axis_outside_region=True)
    return True

def _passages(context,target,passages):
    scopes=context.get('usage_scopes') or context.get('usage_scope_map')
    if scopes is None:return []
    state=usage_scope_identity(scopes,target)
    if state[0]!='body' or state[1]<0:return []
    areas=[a for values in context['regions'].values() for a in values];answer={}
    pages={p.number:p for p in context['_document'].pages} if context.get('_document') is not None else {}
    # Expanded parser windows may contain a prior reference to another figure.
    # Recover only genuinely separate original paragraphs; each window must
    # itself be an unchanged substring of the actual source-native page ink.
    source_rows={}
    chapter=context.get('chapters',{}).get((target.line.page_number,state[1]))
    for window in context.get('body_passages',[]):
        for anchor in window:
            page=pages.get(anchor.page_number)
            if (page is None or anchor.source!='native' or anchor.role in _BAD or not anchor.text_regions
                    or usage_scope_identity(scopes,anchor)!=state or abs(anchor.page_number-target.line.page_number)>4
                    or chapter is not None and context.get('chapters',{}).get((anchor.page_number,state[1]))!=chapter
                    or any(a['page_number']==anchor.page_number and _inside(anchor.bbox,a['bbox']) for a in areas)):continue
            ordered=sorted(page.lines,key=lambda r:(r.bbox[1],r.bbox[0]))
            if _compact(anchor.text) not in _compact(' '.join(r.text for r in ordered)):continue
            typical=body_font(page)
            for row in ordered:
                if (row.source!='native' or row.role in _BAD or row.bold or not row.font_size
                        or typical and row.font_size<typical*.95 or usage_scope_identity(scopes,row)!=state
                        or (row.page_number,row.bbox) in context.get('caption_keys',set())
                        or any(a['page_number']==row.page_number and _inside(row.bbox,a['bbox']) for a in areas)
                        or not anchor.bbox[1]-.5<=(row.bbox[1]+row.bbox[3])/2<=anchor.bbox[3]+.5
                        or _compact(row.text) not in _compact(anchor.text)):continue
                source_rows[(row.page_number,row.bbox,row.text)]=row
    paragraphs=[]
    for row in sorted(source_rows.values(),key=lambda r:(r.page_number,r.bbox[1],r.bbox[0])):
        if (paragraphs and row.page_number==paragraphs[-1][-1].page_number
                and -.5<=row.bbox[1]-paragraphs[-1][-1].bbox[3]<=32
                and row.bbox[0]<=paragraphs[-1][-1].bbox[0]+(row.font_size or 12)):
            paragraphs[-1].append(row)
        else:paragraphs.append([row])
    # A native paragraph can describe the preceding figure, then independently
    # introduce a later chronology stage. Keep only its own printed sentences;
    # never remove a foreign reference from the sentence that contains it.
    for paragraph in paragraphs:
        whole=_joined(paragraph)
        if _DENIED.search(whole.text) or _FOREIGN.search(whole.text) or _LIST_ONLY.search(whole.text):continue
        for part,value in _fragments([whole]):
            if {normalize_label(m.group(1)) for m in _FIGURE.finditer(value)}-{target.number}:continue
            answer[(part.page_number,part.bbox,part.text)]=part
    for rows,value in passages:
        if not rows or value!=' '.join(r.text for r in rows):continue
        if _DENIED.search(value) or _FOREIGN.search(value) or _LIST_ONLY.search(value):continue
        if {normalize_label(m.group(1)) for m in _FIGURE.finditer(value)}-{target.number}:continue
        if any(r.source!='native' or r.role in _BAD or usage_scope_identity(scopes,r)!=state
               or (r.page_number,r.bbox) in context.get('caption_keys',set())
               or any(a['page_number']==r.page_number and _inside(r.bbox,a['bbox']) for a in areas) for r in rows):continue
        for row in rows:
            page=pages.get(row.page_number);native=[]
            if page is not None:
                ordered_source=sorted(page.lines,key=lambda r:(r.bbox[1],r.bbox[0]))
                if _compact(row.text) not in _compact(' '.join(r.text for r in ordered_source)):continue
                typical=body_font(page)
                for original in page.lines:
                    if (original.source!='native' or original.role in _BAD or original.bold
                            or usage_scope_identity(scopes,original)!=state
                            or original.font_size and typical and original.font_size<typical*.95
                            or (original.page_number,original.bbox) in context.get('caption_keys',set())
                            or any(a['page_number']==original.page_number and _inside(original.bbox,a['bbox']) for a in areas)):
                        continue
                    if not row.bbox[1]-.5<=(original.bbox[1]+original.bbox[3])/2<=row.bbox[3]+.5:continue
                    if _compact(original.text) not in _compact(row.text):continue
                    native.append(original)
            for original in native or ([row] if _ink(row) else []):answer[(original.page_number,original.bbox,original.text)]=original
    ordered=sorted(answer.values(),key=lambda r:(r.page_number,r.bbox[1],r.bbox[0]));paragraphs=[]
    for row in ordered:
        if (paragraphs and row.page_number==paragraphs[-1][-1].page_number
                and -.5<=row.bbox[1]-paragraphs[-1][-1].bbox[3]<=max(32,(row.font_size or 12)*1.5)
                and row.bbox[0]<=paragraphs[-1][-1].bbox[0]+(row.font_size or 12)):
            paragraphs[-1].append(row)
        else:paragraphs.append([row])
    result=[]
    for paragraph in paragraphs:result.append(_joined(paragraph))
    return result

def _joined(paragraph):
    text='';regions=[]
    for row in paragraph:
        offset=len(text);text+=row.text+' '
        regions.extend((a+offset,b+offset,box) for a,b,box in row.text_regions)
    return replace(paragraph[0],text=text.rstrip(),text_regions=tuple(regions),bbox=(min(r.bbox[0] for r in paragraph),min(r.bbox[1] for r in paragraph),max(r.bbox[2] for r in paragraph),max(r.bbox[3] for r in paragraph)))

def _fragments(rows):
    answer=[]
    for row in rows:
        for match in re.finditer(r'[^。；;]+[。；;]?',row.text):
            if not match.group().strip():continue
            start,end=match.span();part=span_anchor(row,start,end)
            part=replace(part,text=row.text[start:end],text_regions=tuple((max(a,start)-start,min(b,end)-start,box) for a,b,box in row.text_regions if a<end and b>start),reference_regions=())
            if _ink(part):answer.append((part,part.text))
    return answer

def _years(text):
    years=[int(m.group()) for m in re.finditer(r'(?<!\d)(?:19|20)\d{2}(?!\d)',text)]
    if re.search(r'上世纪八十年代|二十世纪八十年代',text):years.append(1980)
    if re.search(r'二十一世纪|21\s*世纪',text):years.append(2000)
    return years

def _evidence(topology,rows):
    fragments=_fragments(rows);stages=topology['stages'];picked=[];missing_names=0;previous=None
    for i,node in enumerate(stages):
        primary=set(node['primary']);mechanisms=set(node['mechanisms']);names=node['names']
        owned_subject=lambda value:all(_literal(a or b,node['name']+' '+topology['title'])
                                      for a,b in _OWNERS.findall(value))
        node_present=lambda value:primary<=_concepts(value) if primary else all(_literal(n,value) if re.search(r'[a-z]',n) else n in _compact(value) for n in names)
        name_rows=[r for r,value in fragments if owned_subject(value) and node_present(value)] if primary else [r for r,value in fragments if owned_subject(value) and any(_literal(n,value) if re.search(r'[a-z]',n) else n in _compact(value) for n in names)]
        if not primary and names and not all(any(_literal(n,value) if re.search(r'[a-z]',n) else n in _compact(value) for r,value in fragments) for n in names):name_rows=[]
        if not name_rows:
            missing_names+=1
            if primary or not mechanisms:return []
        # A named stage with a printed but unknown mechanism still needs that
        # concrete mechanism in prose; its name alone cannot explain the node.
        if names and not mechanisms and node['details'] and not any(
                _compact(detail['text']) in _compact(value)
                for detail in node['details'] for row,value in fragments):return []
        owned=[]
        if names and not mechanisms:
            for name in names:
                options=[r for r,value in fragments if owned_subject(value) and ( _literal(name,value) if re.search(r'[a-z]',name) else name in _compact(value)) and _OPERATIONS.search(value)
                         and (previous is None or (r.page_number,r.bbox[1])>previous)]
                if not options:return []
                owned.append(min(options,key=lambda r:(r.page_number,r.bbox[1],len(r.text))))
        else:
            options=[r for r,value in fragments if owned_subject(value) and _OPERATIONS.search(value)
                     and (bool(mechanisms&_concepts(value)) if mechanisms else node_present(value))
                     and (node_present(value) or bool(mechanisms&_concepts(value)))
                     and (not primary or node_present(value) or not (_concepts(value)&_PRIMARY))
                     and (mechanisms or (_concepts(value)&_PRIMARY)==primary)
                     and (previous is None or (r.page_number,r.bbox[1])>previous)]
            if not options:return []
            owned=[min(options,key=lambda r:(r.page_number,r.bbox[1],len(r.text)))]
        if names and name_rows and min((r.page_number,r.bbox[1]) for r in owned)<min(
                (r.page_number,r.bbox[1]) for r in name_rows):return []
        start=node['time']['period'][0] if node['time'] else None
        end=node['time']['period'][1] if node['time'] else None
        if end is None and i+1<len(stages) and stages[i+1]['time']:end=stages[i+1]['time']['period'][0]
        dated=owned+([min(name_rows,key=lambda r:(r.page_number,r.bbox[1]))] if names and name_rows else [])
        for row in dated:
            years=_years(row.text)
            if years and any(start is not None and year<start or end is not None and year>=end for year in years):return []
        node['literal_node_in_body']=bool(name_rows);node['body_operations']=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text) for r in owned]
        picked.append(owned);previous=min((r.page_number,r.bbox[1]) for r in owned)
    if missing_names>1:return []
    positions=[min((r.page_number,r.bbox[1]) for r in item) for item in picked]
    if positions!=sorted(positions) or len(set(positions))!=len(positions):return []
    if not any(_PROGRESS.search(r.text) for r in rows):return []
    used={ (r.page_number,r.bbox,r.text):r for part in picked for r in part}
    return list(used.values())

def chronology_relation_proposals(context,groups,nearby,fields=None):
    """Complete independent stage use, bound to one local physical chronology."""
    actual=context['native_fields'] if fields is None else fields;answer=[]
    for ordinal,areas in context['regions'].items():
        target=groups[ordinal][0];valid=[]
        for field in actual.get(ordinal,[]):
            if not any(a['page_number']==field.get('page_number') and _inside(field['bbox'],a['bbox']) for a in areas):continue
            if field.get('source')!='native':
                score=field.get('confidence');detection=field.get('detection_confidence')
                if (field.get('source')!='usage_graphic_ocr_cpu' or isinstance(score,bool) or isinstance(detection,bool)
                        or not isinstance(score,(int,float)) or not isinstance(detection,(int,float))
                        or not math.isfinite(score) or not math.isfinite(detection) or not .98<=score<=1 or not .80<=detection<=1
                        or not field.get('pdf_sha') or not field.get('region_identity')):continue
            valid.append(field)
        topology=_layout(areas[0]['title'],valid)
        if topology is None or not _axis(context,target,topology):continue
        rows=_passages(context,target,nearby(ordinal));used=_evidence(topology,rows)
        if used:answer.append((ordinal,'chronology_complete_stages',used,topology))
    return [entry for entry in answer if not any(other[0]!=entry[0] and
            {(r.page_number,r.bbox,r.text) for r in entry[2]}&{(r.page_number,r.bbox,r.text) for r in other[2]} for other in answer)]
