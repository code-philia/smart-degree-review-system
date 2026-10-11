"""Recognize repeated PDF export canvases from resource identity and soft masks."""
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from collections import defaultdict


@lru_cache(maxsize=128)
def _canvases(path,mtime,size):
    import pymupdf
    from .object_identity import coverage
    groups=defaultdict(list)
    with pymupdf.open(path) as pdf:
        for number,page in enumerate(pdf,1):
            page.set_rotation(0)
            def canvas_box(info):
                box=tuple(info['bbox'])
                return (coverage(tuple(page.rect),[box])>=.98
                        and box[2]-box[0]<=page.rect.width*1.05
                        and box[3]-box[1]<=page.rect.height*1.05)
            # Geometry needs no decoded pixels or image hashes. Resolve the
            # original resource identities only on pages with a possible canvas.
            if not any(canvas_box(info) for info in page.get_image_info()):continue
            for info in page.get_image_info(xrefs=True):
                xref=info.get('xref');box=tuple(info['bbox'])
                if not xref or not canvas_box(info):continue
                groups[xref].append((number,box))
        result=defaultdict(list)
        for xref,uses in groups.items():
            if len({n for n,b in uses})<3:continue
            resource=pdf.extract_image(xref);mask=resource.get('smask')
            if not mask:continue
            pix=pymupdf.Pixmap(pdf,mask)
            if pix.n!=1 or pix.width*pix.height>20_000_000:continue
            low,high=min(pix.samples),max(pix.samples)
            # A uniform <=2% alpha layer repeated at full-page geometry is an
            # export watermark/canvas, not a separate titled academic visual.
            # Faint opaque scientific plots and one-off images cannot qualify.
            if low!=high or high>5:continue
            for number,box in uses:result[number].append(box)
        return dict(result)


def remove_decorative_layers(objects,document):
    path=Path(document.path)
    if not path.is_file():return list(objects),document
    try:
        stat=path.stat();regions=_canvases(str(path.resolve()),stat.st_mtime_ns,stat.st_size)
    except Exception:return list(objects),document
    if not regions:return list(objects),document
    from .object_identity import coverage
    def same(a,b):return coverage(a,[b])>=.98 and coverage(b,[a])>=.98
    from .native_layout import raster_needs_ocr
    pages=[]
    for page in document.pages:
        images=tuple(b for b in page.images if not any(same(b,r) for r in regions.get(page.number,())))
        if images!=page.images:
            page=replace(page,images=images,unreadable=raster_needs_ocr(page.lines,images,page.width,page.height))
        pages.append(page)
    pages=tuple(pages)
    objects=[o for o in objects if o.kind!='figure' or not any(same(o.bbox,r) for r in regions.get(o.page_number,()))]
    return objects,replace(document,pages=pages)
