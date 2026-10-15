"""Bind numbered protocol/functionality uses to actual formal figure boxes.

This is a rule 15 usage view. It never changes the shared parser or invents a
reference number from related content. Caption type and native boxed header
must agree, and the physical target must be unique within the body epoch.
"""
import re

from .usage_text_cache import normalize_text

_USE = re.compile(r'(?P<kind>协议|功能|(?<![A-Za-z0-9_/\\.\-])(?:protocol|functionality))\s*(?P<number>[0-9]+(?:\s*[.\-]\s*[0-9]+)*)(?![0-9.\-A-Za-z_/\\])',re.I)
_TYPES = {'协议':'protocol','protocol':'protocol','功能':'functionality','functionality':'functionality'}
_HEADER = re.compile(r'^(protocol|functionality)\s+\S',re.I)
_NONBODY_ROLES = {'header','footer','figure_caption','table_caption','heading','toc','reference','equation'}


def _inside(a,b):
    return b[0]-.5<=a[0] and b[1]-.5<=a[1] and a[2]<=b[2]+.5 and a[3]<=b[3]+.5


def _overlaps(a,b):
    return max(a[0],b[0])<min(a[2],b[2]) and max(a[1],b[1])<min(a[3],b[3])


def _rounded_rect(drawing):
    """Recognize an actual closed four-sided path with short rounded corners."""
    items=drawing.get('items',[])
    if len(items)!=8 or sorted(item[0] for item in items)!=['c']*4+['l']*4:return None
    b=tuple(drawing['rect']);left,top,right,bottom=b
    width=right-left;height=bottom-top
    if width<30 or height<15:return None
    near=lambda a,z:abs(a-z)<=.12
    equal=lambda a,z:near(a.x,z.x) and near(a.y,z.y)
    edges=set();corners=set()
    for i,item in enumerate(items):
        start=item[1];end=item[-1]
        if not equal(end,items[(i+1)%len(items)][1]):return None
        if item[0]=='l':
            if near(start.x,end.x):
                edge='left' if near(start.x,left) else 'right' if near(start.x,right) else None
                if abs(start.y-end.y)<height*.45:return None
            elif near(start.y,end.y):
                edge='top' if near(start.y,top) else 'bottom' if near(start.y,bottom) else None
                if abs(start.x-end.x)<width*.45:return None
            else:return None
            if edge is None or edge in edges:return None
            edges.add(edge)
        else:
            _,start,first,second,end=item
            candidates=[]
            for x in (left,right):
                for y in (top,bottom):
                    radius=min(15.,width*.25,height*.25)
                    if not all(left-.12<=p.x<=right+.12 and top-.12<=p.y<=bottom+.12
                               and abs(p.x-x)<=radius+.12 and abs(p.y-y)<=radius+.12
                               for p in (start,first,second,end)):continue
                    # Cubic controls must retain the original axis-aligned
                    # tangent on each of the two adjacent straight sides.
                    vertical=(near(start.x,x) and near(first.x,x) and near(end.y,y) and near(second.y,y))
                    horizontal=(near(start.y,y) and near(first.y,y) and near(end.x,x) and near(second.x,x))
                    if (vertical or horizontal) and abs(start.x-end.x)>.15 and abs(start.y-end.y)>.15:
                        candidates.append((x,y))
            if len(candidates)!=1 or candidates[0] in corners:return None
            corners.add(candidates[0])
    return b if len(edges)==len(corners)==4 else None


def _frames(document,numbers):
    """Closed original vector rectangles, including four thin border strokes."""
    answer={p.number:list(p.graphics) for p in document.pages if p.number in numbers}
    try:
        import pymupdf
        with pymupdf.open(document.path) as pdf:
            for number in numbers:
                if not 1<=number<=len(pdf):continue
                horizontal=[];vertical=[];closed=[];rounded=[]
                for drawing in pdf[number-1].get_drawings():
                    if (b:=_rounded_rect(drawing)) is not None:
                        rounded.append((b,drawing.get('fill')))
                    for item in drawing.get('items',[]):
                        if item[0]=='re':
                            b=tuple(item[1]);w=b[2]-b[0];h=b[3]-b[1]
                            if w>=30 and h>=15:closed.append(b)
                            elif w>=30 and 0<=h<=1.2:horizontal.append((b[0],b[2],(b[1]+b[3])/2))
                            elif h>=15 and 0<=w<=1.2:vertical.append(((b[0]+b[2])/2,b[1],b[3]))
                        elif item[0]=='l':
                            a,b=item[1:3]
                            if abs(a.y-b.y)<=.1 and abs(a.x-b.x)>=30:horizontal.append((min(a.x,b.x),max(a.x,b.x),(a.y+b.y)/2))
                            if abs(a.x-b.x)<=.1 and abs(a.y-b.y)>=15:vertical.append(((a.x+b.x)/2,min(a.y,b.y),max(a.y,b.y)))
                for left,top,bottom in vertical:
                    for right,ot,ob in vertical:
                        if right-left<30 or abs(top-ot)>.8 or abs(bottom-ob)>.8:continue
                        if all(any(abs(hx-left)<=.8 and abs(ex-right)<=.8 and abs(y-edge)<=.8
                                   for hx,ex,y in horizontal) for edge in (top,bottom)):
                            closed.append((left,top,right,bottom))
                # A dark outer fill and a white inset paint a single border.
                # Collapse only this demonstrated thin inset, not distinct
                # nested diagrams or arbitrary adjacent rectangles.
                for b,fill in rounded:
                    inset=(fill is not None and all(v>=.98 for v in fill) and
                           any(outer_fill is not None and all(v<=.02 for v in outer_fill) and
                               all(.05<=delta<=2 for delta in
                                   (b[0]-outer[0],b[1]-outer[1],outer[2]-b[2],outer[3]-b[3]))
                               for outer,outer_fill in rounded))
                    if not inset:closed.append(b)
                answer[number]=list({tuple(round(v,3) for v in b):b for b in closed}.values())
    except (OSError,RuntimeError,ValueError,ImportError):
        pass
    return answer


def inline_alias_fragments(index,eligible,pages,fonts,protected,directories,zone):
    """Keep actual wrapped short native reference ink beside body prose."""
    from .usage_reference_evidence import _body_style
    from .bibliography_scope_resume import _native_glyphs
    if not any(any(word in t.line.text for word in ('协议','功能','Protocol','Functionality')) for t in index.figures):return []
    known={(row.page_number,row.bbox) for row,state in eligible}
    proposals=[]
    for row in index.lines:
        key=(row.page_number,row.bbox)
        if key in known or key in protected or key in directories or row.role in _NONBODY_ROLES:continue
        if not _body_style(row,fonts[row.page_number]) or not _native_glyphs(row):continue
        text=normalize_text(row.text).strip()
        typed=_USE.fullmatch(text.rstrip('。.;；'))
        bare=re.fullmatch(r'[0-9]+(?:\s*[.\-]\s*[0-9]+)*[。.;；]?',text)
        if not typed and not bare:continue
        previous=[old for old,state in eligible if old.page_number==row.page_number and state==zone(row)
                  and old.role not in _NONBODY_ROLES and not old.text.rstrip().endswith(('。','；',';'))
                  and 0<=row.bbox[1]-old.bbox[3]<=fonts[row.page_number]*1.75
                  and abs(old.bbox[0]-row.bbox[0])<=fonts[row.page_number]*3]
        if not previous:continue
        if bare and not any(re.search(r'(?:协议|功能|protocol|functionality)\s*$',old.text,re.I) for old in previous):continue
        proposals.append((row,zone(row)))
    frames=_frames(index.document,{row.page_number for row,state in proposals}) if proposals else {}
    return [(row,state) for row,state in proposals if not any(_inside(row.bbox,b) for b in frames.get(row.page_number,[]))]


def formal_alias_references(index,groups,paragraphs,zone):
    """Yield exact native references and their independently owned figure."""
    from .reference_identity_repair import _label,_external
    from .reference_context import local_reference
    from .usage_paragraphs import span_anchor
    uses=[]
    for line,(scope,epoch) in paragraphs:
        if scope!='body' or line.role in _NONBODY_ROLES or line.source!='native':continue
        # Paragraph offsets and native glyph rectangles share this exact
        # normalization. The reference itself may wrap into a boxed row.
        text=normalize_text(line.text)
        for match in _USE.finditer(text):
            if not local_reference(text,match):continue
            reference=_label(match.group('number'),span_anchor(line,match.start(),match.end()),scope)
            substituted=text[:match.start()]+'图 '+reference.number+text[match.end():]
            if _external(substituted,'figure',reference.number):continue
            ink=[box for start,end,box in line.text_regions if start<match.end() and end>match.start()]
            uses.append((reference,_TYPES[match.group('kind').lower()],(scope,epoch),ink or [reference.line.bbox]))
    if not uses:return
    declared={}
    for ordinal,group in enumerate(groups):
        title=' '.join(normalize_text(t.line.text) for t in group)
        kinds={canonical for token,canonical in _TYPES.items() if
               (token in title if not token.isascii() else re.search(r'\b'+token+r'\b',title,re.I))}
        if kinds and any(any(t.number==ref.number and zone(t.line)==state for t in group) for ref,kind,state,ink in uses):declared[ordinal]=kinds
    if not declared:return
    pages={p.number:p for p in index.document.pages}
    frames=_frames(index.document,{groups[i][0].line.page_number for i in declared}|{ref.line.page_number for ref,kind,state,ink in uses})
    formal={}
    for ordinal,kinds in declared.items():
        group=groups[ordinal];caption=group[0].line;page=pages[caption.page_number]
        owned=[b for b in frames.get(page.number,[]) if 0<=caption.bbox[1]-b[3]<=35 and
               b[0]<=(caption.bbox[0]+caption.bbox[2])/2<=b[2]]
        if len(owned)!=1:continue
        b=owned[0]
        headers={m.group(1).lower() for row in page.lines if row.source=='native' and _inside(row.bbox,b)
                 and 0<=row.bbox[1]-b[1]<=35 and abs((row.bbox[0]+row.bbox[2]-b[0]-b[2])/2)<=35
                 and (m:=_HEADER.match(normalize_text(row.text).strip()))}
        if len(headers)==1 and headers<=kinds:formal[ordinal]=next(iter(headers))
    if not formal:return
    for reference,kind,state,ink in uses:
        if any(_overlaps(box,b) for box in ink for b in frames.get(reference.line.page_number,[])):continue
        candidates=[group for ordinal,group in enumerate(groups) if ordinal in formal and formal[ordinal]==kind and
                    any(t.number==reference.number and zone(t.line)==state for t in group)]
        numbered=[group for group in groups if any(t.number==reference.number and zone(t.line)==state for t in group)]
        if len(candidates)==len(numbered)==1:yield reference,candidates[0]


def _formal_symbol_operation(text,match):
    before=re.split(r'[。；;]',text[:match.start()])[-1][-85:]
    after=re.split(r'[。；;]',text[match.end():])[0][:65]
    verbs=r'(?:调用|使用|利用|实现|仿真|模拟)'
    tail=r'\s*(?:(?:该|理想)?功能)?\s*$'
    if re.search(r'(?:不|未|没有|未曾|无需|无须|不必|不需要).{0,5}'+verbs+tail,before):return False
    if re.search(r"\b(?:not|never|cannot|can't|don't|doesn't|didn't|won't|no\s+longer)\b[^.;。；]{0,60}$",before,re.I):return False
    if re.match(r'\s*被.{0,4}(?:禁止|阻止|不允许|禁用)',after):return False
    if re.search(verbs+tail,before):return True
    if re.search(r'\b(?:calls?|invokes?|implements?|realizes?|simulates?)\s+(?:the\s+)?(?:ideal\s+)?(?:functionality\s+)?$',before,re.I):return True
    if re.match(r'\s*(?:允许|接收|处理|计算|返回|被.{0,6}(?:调用|实现|仿真))',after):return True
    return bool(re.match(r'[\s)）\]},，-]*(?:F[A-Za-z0-9_-]+[\s)）\]},，-]*)*(?:混合模型|hybrid\s+model)',after,re.I))


def _formal_symbol_body_rows(index,definitions,frames,paragraphs,zone):
    """Recover larger body ink when smaller formal definitions dominate a page."""
    from .caption_context import body_font
    from .bibliography_scope_resume import _native_glyphs
    from .usage_paragraphs import usage_paragraphs
    pages={p.number:p for p in index.document.pages}
    numbers={group[0].line.page_number for values in definitions.values() for group in values}
    captions={(t.line.page_number,t.line.bbox) for t in index.figures+index.tables}
    extra=[]
    for number in numbers:
        page=pages[number];base=body_font(page)
        neighbors=[body_font(pages[n]) for n in (number-2,number-1,number+1,number+2) if n in pages]
        def eligible(row):
            return (row.source=='native' and _native_glyphs(row) and not row.bold and row.font_size
                    and row.font_size>base*1.06 and abs(row.direction[1])<.05
                    and row.role not in _NONBODY_ROLES and zone(row)[0]=='body'
                    and (row.page_number,row.bbox) not in captions
                    and page.height*.10<row.bbox[1]<page.height*.94
                    and len(re.findall(r'[A-Za-z\u4e00-\u9fff]',row.text))>=15
                    and row.bbox[2]-row.bbox[0]>=page.width*.35
                    and sum(abs(font-row.font_size)<.2 for font in neighbors)>=2
                    and not any(_overlaps(row.bbox,b) for b in (*frames.get(number,[]),*page.images,*page.tables)))
        rows=[row for row in page.lines if eligible(row)]
        for row in rows:
            if any(old.page_number==row.page_number and _inside(row.bbox,old.bbox) for old,state in paragraphs):continue
            if any(other is not row and abs(other.font_size-row.font_size)<.2
                   and min(abs(row.bbox[1]-other.bbox[3]),abs(other.bbox[1]-row.bbox[3]))<=row.font_size*1.5
                   for other in rows):extra.append((row,zone(row)))
    return [*paragraphs,*usage_paragraphs(sorted(extra,key=lambda pair:(pair[0].page_number,pair[0].bbox[1],pair[0].bbox[0])),index.document)]


def formal_symbol_references(index,groups,paragraphs,zone):
    """Bind independent uses of a unique named ideal-functionality definition."""
    from .reference_identity_repair import _label,_external
    from .usage_paragraphs import span_anchor
    header=re.compile(r'^(?:Functionality\s+|理想功能\s*[:：]\s*)(F[A-Za-z][A-Za-z0-9_]*(?:-[A-Za-z0-9_]+)*)\s*(?:[(\[{]|$)')
    pages={p.number:p for p in index.document.pages}
    candidates=[(ordinal,group) for ordinal,group in enumerate(groups)
                if any(word in normalize_text(' '.join(t.line.text for t in group)).lower()
                       for word in ('功能','functionality'))]
    if not candidates:return
    if not any(header.match(normalize_text(row.text).strip()) for ordinal,group in candidates
               for row in pages[group[0].line.page_number].lines):return
    frames=_frames(index.document,{g[0].line.page_number for ordinal,g in candidates})
    definitions={}
    for ordinal,group in candidates:
        caption=group[0].line;page=pages[caption.page_number]
        owned=[b for b in frames.get(page.number,[]) if 0<=caption.bbox[1]-b[3]<=35 and
               b[0]<=(caption.bbox[0]+caption.bbox[2])/2<=b[2]]
        if len(owned)!=1:continue
        b=owned[0]
        names=set()
        title=normalize_text(' '.join(t.line.text for t in group))
        for row in page.lines:
            if row.source!='native':continue
            text=normalize_text(row.text).strip();match=header.match(text)
            if not match:continue
            if text.startswith('理想功能') and '理想功能' not in title:continue
            centered=(_inside(row.bbox,b) and 0<=row.bbox[1]-b[1]<=35 and
                      abs((row.bbox[0]+row.bbox[2]-b[0]-b[2])/2)<=35)
            attached=any(_inside(row.bbox,tab) and b[0]<=tab[0]<tab[2]<=b[2]
                         and tab[1]<b[1]<tab[3]<=b[1]+12
                         and tab[3]-tab[1]<=40 and tab[2]-tab[0]<(b[2]-b[0])*.8
                         for tab in frames.get(page.number,[]) if tab!=b)
            if centered or attached:names.add(match.group(1).replace('_',''))
        if len(names)==1:
            key=(next(iter(names)),zone(caption))
            definitions.setdefault(key,[]).append(group)
    physical_counts={}
    for (name,state),targets in definitions.items():
        key=(name.casefold(),state)
        physical_counts[key]=physical_counts.get(key,0)+len(targets)
    patterns={name:re.compile(r'(?<![A-Za-z0-9_/\\.])'+r'[\s_]*'.join(re.escape(c) for c in name)+r'(?![A-Za-z0-9_\-./\\])')
              for name,state in definitions}
    uses=[]
    for row,state in _formal_symbol_body_rows(index,definitions,frames,paragraphs,zone):
        if state[0]!='body' or row.role in _NONBODY_ROLES or row.source!='native':continue
        text=normalize_text(row.text)
        for name,pattern in patterns.items():
            targets=definitions.get((name,state),[])
            if len(targets)!=1 or physical_counts.get((name.casefold(),state))!=1:continue
            group=targets[0]
            for match in pattern.finditer(text):
                if not _formal_symbol_operation(text,match):continue
                reference=_label(group[0].number,span_anchor(row,match.start(),match.end()),state[0])
                substituted=text[:match.start()]+'图 '+reference.number+text[match.end():]
                if _external(substituted,'figure',reference.number):continue
                ink=[box for start,end,box in row.text_regions if start<match.end() and end>match.start()]
                uses.append((reference,group,ink or [reference.line.bbox]))
    if not uses:return
    frames.update(_frames(index.document,{r.line.page_number for r,g,ink in uses}-set(frames)))
    for reference,group,ink in uses:
        if not any(_overlaps(box,b) for box in ink for b in frames.get(reference.line.page_number,[])):
            yield reference,group
