"""Independent native uses of named program/protocol representations.

This pure usage-only view requires an actual named physical representation and
its concrete operations. It does not equate an algorithm number to a figure,
accept topic names alone, read PDFs/OCR, or mutate parser/index facts.
"""
import re
import unicodedata
from .numbering import normalize_label
from .usage_scope import usage_scope_identity

_FIG=re.compile(r'(?:图|Figures?|Fig\.?)\s*([A-Z]?\d+(?:[.\-–]\d+)*)',re.I)
_ALGORITHM=re.compile(r'(?:算法|Algorithm)\s*(?P<number>\d+(?:[.\-–]\d+)*)',re.I)
_BAD_ROLES={'header','footer','toc','reference','figure_caption','table_caption','heading','equation','code'}
_DENIED=re.compile(r'(?:未|不|没有|无需)(?:采用|使用|实现|定义|讨论|解释|介绍|说明)|\b(?:not|never|without)\b',re.I)

def _text(value):
    value=re.sub(r'[\u2460-\u2473]','',value)
    return unicodedata.normalize('NFKC',value).casefold()

def _compact(value):return re.sub(r'\s+','',_text(value))
def _literal(name,text):return bool(re.search(r'(?<![a-z0-9_\-])'+re.escape(name)+r'(?![a-z0-9_\-])',_text(text)))
def _inside(a,b):return b[0]-.5<=a[0] and b[1]-.5<=a[1] and a[2]<=b[2]+.5 and a[3]<=b[3]+.5
def _field_inside(a,b):return b[0]-1<=a[0] and b[1]-.5<=a[1] and a[2]<=b[2]+1 and a[3]<=b[3]+.5
def _center(field,axis):return (field['bbox'][axis]+field['bbox'][axis+2])/2

def _covered_ink(row):
    """Keep original glyph offsets, including a zero-advance glyph between ink.

    Some PDF fonts print the i in Verifier with a zero-width extraction box.
    It is usable only with original positive-height ink, close neighbours and
    a horizontal native row; a missing offset is never filled in.
    """
    if (row.source!='native' or not row.font_size or row.font_size<=0
            or row.direction[0]<.9 or abs(row.direction[1])>.05):return set()
    covered=set();positive=[]
    for start,end,box in row.text_regions:
        if box[2]>box[0] and box[3]>box[1]:
            covered.update(range(start,end));positive.append((start,end,box))
    for start,end,box in row.text_regions:
        if end!=start+1 or box[2]!=box[0] or box[3]<=box[1]:continue
        before=[b for s,e,b in positive if e==start]
        after=[b for s,e,b in positive if s==end]
        if not before or not after:continue
        a,c=before[-1],after[0]
        if (abs(a[2]-box[0])<=row.font_size*.6 and abs(c[0]-box[0])<=row.font_size*.6
                and abs(a[1]-box[1])<=row.font_size*.2 and abs(c[1]-box[1])<=row.font_size*.2):covered.add(start)
    return covered

def _native_glyphs(row):
    covered=_covered_ink(row)
    return bool(covered) and all(i in covered for i,c in enumerate(row.text) if not c.isspace())

def _native_match(rows,pattern,compact=True):
    """Match only text whose exact original offsets have real native ink."""
    value=[];ink=[]
    for row in rows:
        covered=_covered_ink(row)
        for i,char in enumerate(row.text):
            text=_text(char)
            for c in text:
                if compact and c.isspace():continue
                value.append(c);ink.append(i in covered or c.isspace())
        if not compact:value.append(' ');ink.append(True)
    return any(all(ink[m.start():m.end()]) for m in re.finditer(pattern,''.join(value)))

def named_protocol_identity(title):
    """A printed object name and representation type, never a number alone."""
    text=_text(title)
    text=re.sub(r'^\s*(?:图|figure|fig\.?)\s*[a-z]?\d+(?:[.\-–]\d+)*\s*','',text)
    match=re.match(r'([a-z][a-z0-9_\-]{2,})\s*(?:的\s*)?(步函数|架构|协议)',text)
    if match:
        name,kind=match.groups()
        if kind=='协议' and not re.search(r'交互|流程|形式化',text):return None
        return name,{'步函数':'step','架构':'mapping','协议':'proof'}[kind]
    for pattern,kind in ((r'(?:the\s+)?step\s+function\s+of\s+([a-z][a-z0-9_\-]{2,})','step'),
                         (r'architecture\s+of\s+([a-z][a-z0-9_\-]{2,})','mapping'),
                         (r'([a-z][a-z0-9_\-]{2,})\s+protocol\s+(?:interaction|workflow|flow)','proof')):
        match=re.match(pattern,text)
        if match:return match.group(1),kind
    return None

def _step_layout(fields,name):
    calls={}
    for field in fields:
        match=re.fullmatch(r'([a-z][a-z0-9_]*)\(([a-z][a-z0-9_]*)\)',_compact(field['text']))
        if match:calls.setdefault(match.group(1),[]).append(field)
    if len(calls)!=2:return None
    symbols=sorted(calls,key=lambda symbol:sum(_center(f,0) for f in calls[symbol])/len(calls[symbol]))
    first,second=symbols;n=len(calls[first])
    if n<2 or len(calls[second])!=n:return None
    rows=sorted(calls[first],key=lambda f:_center(f,1));other=sorted(calls[second],key=lambda f:_center(f,1))
    if any(abs(_center(a,1)-_center(b,1))>3 or a['bbox'][2]>=b['bbox'][0] for a,b in zip(rows,other)):return None
    sums=sorted((f for f in fields if _compact(f['text']) in {'⊕','+'}),key=lambda f:_center(f,1))
    if len(sums)!=n or any(abs(_center(a,1)-_center(b,1))>3 for a,b in zip(rows,sums)):return None
    matrix=[f for f in fields if re.fullmatch(r'[a-z]',_compact(f['text'])) and other[0]['bbox'][2]<f['bbox'][0]<sums[0]['bbox'][0]]
    if len(matrix)!=1:return None
    indexed={}
    for field in fields:
        match=re.fullmatch(r'([a-z]+)([1-9]\d*)',_compact(field['text']))
        if match:indexed.setdefault(match.group(1),[]).append((int(match.group(2)),field))
    inputs=[];keys=[]
    for prefix,items in indexed.items():
        if sorted(i for i,f in items)!=list(range(1,n+1)):continue
        ordered=[f for i,f in sorted(items)]
        if all(f['bbox'][2]<rows[j]['bbox'][0] and abs(_center(f,1)-_center(rows[j],1))<3 for j,f in enumerate(ordered)):inputs.append((prefix,ordered))
        if all(f['bbox'][0]>matrix[0]['bbox'][2] and abs(_center(f,0)-_center(sums[j],0))<5 and 0<sums[j]['bbox'][1]-f['bbox'][3]<40 for j,f in enumerate(ordered)):keys.append((prefix,ordered))
    if len(inputs)!=len(keys) or len(inputs)!=1:return None
    claimed=[*rows,*other,*sums,matrix[0],*inputs[0][1],*keys[0][1]]
    if len(claimed)!=len(fields):return None
    return dict(name=name,kind='parallel_composed_step',lanes=n,input=inputs[0][0],
                inner=first,outer=second,matrix=_compact(matrix[0]['text']),key=keys[0][0],fields=fields)

def _mapping_layout(fields,name):
    physical=[f for f in fields if re.search(r'^physical\s+.+\s+chips?$|物理.*芯片',_text(f['text']))]
    vm=[f for f in fields if _compact(f['text']) in {'vm','虚拟机'}]
    hyper=[f for f in fields if _compact(f['text']) in {'hypervisor','虚拟机管理程序'}]
    owners=[f for f in fields if _literal(name,f['text']) and re.search(r'\bpin\b|引脚',_text(f['text']))]
    mapping=[f for f in fields if re.fullmatch(r'mapping|映射',_compact(f['text']))]
    if not all(len(items)==1 for items in (physical,vm,hyper,owners,mapping)):return None
    if not (_center(vm[0],1)<_center(hyper[0],1)<_center(physical[0],1)):return None
    if not (abs(_center(owners[0],0)-_center(mapping[0],0))<=5 and 0<=mapping[0]['bbox'][1]-owners[0]['bbox'][3]<=10):return None
    if not (_center(vm[0],1)-20<=_center(mapping[0],1)<=_center(hyper[0],1)+20):return None
    return dict(name=name,kind='virtual_physical_pin_mapping',fields=fields)

def _proof_layout(fields,name):
    names=[f for f in fields if _literal(name,f['text'])]
    prover=[f for f in fields if re.search(r'证明者|\bprover\b',_text(f['text']))]
    verifier=[f for f in fields if re.search(r'验证者|\bverifier\b',_text(f['text']))]
    generate=[f for f in fields if re.search(r'生成证明|generate.*proof',_text(f['text']))]
    checks=[f for f in fields if re.search(r'配对验证|pairing.*verif',_text(f['text']))]
    booleans=[f for f in fields if re.search(r'[a-z]\s*∈\s*\{\s*0\s*,\s*1\s*\}',_text(f['text']))]
    calls=[f for f in fields if re.search(r'←\s*[a-z][a-z0-9_]*\(',_text(f['text']))]
    if not all(len(items)==1 for items in (names,prover,verifier,generate,checks,booleans,calls)):return None
    if not (prover[0]['bbox'][2]<verifier[0]['bbox'][0] and abs(_center(prover[0],1)-_center(verifier[0],1))<5):return None
    if not (abs(_center(generate[0],0)-_center(prover[0],0))<25 and abs(_center(checks[0],0)-_center(verifier[0],0))<25 and abs(_center(booleans[0],0)-_center(verifier[0],0))<25):return None
    actor=re.search(r'\(([a-z][a-z0-9_]*),\s*([a-z][a-z0-9_]*)\)',_compact(prover[0]['text']))
    public=re.search(r'\(([a-z][a-z0-9_]*)\)',_compact(verifier[0]['text']))
    call=re.search(r'([a-z][a-z0-9_]*|π)←([a-z][a-z0-9_]*)\(([^)]+)\)',_compact(calls[0]['text']))
    boolean=re.search(r'([a-z])∈',_compact(booleans[0]['text']))
    if not actor or not public or not call or public.group(1)!=actor.group(1):return None
    if actor.group(1) not in call.group(3).split(',') or actor.group(2) not in call.group(3).split(','):return None
    return dict(name=name,kind='two_role_proof_protocol',public=actor.group(1),private=actor.group(2),proof=call.group(1),
                generate_function=call.group(2),result=boolean.group(1),fields=fields)

def _layout(title,fields):
    identity=named_protocol_identity(title)
    if identity is None:return None
    name,kind=identity
    return {'step':_step_layout,'mapping':_mapping_layout,'proof':_proof_layout}[kind](fields,name)

def named_protocol_native_candidate(title,fields):
    return _layout(title,[f for f in fields if f.get('source')=='native']) is not None

def _foreign_subject(text,name):
    subjects=re.findall(r'(?<![a-z0-9_\-])([a-z][a-z0-9_\-]{2,})\s*(?:的\s*(?:步函数|架构|协议)|(?:驱动|设备)?\s*(?:采用|使用|实现|维护|将|通过))',_text(text))
    return any(subject!=name for subject in subjects)

def _passages(context,target,passages):
    scopes=context.get('usage_scopes') or context.get('usage_scope_map')
    if scopes is None:return []
    state=usage_scope_identity(scopes,target)
    if state[0]!='body' or state[1]<0:return []
    areas=[a for regions in context['regions'].values() for a in regions]
    result=[]
    for rows,value in passages:
        if not rows or any(r.source!='native' or not _covered_ink(r) or r.role in _BAD_ROLES
                           or usage_scope_identity(scopes,r)!=state
                           or (r.page_number,r.bbox) in context.get('caption_keys',set())
                           or any(a['page_number']==r.page_number and _inside(r.bbox,a['bbox']) for a in areas) for r in rows):continue
        refs={normalize_label(m.group(1)) for m in _FIG.finditer(value)}
        if refs-{target.number} or _DENIED.search(value):continue
        result.append((rows,value))
    return result

def _step_rows(topology,passages):
    name=topology['name'];a=topology['input'];k=topology['key'];n=topology['lanes']
    pattern=(re.escape(topology['matrix'])+r'[·*]?'+re.escape(topology['outer'])+r'\('+re.escape(topology['inner'])+
             r'\('+re.escape(a)+r'\)\)(?:t)?\+'+re.escape(k))
    for rows,value in passages:
        compact=_compact(value)
        if not _literal(name,value) or _foreign_subject(value,name):continue
        if not _native_match(rows,re.escape(name)+r'(?:\[[^]]+\])?(?:的)?步函数[a-z][a-z0-9_]*\('+re.escape(a)+r'\)定义为'):continue
        if not _native_match(rows,pattern):continue
        if not all(_native_match(rows,r'(?<![a-z0-9])'+re.escape(k)+str(i)+r'(?![0-9])') for i in range(1,n+1)):continue
        return rows
    return []

def _mapping_rows(topology,passages):
    name=topology['name'];direction=[];device=[]
    for rows,value in passages:
        if not _literal(name,value) or _foreign_subject(value,name) or not all(_native_glyphs(r) for r in rows):continue
        compact=_compact(value)
        if re.search(r'虚拟引脚(?:编号)?(?:到|→).{0,8}物理引脚.{0,15}映射',compact):direction=rows
        if (re.search(r'每个.{0,40}设备.{0,12}对应.{0,15}独立.{0,15}虚拟.{0,10}芯片',compact)
                and re.search(r'维护.{0,15}虚拟引脚编号.{0,8}物理引脚.{0,15}映射',compact)):device=rows
    return list({(r.page_number,r.bbox,r.text):r for r in direction+device}.values()) if direction and device else []

def _algorithm_rows(context,target,topology,passages):
    name=topology['name'];scopes=context.get('usage_scopes') or context.get('usage_scope_map')
    state=usage_scope_identity(scopes,target);document=context.get('_document')
    if document is None:return []
    named=[rows for rows,value in passages if all(_native_glyphs(r) for r in rows) and _literal(name,value) and not _foreign_subject(value,name)
           and re.search(r'方案|协议|protocol|scheme',value,re.I) and re.search(r'证明|验证|proof|verif',value,re.I)]
    if not named:return []
    links=[]
    for rows,value in passages:
        if not all(_native_glyphs(r) for r in rows):continue
        if re.search(r'文献|参考文献|来源|\b(?:from|paper|reference)\b',value,re.I):continue
        for match in _ALGORITHM.finditer(value):
            if re.search(r'交互|流程|步骤|协议|interaction|workflow|protocol',value,re.I) and re.search(r'如|见|所示|shown|see',value,re.I):links.append((normalize_label(match.group('number')),rows))
    if not links:return []
    candidates=[]
    all_areas=[a for regions in context['regions'].values() for a in regions]
    for page in document.pages:
        if abs(page.number-target.line.page_number)>2:continue
        # A numbered algorithm row and its indented operation can use different
        # fonts. Group the same physical baseline before ordering left-to-right.
        bands=[]
        for row in sorted(page.lines,key=lambda r:(r.bbox[1]+r.bbox[3],r.bbox[0])):
            center=(row.bbox[1]+row.bbox[3])/2
            if bands and abs(center-bands[-1][0])<3:bands[-1][1].append(row)
            else:bands.append((center,[row]))
        ordered=[r for center,band in bands for r in sorted(band,key=lambda r:r.bbox[0])]
        for pos,header in enumerate(ordered):
            match=_ALGORITHM.match(header.text.strip())
            if (not match or not _literal(name,header.text) or usage_scope_identity(scopes,header)!=state
                    or header.source!='native' or not _native_glyphs(header) or header.role in _BAD_ROLES-{'heading','code'}
                    or any(a['page_number']==page.number and _inside(header.bbox,a['bbox']) for a in all_areas)):continue
            number=normalize_label(match.group('number'))
            own_links=[rows for num,rows in links if num==number]
            if not own_links:continue
            program=[];last=None
            for row in ordered[pos+1:]:
                if (row.source!='native' or not _native_glyphs(row) or usage_scope_identity(scopes,row)!=state
                        or row.role in _BAD_ROLES-{'code'} or row.bbox[0]<header.bbox[0]-15
                        or any(a['page_number']==page.number and _inside(row.bbox,a['bbox']) for a in all_areas)):break
                text=_text(row.text).strip()
                numbered=re.match(r'^\d+\s*[:：]',text)
                continuation=last is not None and abs(row.bbox[1]-last.bbox[1])<5 and re.match(r'^(?:return|end|[a-z][a-z0-9_]*\s*←)',text)
                if not numbered and not continuation:break
                program.append(row);last=row
            text=' '.join(_text(r.text) for r in program);compact=_compact(text)
            if _DENIED.search(text) or _foreign_subject(text,name):continue
            if {normalize_label(m.group(1)) for m in _FIG.finditer(text)}-{target.number}:continue
            prover=re.search(r'prover\s*input\s*:',text);verifier=re.search(r'verifier\s*input\s*:',text)
            stage=re.search(r'//\s*verifier',text)
            if not prover or not verifier or not stage or not prover.start()<verifier.start()<stage.start():continue
            prove=re.search(r'([a-z][a-z0-9_]*|π)\s*←\s*'+re.escape(topology['generate_function'])+r'\s*\(([^)]+)\)',text)
            verify=re.search(r'([a-z])\s*←\s*verify\s*\(([^)]+)\)',text)
            if not prove or not verify or not verifier.end()<prove.start()<stage.start()<verify.start():continue
            if not _literal(topology['private'],prove.group(2)) or not _literal(topology['public'],prove.group(2)):continue
            if _literal(topology['private'],verify.group(2)) or not _literal(topology['public'],verify.group(2)) or not _literal(topology['proof'],verify.group(2)):continue
            if verify.group(1)!=topology['result']:continue
            if not re.search(r'if'+re.escape(topology['result'])+r'=1then.*returnvalid.*else.*returninvalid.*endif',compact):continue
            if not _literal(topology['private'],text[prover.end():verifier.start()]):continue
            if re.search(r'隐私属性|private\s+(?:input|attribute)',text[verifier.end():prove.start()]):continue
            candidates.append((header,program,own_links[0]))
    if len(candidates)!=1:return []
    header,program,link=candidates[0]
    topology['independent_algorithm']=dict(number=_ALGORITHM.match(header.text.strip()).group('number'),page_number=header.page_number,
        title=header.text,heading_bbox=header.bbox,bbox=[min(r.bbox[0] for r in program),min(r.bbox[1] for r in program),max(r.bbox[2] for r in program),max(r.bbox[3] for r in program)])
    return list({(r.page_number,r.bbox,r.text):r for r in named[0]+link+[header]+program}.values())

def named_protocol_relation_proposals(context,groups,nearby,fields=None):
    """Return physical proposals; each proof includes separate original ink."""
    actual=context['native_fields'] if fields is None else fields;answer=[]
    for ordinal,areas in context['regions'].items():
        target=groups[ordinal][0]
        native=[f for f in actual.get(ordinal,[]) if f.get('source')=='native' and any(
                a['page_number']==f.get('page_number') and _field_inside(f['bbox'],a['bbox']) for a in areas)]
        topology=_layout(areas[0]['title'],native)
        if topology is None:continue
        passages=_passages(context,target,nearby(ordinal))
        kind=topology['kind']
        rows=(_step_rows(topology,passages) if kind=='parallel_composed_step' else
              _mapping_rows(topology,passages) if kind=='virtual_physical_pin_mapping' else
              _algorithm_rows(context,target,topology,passages))
        if rows:answer.append((ordinal,'named_'+kind,rows,topology))
    # Equal concrete body ink cannot select two independent physical objects.
    return [entry for entry in answer if not any(other[0]!=entry[0] and other[1]==entry[1]
            and {(r.page_number,r.bbox,r.text) for r in entry[2]}&{(r.page_number,r.bbox,r.text) for r in other[2]} for other in answer)]
