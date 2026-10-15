"""Resolve blank scanning canvases using verified form regions and source pixels."""
from dataclasses import replace


def repair_administrative_layout(objects,document):
    from .signature_ocr import recovery_regions
    from .layout_context import area,containment
    from .caption_rules import _matches
    from .local_ocr import signature_remainder_view
    contexts={page.number:recovery_regions(previous,page)
              for previous,page in zip(document.pages,document.pages[1:])}
    pages={p.number:p for p in document.pages}
    views={}
    result=[]
    for obj in objects:
        regions=contexts.get(obj.page_number,())
        page=pages.get(obj.page_number)
        carrier=(page is not None and any(area(b)>=page.width*page.height*.35 for b in page.images))
        eligible=(obj.kind=='figure' and regions and carrier
                  and (obj.role=='native_figure' and all(containment(b,obj.bbox)>=.95 for b in regions)
                       or obj.source_id.startswith('ocr:') and ':grid/' in obj.source_id
                       and area(obj.bbox)>=obj.page_width*obj.page_height*.08))
        if not eligible or any(c.kind=='figure_caption' and _matches(obj,c) for c in objects):
            result.append(obj);continue
        if obj.page_number not in views:
            try:
                import pymupdf,numpy as np
                with pymupdf.open(document.path) as pdf:
                    raw=pdf[obj.page_number-1];raw.set_rotation(0)
                    scale=min(2,2000/max(raw.rect.width,raw.rect.height))
                    pix=raw.get_pixmap(matrix=pymupdf.Matrix(scale,scale),colorspace=pymupdf.csGRAY,alpha=False)
                    gray=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width)
                view,guards,_=signature_remainder_view(gray,scale,regions,display_rotation=page.display_rotation)
                paper=int(np.bincount(view.ravel(),minlength=256).argmax())
                views[obj.page_number]=(view,guards,scale,paper)
            except Exception:
                # Missing/failed pixel evidence cannot remove an observed object.
                views[obj.page_number]=None
        cached=views[obj.page_number]
        if cached is None:
            result.append(obj);continue
        view,guards,scale,paper=cached
        import cv2,numpy as np
        x1,y1,x2,y2=obj.bbox
        left=max(0,int(x1*scale));top=max(0,int(y1*scale))
        right=min(view.shape[1],int(x2*scale)+1);bottom=min(view.shape[0],int(y2*scale)+1)
        region=view[top:bottom,left:right]
        if not region.size:
            result.append(obj);continue
        _,_,components,_=cv2.connectedComponentsWithStats((region<int(paper)-8).astype('uint8'),8)
        ink=any(w>=2*scale and h>=2*scale and size>=8*scale*scale
                for x,y,w,h,size in components[1:])
        unresolved=any(containment(b,obj.bbox)>.1 for b in guards)
        if ink or unresolved:
            result.append(obj)
        else:
            result.append(replace(obj,kind='text',role='administrative_scan_carrier'))
    return result
