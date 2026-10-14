"""CPU OCR for small image regions that a document layout parser can omit.

Uses only bundled, pinned models. Image variants are temporary arrays; the
source PDF is never rewritten. Inference errors and unread text stay explicit.
"""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from time import monotonic
import re


@dataclass(frozen=True)
class OcrText:
    text: str
    score: float
    bbox: tuple[float, float, float, float]
    detection_score: float = 1.0


class _GraphicGuard(tuple):
    """A verified nontext pixel region, compatible with ordinary bbox tuples.

    Text OCR can report letter-shaped bars without interpreting the graphic.
    Such readings remain detector input but cannot make its region readable.
    """


@lru_cache(maxsize=1)
def _engine():
    import os
    import cv2
    import rapidocr
    from rapidocr import RapidOCR
    # Full-document workers already reserve their CPU allocation with OMP.
    # Honor that allocation for the separate OpenCV and ONNX thread pools.
    threads=max(1,min(8,os.cpu_count() or 1,int(os.environ.get("OMP_NUM_THREADS","8"))))
    cv2.setNumThreads(threads)
    models=Path(rapidocr.__file__).parent/"models"
    paths={"Det":"PP-OCRv6_det_small.onnx", "Cls":"ch_ppocr_mobile_v2.0_cls_mobile.onnx",
           "Rec":"PP-OCRv6_rec_small.onnx"}
    if any(not (models/name).is_file() for name in paths.values()):
        raise RuntimeError("Bundled OCR models are missing")
    return RapidOCR(params={
        "Global.log_level":"critical",
        "EngineConfig.onnxruntime.intra_op_num_threads":threads,
        "EngineConfig.onnxruntime.inter_op_num_threads":1,
        **{f"{part}.model_path":str(models/name) for part,name in paths.items()},
    })


def _read_tile(gray):
    import cv2
    from rapidocr.ch_ppocr_rec import TextRecInput
    from rapidocr.utils.process_img import get_rotate_crop_image
    engine=_engine()
    image=cv2.cvtColor(gray,cv2.COLOR_GRAY2BGR)
    # Call the stages directly: RapidOCR.__call__ filters empty/low-score
    # recognitions, which would hide an unread text candidate from this check.
    detector=engine.text_det
    # Keep boxes and scores together. RapidOCR 3.9.2 sorts only the boxes
    # in TextDetector.__call__, so its returned score order cannot be used.
    prepared=detector.get_preprocess(max(image.shape[:2]))(image)
    boxes,detection_scores=detector.postprocess_op(detector.session(prepared),image.shape[:2])
    if boxes is None or not len(boxes):
        return []
    crops=[get_rotate_crop_image(image,box.copy()) for box in boxes]
    recognition=engine.text_rec(TextRecInput(img=crops))
    readings=list(zip(recognition.txts,recognition.scores))
    for i,(text,score) in enumerate(readings):
        if score<.8:
            rotated=engine.text_rec(TextRecInput(img=[cv2.rotate(crops[i],cv2.ROTATE_180)]))
            if rotated.scores[0]>score:
                readings[i]=(rotated.txts[0],rotated.scores[0])
    return [OcrText(text,float(score),(float(box[:,0].min()),float(box[:,1].min()),
                    float(box[:,0].max()),float(box[:,1].max())),float(det_score))
            for (text,score),box,det_score in zip(readings,boxes,detection_scores)]


def _overlap(a,b):
    intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    return intersection/max(1,min((a[2]-a[0])*(a[3]-a[1]),(b[2]-b[0])*(b[3]-b[1])))


def read_remainder(gray, scale, *, deadline, observations=None, guard_boxes=None, source_flat_paper=None):
    """Read overlapping regions at native and enhanced contrast.

    Return every candidate with its confidence, including empty recognitions.
    A high-confidence reading of the same region can resolve a weaker pass.
    """
    import numpy as np
    height,width=gray.shape
    histogram=np.bincount(gray.ravel(),minlength=256)
    paper=int(histogram.argmax())
    flat_paper=(histogram[paper]/gray.size>.98 if source_flat_paper is None else source_flat_paper)
    ys,xs=np.nonzero(gray!=paper)
    if not len(xs):
        return [],0
    # Sparse text is enlarged by cropping its surrounding blank paper. On a
    # textured scan this naturally covers the complete original page extent.
    padding=round(20*scale)
    left=max(0,int(xs.min())-padding);top=max(0,int(ys.min())-padding)
    right=min(width,int(xs.max())+padding+1);bottom=min(height,int(ys.max())+padding+1)
    region=gray[top:bottom,left:right]
    step=round(100*scale);size=round(130*scale)
    hits=[];tiles=0
    for y in range(0,region.shape[0],step):
        for x in range(0,region.shape[1],step):
            original=region[y:y+size,x:x+size]
            if int(original.min())==int(original.max()):
                continue
            background=int(np.bincount(original.ravel(),minlength=256).argmax())
            # Sparse scan remnants need their original pixels, not a large
            # blank inference canvas. Preserve twenty points around every
            # nonuniform pixel and map readings back through this crop.
            local_y,local_x=np.nonzero(original!=background)
            crop_left=max(0,int(local_x.min())-padding)
            crop_top=max(0,int(local_y.min())-padding)
            crop_right=min(original.shape[1],int(local_x.max())+padding+1)
            crop_bottom=min(original.shape[0],int(local_y.max())+padding+1)
            original=original[crop_top:crop_bottom,crop_left:crop_right]
            enhanced=(255-np.clip((background-original.astype("int16"))*16,0,255)).astype("uint8")
            # Local normalization also exposes a one-level faint reference.
            low,high=int(original.min()),int(original.max())
            normalized=((original.astype("float32")-low)*255/(high-low)).astype("uint8")
            views=(original,enhanced,normalized) if flat_paper else (original,enhanced)
            for view_number,view in enumerate(views):
                if monotonic()>=deadline:
                    raise TimeoutError("Local OCR time limit reached")
                tiles+=1
                for item in _read_tile(view):
                    box=((left+x+crop_left+item.bbox[0])/scale,(top+y+crop_top+item.bbox[1])/scale,
                         (left+x+crop_left+item.bbox[2])/scale,(top+y+crop_top+item.bbox[3])/scale)
                    hit=OcrText(item.text,item.score,box,item.detection_score)
                    if observations is not None:
                        observations.append({"text":hit.text,"score":hit.score,
                            "detection_score":hit.detection_score,"bbox":list(box),
                            "view":("raw","contrast","normalized")[view_number]})
                    duplicate=next((i for i,old in enumerate(hits) if _overlap(old.bbox,box)>.8),None)
                    if duplicate is None:
                        hits.append(hit)
                    else:
                        old=hits[duplicate]
                        def compact(text):
                            return re.sub(r"[\s。.,，:：;；]", "", text)
                        old_text,new_text=compact(old.text),compact(hit.text)
                        # A cropped prefix must never replace a complete read.
                        # Preserve incompatible confident readings for matching;
                        # a longer confident read can resolve a weak fragment.
                        if (old_text==new_text or old_text in new_text
                                or (old.score<.8 and len(new_text)>=len(old_text))):
                            if hit.score>old.score or (old_text in new_text and hit.score>=.8):
                                hits[duplicate]=hit
                        elif new_text in old_text:
                            pass
                        else:
                            hits.append(hit)
    if flat_paper and guard_boxes is None:
        # On uniform paper, a localized pixel island is positive evidence of
        # content even if the OCR model cannot decode it (e.g. tiny faint type).
        import cv2
        mask=(gray!=paper).astype("uint8")
        _,_,components,_=cv2.connectedComponentsWithStats(mask,8)
        for x,y,w,h,area in components[1:]:
            if w>=scale and h>=1.5*scale and area>=4:
                box=(x/scale,y/scale,(x+w)/scale,(y+h)/scale)
                # Detection boxes often stop before a final full stop. Allow
                # less than half a text-height of adjacent punctuation without
                # treating separate, unread pixel islands as decoded text.
                def covered(hit):
                    a,b,c,d=hit.bbox
                    pad=.4*min(c-a,d-b)
                    return hit.text.strip() and _overlap(box,(a-pad,b-pad,c+pad,d+pad))>.8
                if not any(covered(hit) for hit in hits):
                    hits.append(OcrText("",0.0,box))
    if guard_boxes is not None:
        for box in guard_boxes:
            if isinstance(box,_GraphicGuard) or not any(hit.text.strip() and _overlap(box,hit.bbox)>.7 for hit in hits):
                hits.append(OcrText("",0.0,box))
    return hits,tiles


def has_unread_text(hits):
    """Recognition confidence is quality, not whether inference ran.

    An empty strong text proposal (also used for the independent pixel guard)
    is an unresolved region. A weak proposal rejected by the recognizer is a
    model nontext decision, retained in the audit instead of declared readable.
    Nonempty low-confidence reads stay input to the detectors, not clean labels.
    """
    return any(not item.text.strip() and item.detection_score>=.8 for item in hits)


def _faint_body_bar_guards(image,labels,components,scale,display_rotation):
    """Positive repeated-stroke evidence, including one-level pale graphics.

    The dark barcode detector must not decide whether a body graphic exists.
    These candidates need filled, consistent original strokes and flat paper
    around the complete run; irregular scanner clouds do not establish bars.
    """
    import numpy as np
    from .native_layout import in_margin
    candidates=[];levels={}
    for ident,(x,y,w,h,area) in enumerate(components[1:],1):
        if area/(w*h)<.95:continue
        pixels=image[y:y+h,x:x+w][labels[y:y+h,x:x+w]==ident]
        histogram=np.bincount(pixels,minlength=256)
        if histogram.max()/len(pixels)<.95:continue
        box=tuple(map(int,(x,y,w,h)))
        candidates.append(box);levels[box]=int(histogram.argmax())
    guards=[]
    for vertical in (True,False):
        bars=[b for b in candidates if .2*scale<=(b[2] if vertical else b[3])<=6*scale
              and (b[3] if vertical else b[2])>=6*scale
              and (b[3] if vertical else b[2])>3*(b[2] if vertical else b[3])]
        while bars:
            seed=bars.pop(0);group=[seed]
            for bar in bars[:]:
                x,y,w,h=bar;a,b,c,d=seed
                aligned=(abs(y-b)<2*scale and abs(h-d)<2*scale) if vertical else (abs(x-a)<2*scale and abs(w-c)<2*scale)
                if aligned:group.append(bar);bars.remove(bar)
            group.sort(key=lambda b:b[0] if vertical else b[1]);runs=[[]]
            for bar in group:
                if runs[-1]:
                    prior=runs[-1][-1]
                    gap=bar[0]-prior[0]-prior[2] if vertical else bar[1]-prior[1]-prior[3]
                    if gap>4*scale:runs.append([])
                runs[-1].append(bar)
            for run in runs:
                if len(run)<12 or max(levels[b] for b in run)-min(levels[b] for b in run)>1:continue
                x=min(b[0] for b in run);y=min(b[1] for b in run)
                right=max(b[0]+b[2] for b in run);bottom=max(b[1]+b[3] for b in run)
                box=(x/scale,y/scale,right/scale,bottom/scale)
                if in_margin(box,image.shape[1]/scale,image.shape[0]/scale,display_rotation):continue
                pad=max(1,round(6*scale));a=max(0,x-pad);b=max(0,y-pad)
                c=min(image.shape[1],right+pad);d=min(image.shape[0],bottom+pad)
                ring=np.ones((d-b,c-a),dtype=bool);ring[y-b:bottom-b,x-a:right-a]=False
                paper=image[b:d,a:c][ring]
                if not len(paper):continue
                histogram=np.bincount(paper,minlength=256);level=int(histogram.argmax())
                if histogram.max()/len(paper)>=.95 and level>max(levels[bar] for bar in run):
                    guards.append(box)
    return guards


def signature_remainder_view(gray,scale,regions,*,display_rotation=0):
    """Separate scan artifacts from coherent ink outside a verified form.

    Only the signature recovery path calls this. Pixel islands are not OCR
    detections: grouped glyphs and substantial unknown content remain guarded,
    including tiny faint text. Original pixels are retained for those regions.
    """
    import cv2
    import numpy as np
    paper=int(np.bincount(gray.ravel(),minlength=256).argmax())
    image=gray.copy();artifacts=[]
    # OCR rectangles can end a few points before the physical table grid.
    # Remove straight border ink near those rectangles, not their bounding union.
    dark=(image<max(0,paper-20)).astype("uint8")
    line_mask=np.zeros_like(dark)
    for size in ((max(3,round(15*scale)),1),(1,max(3,round(15*scale)))):
        line_mask|=cv2.morphologyEx(dark,cv2.MORPH_OPEN,np.ones(size[::-1],dtype="uint8"))
    near=np.zeros_like(dark)
    for x1,y1,x2,y2 in regions:
        pad=round(24*scale)
        a=max(0,round(x1*scale)-pad);b=max(0,round(y1*scale)-pad)
        c=min(image.shape[1],round(x2*scale)+pad);d=min(image.shape[0],round(y2*scale)+pad)
        near[b:d,a:c]=1
    form_mask=np.zeros_like(dark)
    form_pixels=[]
    for x1,y1,x2,y2 in regions:
        a=max(0,int(x1*scale));b=max(0,int(y1*scale))
        c=min(image.shape[1],int(x2*scale)+1);d=min(image.shape[0],int(y2*scale)+1)
        form_mask[b:d,a:c]=1;form_pixels.append((a,b,c,d))
    # Overlapping OCR fragments describe one physical grid frame; only this
    # frame test uses their union. Their intervening pixels remain unmasked.
    frame_pixels=[];pending=list(form_pixels)
    while pending:
        a,b,c,d=pending.pop(0)
        while True:
            joined=[box for box in pending if min(c,box[2])>max(a,box[0])
                    and min(d,box[3])>max(b,box[1])]
            if not joined:break
            for box in joined:
                a=min(a,box[0]);b=min(b,box[1]);c=max(c,box[2]);d=max(d,box[3]);pending.remove(box)
        frame_pixels.append((a,b,c,d))
    line_mask=cv2.morphologyEx(line_mask,cv2.MORPH_CLOSE,np.ones((3,3),dtype="uint8"))
    _,line_labels,line_components,_=cv2.connectedComponentsWithStats(line_mask,8)
    grid=np.zeros_like(dark)
    for ident,(x,y,w,h,size) in enumerate(line_components[1:],1):
        component=line_labels[y:y+h,x:x+w]==ident
        inside=np.count_nonzero(component & form_mask[y:y+h,x:x+w].astype(bool))
        # A physical grid crosses the verified form or forms its close outer
        # frame. Proximity alone cannot turn an independent body line/chart
        # into an administrative border.
        encloses=any(x<=a+3*scale and y<=b+3*scale and x+w>=c-3*scale and y+h>=d-3*scale
                     and a-x<=24*scale and b-y<=24*scale
                     and x+w-c<=24*scale and y+h-d<=24*scale
                     for a,b,c,d in frame_pixels)
        if inside>=size*.5 or encloses:
            grid[y:y+h,x:x+w][component]=1
    # Own actual straight-edge pixels, not a geometric halo. A connected
    # component can include body strokes attached to a frame; its short spurs
    # do not inherit grid ownership. Anti-alias pixels must physically connect
    # to an edge and continue that edge across at least half its length.
    halo=max(1,round(1.5*scale))
    grid_background=cv2.morphologyEx(image,cv2.MORPH_CLOSE,
        np.ones((max(3,round(12*scale)),)*2,dtype="uint8"))
    physical_ink=(grid_background>image).astype("uint8")
    borders=np.zeros_like(grid)
    _,owned_labels,owned_components,_=cv2.connectedComponentsWithStats(grid,8)
    for ident,(x,y,w,h,size) in enumerate(owned_components[1:],1):
        a=max(0,x-halo);b=max(0,y-halo)
        c=min(image.shape[1],x+w+halo);d=min(image.shape[0],y+h+halo)
        core=(owned_labels[b:d,a:c]==ident).astype("uint8")
        ink=physical_ink[b:d,a:c]
        horizontal=np.zeros(d-b,dtype=bool);vertical=np.zeros(c-a,dtype=bool)
        row_coordinates=np.arange(b,d);column_coordinates=np.arange(a,c)
        for left,top,right,bottom in frame_pixels:
            lo=max(a,left);hi=min(c,right);start=max(b,top);stop=min(d,bottom)
            if hi<=lo or stop<=start:continue
            # A frame edge continues across the actual verified form span.
            # A long attached body stem has no such interior continuation,
            # even if it dominates the connected component's bounding box.
            row_edges=(abs(row_coordinates-top)<=24*scale)|(abs(row_coordinates-bottom)<=24*scale)
            col_edges=(abs(column_coordinates-left)<=24*scale)|(abs(column_coordinates-right)<=24*scale)
            horizontal |= row_edges & (core[:,lo-a:hi-a].sum(axis=1)>=max(15*scale,(right-left)*.5))
            vertical |= col_edges & (core[start-b:stop-b,:].sum(axis=0)>=max(15*scale,(bottom-top)*.5))
        row_band=cv2.dilate(horizontal.astype("uint8")[:,None],
                            np.ones((2*halo+1,1),dtype="uint8"))[:,0].astype(bool)
        col_band=cv2.dilate(vertical.astype("uint8")[None,:],
                            np.ones((1,2*halo+1),dtype="uint8"))[0].astype(bool)
        row_band &= ink[:,x-a:x+w-a].sum(axis=1)>=w*.5
        col_band &= ink[y-b:y+h-b,:].sum(axis=0)>=h*.5
        eligible=ink & (row_band[:,None] | col_band[None,:])
        owned=core & eligible
        for _ in range(halo):
            grown=cv2.dilate(owned,np.ones((3,3),dtype="uint8")) & eligible
            if np.array_equal(grown,owned):break
            owned=grown
        borders[b:d,a:c] |= owned
    image[(borders & near).astype(bool)]=paper
    for x1,y1,x2,y2 in regions:
        a=max(0,int(x1*scale));b=max(0,int(y1*scale))
        c=min(image.shape[1],int(x2*scale)+1);d=min(image.shape[0],int(y2*scale)+1)
        image[b:d,a:c]=paper
    # Only a small run of aligned bars in the displayed header/footer margin
    # is a barcode artifact. The same shapes inside the body can be a chart.
    from .native_layout import in_margin
    body_bar_guards=[]
    _,_,components,_=cv2.connectedComponentsWithStats((image<max(0,paper-30)).astype("uint8"),8)
    for vertical in (True,False):
        bars=[]
        for x,y,w,h,area in components[1:]:
            thin,tall=(w,h) if vertical else (h,w)
            if .2*scale<=thin<=6*scale and 6*scale<=tall and tall>3*thin and area/(w*h)>.6:
                bars.append((int(x),int(y),int(w),int(h)))
        while bars:
            seed=bars.pop(0);group=[seed]
            for bar in bars[:]:
                a,b,c,d=seed;x,y,w,h=bar
                aligned=(abs(y-b)<2*scale and abs(h-d)<2*scale) if vertical else (abs(x-a)<2*scale and abs(w-c)<2*scale)
                if aligned:group.append(bar);bars.remove(bar)
            group.sort(key=lambda b:b[0] if vertical else b[1])
            runs=[[]]
            for bar in group:
                if runs[-1]:
                    prev=runs[-1][-1]
                    gap=bar[0]-prev[0]-prev[2] if vertical else bar[1]-prev[1]-prev[3]
                    if gap>4*scale:runs.append([])
                runs[-1].append(bar)
            for run in runs:
                if len(run)<12:continue
                # Joined bars can fail the single-bar shape test. The full
                # validated barcode band includes those fused bars as well.
                x=min(b[0] for b in run);y=min(b[1] for b in run)
                right=max(b[0]+b[2] for b in run);bottom=max(b[1]+b[3] for b in run)
                box=(x/scale,y/scale,right/scale,bottom/scale)
                if all((bar[3] if vertical else bar[2])<=45*scale for bar in run) and in_margin(box,image.shape[1]/scale,image.shape[0]/scale,display_rotation):
                    image[max(0,y-1):bottom+1,max(0,x-1):right+1]=paper
                    artifacts.append({"kind":"parallel_barcode_bars","bars":len(run)})
                else:
                    body_bar_guards.append(box)
    source_histogram=np.bincount(image.ravel(),minlength=256)
    source_flat_paper=bool(source_histogram.max()/image.size>.98)
    # Closing estimates slowly varying paper illumination without a contrast
    # threshold that would erase one-level faint lettering.
    kernel=max(3,round(12*scale))
    background=cv2.morphologyEx(image,cv2.MORPH_CLOSE,np.ones((kernel,kernel),dtype="uint8"))
    ink=(background>image).astype("uint8")
    _,labels,components,_=cv2.connectedComponentsWithStats(ink,8)
    for box in _faint_body_bar_guards(image,labels,components,scale,display_rotation):
        if box not in body_bar_guards:body_bar_guards.append(box)
    glyphs=[];selected=set();guards=[_GraphicGuard(box) for box in body_bar_guards];faint_strips=set();faint_glyphs=set();coherent=set();word_strips=set();stroke_evidence={};local_contrasts={};glyph_holes={}
    for ident,(x,y,w,h,area) in enumerate(components[1:],1):
        if (.35*scale<=w<=40*scale and 1*scale<=h<=40*scale
                and w<6*h and h<6*w and area>=3):
            mask=labels[y:y+h,x:x+w]==ident
            pixels=image[y:y+h,x:x+w][mask]
            contrasts=background[y:y+h,x:x+w][mask].astype("int16")-pixels.astype("int16")
            contrast=int(contrasts.max())
            local_contrasts[ident]=contrast
            # A compact merged glyph needs real bounded internal whitespace.
            # Ragged clouds and solid scanner creases have no glyph counters.
            inverse=(~np.pad(mask,1)).astype("uint8")
            _,hole_labels,hole_components,_=cv2.connectedComponentsWithStats(inverse,8)
            exterior=hole_labels[0,0]
            holes=any(i!=exterior for i in range(1,len(hole_components)))
            glyph_holes[ident]=holes
            pixel_histogram=np.bincount(pixels,minlength=256)
            stroke_level=int(pixel_histogram.argmax())
            uniform_fraction=float(pixel_histogram.max())/len(pixels)
            # Morphological closing can turn a broad one-level paper cloud
            # into apparent ink. Verify the unaltered paper around a weak
            # glyph, and require its stroke to be darker than that paper.
            pad=max(1,round(6*scale));a=max(0,x-pad);b=max(0,y-pad)
            c=min(image.shape[1],x+w+pad);d=min(image.shape[0],y+h+pad)
            ring=np.ones((d-b,c-a),dtype=bool)
            ring[y-b:y+h-b,x-a:x+w-a]=False
            ring_pixels=image[b:d,a:c][ring]
            ring_histogram=np.bincount(ring_pixels,minlength=256)
            ring_level=int(ring_histogram.argmax())
            local_paper=(bool(len(ring_pixels)) and ring_histogram.max()/len(ring_pixels)>=(.90 if holes else .95)
                         and ring_level>stroke_level)
            stroke_evidence[ident]=(contrast>3 or uniform_fraction>=.95 and local_paper)
            density=float(area)/(w*h)
            faint_strip=(density>.8 and min(w,h)>=3.5*scale and max(w,h)>1.25*min(w,h))
            # Decide from the complete glyph group before pruning faint ink.
            # Four-point references may consist entirely of one-level glyphs.
            if 0<contrast<=3:faint_glyphs.add(ident)
            glyphs.append((ident,int(x),int(y),int(w),int(h),density))
            if faint_strip and 0<contrast<=3:faint_strips.add(ident)
            long_word=.15<=density<.8 and holes and max(w,h)>=8*scale and (w>=1.8*h or h>=1.8*w)
            # At three points a type-plus-digit can merge into one glyph island.
            # Its ink area and internal gaps distinguish it from a solid crease.
            merged_word=(holes and .5<=density<.95 and area>=6*scale*scale and max(w,h)>=4*scale
                         and (w>=1.3*h or h>=1.3*w))
            if long_word or merged_word:word_strips.add(ident)
    # A one-level faint line can rasterize as a solid connected text strip.
    # Retain it even when individual glyph holes disappear at scan resolution.
    for ident,x,y,w,h,density in glyphs:
        if ident in faint_strips or ident in word_strips or (w>=2.5*h and h>=2.5*scale) or (h>=2.5*w and w>=2.5*scale):
            selected.add(ident)
    # Match adjacent glyphs in either orientation. Isolated round scan speckles
    # and long creases cannot establish a text line.
    # Spatial buckets bound the work on heavily textured photocopies.
    from collections import defaultdict
    buckets=defaultdict(list);cell=max(1,round(40*scale))
    for glyph in glyphs:buckets[(glyph[1]//cell,glyph[2]//cell)].append(glyph)
    links=defaultdict(set)
    for a in glyphs:
        i,x,y,w,h,density=a
        adjacent=[]
        for dx in range(-1,4):
            for dy in range(-1,4):
                for b in buckets[(x//cell+dx,y//cell+dy)]:
                    j,u,v,s,t,other_density=b
                    if i==j:continue
                    # Two round solid speckles are not a line. A dense CJK
                    # glyph next to a narrow digit remains a text candidate.
                    if (min(density,other_density)>.7 and .65<w/h<1.5 and .65<s/t<1.5):continue
                    horizontal=abs((y+h)-(v+t))<=max(h,t)*.35 and .65<=h/t<=1.5 and 0<=u-x-w<=max(h,t)*2
                    vertical=abs((x+w)-(u+s))<=max(w,s)*.35 and .65<=w/s<=1.5 and 0<=v-y-h<=max(w,s)*2
                    if horizontal or vertical:adjacent.append(b)
        if adjacent:
            links[i].update(b[0] for b in adjacent)
            for other in adjacent:links[other[0]].add(i)
            coherent.add(i);coherent.update(b[0] for b in adjacent)
            selected.add(i);selected.update(b[0] for b in adjacent)
    # A dominant paper colour can still contain widespread JPEG/scanner
    # microtexture. It is not evidence that every tiny island is a text glyph.
    micro=[]
    for ident,(x,y,w,h,size) in enumerate(components[1:],1):
        if ident not in selected and size<4*scale*scale and max(w,h)<=8*scale:
            contrast=paper-int(image[y:y+h,x:x+w].min())
            if 0<contrast<=3:micro.append((int(x),int(y)))
    occupied={(x//max(1,round(80*scale)),y//max(1,round(80*scale))) for x,y in micro}
    source_flat_paper=bool(source_flat_paper and not (len(micro)>=96 and len(occupied)>=8))
    # Coherent lines remain text evidence even on textured paper. Isolated
    # microtexture cannot make a line just because two small islands touch.
    strong_text=set();pending=set(links)
    while pending:
        group=set();queue=[pending.pop()]
        while queue:
            ident=queue.pop();group.add(ident)
            neighbors=links[ident] & pending
            pending.difference_update(neighbors);queue.extend(neighbors)
        boxes=[components[ident] for ident in group]
        left=min(x for x,y,w,h,size in boxes);right=max(x+w for x,y,w,h,size in boxes)
        top=min(y for x,y,w,h,size in boxes);bottom=max(y+h for x,y,w,h,size in boxes)
        horizontal=bottom-top<=1.6*max(h for x,y,w,h,size in boxes) and right-left>=1.25*(bottom-top)
        vertical=right-left<=1.6*max(w for x,y,w,h,size in boxes) and bottom-top>=1.25*(right-left)
        ink_levels=[int(image[y:y+h,x:x+w].min()) for x,y,w,h,size in boxes]
        uniform_ink=max(ink_levels)-min(ink_levels)<=1
        unclipped=left>=3*scale and top>=3*scale and right<=image.shape[1]-3*scale and bottom<=image.shape[0]-3*scale
        if (sum(size for x,y,w,h,size in boxes)>=6*scale*scale and (horizontal or vertical)
                and unclipped and uniform_ink and all(stroke_evidence.get(i,False) for i in group)
                and any(glyph_holes.get(i,False) or components[i][4]/(components[i][2]*components[i][3])<=.7 for i in group)):
            strong_text.update(group)
    strong_text.update(ident for ident in word_strips if components[ident][4]>=6*scale*scale and stroke_evidence[ident])
    # A substantial unexplained dark island remains unresolved (e.g. a graphic),
    # rather than becoming a clean result through text-only OCR.
    _,large_labels,large,_=cv2.connectedComponentsWithStats((image<max(0,paper-20)).astype("uint8"),8)
    for x,y,w,h,area in large[1:]:
        if w>20*scale and h>20*scale and area>100*scale*scale:
            if x<3*scale or y<3*scale or x+w>image.shape[1]-3*scale or y+h>image.shape[0]-3*scale:continue
            box=(float(x/scale),float(y/scale),float((x+w)/scale),float((y+h)/scale));guards.append(box)
            # Preserve this ink for OCR as well as the independent guard.
            overlap=(labels[y:y+h,x:x+w]);selected.update(int(n) for n in np.unique(overlap) if n)
    # Thin parallel body bars may not satisfy either the glyph or large-island
    # thresholds. Keep their original pixels and their independent guard.
    for x1,y1,x2,y2 in body_bar_guards:
        x=max(0,int(x1*scale));y=max(0,int(y1*scale))
        right=min(image.shape[1],round(x2*scale));bottom=min(image.shape[0],round(y2*scale))
        selected.update(int(n) for n in np.unique(labels[y:bottom,x:right]) if n)
    view=np.full_like(image,paper)
    for ident in selected:
        x,y,w,h,area=components[ident]
        # Clipped scan-edge fragments stay available to OCR but cannot stand
        # alone as evidence of an unread text line.
        clipped=x<scale or y<scale or x+w>=image.shape[1]-scale or y+h>=image.shape[0]-scale
        pad=round(2*scale);a=max(0,x-pad);b=max(0,y-pad);c=min(image.shape[1],x+w+pad);d=min(image.shape[0],y+h+pad)
        view[b:d,a:c]=image[b:d,a:c]
        if not clipped and ident in faint_glyphs and (ident in strong_text or source_flat_paper and (ident in faint_strips or ident in coherent or ident in word_strips)):guards.append((float(x/scale),float(y/scale),float((x+w)/scale),float((y+h)/scale)))
    artifacts.append({"kind":"scan_background_and_isolated_speckles","components":len(components)-1,"retained_components":len(selected),"source_flat_paper":source_flat_paper,"unselected_microtexture_components":len(micro)})
    return view,guards,artifacts
