"""Resolve unlettered component observations with native and source evidence.

The original title remains required. A shared resource alone is insufficient:
the source paint must explain every component, and the components must share
native series/axes, declared roles, or a verified existing composite's ink.
No document fields or source bytes are changed.
"""
from dataclasses import replace
from pathlib import Path
import re
import unicodedata

from .numbering import FIGURE_CAPTION,normalize_text,normalize_label
from .figure_identity_repair import _area,_inside,_union,_xover,_gap,_barrier,_join
from .caption_physical_ownership import _PageInk,_native_caption,_native_caption_text,_independent_titles


def _number(cap):
    match=FIGURE_CAPTION.match(normalize_text(cap.text))
    return normalize_label(match.group('number')) if match else None


def _native_label(line,ink):
    if line.source!='native' or not line.text_regions:return ''
    required={i for i,c in enumerate(line.text) if c.strip()}
    regions={a:b for a,z,b in line.text_regions if z-a==1 and _area(b)>0}
    if not required<=regions.keys():return ''
    # All retained glyph boxes need original ink, rather than an invented
    # cached phrase placed near the graphic. Resource membership is checked
    # separately for labels used to link imported vector plots.
    if not all(ink.glyph_owned(regions[i],{'mask':ink.base<255}) for i in required):return ''
    return unicodedata.normalize('NFKC',line.text).strip()


def _series_key(text):
    value=unicodedata.normalize('NFKC',text).lower().strip(' []()“”"')
    value=re.split(r'\s+w/(?:o)?\b',value)[0]
    return re.sub(r'\s+','',value)


def _labels(obj,page,ink,owner=None):
    labels=set()
    for line in page.lines:
        if _inside(line.bbox,obj.bbox)<.8:continue
        text=_native_label(line,ink)
        if not text or len(text)>45 or FIGURE_CAPTION.match(normalize_text(text)):continue
        # Pure tick numbers cannot prove common meaning. Angular ticks are a
        # typed axis attribute, retained only with their actual degree glyph.
        if not re.search(r'[A-Za-z\u4e00-\u9fff]|°',text):continue
        if owner is not None and not ink.glyph_owned(line.bbox,owner):continue
        labels.add(_series_key(text))
    return labels


def _connected(labels,minimum=2):
    seen={0}
    while True:
        added={i for i in range(len(labels)) if i not in seen and any(len(labels[i]&labels[j])>=minimum for j in seen)}
        if not added:return len(seen)==len(labels)
        seen|=added


def _palette(rgb,box):
    import numpy as np
    x0,y0,x1,y1=[int(round(v)) for v in box]
    pixels=rgb[max(y0,0):min(y1,rgb.shape[0]),max(x0,0):min(x1,rgb.shape[1])].reshape(-1,3)
    if len(pixels)<32:return []
    # Flat series paint survives rasterisation; photographic texture does not
    # establish a shared series. Keep repeated saturated exact source colours.
    p=pixels.astype(int);selected=p[(p.max(axis=1)-p.min(axis=1)>45)&(p.min(axis=1)<220)]
    if not len(selected):return []
    # Imported chart bitmaps are resampled at subpixel offsets. Pool nearby
    # colours before counting instead of demanding repeated exact RGB bytes.
    colors,counts=np.unique((selected//16)*16+8,axis=0,return_counts=True);order=np.argsort(counts)[::-1];out=[]
    for i in order:
        if counts[i]<max(20,len(pixels)*.00015):break
        c=colors[i]
        if all(np.linalg.norm(c-a)>35 for a in out):out.append(c)
        if len(out)==10:break
    return out


def _shared_palette(palettes,minimum):
    import numpy as np
    if not palettes or not palettes[0]:return False
    def chroma(c):return (c-c.min())*255/max(1,c.max()-c.min())
    unique=[]
    for a in palettes[0]:
        c=chroma(a)
        if all(np.linalg.norm(c-v)>70 for v in unique):unique.append(c)
    exact=sum(all(any(np.linalg.norm(a-b)<=35 for b in values) for values in palettes[1:]) for a in palettes[0])
    typed=sum(all(any(np.linalg.norm(a-chroma(b))<=65 for b in values) for values in palettes[1:]) for a in unique)
    return exact>=minimum or typed>=minimum


def _role_labels(group,cap,page,ink):
    support=_union([o.bbox for o in group]);found=[]
    for line in page.lines:
        if not (support[1]-18<=line.bbox[1]<=support[3]+28):continue
        if _inside(line.bbox,cap.bbox)>.5:continue
        text=_native_label(line,ink)
        if not text or len(text)>35:continue
        members=[i for i,o in enumerate(group) if _xover(o.bbox,line.bbox)>.6 and _gap(o.bbox,line.bbox)<=28]
        if members:found.append((members,text))
    # A comparison/result namespace explicitly distinguishes input, reference
    # and output roles; merely short titles below unrelated photos do not.
    inputs=[m for m,t in found if re.search(r'输入|\binput\b|^主体$',t,re.I)]
    outputs=[m for m,t in found if re.search(r'标注|本方法|梯度|BRDF|渲染|(?:比例|位置关系)异常|视角不匹配|\b(?:mask|output|ground.?truth)\b',t,re.I)]
    named_methods=[m for m,t in found if re.fullmatch(r'[A-Za-z][A-Za-z\d_-]{1,20}',t)]
    covered={i for members in inputs+outputs+named_methods for i in members}
    if inputs and len(outputs)>=2 and covered==set(range(len(group))):return True
    title=_native_caption_text(cap,page)
    # Two explicitly named power-consumption roles have separately retained
    # native axes. The total title names both devices and the common metric.
    axes=[]
    for obj in group:
        axes.append(' '.join(_labels(obj,page,ink)))
    if len(group)==2 and re.search(r'功耗',title):
        return any('耳机功耗' in x for x in axes) and any('手机功耗' in x for x in axes) and '耳机' in title and '手机' in title
    return False


def _same_composite_ink(group,ink,resources):
    # A duplicate observation may protrude into blank crop margins. Compare
    # the actual source paint against an existing composite, not its envelope.
    established=[o for o in group if o.role in {'native_graphic_container','declared_composite_figure'}]
    for parent in established:
        if not all(_inside(o.bbox,parent.bbox)>.75 for o in group):continue
        for owner in resources:
            if not all(ink.owns(o,owner) for o in group):continue
            x0,y0,x1,y1=[int(round(v*2)) for v in parent.bbox]
            existing=ink.np.zeros_like(owner['mask']);existing[max(y0,0):min(y1,ink.height),max(x0,0):min(x1,ink.width)]=True
            if all(not ((ink.base<255)&owner['mask']&~existing)[max(int(round(o.bbox[1]*2)),0):min(int(round(o.bbox[3]*2)),ink.height),max(int(round(o.bbox[0]*2)),0):min(int(round(o.bbox[2]*2)),ink.width)].any() for o in group):return True
    return False


def _native_overlay(page,ink):
    mask=ink.np.zeros_like(ink.base,dtype=bool)
    for line in page.lines:
        if not _native_label(line,ink) or FIGURE_CAPTION.match(normalize_text(line.text)):continue
        for a,z,b in line.text_regions:
            if z-a!=1 or not line.text[a:z].strip():continue
            x0,y0,x1,y1=[int(round(v*2)) for v in b]
            mask[max(y0,0):min(y1,ink.height),max(x0,0):min(x1,ink.width)]=True
    return mask&(ink.base<255)


def _raster_legend_words(rgb,box):
    """Describe repeated bitmap legend swatches and word ink, without OCR."""
    import numpy as np
    x0,y0,x1,y1=[int(round(v)) for v in box]
    crop=rgb[max(y0,0):min(y1,y0+40),max(x0,0):min(x1,rgb.shape[1])].astype(int)
    if crop.shape[0]<10 or crop.shape[1]<40:return []
    colors=_palette(rgb,box);out=[]
    black=(crop.max(axis=2)<190)&(crop.max(axis=2)-crop.min(axis=2)<20)
    for c in colors:
        hue=(c-c.min())/max(1,c.max()-c.min());p=crop-crop.min(axis=2,keepdims=True);p=p/np.maximum(1,p.max(axis=2,keepdims=True))
        mask=(np.linalg.norm(p-hue,axis=2)<.18)&(crop.max(axis=2)-crop.min(axis=2)>45)&(crop.min(axis=2)<210)
        for y,row in enumerate(mask):
            xs=np.where(row)[0]
            if not len(xs):continue
            starts=np.r_[0,np.where(np.diff(xs)>1)[0]+1];ends=np.r_[starts[1:]-1,len(xs)-1]
            for a,z in zip(starts,ends):
                left,right=int(xs[a]),int(xs[z]);w=right-left+1
                if not 8<=w<=25 or left>crop.shape[1]*.84:continue
                if sum(mask[max(0,y-3):min(len(mask),y+4),left:right+1].sum(axis=1)>=w*.75)>3:continue
                word=black[max(0,y-5):min(len(mask),y+6),right+2:min(crop.shape[1],right+42)]
                yy,xx=np.where(word)
                if len(xx)<12:continue
                word=word[yy.min():yy.max()+1,xx.min():xx.max()+1]
                if not 6<=word.shape[1]<=32 or not 4<=word.shape[0]<=10:continue
                key=(np.linspace(0,word.shape[0]-1,12).round().astype(int),np.linspace(0,word.shape[1]-1,48).round().astype(int))
                sample=word[key[0]][:,key[1]]
                if any(np.linalg.norm(hue-h)<.2 for h,w in out):continue
                out.append((hue,sample))
    return out


def _shared_raster_legends(group,rgb):
    import numpy as np
    descriptions=[_raster_legend_words(rgb,b) for o in group for b in (o.panel_boxes or (o.bbox,))]
    if len(descriptions)<2 or any(len(x)<2 for x in descriptions):return False
    def same(a,b):
        h,u=a;k,v=b
        return np.linalg.norm(h-k)<=.25 and 2*(u&v).sum()/max(1,u.sum()+v.sum())>.72
    return all(sum(any(same(a,b) for b in other) for a in descriptions[0])>=2 for other in descriptions[1:])


def _shared_legend_strip(group,cap,page,ink,resources,rgb):
    from .caption_rules import _matches
    if len(group)!=2:return False
    anchors=[o for o in group if len(o.panel_boxes)>=2 and _matches(o,cap)]
    if len(anchors)!=1:return False
    anchor=anchors[0];legend=next(o for o in group if o is not anchor);b=legend.bbox;a=anchor.bbox
    if not (b[2]-b[0]>=(a[2]-a[0])*.65 and b[3]-b[1]<=25 and (b[2]-b[0])/max(b[3]-b[1],1)>=10 and -3<=a[1]-b[3]<=20):return False
    if _labels(legend,page,ink) or not any(ink.owns(legend,w) for w in resources):return False
    palettes=[_palette(rgb,b),_palette(rgb,a)]
    if not _shared_palette(palettes,3):return False
    # A real legend contains several filled horizontal series swatches.
    # Thin curves or a separate small chart with similar colours are retained.
    np=ink.np;x0,y0,x1,y1=[int(round(v)) for v in b];crop=rgb[max(y0,0):min(y1,rgb.shape[0]),max(x0,0):min(x1,rgb.shape[1])].astype(int);swatches=0
    for color in palettes[0]:
        ys,xs=np.where(np.linalg.norm(crop-color,axis=2)<16)
        if not len(xs):continue
        w=xs.max()-xs.min()+1;h=ys.max()-ys.min()+1
        if w>=6 and h>=2 and w>=h*1.8 and len(xs)>=w*h*.75:swatches+=1
    return swatches>=3 and len(_labels(anchor,page,ink))>=2


def _dashboard_field(rgb,box):
    """A screenshot field needs uniform UI paint and repeated grid rules."""
    import numpy as np
    x0,y0,x1,y1=[int(round(v)) for v in box]
    crop=rgb[max(y0,0):min(y1,rgb.shape[0]),max(x0,0):min(x1,rgb.shape[1])].astype(int)
    if crop.shape[0]<60 or crop.shape[1]<150:return False
    gray=crop.mean(axis=2);neutral=crop.max(axis=2)-crop.min(axis=2)<22
    if neutral.mean()<.6:return False
    background=np.bincount((gray[neutral]//8).astype(int)).argmax()*8+4
    if (np.abs(gray-background)<16).mean()<.55:return False
    # Long rules recur at several ordinates, with a wider toolbar/header
    # region. A solid rectangle, photo or isolated curve is insufficient.
    ys=np.where(((np.abs(gray-background)>7)&neutral).mean(axis=1)>.45)[0]
    bands=np.split(ys,np.where(np.diff(ys)>1)[0]+1)
    short=[b for b in bands if 0<len(b)<=4]
    header=[b for b in bands if len(b)>=6]
    return len(short)>=3 and bool(header) and max(b[0] for b in short)-min(b[0] for b in short)>crop.shape[0]*.45


def _performance_dashboards(group,cap,page,document,ink,resources,rgb):
    title=_native_caption_text(cap,page)
    if not re.search(r'性能|performance',title,re.I) or not re.search(r'系统|system',title,re.I):return False
    number=_number(cap);declared=False
    for p in document.pages:
        if p.number not in (page.number-1,page.number,page.number+1):continue
        lines=sorted(p.lines,key=lambda l:(l.bbox[1],l.bbox[0]))
        for i,l in enumerate(lines):
            text=normalize_text(l.text)
            if l.source!='native' or FIGURE_CAPTION.match(text):continue
            refs=re.finditer(r'(?:图|Figure|Fig\.?)\s*([A-Z]?\d+(?:[.\-]\d+)*)',text,re.I)
            if not any(normalize_label(m.group(1))==number for m in refs):continue
            context=' '.join(n.text for n in lines[max(0,i-3):i+4] if n.source=='native')
            if re.search(r'系统|system',context,re.I) and re.search(r'负载|并发|性能|performance|load|concurren',context,re.I):declared=True
    if not declared:return False
    # Bind every observed member to actual independent raster paint. The
    # common reference explains dashboard views of the same system; source
    # field structure verifies their type rather than assuming it from boxes.
    selected=[]
    for owner in resources:
        if len(owner['names'])!=1 or 'box' not in owner:continue
        b=owner['box']
        if any(_inside(b,o.bbox)>.9 and _area(b)>.15*_area(o.bbox) for o in group) and _dashboard_field(rgb,b):
            if owner['names'] not in [a['names'] for a in selected]:selected.append(owner)
    if not 2<=len(selected)<=8:return False
    mask=ink.np.logical_or.reduce([o['mask'] for o in selected])
    return all(ink.owns(o,{'mask':mask}) for o in group)


def _semantic_source_group(group,cap,page,document,ink,resources,rgb):
    if _shared_legend_strip(group,cap,page,ink,resources,rgb):return True
    if len(group)==2:
        from .caption_rules import _matches
        anchors=[o for o in group if o.role=='shared_caption_panels' and _matches(o,cap)]
        title=_native_caption_text(cap,page)
        if len(anchors)==1 and re.search(r'消融|ablation',title,re.I):
            anchor=anchors[0];chart=next(o for o in group if o is not anchor)
            labels=_labels(anchor,page,ink)
            declaration=re.sub(r'\s+','',unicodedata.normalize('NFKC',title).lower())
            declared=[t for t in labels if t in declaration]
            if len(declared)>=3 and any(ink.owns(chart,w) for w in resources) and _shared_palette([_palette(rgb,o.bbox) for o in group],3):return True
    owners=[o for o in resources if all(ink.owns(g,o) for g in group)]
    if not owners:return False
    if _same_composite_ink(group,ink,resources) or _role_labels(group,cap,page,ink):return True
    for owner in owners:
        if _connected([_labels(o,page,ink,owner) for o in group]):return True
    title=_native_caption_text(cap,page)
    if re.search(r'可视化实验(?:和|与)实验数据',title) and len(group)==2:
        # An actual single imported form paints both the illustration and its
        # measurements; the native total title explicitly declares both roles.
        return any(len(o['names'])==1 for o in owners)
    palettes=[_palette(rgb,o.bbox) for o in group]
    # Three matched flat series colours and explicit native comparison roles
    # can connect a chart bitmap to its visualised outcomes without OCR.
    labels=[_labels(o,page,ink) for o in group]
    named=[x for x in labels if len(x)>=3]
    if named and _shared_palette(palettes,3) and re.search(r'对比|比较|消融|compar|ablation',title,re.I):return True
    if re.search(r'对比|比较|compar',title,re.I) and _shared_raster_legends(group,rgb):return True
    if _performance_dashboards(group,cap,page,document,ink,resources,rgb):return True
    return False


def repair_unlettered_caption_ownership(objects,document):
    if document is None or not Path(document.path).is_file():return list(objects)
    result=list(objects)
    from .caption_rules import detect_caption_rules
    pending={f['location']['page_number'] for f in detect_caption_rules(result,[13],document)['13']['findings']}
    if not pending:return result
    import pymupdf,numpy as np
    try:source=pymupdf.open(document.path)
    except (OSError,ValueError,RuntimeError):return result
    with source:
        for page in document.pages:
            if page.number not in pending or page.display_rotation or not 1<=page.number<=len(source):continue
            caps=[o for o in result if o.page_number==page.number and o.kind=='figure_caption' and _native_caption(o,page)]
            if not caps:continue
            # Bilingual/continuation aliases carry the same namespace.
            titles={}
            for cap in caps:
                key=_number(cap)
                if key not in titles or _area(cap.bbox)>_area(titles[key].bbox):titles[key]=cap
            ink=None
            try:
                for cap in sorted(titles.values(),key=lambda c:c.bbox[1]):
                    aliases=[c for c in caps if _number(c)==_number(cap)]
                    others=[o for o in result if o.page_number==page.number and o.kind.endswith('_caption') and _number(o)!=_number(cap)]
                    low=max((c.bbox[3] for c in others if c.bbox[3]<=cap.bbox[1]),default=page.height*.09)
                    group=[o for o in result if o.kind=='figure' and o.page_number==page.number and low<=o.bbox[1] and o.bbox[3]<=cap.bbox[1]+3]
                    # A bilingual long title's continuation belongs to its
                    # verified native title region, rather than a paragraph
                    # interrupting the component namespace. Use a local view;
                    # the supplied page and its offsets stay byte-identical.
                    barriers=replace(page,lines=tuple(l for l in page.lines if not any(_inside(l.bbox,c.bbox)>.5 for c in aliases)))
                    if len(group)<2:continue
                    support=_union([o.bbox for o in group])
                    if any(c.kind=='figure_caption' and _inside(c.bbox,support)>.65 for c in others):continue
                    from .caption_rules import _matches
                    outside=[o for o in result if o.kind=='figure' and o.page_number==page.number and o not in group]
                    # A prior below-figure title with its own actual preceding
                    # body cannot be borrowed by the next group's first panel.
                    # Otherwise preserve every closer dedicated figure title,
                    # including an additional title beside the total title.
                    unowned=[c for c in others if not (c.bbox[3]<=support[1] and any(o.bbox[3]<=c.bbox[1]+3 and _matches(o,c) for o in outside))]
                    if _independent_titles(group,cap,unowned):continue
                    if _barrier(group,cap,barriers,result):continue
                    if ink is None:
                        ink=_PageInk(source,page.number)
                        pix=source[page.number-1].get_pixmap(matrix=pymupdf.Matrix(1,1),colorspace=pymupdf.csRGB,alpha=False)
                        rgb=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,3)
                        names={n for n,a,b in ink.spans};resources=[]
                        for name in names:
                            owner=ink.removal({name})
                            if owner is not None:resources.append(owner)
                        if resources:
                            resources.append({'names':tuple(sorted(names)),'mask':np.logical_or.reduce([o['mask'] for o in resources])})
                            native=_native_overlay(page,ink)
                            resources += [dict(o,mask=o['mask']|native) for o in list(resources)]
                    if not _semantic_source_group(group,cap,page,document,ink,resources,rgb):continue
                    joined=replace(_join(group,'figure'),role='source_unlettered_composite')
                    ids={id(o) for o in group};result=[o for o in result if id(o) not in ids]+[joined]
            finally:
                if ink is not None:ink.close()
    return result
