"""Caption-declared component ownership backed by original PDF paint removal.

This module never exempts a figure. It joins only source ink explained by a
physical PDF resource and an independently retained caption declaration.
"""
from dataclasses import replace
from pathlib import Path
import re

from .numbering import normalize_text,normalize_label,FIGURE_CAPTION
from .figure_identity_repair import _area,_inside,_union,_xover,_gap,_join,_barrier

_ALPHA=re.compile(r'^\s*[（(]([a-z])[）)](?:\s|$)',re.I)


def _do_spans(data):
    """Read only real top-level Do operands, excluding PDF strings and comments.

    Inline-image streams and malformed lexical nesting fail closed. Mutating
    these offsets affects only a disposable in-memory copy of the source page.
    """
    i=0;prev=None;depth=0;out=[];n=len(data)
    while i<n:
        c=data[i]
        if c in b'\x00\t\n\r\x0c ':i+=1;continue
        if c==37:
            end=data.find(b'\n',i);i=n if end<0 else end+1;continue
        if c==40:
            i+=1;balance=1
            while i<n and balance:
                if data[i]==92:i+=2;continue
                if data[i]==40:balance+=1
                if data[i]==41:balance-=1
                i+=1
            if balance:return []
            prev=None;continue
        if c==60 and data[i:i+2]!=b'<<':
            end=data.find(b'>',i+1)
            if end<0:return []
            i=end+1;prev=None;continue
        if c in b'[]' or data[i:i+2] in (b'<<',b'>>'):
            opening=c==91 or data[i:i+2]==b'<<';depth+=1 if opening else -1
            if depth<0:return []
            i+=2 if data[i:i+2] in (b'<<',b'>>') else 1;prev=None;continue
        start=i;name=c==47
        if name:i+=1
        while i<n and data[i] not in b'\x00\t\n\r\x0c ()<>[]{}/%':i+=1
        if i==start:return []
        token=data[start:i]
        if not name and token==b'BI':return []
        if token==b'Do' and depth==0 and prev and prev[0].startswith(b'/'):
            raw=prev[0][1:];raw=re.sub(rb'#([0-9a-fA-F]{2})',lambda m:bytes([int(m.group(1),16)]),raw)
            out.append((raw.decode('latin1'),prev[1],i))
        prev=(token,start,i) if name and depth==0 else None
    return out if depth==0 else []


class _PageInk:
    def __init__(self,source,number):
        import pymupdf,numpy as np
        self.np=np;self.fit=pymupdf;self.copy=pymupdf.open();self.copy.insert_pdf(source,from_page=number-1,to_page=number-1)
        self.page=self.copy[0];self.scale=2;self.data=self.page.read_contents();self.spans=_do_spans(self.data)
        self.xref=self.copy.get_new_xref();self.copy.update_object(self.xref,'<<>>');self.copy.update_stream(self.xref,self.data);self.page.set_contents(self.xref)
        self.copy.update_stream(self.xref,self.data);a=self.page.get_pixmap(matrix=pymupdf.Matrix(2,2),colorspace=pymupdf.csGRAY,alpha=False)
        original=source[number-1].get_pixmap(matrix=pymupdf.Matrix(2,2),colorspace=pymupdf.csGRAY,alpha=False)
        self.valid=(a.width,a.height,a.samples)==(original.width,original.height,original.samples)
        self.base=np.frombuffer(a.samples,dtype=np.uint8).reshape(a.height,a.width);self.height=a.height;self.width=a.width;self.cache={}
    def close(self):self.copy.close()
    def removal(self,names):
        key=tuple(sorted(names))
        if key in self.cache:return self.cache[key]
        spans=[(a,b) for name,a,b in self.spans if name in names]
        if not spans or not self.valid:return None
        data=bytearray(self.data)
        for a,b in spans:data[a:b]=b' '*(b-a)
        self.copy.update_stream(self.xref,bytes(data));p=self.page.get_pixmap(matrix=self.fit.Matrix(2,2),colorspace=self.fit.csGRAY,alpha=False)
        self.copy.update_stream(self.xref,self.data)
        if (p.height,p.width)!=(self.height,self.width):return None
        after=self.np.frombuffer(p.samples,dtype=self.np.uint8).reshape(p.height,p.width)
        # A one-grey-level stroke counts as ink. Partial lightening is not
        # proof of ownership: the selected source must remove the ink to paper.
        mask=(self.base<255)&(after==255);ys,xs=self.np.where(mask)
        if len(xs)<32:return None
        box=(float(xs.min())/2,float(ys.min())/2,float(xs.max()+1)/2,float(ys.max()+1)/2)
        result={'box':box,'mask':mask,'names':key};self.cache[key]=result;return result
    def owns(self,obj,owner):
        if owner is None:return False
        # Check each true component, including every ink pixel within it.
        # An envelope containing another plot in its white gaps cannot own it.
        for box in obj.panel_boxes or (obj.bbox,):
            x0,y0,x1,y1=[int(round(v*2)) for v in box];x0=max(x0,0);y0=max(y0,0);x1=min(x1,self.width);y1=min(y1,self.height)
            if x1<=x0 or y1<=y0:return False
            ink=self.base[y0:y1,x0:x1]<255;count=int(ink.sum());owned=int((ink&owner['mask'][y0:y1,x0:x1]).sum())
            if count<32 or count-owned!=0:return False
        return True
    def glyph_owned(self,box,owner):
        x0,y0,x1,y1=[int(round(v*2)) for v in box];x0=max(x0,0);y0=max(y0,0);x1=min(x1,self.width);y1=min(y1,self.height)
        if x1<=x0 or y1<=y0:return False
        ink=self.base[y0:y1,x0:x1]<255;n=int(ink.sum());return n>0 and int((ink&owner['mask'][y0:y1,x0:x1]).sum())>=n*.95


def _native_caption(cap,page):
    declared=FIGURE_CAPTION.match(normalize_text(cap.text))
    if not declared:return False
    for line in page.lines:
        m=FIGURE_CAPTION.match(normalize_text(line.text))
        required={i for i,c in enumerate(line.text[:m.end('number')]) if c.strip()} if m else set()
        covered={a for a,z,b in line.text_regions if z-a==1 and a in required and _area(b)>0}
        if (line.source=='native' and m and required==covered and line.bold
                and normalize_label(m.group('number'))==normalize_label(declared.group('number'))
                and _inside(line.bbox,cap.bbox)>.75):return True
    return False



def _native_caption_text(cap,page):
    """Use retained original title glyphs for positional declarations.

    Cache text can supply a title candidate, but cannot invent left/right or
    top/bottom ownership. Uncovered native characters contribute no evidence.
    """
    declared=FIGURE_CAPTION.match(normalize_text(cap.text))
    if declared is None:return ''
    number=normalize_label(declared.group('number'));chunks=[];previous=None
    for line in sorted(page.lines,key=lambda l:(l.bbox[1],l.bbox[0])):
        if line.source!='native' or not line.bold or _inside(line.bbox,cap.bbox)<=.75:continue
        match=FIGURE_CAPTION.match(normalize_text(line.text))
        covered={a for a,z,b in line.text_regions if z-a==1 and _area(b)>0}
        if match:
            required={i for i,c in enumerate(line.text[:match.end('number')]) if c.strip()}
            if normalize_label(match.group('number'))!=number or not required<=covered:
                previous=None;continue
        elif (previous is None or line.bbox[1]-previous.bbox[3]>3
                or not .9<=line.font_size/max(previous.font_size,.01)<=1.1):
            continue
        chunks.append(''.join(c if not c.strip() or i in covered else ' ' for i,c in enumerate(line.text)))
        previous=line
    return ' '.join(chunks)


def _namespace_group(objects,cap,page):
    other=[c for c in objects if c.kind.endswith('_caption') and c.page_number==page.number and c is not cap]
    low=max((c.bbox[3] for c in other if c.bbox[3]<cap.bbox[1]-2),default=page.height*.09)
    return [o for o in objects if o.kind=='figure' and o.page_number==page.number
            and low<=o.bbox[1] and o.bbox[3]<=cap.bbox[1]+2 and _xover(o.bbox,cap.bbox)>.2],other


def _independent_titles(group,cap,other):
    from .caption_rules import _matches
    return any(c.kind=='figure_caption' and any(_matches(o,c) and _gap(c.bbox,o.bbox)<=_gap(cap.bbox,o.bbox)+2 for o in group) for c in other)


def _position_declaration(text):
    value=normalize_text(text)
    left=bool(re.search(r'[（(]\s*(?:左|left)\s*[）)]|左图\s*[：:]|\bLeft\s*:',value,re.I));right=bool(re.search(r'[（(]\s*(?:右|right)\s*[）)]|右图\s*[：:]|\bRight\s*:',value,re.I))
    if left and right:return 'horizontal',(1,1)
    top=bool(re.search(r'上图\s*[：:]|\bTop\s*:',value,re.I));bottom=bool(re.search(r'下图\s*[：:]|\bBottom\s*:',value,re.I))
    if not top or not bottom:return None
    def count(role):
        chinese={'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
        english={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9}
        start='上图' if role==0 else '下图';word='Top' if role==0 else 'Bottom'
        m=re.search(start+r'\s*[：:]\s*([一二三四五六七八九1-9])(?:个|幅|张)',value)
        if m:return chinese.get(m.group(1),int(m.group(1)) if m.group(1).isdigit() else 1)
        m=re.search(word+r'\s*:[^.;。]{0,50}\b(one|two|three|four|five|six|seven|eight|nine)\b[^.;。]{0,30}\b(?:images|frames|plots)\b',value,re.I)
        return english[m.group(1).lower()] if m else 1
    return 'vertical',(count(0),count(1))


def _raster_role_group(group,cap,page,ink):
    declaration=_position_declaration(_native_caption_text(cap,page))
    if declaration is None:return False
    axis,counts=declaration;resources=[]
    for record in ink.page.get_images(full=True):
        if record[9]!=0:continue
        name=record[7]
        for rect in ink.page.get_image_rects(record[0]):
            box=tuple(rect)
            if (min(box[2]-box[0],box[3]-box[1])<25 or _area(box)>page.width*page.height*.45):continue
            if any(_inside(box,o.bbox)>.8 or _inside(o.bbox,box)>.8 for o in group):resources.append((name,box))
    resources=list(dict.fromkeys(resources))
    if len(resources)!=sum(counts):return False
    owners={}
    for name,b in resources:
        owner=ink.removal({name})
        if owner is None:return False
        owners[name]=owner
    union_mask=ink.np.logical_or.reduce([o['mask'] for o in owners.values()]);source_owner={'mask':union_mask}
    if not all(ink.owns(o,source_owner) for o in group):return False
    # Exact stated role cardinalities constrain the source objects. No third
    # independent photo/plot may be silently assigned a left/right identity.
    bands=[]
    for name,b in sorted(resources,key=lambda t:(t[1][0] if axis=='horizontal' else t[1][1])):
        centre=(b[0]+b[2])/2 if axis=='horizontal' else (b[1]+b[3])/2
        match=next((items for c,items in bands if abs(c-centre)<=8),None)
        if match is None:bands.append((centre,[(name,b)]))
        else:match.append((name,b))
    if len(bands)!=2 or tuple(len(items) for c,items in bands)!=counts:return False
    boxes=[_union([b for name,b in items]) for c,items in bands];a,b=boxes
    if axis=='horizontal':
        overlap=max(0,min(a[3],b[3])-max(a[1],b[1]));gap=b[0]-a[2]
        if overlap<min(a[3]-a[1],b[3]-b[1])*.8 or not -2<=gap<=30:return False
    else:
        if _xover(a,b)<.75 or not -2<=b[1]-a[3]<=40:return False
    return True


def _outer_form_tag(owner,page,ink):
    found=[];b=owner['box']
    for line in page.lines:
        m=_ALPHA.match(line.text)
        if line.source!='native' or m is None or line.bbox[3]-line.bbox[1]>24 or len(line.text)>80:continue
        required={i for i,c in enumerate(line.text[:m.end()]) if c.strip()};regions=[r for a,z,r in line.text_regions if z-a==1 and a in required]
        covered={a for a,z,r in line.text_regions if z-a==1 and a in required}
        if covered!=required:continue
        marker=_union(regions)
        if ink.glyph_owned(marker,owner):continue
        if not (-1<=marker[1]-b[3]<=22 and _xover(line.bbox,b)>.5):continue
        if abs((line.bbox[0]+line.bbox[2]-b[0]-b[2])/2)>max(20,(b[2]-b[0])*.08):continue
        found.append((m.group(1).lower(),line))
    return found[0] if len(found)==1 else None


def _form_namespace_group(group,cap,page,ink):
    resources=[]
    forms=[r for r in ink.page.get_xobjects() if r[2]==0]
    if len(forms)>32:return None
    for xref,name,invoker,box in forms:
        if invoker!=0:continue
        owner=ink.removal({name})
        if owner is None or _area(owner['box'])>page.width*page.height*.65:continue
        resources.append(owner)
    # A single imported graphic is a physical container only if removing its
    # actual PDF paint explains every component, including pale external ink.
    declaration=_position_declaration(_native_caption_text(cap,page))
    for owner in resources:
        # An imported Form can contain independent charts. Its physical paint
        # explains the pixels, but a shared native role declaration is also
        # required to assign the two unlabelled bands one title namespace.
        if declaration and len(group)==2 and all(ink.owns(o,owner) for o in group):
            support=_union([o.bbox for o in group])
            a,b=sorted((o.bbox for o in group),key=lambda r:r[0] if declaration[0]=='horizontal' else r[1])
            if declaration[0]=='horizontal':
                overlap=max(0,min(a[3],b[3])-max(a[1],b[1]))
                aligned=overlap>=min(a[3]-a[1],b[3]-b[1])*.8 and -2<=b[0]-a[2]<=30
            else:
                aligned=_xover(a,b)>=.75 and -2<=b[1]-a[3]<=40
            if aligned and _area(support)>=_area(owner['box'])*.55:return group
    tagged=[(tag,owner) for owner in resources if (tag:=_outer_form_tag(owner,page,ink)) is not None]
    if len(tagged)<2:return None
    main_box=_union([owner['box'] for tag,owner in tagged]);shared=[]
    for owner in resources:
        b=owner['box']
        if any(owner is w for tag,w in tagged):continue
        # A common source legend must lie in the true top border of each
        # participating panel; a separate external thin chart is not borrowed.
        if not (b[3]-b[1]<=20 and b[2]-b[0]>=(main_box[2]-main_box[0])*.6
                and 0<=main_box[1]-b[3]<=20):continue
        lines=[l for l in page.lines if l.source=='native' and _inside(l.bbox,b)>.85
               and re.search(r'[A-Za-z\u4e00-\u9fff]',l.text) and l.text_regions]
        if len(lines)<3 or max(l.bbox[1] for l in lines)-min(l.bbox[1] for l in lines)>4:continue
        # Proven source ink, rather than the legend's broad rectangular hull,
        # must participate in at least two original component observations.
        touched=0
        for obj in group:
            x0,y0,x1,y1=[int(round(v*2)) for v in obj.bbox]
            if int(owner['mask'][max(y0,0):min(y1,ink.height),max(x0,0):min(x1,ink.width)].sum())>=16:touched+=1
        if touched>=2:shared.append(owner)
    owners=[]
    for tag,owner in tagged:
        mask=owner['mask'].copy()
        for extra in shared:mask|=extra['mask']
        proof=dict(owner,mask=mask);members=[o for o in group if ink.owns(o,proof)]
        if not members:continue
        support=_union([o.bbox for o in members])
        if _area(support)<_area(owner['box'])*.5:continue
        owners.append((tag[0],tag[1],owner,members))
    if len(owners)<2:return None
    vertical=all(_xover(a[2]['box'],b[2]['box'])>.75 for a in owners for b in owners)
    owners.sort(key=lambda e:(e[2]['box'][1],e[2]['box'][0]) if vertical else (e[2]['box'][0],e[2]['box'][1]))
    tags=[t for t,l,o,m in owners]
    if tags!=[chr(ord('a')+i) for i in range(len(tags))]:return None
    selected=[o for t,l,w,m in owners for o in m]
    if len({id(o) for o in selected})!=len(selected):return None
    for a,b in zip(owners,owners[1:]):
        left,right=a[2]['box'],b[2]['box']
        if vertical:
            if _xover(left,right)<.75 or not 0<=right[1]-left[3]<=55:return None
        else:
            overlap=max(0,min(left[3],right[3])-max(left[1],right[1]))
            if overlap<min(left[3]-left[1],right[3]-right[1])*.75 or not 0<=right[0]-left[2]<=55:return None
    return selected


def _source_native_group(group,cap,page,ink):
    """Bind imported components through their own native labels or shared axes.

    A Form is only a paint observation. It supplies no common identity without
    a retained total title and a native namespace borne by those components.
    Native panel descriptions are removed as text in a disposable rendering;
    images and drawings remain, so unrelated pale ink still fails ownership.
    """
    box=_union([o.bbox for o in group]);forms=[]
    # Numbered children have their own exclusive native-glyph sequence proof.
    # Shared axes/outer (a,b) source paint cannot repair a missing child marker.
    if any(re.search(r'[（(][a-z]\d+[）)]',normalize_text(l.text),re.I)
           and _area(l.bbox)>0 and _inside(l.bbox,(box[0]-45,box[1]-45,box[2]+45,cap.bbox[3]))>.5
           for l in page.lines):return None
    # Overlapping independent observations do not establish exclusive owners.
    # Preserve them for the dedicated parser/native alias reconciliation.
    if any(a is not b and _inside(a.bbox,b.bbox)>.8
           for a in group for b in group):return None
    for xref,name,parent,b in ink.page.get_xobjects():
        if parent:continue
        owner=ink.removal({name})
        if owner is None or _area(owner['box'])<1000:continue
        b=owner['box']
        if (_inside(b,(box[0]-20,box[1]-20,box[2]+20,box[3]+45))<.9
                or b[3]>cap.bbox[1]+2):continue
        forms.append(owner)
    if not forms or len(forms)>32:return None
    panel_lines=[];tags=[];vocab=[];tokens=[]
    for owner in forms:
        b=owner['box'];local=[];words=set()
        for line in page.lines:
            if line.source!='native' or not line.text_regions:continue
            covered={i for a,z,r in line.text_regions if 0<z-a<=3 and _area(r)>0 for i in range(a,z)}
            if any(i not in covered for i,c in enumerate(line.text) if c.strip()):continue
            tag=_ALPHA.match(line.text)
            if (tag and line.bbox[3]-line.bbox[1]<=30
                    and _xover(line.bbox,b)>.35
                    and (_inside(line.bbox,b)>.7 or -1<=line.bbox[1]-b[3]<=45)
                    and abs((line.bbox[0]+line.bbox[2]-b[0]-b[2])/2)
                       <=max(48,(b[2]-b[0])*.45)):
                local.append(tag.group(1).lower());panel_lines.append(line)
            if (not tag and _inside(line.bbox,b)>.85
                    and ink.glyph_owned(line.bbox,owner)):
                text=normalize_text(line.text).strip()
                if len(re.findall(r'[A-Za-z\u4e00-\u9fff]',text))>=3 and not FIGURE_CAPTION.match(text):
                    words.add(text.casefold())
        tags.append(set(local));vocab.append(words)
        tokens.append({t.casefold() for word in words for t in re.findall(r'[A-Za-z]{3,}',word)
                       if t.casefold() not in {'the','and','for','over','avg','average','length','queue','time','iterations','different','methods'}})
    unique=set().union(*tags)
    labelled=(len(unique)>=2 and unique=={chr(ord('a')+i) for i in range(len(unique))}
              and all(tags))
    if not labelled:
        title=_native_caption_text(cap,page)
        parallel_methods=False
        if (len(forms)==2 and len(tokens[0]&tokens[1])>=2
                and re.search(r'各方法|不同.{0,8}(?:方法|算法)|different methods',title,re.I)
                and cap.bbox[2]-cap.bbox[0]>=(box[2]-box[0])*.6):
            a,b=sorted((o['box'] for o in forms),key=lambda b:b[0])
            parallel_methods=(max(0,min(a[3],b[3])-max(a[1],b[1]))>=min(a[3]-a[1],b[3]-b[1])*.75
                              and abs(a[1]-b[1])<=20 and 0<=b[0]-a[2]<=min(a[2]-a[0],b[2]-b[0])*.6)
        # Shared axes/method legends must connect every source component.
        # A generic "comparison" title and one common font are insufficient.
        seen={0}
        while True:
            extra={i for i in range(len(forms)) if i not in seen and any(
                len(vocab[i]&vocab[j])>=2 for j in seen)}
            if not extra:break
            seen.update(extra)
        if len(forms)<2 or len(seen)!=len(forms) and not parallel_methods:return None
        connected={0}
        while True:
            extra=set()
            for i,a in enumerate(forms):
                if i in connected:continue
                a=a['box']
                for j in connected:
                    b=forms[j]['box'];gx=max(a[0]-b[2],b[0]-a[2],0)
                    oy=max(0,min(a[3],b[3])-max(a[1],b[1]))
                    if ((_xover(a,b)>.3 and _gap(a,b)<=max(20,min(a[3]-a[1],b[3]-b[1])*.2))
                            or (oy>=min(a[3]-a[1],b[3]-b[1])*.75
                                and gx<=max(20,min(a[2]-a[0],b[2]-b[0])*.25))):
                        extra.add(i);break
            if not extra:break
            connected.update(extra)
        if len(connected)!=len(forms) and not parallel_methods:return None
    elif len(forms)==1:
        # Repeated (a,b) namespaces within one Form need named band headings
        # actually repeated in the total title; the Form alone cannot unify them.
        title=_native_caption_text(cap,page);heads=[]
        for line in page.lines:
            if (line.source=='native' and line.bold and _inside(line.bbox,forms[0]['box'])>.85
                    and 2<=len(line.text.strip())<=18 and line.text.strip() in title
                    and ink.glyph_owned(line.bbox,forms[0])):heads.append(line)
        if len({l.text.strip() for l in heads})<2:return None
    mask=ink.np.logical_or.reduce([o['mask'] for o in forms])
    if panel_lines:
        copy=ink.fit.open()
        try:
            copy.insert_pdf(ink.copy,from_page=0,to_page=0);p=copy[0]
            for line in dict.fromkeys(panel_lines):p.add_redact_annot(ink.fit.Rect(line.bbox),fill=None)
            p.apply_redactions(images=ink.fit.PDF_REDACT_IMAGE_NONE,
                graphics=ink.fit.PDF_REDACT_LINE_ART_NONE,text=ink.fit.PDF_REDACT_TEXT_REMOVE)
            pix=p.get_pixmap(matrix=ink.fit.Matrix(2,2),colorspace=ink.fit.csGRAY,alpha=False)
            if (pix.width,pix.height)!=(ink.width,ink.height):return None
            after=ink.np.frombuffer(pix.samples,dtype=ink.np.uint8).reshape(ink.height,ink.width)
            mask|=(ink.base<255)&(after==255)
        finally:copy.close()
    proof={'mask':mask}
    if not all(ink.owns(o,proof) for o in group):return None
    return group


def repair_caption_physical_ownership(objects,document):
    if document is None or not Path(document.path).is_file():return list(objects)
    import pymupdf
    result=list(objects)
    try:source=pymupdf.open(document.path)
    except (OSError,ValueError,RuntimeError):return result
    with source:
        for page in document.pages:
            if page.display_rotation or not 1<=page.number<=len(source) or page.width*page.height>2000000:continue
            caps=[o for o in result if o.kind=='figure_caption' and o.page_number==page.number and _native_caption(o,page)]
            if not caps:continue
            ink=None
            try:
                for cap in caps:
                    group,others=_namespace_group(result,cap,page)
                    if len(group)<2 or _independent_titles(group,cap,others) or _barrier(group,cap,page,result):continue
                    box=_union([o.bbox for o in group])
                    if (_gap(box,cap.bbox)>80 or abs((box[0]+box[2]-cap.bbox[0]-cap.bbox[2])/2)>max(24,(box[2]-box[0])*.12)):continue
                    if ink is None:ink=_PageInk(source,page.number)
                    if not ink.valid:continue
                    selected=group if _raster_role_group(group,cap,page,ink) else _form_namespace_group(group,cap,page,ink)
                    if not selected:selected=_source_native_group(group,cap,page,ink)
                    if not selected or len(selected)<2:continue
                    if _independent_titles(selected,cap,others) or _barrier(selected,cap,page,result):continue
                    joined=replace(_join(selected,'figure'),role='source_proved_caption_components')
                    chosen={id(o) for o in selected};result=[o for o in result if id(o) not in chosen]+[joined]
            except (ValueError,IndexError,RuntimeError):
                # PDF rendering/resource ambiguities cannot erase obligations.
                continue
            finally:
                if ink is not None:ink.close()
    return result
