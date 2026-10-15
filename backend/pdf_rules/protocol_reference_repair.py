"""Bind explicitly declared protocol/function carriers to proved prose uses.

The module consumes a DocumentIndex and existing layout observations. It does
not read paths, audit labels, PDF files, caches, OCR services or scan engines.
Every inferred use is bound to a physical caption; targets are never removed.
"""
import re
import unicodedata
from dataclasses import dataclass, replace
from .model import DocumentIndex
from .numbering import FIGURE_CAPTION, FIGURE_REFERENCE, normalize_text, toc_line_keys
from .local_rules import physical_target_key
from .reference_identity_repair import (_add_indirect, _contained, _directory_keys,
    _is_body, _key, _scope_map)

_PROTOCOL = re.compile(r'(?:协议|(?<![A-Za-z])Protocol)\s*(\d+(?:\.\d+)+)\s*'
                       r'[(（]\s*Π\s*([A-Za-z][A-Za-z0-9_-]{2,})\s*[)）]', re.I)
_FUNCTION = re.compile(r'^(?:理想函数|函数|Ideal\s*Functionality|Functionality)\s*[:：]', re.I)
_CONTINUED = re.compile(r'[（(]\s*续\s*[)）]|continued|continuation|Part\s*II\b', re.I)
_LISTS = ('figures','tables','figure_refs','table_refs','graphic_figure_refs',
          'graphic_table_refs','appendices','appendix_refs')

def _norm(text):
    return unicodedata.normalize('NFKC',normalize_text(text)).replace('−','-')

def _compact(text):
    return re.sub(r'\s+','',_norm(text))

def _name(text):
    return text.casefold()

def _names(text):
    return {_name(t) for t in re.findall(r'[A-Za-z][A-Za-z0-9_-]{2,}',_norm(text))}

def _caption_has_name(target, name):
    # Exact identifier boundaries; FExp must not match FExpFast.
    return name in _names(target.line.text)

@dataclass(frozen=True)
class _Carrier:
    page: int
    bbox: tuple
    header: object
    targets: tuple
    name: str
    identity: tuple | None
    inside: str
    continued: bool
    scope: str

def _carriers(index, objects):
    pages={p.number:p for p in index.document.pages}
    scopes,_=_scope_map(index.document,_directory_keys(index.document)|toc_line_keys(index.document))
    observations={}
    for obj in objects:
        if obj.kind not in {'figure','table'} and not (obj.kind=='text' and obj.role in {'code_body','table_body'}):
            continue
        box=tuple(obj.bbox);page=pages.get(obj.page_number)
        if page is None or box[2]-box[0]<80 or box[3]-box[1]<50:
            continue
        if (box[2]-box[0])*(box[3]-box[1])>page.width*page.height*.85:
            continue
        observations[(obj.page_number,box)]=obj
    result=[]
    for (pn,box),obj in observations.items():
        page=pages[pn]
        rows=sorted([l for l in page.lines if _contained(l,box)],key=lambda l:(l.bbox[1],l.bbox[0]))
        if not rows:
            continue
        headers=[l for l in rows if l.bbox[1]-box[1]<=min(42,(box[3]-box[1])*.18)
                 and (_PROTOCOL.match(_norm(l.text)) or _FUNCTION.match(_norm(l.text)))]
        if len(headers)!=1:
            continue
        header=headers[0];pm=_PROTOCOL.match(_norm(header.text))
        if pm:
            identity=(pm.group(1),_name(pm.group(2)));name=identity[1]
        else:
            m=re.search(r'([A-Za-z][A-Za-z0-9_-]{2,})\s*$',_norm(header.text))
            if not m:
                continue
            name=_name(m.group(1));identity=None
        inside=' '.join(l.text for l in rows)
        if not re.search(r'输入|Input',inside,re.I) or not re.search(r'输出|Output',inside,re.I):
            continue
        targets=[]
        for t in index.figures:
            a=t.line.bbox
            if t.line.page_number!=pn or not _caption_has_name(t,name):
                continue
            if not re.search(r'协议|Protocol' if identity else r'理想函数|Ideal\s*Functionality',t.line.text,re.I):
                continue
            gap=a[1]-box[3]
            overlap=max(0,min(a[2],box[2])-max(a[0],box[0]))
            if not -3<=gap<=80 or overlap<min(a[2]-a[0],box[2]-box[0])*.5:
                continue
            # The caption cannot be reached through a competing caption or
            # substantive body paragraph between it and this carrier.
            bridge=[l for l in page.lines if l.bbox[1]>=box[3]+2 and l.bbox[3]<=a[1]-2]
            if any(FIGURE_CAPTION.search(_norm(l.text)) and
                   name not in _names(l.text) for l in bridge):
                continue
            if any(len(l.text)>35 and not FIGURE_CAPTION.search(_norm(l.text)) for l in bridge):
                continue
            targets.append(t)
        continued=bool(_CONTINUED.search(header.text) and
                       any(_CONTINUED.search(t.line.text) for t in targets))
        candidate=_Carrier(pn,box,header,tuple(targets),name,identity,inside,continued,scopes.get(_key(header),'body'))
        # Nested duplicate observations of one physical frame are one carrier.
        duplicate=next((c for c in result if c.page==pn and c.identity==identity and c.name==name
                        and _contained(header,c.bbox) and
                        (set(physical_target_key('figure',t) for t in c.targets)&
                         set(physical_target_key('figure',t) for t in targets) or
                         not c.targets and not targets and _contained(c.header,box))),None)
        if duplicate:
            if (box[2]-box[0])*(box[3]-box[1])>(duplicate.bbox[2]-duplicate.bbox[0])*(duplicate.bbox[3]-duplicate.bbox[1]):
                result.remove(duplicate);result.append(candidate)
        else:
            result.append(candidate)
    return result

def _prose(index,objects,carriers):
    pages={p.number:p for p in index.document.pages}
    directories=_directory_keys(index.document)|toc_line_keys(index.document)
    scopes,nonbody=_scope_map(index.document,directories)
    captions={_key(t.line) for t in index.figures+index.tables}
    regions=[(o.page_number,o.bbox) for o in objects if o.kind in {'figure','table'}
             or (o.kind=='text' and o.role in {'code_body','table_body'})]
    regions.extend((c.page,c.bbox) for c in carriers)
    result=[]
    for page in index.document.pages:
        current=[]
        def flush():
            if current:
                text=' '.join(l.text for l in current)
                box=(min(l.bbox[0] for l in current),min(l.bbox[1] for l in current),
                     max(l.bbox[2] for l in current),max(l.bbox[3] for l in current))
                result.append((replace(current[0],text=text,bbox=box),
                               scopes.get(_key(current[0]),'body'),tuple(current)))
                current.clear()
        for row in sorted(page.lines,key=lambda l:(l.bbox[1],l.bbox[0])):
            if row.bbox[1]<page.height*.10 or row.bbox[1]>page.height*.88:
                continue
            blocked=(_key(row) in captions or _key(row) in nonbody or _key(row) in directories
                     or any(pn==page.number and _contained(row,box) for pn,box in regions))
            if blocked or row.bold or re.match(r'^\s*\d+(?:\.\d+)+\s*$',row.text):
                flush();continue
            if not _is_body(row,captions,directories,pages):
                flush();continue
            if current and (row.bbox[1]-current[-1].bbox[3]>45 or
                            scopes.get(_key(row),'body')!=scopes.get(_key(current[0]),'body') or
                            sum(len(l.text) for l in current)+len(row.text)>1800):
                flush()
            current.append(row)
        flush()
    return result

def _foreign_source_at(text,start,end):
    """Reject an occurrence qualified as an external declaration, not nearby citations."""
    citation=r'\[[0-9,，;；\-– ]+\]'
    prefix=re.split(r'[。；;!?！？]',text[:start])[-1][-150:]
    suffix=text[end:end+150]
    if re.search(r'(?:文献|参考文献)?\s*'+citation+
                 r'\s*(?:中(?:所示|给出|定义|提出)?|的|所?(?:给出|提出|定义|描述)(?:的)?|中的)\s*$',prefix,re.I):
        return True
    if re.match(r'\s*[（(]\s*(?:引自|来自|摘自|改编自)(?:文献|参考文献)?\s*'+citation,suffix,re.I):
        return True
    return bool(re.match(r'\s*(?:from|in|introduced by|proposed by)\s+'
                         r'(?:[A-Za-z][A-Za-z .,&\-]{0,90}\s*)?'+citation,suffix,re.I))


def _local_contract_text(text):
    """Retain complete local math contracts; exclude source-owned descriptions."""
    source=re.compile(r'^\s*(?:文献|参考文献)\s*\[[0-9,，;；\-– ]+\]\s*'
                      r'(?:中(?:的|所示)?|给出|提出|定义|介绍|描述|采用)',re.I)
    sentences=re.split(r'(?<=[。])',text)
    result=[];foreign=False
    for sentence in sentences:
        if source.search(sentence) or re.search(
                r'[（(]\s*(?:引自|摘自|来自|改编自)\s*(?:文献|参考文献)?\s*'
                r'\[[0-9,，;；\-– ]+\]\s*[）)]\s*[。.\s]*$',sentence,re.I):
            foreign=True;continue
        if re.match(r'^\s*(?:本文|本节|我们|our\b|we\b)',sentence,re.I):
            foreign=False
        if not foreign:result.append(sentence)
    return ''.join(result)


def _comparison(text):
    c=_compact(text)
    return {m.groups() for m in re.finditer(
        r'([A-Za-zα-ωΓ])←\[([A-Za-zα-ωΓ])([<>≤≥=◦])([A-Za-zα-ωΓ])\]',c)}

def _comparison_compatible(text,inside):
    actual,declared=_comparison(text),_comparison(inside)
    if actual&declared:
        return True
    parameter=re.search(r'◦∈\{([<>≤≥=,]+)\}',_compact(inside))
    allowed=set(parameter.group(1))- {','} if parameter else set()
    return any((out,x,y)==(other,u,v) and predicate=='◦' and operation in allowed
               for out,x,operation,y in actual
               for other,u,predicate,v in declared)

def _selection(text):
    c=_compact(text).replace('·','*')
    return {m.group(0) for m in re.finditer(
        r'([A-Za-zα-ωΓ])←([A-Za-zα-ωΓ])\*([A-Za-zα-ωΓ])\+\(1-\2\)\*([A-Za-zα-ωΓ])',c)}

def _float_product(text):
    c=_compact(text).replace('·','*')
    return {m.group(0) for m in re.finditer(r'([α-ωΓ])←([α-ωΓ])\*([α-ωΓ])',c)}

def _component_fields(text):
    return set(re.findall(r'[sem][α-ωΓ]',_compact(text)))

def _contract_matches(text,carrier):
    inside=carrier.inside
    if carrier.identity is not None:
        return None
    # These are mathematical operation contracts, independent of the name
    # assigned by an author. Symbols, input domain and sharing output agree.
    if (_comparison_compatible(text,inside) and
        re.search(r'整数',text) and re.search(r'整数|Z2',_compact(inside)) and
        all(re.search(p,text) and re.search(p,inside) for p in (r'秘密|共享',r'布尔.*(?:分享|共享)',r'\{0,\s*1\}'))):
        return '秘密整数输入、相同比较公式/比特及布尔分享输出完整对应'
    if (_selection(text)&_selection(inside) and re.search(r'控制比特',text) and
        re.search(r'候选值',text) and re.search(r'输出',text) and
        re.search(r'秘密|共享|分享',text) and
        re.search(r'算术.*(?:分享|共享)|线性组合',text) and re.search(r'算术.*(?:分享|共享)',inside)):
        return '控制比特和两候选值、相同选择公式及分享输出完整对应'
    if (_float_product(text)&_float_product(inside) and '浮点' in text and
        re.search(r'尾数.*(?:规范化|规格化)',text) and
        len(_component_fields(text)&_component_fields(inside))>=4 and
        all(w in inside for w in ('输入','输出','符号','指数','尾数'))):
        return '相同浮点乘法输入/结果公式及至少四分量符号、尾数规范化对应'
    return None

def _continuation(previous,current):
    if not current.continued or current.page!=previous.page+1 or current.identity!=previous.identity:
        return False
    # Explicit continuation of the same declaration must cross the page edge,
    # with compatible frame widths. Mere same-name next-page diagrams remain
    # competing independent targets.
    width=previous.header.page_width;height=previous.header.page_height
    a,b=previous.bbox,current.bbox
    ratio=min(a[2]-a[0],b[2]-b[0])/max(a[2]-a[0],b[2]-b[0])
    return (a[3]>=height*.70 and b[1]<=height*.25 and ratio>=.80
            and abs((a[0]+a[2]-b[0]-b[2])/2)<=width*.08)

def _bind(out,carrier,line,scope,rows,criterion,events):
    for target in carrier.targets:
        before=set().union(*out.indirect_reference_targets.values()) if out.indirect_reference_targets else set()
        _add_indirect(out,'figure',target,line,scope,None,criterion)
        if events is not None and physical_target_key('figure',target) not in before:
            events.append({'action':'protocol_reference','number':target.number,'page':target.line.page_number,
                'bbox':list(target.line.bbox),'text':target.line.text,'criterion':criterion,
                'carrier_bbox':list(carrier.bbox),
                'declaration':{'page':carrier.header.page_number,'bbox':list(carrier.header.bbox),'text':carrier.header.text},
                'body_context':[{'page':l.page_number,'bbox':list(l.bbox),'text':l.text} for l in rows]})

def repair_protocol_references(index,layout_objects=(),*,evidence=None):
    """Return copied index with narrowly proved protocol/function uses added."""
    out=DocumentIndex(index.document,**{name:list(getattr(index,name)) for name in _LISTS})
    out.indirect_reference_targets={key:set(value) for key,value in getattr(index,'indirect_reference_targets',{}).items()}
    objects=tuple(layout_objects or ())
    carriers=_carriers(out,objects)
    if not carriers:
        return out
    prose=_prose(out,objects,carriers)
    # Exact protocol identities are unique physical entities, except a proved
    # explicitly continued chain of frames on consecutive original pages.
    identities={}
    for c in carriers:
        if c.identity is not None: identities.setdefault((c.scope,c.identity),[]).append(c)
    for (target_scope,identity),group in identities.items():
        group.sort(key=lambda c:(c.page,c.bbox[1]))
        if len(group)>1 and not all(_continuation(a,b) for a,b in zip(group,group[1:])):
            continue
        for line,scope,rows in prose:
            if scope!=target_scope:
                continue
            if any((m.group(1),_name(m.group(2)))==identity and not _foreign_source_at(_norm(line.text),m.start(),m.end())
                   for m in _PROTOCOL.finditer(_norm(line.text))):
                for carrier in group:
                    _bind(out,carrier,line,scope,rows,'正文精确协议编号及Π标识绑定唯一物理声明；续片须原页连续且框头/图题明确续',evidence)
    for line,scope,rows in prose:
        choices=[]
        for c in carriers:
            if c.identity is not None or c.scope!=scope :
                continue
            proof=_contract_matches(_local_contract_text(line.text),c)
            if proof:
                # A typed reference to a different physical figure is an
                # explicit competing owner of the alleged functional prose.
                numbers={re.sub(r'\s+','',m.group('number')) for m in FIGURE_REFERENCE.finditer(_norm(line.text))}
                if numbers and not numbers&{t.number for t in c.targets}:
                    continue
                choices.append((c,proof))
        if len(choices)==1:
            c,proof=choices[0]
            if abs(c.page-line.page_number)>1:
                continue
            if c.page==line.page_number+1 and c.bbox[1]>c.header.page_height*.25:
                continue
            _bind(out,c,line,scope,rows,proof+'，同范围无另一物理合同竞争',evidence)
    return out
