"""Reconcile physical fragments before applying missing-caption rules."""
from dataclasses import replace
from .layout_context import containment, union, _panel_match, PANEL
from .caption_rules import _matches, _horizontal_overlap


def recover_native_raster_partitions(targets, document, captions):
    """Preserve source image obligations when a parser merges their envelopes.

    A retained title beside only one separately placed raster cannot caption
    both images. Explicit panel or positional declarations keep a composite.
    """
    pages = {p.number: p for p in document.pages}
    result = []
    for target in targets:
        if target.kind != 'figure' or target.role != 'image_body' or target.panel_boxes:
            result.append(target)
            continue
        images = sorted({b for b in pages[target.page_number].images
                         if containment(b, target.bbox) >= .95
                         and b[2] - b[0] >= target.page_width * .08
                         and b[3] - b[1] >= target.page_height * .06}, key=lambda b: b[1])
        if len(images) != 2:
            result.append(target)
            continue
        horizontal = _horizontal_raster_partition(images, target, pages[target.page_number], captions)
        if horizontal:
            result.extend(replace(target, bbox=box, panel_boxes=(), role='native_raster_partition',
                                  parent_id=None, parent_bbox=None, parent_kind='', caption_owner_id='')
                          for box in horizontal)
            continue
        upper, lower = images
        gap = lower[1] - upper[3]
        width = min(b[2] - b[0] for b in images)
        bounded = (abs(target.bbox[1] - upper[1]) <= 8
                   and abs(target.bbox[3] - lower[3]) <= 8
                   and max(abs(upper[0] - lower[0]), abs(upper[2] - lower[2])) <= max(20, width * .1))
        lower_target = replace(target, bbox=lower)
        lower_title = any(c.kind == 'figure_caption' and c.page_number == target.page_number
                          and 0 <= c.bbox[1] - lower[3] <= 80 and _matches(lower_target, c)
                          for c in captions)
        if not (bounded and gap >= max(20, min(b[3] - b[1] for b in images) * .12)
                and lower_title):
            result.append(target)
            continue
        result.extend(replace(target, bbox=box, panel_boxes=(), role='native_raster_partition',
                              parent_id=None, parent_bbox=None, parent_kind='', caption_owner_id='')
                      for box in images)
    return result


def _horizontal_raster_partition(images, target, page, captions):
    """Two aligned source placements and an exclusive title prove a split."""
    from .caption_physical_ownership import _position_declaration
    left, right = sorted(images, key=lambda box: box[0])
    height = min(box[3] - box[1] for box in images)
    envelope = union(images)
    if (right[0] - left[2] <= .3
            or any(abs(a - b) > 8 for a, b in zip(envelope, target.bbox))
            or max(abs(left[1] - right[1]), abs(left[3] - right[3])) > max(8, height * .1)):
        return None
    local = [c for c in captions if c.kind == 'figure_caption' and c.page_number == page.number
             and -5 <= c.bbox[1] - envelope[3] <= 80]
    physical = [replace(target, bbox=box, caption_owner_id='') for box in (left, right)]
    if any(_position_declaration(c.text) or all(_matches(obj, c) for obj in physical)
           or abs((c.bbox[0] + c.bbox[2] - envelope[0] - envelope[2]) / 2)
           <= max(2, (c.bbox[3] - c.bbox[1]) * .25)
           for c in local):
        return None
    # Original panel letters bind the two placements to one numbered figure.
    letters = []
    for box in (left, right):
        marks = {_panel_match(line.text).group(1).lower() for line in page.lines
                 if line.source == 'native' and _panel_match(line.text)
                 and containment(line.bbox, box) >= .95}
        letters.append(marks)
    if 'a' in letters[0] and 'b' in letters[1]:
        return None
    if any(_matches(physical[i], c) and _horizontal_overlap(physical[1-i], c) < .1
           for c in local for i in range(2)):
        return (left, right)
    return None


def remove_native_fragments(targets):
    result=[]
    for obj in targets:
        if obj.role=='native_figure' and any(
            parent.kind=='figure' and parent.role in {'image_body','chart_body'}
            and parent.page_number==obj.page_number
            and containment(obj.bbox,parent.bbox)>=.75
            and all(delta <= 12 for delta in (
                parent.bbox[0]-obj.bbox[0],parent.bbox[1]-obj.bbox[1],
                obj.bbox[2]-parent.bbox[2],obj.bbox[3]-parent.bbox[3]))
            for parent in targets):
            continue
        result.append(obj)
    return result



def axis_unit(line, objects, page):
    """A parenthesized SI unit beside a numeric axis is not a subpanel tag."""
    import re
    from .numbering import normalize_text
    text = normalize_text(line.text).strip().casefold()
    if not re.fullmatch(r'[（(](?:s|m|h|v|k)[）)]', text):
        return False
    for obj in objects:
        if obj.page_number != page.number:
            continue
        cx = (line.bbox[0]+line.bbox[2])/2
        cy = (line.bbox[1]+line.bbox[3])/2
        if not (obj.bbox[0]-15 <= cx <= obj.bbox[2]+15 and obj.bbox[1]-30 <= cy <= obj.bbox[3]+5):
            continue
        ticks = [l for l in page.lines if re.fullmatch(r'[+\-−]?\d+(?:\.\d+)?', l.text.strip())
                 and obj.bbox[0] <= (l.bbox[0]+l.bbox[2])/2 <= obj.bbox[2]
                 and line.bbox[1]-20 <= l.bbox[1] <= line.bbox[1]+3]
        if len(ticks) >= 3:
            return True
    return False


def _physical_marker_lines(line,page,objects):
    """Split merged native labels when glyphs prove distinct physical bodies."""
    from .numbering import normalize_text
    value=normalize_text(line.text)
    marks=list(PANEL.finditer(value))
    if line.source!='native' or len(marks)<2 or not line.text_regions:
        return [line]
    physical=list(page.images+page.graphics)
    physical.extend(box for o in objects if o.kind in {'figure','table'}
                    and o.page_number==page.number and not o.role.startswith('native_')
                    for box in (o.panel_boxes or (o.bbox,)))
    split=[];choices_by_marker=[]
    for i,mark in enumerate(marks):
        boxes=[box for start,end,box in line.text_regions
               if start<mark.end() and end>mark.start()
               and mark.start()<=start and end<=mark.end()]
        if not boxes:
            return [line]
        box=union(boxes);x=(box[0]+box[2])/2;y=(box[1]+box[3])/2
        if split and box[0]-split[-1].bbox[2]<=max(3,box[3]-box[1]):
            return [line]
        choices=[body for body in physical if body[0]-15<=x<=body[2]+15
                 and body[1]-15<=box[3] and box[1]<=body[3]+35]
        if not choices:return [line]
        choices_by_marker.append(choices)
        end=marks[i+1].start() if i+1<len(marks) else len(value)
        text=value[mark.start():end].strip().rstrip(';；')
        split.append(replace(line,text=text,bbox=box,text_regions=(),reference_regions=()))
    # A wide next-row image may be closer to both merged labels than the two
    # preceding panels. Resolve the row as a whole instead of discarding the
    # second glyph because two independent nearest-neighbour guesses agree.
    def distinct_row(index, selected):
        if index == len(choices_by_marker):
            return True
        if index >= 8:
            return False
        for choice in choices_by_marker[index]:
            if any(containment(choice, old) >= .85 and containment(old, choice) >= .85
                   for old in selected):
                continue
            if selected and any(min(choice[3], old[3]) - max(choice[1], old[1])
                                < .7 * min(choice[3] - choice[1], old[3] - old[1])
                                for old in selected):
                continue
            if distinct_row(index + 1, selected + [choice]):
                return True
        return False
    return split if distinct_row(0, []) else [line]


def panel_label_lines(page, objects, captions=()):
    """Chinese/English translations at one position name the same subpanel."""
    import re
    from .numbering import normalize_text
    result=[]
    declarations = _declared_panel_letters(page, list(captions) or [o for o in objects if o.kind == 'figure_caption'])
    from .panel_notation import canonical_panel_line, numeric_panel_line
    for line in (fragment for original in sorted(page.lines,key=lambda l:(l.bbox[1],l.bbox[0]))
                 if not any(c.kind.endswith('_caption') and c.page_number == page.number
                            and containment(original.bbox, c.bbox) >= .8 for c in captions)
                 for fragment in _physical_marker_lines(original,page,objects)):
        # Font runs often split a subtitle's marker from its description.
        # Reconstruct only a same-row continuation immediately to its right.
        if PANEL.fullmatch(normalize_text(line.text).strip()):
            suffixes = [other for other in page.lines if other is not line
                        and other.source == line.source
                        and 0 <= other.bbox[0]-line.bbox[2] <= 25
                        and abs(other.bbox[1]-line.bbox[1]) <= 2
                        and abs(other.bbox[3]-line.bbox[3]) <= 2
                        and len(re.findall(r'[A-Za-z\u4e00-\u9fff]',other.text)) >= 3]
            if len(suffixes) == 1:
                suffix = suffixes[0]
                line = replace(line, text=line.text+' '+suffix.text,
                               bbox=union([line.bbox,suffix.bbox]))
        line = numeric_panel_line(line,page,captions,objects)
        line = canonical_panel_line(line,page,captions)
        # A prose explanation assigning several letters to conditions is not
        # another physical occurrence of its first letter. Actual panel labels
        # remain individual lines; repeated adjacent tags/semicolon clauses
        # describe the already labelled bodies.
        description=normalize_text(line.text)
        mentions=list(PANEL.finditer(description))
        if len(mentions)>1 and PANEL.sub('',description).strip() and (re.search(r'[;；]',description) or any(
                not description[a.end():b.start()].strip()
                for a,b in zip(mentions,mentions[1:]))):continue
        bare = line.text.strip().lower()
        owners = [o for o in objects if o.kind == 'figure' and o.page_number == page.number
                  and o.bbox[0]-30 <= line.bbox[0] <= o.bbox[2]
                  and o.bbox[1]-30 <= line.bbox[1] <= o.bbox[3]]
        following = [(box[1], letters) for box,letters in declarations if box[1] > line.bbox[3]
                     and any(max(0,min(box[2],o.bbox[2])-max(box[0],o.bbox[0]))
                             >= .25*min(box[2]-box[0],o.bbox[2]-o.bbox[0]) for o in owners)]
        declared = min(following, key=lambda pair:pair[0])[1] if following else set()
        # A bare letter after a same-row word inside a graphic is part of
        # that label (for example a lane name), not a new panel occurrence.
        # Native PDFs often split a label into different font spans.
        word_prefix = re.fullmatch(r'[a-z]',bare) and any(
            prefix is not line and prefix.source==line.source
            and len(re.findall(r'[A-Za-z\u4e00-\u9fff]',prefix.text))>=2
            and 0<=line.bbox[0]-prefix.bbox[2]<=max(12,(line.bbox[3]-line.bbox[1])*2.5)
            and min(line.bbox[3],prefix.bbox[3])-max(line.bbox[1],prefix.bbox[1])
                >=.75*min(line.bbox[3]-line.bbox[1],prefix.bbox[3]-prefix.bbox[1])
            and any(o.bbox[0]-2<=prefix.bbox[0] and line.bbox[2]<=o.bbox[2]+2
                    and o.bbox[1]<=line.bbox[1]<=o.bbox[3] for o in owners)
            for prefix in page.lines)
        if not word_prefix and len(declared) >= 2 and bare in declared and re.fullmatch(r'[a-z]', bare):
            # Journals commonly print bare bold panel letters. Accept them only
            # when the figure title explicitly describes those same panels.
            if any(o.kind == 'figure' and o.page_number == page.number
                   and o.bbox[0]-30 <= line.bbox[0] <= o.bbox[2]
                   and o.bbox[1]-30 <= line.bbox[1] <= o.bbox[3] for o in objects):
                line = replace(line, text='('+bare+')')
        match=_panel_match(line.text)
        if not match:
            continue
        chinese=bool(re.search(r'[\u4e00-\u9fff]',line.text[match.end():]))
        translated=False
        for old in reversed(result):
            previous=_panel_match(old.text)
            if previous.group(1).lower()!=match.group(1).lower():
                continue
            old_chinese=bool(re.search(r'[\u4e00-\u9fff]',old.text[previous.end():]))
            english=line.text[match.end():] if old_chinese else old.text[previous.end():]
            same_row = min(line.bbox[3], old.bbox[3]) - max(line.bbox[1], old.bbox[1]) >= .5 * min(
                line.bbox[3]-line.bbox[1], old.bbox[3]-old.bbox[1])
            same_label = (normalize_text(line.text[match.end():]).strip().casefold()
                          == normalize_text(old.text[previous.end():]).strip().casefold())
            common_body = any(o.kind == 'figure' and o.page_number == page.number
                and not o.role.startswith('native_') and all(
                    o.bbox[0]-15 <= (l.bbox[0]+l.bbox[2])/2 <= o.bbox[2]+15
                    and o.bbox[1]-15 <= (l.bbox[1]+l.bbox[3])/2 <= o.bbox[3]+35
                    for l in (line, old)) for o in objects)
            stacked_duplicate = (same_label and 0 <= line.bbox[1]-old.bbox[3] <= 35
                and abs((line.bbox[0]+line.bbox[2]-old.bbox[0]-old.bbox[2])/2) <= 25)
            if common_body and (stacked_duplicate or (same_row and (same_label or (
                    chinese != old_chinese and re.search(r'[A-Za-z]{3}', english))))):
                translated = True
                break
            if (chinese!=old_chinese and re.search(r'[A-Za-z]{3}',english)
                    and 0 <= line.bbox[1]-old.bbox[3] <= 35
                    and abs((line.bbox[0]+line.bbox[2]-old.bbox[0]-old.bbox[2])/2) <= 25
                    and not any(o.kind in {'figure','table'} and o.page_number==page.number
                                and old.bbox[3] < o.bbox[1] < line.bbox[3] for o in objects)):
                translated=True
                break
        if not translated:
            result.append(line)
        else:
            # The translated subtitle is one physical label envelope. Keeping
            # only its upper language row loses proximity to top-labelled
            # panels and can turn each subtable into a separate object.
            index=result.index(old)
            result[index]=replace(old,bbox=union([old.bbox,line.bbox]))
    return result


def panel_label_conflict(objects, document, captions=()):
    """A repeated subpanel label inside or just below pieces starts a new figure.

    Use physical label occurrences, not sets per object: a border-straddling
    label can otherwise be assigned to the next panel and lose the restart.
    """
    tags=[]
    for page in document.pages:
        regions=[o.bbox for o in objects if o.page_number==page.number]
        if not regions:
            continue  # No local observation can own a label on this page.
        for line in panel_label_lines(page, objects, captions):
            match=_panel_match(line.text)
            x=(line.bbox[0]+line.bbox[2])/2
            y=(line.bbox[1]+line.bbox[3])/2
            if match and not axis_unit(line, objects, page) and any(b[0]-15<=x<=b[2]+15 and b[1]-15<=y<=b[3]+35 for b in regions):
                tags.append((page.number,match.group(1).lower()))
    return len(tags)!=len(set(tags))


def _shared_grid_title(top, bottom, targets, captions):
    # Wider row gaps need positive grid evidence, not merely nearby objects.
    def peer(item):
        return [t for t in targets if t.kind=='figure' and t.page_number==item.page_number
                and (0<=t.bbox[0]-item.bbox[2]<=80 or 0<=item.bbox[0]-t.bbox[2]<=80)
                and min(t.bbox[3],item.bbox[3])-max(t.bbox[1],item.bbox[1]) >= .7*min(t.bbox[3]-t.bbox[1],item.bbox[3]-item.bbox[1])]
    a,b=peer(top),peer(bottom)
    if not a or not b:return False
    box=union([top.bbox,bottom.bbox]+[t.bbox for t in a+b])
    group=replace(top,bbox=box)
    return any(c.kind=='figure_caption' and c.page_number==top.page_number and _matches(group,c)
               and c.bbox[2]-c.bbox[0]>=(box[2]-box[0])*.75
               and abs((c.bbox[0]+c.bbox[2]-box[0]-box[2])/2)<(box[2]-box[0])*.12 for c in captions)

def reconcile_caption_alias_owners(targets,captions,document):
    """Preserve physical ownership proved by both native bilingual titles.

    Alias folding otherwise drops one parser parent. Two real image carriers
    can share that title even when neither translation spans the final panel.
    """
    from .numbering import caption_match, normalize_label, normalize_text
    from .figure_identity_repair import _barrier
    import re
    pages={p.number:p for p in document.pages}
    targets=list(targets)
    def identity(text):
        text=re.sub(r'(?<=\d)\s*([.\-])\s*(?=\d)',r'\1',normalize_text(text))
        match=caption_match(text,'figure')
        return normalize_label(match.group('number')) if match else None
    def chinese(text):return normalize_text(text).lstrip().startswith('图')
    aliases=[c for c in captions if c.kind=='figure_caption' and c.parent_id and identity(c.text)]
    for offset,a in enumerate(aliases):
        for b in aliases[offset+1:]:
            if (a.page_number!=b.page_number or a.parent_id==b.parent_id
                    or chinese(a.text)==chinese(b.text) or identity(a.text)!=identity(b.text)
                    or abs(a.bbox[1]-b.bbox[1])>45 or _horizontal_overlap(a,b)<.5):continue
            page=pages[a.page_number]
            if not all(any(l.source=='native' and identity(l.text)==identity(c.text)
                           and chinese(l.text)==chinese(c.text) and containment(l.bbox,c.bbox)>.65
                           for l in page.lines) for c in (a,b)):continue
            parents=[[o for o in targets if o.kind=='figure' and o.page_number==a.page_number
                      and o.parent_id==c.parent_id] for c in (a,b)]
            if any(len(items)!=1 for items in parents):continue
            carriers=[[im for im in page.images if containment(items[0].bbox,im)>.9
                       and (im[2]-im[0])*(im[3]-im[1])<page.width*page.height*.72] for items in parents]
            if any(len(items)!=1 for items in carriers):continue
            left,right=sorted((items[0] for items in carriers),key=lambda im:im[0])
            if (left==right or not -2<=right[0]-left[2]<=20
                    or min(left[3],right[3])-max(left[1],right[1])<.8*min(left[3]-left[1],right[3]-right[1])):continue
            members=[o for o in targets if o.kind=='figure' and o.page_number==a.page_number
                     and any(containment(o.bbox,im)>.9 for im in (left,right))]
            if len(members)<2:continue
            box=union([left,right]);width=box[2]-box[0]
            if not all(-3<=c.bbox[1]-box[3]<=60 and abs((c.bbox[0]+c.bbox[2]-box[0]-box[2])/2)<=width*.12 for c in (a,b)):continue
            if any(c not in (a,b) and c.kind=='figure_caption' and c.page_number==a.page_number
                   and not any(identity(c.text)==identity(alias.text) and containment(c.bbox,alias.bbox)>.65
                               for alias in (a,b))
                   and any(_matches(o,c) for o in members) for c in captions):continue
            if _barrier(members,b,page,targets):continue
            ids={id(o) for o in members}
            targets=[o for o in targets if id(o) not in ids]+[replace(members[0],bbox=box,
                role='shared_caption_panels',panel_boxes=tuple(dict.fromkeys((left,right))))]
    return targets


def shared_title_groups(targets,captions,document):
    """Aligned panels can share a title spanning their combined width.

    A short centred caption or proximity alone is insufficient. Separate rows,
    intervening titles and panels with their own title remain independent.
    """
    from .compact_rows import merge_compact_sample_rows
    targets=merge_compact_sample_rows(targets,captions,document)
    pages={page.number:page for page in document.pages}
    for caption in captions:
        if caption.kind!='figure_caption':continue
        eligible=[(i,t) for i,t in enumerate(targets) if t.kind=='figure'
                  and t.page_number==caption.page_number and _matches(t,caption)]
        rows=[]
        for i,t in eligible:
            group=next((g for g in rows if all(
                min(t.bbox[3],other.bbox[3])-max(t.bbox[1],other.bbox[1])
                    >= .75*min(t.bbox[3]-t.bbox[1],other.bbox[3]-other.bbox[1])
                for _,other in g)),None)
            if group is None:rows.append([(i,t)])
            else:group.append((i,t))
        candidates=[]
        for row in rows:
            if len(row)<2 or panel_label_conflict([t for _,t in row],document,captions):continue
            box=union([t.bbox for _,t in row]);width=box[2]-box[0]
            ordered=sorted(row,key=lambda pair:pair[1].bbox[0])
            if any(b.bbox[0]-a.bbox[2]>80 for (_,a),(_,b) in zip(ordered,ordered[1:])):
                from .caption_physical_ownership import _native_caption_text, _position_declaration
                declared = _position_declaration(_native_caption_text(caption, pages[caption.page_number]))
                if not (len(ordered)==2 and all(t.role=='chart_body' for _,t in ordered)
                        and declared==('horizontal',(1,1))):
                    continue
            wide = caption.bbox[2]-caption.bbox[0] >= width*.75
            # A total title may be short, but must straddle the panel gutter,
            # be centred on the entire equal-height row, and name both sides.
            centre = abs((caption.bbox[0]+caption.bbox[2]-box[0]-box[2])/2)
            physical_pair = all(t.role=='image_body' and any(
                containment(t.bbox,b)>=.9 and containment(b,t.bbox)>=.9
                for b in pages[t.page_number].images) for _,t in ordered)
            shared_centre = (centre <= width*.04 and len(ordered)==2
                and (all(t.role=='chart_body' for _,t in ordered) or physical_pair)
                and _horizontal_overlap(ordered[0][1],caption)>=.25
                and _horizontal_overlap(ordered[-1][1],caption)>=.25
                and caption.bbox[0] < ordered[0][1].bbox[2]
                and caption.bbox[2] > ordered[-1][1].bbox[0])
            if not (wide or shared_centre):continue
            if abs((caption.bbox[0]+caption.bbox[2]-box[0]-box[2])/2)>width*.12:continue
            # Another title between a candidate row and this title is a boundary.
            low,high=sorted(( (box[1]+box[3])/2, (caption.bbox[1]+caption.bbox[3])/2 ))
            if any(c is not caption and c.kind=='figure_caption'
                   and c.page_number==caption.page_number and low<(c.bbox[1]+c.bbox[3])/2<high
                   for c in captions):continue
            own=[c for c in captions if c is not caption and c.kind=='figure_caption'
                 and c.page_number==caption.page_number
                 and any(_matches(t,c) and c.bbox[0]>=t.bbox[0]-5 and c.bbox[2]<=t.bbox[2]+5 for _,t in row)]
            if own:continue
            gap=max(caption.bbox[1]-box[3],box[1]-caption.bbox[3],0)
            candidates.append((gap,row,box))
        if candidates:
            _,row,box=min(candidates,key=lambda candidate:candidate[0])
            ids={i for i,_ in row}
            targets=[t for i,t in enumerate(targets) if i not in ids]+[replace(row[0][1],bbox=box,role='shared_caption_panels',
                panel_boxes=tuple(b for _,t in row for b in (t.panel_boxes or (t.bbox,))))]
    return targets


def shared_table_blocks(targets, captions, document):
    """Rejoin touching table pieces, or stacked panels with repeated row labels."""
    pages={page.number:page for page in document.pages}
    targets=list(targets)
    def row_labels(target):
        return {line.text.strip() for line in pages[target.page_number].lines
                if target.bbox[0]-3<=line.bbox[0]<=target.bbox[0]+(target.bbox[2]-target.bbox[0])*.2
                and target.bbox[1]<=line.bbox[1]<=target.bbox[3]
                and len(line.text.strip())>=3 and not line.text.strip().replace('.','').isdigit()}
    def column_headers(target):
        page_lines = pages[target.page_number].lines
        # Text in the right-hand header area, before the first numeric data row.
        right = [l for l in page_lines if target.bbox[0]+(target.bbox[2]-target.bbox[0])*.25 < l.bbox[0] < target.bbox[2]
                 and target.bbox[1] <= l.bbox[1] < target.bbox[3]]
        import re
        data_y = min((l.bbox[1] for l in right if re.fullmatch(r"[+\-−]?\d+(?:\.\d+)?%?",l.text.strip())),default=target.bbox[1]+(target.bbox[3]-target.bbox[1])*.3)
        return {l.text.casefold().strip() for l in right if l.bbox[3] <= data_y and re.search(r"[A-Za-z\u4e00-\u9fff]",l.text)}
    changed=True
    while changed:
        changed=False
        for i,a in enumerate(targets):
            if a.kind!='table':continue
            for j,b in enumerate(targets[i+1:],i+1):
                if b.kind!='table' or a.page_number!=b.page_number:continue
                top,bottom=sorted((a,b),key=lambda t:t.bbox[1])
                gap=bottom.bbox[1]-top.bbox[3]
                native_overlap = top.role in {'native_table','continuous_table_blocks'} and bottom.role in {'native_table','continuous_table_blocks'} and gap < 0
                if not (native_overlap or -2<=gap<=20):continue
                aligned = max(abs(top.bbox[0]-bottom.bbox[0]),abs(top.bbox[2]-bottom.bbox[2]))<=10
                repeated = len(row_labels(top)&row_labels(bottom))>=3
                centred = abs((top.bbox[0]+top.bbox[2]-bottom.bbox[0]-bottom.bbox[2])/2)<=15
                if not (aligned or repeated and centred):continue
                between=[line for line in pages[a.page_number].lines
                         if top.bbox[3]<=line.bbox[1] and line.bbox[3]<=bottom.bbox[1]
                         and line.text.strip()]
                if between:continue
                if any(c.kind=='table_caption' and c.page_number==a.page_number
                       and top.bbox[1]<(c.bbox[1]+c.bbox[3])/2<bottom.bbox[3] for c in captions):continue
                if gap>2:
                    if not repeated:continue
                    top_headers,bottom_headers=column_headers(top),column_headers(bottom)
                    # Repeated methods alone do not establish one table. Different
                    # experiments with conflicting headers must remain independent.
                    if not top_headers or not bottom_headers or not top_headers & bottom_headers:continue
                targets=[t for k,t in enumerate(targets) if k not in {i,j}]+[
                    replace(top,bbox=union([top.bbox,bottom.bbox]),role='continuous_table_blocks')]
                changed=True;break
            if changed:break
    return targets


def continuous_chart_rows(targets, captions, document, *, before_labels=False):
    """Merge abutting panels in the same column; restarted labels are boundaries."""
    targets=list(targets)
    # Preserve the original panel axes before vertical fragments lose their
    # individual geometry and chart_body role in column envelopes.
    if before_labels:
        targets = shared_axis_groups(targets, captions, document)
    changed=True
    while changed:
        changed=False
        for i,a in enumerate(targets):
            if a.kind!='figure':continue
            for j,b in enumerate(targets[i+1:],i+1):
                if b.kind!='figure' or a.page_number!=b.page_number:continue
                top,bottom=sorted((a,b),key=lambda t:t.bbox[1])
                gap=bottom.bbox[1]-top.bbox[3]
                # Grid gutters scale with panel size, not PDF point units.
                # A wider gutter still needs aligned peers and a total title.
                gutter=max(12,min(top.bbox[3]-top.bbox[1],bottom.bbox[3]-bottom.bbox[1])*.2)
                if not -6<=gap<=gutter:continue
                if max(abs(top.bbox[0]-bottom.bbox[0]),abs(top.bbox[2]-bottom.bbox[2]))>15:continue
                if gap>4 and not _shared_grid_title(top,bottom,targets,captions):continue
                if panel_label_conflict([top,bottom],document,captions):continue
                if before_labels and any(
                    page.number == top.page_number and any(
                        top.bbox[0]-15 <= (line.bbox[0]+line.bbox[2])/2 <= top.bbox[2]+15
                        and top.bbox[1]-15 <= line.bbox[1] <= top.bbox[3]+8
                        and not axis_unit(line, [top], page)
                        for line in panel_label_lines(page, [top,bottom], captions))
                    for page in document.pages):
                    continue  # A labelled upper panel must reach letter grouping intact.
                if any(c.kind=='figure_caption' and c.page_number==a.page_number
                       and top.bbox[1]<(c.bbox[1]+c.bbox[3])/2<bottom.bbox[3]
                       and max(c.bbox[0],top.bbox[0])<min(c.bbox[2],top.bbox[2]) for c in captions):continue
                targets=[t for k,t in enumerate(targets) if k not in {i,j}]+[
                    replace(top,bbox=union([top.bbox,bottom.bbox]),role='continuous_chart_panels',
                            panel_boxes=(top.panel_boxes or (top.bbox,))+(bottom.panel_boxes or (bottom.bbox,)))]
                changed=True;break
            if changed:break
    return targets


def remove_embedded_targets(targets, captions, evidence):
    """A widget within a table and a code listing are not standalone figures."""
    import re
    result=[]
    for target in targets:
        if target.kind=='figure' and any(
            parent.kind=='table' and parent.page_number==target.page_number
            and containment(target.bbox,parent.bbox)>=.93
            and any(c.kind=='table_caption' and _matches(parent,c) for c in captions)
            for parent in targets):continue
        code=[o for o in evidence if o.kind=='text' and o.role=='code_body'
              and o.page_number==target.page_number and containment(target.bbox,o.bbox)>=.85]
        if code and any(re.search(r'(?:算法|Algorithm)\s*\d',o.text,re.I)
                        or len(re.findall(r'(?m)^\s*\d+\s*[:.]?\s*(?:for|if|while|return|end)\b',o.text,re.I))>=3
                        for o in code):continue
        result.append(target)
    return result


def shared_axis_groups(targets, captions, document):
    """Rejoin tight plot grids using repeated axes or keyed native legends.

    Geometric proximity alone is insufficient: every connected panel must
    share an axis label with a neighbour, and the group needs one common title.
    """
    import re
    from .numbering import normalize_text
    from .caption_rules import _horizontal_overlap
    pages = {p.number: p for p in document.pages}
    targets = labelled_grid_with_single_typo(targets, captions, document)

    def axes(item):
        x1, y1, x2, y2 = item.bbox
        labels = set()
        for line in pages[item.page_number].lines:
            cx = (line.bbox[0]+line.bbox[2])/2
            cy = (line.bbox[1]+line.bbox[3])/2
            text = re.sub(r'\s+', '', normalize_text(line.text)).casefold()
            near_bottom = y2-24 <= cy <= y2+5 and x1 <= cx <= x2
            near_left = x1-5 <= cx <= x1+30 and y1 <= cy <= y2
            if ((near_bottom or near_left) and len(text) <= 60
                    and re.search(r'[a-z\u4e00-\u9fff]', text)
                    and (not _panel_match(text) or axis_unit(line, [item], pages[item.page_number]))):
                labels.add(text)
        # Numeric series names are meaningful only beside actual coloured
        # PDF keys. Repeated axis ticks alone must never join adjacent plots.
        keyed=[]
        page=pages[item.page_number]
        for line in page.lines:
            if (line.source!='native' or not line.text.strip()
                    or containment(line.bbox,item.bbox)<.9):continue
            if any(containment(mark,item.bbox)>.9
                   and 0<=line.bbox[0]-mark[2]<=8
                   and abs((mark[1]+mark[3]-line.bbox[1]-line.bbox[3])/2)<=4
                   for mark in page.legend_marks):
                keyed.append(line)
        if len(keyed)>=3:
            keyed.sort(key=lambda l:(round(l.bbox[1]/5),l.bbox[0]))
            labels.add('legend:'+ '|'.join(normalize_text(l.text).strip().casefold() for l in keyed))
        metadata=[]
        for line in pages[item.page_number].lines:
            cx=(line.bbox[0]+line.bbox[2])/2;cy=(line.bbox[1]+line.bbox[3])/2
            if y2 <= cy <= y2+50 and x1<=cx<=x2:
                metadata.extend(re.findall(r'([A-Za-z][A-Za-z_]{1,18})\s*=\s*[-+]?\d',line.text))
        if len(set(metadata))>=2:labels.update('metric:'+m.casefold() for m in metadata)
        return labels

    indices = [i for i, o in enumerate(targets) if o.kind == 'figure'
               and o.role in {'chart_body', 'image_body'}]
    labels = {i: axes(targets[i]) for i in indices}
    edges = {i: set() for i in indices}
    for offset, i in enumerate(indices):
        a = targets[i]
        for j in indices[offset+1:]:
            b = targets[j]
            if a.page_number != b.page_number or not labels[i] & labels[j]:
                continue
            widths = [o.bbox[2]-o.bbox[0] for o in (a,b)]
            heights = [o.bbox[3]-o.bbox[1] for o in (a,b)]
            if min(widths)/max(widths) < .65 or min(heights)/max(heights) < .65:
                continue
            xgap = max(a.bbox[0]-b.bbox[2], b.bbox[0]-a.bbox[2], 0)
            ygap = max(a.bbox[1]-b.bbox[3], b.bbox[1]-a.bbox[3], 0)
            yoverlap = min(a.bbox[3],b.bbox[3])-max(a.bbox[1],b.bbox[1])
            if not (xgap <= 35 and yoverlap >= min(heights)*.65
                    or ygap <= (60 if len({s for s in labels[i]&labels[j] if s.startswith('metric:')})>=2 else 24) and _horizontal_overlap(a,b) >= .45):
                continue
            top, bottom = sorted((a,b), key=lambda o:o.bbox[1])
            if ygap and any(c.kind == 'figure_caption' and c.page_number == a.page_number
                            and top.bbox[3]-3 <= c.bbox[1] < bottom.bbox[1]
                            for c in captions):
                continue
            if ygap and any(top.bbox[3]+3 <= l.bbox[1] and l.bbox[3] <= bottom.bbox[1]
                            and len(re.findall(r'[A-Za-z\u4e00-\u9fff]', l.text)) >= 12
                            and l.bbox[2]-l.bbox[0] >= min(widths)*.7
                            for l in pages[a.page_number].lines):
                continue
            if panel_label_conflict([a,b], document, captions):
                continue
            edges[i].add(j)
            edges[j].add(i)
    used = set()
    merged = []
    for start in indices:
        if start in used:
            continue
        component, pending = set(), [start]
        while pending:
            i = pending.pop()
            if i in component:
                continue
            component.add(i)
            pending.extend(edges[i]-component)
        used.update(component)
        if len(component) < 2:
            continue
        members = [targets[i] for i in component]
        if _independently_referenced_rasters(members, captions, pages[members[0].page_number]):
            continue
        box = union([o.bbox for o in members])
        combined = replace(members[0], bbox=box, role='shared_axis_panels',
                           panel_boxes=tuple(b for o in members for b in (o.panel_boxes or (o.bbox,))))
        common = [c for c in captions if c.kind == 'figure_caption'
                  and c.page_number == combined.page_number and _matches(combined,c)
                  and c.bbox[1] >= box[3]-3
                  and abs((c.bbox[0]+c.bbox[2]-box[0]-box[2])/2) <= max(20,(box[2]-box[0])*.08)]
        interior = [c for c in captions if c.kind == 'figure_caption'
                    and c.page_number == combined.page_number
                    and box[1] < c.bbox[1] < box[3]-3
                    and _horizontal_overlap(combined,c) >= .25]
        def caption_gap(target, title):
            return max(title.bbox[1]-target.bbox[3], target.bbox[1]-title.bbox[3], 0)
        independent = []
        for title in captions:
            if title.kind != 'figure_caption' or title.page_number != combined.page_number or title in common:
                continue
            owners = [o for o in members if _matches(o,title)]
            if not owners:
                continue
            gap = min(caption_gap(o,title) for o in owners)
            # An earlier figure's nearby caption belongs to that earlier figure
            # when it has the nearer edge; it is not a member's independent title.
            if not any(i not in component and o.kind == 'figure' and o.page_number == combined.page_number
                       and _matches(o,title) and caption_gap(o,title) < gap
                       for i,o in enumerate(targets)):
                independent.append(title)
        panel_tags = [l for l in pages[combined.page_number].lines
                      if _panel_match(l.text) and not axis_unit(l, members, pages[combined.page_number])
                      and box[3]-3 <= l.bbox[1] <= box[3]+35
                      and box[0]-15 <= (l.bbox[0]+l.bbox[2])/2 <= box[2]+15]
        # A named subpanel can contain several plots with shared axes. Its
        # sibling may use a different axis, so first restore the named panel;
        # the existing letter-order grouping then resolves the full figure.
        row_box = union([o.bbox for o in targets if o.kind == 'figure'
                         and o.page_number == combined.page_number and abs(o.bbox[3]-box[3]) <= 10])
        named_titles = [c for c in captions if c.kind == 'figure_caption'
            and c.page_number == combined.page_number and 0 <= c.bbox[1]-box[3] <= 80
            and abs((c.bbox[0]+c.bbox[2]-row_box[0]-row_box[2])/2) <= max(20,(row_box[2]-row_box[0])*.08)]
        named_panel = bool(panel_tags and named_titles)
        independent = [c for c in independent if not (named_panel and c in named_titles)]
        if (len(common) == 1 or named_panel) and not interior and not independent and not panel_label_conflict(members, document, captions):
            merged.append((component, combined))
    removed = {i for component, _ in merged for i in component}
    return [o for i,o in enumerate(targets) if i not in removed] + [o for _,o in merged]


def _independently_referenced_rasters(members, captions, page):
    """Two original plots explicitly cited as distinct figures keep both titles.

    Repeated axes are common to separate experiments. A source sentence citing
    two figure IDs respectively supplies independent identity evidence even
    after one of those figures loses its main title.
    """
    import re
    from .numbering import LABEL, caption_match, normalize_label, normalize_text
    if len(members) != 2:
        return False
    owners = []
    for member in members:
        choices = [b for b in page.images if containment(member.bbox, b) >= .85
                   and containment(b, member.bbox) >= .85]
        if len(choices) != 1 or choices[0] in owners:
            return False
        owners.append(choices[0])
    pair = re.compile(r'(?:图|Figures?|Figs?\.?)\s*' + LABEL.replace('?P<number>', '?P<first>')
                      + r'\s*(?:和|与|及|、|and\b|&)\s*(?:图|Figures?|Figs?\.?)?\s*'
                      + LABEL.replace('?P<number>', '?P<second>'), re.I)
    low = min(o.bbox[1] for o in members)
    for line in page.lines:
        if (line.source != 'native' or line.bbox[3] > low
                or low - line.bbox[3] > 200
                or not re.search(r'分别|\brespectively\b', line.text, re.I)):
            continue
        match = pair.search(normalize_text(line.text))
        if not match:
            continue
        numbers = {normalize_label(match.group('first')), normalize_label(match.group('second'))}
        if len(numbers) != 2:
            continue
        for cap in captions:
            if cap.kind != 'figure_caption' or cap.page_number != page.number:
                continue
            declared = caption_match(cap.text, 'figure')
            if (declared and normalize_label(declared.group('number')) in numbers
                    and _matches(replace(members[0], bbox=union([o.bbox for o in members])), cap)
                    and len(PANEL.findall(cap.text)) < 2):
                return True
    return False


def recover_interface_figures(objects, document):
    """Reconstruct explicitly labelled UI/code screenshot composites.

    UI headings, an icon, several named fields, ordered subpanel titles and a
    final figure title jointly establish a screenshot envelope.
    """
    import re
    from .caption_rules import _horizontal_overlap
    pages = {p.number:p for p in document.pages}
    objects = recover_native_interface_figures(list(objects), document)
    recovered = []
    for table in objects:
        if table.kind != 'table' or len(re.findall(r'[A-Za-z][A-Za-z /]{1,30}:', table.text)) < 3:
            continue
        if any(c.kind == 'table_caption' and _matches(table,c) for c in objects):
            continue
        page = pages[table.page_number]
        local = [o for o in objects if o.page_number == table.page_number]
        heads = [o for o in local if o.kind == 'text' and o.role == 'title'
                 and 0 <= table.bbox[1]-o.bbox[3] <= 120
                 and o.bbox[0] >= table.bbox[0]-20 and o.bbox[2] <= table.bbox[2]+20]
        icons = [o for o in local if o.kind == 'figure'
                 and o.bbox[2]-o.bbox[0] <= (table.bbox[2]-table.bbox[0])*.25
                 and 0 <= table.bbox[1]-o.bbox[3] <= 100
                 and table.bbox[0]-20 <= o.bbox[0] <= table.bbox[2]]
        if not heads or not icons:
            continue
        labels = [(m.group(1).lower(),l) for l in page.lines if (m:=_panel_match(l.text))
                  and table.bbox[0] <= (l.bbox[0]+l.bbox[2])/2 <= table.bbox[2]]
        first = [l for tag,l in labels if tag == 'a' and 0 <= l.bbox[1]-table.bbox[3] <= 70]
        second = [l for tag,l in labels if tag == 'b']
        for a in first:
            for b in second:
                if not a.bbox[3] < b.bbox[1] < a.bbox[3]+200:
                    continue
                peers = [o for o in local if (o.kind == 'figure' or o.role == 'code_body')
                         and a.bbox[3]-2 <= o.bbox[1] < b.bbox[1]
                         and o.bbox[3] <= b.bbox[3]+3
                         and _horizontal_overlap(table,o) >= .75
                         and _horizontal_overlap(o,replace(o,bbox=b.bbox)) >= .5
                         and o.bbox[2]-o.bbox[0] >= (table.bbox[2]-table.bbox[0])*.65]
                titles = [o for o in local if o.kind == 'figure_caption'
                          and 0 <= o.bbox[1]-b.bbox[3] <= 65 and _horizontal_overlap(table,o) >= .5]
                if not peers or not titles:
                    continue
                box = union([o.bbox for o in [table,*heads,*icons,*peers]])
                if any(o.kind.endswith('_caption') and box[1] < o.bbox[1] < box[3]
                       for o in local):
                    continue
                recovered.append(replace(table,kind='figure',bbox=box,text='',role='captioned_interface'))
    if not recovered:
        return objects
    return [o for o in objects if not (o.kind in {'figure','table'} and any(
        p.page_number == o.page_number and containment(o.bbox,p.bbox) >= .93 for p in recovered))] + recovered


def attach_plot_legends(objects, document):
    """Attach a detached one-column legend using its coloured series keys."""
    import re
    pages = {p.number:p for p in document.pages}
    objects = list(objects)
    removed = set()
    for i, legend in enumerate(objects):
        if legend.kind not in {'figure','table'}:
            continue
        def title_rank(obj, caption):
            gap=max(caption.bbox[1]-obj.bbox[3], obj.bbox[1]-caption.bbox[3], 0)
            center=abs((caption.bbox[0]+caption.bbox[2]-obj.bbox[0]-obj.bbox[2])/2)
            return gap, center
        titles=[c for c in objects if c.kind==legend.kind+'_caption' and _matches(legend,c)]
        if any(not any(chart is not legend and chart.kind=='figure' and chart.role=='chart_body'
                       and _matches(chart,title) and title_rank(chart,title)<title_rank(legend,title)
                       for chart in objects) for title in titles):
            continue
        page = pages[legend.page_number]
        lines = [l for l in page.lines if containment(l.bbox,legend.bbox) >= .8 and l.text.strip()]
        if len(lines) < 2 or any(re.search(r'(?:^|\s)[+\-]?\d+(?:\.\d+)?(?:\s|$)',l.text) for l in lines):
            continue
        if any(abs((a.bbox[1]+a.bbox[3]-b.bbox[1]-b.bbox[3])/2) < 4
               for k,a in enumerate(lines) for b in lines[k+1:]):
            continue  # Several text columns form a table, not a series legend.
        keyed = [l for l in lines if any(m[2] <= l.bbox[0]+3 and l.bbox[0]-m[2] <= 18
                 and abs((m[1]+m[3]-l.bbox[1]-l.bbox[3])/2) <= 7
                 for m in page.legend_marks)]
        if len(keyed) < 2 or len(keyed) < len(lines)*.66:
            keyed = _rendered_series_key_lines(page, legend, lines, document.path)
        if len(keyed) < 2 or len(keyed) < len(lines)*.66:
            continue
        neighbours = [(j,c) for j,c in enumerate(objects) if c.kind == 'figure' and c.role == 'chart_body'
                      and c.page_number == legend.page_number
                      and legend.bbox[2]-legend.bbox[0] <= (c.bbox[2]-c.bbox[0])*.65
                      and max(c.bbox[0]-legend.bbox[2],legend.bbox[0]-c.bbox[2],0) <= 60
                      and min(c.bbox[3],legend.bbox[3])-max(c.bbox[1],legend.bbox[1]) >= (legend.bbox[3]-legend.bbox[1])*.85]
        if len(neighbours) == 1:
            j, chart = neighbours[0]
            objects[j] = replace(chart,bbox=union([chart.bbox,legend.bbox]))
            removed.add(i)
    return [o for i,o in enumerate(objects) if i not in removed]


def complete_panel_envelopes(targets, captions, document):
    """Absorb leftover pieces inside a captioned, explicitly labelled grid.

    Letter grouping creates a rectangular envelope. Reconcile fragments again
    only when that envelope has multiple distinct panel labels, one outer
    title, and no intervening title or repeated label indicating a new figure.
    """
    pages = {p.number: p for p in document.pages}
    result = []
    for child in targets:
        absorbed = False
        if child.kind == 'figure':
            for parent in targets:
                if parent is child or parent.kind != 'figure' or parent.page_number != child.page_number:
                    continue
                pa = (parent.bbox[2]-parent.bbox[0])*(parent.bbox[3]-parent.bbox[1])
                ca = (child.bbox[2]-child.bbox[0])*(child.bbox[3]-child.bbox[1])
                if pa < ca*1.4 or containment(child.bbox, parent.bbox) < .85:
                    continue
                if any(delta > 20 for delta in (
                        parent.bbox[0]-child.bbox[0], parent.bbox[1]-child.bbox[1],
                        child.bbox[2]-parent.bbox[2], child.bbox[3]-parent.bbox[3])):
                    continue
                local_titles = [c for c in captions if c.kind == 'figure_caption'
                                and c.page_number == parent.page_number]
                if not any(_matches(parent, c) for c in local_titles):
                    continue
                if any(parent.bbox[1]+3 < c.bbox[1] < parent.bbox[3]-3
                       for c in local_titles):
                    continue
                page = pages[parent.page_number]
                labels = [l for l in panel_label_lines(page, [parent], captions)
                          if parent.bbox[0]-15 <= (l.bbox[0]+l.bbox[2])/2 <= parent.bbox[2]+15
                          and parent.bbox[1] <= l.bbox[1] <= parent.bbox[3]+35
                          and not axis_unit(l, [parent], page)]
                semantic_group = parent.role in {'shared_caption_panels', 'shared_axis_panels'}
                if (len(labels) >= 2 or semantic_group) and not panel_label_conflict([parent], document, captions):
                    absorbed = True
                    break
        if not absorbed:
            result.append(child)
    return attach_top_series_legends(result, captions, document)


def recover_native_interface_figures(objects, document):
    """Recover UI panels represented as native field text plus a small icon."""
    import re
    pages = {p.number: p for p in document.pages}
    recovered = []
    for icon in objects:
        if icon.kind != 'figure' or icon.bbox[2]-icon.bbox[0] > icon.page_width*.12:
            continue
        page = pages[icon.page_number]
        labels = [(m.group(1).lower(), l) for l in panel_label_lines(page, objects)
                  if (m := _panel_match(l.text))]
        for tag, a in labels:
            if tag != 'a' or not icon.bbox[3] < a.bbox[1] <= icon.bbox[3]+240:
                continue
            following = [b for t,b in labels if t == 'b' and 20 < b.bbox[1]-a.bbox[3] < 220]
            for b in following:
                peers = [o for o in objects if o.kind == 'figure' and o is not icon
                         and o.page_number == icon.page_number
                         and a.bbox[1]-5 <= o.bbox[1] <= a.bbox[3]+30
                         and b.bbox[1]-25 <= o.bbox[3] <= b.bbox[3]+5
                         and o.bbox[2]-o.bbox[0] >= icon.page_width*.45]
                if len(peers) != 1:
                    continue
                peer = peers[0]
                lines = [l for l in page.lines if icon.bbox[1]-8 <= l.bbox[1] < a.bbox[1]-5
                         and peer.bbox[0]-5 <= l.bbox[0] and l.bbox[2] <= peer.bbox[2]+5]
                fields = [l for l in lines if re.fullmatch(r'[A-Za-z][A-Za-z /]{1,24}:',l.text.strip())]
                rows = {round(l.bbox[1]/5) for l in fields if any(
                    r is not l and abs(r.bbox[1]-l.bbox[1]) <= 4
                    and abs(r.bbox[0]-l.bbox[0]) >= 60 for r in fields)}
                if len(fields) < 4 or len(rows) < 2:
                    continue
                titles = [o for o in objects if o.kind == 'figure_caption'
                          and o.page_number == icon.page_number
                          and 0 <= o.bbox[1]-b.bbox[3] <= 45 and _matches(peer, o)]
                if not titles:
                    continue
                box = union([icon.bbox,peer.bbox]+[l.bbox for l in lines])
                if any(o.kind.endswith('_caption') and o.page_number == icon.page_number
                       and box[1] < o.bbox[1] < box[3] for o in objects):
                    continue
                recovered.append(replace(peer,bbox=box,role='captioned_interface'))
    return [o for o in objects if not (o.kind in {'figure','table'} and any(
        p.page_number == o.page_number and containment(o.bbox,p.bbox) >= .93 for p in recovered))] + recovered


def _declared_panel_letters(page, captions=()):
    """Panel declarations belong to their own title, with every title a boundary."""
    import re
    from .numbering import normalize_text
    if captions:
        sources = [(c.bbox, c.text) for c in captions if c.page_number == page.number]
    else:
        ordered = sorted(page.lines, key=lambda line:(line.bbox[1],line.bbox[0]))
        sources = []
        for i, first in enumerate(ordered):
            if not re.match(r'^(?:图|Figure|Fig\.?)\s*[A-Z]?\d',normalize_text(first.text).strip(),re.I):
                continue
            last = first
            title = [first.text]
            for following in ordered[i+1:]:
                if following.bbox[1] < first.bbox[1]+3:
                    continue
                if following.bbox[1]-last.bbox[3] > 12 or following.bbox[1]-first.bbox[1] > 120:
                    break
                if following.bbox[2]-following.bbox[0] < page.width*.45:
                    break
                title.append(following.text)
                last = following
            sources.append((first.bbox, ' '.join(title)))
    declarations = []
    for box, text in sources:
        letters = {m.lower() for m in re.findall(r'[（(]([a-z])[）)]',text,re.I)}
        for start, stop in re.findall(r'[（(]([a-z])[）)]\s*[–—-]\s*[（(]([a-z])[）)]',text,re.I):
            letters.update(chr(i) for i in range(ord(start.lower()),ord(stop.lower())+1))
        declarations.append((box, letters))
    return declarations


def remove_native_label_observations(targets,document,captions=()):
    """A text-only panel mark is evidence about its body, not another body.

    Keep genuine vector/raster ink, other content and ambiguous owners. Native
    observations are discarded only when a distinct physical panel owns all
    their label text; the original native lines remain the panel evidence.
    """
    from .object_identity import coverage
    pages={p.number:p for p in document.pages};result=[]
    for obj in targets:
        if obj.role!='native_figure':result.append(obj);continue
        page=pages[obj.page_number]
        lines=[l for l in page.lines if l.source=='native' and l.text.strip()
               and containment(l.bbox,obj.bbox)>=.85]
        if (not lines or any(not _panel_match(l.text) for l in lines)
                or obj.bbox[3]-obj.bbox[1]>max(l.bbox[3]-l.bbox[1] for l in lines)*2.5):
            result.append(obj);continue
        tag_values={_panel_match(l.text).group(1).lower() for l in lines}
        if len(tag_values)!=1:result.append(obj);continue
        box=union([l.bbox for l in lines]);x=(box[0]+box[2])/2
        owners=[]
        for parent in targets:
            if (parent is obj or parent.kind!='figure' or parent.role.startswith('native_')
                    or parent.page_number!=obj.page_number):continue
            for body in parent.panel_boxes or (parent.bbox,):
                if (body[0]-5<=x<=body[2]+5
                        and -3<=box[1]-body[3]<=35
                        and body[3]-body[1]>(box[3]-box[1])*3
                        and coverage(body,page.images+page.graphics)>=.7):
                    owners.append(body)
        if len(set(owners))!=1 or any(axis_unit(l,targets,page) for l in lines):
            result.append(obj);continue
        unowned=[ink for ink in page.images+page.graphics
                 if min(ink[2],obj.bbox[2])>max(ink[0],obj.bbox[0])
                 and min(ink[3],obj.bbox[3])>max(ink[1],obj.bbox[1])
                 and containment(ink,owners[0])<.93]
        if unowned or coverage(obj.bbox,page.images+page.graphics)>=.2:
            # A separate small graphic remains independent, even when it sits
            # within a glyph. Only duplicate whole-strip placements or blank
            # boundary overlap can be explained by the text-only observation.
            independent=[ink for ink in unowned if containment(ink,obj.bbox)>=.93
                         and not (containment(obj.bbox,ink)>=.85 and containment(ink,obj.bbox)>=.85)]
            from .native_label_carriers import native_text_only
            if independent or not native_text_only(document,page,obj.bbox,lines):
                result.append(obj)
    return result


def panel_owner_rank(obj, targets, candidates, x, y, above, label_box=None):
    """Rank real panel bounds, never the blank corners of a merged envelope."""
    boxes = [b for b in (obj.panel_boxes or (obj.bbox,))
             if b[0]-15 <= x <= b[2]+15
             and b[1]-15 <= (label_box[3] if label_box else y)
             and y <= b[3]+65]
    ranks = []
    for box in boxes:
        inside = box[1] <= y <= box[3]
        preferred = y < box[1] if above else y > box[3]
        wrong_edge = inside and (box[3]-y <= 15 if above else y-box[1] <= 15)
        style_neighbour = any(
            b[0]-15 <= x <= b[2]+15
            and 0 < (b[1]-y if above else y-b[3]) <= 20
            for i in candidates for b in (targets[i].panel_boxes or (targets[i].bbox,)))
        side = 2 if wrong_edge and style_neighbour else 0 if inside else 1 if preferred else 2
        ranks.append((side, max(box[1]-y,y-box[3],0), abs(x-(box[0]+box[2])/2)))
    return min(ranks, default=(3, float('inf'), float('inf')))


def labelled_grid_with_single_typo(targets, captions, document):
    """One duplicated middle letter in a complete grid is not a new figure.

    Require a full aligned grid, one outer title, a contiguous expected letter
    sequence with exactly one adjacent-letter typo, and no restarted (a).
    """
    from collections import Counter
    from .graphic_context import _detached_sentence
    import re
    pages = {p.number:p for p in document.pages}
    targets = list(targets)
    for caption in captions:
        if caption.kind != 'figure_caption':
            continue
        boundary = max((c.bbox[3] for c in captions if c.kind == 'figure_caption'
                        and c.page_number == caption.page_number and c.bbox[3] < caption.bbox[1]),default=0)
        members = [o for o in targets if o.kind == 'figure' and o.role == 'chart_body'
                   and o.page_number == caption.page_number
                   and boundary <= o.bbox[1] < o.bbox[3] <= caption.bbox[1]]
        if len(members) < 4:
            continue
        rows = []
        for o in sorted(members,key=lambda o:(o.bbox[1],o.bbox[0])):
            row = next((r for r in rows if abs(r[0].bbox[1]-o.bbox[1]) <= 15),None)
            if row is None:
                rows.append([o])
            else:
                row.append(o)
        rows = [sorted(r,key=lambda o:o.bbox[0]) for r in rows]
        n = len(rows[0])
        if len(rows) < 2 or n < 2 or any(len(r) != n for r in rows):
            continue
        if any(not 0 <= min(b.bbox[1] for b in lower)-max(a.bbox[3] for a in upper) <= 45
               for upper,lower in zip(rows,rows[1:])):
            continue
        if any(abs(o.bbox[0]-rows[0][j].bbox[0]) > 15
               or abs(o.bbox[2]-rows[0][j].bbox[2]) > 20 for row in rows for j,o in enumerate(row)):
            continue
        if any(b.bbox[0]-a.bbox[2] > 60 for row in rows for a,b in zip(row,row[1:])):
            continue
        envelope = union([o.bbox for o in members])
        if any(c is not caption and c.kind.endswith('_caption')
               and c.page_number == caption.page_number
               and envelope[1] < c.bbox[1] < envelope[3]
               and min(c.bbox[2],envelope[2]) > max(c.bbox[0],envelope[0]) for c in captions):
            continue
        barriers = [line for upper,lower in zip(rows,rows[1:])
                    for line in pages[caption.page_number].lines
                    if max(o.bbox[3] for o in upper) <= line.bbox[1]
                    and line.bbox[3] <= min(o.bbox[1] for o in lower)
                    and min(line.bbox[2],envelope[2]) > max(line.bbox[0],envelope[0])
                    and not _panel_match(line.text)
                    and (_detached_sentence(line,pages[caption.page_number])
                         or (line.bbox[2]-line.bbox[0] >= min(o.bbox[2]-o.bbox[0] for o in members)*.75
                             and len(re.findall(r'[A-Za-z\u4e00-\u9fff]',line.text)) >= 12))]
        if barriers:
            continue
        lines = panel_label_lines(pages[caption.page_number],members,captions)
        tags = []
        for o in [o for row in rows for o in row]:
            labels = [l for l in lines if o.bbox[3]-3 <= l.bbox[1] <= o.bbox[3]+35
                      and o.bbox[0] <= (l.bbox[0]+l.bbox[2])/2 <= o.bbox[2]]
            if len(labels) != 1:
                break
            tags.append(_panel_match(labels[0].text).group(1).lower())
        expected = [chr(ord('a')+i) for i in range(len(members))]
        if len(tags) != len(expected) or tags[0] != 'a':
            continue
        mismatches = [(a,b) for a,b in zip(tags,expected) if a != b]
        counts = Counter(tags)
        if (len(mismatches) != 1 or abs(ord(mismatches[0][0])-ord(mismatches[0][1])) != 1
                or counts['a'] != 1 or sorted(counts.values()).count(2) != 1):
            continue
        combined = replace(members[0],bbox=union([o.bbox for o in members]),role='single_typo_grid')
        if not _matches(combined,caption):
            continue
        if abs((caption.bbox[0]+caption.bbox[2]-combined.bbox[0]-combined.bbox[2])/2) > max(20,(combined.bbox[2]-combined.bbox[0])*.1):
            continue
        ids = {id(o) for o in members}
        targets = [o for o in targets if id(o) not in ids]+[combined]
    return targets


def attach_top_series_legends(targets, captions, document):
    """Attach detached top legend tiles after checking their rendered colour keys."""
    from pathlib import Path
    from .graphic_context import _detached_sentence
    import re
    if not Path(document.path).is_file():
        return targets
    import pymupdf
    import numpy as np
    from .native_diagrams import coloured_series_keys
    pages = {p.number:p for p in document.pages}
    targets = list(targets)
    removed = set()
    with pymupdf.open(document.path) as pdf:
        for index,parent in enumerate(targets):
            if parent.kind != 'figure' or not any(c.kind == 'figure_caption' and _matches(parent,c) for c in captions):
                continue
            page = pages[parent.page_number]
            labels = [l for l in panel_label_lines(page,[parent],captions)
                      if parent.bbox[0]-15 <= (l.bbox[0]+l.bbox[2])/2 <= parent.bbox[2]+15
                      and parent.bbox[1] <= l.bbox[1] <= parent.bbox[3]+35]
            if len(labels) < 2 and parent.role not in {'shared_axis_panels','shared_caption_panels'}:
                continue
            pieces = [(i,o) for i,o in enumerate(targets) if i != index and i not in removed
                      and o.kind == 'figure' and o.role in {'native_figure','continuous_chart_panels','chart_body'}
                      and o.page_number == parent.page_number
                      and 0 < o.bbox[3]-o.bbox[1] <= min(48,max(32,(parent.bbox[3]-parent.bbox[1])*.12))
                      and o.bbox[2]-o.bbox[0] >= 3*(o.bbox[3]-o.bbox[1])
                      and parent.bbox[0]-5 <= o.bbox[0] < o.bbox[2] <= parent.bbox[2]+5
                      and o.bbox[1] <= parent.bbox[1]+5
                      and -20 <= parent.bbox[1]-o.bbox[3] <= 30
                      and not any(c.kind == 'figure_caption' and _matches(o,c) for c in captions)]
            if not pieces:
                continue
            box = union([o.bbox for _,o in pieces])
            if box[3]-box[1] > min(48,max(32,(parent.bbox[3]-parent.bbox[1])*.12)):
                continue
            if any(c.kind.endswith('_caption') and c.page_number == parent.page_number
                   and box[1] < c.bbox[1] < parent.bbox[1]
                   and min(c.bbox[2],parent.bbox[2]) > max(c.bbox[0],parent.bbox[0]) for c in captions):
                continue
            if any(box[3] <= line.bbox[1] and line.bbox[3] <= parent.bbox[1]
                   and min(line.bbox[2],parent.bbox[2]) > max(line.bbox[0],parent.bbox[0])
                   and not _panel_match(line.text)
                   and (_detached_sentence(line,page)
                        or (line.bbox[2]-line.bbox[0] >= (parent.bbox[2]-parent.bbox[0])*.4
                            and len(re.findall(r'[A-Za-z\u4e00-\u9fff]',line.text)) >= 12)) for line in page.lines):
                continue
            source = pdf[parent.page_number-1]
            source.set_rotation(0)
            pix = source.get_pixmap(matrix=pymupdf.Matrix(3,3),clip=pymupdf.Rect(box),colorspace=pymupdf.csRGB,alpha=False)
            rgb = np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,3)
            if coloured_series_keys(rgb):
                targets[index] = replace(parent,bbox=union([parent.bbox,box]))
                removed.update(i for i,_ in pieces)
    return [o for i,o in enumerate(targets) if i not in removed]


def reconcile_physical_rasters(targets, captions, document):
    """A physical PDF raster carrier and its parser fragments share identity.

    A carrier can be a single image or abutting original tiles. Inferred
    envelopes and tiles with empty strips cannot prove physical ownership.
    Internal caption boundaries preserve independent figure obligations.
    """
    pages = {page.number:page for page in document.pages}
    targets = list(targets)
    from .object_identity import coverage
    # One parser body can encompass several original images, each with white
    # crop padding. Keep that composite identity when reconciling native image
    # observations; a padded component must not become a competing title owner.
    for body in list(targets):
        if body.kind!='figure' or body.role!='image_body':continue
        placements=[b for b in pages[body.page_number].images if containment(b,body.bbox)>=.7]
        if len(placements)<2 or coverage(body.bbox,placements)<.9:continue
        envelope=union([body.bbox]+placements)
        if any(c.page_number==body.page_number and c.kind.endswith('_caption')
               and containment(c.bbox,envelope)>.5 for c in captions):continue
        if any(o is not body and o.kind=='figure' and not o.role.startswith('native_')
               and o.page_number==body.page_number and containment(o.bbox,envelope)>.5 for o in targets):continue
        duplicates=[o for o in targets if o.kind=='figure' and o.role=='native_figure'
                    and o.page_number==body.page_number and any(containment(o.bbox,b)>=.98
                        and containment(b,o.bbox)>=.98 for b in placements)]
        if not duplicates:continue
        gone={id(body),*(id(o) for o in duplicates)}
        targets=[o for o in targets if id(o) not in gone]+[replace(body,bbox=envelope)]
    for native in list(targets):
        if native.role not in {'native_figure','continuous_chart_panels'} or native not in targets:
            continue
        placements = pages[native.page_number].images
        single = any(containment(native.bbox,box) >= .98
                     and containment(box,native.bbox) >= .98 for box in placements)
        tiled = (native.role in {'native_figure','continuous_chart_panels'} and len(native.panel_boxes) > 1
                 and coverage(native.bbox,native.panel_boxes) >= .98
                 and all(any(containment(tile,box) >= .98 and containment(box,tile) >= .98
                             for box in placements) for tile in native.panel_boxes))
        if not (single or tiled):
            continue
        bodies = [obj for obj in targets if obj is not native
                  and obj.kind == 'figure' and obj.page_number == native.page_number
                  and not obj.role.startswith('native_')
                  and containment(obj.bbox,native.bbox) >= .93]
        if not bodies:
            continue
        internal_titles = [c for c in captions
                           if c.kind.endswith('_caption') and c.page_number == native.page_number
                           and native.bbox[1] < (c.bbox[1]+c.bbox[3])/2 < native.bbox[3]
                           and min(c.bbox[2],native.bbox[2]) > max(c.bbox[0],native.bbox[0])]
        # A title localized to one side names that independent figure, even
        # when an author exported neighbouring figures into one bitmap.
        local_titles = [c for c in captions if len(bodies) > 1
                        and c.kind == 'figure_caption' and c.page_number == native.page_number
                        and abs((c.bbox[0]+c.bbox[2]-native.bbox[0]-native.bbox[2])/2)
                            > max(20,(native.bbox[2]-native.bbox[0])*.12)
                        and any(_matches(body,c) and body.bbox[0]-5 <= c.bbox[0]
                                and c.bbox[2] <= body.bbox[2]+5 for body in bodies)]
        if internal_titles or local_titles:
            # Explicit split figures cover this bitmap's main extent. Keep
            # their separate title obligations, not an extra carrier target.
            if (len(bodies) > 1
                    and containment(native.bbox,union([body.bbox for body in bodies])) >= .7
                    and any(c.kind == 'figure_caption' and any(_matches(body,c) for body in bodies)
                            for c in internal_titles+local_titles)):
                targets = [obj for obj in targets if obj is not native]
            continue
        merged = replace(bodies[0],bbox=union([native.bbox]+[obj.bbox for obj in bodies]))
        consumed = {id(native),*(id(obj) for obj in bodies)}
        targets = [obj for obj in targets if id(obj) not in consumed]+[merged]
    return reconcile_cropped_rasters(targets, captions, document)


def _rendered_series_key_lines(page, legend, lines, path):
    """Validate raster/hatch swatches only in the space left of legend labels."""
    from pathlib import Path
    if not Path(path).is_file():
        return []
    import pymupdf
    import numpy as np
    scale = 3
    with pymupdf.open(path) as pdf:
        source = pdf[page.number-1]
        source.set_rotation(0)
        clip = pymupdf.Rect(legend.bbox) & source.rect
        if clip.is_empty:
            return []
        pix = source.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip, alpha=False)
        rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
    keyed = []
    for line in lines:
        left=max(clip.x0,line.bbox[0]-22); right=min(clip.x1,line.bbox[0]-1)
        top=max(clip.y0,line.bbox[1]); bottom=min(clip.y1,line.bbox[3])
        x1=max(0,int((left-clip.x0)*scale)); x2=min(pix.width,int((right-clip.x0)*scale))
        y1=max(0,int((top-clip.y0)*scale)); y2=min(pix.height,int((bottom-clip.y0)*scale))
        if x2<=x1 or y2<=y1:
            continue
        patch=rgb[y1:y2,x1:x2].astype('int16')
        color=patch.max(axis=2)-patch.min(axis=2)>=40
        ys,xs=np.nonzero(color)
        if (.02<=color.mean()<=.65 and len(xs)
                and xs.max()-xs.min()+1 <= (y2-y1)*1.8):
            keyed.append(line)
    return keyed


def recover_native_plot_legends(objects, document):
    """A native legend frame supplies swatch grouping missing from layout blocks."""
    from .mineru_layout import LayoutObject
    objects=list(objects); candidates=[]
    for page in document.pages:
        for box in page.graphics:
            if box[2]-box[0]<20 or box[3]-box[1]<20:
                continue
            if any(o.kind in {'figure','table'} and o.page_number==page.number
                   and containment(box,o.bbox)>=.93 for o in objects):
                continue
            lines=[l for l in page.lines if l.text.strip() and containment(l.bbox,box)>=.8]
            if len(lines)<2:
                continue
            if any(containment(box,o.bbox)>=.98 and containment(o.bbox,box)>=.98 for o in candidates):
                continue
            candidates.append(replace(LayoutObject('figure',page.number,box,'',page.width,page.height),
                                      role='native_series_legend'))
    combined=attach_plot_legends(objects+candidates,document)
    return [o for o in combined if o.role!='native_series_legend']


def reconcile_cropped_rasters(targets,captions,document):
    """Reconcile physical images partly outside a cloud parser's tight crop.

    Require actual PDF image placements, a unique overlapping cloud parent,
    bounded crop margins, and no independent caption inside the proposed body.
    A nearby nonoverlapping image remains a separate object.
    """
    from .layout_context import area
    pages={p.number:p for p in document.pages};targets=list(targets)
    for native in list(targets):
        if native not in targets or native.role!='native_figure':continue
        if not any(containment(native.bbox,b)>=.98 and containment(b,native.bbox)>=.98
                   for b in pages[native.page_number].images):continue
        candidates=[]
        for parent in targets:
            if parent.kind!='figure' or parent.role not in {'image_body','chart_body'} or parent.page_number!=native.page_number:continue
            a=containment(native.bbox,parent.bbox);b=containment(parent.bbox,native.bbox)
            width=parent.bbox[2]-parent.bbox[0];height=parent.bbox[3]-parent.bbox[1]
            padding=(min(40,width*.10),min(28,height*.14))
            padded=(parent.bbox[0]-padding[0],parent.bbox[1]-padding[1],parent.bbox[2]+padding[0],parent.bbox[3]+padding[1])
            same_body=a>=.6 and b>=.6
            cropped_piece=(a>=.6 and area(native.bbox)<=area(parent.bbox)*.35
                and containment(native.bbox,padded)>=.95)
            # Small size and a nearby title do not authenticate component
            # ownership. If most visible ink is outside the parser body,
            # preserve the native object until physical containment/lineage
            # supplies stronger proof; padding alone cannot invent a parent.
            if not (same_body or cropped_piece):continue
            envelope=union([native.bbox,parent.bbox])
            internal=[c for c in captions if c.kind.endswith('_caption') and c.page_number==parent.page_number
                and envelope[1]+3<(c.bbox[1]+c.bbox[3])/2<envelope[3]-3
                and min(c.bbox[2],envelope[2])>max(c.bbox[0],envelope[0])]
            if internal:continue
            if any(c.kind=='figure_caption' and c.page_number==native.page_number and _matches(native,c)
                   and c.bbox[2]-c.bbox[0]<=(native.bbox[2]-native.bbox[0])*1.15
                   and abs((c.bbox[0]+c.bbox[2]-native.bbox[0]-native.bbox[2])/2)<10
                   and not _matches(parent,c) for c in captions):continue
            candidates.append(parent)
        if len(candidates)!=1:continue
        parent=candidates[0];merged=replace(parent,bbox=union([native.bbox,parent.bbox]))
        targets=[o for o in targets if o is not native and o is not parent]+[merged]
    return targets
