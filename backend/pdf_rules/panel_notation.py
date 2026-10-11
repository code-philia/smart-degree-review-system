"""Canonicalize panel notation only when the shared title declares its series."""
import re
from dataclasses import replace

ROMANS=('i','ii','iii','iv','v','vi','vii','viii','ix','x')
MARKER=re.compile(r'^\s*[（(](?P<roman>i|ii|iii|iv|v|vi|vii|viii|ix|x)[）)]',re.I)
DECLARED=re.compile(r'[（(](i|ii|iii|iv|v|vi|vii|viii|ix|x)[）)]',re.I)
PREFIXED=re.compile(r'^\s*(?:图|Figure|Fig\.?)\s*[（(]([a-z])[）)]',re.I)


def canonical_panel_line(line,page,captions):
    prefixed=PREFIXED.match(line.text)
    if prefixed:
        # A type word is a panel label only when its common title explicitly
        # describes multiple lettered panels; the object reconciler supplies
        # physical ownership, caption boundaries and restart checks.
        following=[caption for caption in captions
                   if caption.kind=='figure_caption' and caption.page_number==page.number
                   and caption.bbox[1]>line.bbox[3]
                   and min(caption.bbox[2],line.bbox[2])-max(caption.bbox[0],line.bbox[0])
                       >=.25*min(caption.bbox[2]-caption.bbox[0],line.bbox[2]-line.bbox[0])]
        if following:
            # The nearest title is a boundary; a later title cannot borrow a
            # panel that belongs to an independently titled earlier figure.
            caption=min(following,key=lambda c:c.bbox[1])
            tags={v.lower() for v in re.findall(r'[（(]([a-z])[）)]',caption.text,re.I)}
            if len(tags)>=2 and prefixed.group(1).lower() in tags:
                return replace(line,text='('+prefixed.group(1).lower()+')'+line.text[prefixed.end():])
        return line
    match=MARKER.match(line.text)
    if not match:return line
    for caption in captions:
        if caption.kind!='figure_caption' or caption.page_number!=page.number:continue
        tags={v.lower() for v in DECLARED.findall(caption.text)}
        positions=sorted(ROMANS.index(v) for v in tags)
        if len(positions)<2 or positions!=list(range(len(positions))):continue
        roman=match.group('roman').lower()
        if roman not in tags:continue
        letter=chr(ord('a')+ROMANS.index(roman))
        return replace(line,text='('+letter+')'+line.text[match.end():])
    return line


NUMERIC_MARKER=re.compile(r'^\s*[（(](\d{1,2})[）)]')


def numeric_panel_line(line,page,captions,targets):
    """Canonicalize 1..N only with distinct physical panels and one outer title.

    Numerical prose, algorithm steps and cells in one table cannot create a
    panel namespace. Repeated IDs, gaps, independent titles and intervening
    body paragraphs keep their independent title obligations.
    """
    from .numbering import normalize_text
    from .layout_context import union
    from .object_identity import coverage
    from .caption_rules import _matches
    match=NUMERIC_MARKER.match(normalize_text(line.text))
    if not match or not 1<=int(match.group(1))<=26:
        return line
    physical=[]
    for obj in targets:
        if obj.kind not in {'figure','table'} or obj.page_number!=page.number:
            continue
        regions=page.images+page.graphics if obj.kind=='figure' else page.tables+page.graphics
        for box in obj.panel_boxes or (obj.bbox,):
            if coverage(box,regions)>=.8:
                physical.append(replace(obj,bbox=box,panel_boxes=()))
    if len(physical)<2:
        return line
    numbered=[(candidate,int(m.group(1))) for candidate in page.lines
              if (m:=NUMERIC_MARKER.match(normalize_text(candidate.text)))
              and 1<=int(m.group(1))<=26]
    titles=[c for c in captions if c.page_number==page.number and c.kind.endswith('_caption')]
    for caption in titles:
        kind=caption.kind.removesuffix('_caption')
        for above in (False,True):
            if above:
                low=caption.bbox[3]
                high=min((c.bbox[1] for c in titles if c.bbox[1]>low+2),default=page.height)
            else:
                low=max((c.bbox[3] for c in titles if c.bbox[3]<caption.bbox[1]-2),default=0)
                high=caption.bbox[1]
            candidates=[(candidate,number) for candidate,number in numbered
                        if low<=candidate.bbox[1] and candidate.bbox[3]<=high]
            if not any(candidate==line for candidate,_ in candidates):
                continue
            owners=[]
            for candidate,number in candidates:
                x=(candidate.bbox[0]+candidate.bbox[2])/2
                choices=[o for o in physical if o.kind==kind
                         and o.bbox[0]-15<=x<=o.bbox[2]+15
                         and o.bbox[1]-15<=candidate.bbox[3]
                         and candidate.bbox[1]<=o.bbox[3]+35]
                if not choices:
                    continue
                owner=min(choices,key=lambda o:(max(o.bbox[1]-candidate.bbox[3],candidate.bbox[1]-o.bbox[3],0),
                                                abs(x-(o.bbox[0]+o.bbox[2])/2)))
                owners.append((candidate,number,owner))
            numbers=[number for _,number,_ in owners]
            if len(numbers)<2 or sorted(numbers)!=list(range(1,len(numbers)+1)):
                continue
            if len({o.bbox for _,_,o in owners})!=len(owners):
                continue
            box=union([o.bbox for _,_,o in owners])
            parent=replace(owners[0][2],bbox=box)
            if not _matches(parent,caption):
                continue
            width=box[2]-box[0]
            if abs((box[0]+box[2]-caption.bbox[0]-caption.bbox[2])/2)>width*.12:
                continue
            if any(c is not caption and box[1]+2<c.bbox[1]<box[3]-2
                   and min(c.bbox[2],box[2])>max(c.bbox[0],box[0]) for c in titles):
                continue
            if any(candidate not in [l for l,_,_ in owners]
                   and box[1]<candidate.bbox[1]<candidate.bbox[3]<box[3]
                   and not any(o.bbox[0]-2<=candidate.bbox[0] and candidate.bbox[2]<=o.bbox[2]+2
                               and o.bbox[1]-2<=candidate.bbox[1] and candidate.bbox[3]<=o.bbox[3]+2
                               for _,_,o in owners)
                   and len(re.findall(r'[A-Za-z\u4e00-\u9fff]',candidate.text))>=12
                   and candidate.bbox[2]-candidate.bbox[0]>=min(o.bbox[2]-o.bbox[0] for _,_,o in owners)*.75
                   for candidate in page.lines):
                continue
            if any(candidate==line for candidate,_,_ in owners):
                value=normalize_text(line.text)
                return replace(line,text='('+chr(ord('a')+int(match.group(1))-1)+')'+value[match.end():])
    return line
