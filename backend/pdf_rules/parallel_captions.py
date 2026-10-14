"""Recover independently placed captions that share one native PDF line."""
from dataclasses import replace
import re

from .numbering import FIGURE_REFERENCE, TABLE_REFERENCE, caption_match, normalize_label, normalize_text


def _parts(line, page):
    if (line.source != 'native' or not line.text_regions
            or abs(line.direction[1]) > .1 or not re.search(r'\s{2,}', line.text)):
        return ()
    text = normalize_text(line.text)
    for kind, pattern, owners in (
            ('figure', FIGURE_REFERENCE, page.images),
            ('table', TABLE_REFERENCE, page.tables)):
        matches = list(pattern.finditer(text))
        if len(matches) < 2 or text[:matches[0].start()].strip():
            continue
        starts = [0]
        for match in matches[1:]:
            spaces = re.search(r'\s{2,}$', text[:match.start()])
            if not spaces:
                break
            starts.append(match.start())
        if len(starts) != len(matches):
            continue
        parts = []
        for ordinal, start in enumerate(starts):
            stop = starts[ordinal + 1] if ordinal + 1 < len(starts) else len(text)
            while stop > start and text[stop-1].isspace():
                stop -= 1
            fragment = text[start:stop]
            match = caption_match(fragment, kind)
            tail = fragment[match.end('number'):].strip(' .:：、') if match else ''
            if (not match or len(tail) < 2 or ordinal+1 < len(starts) and
                re.search(r'(?:[与和及]|以及|\band|\bversus|\bvs\.?|\bwith)\s*$', tail, re.I)):
                break
            regions = [(a-start,b-start,box) for a,b,box in line.text_regions
                       if a >= start and b <= stop]
            cursor = 0
            for a,b,_ in regions:
                if a != cursor or b <= a:
                    break
                cursor = b
            if cursor != stop-start:
                break
            boxes = [box for _,_,box in regions]
            box = (min(b[0] for b in boxes),min(b[1] for b in boxes),
                   max(b[2] for b in boxes),max(b[3] for b in boxes))
            parts.append((start,stop,match,replace(line,text=fragment,bbox=box,
                text_regions=tuple(regions),reference_regions=())))
        if len(parts) != len(matches):
            continue
        if len({normalize_label(part[2].group('number')) for part in parts}) != len(parts):
            continue
        height = max(1,line.bbox[3]-line.bbox[1])
        if any(right[3].bbox[0]-left[3].bbox[2] < max(12,height)
               for left,right in zip(parts,parts[1:])):
            continue
        owned = []
        for _,_,_,fragment in parts:
            a = fragment.bbox
            candidates = []
            for b in owners:
                if b[2]-b[0] < page.width*.08 or b[3]-b[1] < page.height*.025:
                    continue
                if b[3] < page.height*.13 or b[1] > page.height*.9:
                    continue
                # Labels inside two panels can name those panels while a
                # different shared main caption owns both. Main captions
                # need proof outside the image/table's physical boundary.
                if a[3] > b[1]+.5 and a[1] < b[3]-.5:
                    continue
                overlap = max(0,min(a[2],b[2])-max(a[0],b[0]))
                gap = max(a[1]-b[3],b[1]-a[3],0)
                if overlap >= min(a[2]-a[0],b[2]-b[0])*.6 and gap <= max(36,height*4):
                    candidates.append(b)
            # A comparison in one composite image cannot prove two titles.
            if len(candidates) != 1:
                break
            owned.append(candidates[0])
        if len(owned) != len(parts) or len(set(owned)) != len(parts):
            continue
        if any(right[0]-left[2] < height for left,right in zip(owned,owned[1:])):
            continue
        return tuple((kind,start,stop,match,fragment) for start,stop,match,fragment in parts)
    return ()

def parallel_caption_ranges(line, page):
    """Only the independently proved titles' own numbers are not citations."""
    return tuple((kind,start+match.start('number'),start+match.end('number'))
                 for kind,start,_,match,_ in _parts(line,page))


def recover_parallel_native_captions(document):
    pages = []
    changed = False
    for page in document.pages:
        lines = []
        known = {(line.text,line.bbox) for line in page.lines}
        for line in page.lines:
            lines.append(line)
            parts = _parts(line,page)
            for _,_,_,_,fragment in parts[1:]:
                if (fragment.text,fragment.bbox) not in known:
                    lines.append(fragment)
                    known.add((fragment.text,fragment.bbox))
                    changed = True
        pages.append(replace(page,lines=tuple(lines)) if len(lines)!=len(page.lines) else page)
    return replace(document,pages=tuple(pages)) if changed else document
