"""Pure proofs from unmodified source pixels; no PDF I/O or page identities.

Affine transforms use fitz's (a,b,c,d,e,f) order and normalized source pixels:
    display_x = a * (source_x / width) + c * (source_y / height) + e
    display_y = b * (source_x / width) + d * (source_y / height) + f
A caller must independently qualify the carrier and retain native/alpha ink.
"""
import hashlib
import math
import re
import numpy as np


def _geometry(pixels,source_bbox,source_to_display,page_bbox,alpha):
    a=np.asarray(pixels)
    if a.ndim!=2 or a.dtype!=np.uint8 or not a.size:return None
    if alpha is not None and (np.shape(alpha)!=a.shape or not np.all(np.asarray(alpha)==255)):return None
    t=np.asarray(source_to_display,dtype=float)
    b=np.asarray(source_bbox,dtype=float);page=np.asarray(page_bbox,dtype=float)
    if t.shape!=(6,) or b.shape!=(4,) or page.shape!=(4,):return None
    if not np.all(np.isfinite(np.r_[t,b,page])):return None
    matrix=np.array(((t[0],t[2]),(t[1],t[3])))
    if abs(np.linalg.det(matrix))<1e-8:return None
    # These proofs use an orthogonal physical raster, not a skewed crop guess.
    if abs(np.dot(matrix[:,0],matrix[:,1]))>np.linalg.norm(matrix[:,0])*np.linalg.norm(matrix[:,1])*1e-6:return None
    if any(abs(x)>1e-5 and abs(y)>1e-5 for x,y in matrix.T):return None
    corners=np.array(((0,0),(1,0),(0,1),(1,1)))@matrix.T+t[4:]
    expected=np.r_[corners.min(axis=0),corners.max(axis=0)]
    if np.max(np.abs(expected-b))>1e-3 or min(page[2:]-page[:2])<=0:return None
    h,w=a.shape
    return a,matrix,t[4:],np.linalg.inv(matrix),b,page,(np.linalg.norm(matrix[:,0])/w,np.linalg.norm(matrix[:,1])/h)


def _display_box(box,matrix,offset,w,h):
    x,y,z,d=box
    points=np.array(((x/w,y/h),(z/w,y/h),(x/w,d/h),(z/w,d/h)))@matrix.T+offset
    return tuple(np.r_[points.min(axis=0),points.max(axis=0)])


def _intersects(a,b):
    return min(a[2],b[2])>max(a[0],b[0]) and min(a[3],b[3])>max(a[1],b[1])


def _contains(a,b,tolerance=0):
    return all((a[i]-tolerance<=b[i] if i<2 else a[i]+tolerance>=b[i]) for i in range(4))


def prove_continuous_source_boundary(pixels,*,source_bbox,source_to_display,page_bbox,
        guard,guard_kind,display_sample_pitch,independent_regions=(),alpha=None):
    """Prove only a whole, shallow original scan-edge component.

    Entire source components and the whole normal band are checked. A body
    glyph attached elsewhere, a separate partial line in the band, independent
    native/alpha content, or more than one displayed pixel of crop roundoff
    vetoes this proof. Both binary and actual grayscale/JPEG sources qualify
    at the established visible-ink threshold; metadata reports that threshold.
    """
    import cv2
    if guard_kind not in {'_GraphicGuard','_VisibleInkGuard'}:return None
    if not 0<display_sample_pitch<=1 or any(_intersects(guard,b) for b in independent_regions):return None
    g=_geometry(pixels,source_bbox,source_to_display,page_bbox,alpha)
    if g is None:return None
    a,matrix,offset,inverse,b,page,pitches=g;h,w=a.shape
    visible=np.maximum(0,np.minimum(b[2:],page[2:])-np.maximum(b[:2],page[:2]))
    if np.prod(visible)<np.prod(page[2:]-page[:2])*.95:return None
    guard=np.asarray(guard,dtype=float)
    if guard.shape!=(4,) or not np.all(np.isfinite(guard)) or min(guard[2:]-guard[:2])<=0:return None
    overshoot=np.maximum(0,np.r_[b[:2]-guard[:2],guard[2:]-b[2:]])
    if overshoot.max()>display_sample_pitch+1e-6:return None
    points=(np.array(((guard[0],guard[1]),(guard[2],guard[1]),(guard[0],guard[3]),(guard[2],guard[3])))-offset)@inverse.T
    lo=np.maximum(0,points.min(axis=0)*[w,h]);hi=np.minimum([w,h],points.max(axis=0)*[w,h])
    x,y=np.floor(lo+1e-7).astype(int);z,d=np.ceil(hi-1e-7).astype(int)
    if z<=x or d<=y:return None
    ink=(a<=225).astype('uint8')
    _,labels,parts,_=cv2.connectedComponentsWithStats(ink,8)
    selected={int(v) for v in np.unique(labels[y:d,x:z]) if v}
    if not selected:return None
    for edge,axis,outer in (('top',1,ink[0]),('bottom',1,ink[-1]),('left',0,ink[:,0]),('right',0,ink[:,-1])):
        if not np.all(outer):continue
        normal_pitch=pitches[axis];normal=max(1,math.ceil(2/normal_pitch))
        band=(labels[:normal] if edge=='top' else labels[-normal:] if edge=='bottom' else
              labels[:,:normal] if edge=='left' else labels[:,-normal:])
        ids={int(v) for v in np.unique(band) if v}
        if not ids or not selected<=ids:continue
        source_parts=[];depths=[]
        for n in ids:
            sx,sy,bw,bh,area=map(int,parts[n]);depth=(bh if axis==1 else bw)*normal_pitch
            complete=(sx==0 and bw==w and (sy==0 if edge=='top' else sy+bh==h)) if axis==1 else (sy==0 and bh==h and (sx==0 if edge=='left' else sx+bw==w))
            if not complete or depth>2+1e-6:break
            source_parts.append([sx,sy,bw,bh,area]);depths.append(depth)
        else:
            if (hi[axis]-lo[axis])*normal_pitch>2+1e-6:continue
            # No selected guard ink is inferred from a render-only crop.
            return {'kind':'source_continuous_physical_boundary','source_edge':edge,
                    'source_shape':[h,w],'source_pixel_sha256':hashlib.sha256(a.tobytes()).hexdigest(),
                    'source_to_display':list(source_to_display),'source_bbox':list(source_bbox),
                    'guard_bbox':guard.tolist(),'guard_source_pixel_window':[int(x),int(y),int(z),int(d)],
                    'source_components':source_parts,'whole_edge_coverage':1.0,
                    'maximum_component_depth_points':max(depths),'source_visible_ink_threshold':225,
                    'display_roundoff_outside_source':overshoot.tolist(),'display_sample_pitch':display_sample_pitch,
                    'independent_regions_veto_checked':True,'opaque_source_only':True}
    return None


def _hit_value(h,key):
    return h[key] if isinstance(h,dict) else getattr(h,key)


def _measure_strict_bar_fringe(a,visible_labels,visible_id,source_box,*,paper):
    """Measure a closed component tree, never a clipped/padded soft halo.

    The original <=225 component is already proved from the whole array.
    Every actual higher source gray level is visited until the first topology
    failure. A two-pixel sentinel surrounds that exact box: any escape beyond
    the one-pixel limit must cross it, so a successful component is its whole
    source component, including paths that would reach ink outside this ROI.
    """
    import cv2
    x,y,w,h=map(int,source_box);height,width=a.shape
    sx,sy=max(0,x-2),max(0,y-2);z,d=min(width,x+w+2),min(height,y+h+2)
    original=visible_labels[sy:d,sx:z];roi=a[sy:d,sx:z];seed=original==visible_id
    chosen_box=[x,y,w,h];chosen_pixels=int(np.count_nonzero(seed));chosen_level=225
    chosen_mask=seed[y-sy:y-sy+h,x-sx:x-sx+w]
    reason='paper_background';stopped=int(paper);levels=[];stop_foreign=[]
    for level in (int(v) for v in np.unique(roi) if 225<v<paper):
        _,labels,parts,_=cv2.connectedComponentsWithStats((roi<=level).astype('uint8'),8)
        ids={int(v) for v in np.unique(labels[seed]) if v}
        if len(ids)!=1:reason='source_component_split';stopped=level;break
        n=next(iter(ids));qx,qy,qw,qh,area=map(int,parts[n]);member=labels[qy:qy+qh,qx:qx+qw]==n
        foreign={int(v) for v in np.unique(original[qy:qy+qh,qx:qx+qw][member]) if v}
        extension=[x-sx-qx,y-sy-qy,sx+qx+qw-x-w,sy+qy+qh-y-h]
        if foreign!={visible_id}:
            reason='foreign_visible_core';stopped=level;stop_foreign=sorted(foreign-{visible_id});break
        if any(v>1 or v<0 for v in extension):
            reason='one_source_pixel_limit';stopped=level;break
        # A successful bbox is strictly inside each artificial two-pixel
        # sentinel; at real image boundaries the original array itself ends.
        if ((sx>0 and qx==0) or (sy>0 and qy==0)
                or (z<width and qx+qw==z-sx) or (d<height and qy+qh==d-sy)):
            reason='sentinel_escape';stopped=level;break
        present={int(v) for v in np.unique(labels[qy:qy+qh,qx:qx+qw]) if v}
        if present!={n}:reason='independent_source_ink';stopped=level;break
        chosen_box=[sx+qx,sy+qy,qw,qh];chosen_pixels=area;chosen_level=level;chosen_mask=member.copy();levels.append(level)
    cx,cy,cw,ch=chosen_box
    extension=[x-cx,y-cy,cx+cw-x-w,cy+ch-y-h]
    return {'source_box':chosen_box,'source_pixels':chosen_pixels,
            'visible225_source_box':[x,y,w,h],'chosen_source_level':chosen_level,
            'source_paper_level':int(paper),'visited_valid_source_levels':levels,
            'topology_stop_source_level':stopped,'topology_stop_reason':reason,
            'topology_stop_foreign_visible_ids':stop_foreign,
            'visible225_to_fringe_extension_pixels':extension,'maximum_extension_pixels':max(extension),
            'source_sentinel_window':[sx,sy,z,d],'entire_component_proved':True,
            'chosen_component_mask_sha256':hashlib.sha256(chosen_mask.astype('uint8').tobytes()).hexdigest()}


def _bar_guard_source_obligations(a,visible,fringes,window):
    """Keep independent weak ink in a broad guard as a source obligation.

    Inspection uses actual measured component levels, not a fixed gray246
    cutoff. The source background diagnostics remain separate from owned bar
    pixels: weak one-source-pixel texture and immediate bar-adjacent ringing
    can be background, but a coherent independent core outside that support
    cannot borrow the whole barcode rectangle.
    """
    import cv2
    x,y,z,d=window;patch=a[y:d,x:z]
    owned=np.zeros(patch.shape,bool)
    for f in fringes:
        fx,fy,fw,fh=f['source_box'];cx,cy,cz,cd=max(x,fx),max(y,fy),min(z,fx+fw),min(d,fy+fh)
        if cz<=cx or cd<=cy:continue
        owned[cy-y:cd-y,cx-x:cz-x]|=a[cy:cd,cx:cz]<=f['chosen_source_level']
    level=max(f['chosen_source_level'] for f in fringes)
    _,labels,parts,_=cv2.connectedComponentsWithStats((patch<=level).astype('uint8'),8)
    seeded={int(v) for v in np.unique(labels[owned]) if v};background=[]
    for n,(sx,sy,w,h,area) in enumerate(parts[1:],1):
        if n in seeded:continue
        sx,sy,w,h,area=map(int,(sx,sy,w,h,area));member=labels[sy:sy+h,sx:sx+w]==n
        tones=patch[sy:sy+h,sx:sx+w][member]
        if tones.min()<=225:return None
        core=bool(np.any(cv2.erode(member.astype('uint8'),np.ones((2,2),np.uint8),borderType=cv2.BORDER_CONSTANT,borderValue=0)))
        box=(x+sx,y+sy,x+sx+w,y+sy+h)
        # Distance is measured between original source pixel footprints.
        # This classifies weak background, never expands an owned region.
        near=any(max(v['source_box'][0]-box[2],box[0]-v['source_box'][0]-v['source_box'][2],
                     v['source_box'][1]-box[3],box[1]-v['source_box'][1]-v['source_box'][3],0)<=2 for v in visible)
        # A single mixed-tone 2x2 source grain may be exposed when a
        # displayed guard rounds through one extra original source row.
        # This does not qualify a flat painted block or a coherent stroke.
        grain=w<=2 and h<=2 and tones.max()>tones.min()
        if core and not near and not grain:return None
        background.append({'source_box':[x+sx,y+sy,w,h],'source_pixels':area,
                           'tone_min':int(tones.min()),'tone_max':int(tones.max()),
                           'has_two_by_two_source_core':core,
                           'immediate_two_source_pixel_bar_support':near,
                           'background_kind':'bar_adjacent_weak_texture' if near else
                                             'isolated_mixed_tone_source_grain' if grain else 'one_source_pixel_weak_texture'})
    return {'inspection_source_level':level,'actual_bar_component_pixels':int(np.count_nonzero(owned)),
            'unowned_source_pixels_at_inspected_level':int(np.count_nonzero((patch<=level)&~owned)),
            'independent_weak_background_components':background,
            'background_is_separate_from_foreground_ownership':True,
            'brighter_source_levels_are_not_proved_by_this_check':True}


def prove_signed_form_barcode(pixels,*,source_bbox,source_to_display,page_bbox,observations,
        decision_schema_proof,guard=None,independent_regions=(),alpha=None,display_sample_pitch=.5):
    """Prove measured parallel bars paired with a signed decision's student ID.

    This does not widen a global margin. Bars and their numeric label must be
    above the independently proved grid and right of its printed form title.
    A same-row printed 学号 field must independently carry exactly that ID.
    """
    import cv2
    if not 0<display_sample_pitch<=1:return None
    from .local_ocr import OcrText
    from .signature_structure import _decision_schema,compact
    g=_geometry(pixels,source_bbox,source_to_display,page_bbox,alpha)
    if g is None:return None
    a,matrix,offset,inverse,b,page,pitches=g;h,w=a.shape;width,height=page[2]-page[0],page[3]-page[1]
    proof=decision_schema_proof or {};grid=proof.get('source_grid_region')
    count=proof.get('committee_rows',0)
    if (count<5 or proof.get('signed_rows',0)<max(3,(count+1)//2)
            or proof.get('chair_has_signature_ink') is not True or not grid
            or grid[2]-grid[0]<width*.6 or grid[3]-grid[1]<height*.5):return None
    hits=tuple(OcrText(text=_hit_value(q,'text'),score=_hit_value(q,'score'),bbox=tuple(_hit_value(q,'bbox')),
                      detection_score=_hit_value(q,'detection_score')) for q in observations)
    if not _decision_schema(hits,width,height):return None
    printed=[q for q in hits if q.score>=.9]
    titles=[q for q in printed if '学位论文答辩决议书' in compact(q.text) and q.bbox[1]<height*.2]
    if len(titles)!=1:return None
    title=titles[0]
    numeric=re.compile(r'^[:：.\-\s]*([0-9]{6,24})$')
    labels=[q for q in hits if q.score>=.85 and numeric.fullmatch(q.text.strip())]
    paired=[]
    for field in printed:
        t=compact(field.text)
        if t.startswith('学号'):
            tail=t[2:].lstrip(':：')
            if re.fullmatch(r'[0-9]{6,24}',tail):paired.append((tail,field.bbox,field.bbox))
        if t!='学号':continue
        middle=(field.bbox[1]+field.bbox[3])/2
        for value in labels:
            if (value.bbox[0]>=field.bbox[2]-3 and value.bbox[0]-field.bbox[2]<=width*.15
                    and abs((value.bbox[1]+value.bbox[3])/2-middle)<=8
                    and _contains(grid,field.bbox,2) and _contains(grid,value.bbox,2)):
                paired.append((numeric.fullmatch(value.text.strip())[1],field.bbox,value.bbox))
    if not paired:return None
    dark=(a<128).astype('uint8');_,component_ids,parts,_=cv2.connectedComponentsWithStats(dark,8)
    bars=[]
    for n,(x,y,bw,bh,area) in enumerate(parts[1:],1):
        box=_display_box((x,y,x+bw,y+bh),matrix,offset,w,h);cw,ch=box[2]-box[0],box[3]-box[1]
        if .1<=cw<=12 and 10<=ch<=60 and ch>=4*cw and area/(bw*bh)>=.7:bars.append((n,box,(int(x),int(y),int(x+bw),int(y+bh))))
    visible_labels=visible_parts=None;source_paper=None
    while bars:
        seed=bars.pop(0);peers=[q for q in bars if abs(q[1][1]-seed[1][1])<=2 and abs((q[1][3]-q[1][1])-(seed[1][3]-seed[1][1]))<=2]
        for q in peers:bars.remove(q)
        groups=[[]]
        for q in sorted([seed]+peers,key=lambda q:q[1][0]):
            if groups[-1] and q[1][0]-groups[-1][-1][1][2]>4+max(pitches):groups.append([])
            groups[-1].append(q)
        for group in groups:
            if len(group)<12:continue
            box=(min(q[1][0] for q in group),min(q[1][1] for q in group),max(q[1][2] for q in group),max(q[1][3] for q in group))
            if box[2]-box[0]>width*.35 or box[0]<title.bbox[2]+5 or box[3]>grid[1]+1:continue
            source_box=(min(q[2][0] for q in group),min(q[2][1] for q in group),max(q[2][2] for q in group),max(q[2][3] for q in group));sx,sy,z,d=source_box
            own={q[0] for q in group};all_ink={int(n) for n in np.unique(component_ids[sy:d,sx:z]) if n}
            if all_ink!=own:continue
            # Recover measured original soft edges from each independently
            # proved dark bar. This never pads a rectangle. Every soft
            # component must correspond to exactly one selected dark core,
            # contain no foreign dark component and extend at most two
            # ORIGINAL source pixels beyond that core on each side.
            if visible_labels is None:
                _,visible_labels,visible_parts,_=cv2.connectedComponentsWithStats((a<=225).astype('uint8'),8)
            visible=[];visible_ids=set();invalid=False
            for core_id,_,(cx,cy,cz,cd) in group:
                seed_mask=component_ids[cy:cd,cx:cz]==core_id
                peers={int(n) for n in np.unique(visible_labels[cy:cd,cx:cz][seed_mask]) if n}
                if len(peers)!=1:invalid=True;break
                visible_id=next(iter(peers))
                if visible_id in visible_ids:invalid=True;break
                vx,vy,vw,vh,area=map(int,visible_parts[visible_id]);vz,vd=vx+vw,vy+vh
                extension=[cx-vx,cy-vy,vz-cz,vd-cd]
                if any(e<0 or e>2 for e in extension):invalid=True;break
                member=visible_labels[vy:vd,vx:vz]==visible_id
                hard_ids={int(n) for n in np.unique(component_ids[vy:vd,vx:vz][member]) if n}
                if hard_ids!={core_id}:invalid=True;break
                visible_ids.add(visible_id)
                visible.append({'source_component_id':visible_id,'source_core_id':core_id,
                                'source_box':[vx,vy,vw,vh],'source_pixels':area,
                                'core_to_soft_extension_pixels':extension,
                                'display_bbox':list(_display_box((vx,vy,vz,vd),matrix,offset,w,h))})
            if invalid:continue
            hard_box=box
            vsx=min(v['source_box'][0] for v in visible);vsy=min(v['source_box'][1] for v in visible)
            vsz=max(v['source_box'][0]+v['source_box'][2] for v in visible);vsd=max(v['source_box'][1]+v['source_box'][3] for v in visible)
            present={int(n) for n in np.unique(visible_labels[vsy:vsd,vsx:vsz]) if n}
            if present!=visible_ids:continue
            visible_box=(min(v['display_bbox'][0] for v in visible),min(v['display_bbox'][1] for v in visible),
                         max(v['display_bbox'][2] for v in visible),max(v['display_bbox'][3] for v in visible))
            if source_paper is None:source_paper=int(np.bincount(a.ravel(),minlength=256).argmax())
            fringes=[]
            for v in visible:
                fringe=_measure_strict_bar_fringe(a,visible_labels,v['source_component_id'],v['source_box'],paper=source_paper)
                fx,fy,fw,fh=fringe['source_box']
                fringes.append(dict(fringe,source_component_id=v['source_component_id'],source_core_id=v['source_core_id'],
                                     display_bbox=list(_display_box((fx,fy,fx+fw,fy+fh),matrix,offset,w,h))))
            box=(min(v['display_bbox'][0] for v in fringes),min(v['display_bbox'][1] for v in fringes),
                 max(v['display_bbox'][2] for v in fringes),max(v['display_bbox'][3] for v in fringes))
            if box[3]>grid[1]+1:continue
            for label in labels:
                value=numeric.fullmatch(label.text.strip())[1]
                matches=[p for p in paired if p[0]==value and p[2]!=label.bbox]
                if len(matches)!=1:continue
                if not (-2<=label.bbox[1]-box[3]<=12 and label.bbox[3]-label.bbox[1]<=22
                        and label.bbox[0]>=box[0]-12 and label.bbox[2]<=box[2]+12
                        and label.bbox[3]<=grid[1]+2):continue
                if not _contains(source_bbox,label.bbox,max(pitches)):continue
                regions=[box,label.bbox]
                if any(_intersects(r,v) for r in regions for v in independent_regions):continue
                source_guard_window=None;guard_bar_component_pixels=None;guard_background=None
                if guard is not None:
                    in_bar=_contains(box,guard,display_sample_pitch)
                    in_label=_contains(label.bbox,guard,display_sample_pitch)
                    if not in_bar and not in_label:continue
                    if in_bar:
                        points=(np.array(((guard[0],guard[1]),(guard[2],guard[1]),(guard[0],guard[3]),(guard[2],guard[3])))-offset)@inverse.T
                        lo=np.maximum(0,points.min(axis=0)*[w,h]);hi=np.minimum([w,h],points.max(axis=0)*[w,h])
                        gx,gy=np.floor(lo+1e-7).astype(int);gz,gd=np.ceil(hi-1e-7).astype(int)
                        source_guard_window=[int(gx),int(gy),int(gz),int(gd)];owned=0
                        for fringe in fringes:
                            fx,fy,fw,fh=fringe['source_box'];cx,cy,cz,cd=max(gx,fx),max(gy,fy),min(gz,fx+fw),min(gd,fy+fh)
                            if cz<=cx or cd<=cy:continue
                            if fringe['chosen_source_level']==225:
                                owned+=int(np.count_nonzero(visible_labels[cy:cd,cx:cz]==fringe['source_component_id']))
                            else:
                                # The complete chosen component was proved
                                # above with no independent source island.
                                owned+=int(np.count_nonzero(a[cy:cd,cx:cz]<=fringe['chosen_source_level']))
                        if not owned:continue
                        guard_background=_bar_guard_source_obligations(a,visible,fringes,source_guard_window)
                        if guard_background is None:continue
                        guard_bar_component_pixels=owned
                return {'kind':'source_parallel_bars_paired_signed_form_id','parallel_bar_count':len(group),
                        'bar_bbox':list(box),'hard128_bar_bbox':list(hard_box),'visible225_bar_bbox':list(visible_box),
                        'source_fringe_bar_components':fringes,
                        'guard_source_pixel_window':source_guard_window,'guard_bar_component_pixels':guard_bar_component_pixels,
                        'guard_weak_source_background_diagnostics':guard_background,
                        'source_visible_bar_components':visible,'source_visible_bar_threshold':225,
                        'label_bbox':list(label.bbox),'paired_student_id':value,
                        'student_id_field_bbox':list(matches[0][1]),'student_id_value_bbox':list(matches[0][2]),
                        'source_bar_pixel_boxes':[list(q[2]) for q in group],'source_shape':[h,w],
                        'source_pixel_sha256':hashlib.sha256(a.tobytes()).hexdigest(),
                        'source_to_display':list(source_to_display),'source_bbox':list(source_bbox),
                        'decision_schema_proof':dict(proof),'display_regions':[list(r) for r in regions],
                        'independent_regions_veto_checked':True,'opaque_source_only':True}
    return None


def exact_contiguous_source_partitions(views):
    """Return maximal equal-pitch original pixel partitions without resampling.

    Views are dictionaries with pixels, source_bbox and source_to_display.
    Member indices refer to the unchanged input list. Unmatched views remain
    the caller's independent source obligations; a partial header partition
    supplies barcode pixels, not proof of a complete physical paper boundary.
    """
    valid=[]
    for index,view in enumerate(views):
        g=_geometry(view['pixels'],view['source_bbox'],view['source_to_display'],view['source_bbox'],view.get('alpha'))
        if g is not None:valid.append((index,view,g))
    results=[];consumed=set()
    for axis in (0,1):
        moving=1-axis;fixed=axis;candidates=[]
        for first in valid:
            if first[0] in consumed:continue
            chain=[first];seen={first[0]}
            while True:
                _,_,prior=chain[-1];px,pm,po,*_=prior
                following=[]
                for candidate in valid:
                    index,_,g=candidate
                    if index in seen or index in consumed:continue
                    q,qm,qo,*_=g
                    if q.shape[1-axis]!=px.shape[1-axis]:continue
                    if np.max(np.abs(qm[:,fixed]-pm[:,fixed]))>1e-4:continue
                    if np.max(np.abs(qm[:,moving]/q.shape[axis]-pm[:,moving]/px.shape[axis]))>np.linalg.norm(pm[:,moving])/px.shape[axis]*1e-5:continue
                    displacement=qo-(po+pm[:,moving])
                    if np.max(np.abs(displacement))<=1e-4:following.append(candidate)
                if len(following)!=1:break
                chain.append(following[0]);seen.add(following[0][0])
            if len(chain)>=2:candidates.append(chain)
        for chain in sorted(candidates,key=len,reverse=True):
            indices=[q[0] for q in chain]
            if any(i in consumed for i in indices):continue
            planes=[q[2][0] for q in chain];pixels=np.concatenate(planes,axis=axis)
            matrix=chain[0][2][1].copy();offset=chain[0][2][2].copy()
            matrix[:,moving]=sum((q[2][1][:,moving] for q in chain),np.zeros(2))
            transform=[matrix[0,0],matrix[1,0],matrix[0,1],matrix[1,1],offset[0],offset[1]]
            h,w=pixels.shape;box=_display_box((0,0,w,h),matrix,offset,w,h)
            errors=[(right[2][2]-(left[2][2]+left[2][1][:,moving])).tolist() for left,right in zip(chain,chain[1:])]
            originals=np.asarray([q[1]['source_bbox'] for q in chain]);union=np.r_[originals[:,:2].min(axis=0),originals[:,2:].max(axis=0)]
            endpoint_error=float(np.max(np.abs(np.asarray(box)-union)))
            if endpoint_error>1e-4:continue
            results.append({'pixels':pixels,'source_bbox':list(box),'source_to_display':transform,
                            'kind':'exact_contiguous_original_source_partition','array_axis':axis,
                            'source_indices':indices,'source_shapes':[list(p.shape) for p in planes],
                            'source_pixel_hashes':[hashlib.sha256(p.tobytes()).hexdigest() for p in planes],
                            'partition_pixel_sha256':hashlib.sha256(pixels.tobytes()).hexdigest(),
                            'original_source_to_display':[list(q[1]['source_to_display']) for q in chain],
                            'original_source_bboxes':[list(q[1]['source_bbox']) for q in chain],
                            'join_displacements_points':errors,
                            'maximum_join_roundoff_points':max([endpoint_error]+[max(map(abs,e)) for e in errors]),
                            'resampled':False})
            consumed.update(indices)
    return tuple(results)


def _whole_source_edge(g,source_edge,ink_labels,ink_parts):
    """Private component primitive; it grants no partial-carrier exemption."""
    a,matrix,offset,inverse,b,page,pitches=g;h,w=a.shape
    axis=1 if source_edge in {'top','bottom'} else 0
    outer=(ink_labels[0] if source_edge=='top' else ink_labels[-1] if source_edge=='bottom' else
           ink_labels[:,0] if source_edge=='left' else ink_labels[:,-1])
    if np.any(outer==0):return None
    pitch=pitches[axis];normal=max(1,math.ceil(2/pitch))
    band=(ink_labels[:normal] if source_edge=='top' else ink_labels[-normal:] if source_edge=='bottom' else
          ink_labels[:,:normal] if source_edge=='left' else ink_labels[:,-normal:])
    ids={int(v) for v in np.unique(outer) if v}
    if not ids:return None
    parts=[];depths=[]
    for n in ids:
        x,y,bw,bh,area=map(int,ink_parts[n]);depth=(bh if axis==1 else bw)*pitch
        full=(x==0 and bw==w and (y==0 if source_edge=='top' else y+bh==h)) if axis==1 else (y==0 and bh==h and (x==0 if source_edge=='left' else x+bw==w))
        if not full or depth>2+1e-6:return None
        parts.append([x,y,bw,bh,area]);depths.append(depth)
    return {'source_edge':source_edge,'source_components':parts,'whole_edge_coverage':1.0,
            'maximum_component_depth_points':max(depths),'source_ids':ids}


def prove_contiguous_paper_boundary(views,*,page_bbox,guard,guard_kind,display_sample_pitch,independent_regions=()):
    """Prove a full shallow physical edge across original opaque paper planes.

    Different along-edge pitches stay separate. Group geometry must cover at
    least 95% of the page through exact contiguous rectangular seams. Each
    original edge component, including unobserved guard segments, must span
    its complete source edge and contain no body stem or separate normal-band
    ink. No source pixel is resampled; a partial tile alone supplies no proof.
    """
    import cv2
    if guard_kind not in {'_GraphicGuard','_VisibleInkGuard'} or len(views)<2:return None
    if not 0<display_sample_pitch<=1 or any(_intersects(guard,b) for b in independent_regions):return None
    geometries=[]
    for view in views:
        g=_geometry(view['pixels'],view['source_bbox'],view['source_to_display'],page_bbox,view.get('alpha'))
        if g is None:return None
        geometries.append(g)
    boxes=np.asarray([g[4] for g in geometries]);union=np.r_[boxes[:,:2].min(axis=0),boxes[:,2:].max(axis=0)];page=geometries[0][5]
    along=None;order=None;gaps=None
    for candidate in (0,1):
        fixed=1-candidate
        if max(np.ptp(boxes[:,fixed]),np.ptp(boxes[:,fixed+2]))>1e-4:continue
        candidate_order=np.argsort(boxes[:,candidate]);candidate_gaps=[float(boxes[r,candidate]-boxes[l,candidate+2]) for l,r in zip(candidate_order,candidate_order[1:])]
        if any(abs(v)>1e-4 for v in candidate_gaps):continue
        along=candidate;order=candidate_order;gaps=candidate_gaps;break
    if along is None:return None
    visible=np.maximum(0,np.minimum(union[2:],page[2:])-np.maximum(union[:2],page[:2]));coverage=float(np.prod(visible)/np.prod(page[2:]-page[:2]))
    if coverage<.95:return None
    guard=np.asarray(guard,dtype=float)
    if guard.shape!=(4,) or not np.all(np.isfinite(guard)) or min(guard[2:]-guard[:2])<=0:return None
    overshoot=np.maximum(0,np.r_[union[:2]-guard[:2],guard[2:]-union[2:]])
    if overshoot.max()>display_sample_pitch+1e-6:return None
    prepared=[]
    for g in geometries:
        _,labels,parts,_=cv2.connectedComponentsWithStats((g[0]<=225).astype('uint8'),8);prepared.append((labels,parts))
    for display_edge,axis,side in (('left',0,0),('right',0,2),('top',1,1),('bottom',1,3)):
        normal_extent=min(guard[axis+2],union[axis+2])-max(guard[axis],union[axis])
        if not 0<normal_extent<=2+1e-6:continue
        members=[i for i,b in enumerate(boxes) if abs(b[side]-union[side])<=1e-4]
        if not members:continue
        source_proofs=[];windows=[];failed=False;edge_ids={};source_edges={}
        for index in members:
            g=geometries[index];a,matrix,offset,inverse,b,_,pitches=g;h,w=a.shape;labels,parts=prepared[index]
            source_edge=None
            for name,point in (('left',(0,.5)),('right',(1,.5)),('top',(.5,0)),('bottom',(.5,1))):
                mapped=matrix@point+offset
                if abs(mapped[axis]-b[side])<=1e-4:source_edge=name;break
            if source_edge is None:failed=True;break
            proof=_whole_source_edge(g,source_edge,labels,parts)
            if proof is None:failed=True;break
            edge_ids[index]=proof['source_ids'];source_edges[index]=source_edge
            sample=None
            clipped=np.r_[np.maximum(guard[:2],b[:2]),np.minimum(guard[2:],b[2:])]
            if min(clipped[2:]-clipped[:2])>0:
                pts=(np.array(((clipped[0],clipped[1]),(clipped[2],clipped[1]),(clipped[0],clipped[3]),(clipped[2],clipped[3])))-offset)@inverse.T
                lo=np.maximum(0,pts.min(axis=0)*[w,h]);hi=np.minimum([w,h],pts.max(axis=0)*[w,h]);x,y=np.floor(lo+1e-7).astype(int);z,d=np.ceil(hi-1e-7).astype(int)
                chosen={int(n) for n in np.unique(labels[y:d,x:z]) if n}
                if not chosen or not chosen<=proof['source_ids']:failed=True;break
                sample=[int(x),int(y),int(z),int(d)];windows.append(index)
            source_proofs.append({'source_index':index,'source_bbox':b.tolist(),
                                  'source_to_display':list(views[index]['source_to_display']),
                                  'source_shape':[h,w],'source_pixel_sha256':hashlib.sha256(a.tobytes()).hexdigest(),
                                  'guard_source_pixel_window':sample,**{k:v for k,v in proof.items() if k!='source_ids'}})
        if failed or not windows:continue
        # Inspect the exact normal span this proof can own across the whole
        # edge, including planes outside the requested guard. Disconnected
        # ink farther inside the paper is not part of this proved edge; its
        # separate guards remain unowned. The ceiling is still strictly 2pt.
        proved_band=max(normal_extent,max(v['maximum_component_depth_points'] for v in source_proofs))
        for index in members:
            g=geometries[index];labels=prepared[index][0];source_edge=source_edges[index]
            original_axis=1 if source_edge in {'top','bottom'} else 0
            count=max(1,math.ceil(proved_band/g[-1][original_axis]-1e-7))
            band=(labels[:count] if source_edge=='top' else labels[-count:] if source_edge=='bottom' else
                  labels[:,:count] if source_edge=='left' else labels[:,-count:])
            if not {int(n) for n in np.unique(band) if n}<=edge_ids[index]:failed=True;break
        if failed:continue
        # Every physical piece of the guard must belong to an edge member;
        # geometry alone never licenses pixels from another paper plane.
        if any(_intersects(guard,b) and i not in members for i,b in enumerate(boxes)):continue
        return {'kind':'source_contiguous_paper_physical_boundary','display_edge':display_edge,
                'paper_group_bbox':union.tolist(),'paper_group_coverage_fraction':coverage,
                'source_plane_count':len(views),'source_planes':source_proofs,
                'source_plane_bboxes':boxes.tolist(),'physical_partition_axis':along,
                'physical_plane_order':[int(i) for i in order],'exact_seam_roundoff_points':gaps,
                'guard_bbox':guard.tolist(),'display_roundoff_outside_source':overshoot.tolist(),
                'display_sample_pitch':display_sample_pitch,'maximum_component_depth_points':max(v['maximum_component_depth_points'] for v in source_proofs),
                'source_visible_ink_threshold':225,'maximum_guard_owned_normal_band_points':proved_band,
                'resampled':False,'opaque_source_only':True,
                'independent_regions_veto_checked':True}
    return None
