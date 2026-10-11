"""Read literal figure/table prefixes stored as tiny inline bitmap text.

Only original embedded pixels are read. Numbers are never inferred from prose,
chapter order or neighbouring captions. Uncertain/nontext rasters stay images.
"""
from dataclasses import replace
from functools import lru_cache
from collections import defaultdict
import re

from .numbering import normalize_text

_PREFIX = re.compile(r'^(?:图|表|Fig(?:ure)?\.?|Table)\s*(?:[A-Z]\.?\s*)?\d+(?:\s*[.\-]\s*\d+)*$', re.I)
_SECTION_PREFIX = re.compile(r'^\d+(?:\.\d+)+$')


def prefix_candidates(document):
    result = []
    for page in document.pages:
        for box in page.images:
            width,height = box[2]-box[0],box[3]-box[1]
            if not (6 <= width <= page.width*.18 and 4 <= height <= page.height*.035
                    and 1.4 <= width/height <= 12):
                continue
            rows = []
            for line in page.lines:
                h=line.bbox[3]-line.bbox[1]
                if (line.source != 'native' or line.direction != (1.0,0.0)
                        or line.role in {'header','footer','equation'} or h <= 0
                        or len(re.findall(r'[A-Za-z\u4e00-\u9fff]',line.text)) < 3
                        or line.bbox[2]-line.bbox[0] < h*2):
                    continue
                overlap=min(box[3],line.bbox[3])-max(box[1],line.bbox[1])
                if (-1 <= line.bbox[0]-box[2] <= h*.9 and overlap >= min(h,height)*.6
                        and abs((box[1]+box[3]-line.bbox[1]-line.bbox[3])/2) <= h*.45):
                    rows.append(line)
            if len(rows)==1:
                result.append((page.number,box,rows[0]))
    return result


@lru_cache(maxsize=32)
def _recognize_pixels(payloads):
    """Reuse the bundled recognizer and cache batches by exact pixel payload."""
    import cv2
    import numpy as np
    from rapidocr.ch_ppocr_rec import TextRecInput
    from .local_ocr import _engine
    images=[cv2.imdecode(np.frombuffer(payload,np.uint8),cv2.IMREAD_COLOR) for payload in payloads]
    output=_engine().text_rec(TextRecInput(img=images))
    return tuple((str(text),float(score)) for text,score in zip(output.txts,output.scores))


def recover_raster_caption_prefixes(document):
    candidates=prefix_candidates(document)
    if not candidates or not document.path.is_file():
        return document
    import pymupdf
    import logging
    payloads={};bound=[]
    with pymupdf.open(document.path) as pdf:
        info_by_page={}
        for number,box,line in candidates:
            if number not in info_by_page:
                page=pdf[number-1];page.set_rotation(0)
                info_by_page[number]=page.get_image_info(xrefs=True)
            infos=[item for item in info_by_page[number]
                   if item.get('xref') and max(abs(a-b) for a,b in zip(item['bbox'],box)) <= .1
                   and abs(item['transform'][1]) < .01 and abs(item['transform'][2]) < .01]
            if len(infos)!=1:
                continue
            payload=pdf.extract_image(infos[0]['xref'])['image']
            payloads.setdefault(payload,len(payloads));bound.append((number,box,line,payload))
    readings={}
    unique=list(payloads)
    try:
        for start in range(0,len(unique),64):
            batch=tuple(unique[start:start+64])
            readings.update(zip(batch,_recognize_pixels(batch)))
    except (ImportError,OSError,RuntimeError,ValueError) as exc:
        logging.getLogger(__name__).warning('Caption prefix OCR unavailable: %s',type(exc).__name__)
        return document
    # A bare numeric bitmap can be a plot, tick, or formula. Only independently
    # observed identical section-number/title pairs in a dotted TOC row and a
    # non-TOC heading establish its text-prefix identity; neither is inferred.
    sections=defaultdict(list)
    for number,box,line,payload in bound:
        text,score=readings[payload]
        prefix=re.sub(r'\s+','',normalize_text(text))
        if score < .97 or not _SECTION_PREFIX.fullmatch(prefix):continue
        body=normalize_text(line.text).strip()
        toc=re.fullmatch(r'(.+?)\s*[.·…]{3,}\s*\d+',body)
        title=toc.group(1) if toc else body
        sections[(prefix,re.sub(r'\s+','',title))].append((number,line.bbox,bool(toc)))
    numbered=set()
    for entries in sections.values():
        toc_pages={number for number,box,toc in entries if toc}
        heading_pages={number for number,box,toc in entries if not toc}
        if toc_pages and heading_pages and toc_pages.isdisjoint(heading_pages):
            numbered.update((number,box) for number,box,toc in entries)
    changes={};consumed={}
    for number,box,line,payload in bound:
        text,score=readings[payload]
        prefix=normalize_text(text).strip()
        section=(number,line.bbox) in numbered
        if score < .97 or not (_PREFIX.fullmatch(prefix) or section):
            continue
        prefix=re.sub(r'\s+','',prefix)
        offset=len(prefix)+1
        body=normalize_text(line.text)
        # The OCR prefix has one observed word box, never invented per-glyph
        # native coordinates. The existing title glyphs retain exact offsets.
        updated=replace(line,text=prefix+' '+body,source='local_numbered_prefix_ocr' if section else 'local_caption_prefix_ocr',
                        bbox=(box[0],min(box[1],line.bbox[1]),line.bbox[2],max(box[3],line.bbox[3])),
                        text_regions=((0,len(prefix),box),)+tuple((a+offset,b+offset,bbox)
                            for a,b,bbox in line.text_regions),reference_regions=())
        key=(number,line.bbox)
        if key in changes:
            continue
        changes[key]=updated;consumed.setdefault(number,set()).add(box)
    if not changes:
        return document
    return replace(document,pages=tuple(replace(page,
        lines=tuple(changes.get((page.number,line.bbox),line) for line in page.lines),
        images=tuple(box for box in page.images if box not in consumed.get(page.number,())))
        for page in document.pages))
