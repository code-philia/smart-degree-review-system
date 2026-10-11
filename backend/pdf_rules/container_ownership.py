"""Restore academic containers from explicit titles and original PDF structure.

Parser body types are candidates. A declared panel belongs to its common
academic figure even when the panel itself has a statistical table layout.
"""
from dataclasses import replace
import re
from .layout_context import union, containment, area, _panel_match
from .caption_rules import _matches
from .native_graphics import visible_drawings


def _mixed_panel_identity(objects,document):
    """Restore parser types from a physically labelled common figure.

    A caption's description need not repeat its panel letters. First assemble
    the original labelled namespace, then bind its envelope to the common
    figure title; per-piece caption distance is not object identity.
    """
    from .layout_context import _panel_group
    from .object_identity import coverage
    pages={p.number:p for p in document.pages}
    captions=[o for o in objects if o.kind.endswith('_caption')]
    result=list(objects)
    for number,page in pages.items():
        candidates=[o for o in objects if o.kind in {'figure','table'} and o.page_number==number
                    and not (o.kind=='table' and any(c.kind=='table_caption'
                             and _matches(o,c) for c in captions))]
        if {o.kind for o in candidates}!={'figure','table'}:continue
        # The original raster/graphic placements must support each candidate.
        # Table-shaped prose and internal record markers cannot create panels.
        candidates=[o for o in candidates if coverage(o.bbox,page.images+page.graphics)>=.8]
        from .logical_objects import remove_native_fragments
        normalized=remove_native_fragments([replace(o,kind='figure') for o in candidates])
        if not normalized:continue
        for group in _panel_group(normalized,document,captions):
            if len(group.panel_boxes)<2:continue
            parts=[o for o in candidates if o.bbox in group.panel_boxes]
            if {o.kind for o in parts}!={'figure','table'}:continue
            from .layout_context import _caption_aliases
            from .logical_objects import panel_label_lines
            marks = [line for line in panel_label_lines(page, normalized, captions)
                     if containment(line.bbox, group.bbox) >= .8]
            # A total caption cannot occupy the printed text of a distinct
            # panel label. Expanded label envelopes are not title evidence.
            matched_titles=[c for c in captions if c.kind=='figure_caption' and _matches(group,c)
                            and not any(min(c.bbox[2],line.bbox[2])-max(c.bbox[0],line.bbox[0])>2
                                        and min(c.bbox[3],line.bbox[3])-max(c.bbox[1],line.bbox[1])>max(2,min(c.bbox[3]-c.bbox[1],line.bbox[3]-line.bbox[1])*.3)
                                        for line in marks)]
            titles=_caption_aliases(matched_titles)
            if len(titles)!=1:continue
            title=titles[0]
            width=group.bbox[2]-group.bbox[0]
            if abs((title.bbox[0]+title.bbox[2]-group.bbox[0]-group.bbox[2])/2)>width*.12:continue
            if any(c not in matched_titles and c.page_number==number
                   and group.bbox[1]<c.bbox[1]<group.bbox[3]
                   and min(c.bbox[2],group.bbox[2])>max(c.bbox[0],group.bbox[0])
                   for c in captions):continue
            result=[replace(o,kind='figure',role='captioned_figure_panel')
                    if o in parts and o.kind=='table' else o for o in result]
    return result


def reclassify_mixed_panels(objects,document):
    result=_mixed_panel_identity(objects,document)
    pages={p.number:p for p in document.pages}
    for caption in objects:
        if caption.kind!='figure_caption':continue
        declared={s.lower() for s in re.findall(r'[（(]([a-z])[）)]',caption.text,re.I)}
        if len(declared)<2:continue
        parts=[];tags=set()
        for obj in result:
            if obj.kind not in {'figure','table'} or obj.page_number!=caption.page_number:continue
            if not _matches(replace(obj,kind='figure'),caption):continue
            if obj.kind=='table' and any(c.kind=='table_caption' and _matches(obj,c) for c in objects):continue
            labels=[]
            for line in pages[obj.page_number].lines:
                match=_panel_match(line.text)
                if not match or match.group(1).lower() not in declared:continue
                x=(line.bbox[0]+line.bbox[2])/2
                # Explicit labels immediately below a body establish ownership;
                # an internal row marker in a real table does not.
                if obj.bbox[0]-10<=x<=obj.bbox[2]+10 and -3<=line.bbox[1]-obj.bbox[3]<=35:
                    labels.append(match.group(1).lower())
            if len(set(labels))==1:
                parts.append(obj);tags.update(labels)
        if {o.kind for o in parts}!={'figure','table'} or not declared.issubset(tags):continue
        box=union([o.bbox for o in parts]);width=box[2]-box[0]
        if caption.bbox[2]-caption.bbox[0]<width*.75:continue
        if abs((caption.bbox[0]+caption.bbox[2]-box[0]-box[2])/2)>width*.12:continue
        # A title between the pieces denotes another independent object.
        if any(c is not caption and c.kind.endswith('_caption') and c.page_number==caption.page_number
               and box[1]<c.bbox[1]<box[3]
               and min(c.bbox[2],box[2])>max(c.bbox[0],box[0]) for c in objects):continue
        result=[replace(o,kind='figure',role='captioned_figure_panel')
                if o in parts and o.kind=='table' else o for o in result]
    return result


def _horizontal_rules(raw, minimum_width=None):
    rules=[]
    minimum_width=raw.rect.width*.5 if minimum_width is None else minimum_width
    for drawing in visible_drawings(raw):
        for item in drawing['items']:
            if item[0]=='l':
                a,b=item[1:3]
                if abs(a.y-b.y)<=1 and abs(a.x-b.x)>=minimum_width:
                    rules.append((min(a.x,b.x),(a.y+b.y)/2,max(a.x,b.x)))
            elif item[0]=='re' and item[1].height<=3 and item[1].width>=minimum_width:
                box=item[1];rules.append((box.x0,(box.y0+box.y1)/2,box.x1))
    return sorted(set(rules),key=lambda r:r[1])


def _recover_captioned_text_frames(objects, document):
    """An explicitly titled table owns text inside its original ruled frame.

    Support titles above or below the frame. Parser fragments and single
    screenshot bodies inherit this identity only with native boundaries and
    repeated text rows; axes, intervening titles and outside images do not.
    """
    import pymupdf
    from .numbering import normalize_text
    if not document.path.is_file():
        return list(objects)
    result=list(objects)
    captions=[o for o in objects if o.kind.endswith('_caption')]
    pages={p.number:p for p in document.pages}
    with pymupdf.open(document.path) as original:
        rule_cache={}
        for caption in captions:
            if caption.kind!='table_caption':
                continue
            number=caption.page_number;page=pages[number]
            widths=[o.bbox[2]-o.bbox[0] for o in objects if o.kind in {'figure','table'}
                    and o.page_number==number and (_matches(replace(o,kind='table'),caption)
                    or containment(caption.bbox,o.bbox)>=.85)]
            if not widths:
                continue
            # Authenticate rules against the observed candidate frame width.
            # A narrow real table does not need to occupy half the PDF page.
            minimum_width=max(10,min(widths)*.75)
            cache_key=(number,minimum_width)
            if cache_key not in rule_cache:
                raw=original[number-1];raw.set_rotation(0)
                rule_cache[cache_key]=_horizontal_rules(raw,minimum_width)
            rules=rule_cache[cache_key]
            frames=[]
            for upper_index,upper in enumerate(rules):
                for lower in rules[upper_index+1:]:
                    if lower[1]-upper[1]<20:
                        continue
                    if max(abs(upper[0]-lower[0]),abs(upper[2]-lower[2]))>8:
                        continue
                    above=-3<=upper[1]-caption.bbox[3]<=35
                    below=-3<=caption.bbox[1]-lower[1]<=35
                    if not (above or below):
                        continue
                    box=(upper[0],upper[1],upper[2],lower[1])
                    if not box[0]-10<=(caption.bbox[0]+caption.bbox[2])/2<=box[2]+10:
                        continue
                    # Numbered titles inside a proposed frame are separate
                    # academic objects, even when the same outer rules span them.
                    if any(c is not caption and c.page_number==number
                           and box[1]+2<c.bbox[1]<box[3]-2
                           and min(c.bbox[2],box[2])>max(c.bbox[0],box[0]) for c in captions):
                        continue
                    lines=[l for l in page.lines if containment(l.bbox,box)>=.85]
                    texts=[normalize_text(l.text).strip() for l in lines]
                    long_rows=sum(len(re.findall(r'[A-Za-z\u4e00-\u9fff]',t))>=10 for t in texts)
                    prose_rows=sum(len(re.findall(r'[A-Za-z\u4e00-\u9fff]',t))>=30 for t in texts)
                    # Some parser table bodies swallow their own footer
                    # title and subsequent prose. Two native rules plus that
                    # interior title recover the actual table boundary.
                    cropped=[o for o in result if below and o.kind=='table'
                             and o.page_number==number
                             and containment(box,o.bbox)>=.93
                             and abs(o.bbox[1]-box[1])<=15
                             and max(abs(o.bbox[0]-box[0]),abs(o.bbox[2]-box[2]))<=15
                             and o.bbox[1]<caption.bbox[1]<caption.bbox[3]<o.bbox[3]]
                    if (long_rows<3 or prose_rows<2) and not cropped:
                        continue
                    parts=[o for o in result if o.kind in {'figure','table'}
                           and o.page_number==number and containment(o.bbox,box)>=.93]
                    parts += [o for o in cropped if o not in parts]
                    if not parts:
                        continue
                    parent=replace(parts[0],kind='table',bbox=box,text='',
                                   role='captioned_text_table',
                                   panel_boxes=tuple(b for o in parts for b in (o.panel_boxes or (o.bbox,))))
                    if _matches(parent,caption):
                        frames.append((box,parts,parent))
            if not frames:
                continue
            # Use the complete physical frame, rather than each internal row
            # separator. An intervening title above already delimits the frame.
            _,parts,parent=max(frames,key=lambda f:area(f[0]))
            result=[o for o in result if o not in parts]+[parent]
    return result


def recover_ruled_table_containers(objects,document):
    """A common table title, repeated record fields and real rules define rows.

    The source PDF supplies boundaries. A heading or geometric proximity by
    itself cannot absorb an image, table or an unrelated lower-page figure.
    """
    import pymupdf
    from collections import Counter
    from .numbering import normalize_text
    if not document.path.is_file():return list(objects)
    objects=_recover_captioned_text_frames(objects,document)
    captions=[o for o in objects if o.kind.endswith('_caption')]
    candidates=[c for c in captions if c.kind=='table_caption' and sum(
        o.kind in {'figure','table'} and o.page_number==c.page_number for o in objects)>=2]
    if not candidates:return list(objects)
    pages={p.number:p for p in document.pages};result=list(objects);page_rules={}
    with pymupdf.open(document.path) as original:
        for caption in candidates:
            number=caption.page_number;page=pages[number]
            if number not in page_rules:
                raw=original[number-1];raw.set_rotation(0)
                page_rules[number]=_horizontal_rules(raw)
            below=[r for r in page_rules[number] if -3<=r[1]-caption.bbox[3]<=35
                   and r[0]-10<=(caption.bbox[0]+caption.bbox[2])/2<=r[2]+10]
            if not below:continue
            first=min(below,key=lambda r:abs(r[1]-caption.bbox[3]))
            boundary=min((c.bbox[1] for c in captions if c is not caption and c.page_number==number
                          and c.bbox[1]>first[1]+2),default=page.height)
            rules=[r for r in page_rules[number] if first[1]-1<=r[1]<boundary
                   and max(abs(r[0]-first[0]),abs(r[2]-first[2]))<=8]
            chain=[]
            for rule in rules:
                if chain and rule[1]-chain[-1][1]>min(120,page.height*.15):break
                if not chain or rule[1]-chain[-1][1]>3:chain.append(rule)
            if len(chain)<4:continue
            box=(first[0],chain[0][1],first[2],chain[-1][1])
            parts=[o for o in result if o.kind in {'figure','table'} and o.page_number==number
                   and containment(o.bbox,box)>=.93]
            if len(parts)<2:continue
            fields=set()
            for line in page.lines:
                if containment(line.bbox,box)<.85:continue
                match=re.match(r'^\s*([A-Za-z][A-Za-z0-9 -]{0,24}|[\u4e00-\u9fff]{1,12})\s*[:：]',normalize_text(line.text))
                if match:fields.add((match.group(1).strip().casefold(),round(line.bbox[1]/4)))
            counts=Counter(label for label,_ in fields)
            if sum(count>=2 for count in counts.values())<2:continue
            title_probe=replace(parts[0],kind='table',bbox=box)
            if not _matches(title_probe,caption):continue
            parent=replace(title_probe,text='',role='ruled_table_container',
                           panel_boxes=tuple(b for o in parts for b in (o.panel_boxes or (o.bbox,))))
            result=[o for o in result if o not in parts]+[parent]
    return result


def recover_code_like_result_tables(objects,document):
    """An explicit table title plus a native numeric grid overrides a code tag.

    Pipeline arrows inside row labels are data. Require repeated physical
    result columns, never promote arbitrary code or proximity to a title.
    """
    from .numbering import normalize_text
    pages={p.number:p for p in document.pages};result=[]
    for obj in objects:
        candidate=replace(obj,kind='table')
        if obj.kind!='text' or obj.role!='code_body' or not any(
                c.kind=='table_caption' and _matches(candidate,c) for c in objects):
            result.append(obj);continue
        page=pages[obj.page_number];rows=[]
        for line in page.lines:
            if containment(line.bbox,obj.bbox)<.85:continue
            value=normalize_text(line.text).strip()
            if not re.fullmatch(r'[+\-]?[0-9]+(?:[.][0-9]+)?(?:\s*±\s*[0-9]+(?:[.][0-9]+)?)?',value):continue
            center=(line.bbox[1]+line.bbox[3])/2
            row=next((r for r in rows if abs(r[0]-center)<=max(3,(line.bbox[3]-line.bbox[1])*.5)),None)
            if row is None:rows.append([center,[line]])
            else:row[1].append(line)
        profiles=[]
        for y,cells in rows:
            cells=sorted(cells,key=lambda l:l.bbox[0])
            if len(cells)<3:continue
            if any(b.bbox[0]-a.bbox[2]<page.width*.015 for a,b in zip(cells,cells[1:])):continue
            label=any(containment(l.bbox,obj.bbox)>=.85 and l.bbox[2]<cells[0].bbox[0]
                      and abs((l.bbox[1]+l.bbox[3])/2-y)<=max(18,l.bbox[3]-l.bbox[1])
                      and re.search(r'[A-Za-z\u4e00-\u9fff]',l.text) for l in page.lines)
            if label:profiles.append([(l.bbox[0]+l.bbox[2])/2 for l in cells])
        aligned=any(sum(len(other)==len(profile) and all(abs(a-b)<=page.width*.012
                      for a,b in zip(profile,other)) for other in profiles)>=3 for profile in profiles)
        result.append(replace(obj,kind='table',role='table_body') if aligned else obj)
    return result
