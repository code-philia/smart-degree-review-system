"""Verify render proposals against original embedded source pixels."""
import io
import pymupdf

def scan_carrier_partition(boxes,width,height):
    """Recognize a paper-sized raster or its contiguous scanner strips.

    This only selects an OCR/source inspection. It supplies no page exemption.
    """
    if any((b[2]-b[0])*(b[3]-b[1])>=width*height*.85 for b in boxes):return True
    for axis,span,extent in ((0,width,height),(1,height,width)):
        tiles=[b for b in boxes if b[axis+2]-b[axis]>=span*.85]
        if len(tiles)<2:continue
        along=1-axis;tiles=sorted(tiles,key=lambda b:b[along])
        if (max(b[axis] for b in tiles)-min(b[axis] for b in tiles)>2
                or max(b[axis+2] for b in tiles)-min(b[axis+2] for b in tiles)>2):continue
        if any(not -1<=right[along]-left[along+2]<=2 for left,right in zip(tiles,tiles[1:])):continue
        covered=sum((b[2]-b[0])*(b[3]-b[1]) for b in tiles)
        if covered>=width*height*.85 and tiles[-1][along+2]-tiles[0][along]>=extent*.85:return True
    return False

def _coalesce_scan_sources(pdf,images,width,height,masks):
    """Keep maximal exact pixel joins, and retain every unmatched source."""
    import numpy as np
    from PIL import Image
    from .scan_boundary_proof import exact_contiguous_source_partitions
    source_infos=[i for i in images if i.get('xref') and i['xref'] not in masks]
    views=[{'pixels':np.asarray(Image.open(io.BytesIO(pdf.extract_image(i['xref'])['image'])).convert('L')),
            'source_bbox':i['bbox'],'source_to_display':i['transform']} for i in source_infos]
    groups=exact_contiguous_source_partitions(views)
    consumed=set();virtuals=[];records=[]
    for group in groups:
        members=[source_infos[n] for n in group['source_indices']]
        consumed.update(id(i) for i in members)
        pixels=group['pixels']
        virtual={**members[0],'bbox':tuple(group['source_bbox']),
                 'width':pixels.shape[1],'height':pixels.shape[0],
                 'transform':tuple(group['source_to_display']),
                 'bpc':members[0]['bpc'] if len({i['bpc'] for i in members})==1 else 8,
                 '_source_pixels':pixels,'_source_partition_xrefs':[i['xref'] for i in members]}
        virtuals.append(virtual)
        record={k:v for k,v in group.items() if k!='pixels'}
        record['xrefs']=virtual['_source_partition_xrefs']
        records.append(record)
    return virtuals+[i for i in images if id(i) not in consumed],records

def _paper_partition_sources(images,width,height,masks):
    """Qualify contiguous opaque paper tiles, without assuming equal pitch."""
    for axis,span,extent in ((0,width,height),(1,height,width)):
        along=1-axis
        tiles=[i for i in images if i.get('xref') and i['xref'] not in masks
               and i['bbox'][axis+2]-i['bbox'][axis]>=span*.85
               and abs(i['transform'][1])+abs(i['transform'][2])<=1e-5
               and i['transform'][0]>0 and i['transform'][3]>0]
        if len(tiles)<2:continue
        tiles.sort(key=lambda i:i['bbox'][along]);boxes=[i['bbox'] for i in tiles]
        if (max(b[axis] for b in boxes)-min(b[axis] for b in boxes)>.02
                or max(b[axis+2] for b in boxes)-min(b[axis+2] for b in boxes)>.02):continue
        if any(abs(right[along]-left[along+2])>.02 for left,right in zip(boxes,boxes[1:])):continue
        visible=sum((pymupdf.Rect(b)&pymupdf.Rect(0,0,width,height)).get_area() for b in boxes)
        if visible<width*height*.85 or boxes[-1][along+2]-boxes[0][along]<extent*.85:continue
        return {i['xref'] for i in tiles},[{'kind':'contiguous_opaque_source_paper_tiles',
             'xrefs':[i['xref'] for i in tiles],'source_bboxes':[list(b) for b in boxes],
             'source_partition_xrefs':[i.get('_source_partition_xrefs',[i['xref']]) for i in tiles],
             'whole_paper_visible_coverage':visible/(width*height),
             'source_pitch_preserved':True,'resampling_used_for_partition_ownership':False}]
    return set(),[]

def scan_barcode_regions(gray,scale,hits):
    """Own only proved margin bars and their adjacent numerical reading."""
    import cv2,numpy as np,re
    height,width=gray.shape[0]/scale,gray.shape[1]/scale
    _,_,parts,_=cv2.connectedComponentsWithStats((gray<128).astype('uint8'),8)
    bars=[tuple(map(int,p)) for p in parts[1:]
          if .2*scale<=p[2]<=6*scale and 10*scale<=p[3]<=60*scale
          and p[3]>4*p[2] and p[4]/(p[2]*p[3])>=.7]
    regions=[]
    while bars:
        seed=bars.pop(0);group=[seed]
        peers=[p for p in bars if abs(p[1]-seed[1])<=2*scale and abs(p[3]-seed[3])<=2*scale]
        for p in peers:bars.remove(p)
        group.extend(peers);group.sort(key=lambda p:p[0])
        runs=[[]]
        for p in group:
            if runs[-1] and p[0]-runs[-1][-1][0]-runs[-1][-1][2]>4*scale:runs.append([])
            runs[-1].append(p)
        for run in runs:
            if len(run)<12:continue
            box=(min(p[0] for p in run)/scale,min(p[1] for p in run)/scale,
                 max(p[0]+p[2] for p in run)/scale,max(p[1]+p[3] for p in run)/scale)
            if box[2]-box[0]>width*.35 or not (box[1]<=height*.04 and box[3]<=height*.09):continue
            labels=[h for h in hits if h.score>=.85 and re.fullmatch(r'[:：.\-\s]*[0-9]{6,24}',h.text.strip())
                    and -5<=h.bbox[1]-box[3]<=12 and h.bbox[3]-h.bbox[1]<=22
                    and h.bbox[0]>=box[0]-12 and h.bbox[2]<=box[2]+12]
            if not labels:continue
            regions.append((box[0]-2,box[1]-2,box[2]+2,box[3]+2))
            regions.extend((h.bbox[0]-3,h.bbox[1]-3,h.bbox[2]+3,h.bbox[3]+3) for h in labels)
    return regions

def _jpeg_block_background(pixels,box,cache):
    """Prove repeated JPEG blocks, never merely faint ink.

    Require identical complete codec-sized blocks at three distant source
    locations and edge-bound lobes without glyph counters. Qualify either
    low-frequency DCT variation or row-constant stripes in the last complete
    source codec row. Real text and independent image layers keep guards.
    """
    import cv2,numpy as np
    h,w=pixels.shape;x1,y1,x2,y2=box;proof=[]
    for y in range(y1//8*8,y2,8):
        for x in range(x1//8*8,x2,8):
            block=pixels[y:y+8,x:x+8]
            if block.shape!=(8,8):return None
            paper=int(block.max())
            if int(block.min())==paper:continue
            if paper<250 or paper-int(block.min())>12:return None
            if not np.array_equal(block,block[:,::-1]):return None
            ink=(block<paper).astype('uint8')
            count,labels,parts,_=cv2.connectedComponentsWithStats(ink,8)
            # The last complete codec row can carry repeating horizontal
            # scan stripes whose energy is high-frequency. Every source row
            # must be constant; body blocks and glyph shapes do not qualify.
            boundary_stripe=(y==(h//8-1)*8 and np.all(block==block[:,:1]))
            if (count<3 and not boundary_stripe) or any(not (a==0 or b==0 or a+c==8 or b+d==8) for a,b,c,d,size in parts[1:]):return None
            inverse=np.pad(1-ink,1,constant_values=1)
            n,holes,_,_=cv2.connectedComponentsWithStats(inverse,8)
            if n>2:return None
            coefficients=cv2.dct(block.astype('float32'));coefficients[0,0]=0
            energy=float(np.sum(coefficients**2))
            low=float(np.sum(coefficients[:4,:4]**2))/energy if energy else 0
            if low<.96 and not boundary_stripe:return None
            key=block.tobytes()
            if key not in cache:
                locations=[]
                for b in range(0,h-7,8):
                    for a in range(0,w-7,8):
                        if pixels[b:b+8,a:a+8].tobytes()==key:locations.append((a,b))
                cache[key]=locations
            locations=cache[key]
            # Separate copies across the scan, not adjacent glyphs or a line.
            buckets={(a//128,b//128) for a,b in locations}
            if len(locations)<3 or len(buckets)<3:return None
            proof.append({'source_block':[x,y,8,8],'exact_repetitions':[list(p) for p in locations],
                          'low_frequency_dct_energy':low,'has_glyph_counter':False,
                          'source_boundary_row_stripe':bool(boundary_stripe)})
    return proof or None

def _dense_source_graphics(pixels,info,display_rotation_matrix):
    """Keep actual filled source graphics; JPEG soft joins are not fills."""
    import cv2,numpy as np
    h,w=pixels.shape;transform=pymupdf.Matrix(*info['transform'])
    support=(pixels<255).astype('uint8')
    _,_,parts,_=cv2.connectedComponentsWithStats(support,8)
    proofs=[]
    for x,y,bw,bh,area in parts[1:]:
        box=pymupdf.Rect((x/w,y/h,(x+bw)/w,(y+bh)/h))*transform
        if box.width<10 or box.height<10 or area<.65*bw*bh:continue
        patch=pixels[y:y+bh,x:x+bw]
        values=patch[support[y:y+bh,x:x+bw]!=0]
        dark_density=float(np.count_nonzero(patch<=225))/(bw*bh)
        tone_span=int(values.max())-int(values.min())
        # Gray JPEG pixels connect printed rows at paper-1. Those components
        # are mostly paper-colored and span the full text contrast range.
        if dark_density<.65 and tone_span>20:continue
        display=box*display_rotation_matrix
        proofs.append({'kind':'nontransparent_source_graphic','xref':info['xref'],
                       'bbox':list(display),'source_box':[int(x),int(y),int(bw),int(bh)],
                       'visible_source_pixels':int(area),'source_dark_density':dark_density,
                       'occupied_source_tone_span':tone_span})
    return proofs

def _alpha_form_source(pixels,info,rotation):
    """A common transform cannot give a separate layer form ownership."""
    import cv2,numpy as np
    from dataclasses import replace
    from .local_ocr import _read_tile
    from .signature_structure import _declaration_regions,_decision_regions
    mode=int(np.bincount(pixels.ravel(),minlength=256).argmax())
    ys,xs=np.where(pixels<mode)
    if not len(xs):return True,{'kind':'uniform_source_alpha_paper','xref':info['xref']}
    # A localized overlay has no independently observed complete paper form.
    if (xs.max()-xs.min()<pixels.shape[1]*.25
            or ys.max()-ys.min()<pixels.shape[0]*.25):
        return False,{'kind':'localized_alpha_source_without_form','xref':info['xref']}
    box=pymupdf.Rect(info['bbox'])
    width,height=(box.height,box.width) if rotation%180 else (box.width,box.height)
    display=np.rot90(pixels,-rotation//90) if rotation else pixels
    # Preserve the intrinsic source pitch; downsampling a separate printed
    # form layer can erase the very field evidence this check must prove.
    scale=min(display.shape[1]/width,display.shape[0]/height,2400/max(width,height))
    image=cv2.resize(display,(max(1,round(width*scale)),max(1,round(height*scale))))
    spread=int(image.max())-int(image.min())
    if 0<spread<=20:
        image=np.rint((image.astype('float32')-image.min())*255/spread).astype('uint8')
    hits=tuple(replace(h,bbox=tuple(v/scale for v in h.bbox)) for h in _read_tile(image))
    barcodes=scan_barcode_regions(image,scale,hits)
    regions=_declaration_regions(hits,width,height,barcodes,gray=image,scale=scale)
    if not regions:regions=_decision_regions(hits,width,height,image,scale)
    return bool(regions),{'kind':'source_alpha_form_cpu_read','xref':info['xref'],
                          'observed_rows':len(hits),'complete_source_schema':bool(regions),
                           'source_ocr_sample_pitch':scale,'source_shape':list(pixels.shape)}

def source_artifacts(document,page,regions,guards,*,observations=(),decision_schema_proof=None,display_sample_pitch=.5):
    import cv2,numpy as np
    from PIL import Image
    from .page_policy import _inside
    from .local_ocr import signature_remainder_view
    retained=[];proofs=[];texture_cache={}
    class _IndependentInkGuard(tuple):pass
    with pymupdf.open(document.path) as pdf:
        raw=pdf[page.number-1]
        native=[]
        for block in raw.get_text('dict')['blocks']:
            for line in block.get('lines',[]):
                text=''.join(s['text'] for s in line.get('spans',[]))
                box=tuple(pymupdf.Rect(line['bbox'])*raw.rotation_matrix)
                if text.strip() and not any(_inside(box,b,3) for b in regions):native.append(box)
        for drawing in raw.get_drawings():
            box=tuple(drawing['rect']*raw.rotation_matrix)
            # A field rectangle does not establish ownership of an
            # independent native path, including an unfilled or pale plot.
            painted=any(drawing.get(style) is not None
                        and drawing.get(opacity,1)>0
                        and any(v<.999 for v in drawing[style])
                        for style,opacity in (("fill","fill_opacity"),("color","stroke_opacity")))
            if painted:native.append(box)
        if native:return guards+[_IndependentInkGuard(b) for b in native],[{'kind':'independent_native_ink','regions':[list(b) for b in native]}]
        images=raw.get_image_info(xrefs=True);carriers=[];barcodes=[]
        masks={entry[0]:entry[1] for entry in raw.get_images(full=True) if entry[1]}
        work_images,partition_records=_coalesce_scan_sources(pdf,images,float(raw.mediabox.width),float(raw.mediabox.height),masks)
        proofs.extend(partition_records)
        partition_ids,tile_proofs=_paper_partition_sources(work_images,float(raw.mediabox.width),float(raw.mediabox.height),masks)
        proofs.extend(tile_proofs)
        for info in work_images:
            if not info.get('xref'):continue
            box=pymupdf.Rect(info['bbox'])*raw.rotation_matrix
            visible=box&raw.rect
            encoded=({'ext':'source_partition'} if info.get('_source_partition_xrefs') else pdf.extract_image(info['xref']))
            pixels=(info['_source_pixels'] if '_source_pixels' in info else np.asarray(Image.open(io.BytesIO(encoded['image'])).convert('L')))
            if info['xref'] in masks:
                alpha=np.asarray(Image.open(io.BytesIO(pdf.extract_image(masks[info['xref']])['image'])).convert('L'))
                if alpha.shape!=pixels.shape:continue
                # Transparent source values are not visible page ink. Keep
                # every partly visible stroke and its original alpha coverage.
                pixels=np.rint(pixels.astype('float32')*alpha/255+255-alpha).astype('uint8')
            graphic_proofs=(_dense_source_graphics(pixels,info,raw.rotation_matrix)
                if info['xref'] in masks or box.get_area()<raw.rect.get_area()*.85 else [])
            proofs.extend(graphic_proofs)
            retained.extend(_IndependentInkGuard(p["bbox"]) for p in graphic_proofs)
            from .barcode_carriers import _one_dimensional_bars
            if (visible.width<=raw.rect.width*.35 and visible.height<=raw.rect.height*.12
                    and (visible.y1<raw.rect.height*.12 or visible.y0>raw.rect.height*.9)
                    and (_one_dimensional_bars(pixels) or _one_dimensional_bars(np.rot90(pixels,2)))):
                barcodes.append((info['xref'],tuple(box),None))
            if info['bpc']==1 and (box.y1<raw.rect.height*.065 or visible.width<raw.rect.width*.025 and visible.x0>raw.rect.width*.96):
                _,_,parts,_=cv2.connectedComponentsWithStats((pixels<128).astype('uint8'),8)
                bars=int(sum(w<max(20,pixels.shape[1]*.04) and h>pixels.shape[0]*.4 for x,y,w,h,area in parts[1:]))
                if bars>=12:barcodes.append((info['xref'],tuple(box),bars))
            if info['width']<1000 or (box.get_area()<raw.rect.get_area()*.85 and info['xref'] not in partition_ids):continue
            inverse=pymupdf.Matrix(*info['transform']);inverse.invert()
            h,w=pixels.shape;scale=w/pymupdf.Rect(info['bbox']).width
            normalized=[pymupdf.Rect(b)*raw.derotation_matrix*inverse for b in regions]
            source_regions=[tuple(v*(w if n%2==0 else h)/scale for n,v in enumerate(b)) for b in normalized]
            _,source_guards,artifacts=signature_remainder_view(pixels,scale,source_regions,display_rotation=0)
            mapped=[];transform=pymupdf.Matrix(*info['transform'])
            for source_guard in source_guards:
                b=pymupdf.Rect(tuple(v*scale/(w if n%2==0 else h) for n,v in enumerate(source_guard)))*transform*raw.rotation_matrix
                mapped.append(tuple(b))
            mode=int(np.bincount(pixels.ravel(),minlength=256).argmax())
            _,labels,parts,_=cv2.connectedComponentsWithStats((pixels<mode).astype('uint8'),8)
            carriers.append((info,pixels,inverse,mapped,mode,labels,parts))
            # A pale solid image can disappear from the displayed morphology
            # and from glyph proposals. Its actual nontransparent source ink
            # still has an independent obligation outside the proved form.
            if info['xref'] in masks:
                source_ink=(pixels<mode).astype('uint8')
                owns_form,layer_proof=_alpha_form_source(pixels,info,raw.rotation)
                proofs.append(layer_proof)
                if not owns_form and source_ink.any():
                    ys,xs=np.where(source_ink)
                    support=(float(xs.min()/w),float(ys.min()/h),
                             float((xs.max()+1)/w),float((ys.max()+1)/h))
                    guarded=tuple(pymupdf.Rect(support)*transform*raw.rotation_matrix)
                    retained.append(_IndependentInkGuard(guarded))
                    proofs.append({'kind':'independent_alpha_source_ink',
                                   'xref':info['xref'],'bbox':list(guarded)})
        carrier_ids={i['xref'] for i,*_ in carriers}
        carrier_ids.update(x for i,*_ in carriers for x in i.get('_source_partition_xrefs',[]))
        barcode_ids={b[0] for b in barcodes}
        # Some scans encode one paper carrier as aligned background and
        # alpha foreground images. Their separate source values still need
        # individual residual checks; their common transform is not a new
        # independent research image layer.
        aligned_carrier=(bool(carriers) and all(max(abs(a-b) for a,b in zip(i['transform'],carriers[0][0]['transform']))<=.5
                                               for i,*_ in carriers))
        partition_carrier=bool(partition_ids) and partition_ids<={i['xref'] for i,*_ in carriers}
        qualified_carrier=aligned_carrier or partition_carrier
        independent=[]
        for info in images:
            box=tuple(pymupdf.Rect(info['bbox'])*raw.rotation_matrix)
            if info['xref'] in barcode_ids:continue
            if info['xref'] in carrier_ids and qualified_carrier:continue
            if not any(_inside(box,b,3) for b in regions):independent.append(box)
        if independent:
            return guards+[_IndependentInkGuard(b) for b in independent],[{'kind':'independent_image_layers','regions':[list(b) for b in independent]}]
        from .scan_boundary_proof import prove_signed_form_barcode,prove_continuous_source_boundary,prove_contiguous_paper_boundary
        independent_regions=[b for b in retained if type(b).__name__=='_IndependentInkGuard']
        measured_barcodes=[]
        if decision_schema_proof:
            for source_info,source_pixels,*_ in carriers:
                if source_info['xref'] in masks:continue
                proof=prove_signed_form_barcode(source_pixels,
                    source_bbox=tuple(pymupdf.Rect(source_info['bbox'])*raw.rotation_matrix),
                    source_to_display=tuple(pymupdf.Matrix(*source_info['transform'])*raw.rotation_matrix),
                    page_bbox=tuple(raw.rect),observations=observations,
                    decision_schema_proof=decision_schema_proof,
                    independent_regions=independent_regions,display_sample_pitch=display_sample_pitch)
                if proof:
                    proof['xref']=source_info['xref']
                    proof['source_partition_xrefs']=source_info.get('_source_partition_xrefs',[])
                    measured_barcodes.append(proof)
        for guard in guards:
            candidates=[p for p in measured_barcodes if type(guard).__name__!='_IndependentInkGuard'
                          and any(_inside(guard,b,display_sample_pitch) for b in p['display_regions'])]
            matched=None
            for candidate in candidates:
                source_info,source_pixels,*_=next(c for c in carriers if c[0]['xref']==candidate['xref'])
                # The group rectangle is a proposal. Every actual guard
                # needs ink from an individually proved original component.
                matched=prove_signed_form_barcode(source_pixels,
                    source_bbox=tuple(pymupdf.Rect(source_info['bbox'])*raw.rotation_matrix),
                    source_to_display=tuple(pymupdf.Matrix(*source_info['transform'])*raw.rotation_matrix),
                    page_bbox=tuple(raw.rect),observations=observations,
                    decision_schema_proof=decision_schema_proof,guard=guard,
                    independent_regions=independent_regions,display_sample_pitch=display_sample_pitch)
                if matched is not None:
                    matched.update(xref=source_info['xref'],
                                   source_partition_xrefs=source_info.get('_source_partition_xrefs',[]))
                    break
            if matched is not None:
                proofs.append(dict(matched,guard_bbox=list(guard)));continue
            boundary=None
            if type(guard).__name__ in {'_GraphicGuard','_VisibleInkGuard'} and len(carriers)==1:
                source_info,source_pixels,*_=carriers[0]
                if source_info['xref'] not in masks:
                    boundary=prove_continuous_source_boundary(source_pixels,
                        source_bbox=tuple(pymupdf.Rect(source_info['bbox'])*raw.rotation_matrix),
                        source_to_display=tuple(pymupdf.Matrix(*source_info['transform'])*raw.rotation_matrix),
                        page_bbox=tuple(raw.rect),guard=guard,guard_kind=type(guard).__name__,
                        display_sample_pitch=display_sample_pitch,independent_regions=independent_regions)
            if boundary is None and qualified_carrier and len(carriers)>1 and all(c[0]['xref'] not in masks for c in carriers):
                views=[{'pixels':c[1],
                        'source_bbox':tuple(pymupdf.Rect(c[0]['bbox'])*raw.rotation_matrix),
                        'source_to_display':tuple(pymupdf.Matrix(*c[0]['transform'])*raw.rotation_matrix)}
                       for c in carriers]
                boundary=prove_contiguous_paper_boundary(views,page_bbox=tuple(raw.rect),
                    guard=guard,guard_kind=type(guard).__name__,display_sample_pitch=display_sample_pitch,
                    independent_regions=independent_regions)
                if boundary:
                    for source_proof in boundary['source_planes']:
                        source_info=carriers[source_proof['source_index']][0]
                        source_proof.update(xref=source_info['xref'],
                            source_partition_xrefs=source_info.get('_source_partition_xrefs',[]))
            if boundary is not None:
                proofs.append(dict(boundary,xref=carriers[0][0]['xref']));continue
            if type(guard).__name__ in {'_GraphicGuard','_TextGuard'}:retained.append(guard);continue
            barcode=next((b for b in barcodes if _inside(guard,b[1],3)),None)
            if barcode is not None:
                proofs.append({'kind':'source_parallel_margin_barcode','bbox':list(guard),'xref':barcode[0],'bars':barcode[2]});continue
            if not qualified_carrier:retained.append(guard);continue
            if len(carriers)>1:
                if any((pymupdf.Rect(guard)&pymupdf.Rect(b)).get_area()>0 for _,_,_,source_guards,*_ in carriers for b in source_guards):
                    retained.append(guard);continue
                # An omitted source proposal is not proof that visible ink is
                # absent. Only an actually uniform paper patch in every
                # original aligned layer can own a render-only observation.
                uniform=True
                covered=False
                for source_info,source_pixels,source_inverse,_,source_mode,*_ in carriers:
                    source_display=pymupdf.Rect(source_info["bbox"])*raw.rotation_matrix
                    if (pymupdf.Rect(guard)&source_display).get_area()<=0:continue
                    covered=True
                    source_box=pymupdf.Rect(guard)*raw.derotation_matrix*source_inverse
                    sh,sw=source_pixels.shape
                    patch=source_pixels[max(0,int(source_box.y0*sh)):min(sh,int(source_box.y1*sh)+1),
                                        max(0,int(source_box.x0*sw)):min(sw,int(source_box.x1*sw)+1)]
                    if not patch.size or not np.all(patch==source_mode):uniform=False;break
                if type(guard).__name__=='_VisibleInkGuard' or not uniform or not covered:retained.append(guard);continue
                proofs.append({'kind':'aligned_source_layer_reproposal','bbox':list(guard),
                               'xrefs':sorted(carrier_ids),'alpha_masked_xrefs':sorted(carrier_ids & masks.keys())});continue
            if any(i['xref'] not in carrier_ids|barcode_ids and (pymupdf.Rect(guard)&(pymupdf.Rect(i['bbox'])*raw.rotation_matrix)).get_area()>0 for i in images):
                retained.append(guard);continue
            info,pixels,inverse,source_guards,mode,labels,parts=carriers[0]
            h,w=pixels.shape;b=pymupdf.Rect(guard)*raw.derotation_matrix*inverse
            x1=max(0,int(b.x0*w));y1=max(0,int(b.y0*h));x2=min(w,int(b.x1*w)+1);y2=min(h,int(b.y1*h)+1)
            encoded=({'ext':'source_partition'} if info.get('_source_partition_xrefs') else pdf.extract_image(info['xref']))
            repeated=(_jpeg_block_background(pixels,(x1,y1,x2,y2),texture_cache)
                      if encoded.get('ext') in {'jpg','jpeg'} and type(guard).__name__ not in
                      {'_TextGuard','_GraphicGuard','_IndependentInkGuard','_VisibleInkGuard'} else None)
            if repeated:
                proofs.append({'kind':'repeated_source_jpeg_background_blocks','bbox':list(guard),
                               'xref':info['xref'],'blocks':repeated});continue
            if any((pymupdf.Rect(guard)&pymupdf.Rect(b)).get_area()>0 for b in source_guards):
                retained.append(guard);continue
            if type(guard).__name__=='_VisibleInkGuard':
                # Only the explicit shallow physical-edge/barcode proofs
                # above can own visible ink. A page-sized component bbox
                # says nothing about its connected body strokes.
                retained.append(guard);continue
            patch=pixels[y1:y2,x1:x2]
            if not patch.size or not np.all(patch==mode):retained.append(guard);continue
            proofs.append({'kind':'source_baseline_reproposal','bbox':list(guard),'xref':info['xref'],
                           'source_box':[x1,y1,x2,y2],'source_shape':[w,h],'source_paper_mode':mode,
                           'source_guard_regions':[list(b) for b in source_guards],
                           'clipped_continuous_source_components':[]})
    return retained,proofs
