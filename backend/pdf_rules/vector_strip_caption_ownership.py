"""Bind annotated vector strips by their actual common cell partition."""
from dataclasses import replace
from pathlib import Path
from collections import Counter
import re
import unicodedata
from .figure_identity_repair import _inside,_union,_join,_area
from .numbering import FIGURE_CAPTION,FIGURE_REFERENCE,normalize_label,normalize_text
from .caption_context import body_font
from .mineru_layout import caption_identity
from .descriptive_caption_ownership import _declared_lines
from .caption_physical_ownership import _PageInk

def _distance(a,b):
    return max(a[0]-b[2],b[0]-a[2],a[1]-b[3],b[1]-a[3],0)

def _partition(frame,drawings):
    b=tuple(frame['rect']);cuts=[]
    for d in drawings:
        for item in d['items']:
            if item[0]!='l':continue
            a,z=item[1:3]
            if abs(a.x-z.x)<.2 and abs(min(a.y,z.y)-b[1])<.2 and abs(max(a.y,z.y)-b[3])<.2 and b[0]<a.x<b[2]:cuts.append(round(a.x,1))
    return set(cuts)

def _path_mask(drawings,ink,page):
    with ink.fit.open() as pdf:
        p=pdf.new_page(width=page.width,height=page.height)
        for d in drawings:
            shape=p.new_shape()
            for item in d['items']:
                if item[0]=='l':shape.draw_line(item[1],item[2])
                elif item[0]=='re':shape.draw_rect(item[1])
                elif item[0]=='c':shape.draw_bezier(*item[1:])
                else:return None
            shape.finish(width=d.get('width') or 0,color=d.get('color'),fill=d.get('fill'),
                lineCap=max(d.get('lineCap') or (0,)),lineJoin=d.get('lineJoin') or 0,
                closePath=d.get('closePath',False),even_odd=d.get('even_odd') or False,
                dashes=d.get('dashes'),
                stroke_opacity=d.get('stroke_opacity') or 1,fill_opacity=d.get('fill_opacity') or 1)
            shape.commit()
        pix=p.get_pixmap(matrix=ink.fit.Matrix(2,2),colorspace=ink.fit.csGRAY,alpha=False)
        return ink.np.frombuffer(pix.samples,dtype=ink.np.uint8).reshape(pix.height,pix.width)<255

def _text_objects(data):
    """Find real BT/ET operators, never tokens inside PDF strings or images.

    Explicit rendering modes and malformed lexical structures fail closed.
    The supported source uses the default fill mode, so its text state can
    be preserved while making one actual text object invisible in a copy.
    """
    i=0;n=len(data);start=None;out=[];depth=0
    while i<n:
        c=data[i]
        if c in b'\x00\t\n\r\x0c ':i+=1;continue
        if c==37:
            z=data.find(b'\n',i);i=n if z<0 else z+1;continue
        if c==40:
            i+=1;balance=1
            while i<n and balance:
                if data[i]==92:i+=2;continue
                if data[i]==40:balance+=1
                if data[i]==41:balance-=1
                i+=1
            if balance:return []
            continue
        if c==60 and data[i:i+2]!=b'<<':
            z=data.find(b'>',i+1)
            if z<0:return []
            i=z+1;continue
        if c in b'[]' or data[i:i+2] in (b'<<',b'>>'):
            depth+=1 if c==91 or data[i:i+2]==b'<<' else -1
            if depth<0:return []
            i+=2 if data[i:i+2] in (b'<<',b'>>') else 1;continue
        a=i
        if c==47:i+=1
        while i<n and data[i] not in b'\x00\t\n\r\x0c ()<>[]{}/%':i+=1
        if i==a:return []
        token=data[a:i]
        if token in (b'BI',b'Tr'):return []
        if depth:continue
        if token==b'BT':
            if start is not None:return []
            start=a
        elif token==b'ET':
            if start is None:return []
            out.append((start,i));start=None
    return out if start is None and depth==0 else []

def _filled_glyphs(page):
    result=Counter()
    for span in page.get_texttrace():
        if span['type']!=0:continue
        for code,glyph,origin,box in span['chars']:
            result[(span['font'],round(span['size'],3),unicodedata.normalize('NFKC',chr(code)),
                    tuple(round(v,3) for v in (*origin,*box)))]+=1
    return result

def _native_text_paint(ink,lines):
    """Prove actual original text paint, including italic glyph overhang.

    Changing only Tr in a disposable source copy preserves fonts, geometry,
    paths and colours. A text object is admitted only when every disappearing
    glyph has the same native character and original glyph box. Independent
    pale ink under a glyph remains after suppression and cannot be claimed.
    """
    objects=_text_objects(ink.data);original=_filled_glyphs(ink.page)
    approved=set()
    regions=[(unicodedata.normalize('NFKC',l.text[a:z]),box) for l in lines for a,z,box in l.text_regions
             if z-a==1 and _area(box)>0]
    for key in original:
        box=key[3][2:]
        # A PDF font can lack a Unicode map for its actual accent glyph.
        # Its original glyph box still has to match one retained native
        # character exactly; no neighbouring or invented region is admitted.
        if any((key[2]==text or key[2]=='\ufffd') and max(abs(a-b) for a,b in zip(box,region))<.05 for text,region in regions):approved.add(key)
    mask=ink.np.zeros_like(ink.base,dtype=bool)
    try:
        for a,z in objects:
            data=ink.data[:a+2]+b' 3 Tr '+ink.data[a+2:z-2]+b' 0 Tr '+ink.data[z-2:]
            ink.copy.update_stream(ink.xref,data)
            remaining=_filled_glyphs(ink.page);lost=original-remaining
            if not lost or remaining-original or any(k not in approved and not k[2].isspace() for k in lost):continue
            pix=ink.page.get_pixmap(matrix=ink.fit.Matrix(2,2),colorspace=ink.fit.csGRAY,alpha=False)
            after=ink.np.frombuffer(pix.samples,dtype=ink.np.uint8).reshape(pix.height,pix.width)
            if after.shape==ink.base.shape:mask|=(ink.base<255)&(after==255)
    finally:ink.copy.update_stream(ink.xref,ink.data)
    return mask

def repair_vector_strip_caption_ownership(objects,document):
    result=list(objects)
    if document is None or not Path(document.path).is_file():return result
    from .caption_rules import detect_caption_rules
    pending={f['page'] for f in detect_caption_rules(result,[13],document)['13']['findings']}
    if not pending:return result
    import pymupdf
    with pymupdf.open(document.path) as source:
        for page in document.pages:
            if page.number not in pending or page.display_rotation:continue
            caps=[c for c in result if c.kind=='figure_caption' and c.page_number==page.number]
            for cap in caps:
                lines=_declared_lines(cap,page)
                if not lines:continue
                prior=max((c.bbox[3] for c in caps if c is not cap and c.bbox[3]<cap.bbox[1]),default=page.height*.1)
                group=[o for o in result if o.kind=='figure' and o.page_number==page.number and prior<o.bbox[1]<o.bbox[3]<=cap.bbox[1]+2]
                if len(group)<2:continue
                box=_union([o.bbox for o in group]);size=body_font(page)
                drawings=[d for d in source[page.number-1].get_drawings() if _inside(tuple(d['rect']),box)>.9 or (d['rect'].width==0 and box[0]<=d['rect'].x0<=box[2] and box[1]<=d['rect'].y0<=d['rect'].y1<=box[3])]
                frames=[d for d in drawings if len(d['items'])==1 and d['items'][0][0]=='re' and d['type']=='s' and d['rect'].width>page.width*.5 and 5<d['rect'].height<max(20,size*2) and d['rect'].width/d['rect'].height>12]
                if not 2<=len(frames)<=8:continue
                frames.sort(key=lambda d:d['rect'].y0);first=frames[0]['rect']
                if any(abs(d['rect'].x0-first.x0)>.3 or abs(d['rect'].width-first.width)>.3 or abs(d['rect'].height-first.height)>.3 for d in frames):continue
                partitions=[_partition(d,drawings) for d in frames]
                rich=[c for c in partitions if len(c)>=4]
                if len(rich)<2 or len(set.intersection(*rich))<4:continue
                number=normalize_label(FIGURE_CAPTION.match(normalize_text(cap.text)).group('number'))
                introductions=[l for l in page.lines if l.source=='native' and box[1]-80<=l.bbox[3]<=box[1] and any(normalize_label(m.group('number'))==number for m in FIGURE_REFERENCE.finditer(normalize_text(l.text)))]
                if not introductions:continue
                annotations=[l for l in page.lines if l.source=='native' and _inside(l.bbox,box)>.6]
                if any(l.font_size>=size*.95 and (len(re.findall(r'[\u4e00-\u9fff]',l.text))>=10 or len(re.findall(r'[A-Za-z]{2,}',l.text))>=5) for l in annotations):continue
                if any(sum(1 for l in annotations if _inside(l.bbox,(r['rect'].x0-2,r['rect'].y0-3,r['rect'].x1+2,r['rect'].y1+3))>.7 and re.fullmatch(r'[01\s·.]+',l.text))<2 for r in frames):continue
                selected=list(frames)
                # Arrow stems deliberately stop before a cell border. Admit
                # their endpoint-sized gap; a detached dot supplies no stem.
                for dr in drawings:
                    if dr in selected or len(dr['items'])!=1 or dr['items'][0][0]!='l':continue
                    a,z=dr['items'][0][1:3]
                    if abs(a.x-z.x)>.2:continue
                    if any(r['rect'].x0<a.x<r['rect'].x1 and abs(a.y-z.y)>=r['rect'].height*.9
                           and (0<=r['rect'].y0-max(a.y,z.y)<=r['rect'].height*.51
                                or 0<=min(a.y,z.y)-r['rect'].y1<=r['rect'].height*.51) for r in frames):selected.append(dr)
                while True:
                    more=[d for d in drawings if not any(d is a for a in selected) and any(_distance(tuple(d['rect']),tuple(a['rect']))<=2.5 for a in selected)]
                    if not more:break
                    selected.extend(more)
                ink=_PageInk(source,page.number)
                try:
                    if not ink.valid:continue
                    mask=_path_mask(selected,ink,page)
                    if mask is None:continue
                    mask|=_native_text_paint(ink,annotations+lines)
                    if not all(ink.owns(o,{'mask':mask}) for o in group):continue
                    joined=replace(_join(group,'figure'),role='proven_shared_vector_partition',caption_owner_id=caption_identity(cap))
                    gone={id(o) for o in group};result=[o for o in result if id(o) not in gone]+[joined]
                finally:ink.close()
    return result
