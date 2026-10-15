"""Caption identity uses page typography and paragraph continuity, not verbs alone."""
import re
from collections import Counter
from .numbering import FIGURE_CAPTION,TABLE_CAPTION,normalize_text,normalize_label,caption_match

def _body_lines(page):
    return [l for l in page.lines if abs(l.direction[0])>.9
            and l.bbox[2]-l.bbox[0]>page.width*.6
            and len(re.findall(r'[A-Za-z\u4e00-\u9fff]',l.text))>=12
            and page.height*.09<l.bbox[1]<page.height*.92]

def body_font(page):
    sizes=Counter()
    for l in _body_lines(page):
        value=getattr(l,'font_size',None)
        if value and not (FIGURE_CAPTION.search(normalize_text(l.text)) or TABLE_CAPTION.search(normalize_text(l.text))):
            sizes[round(value,1)]+=len(l.text)
    return sizes.most_common(1)[0][0] if sizes else None

def _isolated_native_bold_title(line,page,kind):
    """A separate bold title below its native visual may use the body size.

    Require actual visual geometry, title alignment and paragraph separation;
    a bold citation attached to following prose keeps its body identity.
    """
    if (line.source!='native' or not line.bold or not line.font_size
            or abs(line.direction[0])<.9 or page.display_rotation):return False
    pattern=FIGURE_CAPTION if kind=='figure' else TABLE_CAPTION
    declared=pattern.match(normalize_text(line.text))
    if not declared or len(re.findall(r'[A-Za-z\u4e00-\u9fff]',normalize_text(line.text)[declared.end('number'):]))<3:return False
    tail=normalize_text(line.text)[declared.end('number'):].strip()
    # A relative subject followed by a finite enumeration is a citation,
    # even when somebody applies bold title-sized formatting to that prose.
    if re.match(r'^所.{0,40}(?:依次为|分别为|包括|包含|采用|是)',tail):return False
    # 'Visible/in-use satellite counts' is a noun comparison, although the
    # shared caption grammar treats a leading 'visible' as a prose predicate.
    # A slash elsewhere in a finite sentence cannot override that grammar.
    nominal_pair=bool(re.fullmatch(
        r'可见\s*/\s*在用\s*(?:[A-Z][A-Z0-9-]{0,11}\s*)?卫星(?:数量|数目)?(?:对比|比较|分布)',tail))
    if not caption_match(normalize_text(line.text),kind) and not nominal_pair:return False
    h=max(1,line.bbox[3]-line.bbox[1])
    chinese=normalize_text(line.text).lstrip().startswith(('图','表'))
    for peer in page.lines:
        other=pattern.match(normalize_text(peer.text))
        if (peer!=line and peer.source=='native' and peer.bold and other
                and normalize_text(peer.text).lstrip().startswith(('图','表'))!=chinese
                and -5<=peer.bbox[1]-line.bbox[3]<=60
                and normalize_label(other.group('number'))!=normalize_label(declared.group('number'))):return False
    boxes=(*page.images,*getattr(page,'graphics',())) if kind=='figure' else page.tables
    nearby=[b for b in boxes if b[2]-b[0]>=30 and b[3]-b[1]>=15
            and 0<=line.bbox[1]-b[3]<=65
            and min(b[2],line.bbox[2])-max(b[0],line.bbox[0])>0]
    if not nearby:return False
    end=max(b[3] for b in nearby);row=[b for b in nearby if end-b[3]<=15]
    left=min(b[0] for b in row);right=max(b[2] for b in row)
    if abs((line.bbox[0]+line.bbox[2]-left-right)/2)>max(h*1.8,(right-left)*.08):return False
    prose=[l for l in _body_lines(page) if l.source=='native' and not l.bold
           and not any(p.search(normalize_text(l.text)) for p in (FIGURE_CAPTION,TABLE_CAPTION))]
    typical=Counter(round(l.font_size,1) for l in prose if l.font_size)
    if typical and line.font_size>typical.most_common(1)[0][0]*1.05:return False
    if any(end+2<l.bbox[1]<line.bbox[1] and len(l.text.strip())>=25
           and l.bbox[2]-l.bbox[0]>page.width*.45 for l in prose):return False
    if any(0<=l.bbox[1]-line.bbox[3]<h*1.5 for l in prose):return False
    if any(l!=line and line.block_id is not None and l.block_id==line.block_id
           and not l.bold and len(l.text.strip())>=12
           and 0<=l.bbox[1]-line.bbox[3]<=h*2 for l in page.lines):return False
    return True


def paragraph_start(line,page):
    if any(_isolated_native_bold_title(line,page,k) for k in ('figure','table')):return False
    h=max(1,line.bbox[3]-line.bbox[1]);body=_body_lines(page)
    if not body or line.bbox[2]-line.bbox[0]<page.width*.6:return False
    left=min(l.bbox[0] for l in body);right=sorted(l.bbox[2] for l in body)[len(body)//2]
    indent=line.bbox[0]-left
    right_inset=right-line.bbox[2]
    # A long centred title may have the same left inset as a paragraph. On
    # graphics-only pages table headers also make the inferred body font noisy.
    # Apply this only where there is no independent wide prose. Table headers
    # are geometry evidence, not a paragraph font/margin sample.
    def in_table(candidate):
        box=candidate.bbox
        return any(max(0,min(box[2],t[2])-max(box[0],t[0]))
                   *max(0,min(box[3],t[3])-max(box[1],t[1]))
                   >=(box[2]-box[0])*(box[3]-box[1])*.8 for t in page.tables)
    prose=[l for l in body if not in_table(l)
           and not (getattr(l,'bold',False) and any(
               caption_match(normalize_text(l.text),kind) for kind in ('figure','table')))]
    if (not prose and getattr(line,'bold',False) and min(indent,right_inset)>=h
            and abs(indent-right_inset)<=h*.75 and visual_support(line,page)
            and any(caption_match(normalize_text(line.text),kind) for kind in ('figure','table'))):return False
    font=getattr(line,'font_size',None);typical=body_font(page)
    if font and typical and font<typical*.95 and getattr(line,'bold',False):return False
    body_style=bool(font and typical and abs(font-typical)<=typical*.05 and not getattr(line,'bold',False))
    following=[l for l in body if 0<=l.bbox[1]-line.bbox[3]<=h*1.1
               and abs(l.bbox[0]-left)<=h*.5
               and .85<=(l.bbox[3]-l.bbox[1])/h<=1.2]
    # Standard first-line indentation followed by a full-width body line.
    return bool((following or body_style or line.text.rstrip().endswith(("。",".","!","?","！","？")))
                and h*1.3<=indent<=h*2.8
                and abs(line.bbox[2]-right)<=h*1.5)


def paragraph_continuation(line,page):
    """Recognize a wrapped body sentence from its layout and body typography.

    A caption-sized bold line or a line next to an actual visual retains its
    caption identity. No particular sentence wording or document ID is needed.
    """
    font=getattr(line,'font_size',None)
    typical=body_font(page)
    if (not font or not typical or abs(font-typical)>typical*.05
            or getattr(line,'bold',False)
            or line.bbox[2]-line.bbox[0]<page.width*.6):return False
    h=max(1,line.bbox[3]-line.bbox[1])
    nearby_visual=visual_support(line,page)
    for other in _body_lines(page):
        if other==line or getattr(other,'bold',False):continue
        other_font=getattr(other,'font_size',None)
        if not other_font or abs(other_font-font)>font*.05:continue
        # Neighbouring numbered titles do not establish a prose paragraph.
        if any(pattern.search(normalize_text(other.text)) for pattern in (FIGURE_CAPTION,TABLE_CAPTION)):continue
        # A sentence ending in an explicit citation cue continues into the
        # next aligned line even when the paragraph lies between two tables.
        if nearby_visual and not re.search(r'(?:如|见|汇总于|列于|示于|对应于?)\s*$',normalize_text(other.text)):continue
        gap=line.bbox[1]-other.bbox[3]
        aligned=abs(line.bbox[0]-other.bbox[0])<=h*.5
        follows_first_line=(h*.8<=other.bbox[0]-line.bbox[0]<=h*2.8
                            and paragraph_start(other,page))
        if (0<=gap<=h and (aligned or follows_first_line)
                and abs(line.bbox[2]-other.bbox[2])<=h*1.5):return True
    return False

def visual_support(line,page):
    for box in (*page.images,*page.tables,*getattr(page,'graphics',())):
        overlap=min(box[2],line.bbox[2])-max(box[0],line.bbox[0])
        if box[2]-box[0]<30 or box[3]-box[1]<15 or overlap<=0:continue
        if (0<=line.bbox[1]-box[3]<=65 or 0<=box[1]-line.bbox[3]<=65):return True
    return False

def _styled_bilingual_title(line, page, kind, match, objects):
    """Native title typography, translation and visual prove identity together.

    Full-width descriptive sentences are ordinary academic titles. A prose
    predicate alone cannot turn such a title into its own body reference.
    Require the same numbered opposite-language styled title immediately
    after the native title block, plus an independently located visual.
    """
    if (line.source != 'native' or not line.bold or not line.font_size
            or abs(line.direction[0]) < .9):
        return False
    h = max(1, line.bbox[3]-line.bbox[1])
    block = [line]
    if line.block_id is not None:
        for row in sorted(page.lines, key=lambda l: (l.bbox[1],l.bbox[0])):
            if row.bbox[1] <= line.bbox[1]:
                continue
            previous = block[-1]
            if (row.block_id != line.block_id or row.source != 'native'
                    or not row.bold or not row.font_size
                    or abs(row.font_size-line.font_size) > line.font_size*.1
                    or row.bbox[1]-previous.bbox[3] > max(15,h*1.5)):
                continue
            if any(p.search(normalize_text(row.text)) for p in (FIGURE_CAPTION,TABLE_CAPTION)):
                break
            block.append(row)
    # Sample independent body prose, rather than long title continuations.
    prose = Counter(round(l.font_size,1) for l in _body_lines(page)
                    if l.source == 'native' and not l.bold and l.font_size)
    typical = prose.most_common(1)[0][0] if prose else None
    if typical and line.font_size >= typical*.95:
        return False
    box = (min(l.bbox[0] for l in block),line.bbox[1],
           max(l.bbox[2] for l in block),max(l.bbox[3] for l in block))
    from .mineru_layout import LayoutObject
    from .caption_rules import _matches
    title = LayoutObject(kind+'_caption',page.number,box,line.text,page.width,page.height)
    native = page.images if kind == 'figure' else page.tables
    physical = [LayoutObject(kind,page.number,b,'',page.width,page.height) for b in native]
    physical.extend(o for o in objects or () if o.kind == kind and o.page_number == page.number)
    if not any(_matches(o,title) for o in physical):
        return False
    chinese = normalize_text(line.text).lstrip().startswith(('图','表'))
    for peer in page.lines:
        text = normalize_text(peer.text)
        pattern = FIGURE_CAPTION if kind == 'figure' else TABLE_CAPTION
        translated = pattern.search(text)
        if (peer == line or peer.source != 'native' or not peer.bold or not peer.font_size
                or abs(peer.font_size-line.font_size) > line.font_size*.1
                or not translated
                or normalize_label(translated.group('number')) != normalize_label(match.group('number'))
                or text.lstrip().startswith(('图','表')) == chinese):
            continue
        a,b = box,peer.bbox
        gap = max(a[1]-b[3],b[1]-a[3],0)
        overlap = max(0,min(a[2],b[2])-max(a[0],b[0]))
        if gap <= max(18,h*2) and overlap >= min(a[2]-a[0],b[2]-b[0])*.5:
            return True
    return False


def contextual_caption(line,page,kind,objects=()):
    text=normalize_text(line.text)
    from .caption_identity import bilingual_alias_kind
    alias=bilingual_alias_kind(line,page,objects)
    if alias and alias!=kind:return None
    printed=('table' if kind=='figure' else 'figure') if alias else kind
    pattern=FIGURE_CAPTION if printed=='figure' else TABLE_CAPTION
    match=pattern.search(text)
    if not match:return None
    from .native_caption_blocks import native_caption_block
    if native_caption_block(line,page,printed,objects):return match
    usual=caption_match(text,printed)
    tail=text[match.end('number'):].strip()
    # "用于..." can start a noun title as well as a body statement. On a
    # graphics-only page, a separate compact, smaller title of this same object
    # establishes the typography needed to recognize its larger prose sentence.
    font=getattr(line,'font_size',None)
    if (tail.startswith('用于') and re.search(r'[。；;]',tail) and font
            and not getattr(line,'bold',False)
            and line.bbox[2]-line.bbox[0]>page.width*.6):
        for other in page.lines:
            other_font=getattr(other,'font_size',None)
            peer=caption_match(other.text,kind)
            if (other!=line and peer and other_font and other_font<font*.95
                    and normalize_label(peer.group('number'))==normalize_label(match.group('number'))
                    and other.bbox[2]-other.bbox[0]<(line.bbox[2]-line.bbox[0])*.9):
                return None
    # An inline subheading can split the first prose line into a short fragment.
    # Its body font and following aligned full-width sentence supply evidence,
    # even though the fragment itself has no normal paragraph indentation.
    typical=body_font(page);h=max(1,line.bbox[3]-line.bbox[1])
    if font and typical and abs(font-typical)<=typical*.05 and not line.bold:
        following=[l for l in _body_lines(page) if not l.bold and l.font_size
                   and abs(l.font_size-font)<=font*.05
                   and 0<=l.bbox[1]-line.bbox[3]<=h*1.2
                   and abs(l.bbox[2]-line.bbox[2])<=h
                   and l.bbox[0]+h*3<line.bbox[0]]
        if following and not visual_support(line,page):return None
    # Finite prose predicates in the document's body font remain citations,
    # including a short standalone paragraph or the last line before a page break.
    finite=re.match(r'^(?:更|较|更加|较为)?(?:直观地|清楚地|清晰地|详细地|全面地)?[\u4e00-\u9fff]{1,8}了',tail)
    if finite and font and not line.bold:
        if typical and abs(font-typical)<=typical*.05:
            return None
        # A continuation page may contain no wide prose sample. Its own
        # smaller continued title establishes typography independently of
        # the short finite sentence below the table. A new adjacent visual
        # still keeps its separate title obligation.
        if not typical and text.rstrip().endswith(('。','.','！','!','？','?')):
            from .mineru_layout import LayoutObject
            from .caption_rules import _matches
            title=LayoutObject(kind+'_caption',page.number,line.bbox,line.text,page.width,page.height)
            independent_visual=visual_support(line,page) or any(
                obj.kind==kind and obj.page_number==page.number and _matches(obj,title)
                for obj in objects or ())
            if not independent_visual:
                for peer in page.lines:
                    declared=caption_match(peer.text,printed)
                    peer_font=getattr(peer,'font_size',None)
                    if (peer!=line and peer.source=='native' and declared
                            and normalize_label(declared.group('number'))==normalize_label(match.group('number'))
                            and re.match(r'^\s*(?:[（(]\s*(?:续|continued)\s*[）)]|'
                                     r'(?:续表?|continued)(?:\s|$|[:：]))',
                                     normalize_text(peer.text)[declared.end('number'):],re.I)
                            and peer_font and peer_font<font*.95
                            and visual_support(peer,page)):
                        return None
    if paragraph_continuation(line,page):return None
    if paragraph_start(line,page):
        continuation=any(l!=line and line.block_id is not None and l.block_id==line.block_id
                         and 0<=l.bbox[1]-line.bbox[3]<=15 for l in page.lines)
        # A real multi-line title may itself be first-line indented. Its
        # shared text block plus adjacent visual separates it from prose.
        tail=text[match.end('number'):].strip()
        prose=re.search(r'[。；;]|^(?:汇报|汇总|呈现|将|从|中|总结)',tail)
        if not (usual and continuation and visual_support(line,page) and not prose):return None
    if usual:return usual
    if _styled_bilingual_title(line,page,kind,match,objects):return match
    if _isolated_native_bold_title(line,page,kind):return match
    # Recover a rejected title only with independent typographic evidence:
    # compact centred line, smaller than surrounding prose.
    body=_body_lines(page)
    if not body or abs(line.direction[0])<.9:return None
    left=min(l.bbox[0] for l in body);right=sorted(l.bbox[2] for l in body)[len(body)//2]
    heights=sorted(l.bbox[3]-l.bbox[1] for l in body)
    h=line.bbox[3]-line.bbox[1];typical=heights[len(heights)//2]
    centred=abs((line.bbox[0]+line.bbox[2]-left-right)/2)<(right-left)*.08
    compact=line.bbox[2]-line.bbox[0]<(right-left)*.86
    # A nominal title can begin with “为...” and end in a full stop.
    # Independently smaller bold typography, centring and its real visual
    # establish a title without weakening ordinary body-reference recognition.
    typical_font=body_font(page)
    if centred and compact and line.bold and font and typical_font and font<typical_font*.95:
        # Thin PDF grid lines may evade native table extraction. Parser body
        # geometry can support a native title whose font/placement are proved
        # independently; an unverified parser caption alone cannot do so.
        from .mineru_layout import LayoutObject
        from .caption_rules import _matches
        title=LayoutObject(kind+'_caption',page.number,line.bbox,line.text,page.width,page.height)
        supported=visual_support(line,page) or any(
            obj.kind==kind and _matches(obj,title) for obj in objects or ())
        if supported:return match
    noun_title=not re.search(r'[。!?！？；;]',text[match.end('number'):])
    tail=text[match.end('number'):].strip()
    nominal_prefix=re.match(r'(?:为了|为.{1,40}(?:而|所)|(?:引用自|引自|来自).{1,80}(?:的|示意图|结构|比较|结果|过程))',tail)
    if centred and compact and h<typical*.98 and noun_title and nominal_prefix and visual_support(line,page):return match
    return None


def caption_number_fragment(line,page):
    """A styled leftover title number is neither prose nor a complete title.

    Require the native title font, centred placement and a nearby full title.
    This does not create a target: a later prose citation must still resolve to
    an actual caption, and a graphic without a complete title remains checked.
    """
    text=normalize_text(line.text).strip()
    kind=('figure' if re.fullmatch(r'(?:图|Figure|Fig[.]?)\s*(?:[A-Z][.]?)?[0-9]+(?:[.\-][0-9]+)*',text,re.I)
          else 'table' if re.fullmatch(r'(?:表|Table)\s*(?:[A-Z][.]?)?[0-9]+(?:[.\-][0-9]+)*',text,re.I)
          else None)
    if not kind or not line.bold or not line.font_size:return False
    if abs((line.bbox[0]+line.bbox[2])/2-page.width/2)>page.width*.05:return False
    for other in page.lines:
        if (other==line or not other.bold or not other.font_size
                or abs(other.font_size-line.font_size)>line.font_size*.05):continue
        if 0<=line.bbox[1]-other.bbox[3]<=60 and contextual_caption(other,page,kind):return True
    return False


def caption_region_lines(document,objects):
    """Validate a multi-line title region against its native title and typography.

    Cloud rectangles alone cannot remove prose from rule 11. Require an
    independently recognized title at the region's top and its smaller text
    style for subsequent explanation lines. Preserve citations as usage.
    """
    from .numbering import normalize_label
    pages={p.number:p for p in document.pages};keys=set()
    from .native_caption_blocks import native_caption_block
    for page in document.pages:
        for line in page.lines:
            block=native_caption_block(line,page,"figure",objects)
            if block:
                keys.update((row.page_number,row.bbox) for row in block.rows)
    def covered(line,obj):
        a=line.bbox;b=obj.bbox;area=max(0,a[2]-a[0])*max(0,a[3]-a[1])
        overlap=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
        return area>0 and overlap/area>=.9
    for obj in objects or ():
        if obj.kind not in {'figure_caption','table_caption'} or obj.page_number not in pages:continue
        kind=obj.kind.removesuffix('_caption');page=pages[obj.page_number]
        declared=caption_match(normalize_text(obj.text),kind)
        if not declared:continue
        anchors=[l for l in page.lines if covered(l,obj) and 0<=l.bbox[1]-obj.bbox[1]<=25
                 and (m:=contextual_caption(l,page,kind,objects)) and normalize_label(m.group('number'))==normalize_label(declared.group('number'))]
        for anchor in anchors:
            for line in page.lines:
                if not covered(line,obj) or line.bbox[1]<anchor.bbox[1]-1:continue
                same_font=(anchor.font_size and line.font_size and abs(anchor.font_size-line.font_size)<=anchor.font_size*.08)
                same_block=(anchor.block_id is not None and line.block_id==anchor.block_id)
                if line==anchor or same_font or (same_block and not anchor.font_size and not line.font_size):
                    keys.add((line.page_number,line.bbox))
    return keys
