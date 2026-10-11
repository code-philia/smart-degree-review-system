"""Verify caption-declared panel letters directly in original raster paint."""
from dataclasses import replace
from pathlib import Path
import re
from .figure_identity_repair import _inside,_union,_join,_xover
from .source_native_caption_ownership import _owners,_declared,_combined_mask,_OriginalPageInk
from .caption_physical_ownership import _PageInk
from .descriptive_caption_ownership import _declared_lines
from .mineru_layout import caption_identity
from .numbering import normalize_text

_TAG=re.compile(r'^\s*[（(]\s*([a-z])\s*[）)]\s*$',re.I)

def _read_region(source_page,box,scale):
    import pymupdf,numpy as np
    from .local_ocr import _read_tile
    pix=source_page.get_pixmap(clip=pymupdf.Rect(box),matrix=pymupdf.Matrix(scale,scale),colorspace=pymupdf.csGRAY,alpha=False)
    gray=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width)
    out=[]
    # pixmap coordinates are rounded to the rendered clip origin.
    for hit in _read_tile(gray):
        m=_TAG.fullmatch(hit.text)
        if not m or hit.score<.98 or hit.detection_score<.5:continue
        b=tuple((v+(pix.x if i%2==0 else pix.y))/scale for i,v in enumerate(hit.bbox))
        out.append((m.group(1).lower(),b))
    return out

def _bitmap(source_page,record):
    """Read the owning image's own samples and transparency, never neighbours."""
    import pymupdf,numpy as np
    pix=pymupdf.Pixmap(source_page.parent,record[0])
    if pix.colorspace is None:return None
    gray=pymupdf.Pixmap(pymupdf.csGRAY,pix)
    samples=np.frombuffer(gray.samples,dtype=np.uint8).reshape(gray.height,gray.width,gray.n)[:,:,0].copy()
    if record[1]:
        alpha=pymupdf.Pixmap(source_page.parent,record[1])
        if (alpha.height,alpha.width)!=(gray.height,gray.width) or alpha.n!=1:return None
        opacity=np.frombuffer(alpha.samples,dtype=np.uint8).reshape(alpha.height,alpha.width).astype(np.uint32)
        samples=((samples.astype(np.uint32)*opacity+255*(255-opacity)+127)//255).astype(np.uint8)
    return samples

def _read_bitmap_region(gray,placement,matrix,box,scale):
    import pymupdf,numpy as np,cv2
    from .local_ocr import _read_tile
    # Restrict source reading to upright placements. A rotated or mirrored
    # source must prove its own placement through a separate supported route.
    if abs(matrix.b)>.001 or abs(matrix.c)>.001 or matrix.a<=0 or matrix.d<=0:return []
    h,w=gray.shape
    x0=max(0,int((box[0]-matrix.e)/matrix.a*w));y0=max(0,int((box[1]-matrix.f)/matrix.d*h))
    x1=min(w,int(np.ceil((box[2]-matrix.e)/matrix.a*w)));y1=min(h,int(np.ceil((box[3]-matrix.f)/matrix.d*h)))
    if x1<=x0 or y1<=y0:return []
    crop=np.ascontiguousarray(gray[y0:y1,x0:x1])
    width=max(1,round((x1-x0)*matrix.a/w*scale));height=max(1,round((y1-y0)*matrix.d/h*scale))
    image=cv2.resize(crop,(width,height),interpolation=cv2.INTER_CUBIC)
    rx=width/(x1-x0);ry=height/(y1-y0);out=[]
    for hit in _read_tile(image):
        m=_TAG.fullmatch(hit.text)
        if not m or hit.score<.98 or hit.detection_score<.5:continue
        b=pymupdf.Rect((x0+hit.bbox[0]/rx)/w,(y0+hit.bbox[1]/ry)/h,
                       (x0+hit.bbox[2]/rx)/w,(y0+hit.bbox[3]/ry)/h)*matrix
        out.append((m.group(1).lower(),tuple(b)))
    return out

def _source_markers(owner,objects,source_page,ink,joint):
    found=[];b=owner['box']
    # Paint difference bounds omit blank paper around letters. Read the actual
    # original image placement, retaining the physical glyph ownership gate.
    placements=[(record,rect,matrix) for record in source_page.get_images(full=True) if record[7] in owner['names']
                for rect,matrix in source_page.get_image_rects(record[0],transform=True)]
    near=[r for r in placements if _inside(b,tuple(r[1]))>.9]
    if len(near)!=1:return []
    record,rect,matrix=near[0];b=tuple(rect);gray=_bitmap(source_page,record)
    if gray is None:return []
    read=lambda region,scale:_read_bitmap_region(gray,rect,matrix,region,scale)
    # Re-read cached OCR labels: a parser transcription alone never supplies
    # a letter namespace. The actual source image must paint that marker.
    for obj in objects:
        m=_TAG.fullmatch(normalize_text(obj.text)) if obj.kind=='text' and obj.role in {'chart_caption','image_caption'} else None
        if not m or _inside(obj.bbox,b)<.8:continue
        r=(obj.bbox[0]-3,obj.bbox[1]-3,obj.bbox[2]+3,obj.bbox[3]+3)
        for letter,box in read(r,6):
            if letter==m.group(1).lower() and _inside(box,b)>.95 and ink.glyph_owned(box,joint):found.append((letter,box))
    if found:return found
    # Horizontal panels conventionally put markers at their lower margin;
    # stacked image rows put them on the left margin. Only these narrow
    # original strips are read; they cannot borrow adjacent page labels.
    strips=[(b[0],max(b[1],b[3]-25),b[2],b[3],3)]
    for fraction in (0,.35):
        strips.append((b[0],b[1]+fraction*(b[3]-b[1]),min(b[2],b[0]+20),b[1]+min(1,fraction+.55)*(b[3]-b[1]),6))
    for x0,y0,x1,y1,scale in strips:
        for letter,box in read((x0,y0,x1,y1),scale):
            if _inside(box,b)>.95 and ink.glyph_owned(box,joint):found.append((letter,box))
    return found

def repair_raster_marker_caption_ownership(objects,document):
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
            ink=None
            try:
                for cap in caps:
                    lines=_declared_lines(cap,page);declared=_declared(' '.join(l.text for l in lines))
                    if len(declared)<4:continue
                    prior=max((c.bbox[3] for c in caps if c is not cap and c.bbox[3]<cap.bbox[1]),default=page.height*.08)
                    group=[o for o in result if o.kind=='figure' and o.page_number==page.number and prior<=o.bbox[1] and o.bbox[3]<=cap.bbox[1]+2 and _xover(o.bbox,cap.bbox)>.2]
                    if len(group)<2:continue
                    envelope=_union([o.bbox for o in group])
                    if any(c is not cap and _inside(c.bbox,envelope)>.5 for c in caps):continue
                    if ink is None:
                        ink=_PageInk(source,page.number)
                        if not ink.valid:ink.close();ink=_OriginalPageInk(source,page.number,document.path)
                    if not ink.valid:continue
                    owners=_owners(group,cap,ink,False)
                    if not 2<=len(owners)<=8 or any(w['kind']!='raster' for w in owners):continue
                    # Transparent placements can overlap. Their separate
                    # knockouts leave ink from the other resource; joint
                    # removal must still turn every observed ink pixel white.
                    names={n for w in owners for n in w['names']}
                    mask=_combined_mask(names,lines,ink);joint={'mask':mask}
                    if mask is None or not all(ink.owns(o,joint) for o in group):continue
                    labels=[];complete=True
                    for owner in owners:
                        seen=_source_markers(owner,result,source[page.number-1],ink,joint)
                        if not seen:complete=False;break
                        labels.extend(seen)
                    if not complete:continue
                    letters={letter for letter,box in labels}
                    if letters!=declared:continue
                    # Repeated readings of one marker are aliases; repeated
                    # markers in physically separate regions remain ambiguous.
                    if any(a==b and max(abs(x-y) for x,y in zip(xbox,ybox))>8 for i,(a,xbox) in enumerate(labels) for b,ybox in labels[i+1:]):continue
                    if any(l.source=='native' and _inside(l.bbox,envelope)>.8 and not ink.glyph_owned(l.bbox,{'mask':mask}) for l in page.lines):continue
                    joined=replace(_join(group,'figure'),role='original_raster_declared_panel_namespace',caption_owner_id=caption_identity(cap))
                    gone={id(o) for o in group};result=[o for o in result if id(o) not in gone]+[joined]
            except (ValueError,IndexError,RuntimeError,ImportError):continue
            finally:
                if ink is not None:ink.close()
    return result
