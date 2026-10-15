"""Strict 4x observations for unresolved concrete visual relations.

Small rotated axis strips are requested only from measured physical columns.
Every fact retains its source PDF, complete graphic region and coordinates.
This module supplies image facts, never a usage decision.
"""
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile

from .usage_graphic_ocr import (_box,_json,_ocr_signature,_observe_at_scale,
                                _text,_confidence,_FIELDS)
from .local_ocr import _read_tile

_FORMAT='usage-relation-pixels-v1'
_SCALE=4.0


def _valid_facts(facts,context):
    if not isinstance(facts,list):return False
    a=context['bbox']
    for fact in facts:
        if not isinstance(fact,dict) or set(fact)!=_FIELDS|{'render_rotation'}:return False
        b=_box(fact['bbox'])
        if (b is None or not _text(fact['text'])
                or not _confidence(fact['confidence'],.90)
                or not _confidence(fact['detection_confidence'],.80)
                or fact['pdf_sha']!=context['pdf_sha'] or fact['page_number']!=context['page_number']
                or fact['region_identity']!=context['region_identity']
                or fact['source']!='usage_graphic_ocr_cpu'
                or fact['render_scale']!=_SCALE or fact['render_rotation'] not in (0,-1)
                or not(a[0]-.01<=b[0]<b[2]<=a[2]+.01 and a[1]-.01<=b[1]<b[3]<=a[3]+.01)):
            return False
    return True


def _cached(path,context):
    try:
        if path.stat().st_size>8*1024*1024:return None
        row=json.loads(path.read_text(encoding='utf-8'))
        if (set(row)!={'format','context','facts','facts_sha'} or row['format']!=_FORMAT
                or row['context']!=context or not _valid_facts(row['facts'],context)
                or sha256(_json(row['facts'])).hexdigest()!=row['facts_sha']):return None
        return row['facts']
    except (OSError,ValueError,TypeError,KeyError):return None


def _save(path,context,facts):
    temporary=None
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        row=dict(format=_FORMAT,context=context,facts=facts,facts_sha=sha256(_json(facts)).hexdigest())
        with tempfile.NamedTemporaryFile(mode='wb',dir=path.parent,prefix='relation-pixels-',suffix='.tmp',delete=False) as f:
            temporary=Path(f.name);f.write(_json(row))
        os.replace(temporary,path);temporary=None
    except (OSError,ValueError,TypeError):pass
    finally:
        if temporary is not None:
            try:temporary.unlink()
            except OSError:pass


def _rotated_fields(page,context,box):
    import numpy as np
    import pymupdf
    clip=pymupdf.Rect(box)&page.rect
    if clip.is_empty:return []
    pix=page.get_pixmap(matrix=pymupdf.Matrix(_SCALE,_SCALE),colorspace=pymupdf.csGRAY,alpha=False,clip=clip)
    gray=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width)
    answer=[]
    for hit in _read_tile(np.ascontiguousarray(np.rot90(gray,-1))):
        b=_box(hit.bbox)
        if b is None or not _text(hit.text) or not _confidence(hit.score,.9) or not _confidence(hit.detection_score,.8):continue
        # Inverse clockwise quarter-turn, followed by the exact pixmap origin.
        mapped=[max(clip.x0,(pix.x+b[1])/_SCALE),max(clip.y0,(pix.y+pix.height-b[2])/_SCALE),
                min(clip.x1,(pix.x+b[3])/_SCALE),min(clip.y1,(pix.y+pix.height-b[0])/_SCALE)]
        if _box(mapped) is None:continue
        if not(clip.x0+1<mapped[0]<mapped[2]<clip.x1-1 and clip.y0+1<mapped[1]<mapped[3]<clip.y1-1):continue
        answer.append(dict(text=hit.text.strip(),bbox=mapped,page_number=context['page_number'],
            source='usage_graphic_ocr_cpu',confidence=float(hit.score),detection_confidence=float(hit.detection_score),
            pdf_sha=context['pdf_sha'],region_identity=context['region_identity'],render_scale=_SCALE,render_rotation=-1))
    return answer


def relation_ocr_supplement(index,regions,axis_tiles=None):
    result={group:[] for group in regions}
    if not regions:return result
    try:
        import pymupdf
        raw=Path(index.document.path).read_bytes();pdf_sha=sha256(raw).hexdigest()
        signature=sha256(_json(dict(base_signature=_ocr_signature(),
            adapter_sha=sha256(Path(__file__).read_bytes()).hexdigest(),scale=_SCALE,
            strategy='unresolved-concrete-relations-and-measured-vertical-axis-strips',rotations=[0,-1]))).hexdigest()
        directory=os.environ.get('MINERU_USAGE_OCR_CACHE_DIR')
        with pymupdf.open(stream=raw,filetype='pdf') as pdf:
            for group,areas in regions.items():
                for area in areas:
                    try:
                        number=area.get('page_number');box=_box(area.get('bbox'))
                        if not isinstance(number,int) or isinstance(number,bool) or not 1<=number<=len(pdf) or box is None:continue
                        page=pdf[number-1];page.set_rotation(0)
                        strips=[]
                        for tile in (axis_tiles or {}).get(group,[]):
                            b=_box(tile.get('bbox'))
                            if b and tile.get('page_number')==number and box[0]<=b[0]<b[2]<=box[2] and box[1]<=b[1]<b[3]<=box[3]:strips.append(list(b))
                        physical=dict(pdf_sha=pdf_sha,page_number=number,bbox=list(box))
                        context=dict(physical,region_identity=sha256(_json(physical)).hexdigest(),ocr_signature=signature,axis_tiles=strips)
                        cache=Path(directory)/('usage-relation-scale4-'+sha256(_json(context)).hexdigest()+'.json') if directory else None
                        facts=_cached(cache,context) if cache else None
                        if facts is None:
                            facts=[dict(f,render_rotation=0) for f in _observe_at_scale(page,context,_SCALE)]
                            for strip in strips:facts.extend(_rotated_fields(page,context,strip))
                            if not _valid_facts(facts,context):continue
                            if cache:_save(cache,context,facts)
                        result[group].extend({**fact,'bbox':list(fact['bbox'])} for fact in facts)
                    except Exception:continue
    except Exception:return result
    return result
