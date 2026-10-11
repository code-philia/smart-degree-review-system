"""Repair academic table identity from physical evidence, after caption preparation.

Parser IDs are used only to preserve genuine parent ownership. Decisions do not
depend on a PDF path, corpus ID, finding ordinal, or the presence of an alarm.
Observations absorbed by a declared non-table object remain as text evidence.
"""
from collections import Counter
from dataclasses import replace
import re
from statistics import median

from .caption_rules import _matches
from .layout_context import containment, union, caption_line_box
from .mineru_layout import LayoutObject
from .numbering import caption_match, normalize_text, TABLE_CAPTION

GLOSSARY = re.compile(r"^(?:主要)?(?:符号|术语|中英文术语|简称|缩略[词语])(?:对照|注释)?表$|^List of (?:Symbols|Abbreviations)$", re.I)
CHAPTER = re.compile(r"^第\s*[一二三四五六七八九十0-9]+\s*章|^Chapter\s+[0-9IVX]+", re.I)
SECTION = re.compile(r"^(?:[A-Z]\.?\d+(?:\.\d+)*|\d+(?:\.\d+)+)\s+\S+", re.I)
PROGRAM = re.compile(r"^(?:算法|函数|Algorithm)\s*[A-Z]?\.?\s*\d+(?:[.\-]\d+)*", re.I)
LISTING = re.compile(r"^(?:Listing|代码(?:列表|清单)?|Code(?: Listing)?)\s*[A-Z]?\.?\s*\d+", re.I)
PANEL = re.compile(r"^[（(]([a-z0-9])[）)](?:\s*\S|\s*$)", re.I)
PROMPT = re.compile(r"Prompt\s*Template|(?:提示词|Prompt).*(?:Few.Shot|Chain.of.Thought)|(?:Few.Shot|Chain.of.Thought).*Prompt", re.I)


def _text(value):
    return normalize_text(value).strip()


def _inside_lines(obj, page):
    return [l for l in page.lines if containment(l.bbox, obj.bbox) >= .75]


def _overlap(a, b):
    width = min(a[2]-a[0], b[2]-b[0])
    return max(0, min(a[2], b[2])-max(a[0], b[0])) / width if width > 0 else 0


def _near_title(target, line, gap=65):
    return (_overlap(target.bbox, line.bbox) >= .5
            and (-3 <= target.bbox[1]-line.bbox[3] <= gap
                 or containment(line.bbox, target.bbox) >= .8
                 or -3 <= line.bbox[1]-target.bbox[3] <= gap))


def _own_caption(target, captions):
    return [c for c in captions if c.page_number == target.page_number
            and (_matches(target, c) or (target.parent_id and target.parent_id == c.parent_id))]


def _body_gap(page, boxes, top, bottom, allowed=()):
    """Only genuine intervening content blocks ownership, not cells/headings."""
    if bottom <= top + 3:
        return False
    for line in page.lines:
        if line.bbox[1] < top - 1 or line.bbox[3] > bottom + 1:
            continue
        if line.bbox[1] < page.height*.1 or line.bbox[3] >= page.height*.95:
            continue
        if any(containment(line.bbox, b) >= .65 for b in boxes):
            continue
        text = _text(line.text)
        if not text or text in allowed or PANEL.match(text):
            continue
        if re.fullmatch(r"[0-9IVXivx]+", text):
            continue
        return True
    return False


def _exclusive_frame_heading(target,line,page):
    """A frame declaration is outside the grid or owns a unique top row."""
    if line.bbox[3]<=target.bbox[1]+3:
        return not _body_gap(page,[line.bbox,target.bbox],line.bbox[3],target.bbox[1])
    if line.bbox[1]>target.bbox[1]+25:
        return False
    cy=(line.bbox[1]+line.bbox[3])/2
    others=[l for l in _inside_lines(target,page) if l is not line
            and abs((l.bbox[1]+l.bbox[3])/2-cy)<=5
            and (l.bbox[0]>=line.bbox[2]+5 or l.bbox[2]<=line.bbox[0]-5)]
    return not others


def _boolean_query_rows(rows):
    """A wrapped query keeps its quoted terms/parentheses across native rows."""
    if not rows or not re.match(r"^(?:TI|TS)\s*=\s*\(",rows[0],re.I):
        return False
    if len(re.findall(r"\b(?:AND|OR|NOT|NEAR/\d+)\b"," ".join(rows),re.I))<2:
        return False
    depth=0;quoted=False
    for row in rows:
        if not quoted and depth==0 and not re.match(
                r"^(?:(?:TI|TS|DT|SU)\s*=|(?:AND|OR|NOT)\b)",row,re.I):
            return False
        escaped=False
        for char in row:
            if char=='"' and not escaped:quoted=not quoted
            elif not quoted:
                if char=='(':depth+=1
                elif char==')':
                    depth-=1
                    if depth<0:return False
                elif char in "{};":return False
            escaped=(char=="\\" and not escaped)
    return depth==0 and not quoted


def _listing_contents(target,lines):
    """Require actual listing structure, never punctuation or one code cell."""
    from .program_identity import _c_declaration, instruction_template
    titles=[line for line in lines if LISTING.match(_text(line.text))]
    material=[line for line in lines if not any(
        abs((line.bbox[1]+line.bbox[3]-title.bbox[1]-title.bbox[3])/2)<=4
        for title in titles)]
    clean=lambda text:re.sub(r"^\s*\d+\s+","",_text(text)).strip()
    native=[clean(line.text) for line in material if clean(line.text)]
    chunks=["\n".join(clean(row) for row in target.text.splitlines()),
            "\n".join(native)]
    if any(_c_declaration(" ".join(chunk.splitlines())) or instruction_template(chunk)
           for chunk in chunks if chunk):
        return True
    # Whole native rows must predominantly be code/query expressions. A
    # complete inline try/catch is valid, but one cell beside ordinary data
    # rows cannot provide identity for the surrounding comparison table.
    rows=[row for row in native if row not in {"...","…"}
          and not row.startswith(("//","/*","*/"))]
    if not rows:
        rows=[clean(row) for row in target.text.splitlines() if clean(row)]
    if not rows:return False
    if _boolean_query_rows(rows):
        return True
    query=[row for row in rows if re.match(
        r"^(?:(?:TI|TS|DT|SU)\s*=|(?:AND|OR|NOT|NEAR/\d+)\b|[\x22\x27()])",row,re.I)]
    if (any(re.match(r"^(?:TI|TS)\s*=\s*\(",row,re.I) for row in query)
            and len(re.findall(r"\b(?:AND|OR|NOT|NEAR/\d+)\b"," ".join(query),re.I))>=2
            and len(query)>=len(rows)*.6):
        return True
    syntax=re.compile(
        r"^(?:[{};]+\s*(?:(?:catch|else)\b.*)?|"
        r"(?:try|catch|finally|throw|return|import|package)\b.*|"
        r"(?:public|private|protected|static|class|interface)\b.*|"
        r"[A-Za-z_$]\w*(?:\.[A-Za-z_$]\w*)*\s*\([^;{}]*\)\s*;|"
        r"(?:const\s+)?[A-Za-z_]\w*(?:::\w*)*(?:\s+|\s*[*&]\s*)"
        r"[A-Za-z_]\w*(?:\s*\[[^]]*\])?\s*(?:=.*)?;)\s*$",re.I)
    code=[row for row in rows if syntax.fullmatch(row)]
    structured=any(re.match(r"^(?:try|catch|class|interface|public|private|protected|static)\b",row,re.I)
                   for row in code)
    inline=any(re.match(r"^try\s*\{",row,re.I) and re.search(r"\}\s*catch\s*\(",row,re.I)
               for row in code)
    return len(code)>=len(rows)*.6 and (len(code)>=2 or (structured and inline))


def _non_table_frame(target, page):
    from .program_identity import native_statement_frame
    if native_statement_frame(target,page):
        return 'native_source_statement'
    lines = _inside_lines(target, page)
    body = " ".join([target.text] + [l.text for l in lines])
    candidates = [l for l in page.lines if _near_title(target,l)
                  and (LISTING.match(_text(l.text)) or _exclusive_frame_heading(target,l,page))]
    for line in candidates:
        title = _text(line.text)
        program=PROGRAM.match(title)
        descriptive=title[program.end():].strip() if program else ""
        if program and len(re.findall(r"[A-Za-z\u4e00-\u9fff]",descriptive))>=4 and not re.match(r"^(?:Input|Output)\b",descriptive,re.I) and (
            re.search(r"\b(?:Input|Output|return|for|while)\b|输入|输出|←|赋值", body, re.I)
            or len(re.findall(r"(?:^|\s)\d{1,2}(?:\s|[.:])", body)) >= 3):
            return "declared_algorithm"
        if (LISTING.match(title)
                and not re.search(r"\b(?:shows?|illustrates?|describes?|presents?|is|are|was|were)\b",title,re.I)
                and _listing_contents(target,lines)):
            return "declared_code_listing"
        if PROMPT.search(title) and (
            len(re.findall(r"\b(?:Role|Context|Constraints|Output|Input|Examples|Analysis)\b", body, re.I)) >= 2):
            return "declared_prompt"
        if ("定义" in title or re.search(r"\bDefinition\b", title, re.I)) and (
            re.search(r"\bYES\b", body) and re.search(r"\bNO\b", body)
            and re.search(r"\bInput\b|输入", body, re.I)):
            return "declared_definition"
        if (title.endswith("模块示例") and
                re.search(r"输入|Input|原始句子", body, re.I) and
                re.search(r"输出|Output|三元组|分析结果", body, re.I)):
            return "declared_example"
        if re.match(r"^(?:Research Question|研究问题)\s*\d+", title, re.I) and len(lines) <= 8:
            return "declared_question"
    return ""



def _recover_printed_titles(objects, document):
    """Recover printed declarations using their actual native text rectangles."""
    result=list(objects)
    for page in document.pages:
        tables=[o for o in result if o.kind=="table" and o.page_number==page.number]
        # Font fallback can give one Greek glyph a page-sized native rectangle.
        # Use the same character-evidence bounds as initial caption preparation.
        lines=[replace(l,bbox=caption_line_box(l)) for l in page.lines]
        for line in lines:
            text=_text(line.text)
            match=TABLE_CAPTION.match(text)
            sideways=abs(line.direction[0])<.1 and bool(re.fullmatch(r"续表\s*[A-Z]?\d+(?:[.\-]\d+)*",text))
            if not sideways and not (match and line.bold):
                continue
            native=[line]
            if not sideways:
                # Continue a printed caption only through consecutive lines with
                # the same title typography and text block, never normal body.
                for other in sorted(lines,key=lambda l:l.bbox[1]):
                    if other.bbox[1]<line.bbox[3]-2 or other is line:
                        continue
                    if other.bbox[1]-native[-1].bbox[3]>8:
                        break
                    if (not other.bold or other.font_size!=line.font_size
                            or other.block_id!=line.block_id or TABLE_CAPTION.match(_text(other.text))):
                        break
                    native.append(other)
            box=union([l.bbox for l in native])
            caption=LayoutObject("table_caption",page.number,box," ".join(l.text for l in native),
                                 page.width,page.height,"printed_table_title")
            duplicates=[c for c in result if c.kind=="table_caption" and c.page_number==page.number
                        and ((sideways and _text(c.text)==text)
                             or (match and (m:=TABLE_CAPTION.match(_text(c.text)))
                                 and m.group("number")==match.group("number")))]
            if duplicates:
                if sideways:
                    result=[replace(o,bbox=line.bbox) if o in duplicates else o for o in result]
                elif all(containment(box,c.bbox)<.9 for c in duplicates):
                    result=[replace(o,bbox=union([o.bbox,box])) if o in duplicates else o for o in result]
                continue
            owned=[t for t in tables if _matches(t,caption)]
            if len(owned)!=1 or _body_gap(page,[t.bbox for t in tables]+[l.bbox for l in native],
                                         caption.bbox[3],owned[0].bbox[1]):
                continue
            result.append(caption)
    return result

def _extend_caption_notes(objects,pages):
    result=[]
    for caption in objects:
        if caption.kind!="table_caption" or caption.parent_bbox is None:
            result.append(caption);continue
        page=pages.get(caption.page_number)
        owned=[t for t in objects if t.kind=="table" and t.page_number==caption.page_number
               and t.parent_id and t.parent_id==caption.parent_id]
        if page is None or len(owned)!=1 or owned[0].bbox[1]-caption.bbox[3]<=80:
            result.append(caption);continue
        target=owned[0]
        notes=sorted([l for l in page.lines if caption.bbox[3]-1<=l.bbox[1]
                      and l.bbox[3]<=target.bbox[1]+1],key=lambda l:l.bbox[1])
        native_titles=[l for l in page.lines if containment(l.bbox,caption.bbox)>=.75]
        title_font=max((l.font_size for l in native_titles if l.font_size),default=0)
        outside=[l.font_size for l in page.lines if l.font_size and l.bbox[1]>page.height*.11
                 and containment(l.bbox,target.bbox)<.2 and l not in notes and l not in native_titles]
        small_type=bool(title_font and notes and all(l.font_size==title_font for l in notes)
                        and outside and median(outside)>=title_font*1.1)
        if not notes or not (small_type or re.match(r"^(?:注|说明|Note)\s*[:：.]",_text(notes[0].text),re.I)):
            result.append(caption);continue
        competing=[o for o in objects if o.kind in {"table","figure"} and o.page_number==page.number
                   and o is not target and caption.bbox[3]<o.bbox[1]<target.bbox[1]]
        if competing:
            result.append(caption);continue
        result.append(replace(caption,bbox=union([caption.bbox]+[l.bbox for l in notes]),
                              text=caption.text+" "+" ".join(l.text for l in notes)))
    return result


def _declared_figure_parts(objects):
    result=[]
    figures=[o for o in objects if o.kind=="figure"]
    titles=[o for o in objects if o.kind=="figure_caption"]
    table_titles=[o for o in objects if o.kind=="table_caption"]
    owned_figures=[f for f in figures if _own_caption(f,titles)]
    for target in objects:
        if target.kind!="table" or _own_caption(target,table_titles):
            result.append(target);continue
        owners=[f for f in owned_figures if f.page_number==target.page_number
                and containment(target.bbox,f.bbox)>=.94]
        declarations=[c for c in titles if c.page_number==target.page_number
                      and c.parent_bbox is not None and containment(target.bbox,c.parent_bbox)>=.94]
        declaration_numbers={m.group("number") for c in declarations
                             if (m:=re.match(r"^(?:图|Figure|Fig\.?)\s*(?P<number>[A-Z]?\d+(?:[.\-]\d+)*)",_text(c.text),re.I))}
        if owners:
            result.append(replace(target,kind="text",role="declared_figure_component"));continue
        if len(declaration_numbers)==1:
            # A source-declared figure may contain a smaller native figure window.
            # Its table-shaped observation must not introduce a second rule-13 target.
            nearby=[f for f in figures if f.page_number==target.page_number
                    and (containment(f.bbox,target.bbox)>=.4 or containment(target.bbox,f.bbox)>=.4)]
            if nearby:
                result.append(replace(target,kind="text",role="declared_figure_component"))
            else:
                # Preserve one full physical figure rather than a distant cropped row.
                result.append(replace(target,kind="figure",role="declared_figure",
                                      bbox=union([target.bbox]+[c.parent_bbox for c in declarations])))
        else:
            result.append(target)
    return result

def _absorb_contained_tables(objects):
    result = list(objects)
    tables = [o for o in result if o.kind == "table"]
    captions = [o for o in result if o.kind == "table_caption"]
    absorbed = set()
    replacements = {}
    # An actual captioned full table is evidence; arbitrary shared parser parents
    # or an envelope around two independent tables are insufficient.
    for owner in sorted(tables, key=lambda t: (t.bbox[2]-t.bbox[0])*(t.bbox[3]-t.bbox[1]), reverse=True):
        if id(owner) in absorbed or not _own_caption(owner, captions):
            continue
        parts = [t for t in tables if t is not owner and id(t) not in absorbed
                 and t.page_number == owner.page_number
                 and containment(t.bbox, owner.bbox) >= .90]
        if not parts:
            continue
        # At most a small extraction tolerance may extend an original envelope.
        parts = [p for p in parts if p.bbox[0] >= owner.bbox[0]-3 and p.bbox[2] <= owner.bbox[2]+3
                 and p.bbox[1] >= owner.bbox[1]-3 and p.bbox[3] <= owner.bbox[3]+3]
        if parts:
            absorbed.update(id(p) for p in parts)
            replacements[id(owner)] = replace(owner, bbox=union([owner.bbox]+[p.bbox for p in parts]),
                                              panel_boxes=owner.panel_boxes or (owner.bbox,))
    return [replacements.get(id(o), o) for o in result if id(o) not in absorbed]



def _panel_tags(target,page):
    tagged=[l for l in page.lines if PANEL.match(_text(l.text))
            and _overlap(l.bbox,target.bbox)>=.5 and len(_text(l.text))<=110]
    top=[l for l in tagged if target.bbox[1]-45<=l.bbox[1]<=target.bbox[1]+25]
    bottom=[l for l in tagged if target.bbox[3]-15<=l.bbox[1]<=target.bbox[3]+15]
    return [(PANEL.match(_text(l.text)).group(1).lower(),l) for l in (top or bottom)]


def _parallel_comparison(group,caption,page):
    if len(group)!=2 or any(t.kind!="table" for t in group):
        return False
    a,b=sorted(group,key=lambda t:t.bbox[0])
    if a.bbox[2]>=b.bbox[0] or abs(a.bbox[1]-b.bbox[1])>20:
        return False
    if (min(a.bbox[3],b.bbox[3])-max(a.bbox[1],b.bbox[1])
            < min(a.bbox[3]-a.bbox[1],b.bbox[3]-b.bbox[1])*.75):
        return False
    box=union([t.bbox for t in group]);width=box[2]-box[0]
    if (caption.bbox[2]-caption.bbox[0]<width*.65
            or abs(caption.bbox[0]+caption.bbox[2]-box[0]-box[2])>width*.2):
        return False
    def header(t):
        cells=_inside_lines(t,page)
        if not cells:return ()
        y=min(l.bbox[1] for l in cells)
        return tuple(_text(l.text).lower() for l in sorted(cells,key=lambda l:l.bbox[0])
                     if l.bbox[1]<=y+5)
    x,y=header(a),header(b)
    return len(x)>=3 and len(y)==len(x) and x[-2:]==y[-2:] and any(re.search(r"[A-Za-z\u4e00-\u9fff]",v) for v in x[-2:])

def _figure_annotations(group,page,caption,side):
    box=union([t.bbox for t in group])
    observed={_text(l.text) for t in group for l in _inside_lines(t,page)}
    result=[]
    for line in page.lines:
        text=_text(line.text)
        if any(containment(line.bbox,t.bbox)>=.65 for t in group):
            continue
        vertical=abs(line.direction[0])<.1
        legend=(side and vertical and caption.bbox[2]-3<=line.bbox[0]<=box[2]
                and box[1]-10<=line.bbox[1] and line.bbox[3]<=box[3]+10)
        repeated=(len(text)<=35 and text in observed and box[1]-50<=line.bbox[1]<box[1]
                  and _overlap(line.bbox,box)>=.5)
        axis=(len(text)<=45 and not re.search(r"[。!?！？]$",text)
              and re.search(r"时间|分钟|秒|time|latency|accuracy|memory|\\([%s]\\)",text,re.I)
              and any(-2<=line.bbox[1]-t.bbox[3]<=20 and _overlap(line.bbox,t.bbox)>=.6
                      for t in group if t.kind=="figure"))
        if legend or repeated or axis:result.append(line)
    return result


def _physical_panel_labels(page,group,captions):
    # Canonical labels retain bilingual rows and split native merged glyph spans.
    # Ownership is checked against physical constituents, never a page-wide band.
    from .logical_objects import panel_label_lines
    boxes=[box for target in group for box in (target.panel_boxes or (target.bbox,))]
    return [line for line in panel_label_lines(page,group,captions)
            if PANEL.match(_text(line.text)) and any(
                box[0]-15 <= (line.bbox[0]+line.bbox[2])/2 <= box[2]+15
                and box[1]-45 <= line.bbox[1] and line.bbox[3] <= box[3]+35
                for box in boxes)]


def _title_covers_panel_text(caption,labels):
    for line in labels:
        xover=min(caption.bbox[2],line.bbox[2])-max(caption.bbox[0],line.bbox[0])
        yover=min(caption.bbox[3],line.bbox[3])-max(caption.bbox[1],line.bbox[1])
        height=min(caption.bbox[3]-caption.bbox[1],line.bbox[3]-line.bbox[1])
        if xover>0 and yover>max(2,height*.3):
            return True
    return False


def _exclusive_single_figure_title(group,caption,targets,captions):
    if len(group)!=1 or not _matches(group[0],caption):
        return False
    def gap(target,title):
        return max(title.bbox[1]-target.bbox[3],target.bbox[1]-title.bbox[3],0)
    def number(title):
        match=re.match(r"^(?:图|Figure|Fig\.?)\s*([A-Z]?\d+(?:[.\-]\d+)*)",_text(title.text),re.I)
        return match.group(1).casefold() if match else ""
    for peer in targets:
        if peer in group or peer.kind!="figure" or not _matches(peer,caption):
            continue
        # Native windows contained in the same physical body do not compete.
        if (containment(peer.bbox,group[0].bbox)>=.5
                or containment(group[0].bbox,peer.bbox)>=.5):
            continue
        # A separately captioned neighbouring figure keeps its closer own title.
        if any(other is not caption and number(other)!=number(caption)
               and _matches(peer,other) and gap(peer,other)<gap(peer,caption)
               for other in captions):
            continue
        return False
    return True


def _join_figure_bands(objects,pages):
    """An explicit figure declaration owns its table-shaped physical panels."""
    result=list(objects)
    for page in pages.values():
        captions=[c for c in result if c.kind=="figure_caption" and c.page_number==page.number]
        boundaries=[c for c in result if c.kind in {"table_caption","figure_caption"}
                    and c.page_number==page.number and c.role!="unnumbered_panel_title"]
        for caption in captions:
            targets=[t for t in result if t.kind in {"table","figure"} and t.page_number==page.number]
            side=caption.bbox[3]-caption.bbox[1]>3*(caption.bbox[2]-caption.bbox[0])
            if side:
                group=[t for t in targets if t.bbox[0]>=caption.bbox[2]-3
                       and t.bbox[1]>=caption.bbox[1]-30 and t.bbox[3]<=caption.bbox[3]+30]
            else:
                above=[t for t in targets if 0<=caption.bbox[1]-t.bbox[3]<=80]
                below=[t for t in targets if 0<=t.bbox[1]-caption.bbox[3]<=80]
                if above:
                    top=max([c.bbox[3] for c in boundaries if c.bbox[3]<caption.bbox[1]-2] or [page.height*.1])
                    bottom=caption.bbox[1]+3
                elif below:
                    top=caption.bbox[3]-3
                    bottom=min([c.bbox[1] for c in boundaries if c.bbox[1]>caption.bbox[3]+2] or [page.height*.93])
                else:continue
                group=[t for t in targets if t.bbox[1]>=top-3 and t.bbox[3]<=bottom+3]
            tables=[t for t in group if t.kind=="table"]
            if not tables:continue
            table_titles=[c for c in boundaries if c.kind=="table_caption"]
            if any(_own_caption(t,table_titles) for t in tables):continue
            # Source ownership, a named multi-panel declaration, or an exclusive
            # single physical table paired to a figure title provides identity.
            direct=bool(caption.parent_id and any(t.parent_id==caption.parent_id for t in tables))
            multiple=bool(re.search(r"(?:[（(][a-z][）)].*){2,}|above figures|上方.*下方|上图.*下图",_text(caption.text),re.I))
            single=_exclusive_single_figure_title(group,caption,targets,captions)
            box=union([t.bbox for t in group])
            width=box[2]-box[0]
            centered=(caption.bbox[2]-caption.bbox[0]>=width*.6
                      and abs(caption.bbox[0]+caption.bbox[2]-box[0]-box[2])<=width*.2)
            panel_lines=_physical_panel_labels(page,group,boundaries)
            if _title_covers_panel_text(caption,panel_lines):
                continue
            panel_labels=[PANEL.match(_text(l.text)).group(1).lower() for l in panel_lines]
            if len(panel_labels)!=len(set(panel_labels)):
                continue
            namespace={"a","b"}.issubset(panel_labels)
            # Labels belonging to the figure below do not declare an unrelated
            # table above it. Each table needs its own panel or source ownership.
            if namespace and not direct and any(not _panel_tags(t,page) for t in tables):
                continue
            multiple=multiple or namespace
            if namespace:
                centered=(caption.bbox[2]-caption.bbox[0]>=width*.3
                          and abs(caption.bbox[0]+caption.bbox[2]-box[0]-box[2])<=width*.2)
            if not single and not ((direct or multiple) and (side or centered)):
                continue
            annotations=_figure_annotations(group,page,caption,side)
            boxes=[t.bbox for t in group]+[l.bbox for l in panel_lines]+[l.bbox for l in annotations]+[caption.bbox]
            if _body_gap(page,boxes,min(box[1],caption.bbox[1]),max(box[3],caption.bbox[3])):
                continue
            kept=next((t for t in group if t.kind=="figure"),group[0])
            merged=replace(kept,kind="figure",bbox=union([box]+[l.bbox for l in panel_lines]+[l.bbox for l in annotations]),
                           role="declared_figure_panels",panel_boxes=tuple(t.bbox for t in group))
            if not _matches(merged,caption):continue
            result=[merged if o is kept else o for o in result if o is kept or o not in group]
    return result

def _continue_example_frames(objects,pages):
    result=[]
    for target in objects:
        page=pages.get(target.page_number);previous=pages.get(target.page_number-1)
        if target.kind!="table" or page is None or previous is None or target.bbox[1]>page.height*.25:
            result.append(target);continue
        body=target.text+" "+" ".join(l.text for l in _inside_lines(target,page))
        titles=[l for l in previous.lines if _text(l.text).endswith("模块示例")
                and len(_text(l.text))>4 and l.bbox[1]>=previous.height*.65]
        if len(titles)!=1 or len(re.findall(r"〈|←",body))<3:
            result.append(target);continue
        title=titles[0]
        tail=sorted([l for l in previous.lines if l.bbox[1]>=title.bbox[3]
                     and l.bbox[3]<previous.height*.93 and not re.fullmatch(r"[0-9IVXivx]+",_text(l.text))],key=lambda l:l.bbox[1])
        if (not tail or tail[-1].bbox[3]<previous.height*.82
                or not any("输入" in l.text for l in tail)
                or re.search(r"[。！？.!?][”'\"]?$",_text(tail[-1].text))
                or any(c.kind=="table_caption" and _matches(target,c) for c in objects)):
            result.append(target);continue
        result.append(replace(target,kind="text",role="declared_example_continuation"))
    return result


def _join_declared_panels(objects,pages):
    result=list(objects)
    for page in pages.values():
        captions=sorted([c for c in result if c.kind=="table_caption" and c.page_number==page.number
                         and c.role not in {"unnumbered_heading","unnumbered_panel_title"}
                         and not GLOSSARY.fullmatch(_text(c.text))],key=lambda c:c.bbox[1])
        boundaries=sorted([c for c in result if c.kind in {"table_caption","figure_caption"}
                           and c.page_number==page.number and c.role!="unnumbered_panel_title"
                           and not GLOSSARY.fullmatch(_text(c.text))],key=lambda c:c.bbox[1])
        for caption in captions:
            targets=[t for t in result if t.kind in {"table","figure"} and t.page_number==page.number]
            below=[t for t in targets if 0<=t.bbox[1]-caption.bbox[3]<=80]
            above=[t for t in targets if 0<=caption.bbox[1]-t.bbox[3]<=80]
            if below:
                top=caption.bbox[3]-5
                bottom=min([c.bbox[1] for c in boundaries if c.bbox[1]>caption.bbox[3]+2] or [page.height*.93])
            elif above:
                bottom=caption.bbox[1]+5
                top=max([c.bbox[3] for c in boundaries if c.bbox[3]<caption.bbox[1]-2] or [page.height*.1])
            else:
                continue
            group=[t for t in targets if top<=t.bbox[1] and t.bbox[3]<=bottom+3
                   and _overlap(t.bbox,caption.bbox)>=.25]
            if len([t for t in group if t.kind=="table"])<2:
                continue
            table_namespace=any(_panel_tags(t,page) for t in group if t.kind=="table")
            group=[t for t in group if t.kind=="table" or (table_namespace and _panel_tags(t,page))]
            tagged=[(t,_panel_tags(t,page)) for t in group]
            # Count distinct physical labels, after bilingual deduplication.
            # An overlapping parser window may see the very same label twice;
            # a second printed occurrence starts an independent namespace.
            physical_labels=_physical_panel_labels(page,group,boundaries)
            counts=Counter(PANEL.match(_text(line.text)).group(1).lower()
                           for line in physical_labels)
            if any(count>1 for count in counts.values()):
                continue
            tags=[(tag,l) for t,pairs in tagged for tag,l in pairs]
            band_tags=[(PANEL.match(_text(l.text)).group(1).lower(),l) for l in page.lines
                       if PANEL.match(_text(l.text)) and top<=l.bbox[1]<=bottom and len(_text(l.text))<=110]
            labels=sorted(set(tag for tag,_ in band_tags))
            consecutive=bool(len(labels)>=2 and labels[0] in {"a","1"}
                             and all(ord(b)==ord(a)+1 for a,b in zip(labels,labels[1:])))
            explicit_split=bool(re.search(r"\b(?:upper|top)\b.*\b(?:lower|bottom)\b|上表.*下表|上半.*下半",_text(caption.text),re.I))
            same_number=[c.text for c in captions if (m:=TABLE_CAPTION.match(_text(c.text)))
                         and (n:=TABLE_CAPTION.match(_text(caption.text))) and m.group("number")==n.group("number")]
            declaration="".join(re.sub(r"\s+","",_text(x)).lower() for x in same_number)
            headings=[]
            for table in group:
                native=sorted([l for l in _inside_lines(table,page) if l.bbox[1]<=table.bbox[1]+25],key=lambda l:l.bbox[1])
                candidates=[re.sub(r"\s+","",_text(l.text)).lower() for l in native]
                headings.append(next((v for v in candidates if len(re.findall(r"[A-Za-z\u4e00-\u9fff]",v))>=4
                                      and v in declaration),None))
            semantic=bool(len(group)>=2 and all(headings) and len(set(headings))==len(headings))
            parallel=_parallel_comparison(group,caption,page)
            if not explicit_split and not semantic and not parallel and (not consecutive or len([t for t,pairs in tagged if pairs])<2):
                continue
            band_tags=list({(tag,tuple(l.bbox),l.text):(tag,l) for _,pairs in tagged for tag,l in pairs}.values())
            wrapped=[l for _,title in band_tags for l in page.lines
                     if l.font_size==title.font_size and title.bbox[1]<=l.bbox[1]<title.bbox[3]+30
                     and _overlap(l.bbox,title.bbox)>=.75]
            boxes=[t.bbox for t in group]+[l.bbox for _,l in band_tags]+[l.bbox for l in wrapped]+[caption.bbox]
            group_box=union([t.bbox for t in group]+[l.bbox for _,l in band_tags]+[l.bbox for l in wrapped])
            if not _matches(replace(group[0],bbox=group_box),caption):
                continue
            if _body_gap(page,boxes,min(group_box[1],caption.bbox[1]),max(group_box[3],caption.bbox[3])):
                continue
            kept=next(t for t in group if t.kind=="table")
            merged=replace(kept,bbox=group_box,text="\n".join(t.text for t in group if t.text),
                           role="declared_table_panels",panel_boxes=tuple(t.bbox for t in group))
            result=[merged if o is kept else o for o in result if o is kept or o not in group]
    return result

def _exclusive_section_titles(objects, pages):
    result = list(objects)
    for page in pages.values():
        targets = [o for o in result if o.kind in {"table","figure"} and o.page_number == page.number]
        captions = [o for o in result if o.kind == "table_caption"]
        headings = sorted([l for l in page.lines if SECTION.match(_text(l.text))
                           and (l.role == "title" or (l.font_size is not None and l.font_size >= 12))
                           and not re.search(r"[。；;!?！？]", l.text)], key=lambda l:l.bbox[1])
        for i, heading in enumerate(headings):
            end = headings[i+1].bbox[1] if i+1 < len(headings) else page.height*.93
            owned = [t for t in targets if t.bbox[1] >= heading.bbox[3]-2 and t.bbox[1] < end]
            if len(owned) != 1 or owned[0].kind != "table" or _own_caption(owned[0], captions):
                continue
            target = owned[0]
            if target.bbox[1]-heading.bbox[3] > 80:
                continue
            if (_body_gap(page,[t.bbox for t in targets],heading.bbox[3],target.bbox[1])
                    or _body_gap(page,[target.bbox],target.bbox[3],end)):
                continue
            caption = LayoutObject("table_caption", page.number, heading.bbox, heading.text,
                                   page.width, page.height, "exclusive_section_table_title")
            if _matches(target, caption):
                result.append(caption)
    return result



def _glossary_continuation(page,tables):
    """Require actual symbol/definition columns and no transition to body prose."""
    if not tables:return False
    pairs=[]
    for table in tables:
        profile=_column_profile(table,page)
        if len(profile) not in {2,3,4}:continue
        rows=[]
        for line in sorted(_inside_lines(table,page),key=lambda l:l.bbox[1]):
            cy=(line.bbox[1]+line.bbox[3])/2
            row=next((r for r in rows if abs(r[0]-cy)<=5),None)
            if row is None:rows.append([cy,[line]])
            else:row[1].append(line)
        for _,cells in rows:
            cells=sorted(cells,key=lambda l:l.bbox[0])
            if len(cells)<2 or cells[-1].bbox[0]-cells[0].bbox[0]<40:continue
            left,right=_text(cells[0].text),_text(cells[-1].text)
            letters=len(re.findall(r"[A-Za-z\u4e00-\u9fff]",right))
            symbol=bool(len(left)<=30 and re.search(r"[A-Za-z\u4e00-\u9fffα-ωΑ-Ω]",left)
                        and not re.fullmatch(r"\d+(?:\.\d+)*",left))
            translation=bool(len(profile)<4 or all(len(re.findall(r"[A-Za-z\u4e00-\u9fff]",_text(c.text)))>=3 for c in cells[1:-1]))
            pairs.append(symbol and translation and letters>=4 and not re.fullmatch(r"[\d\s.,%+\-±/]+",right))
    if len(pairs)<3 or sum(pairs)/len(pairs)<.65:return False
    for line in page.lines:
        if line.bbox[1]<page.height*.1 or line.bbox[3]>page.height*.93:continue
        if any(containment(line.bbox,t.bbox)>=.65 for t in tables):continue
        text=_text(line.text)
        if (not text or GLOSSARY.fullmatch(text) or re.fullmatch(r"[0-9IVXivx]+",text)
                or "符号" in text or "术语" in text
                or (CHAPTER.match(text) and re.search(r"[：:、]",text))):
            continue
        if (re.search(r"[。.!?！？]$",text) or len(re.findall(r"[A-Za-z\u4e00-\u9fff]",text))>=18):
            return False
    return True


def _glossary_fragments(objects,pages):
    result,active,previous=[],False,None
    scopes=set()
    captions=[o for o in objects if o.kind=="table_caption" and TABLE_CAPTION.match(_text(o.text))]
    for number,page in sorted(pages.items()):
        if previous is not None and number!=previous+1:active=False
        titles=[l for l in page.lines if GLOSSARY.fullmatch(_text(l.text)) and l.bbox[1]>=page.height*.11]
        running=any(GLOSSARY.fullmatch(_text(l.text)) for l in page.lines)
        transition=any((CHAPTER.match(_text(l.text)) and not re.search(r"[：:、]",_text(l.text))
                        or re.match(r"^\d+[.\s]+\s*(?:Introduction|Experiments?|Methods?|Results?|Discussion)\b",_text(l.text),re.I))
                       and l.bbox[1]>=page.height*.11 for l in page.lines)
        if transition and not running:active=False
        if titles:active=True
        tables=[o for o in objects if o.kind=="table" and o.page_number==number]
        if active and not titles and not running and not _glossary_continuation(page,tables):
            active=False
        if active and (titles or running or tables):scopes.add(number)
        previous=number
    for target in objects:
        if target.kind=="table" and target.page_number in scopes and not _own_caption(target,captions):
            result.append(replace(target,kind="text",role="declared_glossary_fragment"))
        else:result.append(target)
    return result

def _column_profile(target, page):
    rows = []
    for line in sorted(_inside_lines(target,page), key=lambda l:(l.bbox[1],l.bbox[0])):
        if not _text(line.text) or line.bbox[2]-line.bbox[0] > (target.bbox[2]-target.bbox[0])*.8:
            continue
        y=(line.bbox[1]+line.bbox[3])/2
        row=next((r for r in rows if abs(r[0]-y)<=4),None)
        if row is None:
            rows.append([y,[line]])
        else:
            row[1].append(line)
    valid=[sorted(cells,key=lambda l:l.bbox[0]) for _,cells in rows if 2<=len(cells)<=16]
    if not valid:
        return ()
    count=Counter(len(r) for r in valid).most_common(1)[0][0]
    valid=[r for r in valid if len(r)==count]
    if len(valid)<2:
        return ()
    return tuple(median(r[i].bbox[0] for r in valid) for i in range(count))


def _join_continuous_grid_windows(objects,pages):
    result=list(objects)
    captions=[c for c in result if c.kind=="table_caption"]
    owners=[t for t in result if t.kind=="table" and _own_caption(t,captions)]
    absorbed=set();replacements={}
    for owner in owners:
        page=pages.get(owner.page_number)
        if page is None:continue
        a=_column_profile(owner,page)
        if len(a)<4:continue
        for target in result:
            if (target.kind!="table" or target is owner or id(target) in absorbed
                    or target.page_number!=owner.page_number or _own_caption(target,captions)
                    or target.bbox[1]<owner.bbox[3] or _overlap(owner.bbox,target.bbox)<.95):
                continue
            b=_column_profile(target,page)
            if len(a)!=len(b) or any(abs(x-y)>6 for x,y in zip(a,b)):continue
            gap=[l for l in page.lines if owner.bbox[3]-2<=l.bbox[1]<target.bbox[1]
                 and _overlap(l.bbox,owner.bbox)>=.5]
            rows=[]
            for line in sorted(gap,key=lambda l:l.bbox[1]):
                y=(line.bbox[1]+line.bbox[3])/2
                row=next((r for r in rows if abs(r[0]-y)<=4),None)
                if row is None:rows.append([y,[line]])
                else:row[1].append(line)
            dense=[r for r in rows if len(r[1])>=len(a)*.7]
            if len(dense)<3:continue
            heights=[l.bbox[3]-l.bbox[1] for _,ls in dense for l in ls]
            limit=max(25,median(heights)*3)
            ys=[owner.bbox[3]]+[y for y,_ in dense]+[target.bbox[1]]
            if any(v-u>limit for u,v in zip(ys,ys[1:])):continue
            if any(len(ls)<len(a)*.7 and (len(ls)!=1 or len(_text(ls[0].text))>90
                                      or re.search(r"[。.!?！？]$",_text(ls[0].text)))
                   for _,ls in rows):continue
            absorbed.add(id(target))
            replacements[id(owner)]=replace(owner,bbox=union([owner.bbox,target.bbox]),
                                             role="continuous_table_grid",
                                             panel_boxes=owner.panel_boxes or (owner.bbox,target.bbox))
    return [replacements.get(id(o),o) for o in result if id(o) not in absorbed]


def _semantic_column_header(target,page):
    lines=_inside_lines(target,page)
    if not lines:return ()
    top=min(line.bbox[1] for line in lines)
    row=sorted([line for line in lines if abs(line.bbox[1]-top)<8],key=lambda line:line.bbox[0])
    values=tuple(_text(line.text).casefold() for line in row)
    # A compact row of column names differs from a definition sentence or data.
    # Numeric rows and wrapped prose do not establish a new semantic header.
    if len(values)<2 or not all(re.fullmatch(
            r"[a-z][a-z0-9 _()/%.+\-]{0,39}|[\u4e00-\u9fff]{1,12}",value)
            for value in values):
        return ()
    return values


def _continue_tables(objects, pages):
    result=list(objects)
    tables=sorted([o for o in result if o.kind=="table"],key=lambda o:(o.page_number,o.bbox[1]))
    captions=[o for o in result if o.kind=="table_caption"]
    matched={id(t) for t in tables if _own_caption(t,captions)}
    inherited=set()
    for second in tables:
        if id(second) in matched or second.bbox[1] > second.page_height*.25:
            continue
        candidates=[first for first in tables if first.page_number==second.page_number-1
                    and id(first) in matched and first.bbox[3]>=first.page_height*.83
                    and _overlap(first.bbox,second.bbox)>=.85]
        if len(candidates)!=1:
            continue
        first=candidates[0]
        a,b=pages.get(first.page_number),pages.get(second.page_number)
        if a is None or b is None:
            continue
        if (_body_gap(a,[first.bbox],first.bbox[3],a.height*.95)
                or _body_gap(b,[second.bbox],b.height*.1,second.bbox[1])):
            continue
        new_header=_semantic_column_header(second,b)
        if new_header and new_header!=_semantic_column_header(first,a):
            continue
        x,y=_column_profile(first,a),_column_profile(second,b)
        if len(x)<2 or len(x)!=len(y) or any(abs(i-j)>12 for i,j in zip(x,y)):
            continue
        inherited.add(id(second));matched.add(id(second))
    return [replace(o,kind="text",role="continued_table_fragment") if id(o) in inherited else o for o in result]


def _numbered_math_fragment(target,page):
    lines=_inside_lines(target,page)
    text=" ".join(_text(l.text) for l in lines)
    if re.search(r"[\u4e00-\u9fff]",text):
        return False
    words=re.findall(r"[A-Za-z]{2,}",text)
    allowed={"mod","log","sin","cos","tan","exp","max","min","lim","arg","det","ln"}
    if not words or any(w.lower() not in allowed and w[1:].lower() not in allowed for w in words):
        return False
    numbers=[l for l in page.lines if re.fullmatch(r"[（(](?:[A-Z]\.?)?\d+(?:[.\-]\d+)*[）)]",_text(l.text))
             and l.bbox[0]>=target.bbox[2] and l.bbox[0]-target.bbox[2]<=page.width*.2
             and target.bbox[1]<=l.bbox[1]<=target.bbox[3]]
    return len(numbers)>=2 and len(re.findall(r"[+*/∑∏−-]|\b(?:log|sin|cos|exp)\b",text))>=4


def _illustrated_table_prefixes(objects, pages, document):
    """Bind a graphic-only table prefix to its source-proved next-page cells.

    A spanning parser table may start with an illustration, with all native
    data cells on the following page. The prefix must not consume the only
    caption and leave the actual data table falsely untitled.
    """
    from .caption_rules import _body_between
    tables = [o for o in objects if o.kind == 'table']
    captions = [o for o in objects if o.kind == 'table_caption']
    prefixes = set()
    clean = lambda value: re.sub(r'[\s_{}]', '', _text(value)).casefold()
    for first in tables:
        page = pages.get(first.page_number)
        if (page is None or not first.text or first.bbox[3] < page.height*.83
                or _inside_lines(first, page)):
            continue
        rasters = [box for box in page.images if containment(box, first.bbox) >= .95
                   and (box[2]-box[0])*(box[3]-box[1]) >=
                       (first.bbox[2]-first.bbox[0])*(first.bbox[3]-first.bbox[1])*.6]
        if len(rasters) != 1:
            continue
        candidates = [o for o in tables if o.page_number == first.page_number+1
                      and not o.text.strip() and o.bbox[1] <= o.page_height*.15
                      and abs(o.bbox[0]-first.bbox[0]) <= 6
                      and abs(o.bbox[2]-first.bbox[2]) <= 6
                      and not _own_caption(o, captions)]
        if len(candidates) != 1:
            continue
        second = candidates[0]
        following = pages.get(second.page_number)
        if (following is None or len(_column_profile(second, following)) < 3
                or _body_between(first, second, document)):
            continue
        cells = {clean(line.text) for line in _inside_lines(second, following)
                 if line.source == 'native' and len(clean(line.text)) >= 3}
        source = clean(first.text)
        if len(cells) >= 12 and sum(cell in source for cell in cells) >= len(cells)*.8:
            prefixes.add(id(first))
    return [replace(o, kind='text', role='illustrated_table_prefix')
            if id(o) in prefixes else o for o in objects]


def repair_table_identity(objects, document):
    """Return LayoutObjects with evidence-backed table ownership repaired.

    This is intentionally a final preparation pass; it must not be run on raw
    layout before the existing source, caption and physical parent recovery.
    """
    if document is None:
        return list(objects)
    pages={p.number:p for p in document.pages}
    result=_illustrated_table_prefixes(objects,pages,document)
    result=_recover_printed_titles(result,document)
    result=_extend_caption_notes(result,pages)
    result=_join_figure_bands(result,pages)
    result=_declared_figure_parts(result)
    result=_absorb_contained_tables(result)
    result=[replace(o,kind="text",role=identity) if o.kind=="table"
            and (page:=pages.get(o.page_number)) is not None
            and not _own_caption(o,[c for c in result if c.kind=="table_caption"])
            and (identity:=_non_table_frame(o,page)) else o for o in result]
    result=[replace(o,kind="text",role="numbered_math_fragment") if o.kind=="table"
            and (page:=pages.get(o.page_number)) is not None
            and not _own_caption(o,[c for c in result if c.kind=="table_caption"])
            and _numbered_math_fragment(o,page) else o for o in result]
    result=_continue_example_frames(result,pages)
    result=_join_declared_panels(result,pages)
    result=_exclusive_section_titles(result,pages)
    result=_glossary_fragments(result,pages)
    result=_join_continuous_grid_windows(result,pages)
    return _continue_tables(result,pages)

