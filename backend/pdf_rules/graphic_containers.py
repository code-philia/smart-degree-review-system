"""Recover split pieces owned by one physical vector frame in the source PDF."""
from dataclasses import replace
from .layout_context import area, containment, union
from .logical_objects import panel_label_conflict


def _original_rectangular_clips(targets, document):
    """Original display-list clip rectangles, including placed vector Forms.

    A drawing path's bounding box only covers one axis/bar. A rectangular
    clipping command retains the actual placed container and its transform.
    Nonrectangular clips and page canvases cannot establish this ownership.
    """
    from collections import Counter
    from pathlib import Path
    import pymupdf
    if not Path(document.path).is_file():
        return {}
    counts=Counter(obj.page_number for obj in targets if obj.kind in {"figure","table"})
    result={}
    with pymupdf.open(document.path) as source:
        for number,count in counts.items():
            if count<2 or not 1<=number<=len(source):
                continue
            page=source[number-1];page.set_rotation(0)
            frames=set()
            for drawing in page.get_cdrawings(extended=True):
                items=drawing.get("items",())
                if drawing.get("type")!="clip" or len(items)!=1 or items[0][0]!="re":
                    continue
                frame=pymupdf.Rect(items[0][1]) & pymupdf.Rect(drawing["scissor"]) & page.rect
                if frame.width>3 and frame.height>3 and frame.get_area()<=page.rect.get_area()*.65:
                    frames.add(tuple(frame))
            result[number]=frames
    return result


def merge_physical_graphic_containers(targets, captions, document):
    """Require a real bounded drawing, one outer title and no internal titles.

    Geometric proximity alone is insufficient. Original PDF drawing rectangles
    supply the shared object boundary; parser regions supply constituent pieces.
    """
    result=list(targets)
    native_clips=_original_rectangular_clips(targets,document)
    for page in document.pages:
        clip_frames=native_clips.get(page.number,set())
        for frame in sorted(set(page.graphics)|clip_frames, key=area):
            if not 0 < area(frame) <= page.width*page.height*.65:
                continue
            parts=[obj for obj in result if (obj.kind=='figure' or frame in clip_frames and obj.kind=='table')
                   and obj.page_number==page.number and containment(obj.bbox,frame)>=.97]
            if len(parts)<2 or not any(obj.kind=='figure' for obj in parts):
                continue
            # Raster charts omit the frame's shared legend and per-panel
            # names. Those native text/mark rectangles are payload too;
            # do not treat their reserved rows as empty physical margins.
            payload=[obj.bbox for obj in parts]
            payload.extend(line.bbox for line in page.lines
                           if line.text.strip() and containment(line.bbox,frame)>=.97)
            payload.extend(box for box in page.legend_marks
                           if containment(box,frame)>=.97)
            extent=union(payload)
            if area(extent) < area(frame)*.65:
                continue
            page_titles=[c for c in captions if c.kind.endswith('_caption') and c.page_number==page.number]
            titles=[c for c in page_titles if c.kind=='figure_caption']
            if any(containment(c.bbox,frame)>=.5 for c in page_titles):
                continue
            from .caption_rules import _matches
            if any(obj.kind=='table' and c.kind=='table_caption' and _matches(obj,c)
                   for obj in parts for c in page_titles):
                continue
            outer=[c for c in titles
                   if -2 <= c.bbox[1]-frame[3] <= 30
                   and abs((c.bbox[0]+c.bbox[2]-frame[0]-frame[2])/2) <= (frame[2]-frame[0])*.15]
            if not outer or panel_label_conflict(parts,document,titles):
                continue
            boxes=tuple(box for obj in parts for box in (obj.panel_boxes or (obj.bbox,)))
            merged=replace(next(obj for obj in parts if obj.kind=='figure'),bbox=frame,role='native_graphic_container',panel_boxes=boxes)
            result=[obj for obj in result if obj not in parts]+[merged]
    return result


def remove_internal_bitmap_fragments(targets,captions,document):
    """An expanded physical bitmap owns its uncaptioned small interior pieces."""
    from .caption_rules import _matches
    pages={page.number:page for page in document.pages}
    result=[]
    for child in targets:
        if child.kind!='figure':
            result.append(child);continue
        embedded=False
        for parent in targets:
            if parent==child or parent.kind!='figure' or parent.page_number!=child.page_number:continue
            if area(child.bbox)>area(parent.bbox)*.2 or containment(child.bbox,parent.bbox)<.93:continue
            carriers=[box for box in pages[child.page_number].images
                      if containment(child.bbox,box)>=.93 and containment(parent.bbox,box)>=.93
                      and containment(box,parent.bbox)>=.85]
            if not carriers:continue
            internal_title=any(c.kind=='figure_caption' and c.page_number==child.page_number
                and _matches(child,c) and any(containment(c.bbox,box)>=.8 for box in carriers) for c in captions)
            if internal_title:continue
            embedded=True;break
        if not embedded:result.append(child)
    return result


def recover_declared_vector_panels(objects,document):
    """Recover a vector text panel expressly named by a shared left/right title."""
    import re
    from .mineru_layout import LayoutObject
    from .caption_rules import _matches
    result=list(objects)
    for page in document.pages:
        titles=[c for c in result if c.kind=='figure_caption' and c.page_number==page.number
                and re.search(r'左图.*右图|右图.*左图|\bleft\b.*\bright\b|\bright\b.*\bleft\b',c.text,re.I|re.S)]
        if not titles:continue
        page_titles=[c for c in result if c.kind.endswith('_caption') and c.page_number==page.number]
        for frame in sorted(set(page.graphics),key=area):
            if not 1000<area(frame)<page.width*page.height*.5:continue
            # A drawing envelope that swallows an established academic title
            # is not another independently captioned graphic. In particular,
            # matching only its lower translation must not create a parent
            # that later fails to match the unified bilingual title.
            if any(containment(c.bbox,frame)>=.5 for c in page_titles):continue
            probe=LayoutObject('figure',page.number,frame,'',page.width,page.height,'native_vector_panel')
            if not any(_matches(probe,c) for c in titles):continue
            if any(o.kind=='figure' and o.page_number==page.number and containment(frame,o.bbox)>=.93 for o in result):continue
            fragments=[o for o in result if o.kind=='figure' and o.page_number==page.number
                       and containment(o.bbox,frame)>=.93 and area(o.bbox)<area(frame)*.1]
            text=[l for l in page.lines if containment(l.bbox,frame)>=.9 and len(l.text.strip())>=8]
            if len(fragments)>=2 and len(text)>=4:
                result.append(probe)
    return result
