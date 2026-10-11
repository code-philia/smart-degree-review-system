"""Group adjacent bilingual titles of one physical figure or table."""
from dataclasses import replace
import re
from .numbering import normalize_text, caption_match


def _language(label):
    return 'zh' if normalize_text(label.line.text).lstrip().startswith(('图','表')) else 'en'


def _full_caption(label,lines):
    """Use native paragraph membership to include title continuations only."""
    first=label.line
    if first.block_id is None:return label
    joined=[first]
    rows=sorted((l for l in lines if l.page_number==first.page_number and l.bbox[1]>first.bbox[1]),key=lambda l:(l.bbox[1],l.bbox[0]))
    for row in rows:
        previous=joined[-1]
        h=first.bbox[3]-first.bbox[1];other_h=row.bbox[3]-row.bbox[1]
        if row.bbox[1]-previous.bbox[3]>max(15,h*1.5):break
        if caption_match(row.text,'figure') or caption_match(row.text,'table'):break
        if row.block_id!=first.block_id or row.source!=first.source:break
        aligned=(abs(row.bbox[0]-first.bbox[0])<=h or
                 abs((row.bbox[0]+row.bbox[2]-first.bbox[0]-first.bbox[2])/2)<=h*1.5)
        if not aligned or not .9*h<=other_h<=1.1*h:break
        joined.append(row)
    if len(joined)==1:return label
    boxes=[l.bbox for l in joined]
    box=(min(b[0] for b in boxes),first.bbox[1],max(b[2] for b in boxes),max(b[3] for b in boxes))
    return replace(label,line=replace(first,text='\n'.join(l.text for l in joined),bbox=box))


def _continuation_bridge(a, b, lines):
    """Centred title wrapping can create one PDF text block per physical row."""
    top,bottom=sorted((a.line,b.line),key=lambda l:l.bbox[1])
    h=top.bbox[3]-top.bbox[1]
    if bottom.bbox[1]-top.bbox[3]>120:return False
    rows=sorted((l for l in lines if l.page_number==top.page_number and top.bbox[3]<=l.bbox[1] and l.bbox[3]<=bottom.bbox[1]),key=lambda l:l.bbox[1])
    if not rows:return False
    previous=top
    centre=(top.bbox[0]+top.bbox[2])/2
    for row in rows:
        if (row.bbox[1]-previous.bbox[3]>max(12,h) or row.source!=top.source
                or abs((row.bbox[0]+row.bbox[2])/2-centre)>h*1.5
                or not .85*h<=row.bbox[3]-row.bbox[1]<=1.15*h
                or caption_match(row.text,'figure') or caption_match(row.text,'table')):
            return False
        previous=row
    return bottom.bbox[1]-previous.bbox[3]<=max(12,h)


def _same_bilingual_number(a, b):
    if a.number == b.number:
        return True
    if _language(a) == _language(b):
        return False
    zh, en = (a, b) if _language(a) == 'zh' else (b, a)
    # A repeated chapter prefix printed as "Figure 2-2.3" may be the
    # adjacent translation of "图2.3". Do not shorten legitimate dotted
    # three-component IDs or arbitrary mismatches. Independent typography
    # and the ordinary same-page/overlap/wrapping checks must also agree.
    match = next((caption_match(en.line.text, kind) for kind in ('figure','table')
                  if caption_match(en.line.text, kind)), None)
    raw = match.group('number') if match else ''
    repeated = re.fullmatch(r'([0-9]+)-\1\.([0-9]+)', raw)
    if not repeated or zh.number != f'{repeated[1]}.{repeated[2]}':
        return False
    left, right = zh.line, en.line
    return bool(left.source == right.source == 'native'
                and left.bold and right.bold and left.font_size and right.font_size
                and abs(left.font_size-right.font_size) <= left.font_size*.1)


def _pair_distance(a, b, lines=(), document=None):
    if ((a.scope, a.line.page_number) != (b.scope, b.line.page_number)
            or not _same_bilingual_number(a, b)):
        return None
    if _language(a) == _language(b):
        return None
    if a.number != b.number:
        if document is None:
            return None
        page = next(p for p in document.pages if p.number == a.line.page_number)
        upper, lower = sorted((a.line,b.line),key=lambda l:l.bbox[1])
        for box in (*page.images,*page.tables,*getattr(page,'graphics',())):
            overlap = min(box[2],upper.bbox[2],lower.bbox[2])-max(box[0],upper.bbox[0],lower.bbox[0])
            # A separate graphic between two labels is a physical boundary;
            # whole-page canvases and objects outside the title column are not.
            if (box[2]-box[0] >= 30 and box[3]-box[1] >= 4 and overlap > 0
                    and upper.bbox[3] <= box[1]+.5
                    and box[3] <= lower.bbox[1]+.5):
                return None
    x1,y1,x2,y2 = a.line.bbox
    bx1,by1,bx2,by2 = b.line.bbox
    overlap = max(0,min(x2,bx2)-max(x1,bx1))
    if overlap < min(x2-x1,bx2-bx1)*.5:
        return None
    gap = max(y1-by2,by1-y2,0)
    if gap > max(18,2*min(y2-y1,by2-by1)) and not _continuation_bridge(a,b,lines):
        return None
    return gap + abs((x1+x2-bx1-bx2)/2)*.01


def caption_groups(labels,lines=(),document=None):
    """Keep other pages, scopes, numbers and separated objects independent."""
    full=[_full_caption(label,lines) for label in labels]
    used=set()
    for i, label in enumerate(labels):
        if i in used:
            continue
        candidates=[]
        for j in range(i+1,len(labels)):
            if j in used:
                continue
            distance=_pair_distance(full[i],full[j],lines,document)
            if distance is not None:
                candidates.append((distance,j))
        group=[label]
        if candidates:
            _,j=min(candidates)
            used.add(j);group=[full[i],full[j]]
            if group[0].number != group[1].number:
                group.sort(key=lambda item: _language(item) != 'zh')
        yield group


def bilingual_alias_kind(line,page,objects=()):
    """One physical visual cannot acquire a second type from its translation.

    A nearby Chinese title, matching number and native title typography must
    agree with independent body geometry. Without that evidence preserve both
    labels so uncertainty cannot silently exempt an actual object.
    """
    from .mineru_layout import LayoutObject
    from .caption_rules import _matches
    from .numbering import normalize_label
    text=normalize_text(line.text).strip()
    printed=next((kind for kind in ('figure','table') if caption_match(text,kind)),None)
    if not printed or text.startswith(('图','表')):return None
    match=caption_match(text,printed);canonical='table' if printed=='figure' else 'figure'
    for peer in page.lines:
        if not normalize_text(peer.text).lstrip().startswith('表' if canonical=='table' else '图'):continue
        paired=caption_match(normalize_text(peer.text),canonical)
        if not paired or normalize_label(paired.group('number'))!=normalize_label(match.group('number')):continue
        if not (line.bold and peer.bold):continue
        if line.font_size and peer.font_size and abs(line.font_size-peer.font_size)>peer.font_size*.1:continue
        a=line.bbox;b=peer.bbox;overlap=max(0,min(a[2],b[2])-max(a[0],b[0]))
        gap=max(a[1]-b[3],b[1]-a[3],0)
        if gap>max(18,min(a[3]-a[1],b[3]-b[1])*2) or overlap<min(a[2]-a[0],b[2]-b[0])*.5:continue
        title=LayoutObject(canonical+'_caption',page.number,peer.bbox,peer.text,page.width,page.height)
        boxes=page.tables if canonical=='table' else page.images
        physical=[LayoutObject(canonical,page.number,box,'',page.width,page.height) for box in boxes]
        physical.extend(o for o in objects or () if o.kind==canonical and o.page_number==page.number)
        confirmed=[o for o in physical if _matches(o,title)]
        if not confirmed:continue
        # Independent visuals beside the title are separate objects; proximity
        # or matching numbers alone cannot merge them.
        independent=[o for o in objects or () if o.kind==printed and o.page_number==page.number
                     and _matches(o,LayoutObject(printed+'_caption',page.number,line.bbox,line.text,page.width,page.height))
                     and not any(_contained(o.bbox,p.bbox)>.9 for p in confirmed)]
        if not independent:return canonical
    return None


def _contained(a,b):
    return max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))/max(1,(a[2]-a[0])*(a[3]-a[1]))


def reconcile_caption_bounds(objects,document):
    """An independently styled panel label marks the end of a title region.

    Preserve multi-line title prose. Only trim a parser rectangle when native
    caption identity and a differently styled standalone panel row prove that
    the parser has extended it into the visual itself.
    """
    import re
    from .caption_context import contextual_caption
    from .numbering import normalize_label
    pages={p.number:p for p in document.pages};result=[]
    panel=re.compile(r'^[（(]{1,2}[a-z][）)]{1,2}(?:\s|[\u4e00-\u9fff])',re.I)
    for obj in objects:
        if not obj.kind.endswith('_caption'):
            result.append(obj);continue
        kind=obj.kind.removesuffix('_caption');page=pages[obj.page_number]
        declared=caption_match(obj.text,kind)
        anchors=[l for l in page.lines if l.source=='native' and l.bold and l.font_size
                 and _contained(l.bbox,obj.bbox)>=.85 and (m:=contextual_caption(l,page,kind,objects))
                 and declared and normalize_label(m.group('number'))==normalize_label(declared.group('number'))]
        markers=[l for l in page.lines if l.source=='native' and panel.match(normalize_text(l.text).strip())
                 and _contained(l.bbox,obj.bbox)>=.65
                 and any(l.bbox[1]>=a.bbox[3] and l.font_size
                         and (abs(l.font_size-a.font_size)>a.font_size*.1 or l.bold!=a.bold) for a in anchors)]
        if markers:
            end=min(l.bbox[1] for l in markers)-.5
            if end>obj.bbox[1]:obj=replace(obj,bbox=(obj.bbox[0],obj.bbox[1],obj.bbox[2],end))
        result.append(obj)
    return result
