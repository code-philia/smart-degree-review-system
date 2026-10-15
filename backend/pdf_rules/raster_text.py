"""Confirm bitmap chapter glyphs using original pixels and native text baselines."""
from functools import lru_cache
from pathlib import Path
import re
from .numbering import normalize_text,is_toc_line
from .caption_context import body_font


def overlap(a,b):
    area=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    return area/max(1,(a[2]-a[0])*(a[3]-a[1]))


@lru_cache(maxsize=512)
def _chapter_pixels(path,mtime,size,number,box):
    import pymupdf
    import numpy as np
    from .local_ocr import _read_tile
    with pymupdf.open(path) as source:
        page=source[number-1];page.set_rotation(0)
        clip=pymupdf.Rect(box)+(-2,-2,2,2)
        pix=page.get_pixmap(matrix=pymupdf.Matrix(6,6),clip=clip,colorspace=pymupdf.csGRAY,alpha=False)
        gray=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width)
    hits=_read_tile(gray)
    text=''.join(normalize_text(h.text).replace(' ','') for h in sorted(hits,key=lambda h:h.bbox[0]) if h.score>=.8)
    return bool(re.fullmatch(r'第[一二三四五六七八九十百零〇0-9]+章',text))


def raster_heading_regions(document,objects=()):
    path=Path(document.path)
    if not path.is_file():return {}
    stat=path.stat();regions={}
    for page in document.pages:
        boxes=[];typical=body_font(page)
        for line in page.lines:
            if line.source!='native' or not re.search(r'[A-Za-z\u4e00-\u9fff]',line.text):continue
            if not (line.bold or line.font_size and typical and line.font_size>=typical*1.1 or is_toc_line(line.text)):continue
            height=line.bbox[3]-line.bbox[1]
            cluster=[b for b in page.images if b[2]<=line.bbox[0]+2 and 0<=line.bbox[0]-b[2]<=height*5
                     and b[3]-b[1]<=height*1.4 and b[2]-b[0]<=height*5
                     and min(b[3],line.bbox[3])-max(b[1],line.bbox[1])>=min(b[3]-b[1],height)*.65]
            if not cluster:continue
            box=(min(b[0] for b in cluster),min(b[1] for b in cluster),max(b[2] for b in cluster),max(b[3] for b in cluster))
            if box[2]-box[0]>height*5 or line.bbox[0]-box[2]>height*1.5:continue
            try:
                confirmed=_chapter_pixels(str(path.resolve()),stat.st_mtime_ns,stat.st_size,page.number,box)
            except Exception:
                confirmed=False  # Failed recognition cannot hide a candidate figure.
            if not confirmed:
                native=re.sub(r'\s+','',normalize_text(line.text))
                for obj in objects:
                    if obj.page_number!=page.number or obj.kind!='text' or obj.role not in {'title','text'}:continue
                    readings=obj.text_lines or ((obj.text,obj.bbox),)
                    for text,rect in readings:
                        compact=re.sub(r'\s+','',normalize_text(text))
                        chapter=re.match(r'^(?:第)?[一二三四五六七八九十百零〇0-9]+章',compact)
                        if not chapter or not native[:4] or len(native)<4:continue
                        same_row=min(rect[3],line.bbox[3])-max(rect[1],line.bbox[1])>=height*.5
                        if (same_row and overlap(box,rect)>=.85
                                and compact[chapter.end():].startswith(native[:min(12,len(native))])):
                            confirmed=True;break
                    if confirmed:break
            if confirmed and box not in boxes:boxes.append(box)
        if boxes:regions[page.number]=boxes
    return regions
