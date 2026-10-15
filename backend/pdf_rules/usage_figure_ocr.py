"""Supplement unresolved physical figure regions at 3x, with bound fact caches.

The caller decides which groups remain unresolved after native and first-scale
evidence. This adapter neither decides usage nor modifies the index or PDF.
"""
from hashlib import sha256
import os
import re
from pathlib import Path
from .usage_graphic_ocr import (_box,_json,_ocr_signature,_cached,_save,
                                _observe_at_scale,_valid_facts)


def figure_ocr_supplement(index,regions):
    return _supplement(index,regions,tiled=False)


def figure_ocr_tiles(index,regions):
    """Observe caller-selected still-unresolved domains in overlapping 3x tiles.

    Call only after ordinary 3x facts did not establish usage. Fields retain
    the original whole-region identity and coordinates; tiling changes only
    the CPU OCR observation and its separately bound cache strategy.
    """
    return _supplement(index,regions,tiled=True)


def figure_ocr_label_rows(index,regions,graphic_evidence):
    """Observe unresolved aligned comparison labels at 3x before large tiles.

    The clip is selected by already observed input/our-method ink, within the
    original graphic. Its facts retain the whole physical region identity.
    """
    result={group:[] for group in regions}
    if not regions:return result
    try:
        import pymupdf
        raw=Path(index.document.path).read_bytes();pdf_sha=sha256(raw).hexdigest()
        base=dict(base_signature=_ocr_signature(),supplement_sha=sha256(Path(__file__).read_bytes()).hexdigest(),
                  strategy='unresolved-physical-aligned-or-ordered-label-row-3x-12pt-interior1pt-v2')
        directory=os.environ.get('MINERU_USAGE_OCR_CACHE_DIR')
        native={(line.page_number,tuple(line.bbox),line.text,line.source)
                for page in index.document.pages for line in page.lines}
        with pymupdf.open(stream=raw,filetype='pdf') as pdf:
            for group,areas in regions.items():
                for area in areas:
                    number=area.get('page_number');box=_box(area.get('bbox'))
                    if not isinstance(number,int) or isinstance(number,bool) or not 1<=number<=len(pdf) or box is None:continue
                    physical=dict(pdf_sha=pdf_sha,page_number=number,bbox=list(box))
                    identity=sha256(_json(physical)).hexdigest();observed=[]
                    for field in graphic_evidence.get(group,[]):
                        fb=_box(field.get('bbox'))
                        if fb is None or field.get('page_number')!=number:continue
                        native_anchor=(number,tuple(fb),field.get('text'),field.get('source')) in native
                        cpu_anchor=(field.get('source')=='usage_graphic_ocr_cpu'
                                    and field.get('confidence',0)>=.90 and field.get('detection_confidence',0)>=.80
                                    and field.get('pdf_sha')==pdf_sha and field.get('region_identity')==identity)
                        if not native_anchor and not cpu_anchor:continue
                        if not (box[0]<=fb[0]<fb[2]<=box[2] and box[1]<=fb[1]<fb[3]<=box[3]):continue
                        observed.append((field,fb))
                    inputs=[(f,b) for f,b in observed if re.fullmatch(r'输入(?:图像)?|input(?:\s+image)?|目标表情',f.get('text',''),re.I)]
                    ours=[(f,b) for f,b in observed if re.fullmatch(r'本章方法|本文方法|本方法|our(?:s| method)?',f.get('text',''),re.I)]
                    clips=[]
                    for af,a in inputs:
                        for bf,b in ours:
                            if abs((a[1]+a[3]-b[1]-b[3])/2)>18:continue
                            clip=[box[0],max(box[1],min(a[1],b[1])-12),box[2],min(box[3],max(a[3],b[3])+12)]
                            if not any(abs(clip[1]-old[1])<=3 and abs(clip[3]-old[3])<=3 for old in clips):clips.append(clip)
                    steps=[]
                    for field,fb in observed:
                        match=re.match(r'^\s*([1-9])\)\s+\S.{7,}',field.get('text',''))
                        if match:steps.append((int(match.group(1)),fb))
                    steps=sorted({(n,tuple(fb)) for n,fb in steps},key=lambda v:v[1][1])
                    if len({n for n,fb in steps})>=2:
                        ordered=all(a[0]<b[0] for a,b in zip(steps,steps[1:]) if abs(a[1][1]-b[1][1])>3)
                        if ordered and steps[0][0]>1:
                            # Observe the real upper part preceding an already
                            # read numbered step. No missing label is inferred.
                            first=steps[0][1]
                            clip=[box[0],box[1],box[2],min(box[3],first[3]+12)]
                            if clip[3]-clip[1]<=100:clips.append(clip)
                    if not clips:continue
                    signature=sha256(_json(dict(base,label_clips=clips))).hexdigest()
                    context=dict(physical,region_identity=identity,ocr_signature=signature,label_clips=clips)
                    cache=Path(directory)/('usage-figure-label-row3-'+sha256(_json(context)).hexdigest()+'.json') if directory else None
                    facts=_cached(cache,context) if cache else None
                    if facts is None:
                        page=pdf[number-1];page.set_rotation(0);facts=[]
                        for clip in clips:
                            clip_context=dict(context,bbox=clip)
                            hits=_observe_at_scale(page,clip_context,3.0)
                            if _valid_facts(hits,clip_context):facts.extend(f for f in hits if
                                clip[0]+1<=f['bbox'][0] and clip[1]+1<=f['bbox'][1]
                                and f['bbox'][2]<=clip[2]-1 and f['bbox'][3]<=clip[3]-1)
                        if not _valid_facts(facts,context):continue
                        if cache:_save(cache,context,facts)
                    result[group].extend({**f,'bbox':list(f['bbox'])} for f in facts)
    except Exception:
        return result
    return result


def _tiles(box):
    width=box[2]-box[0];height=box[3]-box[1]
    for x in (0,.275,.55):
        for y in (0,.4):
            yield [box[0]+x*width,box[1]+y*height,
                   min(box[2],box[0]+(x+.45)*width),min(box[3],box[1]+(y+.6)*height)]


def _supplement(index,regions,*,tiled):
    result={group:[] for group in regions}
    if not regions:return result
    try:
        import pymupdf
        raw=Path(index.document.path).read_bytes();pdf_sha=sha256(raw).hexdigest()
        signature=sha256(_json(dict(base_signature=_ocr_signature(),
            supplement_sha=sha256(Path(__file__).read_bytes()).hexdigest(),
            strategy='unresolved-physical-figure-overlap-3x-three-columns-two-rows-interior1pt-v2' if tiled
                     else 'unresolved-physical-figure-second-scale-3.0'))).hexdigest()
        directory=os.environ.get('MINERU_USAGE_OCR_CACHE_DIR')
        with pymupdf.open(stream=raw,filetype='pdf') as pdf:
            for group,areas in regions.items():
                for area in areas:
                    try:
                        number=area.get('page_number');box=_box(area.get('bbox'))
                        if (not isinstance(number,int) or isinstance(number,bool)
                                or not 1<=number<=len(pdf) or box is None):continue
                        page=pdf[number-1];page.set_rotation(0)
                        if (pymupdf.Rect(box)&page.rect).is_empty:continue
                        physical=dict(pdf_sha=pdf_sha,page_number=number,bbox=list(box))
                        context=dict(physical,region_identity=sha256(_json(physical)).hexdigest(),ocr_signature=signature)
                        prefix='usage-figure-tiles3-' if tiled else 'usage-figure-scale3-'
                        cache=Path(directory)/(prefix+sha256(_json(context)).hexdigest()+'.json') if directory else None
                        facts=_cached(cache,context) if cache else None
                        if facts is None:
                            if tiled:
                                facts=[]
                                for tile in _tiles(box):
                                    tile_context=dict(context,bbox=tile)
                                    observed=_observe_at_scale(page,tile_context,3.0)
                                    if _valid_facts(observed,tile_context):
                                        # A word cut by a tile edge can be a
                                        # confident partial identifier. Another
                                        # overlapping tile supplies its intact
                                        # version; the clipped fragment is not a fact.
                                        facts.extend(f for f in observed if
                                            tile[0]+1<=f['bbox'][0] and tile[1]+1<=f['bbox'][1]
                                            and f['bbox'][2]<=tile[2]-1 and f['bbox'][3]<=tile[3]-1)
                                unique={ (f['text'],tuple(round(v,2) for v in f['bbox'])):f for f in facts }
                                facts=list(unique.values())
                            else:
                                facts=_observe_at_scale(page,context,3.0)
                            if not _valid_facts(facts,context):continue
                            if cache:_save(cache,context,facts)
                        result[group].extend({**fact,'bbox':list(fact['bbox'])} for fact in facts)
                    except Exception:
                        continue
    except Exception:
        return result
    return result
