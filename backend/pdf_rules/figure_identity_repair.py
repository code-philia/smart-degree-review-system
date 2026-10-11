"""Resolve declared figure identities without turning unknown figures into text.

The caller supplies already recovered layout objects. Only positive evidence
changes an object's kind: inline body placement, a textual declaration, or a
caption that owns a physical composite. Missing captions are never exemptions.
"""
from dataclasses import replace
from pathlib import Path
import re
import unicodedata

from .mineru_layout import LayoutObject
from .numbering import normalize_text

_PANEL = re.compile(r'^\s*[（(]([a-z])[）)](?:\s|$)', re.I)
_NUMBERED_PANEL = re.compile(r'^\s*[（(]([a-z])([1-9][0-9]?)[）)](?:\s|$)', re.I)
_CAPTION = re.compile(r'^\s*(?:图|表|Figure|Fig\.?|Table)\s*[A-Z]?\d', re.I)
_FIGURE_REF = re.compile(r'(?:图|Figure|Fig\.?)\s*[A-Z]?\d+(?:[.\-]\d+)+', re.I)
_TEXT_DECLARATION = re.compile(r'提示(?:词|模板|工程)|(?:模板|指令|格式|内容|视角).{0,16}(?:如下|以下)|(?:设计|整理|给出).{0,10}以下.{0,10}(?:视角|提示|内容)|Provide a response|(?:仿真|模拟).{0,12}(?:内容|案例|示例)|(?:prompt|instruction)\s+(?:template|below)|(?:Listing|代码)\s*[A-Z]?\d', re.I)
_PROMPT_CONTENT = re.compile(r'\b(?:prompt|instruction|you are|your task|step [1-4]|JSON|summary|custom itinerary|stamina|aspect [IVX]+)\b|^\s*(?:def |if |for |return |class )', re.I)


def _area(b):
    return max(0,b[2]-b[0])*max(0,b[3]-b[1])


def _intersection(a,b):
    return (max(a[0],b[0]),max(a[1],b[1]),min(a[2],b[2]),min(a[3],b[3]))


def _inside(a,b):
    return _area(_intersection(a,b))/max(_area(a),1e-9)


def _union(boxes):
    return (min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes))


def _xover(a,b):
    return max(0,min(a[2],b[2])-max(a[0],b[0]))/max(1,min(a[2]-a[0],b[2]-b[0]))


def _gap(a,b):
    return max(a[1]-b[3],b[1]-a[3],0)


def _native(obj):
    return not obj.source_id and (obj.role.startswith('native_') or obj.role in {'continuous_chart_panels','shared_axis_panels'})


def _body_line(line):
    text=normalize_text(line.text).strip()
    return not _CAPTION.match(text) and not _PANEL.match(text) and (
        len(re.findall(r'[\u4e00-\u9fff]',text))>=14 or len(re.findall(r'[A-Za-z]',text))>=65)


def _text_evidence(obj,page,document):
    box=obj.bbox; width=box[2]-box[0];height=box[3]-box[1]
    overlap=[l for l in page.lines if _area(_intersection(l.bbox,box))>0]
    body=[l for l in overlap if _body_line(l) and _xover(l.bbox,box)>.2
          and l.bbox[2]-l.bbox[0]>width*1.7]
    # An inline mathematical bitmap or a PDF glyph carrier is located within
    # native paragraph lines whose actual text extends outside its carrier.
    inline=[l for l in overlap if len(l.text.strip())>=15 and _xover(l.bbox,box)>.75
            and l.bbox[2]-l.bbox[0]>width*2 and abs((l.bbox[1]+l.bbox[3]-box[1]-box[3])/2)<14]
    glyphs=[b for l in inline for a,z,b in l.text_regions if 0<z-a<=2 and l.text[a:z].strip()]
    if height<=36 and width<page.width*.3 and any(_inside(box,b)>.8 for b in glyphs):
        return 'inline_body_carrier'
    headings=[l for l in page.lines if re.match(r'^\s*(?:算法|Algorithm)\s*\d',normalize_text(l.text),re.I)]
    if _native(obj) and width<=40 and height<=40 and any(_gap(box,l.bbox)<15
           and max(box[0]-l.bbox[2],l.bbox[0]-box[2],0)<30
           and any(re.match(r'\s*(?:Data:|Result:|Input:|Output:)',n.text,re.I)
                   and 0<n.bbox[1]-l.bbox[3]<55 for n in page.lines) for l in headings):
        return 'algorithm_text_carrier'
    inner=[l for l in page.lines if _inside(l.bbox,box)>=.7 and l.text.strip()]
    math=' '.join(l.text for l in inner)
    equation_number=any(re.fullmatch(r'\s*[（(]\d+(?:[.\-]\d+)+[）)]\s*',l.text)
                        and abs((l.bbox[1]+l.bbox[3]-box[1]-box[3])/2)<18
                        and l.bbox[0]>=box[2]-8 for l in page.lines)
    if height<65 and equation_number and re.search(r'[=∈∑∫∀→⊙|]',math):
        return 'numbered_expression'
    if len(inner)<4:
        return None
    context=[l for l in page.lines if (box[1]-125<=l.bbox[1]<box[1]
             or box[3]<l.bbox[1]<=box[3]+90) and not _CAPTION.match(normalize_text(l.text))]
    previous=next((p for p in document.pages if p.number==page.number-1),None)
    separate_template_intro=False
    if previous:
        substantive=[l for l in previous.lines if l.bbox[1]>previous.height*.14
                     and l.bbox[3]<previous.height*.88 and len(l.text.strip())>8]
        preceding=sorted(substantive,key=lambda l:l.bbox[1])
        endings=sorted([l for l in previous.lines if l.bbox[1]>previous.height*.14
                        and l.bbox[3]<previous.height*.88 and l.text.strip()],key=lambda l:l.bbox[1])
        intro=''.join(l.text for l in endings[-2:])
        separate_template_intro=bool(re.search(r'提示(?:词|模板).{0,20}(?:如下|以下)[：:]?\s*$',intro)
                                     and not _FIGURE_REF.search(intro))
        context=preceding[-12:]+context
    declarations=' '.join(l.text for l in context)
    # A body reference explicitly presents the screenshot as an academic
    # figure; text density or prompt words cannot erase its title obligation.
    content=unicodedata.normalize('NFKC',' '.join(l.text for l in inner))
    if (separate_template_intro and re.match(r'\s*(?:Prompt\s+for|提示模板|提示词)',inner[0].text,re.I)
            and _PROMPT_CONTENT.search(content) and not any(_FIGURE_REF.search(l.text) for l in context if l.page_number==page.number)):
        return 'separately_declared_prompt_template'
    if _FIGURE_REF.search(declarations):
        return None
    content=unicodedata.normalize('NFKC',' '.join(l.text for l in inner))
    if (re.search(r'(?:以下|下面|如下).{0,12}交换图|交换图.{0,8}成立|commutative diagram',declarations,re.I)
            and not re.search(r'[\u4e00-\u9fff]',content)
            and len(re.findall(r'[α-ωΑ-Ω]',content))>=2
            and not re.search(r'\b[A-Za-z]{14,}\b',content)):
        return 'mathematical_mapping_expression'
    if (re.search(r'(?:代码|Listing|Code)\s*[A-Z]?[.\-]?\d',declarations,re.I)
            and re.search(r'self\.|\breturn\b|\bdef\s+|\w+\.\w+\(|Dict\[',content)):
        return 'declared_code_listing'
    if _TEXT_DECLARATION.search(declarations) and _PROMPT_CONTENT.search(content):
        return 'declared_text_block'
    return None


def _blank_carrier(obj,pdf):
    if pdf is None or not _native(obj) or _area(obj.bbox)>obj.page_width*obj.page_height*.08:
        return False
    try:
        import pymupdf
        page=pdf[obj.page_number-1]
        clip=pymupdf.Rect(obj.bbox)*page.rotation_matrix
        pix=page.get_pixmap(matrix=pymupdf.Matrix(1,1),clip=clip,colorspace=pymupdf.csGRAY,alpha=False)
        return bool(pix.samples) and all(v==255 for v in pix.samples)
    except (ValueError,IndexError):
        return False



def _native_glyph_carrier(obj,page,pdf):
    if not _native(obj) or _area(obj.bbox)>page.width*page.height*.06:return False
    lines=[l for l in page.lines if (_body_line(l) or len(l.text)>15 and l.bbox[2]-l.bbox[0]>page.width*.45)
           and _area(_intersection(l.bbox,obj.bbox))>0]
    direct=bool(lines)
    if not lines:
        # Native MathType fragments can occupy a gap between separately
        # encoded prose spans, or form part of a numbered display equation.
        # The same complete source-pixel/glyph proof still applies below.
        equation=any(re.fullmatch(r'\s*[（(]\d+(?:[.\-]\d+)+[）)]\s*',l.text)
                     and abs((l.bbox[1]+l.bbox[3]-obj.bbox[1]-obj.bbox[3])/2)<22
                     for l in page.lines)
        prose=any(_body_line(l) and _gap(l.bbox,obj.bbox)<5
                  and max(l.bbox[0]-obj.bbox[2],obj.bbox[0]-l.bbox[2],0)<25
                  for l in page.lines)
        if not equation and not prose:return False
        lines=[l for l in page.lines if l.source=='native'
               and _area(_intersection(l.bbox,obj.bbox))>0]
        if not lines:return False
    # A carrier can straddle a short native heading and its full paragraph.
    # Include original native glyph boxes, then still require every ink pixel
    # to be owned by those characters; diagram strokes remain outside.
    lines += [l for l in page.lines if l.source=='native' and l not in lines
              and _area(_intersection(l.bbox,obj.bbox))>0]
    regions=[b for l in lines for a,z,b in l.text_regions if 0<z-a<=2 and l.text[a:z].strip()]
    if not regions:return False
    if direct and any(_inside(obj.bbox,b)>.95 for b in regions):return True
    if pdf is None:return False
    try:
        import pymupdf
        source=pdf[obj.page_number-1]
        clip=pymupdf.Rect(obj.bbox)*source.rotation_matrix
        pix=source.get_pixmap(matrix=pymupdf.Matrix(2,2),clip=clip,colorspace=pymupdf.csGRAY,alpha=False)
        physical=[pymupdf.Rect(b)*source.rotation_matrix for b in regions]
        ink=outside=0; samples=pix.samples
        for y in range(pix.height):
            for x in range(pix.width):
                if samples[y*pix.width+x]==255:continue
                ink+=1;px=(pix.x+x+.5)/2;py=(pix.y+y+.5)/2
                if not any(b.x0-1<=px<=b.x1+1 and b.y0-1<=py<=b.y1+1 for b in physical):outside+=1
        return ink>0 and outside<=ink*.002
    except (ValueError,IndexError):return False


def _inline_source_carrier(obj,page,pdf):
    """An atomic source symbol placed in a native paragraph's actual gap."""
    if pdf is None or not _native(obj):return False
    b=obj.bbox;w=b[2]-b[0];h=b[3]-b[1]
    if w>page.width*.25 or h>36:return False
    row=[l for l in page.lines if l.source=='native' and not _CAPTION.match(normalize_text(l.text))
         and not _PANEL.match(normalize_text(l.text)) and l.text.strip()
         and abs((l.bbox[1]+l.bbox[3]-b[1]-b[3])/2)<=max(6,h*.6)]
    left=[l for l in row if -2<=b[0]-l.bbox[2]<=6]
    right=[l for l in row if -2<=l.bbox[0]-b[2]<=6]
    paragraph=bool(left and right and any(_body_line(l) for l in left+right))
    # A native mathematical expression can encode one operator as paint while
    # the two neighbouring terms are text. This is bounded to one glyph cell.
    math_gap=(left and right and w<=12 and h<=20
              and any(re.search(r'[=∈∑∫∀→⊙]',l.text) for l in left+right)
              and all(not re.search(r'[\u4e00-\u9fff]',l.text) for l in left+right))
    if math_gap:return True
    from .caption_physical_ownership import _PageInk
    ink=_PageInk(pdf,obj.page_number)
    try:
        forms=[r for r in ink.page.get_xobjects() if r[2]==0]
        if len(forms)>32:return False
        for xref,name,parent,scope in forms:
            owner=ink.removal({name})
            if owner is None or not ink.owns(obj,owner):continue
            scope=owner['box']
            native=[l for l in page.lines if l.source=='native' and l.text_regions
                    and _inside(l.bbox,scope)>.6]
            math=' '.join(l.text for l in native)
            formula=(scope[2]-scope[0]<page.width*.25 and scope[3]-scope[1]<=36
                     and len(native)>=3 and re.search(r'[=∈∑∫∀→⊙]',math)
                     and len(re.findall(r'[A-Za-zα-ωΑ-Ω]',math))>=3
                     and not re.search(r'[\u4e00-\u9fff]',math))
            variable_intro=any(re.match(r'\s*[A-Za-zα-ωΑ-Ω]{1,3}\s*(?:为|表示|是)',l.text)
                    and abs(l.bbox[0]-scope[0])<=12 and _gap(l.bbox,scope)<3
                    for l in page.lines)
            if formula or variable_intro and scope[2]-scope[0]<=20 and scope[3]-scope[1]<=24:return True
            if (paragraph and scope[2]-scope[0]<=max(20,w*1.6) and scope[3]-scope[1]<=max(20,h*1.6)
                    and _inside(scope,(b[0]-3,b[1]-5,b[2]+3,b[3]+5))>.9):return True
        return False
    finally:ink.close()


def _raster_columns(source,number,box):
    import pymupdf
    page=source[number-1]
    pix=page.get_pixmap(matrix=pymupdf.Matrix(2,2),clip=pymupdf.Rect(box)*page.rotation_matrix,
                        colorspace=pymupdf.csGRAY,alpha=False)
    best=[]
    samples=pix.samples;minimum=pix.width*.12
    for y in range(int(pix.height*.6),int(pix.height*.98)):
        spans=[];start=None
        for x in range(pix.width+1):
            dark=x<pix.width and samples[y*pix.width+x]<160
            if dark and start is None:start=x
            if not dark and start is not None:
                if x-start>=minimum:spans.append((start/pix.width,x/pix.width))
                start=None
        if 2<=len(spans)<=5 and max(b-a for a,b in spans)<min(b-a for a,b in spans)*1.4:
            if sum(b-a for a,b in spans)>sum(b-a for a,b in best):best=spans
    return best


def _claim_cross_page_parts(objects,document):
    from .caption_rules import _matches
    if not Path(document.path).is_file():return objects
    import pymupdf
    pages={p.number:p for p in document.pages};result=list(objects)
    captions=[o for o in objects if o.kind=='figure_caption']
    with pymupdf.open(document.path) as source:
        for i,first in enumerate(result):
            if first.kind!='figure' or first.role!='continuous_chart_panels':continue
            page=pages.get(first.page_number);following=pages.get(first.page_number+1)
            if page is None or following is None:continue
            if any(c.page_number==first.page_number and _matches(first,c) for c in captions):continue
            rows=sorted([b for b in page.images if _inside(b,first.bbox)>.93
                         and b[2]-b[0]>(first.bbox[2]-first.bbox[0])*.8 and b[3]-b[1]>50],key=lambda b:b[1])
            if len(rows)<2 or any(abs(a[2]-a[0]-b[2]+b[0])>3 or not -.5<=b[1]-a[3]<=2
                                  for a,b in zip(rows,rows[1:])):continue
            if any(_body_line(l) and first.bbox[3]<l.bbox[1]<page.height*.88 for l in page.lines):continue
            mains=[o for o in result if o.kind=='figure' and o.page_number==following.number
                   and o.bbox[1]<following.height*.25 and _xover(o.bbox,first.bbox)>.93]
            for main in mains:
                titles=[c for c in captions if c.page_number==main.page_number and _matches(main,c)
                        and _gap(main.bbox,c.bbox)<45]
                if len(titles)!=1:continue
                next_rows=[b for b in following.images if _inside(b,main.bbox)>.93
                           and b[2]-b[0]>(main.bbox[2]-main.bbox[0])*.8 and b[3]-b[1]>50]
                if len(next_rows)!=1:continue
                if abs((rows[-1][2]-rows[-1][0])-(next_rows[0][2]-next_rows[0][0]))>3:continue
                if any(_body_line(l) and following.height*.13<l.bbox[1]<main.bbox[1] for l in following.lines):continue
                profiles=[_raster_columns(source,page.number,b) for b in rows]
                profiles.append(_raster_columns(source,following.number,next_rows[0]))
                base=profiles[0]
                if len(base)<3 or any(len(p)!=len(base) or any(abs(a-c)>.035 or abs(b-d)>.035
                    for (a,b),(c,d) in zip(base,p)) for p in profiles[1:]):continue
                owner=main.source_id or f'figure:{main.page_number}:{titles[0].text}'
                result[i]=replace(first,kind='text',role='owned_cross_page_figure_part',parent_id=owner,parent_bbox=None,parent_kind='figure')
                break
    return result


def _barrier(group,caption,page,objects):
    from .graphic_context import _detached_sentence
    box=_union([o.bbox for o in group]); top=min(box[1],caption.bbox[1]);bottom=max(box[3],caption.bbox[3])
    for l in page.lines:
        if not (top<=l.bbox[1]<bottom) or _CAPTION.match(normalize_text(l.text)) or _PANEL.match(normalize_text(l.text)):
            continue
        detached=_detached_sentence(l,page)
        if not (_body_line(l) or detached):
            continue
        if any(_inside(l.bbox,o.bbox)>=.65 for o in group) or _inside(l.bbox,caption.bbox)>.5:
            continue
        if detached and _xover(l.bbox,box)>0:
            return True
        if _xover(l.bbox,box)>=.75 and l.bbox[2]-l.bbox[0]>=(box[2]-box[0])*.72:
            return True
    return False


def _physical_panel_marker(line,group):
    """Bind a panel tag to real component ink, rather than a prose envelope."""
    marker=line.bbox
    raw_match=_PANEL.match(line.text)
    if line.source=='native' and raw_match and line.text_regions:
        required={i for i,c in enumerate(line.text[:raw_match.end()]) if c.strip()}
        glyphs=[(a,z,b) for a,z,b in line.text_regions
                if z-a==1 and a in required]
        if {a for a,z,b in glyphs}==required:
            marker=_union([b for a,z,b in glyphs])
    x=(marker[0]+marker[2])/2;y=(marker[1]+marker[3])/2
    # A previously merged rectangular envelope can contain whitespace beside
    # its true pieces. Only the actual components may own an annotation.
    components=[b for o in group for b in (o.panel_boxes or (o.bbox,))]
    if not any(b[0]-15<=x<=b[2]+15 and b[1]-45<=y<=b[3]+45 for b in components):
        return None
    return marker


def _numbered_panel_members(group,caption,page,parents):
    """Own numbered children only through their native tag and parent band.

    A total (a,b) namespace can contain (a1,a2) and (b1,b2). A parent tag
    centred beneath a band does not give an untagged neighbour membership.
    Every child needs complete original character rectangles and one unique
    physical component immediately above its own prefix.
    """
    pieces=[(i,k,b) for i,o in enumerate(group)
            for k,b in enumerate(o.panel_boxes or (o.bbox,))]
    families={}
    for line in page.lines:
        match=_NUMBERED_PANEL.match(line.text)
        if (match is None or line.source!='native'
                or _inside(line.bbox,caption.bbox)>.5):continue
        required={i for i,c in enumerate(line.text[:match.end()]) if c.strip()}
        glyphs=[(a,z,b) for a,z,b in line.text_regions
                if z-a==1 and a in required and _area(b)>0]
        if {a for a,z,b in glyphs}!=required:continue
        marker=_union([b for a,z,b in glyphs]);x=(marker[0]+marker[2])/2
        candidates=[(i,k,b) for i,k,b in pieces
                    if b[0]-15<=x<=b[2]+15 and -2<=marker[1]-b[3]<=45
                    and _xover(line.bbox,b)>=.4]
        if len(candidates)!=1:continue
        families.setdefault(match.group(1).lower(),[]).append(
            (int(match.group(2)),line,candidates[0]))
    owned=set()
    for tag,children in families.items():
        children.sort(key=lambda c:c[0])
        if [n for n,l,p in children]!=list(range(1,len(children)+1)) or len(children)<2:continue
        if len({(i,k) for n,l,(i,k,b) in children})!=len(children):continue
        if max(l.bbox[1] for n,l,p in children)-min(l.bbox[1] for n,l,p in children)>4:continue
        band=sorted((b for n,l,(i,k,b) in children),key=lambda b:b[0])
        if any(max(0,min(a[3],b[3])-max(a[1],b[1]))<.8*min(a[3]-a[1],b[3]-b[1])
               or not -2<=b[0]-a[2]<=20 for a,b in zip(band,band[1:])):continue
        box=_union(band);last=max(l.bbox[3] for n,l,p in children)
        aliases=[]
        for parent in parents:
            match=_PANEL.match(parent.text)
            if match is None or match.group(1).lower()!=tag or parent.source!='native':continue
            required={i for i,c in enumerate(parent.text[:match.end()]) if c.strip()}
            covered={a for a,z,b in parent.text_regions if z-a==1 and a in required and _area(b)>0}
            if (required!=covered or not -2<=parent.bbox[1]-last<=32
                    or abs((parent.bbox[0]+parent.bbox[2]-box[0]-box[2])/2)>max(24,(box[2]-box[0])*.12)):continue
            aliases.append(parent)
        if len(aliases)!=1:continue
        owned.update(i for n,l,(i,k,b) in children)
    return owned


def _labelled_members(group,caption,page):
    """Keep direct owners and compact bands named by one wide panel label."""
    labels=[l for l in page.lines if _PANEL.match(normalize_text(l.text))
            and _inside(l.bbox,caption.bbox)<=.5
            and _physical_panel_marker(l,group) is not None]
    # A numbered native family requires its actual parent prefix too. A
    # missing prefix cannot fall back to the centred whole description line
    # and accidentally claim both components before child ownership is checked.
    numbered_tags={m.group(1).lower() for l in page.lines
                   if l.source=='native' and (m:=_NUMBERED_PANEL.match(l.text))
                   and _inside(l.bbox,caption.bbox)<=.5}
    proved=[]
    for label in labels:
        match=_PANEL.match(label.text)
        if match and match.group(1).lower() in numbered_tags:
            required={i for i,c in enumerate(label.text[:match.end()]) if c.strip()}
            covered={a for a,z,b in label.text_regions if z-a==1 and a in required and _area(b)>0}
            if label.source!='native' or required!=covered:continue
        proved.append(label)
    labels=proved
    covered={i for i,o in enumerate(group)
             if any(_physical_panel_marker(l,[o]) is not None for l in labels)}
    covered.update(_numbered_panel_members(group,caption,page,labels))
    box=_union([o.bbox for o in group])
    # A single short tag cannot give its neighbours an identity. An actual
    # wide, centred row label can name several tightly arranged curves in
    # that band; its horizontal footprint and neighbouring tag bands bound
    # the additional physical ownership.
    for label in labels:
        if (label.bbox[2]-label.bbox[0]<(box[2]-box[0])*.5
                or abs((label.bbox[0]+label.bbox[2]-box[0]-box[2])/2)>(box[2]-box[0])*.12
                or label.bbox[3]-label.bbox[1]>36
                or len(re.findall(r'[（(][a-z][）)]',normalize_text(label.text),re.I))!=1):
            continue
        start=max((l.bbox[3] for l in labels if l.bbox[3]<label.bbox[1]-2),default=box[1])
        pieces=[(i,b) for i,o in enumerate(group) for b in (o.panel_boxes or (o.bbox,))
                if start-2<=b[1] and b[3]<=label.bbox[1]+2
                and _xover(b,label.bbox)>=.3]
        seen={j for j,(i,b) in enumerate(pieces)
              if _physical_panel_marker(label,[replace(group[i],bbox=b,panel_boxes=())]) is not None}
        while True:
            extra=set()
            for j,(i,a) in enumerate(pieces):
                if j in seen:continue
                for k in seen:
                    b=pieces[k][1]
                    ox=max(0,min(a[2],b[2])-max(a[0],b[0]))
                    oy=max(0,min(a[3],b[3])-max(a[1],b[1]))
                    gx=max(a[0]-b[2],b[0]-a[2],0);gy=_gap(a,b)
                    if ((gx<=20 and oy>=.5*min(a[3]-a[1],b[3]-b[1]))
                            or (gy<=20 and ox>=.5*min(a[2]-a[0],b[2]-b[0]))):
                        extra.add(j);break
            if not extra:break
            seen.update(extra)
        covered.update(pieces[j][0] for j in seen)
    return [o for i,o in enumerate(group) if i in covered]


def _labelled(group,caption,page):
    box=_union([o.bbox for o in group])
    labels=[]
    for l in page.lines:
        match=_PANEL.match(normalize_text(l.text))
        if not match or _inside(l.bbox,caption.bbox)>.5:
            continue
        marker=_physical_panel_marker(l,group)
        if marker is not None and box[1]-45<=marker[1]<=box[3]+45 and _xover(marker,box)>0:
            labels.append((match.group(1).lower(),marker))
    unique={tag for tag,_ in labels}
    if len(unique)<2 or 'a' not in unique or unique!={chr(ord('a')+i) for i in range(len(unique))}:
        return False
    # OCR and native aliases of one label are harmless. Two spatially distinct
    # occurrences of the same label start independent figure namespaces.
    for tag in unique:
        boxes=[b for t,b in labels if t==tag]
        if any(abs(a[1]-b[1])>22 or abs(a[0]-b[0])>40 for a in boxes for b in boxes):
            return False
    # Labels inside an already composite body describe that body. External
    # pieces need their own label evidence; the body's internal (a,b) cannot
    # turn an unrelated neighbouring chart into another panel.
    for owner in group:
        internal={tag for tag,b in labels if _inside(b,owner.bbox)>=.6}
        if len(internal)<2:continue
        external=[o for o in group if o is not owner and _inside(o.bbox,owner.bbox)<.9]
        if not external:continue
        outside=_union([o.bbox for o in external])
        if not any(_inside(b,owner.bbox)<.5 and outside[1]-45<=b[1]<=outside[3]+45
                   and _xover(b,outside)>0 for tag,b in labels):
            return False
    # The nearest total caption must follow the final labelled band (or precede
    # the first), and its horizontal centre must belong to the combined group.
    centre=abs((caption.bbox[0]+caption.bbox[2]-box[0]-box[2])/2)
    return centre<=max(24,(box[2]-box[0])*.14) and _gap(box,caption.bbox)<=80


def _dense_grid(group,caption,page):
    box=_union([o.bbox for o in group]);w=box[2]-box[0]
    if abs((caption.bbox[0]+caption.bbox[2]-box[0]-box[2])/2)>max(18,w*.08):
        return False
    if _gap(box,caption.bbox)>65:
        return False
    # A parser parent or a real physical graphic spanning the pieces proves
    # their common container. A whole-page scan is never such a container.
    carriers=list(page.images)+list(page.graphics)
    carriers += [o.parent_bbox for o in group if o.parent_bbox is not None]
    if any(_area(b)<page.width*page.height*.72 and all(_inside(o.bbox,b)>.9 for o in group)
           and _area(box)/max(_area(b),1)>.45 for b in carriers):
        return True
    # Mixed image/results rows are declared table cells, with alternating
    # photos and numerical tables in one aligned results namespace.
    if caption.kind=='table_caption' and any(o.kind=='table' for o in group) and any(o.kind=='figure' for o in group):
        return caption.bbox[2]-caption.bbox[0]>=w*.7
    if len(group)<3:
        return False
    if caption.kind=='figure_caption' and caption.bbox[2]-caption.bbox[0]<w*.7:
        rows={round((o.bbox[1]+o.bbox[3])/2/30) for o in group}
        columns={round((o.bbox[0]+o.bbox[2])/2/30) for o in group}
        if len(rows)<2 or len(columns)<2:return False
    # Compact stacks/grid charts: all pieces must connect through aligned
    # edges with a gutter small relative to the panel, not title proximity.
    seen={0};changed=True
    while changed:
        changed=False
        for i,o in enumerate(group):
            if i in seen:continue
            a=o.bbox
            for j in tuple(seen):
                b=group[j].bbox
                xgap=max(a[0]-b[2],b[0]-a[2],0);ygap=_gap(a,b)
                xaligned=_xover(a,b)>.75
                yaligned=max(0,min(a[3],b[3])-max(a[1],b[1]))>=min(a[3]-a[1],b[3]-b[1])*.75
                if (xaligned and ygap<=max(14,min(a[3]-a[1],b[3]-b[1])*.2)) or (yaligned and xgap<=max(14,min(a[2]-a[0],b[2]-b[0])*.15)):
                    seen.add(i);changed=True;break
    plural=bool(re.search(r'不同|对比|比较|各|结果|示意|Compar|different|results|schedule',caption.text,re.I))
    return len(seen)==len(group) and plural


def _exclusive_table_title(obj,caption,targets,captions):
    from .caption_rules import _matches
    for other in targets:
        if other is obj or other.page_number!=obj.page_number:continue
        # A numeric cell contained in the same physical body is not an
        # independent neighbour. Established outside owners keep their title.
        if _inside(obj.bbox,other.bbox)>.9 or _inside(other.bbox,obj.bbox)>.9:continue
        if not _matches(replace(other,kind='table'),caption):continue
        if other.kind=='table':return False
        own=any(c.kind=='figure_caption' and c.page_number==other.page_number
                and _matches(other,c) for c in captions)
        if own and _gap(other.bbox,caption.bbox)<=_gap(obj.bbox,caption.bbox)+2:
            return False
    return True


def _join(group,kind):
    first=group[0]
    boxes=tuple(dict.fromkeys(tuple(b) for o in group for b in (o.panel_boxes or (o.bbox,))))
    return replace(first,kind=kind,bbox=_union([o.bbox for o in group]),panel_boxes=boxes,
                   role='declared_composite_'+kind)




def _trim_panel_caption_edge(obj,page,captions):
    """Exclude a title accidentally included in a parser's panel envelope."""
    panels=obj.panel_boxes
    if len(panels)<2 or not all(_inside(b,obj.bbox)>.95 for b in panels):return obj
    # Each declared panel must also have a bounded original PDF image. A scan
    # canvas or an unsupported parser subdivision cannot prove this crop.
    if not all(any(_inside(b,im)>.85 and _area(im)<=_area(b)*1.65
                   for im in page.images) for b in panels):return obj
    support=[im for b in panels for im in page.images
             if _inside(b,im)>.85 and _area(im)<=_area(b)*1.65]
    end=max(b[3] for b in (*panels,*support))
    caps=[c for c in captions if c.kind=='figure_caption' and c.page_number==obj.page_number
          and _xover(c.bbox,obj.bbox)>.5 and end<=c.bbox[1]<obj.bbox[3]<=c.bbox[3]+5
          and c.bbox[1]-end<=80]
    if len(caps)!=1:return obj
    cap=caps[0]
    # Preserve any physical graphic in the proposed removed band. Merely
    # containing an internal title does not let a figure discard its body.
    if any(_area(_intersection(b,obj.bbox))>0 and b[3]>end+3
           and b[1]<obj.bbox[3] and _area(b)<page.width*page.height*.8
           for b in (*page.images,*page.graphics)):return obj
    band=[l for l in page.lines if end<=l.bbox[1]<cap.bbox[1] and _xover(l.bbox,obj.bbox)>0]
    if any(_body_line(l) for l in band):return obj
    labels=[l.bbox[3] for l in band if _PANEL.match(normalize_text(l.text))]
    end=max([end,*labels])
    return replace(obj,bbox=(obj.bbox[0],obj.bbox[1],obj.bbox[2],end))


def _directional_arrow(obj,pdf):
    """Pixel proof of a solid shaft with a single tapered arrowhead."""
    if pdf is None:return False
    import pymupdf
    page=pdf[obj.page_number-1]
    pix=page.get_pixmap(matrix=pymupdf.Matrix(2,2),clip=pymupdf.Rect(obj.bbox)*page.rotation_matrix,
                        colorspace=pymupdf.csGRAY,alpha=False)
    if pix.width<80 or pix.height<6:return False
    samples=pix.samples;profiles=[];centres=[];gaps=0
    for x in range(pix.width):
        ys=[y for y in range(pix.height) if samples[y*pix.width+x]<254]
        if not ys:profiles.append(0);continue
        span=ys[-1]-ys[0]+1
        profiles.append(span);centres.append((ys[-1]+ys[0])/2)
        gaps+=span-len(ys)
    occupied=sum(v>0 for v in profiles)
    if occupied<pix.width*.9 or gaps>sum(profiles)*.02:return False
    if max(centres)-min(centres)>max(3,pix.height*.12):return False
    for profile in (profiles,list(reversed(profiles))):
        mid=sorted(profile[int(pix.width*.25):int(pix.width*.65)])
        shaft=mid[len(mid)//2];peak=max(profile);pos=profile.index(peak)
        if shaft<=0 or peak<shaft*1.45 or not pix.width*.65<pos<pix.width*.98:continue
        if sum(abs(v-shaft)<=2 for v in mid)<len(mid)*.9:continue
        tail=profile[pos:];steps=[b<=a+1 for a,b in zip(tail,tail[1:])]
        if len(tail)>=5 and tail[-1]<=peak*.3 and sum(steps)>=len(steps)*.9:return True
    return False


def _attach_time_arrow(objects,pages,pdf):
    result=list(objects);caps=[o for o in objects if o.kind=='figure_caption']
    for cap in caps:
        page=pages.get(cap.page_number)
        if page is None:continue
        for main in list(result):
            if main.kind!='figure' or main.page_number!=cap.page_number or len(main.panel_boxes)<2:continue
            if not _labelled([main],cap,page):continue
            timed=[l for l in page.lines if _PANEL.match(normalize_text(l.text))
                   and _inside(l.bbox,main.bbox)>.6
                   and re.search(r'时间|time|\d\s*(?:ms|s|seconds)\b',l.text,re.I)]
            if len(timed)<2:continue
            for arrow in list(result):
                if arrow is main or arrow.kind!='figure' or arrow.page_number!=main.page_number:continue
                a=arrow.bbox;b=main.bbox
                if not (b[3]<=a[1]<=b[3]+30 and a[3]<=cap.bbox[1]+2
                        and 3<a[3]-a[1]<=min(40,(b[3]-b[1])*.25)
                        and abs(a[0]-b[0])<12 and abs(a[2]-b[2])<12):continue
                if _barrier([main,arrow],cap,page,result):continue
                if any(c is not cap and c.page_number==main.page_number
                       and _gap(c.bbox,a)<_gap(cap.bbox,a) and _xover(c.bbox,a)>.5 for c in caps):continue
                if not _directional_arrow(arrow,pdf):continue
                joined=_join([main,arrow],'figure');result.remove(main);result.remove(arrow);result.append(joined)
                break
    return result


def _recover_labelled_vectors(objects,pages):
    result=list(objects)
    captions=[o for o in objects if o.kind.endswith('_caption')]
    for cap in captions:
        if cap.kind!='figure_caption':continue
        page=pages.get(cap.page_number)
        if page is None:continue
        same=[o for o in result if o.page_number==cap.page_number and o.kind=='figure']
        if not same:continue
        others=[c for c in captions if c is not cap and c.page_number==cap.page_number]
        low=max((c.bbox[3] for c in others if c.bbox[3]<=cap.bbox[1]),default=0)
        high=min((c.bbox[1] for c in others if c.bbox[1]>=cap.bbox[3]),default=page.height)
        labels=[(m.group(1).lower(),l) for l in page.lines
                if (m:=_PANEL.match(normalize_text(l.text))) and low<=l.bbox[1]<=high
                and _inside(l.bbox,cap.bbox)<.5]
        tags={t for t,l in labels}
        if len(tags)<2 or tags!={chr(ord('a')+i) for i in range(len(tags))}:continue
        proposals=[]
        for tag,label in labels:
            frames=[b for b in page.graphics if 1000<_area(b)<page.width*page.height*.65
                    and min(b[2]-b[0],b[3]-b[1])>35 and _gap(b,label.bbox)<=40
                    and _xover(b,label.bbox)>.65 and _inside(cap.bbox,b)<.4]
            if not frames:continue
            frame=max(frames,key=_area)
            if any(_inside(frame,o.bbox)>.9 for o in same):continue
            if any(_inside(c.bbox,frame)>.5 for c in others):continue
            proposals.append(LayoutObject('figure',page.number,frame,'',page.width,page.height,
                                          role='declared_vector_panel'))
        if not proposals:continue
        group=same+proposals
        if _labelled(group,cap,page) and not _barrier(group,cap,page,objects):
            result.extend(proposals)
    return result


def _map_object(obj,transform,width,height):
    return replace(obj,bbox=transform(obj.bbox),page_width=width,page_height=height,
                   panel_boxes=tuple(transform(b) for b in obj.panel_boxes),
                   parent_bbox=transform(obj.parent_bbox) if obj.parent_bbox is not None else None,
                   text_lines=tuple((t,transform(b)) for t,b in obj.text_lines))


def _upright_views(objects,pages):
    rotated={n:p for n,p in pages.items() if any(o.page_number==n and o.kind.endswith('_caption')
             and o.bbox[3]-o.bbox[1]>3*(o.bbox[2]-o.bbox[0]) for o in objects)}
    transforms={n:(lambda b,w=p.width:(b[1],w-b[2],b[3],w-b[0])) for n,p in rotated.items()}
    mapped=[_map_object(o,transforms[o.page_number],rotated[o.page_number].height,rotated[o.page_number].width)
            if o.page_number in rotated else o for o in objects]
    views=dict(pages)
    for n,p in rotated.items():
        transform=transforms[n]
        views[n]=replace(p,width=p.height,height=p.width,
            lines=tuple(replace(l,bbox=transform(l.bbox),page_width=p.height,page_height=p.width) for l in p.lines),
            images=tuple(transform(b) for b in p.images),graphics=tuple(transform(b) for b in p.graphics),
            tables=tuple(transform(b) for b in p.tables))
    return mapped,views,rotated


def repair_figure_identity(objects,document):
    """Return layout objects with independently established academic identities.

    This is deliberately independent of paper names, IDs, expected findings,
    and evaluation labels. Call at the end of ``prepare_caption_layout``.
    """
    if document is None:
        return list(objects)
    pages={p.number:p for p in document.pages};pdf=None
    if Path(document.path).is_file():
        try:
            import pymupdf
            pdf=pymupdf.open(document.path)
        except (OSError,ValueError):
            pass
    fixed=[]
    captions=[o for o in objects if o.kind=='figure_caption']
    try:
        for o in objects:
            page=pages.get(o.page_number)
            if o.kind=='figure' and page is not None:
                o=_trim_panel_caption_edge(o,page,captions)
                reason=_text_evidence(o,page,document)
                glyph=_native_glyph_carrier(o,page,pdf) if reason is None else False
                inline=_inline_source_carrier(o,page,pdf) if not reason and not glyph else False
                if reason or glyph or inline or _blank_carrier(o,pdf):
                    o=replace(o,kind='text',role=reason or ('native_body_glyph_carrier' if glyph else 'source_inline_symbol' if inline else 'blank_native_carrier'))
            fixed.append(o)
        fixed=_attach_time_arrow(fixed,pages,pdf)
    finally:
        if pdf is not None:pdf.close()
    fixed,pages,rotated=_upright_views(fixed,pages)
    fixed=_recover_labelled_vectors(fixed,pages)
    captions=[o for o in fixed if o.kind in {'figure_caption','table_caption'}]
    targets=[o for o in fixed if o.kind in {'figure','table'}]
    rest=[o for o in fixed if o.kind not in {'figure','table'}]
    # Resolve total title ownership before looking at the last individual
    # panel's title distance. Both above and below titles remain valid.
    for cap in sorted(captions,key=lambda c:(c.page_number,c.bbox[1])):
        page=pages.get(cap.page_number)
        if page is None:continue
        kind=cap.kind.removesuffix('_caption')
        same=[o for o in targets if o.page_number==cap.page_number and (o.kind==kind or kind=='table')]
        for side in ('above','below'):
            others=[c for c in captions if c is not cap and c.page_number==cap.page_number]
            low=max((c.bbox[3] for c in others if c.bbox[3]<=cap.bbox[1]),default=0)
            high=min((c.bbox[1] for c in others if c.bbox[1]>=cap.bbox[3]),default=page.height)
            group=[o for o in same if _xover(o.bbox,cap.bbox)>=.15 and (
                low<=o.bbox[1] and o.bbox[3]<=cap.bbox[1]+5 if side=='above' else
                cap.bbox[3]-5<=o.bbox[1] and o.bbox[3]<=high)]
            group=[o for o in group if not any(c.kind==o.kind+'_caption'
                and _gap(c.bbox,o.bbox)<=80 and _xover(c.bbox,o.bbox)>=.65
                and _gap(cap.bbox,o.bbox)>_gap(c.bbox,o.bbox)+5 for c in others)]
            if len(group)<2 or _barrier(group,cap,page,fixed):continue
            if _labelled(group,cap,page):
                if kind=='figure':
                    # A labelled namespace proves only the bodies that own its
                    # actual markers. Leave unlabelled neighbours as independent
                    # figures with their own missing-caption obligation.
                    marked=_labelled_members(group,cap,page)
                    if len(marked)<2 or not _labelled(marked,cap,page):continue
                    group=marked
            elif not _dense_grid(group,cap,page):continue
            # A dedicated caption of the group's original kind establishes an
            # independent object; a Table title must not override it.
            if any(c is not cap and c.kind==o.kind+'_caption' and c.page_number==o.page_number
                   and _gap(c.bbox,o.bbox)<45 and _xover(c.bbox,o.bbox)>.5
                   for o in group for c in others):continue
            if kind=='table' and any(o.kind=='figure' for o in group):
                envelope=_union([o.bbox for o in group])
                photos=[o for o in group if o.kind=='figure']
                for cell in same:
                    if cell.kind!='table' or cell in group or _inside(cell.bbox,envelope)<.9:continue
                    if any(max(0,min(cell.bbox[3],im.bbox[3])-max(cell.bbox[1],im.bbox[1]))
                           >=min(cell.bbox[3]-cell.bbox[1],im.bbox[3]-im.bbox[1])*.65
                           and max(cell.bbox[0]-im.bbox[2],im.bbox[0]-cell.bbox[2],0)<20
                           for im in photos):
                        group.append(cell)
            joined=_join(group,kind)
            ids={id(o) for o in group};targets=[o for o in targets if id(o) not in ids]+[joined]
            same=[o for o in same if id(o) not in ids]+[joined]
    # A nearby exclusive declared Table title may identify a single chart.
    for i,o in enumerate(targets):
        if o.kind!='figure':continue
        table_caps=[c for c in captions if c.kind=='table_caption' and c.page_number==o.page_number
                    and _gap(c.bbox,o.bbox)<=65 and _xover(c.bbox,o.bbox)>=.65
                    and abs((c.bbox[0]+c.bbox[2]-o.bbox[0]-o.bbox[2])/2)<=max(20,(o.bbox[2]-o.bbox[0])*.16)
                    and _exclusive_table_title(o,c,targets,captions)]
        own=[c for c in captions if c.kind=='figure_caption' and c.page_number==o.page_number
             and _gap(c.bbox,o.bbox)<=80 and _xover(c.bbox,o.bbox)>=.4]
        if len(table_caps)==1 and not own and not _barrier([o],table_caps[0],pages[o.page_number],fixed):
            targets[i]=replace(o,kind='table',role='declared_table_graphic')
    result=targets+rest
    for i,o in enumerate(result):
        if o.page_number in rotated:
            p=rotated[o.page_number]
            inverse=lambda b,w=p.width:(w-b[3],b[0],w-b[1],b[2])
            result[i]=_map_object(o,inverse,p.width,p.height)
    from .caption_physical_ownership import repair_caption_physical_ownership
    return repair_caption_physical_ownership(_claim_cross_page_parts(result,document),document)
