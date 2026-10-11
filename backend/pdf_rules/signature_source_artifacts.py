"""Verify render proposals against original embedded source pixels."""
import io
import pymupdf

def source_artifacts(document,page,regions,guards):
    import cv2,numpy as np
    from PIL import Image
    from .page_policy import _inside
    from .local_ocr import signature_remainder_view
    retained=[];proofs=[]
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
            if not any(_inside(box,b,3) for b in regions):native.append(box)
        if native:return guards+[_IndependentInkGuard(b) for b in native],[{'kind':'independent_native_ink','regions':[list(b) for b in native]}]
        images=raw.get_image_info(xrefs=True);carriers=[];barcodes=[]
        for info in images:
            if not info.get('xref'):continue
            box=pymupdf.Rect(info['bbox'])*raw.rotation_matrix
            visible=box&raw.rect
            encoded=pdf.extract_image(info['xref'])
            pixels=np.asarray(Image.open(io.BytesIO(encoded['image'])).convert('L'))
            if info['bpc']==1 and (box.y1<raw.rect.height*.065 or visible.width<raw.rect.width*.025 and visible.x0>raw.rect.width*.96):
                _,_,parts,_=cv2.connectedComponentsWithStats((pixels<128).astype('uint8'),8)
                bars=int(sum(w<max(20,pixels.shape[1]*.04) and h>pixels.shape[0]*.4 for x,y,w,h,area in parts[1:]))
                if bars>=12:barcodes.append((info['xref'],tuple(box),bars))
            if info['width']<1000 or box.get_area()<raw.rect.get_area()*.85:continue
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
        carrier_ids={i['xref'] for i,*_ in carriers};barcode_ids={b[0] for b in barcodes}
        independent=[]
        for info in images:
            box=tuple(pymupdf.Rect(info['bbox'])*raw.rotation_matrix)
            if info['xref'] in barcode_ids:continue
            if info['xref'] in carrier_ids and len(carrier_ids)==1:continue
            if not any(_inside(box,b,3) for b in regions):independent.append(box)
        if independent:
            return guards+[_IndependentInkGuard(b) for b in independent],[{'kind':'independent_image_layers','regions':[list(b) for b in independent]}]
        for guard in guards:
            if type(guard).__name__ in {'_GraphicGuard','_TextGuard'}:retained.append(guard);continue
            barcode=next((b for b in barcodes if _inside(guard,b[1],3)),None)
            if barcode is not None:
                proofs.append({'kind':'source_parallel_margin_barcode','bbox':list(guard),'xref':barcode[0],'bars':barcode[2]});continue
            if len(carrier_ids)!=1:retained.append(guard);continue
            if any(i['xref'] not in carrier_ids|barcode_ids and (pymupdf.Rect(guard)&(pymupdf.Rect(i['bbox'])*raw.rotation_matrix)).get_area()>0 for i in images):
                retained.append(guard);continue
            info,pixels,inverse,source_guards,mode,labels,parts=carriers[0]
            if any((pymupdf.Rect(guard)&pymupdf.Rect(b)).get_area()>0 for b in source_guards):
                retained.append(guard);continue
            h,w=pixels.shape;b=pymupdf.Rect(guard)*raw.derotation_matrix*inverse
            x1=max(0,int(b.x0*w));y1=max(0,int(b.y0*h));x2=min(w,int(b.x1*w)+1);y2=min(h,int(b.y1*h)+1)
            component_proofs=[]
            if type(guard).__name__=='_VisibleInkGuard':
                if info['bpc']==1 and x2>x1 and y2>y1:
                    ink=pixels<128;normal=max(5,round(min(h,w)*.002))
                    # This original binary edge contains a physical line
                    # across almost the complete carrier. Own only actual
                    # source pixels in its narrow normal extent, not a
                    # geometric page-margin column or an attached body stem.
                    edge=None
                    if y1==0 and ink[:normal].mean(axis=1).max()>.9 and not ink[max(normal,y1):y2,x1:x2].any():edge='top'
                    if y2==h and ink[-normal:].mean(axis=1).max()>.9 and not ink[y1:min(h-normal,y2),x1:x2].any():edge='bottom'
                    if x1==0 and ink[:,:normal].mean(axis=0).max()>.9 and not ink[y1:y2,max(normal,x1):x2].any():edge='left'
                    if x2==w and ink[:,-normal:].mean(axis=0).max()>.9 and not ink[y1:y2,x1:min(w-normal,x2)].any():edge='right'
                    if edge:
                        proofs.append({'kind':'source_continuing_binary_boundary','bbox':list(guard),'xref':info['xref'],
                                       'source_box':[x1,y1,x2,y2],'edge':edge,'maximum_normal_depth':normal});continue
                # An absence of text proposals cannot own visible body ink.
                # A clipped sample of the continuous original scan field is
                # distinct from a separate ink island inside the carrier.
                if not (x1==0 or y1==0 or x2==w or y2==h):retained.append(guard);continue
                selected=[int(n) for n in np.unique(labels[y1:y2,x1:x2]) if n]
                if not selected:retained.append(guard);continue
                for n in selected:
                    x,y,bw,bh,area=map(int,parts[n])
                    if not (x==0 and y==0 and x+bw==w and y+bh==h):break
                    component_proofs.append([x,y,bw,bh,area])
                if len(component_proofs)!=len(selected):retained.append(guard);continue
            proofs.append({'kind':'source_baseline_reproposal','bbox':list(guard),'xref':info['xref'],
                           'source_box':[x1,y1,x2,y2],'source_shape':[w,h],'source_paper_mode':mode,
                           'source_guard_regions':[list(b) for b in source_guards],
                           'clipped_continuous_source_components':component_proofs})
    return retained,proofs
