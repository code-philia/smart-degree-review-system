"""Bind explicit algorithm uses to a figure carrying that physical pseudocode."""
import re
from collections import defaultdict
from .numbering import normalize_text,normalize_label
from .local_rules import physical_target_key
from .reference_context import local_reference

_HEADER=re.compile(r'^\s*(?:算法|Algorithms?)\s*([A-Z]?\s*\.?\s*\d+(?:\s*[.\-]\s*\d+)*)\s+(.+)',re.I)
_USE=re.compile(r'(?:算法|(?<![A-Za-z])Algorithms?)\s*(?P<number>[A-Z]?\s*\.?\s*\d+(?:\s*[.\-]\s*\d+)*)(?![A-Za-z0-9]|\s*[.\-]\s*\d)',re.I)

_CITATION=r'\[\s*\d+(?:\s*[,，、–—-]\s*\d+)*\s*\]'

def _external_occurrence(text,match):
    """Source ownership applies to this occurrence, not the whole paragraph."""
    before=text[:match.start()];after=text[match.end():]
    if re.search(r'(?:文献|参考文献|论文|研究)\s*'+_CITATION+
                 r'\s*(?:中|里)?\s*(?:所?(?:给出|提出|描述|定义|列出|提供|介绍)(?:的)?|的)?\s*$',before):
        return True
    if re.match(r'\s*[(（]?\s*(?:引自|摘自|改编自|转载自|取自|源自)\s*'
                r'(?:文献|参考文献|论文)?\s*'+_CITATION,after):
        return True
    # A bounded author/citation qualifier after "from" cannot consume a
    # later local algorithm occurrence or a sentence about cited components.
    author=r"[A-Z][A-Za-z'’.-]*(?:\s+(?:[A-Z][A-Za-z'’.-]*|et|al\.?|and|&))*"
    return bool(re.match(r'\s*(?i:from)\s+(?:(?i:Ref(?:erence)?s?\.?)\s*)?'
                         r'(?:'+author+r'\s*)?'+_CITATION,after))

def _complete_procedure(obj):
    if obj.kind not in {'text','figure','table'}:return None
    raw=re.sub(r'<[^>]*>','',obj.text)
    if len(re.findall(r'(?:^|\n)\s*(?:算法|Algorithms?)\s*[A-Z]?\s*\.?\s*\d+',raw,re.I))!=1:return None
    header=_HEADER.match(raw)
    if not header or len(header.group(2).strip())<5:return None
    if not re.search(r'输入\s*[:：]|\bInput\s*:',raw,re.I) or not re.search(r'输出\s*[:：]|\bOutput\s*:',raw,re.I):return None
    if len(re.findall(r'(?:^|\n)\s*\d+\s+\S',raw))<2:return None
    return normalize_label(re.sub(r'\s+','',header.group(1)))

def _native_section_boundary(row,page):
    from .caption_context import body_font
    text=normalize_text(row.text).strip()
    if not re.match(r'^(?:第[一二三四五六七八九十百零\d]+[章节篇部]\s*\S|Chapter\s+(?:\d+|[IVX]+)\s+\S|\d+(?:\.\d+)*\s+\S)',text,re.I):return False
    if re.search(r'[。；;！？!?]',text) or len(text)>90:return False
    size=row.font_size or 0;typical=body_font(page) or 12
    # The actual large/bold title wins before page-margin clipping. A small
    # 9pt running header, including a bold one, remains a running header.
    return size>=max(10,typical*.95) and (row.bold or size>=typical*1.2)

def _physical_text(box,owner):
    w=max(0,min(box[2],owner[2])-max(box[0],owner[0]));h=max(0,min(box[3],owner[3])-max(box[1],owner[1]))
    area=max(1,(box[2]-box[0])*(box[3]-box[1]));owner_area=max(1,(owner[2]-owner[0])*(owner[3]-owner[1]))
    return w*h/area>=.90 and w*h/owner_area>=.65 and abs(box[1]-owner[1])<=18

def repair_algorithm_figure_usage(index,body,pages,objects,events=None):
    from .reference_identity_repair import _usage_owner,_semantic_contexts,_add_indirect,_semantic_text
    from .reference_identity_repair import _directory_keys,_scope_map,_key
    from .numbering import toc_line_keys
    records=defaultdict(dict)
    complete=[(number,obj) for obj in objects if (number:=_complete_procedure(obj)) is not None]
    scopes,_=_scope_map(index.document,_directory_keys(index.document)|toc_line_keys(index.document))
    scoped_positions=sorted(((line.page_number,line.bbox[1]),scopes.get(_key(line),'body'))
                            for line in index.document.lines)
    def scope_at(obj):
        preceding=[scope for position,scope in scoped_positions if position<=(obj.page_number,obj.bbox[1])]
        return preceding[-1] if preceding else 'body'
    competitors=defaultdict(list)
    for number,obj in complete:
        key=(scope_at(obj),number);box=tuple(obj.bbox)
        # Multiple parser observations of the same complete physical procedure
        # are one competitor. Equal titles/numbers on other pages are separate.
        if not any(old.page_number==obj.page_number and
                   (_physical_text(box,old.bbox) or _physical_text(old.bbox,box))
                   for old in competitors[key]):
            competitors[key].append(obj)
    for target in index.figures:
        owner=_usage_owner(target,'figure',pages,objects)
        if owner is None:continue
        declarations={}
        for number,obj in complete:
            if obj.page_number==target.line.page_number and _physical_text(obj.bbox,owner):
                declarations[number]=obj
        if len(declarations)!=1:continue
        number,obj=next(iter(declarations.items()))
        records[(target.scope,number)][(target.line.page_number,tuple(owner))]=(target,obj)
    owners=[(obj.page_number,tuple(obj.bbox)) for number,obj in complete]
    owners.extend((target.line.page_number,tuple(_usage_owner(target,'figure',pages,objects)))
                  for values in records.values() for target,obj in values.values())
    def inside(line):
        a=line.bbox;area=max(1,(a[2]-a[0])*(a[3]-a[1]))
        return any(page==line.page_number and b[0]<=(a[0]+a[2])/2<=b[2] and b[1]<=(a[1]+a[3])/2<=b[3]
                   and max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))/area>=.75 for page,b in owners)
    eligible=[(line,scope) for line,scope in body if not inside(line)]
    for line,scope,sources in _semantic_contexts(eligible,index.document):
        text=normalize_text(line.text)
        for match in _USE.finditer(text):
            if not local_reference(text,match) or _external_occurrence(text,match):continue
            number=normalize_label(re.sub(r'\s+','',match.group(1)))
            candidates=records.get((scope,number),{})
            if len(candidates)!=1 or len(competitors.get((scope,number),()))!=1:continue
            target,obj=next(iter(candidates.values()))
            before=len(events) if events is not None else 0
            _add_indirect(index,'figure',target,line,scope,events,'正文精确算法编号与同一物理图内完整伪代码的算法题名唯一对应；保留图题原编号')
            if events is not None and len(events)>before:
                events[-1]['algorithm_number']=number
                events[-1]['algorithm_physical_declaration']=dict(page=obj.page_number,bbox=list(obj.bbox),text=obj.text)
                events[-1]['body_context']=sources

    # A "below" pointer is permitted only for a complete, distinctly named
    # procedure that immediately follows it. Check native headings as well as
    # eligible prose; filtered-out section titles remain real boundaries.
    def subject(text,title):
        clean=lambda value:re.sub(r'基于|可学习|算法实现|算法|图像压缩|融合|机制|模型|方法|的|\s+','',normalize_text(value))
        parts=[clean(part) for part in re.split(r'与|和|及|、',title)]
        parts=[part for part in parts if len(part)>=4]
        return len(parts)>=2 and all(part in clean(text) for part in parts)
    def immediately_follows(sources,target,obj):
        last=sources[-1];end=(last['page'],last['bbox'][3]);start=(obj.page_number,obj.bbox[1])
        if not end<start or not 0<=obj.page_number-last['page']<=1:return False
        keys={(source['page'],tuple(source['bbox'])) for source in sources}
        for page in index.document.pages:
            if not last['page']<=page.number<=obj.page_number:continue
            for row in page.lines:
                if not row.text.strip():continue
                position=(row.page_number,row.bbox[1])
                if not end<position<start or (row.page_number,tuple(row.bbox)) in keys:continue
                if _native_section_boundary(row,page):return False
                if not page.height*.115<row.bbox[1]<page.height*.90:continue
                if re.fullmatch(r'\s*\d{1,4}\s*',row.text) and row.bbox[1]>page.height*.86:continue
                return False
        return True
    for line,scope,sources in _semantic_contexts(eligible,index.document):
        if not re.search(r'(?:如下|下(?:面|文))所示\s*[:：]?\s*$',line.text) or not re.search(r'算法(?:实现)?',line.text):continue
        candidates={}
        for (target_scope,number),values in records.items():
            if scope!=target_scope or len(values)!=1 or len(competitors.get((scope,number),()))!=1:continue
            target,obj=next(iter(values.values()));header=_HEADER.match(re.sub(r'<[^>]*>','',obj.text))
            if header and subject(line.text,header.group(2).split('\n')[0]) and immediately_follows(sources,target,obj):
                candidates[physical_target_key('figure',target)]=(target,obj,number)
        if len(candidates)!=1:continue
        target,obj,number=next(iter(candidates.values()));before=len(events) if events is not None else 0
        _add_indirect(index,'figure',target,line,scope,events,'正文完整具名算法的如下所示指针与紧随其后的完整伪代码唯一对应；不跨过正文或章节题名')
        if events is not None and len(events)>before:
            events[-1]['algorithm_number']=number
            events[-1]['algorithm_physical_declaration']=dict(page=obj.page_number,bbox=list(obj.bbox),text=obj.text)
            events[-1]['body_context']=sources
    return index
