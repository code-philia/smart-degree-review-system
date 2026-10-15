"""Use precise named procedure sections without borrowing neighbouring flows."""
import re
from .caption_context import body_font
from .local_rules import physical_target_key

_ENUM=re.compile(r'^\s*\d+[)）.]\s*(\S.+?)\s*$')
_MARKER=re.compile(r'^\s*\d+[)）.]\s*$')
_WORD=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*')
_OPERATIONS=('切分','索引','检索','召回','拼接','生成','排序','压缩','改写','转换','替换','重组','搜索','路由','预测','评价','规划','调用','分解','反馈','更新')


def _name_signature(title,names):
    # Keep the ordered complete compound name, rather than isolated shared
    # words such as RAG that also belong to the neighbouring workflow.
    tokens=[re.sub(r'[-_.]','',m.group()).casefold() for m in _WORD.finditer(title)]
    return tuple(dict.fromkeys(t for t in tokens if t in names))


def _compound_mentions(text,signatures):
    words=list(_WORD.finditer(text))
    tokens=[re.sub(r'[-_.]','',m.group()).casefold() for m in words]
    found=[]
    signatures=set(signatures)
    # A comparison remains ambiguous even when its other named procedure has
    # no figure. Recognize complete compounds in the same naming family;
    # function words such as "the RAG" do not introduce a method identity.
    ignored={'a','an','the','this','that','and','or','of','to','in','for','with'}
    for signature in tuple(signatures):
        if len(signature)<2:continue
        for start in range(len(words)-len(signature)+1):
            candidate=tuple(tokens[start:start+len(signature)])
            if candidate[1:]==signature[1:] and len(candidate[0])>=3 and candidate[0] not in ignored:
                signatures.add(candidate)
    for signature in signatures:
        for start in range(len(words)-len(signature)+1):
            end=start+len(signature)
            if tuple(tokens[start:end])!=signature:continue
            if any(not re.fullmatch(r'[\s/-]*',text[words[i].end():words[i+1].start()]) for i in range(start,end-1)):continue
            found.append((words[start].start(),words[end-1].end(),signature))
    return sorted(found)


def _owned_operations(prose,signature,signatures):
    operations=set();proof=[];owned_clauses=[]
    for line,scope,sources in prose:
        owner=None;used=False
        for clause in re.split(r'[。；;！？!?]',line.text):
            mentions=_compound_mentions(clause,signatures)
            if mentions:
                last=mentions[-1];owner=last[2]
                other=next((m for m in reversed(mentions[:-1]) if m[2]!=owner),None)
                # A compound pair joined as a common subject has no unique
                # owner. A contrast followed by an explicit own subject does.
                if other and re.fullmatch(r'\s*(?:和|与|及|、|以及|and|or|[,，/])\s*',clause[other[1]:last[0]],re.I):owner=None
                if owner==signature and re.search(r'(?:尚未|未曾|并未|没有|未|不在)[^。；;]{0,40}(?:说明|介绍|描述|给出|展示|实现|展开)',clause[last[1]:]):owner=None
            if owner!=signature:continue
            current={word for word in _OPERATIONS if word in clause}
            if current:
                operations.update(current);owned_clauses.append(clause.strip());used=True
        if used:proof.append((line,scope,sources))
    return operations,proof,owned_clauses


def _major_heading(line,typical):
    # Running headers often repeat the chapter name at 9pt. A real native
    # title remains a boundary even when its top falls inside that margin.
    text=line.text.strip();size=line.font_size
    return bool(line.source=='native' and len(text)<70 and size and size>=14
                and (not typical or size>=typical*1.12 or line.bold and size>=typical)
                and re.match(r'^(?:第\s*[0-9一二三四五六七八九十百]+\s*[章节]|Chapter\s+\d+(?:\s|$))',text,re.I))


def repair_named_workflow_sections(index,body,pages,objects,events=None):
    from .reference_identity_repair import _usage_owner,_usage_title,_workflow_names,_semantic_names,_add_indirect,_semantic_contexts
    boundaries=[]
    for page in index.document.pages:
        typical=body_font(page)
        rows=sorted(page.lines,key=lambda l:(l.bbox[1],l.bbox[0]))
        for line in rows:
            if line.role.startswith(('figure','table','header','footer')):continue
            if any(b[0]<=line.bbox[0] and b[1]<=line.bbox[1] and b[2]>=line.bbox[2] and b[3]>=line.bbox[3] for b in (*page.images,*page.tables,*page.graphics)):continue
            if _major_heading(line,typical):
                boundaries.append(((page.number,line.bbox[1]),set(),line));continue
            if not page.height*.115<line.bbox[1]<page.height*.90:continue
            text=line.text.strip();match=_ENUM.fullmatch(text)
            # Headings need native numbering and typography/adjacency, not a
            # model name mentioned at the start of an ordinary paragraph.
            paired=False
            if not match and len(text)<70:
                paired=any(_MARKER.fullmatch(other.text) and abs(other.bbox[1]-line.bbox[1])<=3 and 0<=line.bbox[0]-other.bbox[2]<=35 for other in rows)
            if (match or paired) and len(text)<70 and not re.search(r'[，,。；;：:]',text):
                names=_semantic_names(match.group(1) if match else text)
                boundaries.append(((page.number,line.bbox[1]),names,line))
            elif len(text)<70 and line.font_size and typical and line.font_size>=typical*1.12:
                boundaries.append(((page.number,line.bbox[1]),set(),line))
    boundaries.sort(key=lambda v:v[0])
    sections=[]
    for pos,(start,names,heading) in enumerate(boundaries):
        end=boundaries[pos+1][0] if pos+1<len(boundaries) else (float('inf'),0)
        if len(names)>=2:sections.append((start,end,names,heading))
    signatures=set()
    for target in index.figures:
        title=_usage_title(target,'figure',objects,pages)
        names=_workflow_names(title)
        if len(names)>=2:signatures.add(_name_signature(title,names))
    for start,end,names,heading in sections:
        candidates={}
        for target in index.figures:
            owner=_usage_owner(target,'figure',pages,objects)
            if owner is None or not start<(target.line.page_number,owner[1])<end:continue
            title=_usage_title(target,'figure',objects,pages)
            if not re.search(r'执行(?:过程|流程)|execution\s+(?:process|workflow)|workflow',title,re.I):continue
            title_names=_workflow_names(title)
            if len(title_names)<2 or not title_names<=names:continue
            candidates[(target.line.page_number,tuple(owner))]=(target,title_names,title)
        if len(candidates)!=1:continue
        target,title_names,title=next(iter(candidates.values()))
        selected=[(line,scope) for line,scope in body if scope==target.scope and start<(line.page_number,line.bbox[1])<end]
        prose=_semantic_contexts(selected,index.document)
        operations,proof,owned_clauses=_owned_operations(prose,_name_signature(title,title_names),signatures)
        if len(operations)<3 or not proof:continue
        line,scope,sources=proof[0]
        before=len(events) if events is not None else 0
        _add_indirect(index,'figure',target,line,scope,events,'正文具名编号小节说明主对象自身至少三个执行步骤，与该小节唯一同名物理流程图对应；不借用竞争对象步骤或双方泛化比较')
        if events is not None and len(events)>before:
            events[-1]['workflow_section_heading']=dict(page=heading.page_number,bbox=list(heading.bbox),text=heading.text)
            events[-1]['operations']=sorted(operations)
            events[-1]['workflow_owned_clauses']=owned_clauses
            events[-1]['body_context']=[s for line,scope,sources in proof for s in sources]
    return index