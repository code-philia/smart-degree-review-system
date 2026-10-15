"""Resolve explicit unnumbered deictics only when there is one nearby object."""
import re
from dataclasses import replace
from .model import Label
from .numbering import normalize_text

DEICTIC=re.compile(r'(?:如(?P<direction>[上下]?)(?P<kind>[图表])(?:\s*所示|(?=\s*[:：。.!！？?；;]|\s*$))|(?:参见|见)(?P<direction2>[上下])(?P<kind2>[图表])|(?:记录于|列于|示于)(?P<direction3>[上下])(?P<kind3>[图表])(?!面|层|征)|(?P<direction4>[上下])(?P<kind4>[图表])(?:中|里)?\s*(?:列出|给出|展示|呈现|显示|记录|汇总))')

def add_implicit_references(index,eligible_lines,visual_objects=(), *, paragraphs_restored=False):
    from .usage_paragraphs import usage_paragraphs,span_anchor
    if not paragraphs_restored:
        eligible_lines=usage_paragraphs(eligible_lines,index.document)
    offsets={};cursor=0
    for page in index.document.pages:offsets[page.number]=cursor;cursor+=page.height
    boundaries=section_boundaries(index.document,visual_objects,offsets)
    for line,scope in eligible_lines:
        normalized=normalize_text(line.text)
        for match in DEICTIC.finditer(normalized):
            # Unresolved typesetting numbers (e.g. LaTeX ??) are not a valid
            # unnumbered deictic. Proximity cannot invent their missing target.
            if re.match(r"\s*[?？](?:\s*[?？])+",normalized[match.end():]):
                continue
            kind=match.group('kind') or match.group('kind2') or match.group('kind3') or match.group('kind4')
            direction=match.group('direction') or match.group('direction2') or match.group('direction3') or match.group('direction4')
            targets=index.figures if kind=='图' else index.tables
            candidates={}
            evidence=span_anchor(line,match.start(),match.end())
            position=offsets[line.page_number]+(evidence.bbox[1]+evidence.bbox[3])/2
            for target in targets:
                if target.scope!=scope or abs(target.line.page_number-line.page_number)>1:continue
                t=target.line
                where=offsets[t.page_number]+(t.bbox[1]+t.bbox[3])/2
                distance=where-position
                if any(min(position,where)<boundary<max(position,where) for boundary in boundaries):continue
                if direction=='下' and distance<=0 or direction=='上' and distance>=0:continue
                if abs(distance)>line.page_height*.45:
                    from .caption_rules import _matches
                    from .mineru_layout import LayoutObject
                    caption=LayoutObject(('figure' if kind=='图' else 'table')+'_caption',t.page_number,t.bbox,t.text,t.page_width,t.page_height)
                    regions=[o for o in visual_objects if o.kind==('figure' if kind=='图' else 'table') and o.page_number==t.page_number and _matches(o,caption)]
                    close=[offsets[o.page_number]+min(max(position-offsets[o.page_number],o.bbox[1]),o.bbox[3]) for o in regions]
                    if not close or min(abs(v-position) for v in close)>line.page_height*.9:continue
                candidates[(target.scope,target.number)]=target
            if len(candidates)!=1:continue
            target=next(iter(candidates.values()))
            boxes=[box for start,end,box in line.text_regions if start<match.end() and end>match.start()]
            anchor=replace(line,bbox=(min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes))) if boxes else line
            ref=Label(target.number,anchor,scope)
            (index.figure_refs if kind=='图' else index.table_refs).append(ref)

    from .untyped_references import add_untyped_references
    add_untyped_references(index,eligible_lines,visual_objects)
    from .descriptive_references import add_descriptive_references
    add_descriptive_references(index,eligible_lines,offsets,boundaries)


def section_boundaries(document,visual_objects,offsets):
    """Running chapter headers, page numbers and graphic labels are not sections."""
    from collections import defaultdict
    repeats=defaultdict(set)
    for page in document.pages:
        for line in page.lines:
            if line.bbox[1]<page.height*.12:
                repeats[(normalize_text(line.text).strip(),round(line.bbox[1]/16))].add(page.number)
    boundaries=[]
    for line in document.lines:
        text=normalize_text(line.text).strip()
        if not line.page_height*.08<=line.bbox[1]<=line.page_height*.92:continue
        if line.bbox[1]<line.page_height*.12 and len(repeats[(text,round(line.bbox[1]/16))])>=2:continue
        if re.fullmatch(r'\d+',text):continue
        if re.fullmatch(r'\d+(?:[.]\d+)+',text) and not (line.bold or line.font_size and line.font_size>=12):continue
        if any(o.kind in {'figure','table'} and o.page_number==line.page_number and o.bbox[0]<=line.bbox[0] and o.bbox[1]<=line.bbox[1] and o.bbox[2]>=line.bbox[2] and o.bbox[3]>=line.bbox[3] for o in visual_objects):continue
        if re.match(r'^\d+\s+',text) and not line.bold and re.search(r'[，,；;。]',text):continue
        if re.match(r'^(?:第\s*[一二三四五六七八九十0-9]+\s*章|chapter\s+[IVX0-9]+|\d+(?:[.]\d+)*(?:\s+|$))',text,re.I):
            boundaries.append(offsets[line.page_number]+line.bbox[1])
    return boundaries
