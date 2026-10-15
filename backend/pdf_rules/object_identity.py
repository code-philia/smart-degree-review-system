"""Resolve layout object type using physical envelopes and explicit local titles."""
from dataclasses import replace
import re
from .numbering import normalize_text
from .mineru_layout import LayoutObject
from .caption_rules import _matches, _horizontal_overlap
from .native_layout import _union_area

ALGORITHM = re.compile(r'^(?:续(?:接)?\s*|(?:continued|continuation\s+of)\s+)?(?:算法|Algorithm)\s*(?:[A-Z]\.?)?\d+(?:[.\-]\d+)*', re.I)
GLOSSARY = re.compile(r'^(?:中英文术语对照表|术语对照表|缩略语(?:对照)?表|符号(?:对照)?表|List of (?:Abbreviations|Symbols))$', re.I)

def area(box):return max(0,box[2]-box[0])*max(0,box[3]-box[1])

def coverage(box, regions):
    clips=[]
    for b in regions:
        clip=(max(box[0],b[0]),max(box[1],b[1]),min(box[2],b[2]),min(box[3],b[3]))
        if area(clip)>0:clips.append(clip)
    size=area(box)
    return _union_area(clips)/size if size>0 else 0.0

def algorithm_frame(obj,page):
    lines=[line for line in page.lines if obj.bbox[0]-3 <= line.bbox[0] <= obj.bbox[2]
           and obj.bbox[1]-30 <= line.bbox[1] <= obj.bbox[3]]
    head=any(ALGORITHM.match(normalize_text(line.text).strip())
             and line.bbox[1] <= obj.bbox[1]+30 for line in lines)
    text=' '.join(normalize_text(line.text) for line in lines)
    inputs = bool(re.search(r'\b(?:Input|Require|Ensure|Output|Data|Result)\s*[:：]|(?:输入|输出)\s*[:：]',text,re.I))
    statements = sum(bool(re.search(r'^(?:\d+\s*[:.]?\s*)?(?:for(?:each)?\b.+do(?:\s|$)|while\b.+do(?:\s|$)|if\b.+then(?:\s|$)|end(?:\s|$)|return\b)',normalize_text(line.text).strip(),re.I)) for line in lines)
    # Original PDFs often paint line numbers in a separate left column.
    # Count physical code rows, rather than requiring a flattened '20 statement'.
    assignments = sum('←' in normalize_text(line.text) for line in lines)
    numbered=0
    for line in lines:
        text=normalize_text(line.text).strip()
        if re.match(r'^\d+\s*[:.]?\s+\S',text):
            numbered+=1;continue
        if re.fullmatch(r'\d+\s*[:.]?',text):continue
        if any(re.fullmatch(r'\d+\s*[:.]?',normalize_text(n.text).strip())
               and 0<=line.bbox[0]-n.bbox[2]<=40
               and min(line.bbox[3],n.bbox[3])-max(line.bbox[1],n.bbox[1])
                   >=min(line.bbox[3]-line.bbox[1],n.bbox[3]-n.bbox[1])*.5 for n in lines):
            numbered+=1
    return head and ((inputs and (statements>=2 or assignments>=3))
                     or (not inputs and numbered>=3 and statements>=2 and assignments>=1)
                     or numbered_instruction_namespace(lines))


def numbered_instruction_namespace(lines):
    """Typed algorithm title plus an ordered instruction column, not data cells.

    Natural-language procedures have no mandatory Input/return/assignment
    syntax. Their original bold heading and continuous step rows supply type
    identity. A plain algorithm mention, numeric results or parallel data
    cells cannot supply that identity.
    """
    def same_row(a,b):
        return min(a.bbox[3],b.bbox[3])-max(a.bbox[1],b.bbox[1]) >= .7*min(a.bbox[3]-a.bbox[1],b.bbox[3]-b.bbox[1])
    headings=[line for line in lines if line.bold and ALGORITHM.match(normalize_text(line.text).strip())
              and not any(other is not line and same_row(line,other) and other.text.strip() for other in lines)]
    if not headings:return False
    rows=[];bodies=[]
    for line in lines:
        text=normalize_text(line.text).strip()
        joined=re.match(r'^(\d{1,3})(?:\s*[:.](?!\d)\s*|\s+)(\S.+)$',text)
        members=[line]
        if joined:
            number=int(joined.group(1));body=joined.group(2)
        else:
            standalone=re.fullmatch(r'(\d{1,3})\s*[:.]?',text)
            if not standalone:continue
            choices=[other for other in lines if other is not line and same_row(line,other)
                     and 0<=other.bbox[0]-line.bbox[2]<=40 and other.text.strip()]
            if not choices:continue
            right=min(choices,key=lambda other:other.bbox[0])
            number=int(standalone.group(1));body=normalize_text(right.text).strip();members.append(right)
        if len(re.findall(r'[^\W\d_]',body,re.U))<2:continue
        if any(other not in members and same_row(line,other) and other.text.strip() for other in lines):
            return False  # Numeric/parameter columns retain table identity.
        if any(number==n and same_row(line,old) for n,old in rows):continue
        rows.append((number,line));bodies.append(body)
    if len(rows)<3:return False
    # Flattened OCR can erase the physical name/value column boundary.
    # Repeated scalar parameter records are data, even with a nearby
    # algorithm heading and ordered row indices; letter count is not action
    # semantics. Full instruction sentences do not match this record grammar.
    scalar=r'[+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?'
    identifier=r'[^\W\d][\w\-]*'
    values=scalar+r'(?:\s+'+scalar+r')*'
    pairs=[re.fullmatch(identifier+r'(?:\s+'+identifier+r')*\s+'
                       r'(?P<value>'+values+r'|'+identifier+r')',body) for body in bodies]
    actions=re.compile(
        r'^(?:set|initiali[sz]e|update|compute|calculate|predict|search|sample|train|select|choose|'
        r'insert|delete|replace|generate|collect|compare|evaluate|obtain|output|sort|merge|normalize|return)\b'
        r'|^(?:施加|设置|初始化|更新|计算|预测|搜索|采样|训练|选择|生成|收集|比较|评估|获取|输出|排序|合并|归一化)',re.I)
    numeric_records=sum(bool(pair and re.fullmatch(values,pair.group('value'))) for pair in pairs)
    if all(pairs) and numeric_records>=2 and not any(actions.search(body) for body in bodies):return False
    rows.sort(key=lambda pair:pair[1].bbox[1])
    numbers=[number for number,_ in rows]
    if numbers[0] not in (0,1) or numbers!=list(range(numbers[0],numbers[0]+len(numbers))):return False
    return any(heading.bbox[3]<=rows[0][1].bbox[1]+2 for heading in headings)


def refine_targets(objects,document):
    pages={p.number:p for p in document.pages}
    from .raster_text import raster_heading_regions
    heading_regions=raster_heading_regions(document,objects)
    captions=[o for o in objects if o.kind.endswith('_caption')]
    corrected=[]
    for obj in objects:
        if obj.kind=='figure':
            page=pages[obj.page_number]
            candidate=replace(obj,kind='table')
            titles=[c for c in captions if c.kind=='table_caption' and _matches(candidate,c)]
            own_figures=[c for c in captions if c.kind=='figure_caption' and _matches(obj,c)]
            embedded_title = any(c.role == "image_caption" and c.page_number == obj.page_number
                                 and 0 <= obj.bbox[1]-c.bbox[3] <= 40 for c in titles)
            if (titles and not own_figures and (coverage(obj.bbox,page.tables)>=.7 or embedded_title)
                    and any(not any(o.kind=='table' and o.page_number==obj.page_number and _matches(o,title) for o in objects) for title in titles)):
                obj=replace(obj,kind='table',role='captioned_native_table')
        corrected.append(obj)
    objects=corrected
    charts=[o for o in objects if o.kind=='figure' and o.role in {'chart_body','image_body','native_flow_diagram'}]
    from .layout_context import _panel_group
    chart_envelopes=_panel_group(charts,document,captions)
    result=[]
    for obj in objects:
        from .native_equations import native_numbered_equation
        if native_numbered_equation(obj,pages[obj.page_number],document,captions):
            continue
        if (obj.kind=='figure' and any(coverage(obj.bbox,[box])>=.9 for box in heading_regions.get(obj.page_number,()))
                and not any(c.kind=='figure_caption' and _matches(obj,c) for c in captions)):
            continue
        if obj.kind in {'figure', 'table'} and any(
                equation.role == 'interline_equation' and equation.page_number == obj.page_number
                and coverage(obj.bbox,[equation.bbox]) >= .9
                and (coverage(equation.bbox,[obj.bbox]) >= .9
                     or re.search(r'\\tag\s*\{[A-Z]?\d+(?:[.\-]\d+)*\}',equation.text))
                and not any(c.kind==obj.kind+'_caption' and _matches(obj,c) for c in captions)
                for equation in objects):
            # Glyph XObjects inside a declared numbered equation inherit its
            # equation identity. They are not separately captioned figures.
            continue
        if obj.kind in {'figure', 'table'} and code_listing(obj,pages[obj.page_number],objects,captions):
            continue
        from .formal_protocols import formal_protocol_continuation
        if obj.kind in {'figure','table'} and formal_protocol_continuation(obj,pages[obj.page_number],objects,pages,captions):
            continue
        if obj.kind!='table':
            result.append(obj);continue
        page=pages[obj.page_number]
        own=[c for c in captions if c.kind=='table_caption' and _matches(obj,c)]
        if source_title_window(obj, objects, captions, page, own):
            continue
        own_nearer=[title for title in own if not any(o.kind=='table' and o!=obj and o.page_number==obj.page_number
                    and _matches(o,title) and min(abs(o.bbox[1]-title.bbox[3]),abs(title.bbox[1]-o.bbox[3]))
                    < min(abs(obj.bbox[1]-title.bbox[3]),abs(title.bbox[1]-obj.bbox[3])) for o in objects)]
        if not own_nearer and algorithm_frame(obj,page):continue
        # Table-shaped components embedded in a larger captioned raster figure
        # inherit the identity of that figure; they are not standalone tables.
        parents=[o for o in objects if o.kind=='figure' and o.page_number==obj.page_number
                 and coverage(obj.bbox,[o.bbox])>=.93 and area(o.bbox)>=area(obj.bbox)*.95]
        if not own and any(any(c.kind=='figure_caption' and _matches(parent,c) for c in captions) for parent in parents):continue
        # Sliding native rule windows may bridge two real tables and a title.
        bodies=[o for o in objects if o.kind=='table' and o.role=='table_body' and o.page_number==obj.page_number]
        crossed=[o for o in bodies if _horizontal_overlap(obj,o)>=.8 and coverage(obj.bbox,[o.bbox])>0 and coverage(obj.bbox,[o.bbox])<.93]
        interior_title=any(c.kind=='table_caption' and c.role=='table_caption' and c.page_number==obj.page_number
                           and _horizontal_overlap(obj,c)>=.5
                           and obj.bbox[1]<c.bbox[1]<c.bbox[3]<obj.bbox[3] for c in captions)
        if obj.role=='native_table' and len(crossed)>=2 and interior_title:continue
        # A three-line detector also sees graph axes/legends. The cloud's
        # explicit chart regions supply independent object identity here.
        if obj.role=='native_table' and coverage(obj.bbox,[c.bbox for c in chart_envelopes if c.page_number==obj.page_number]) >= .75:
            continue
        if obj.role == 'native_table' and not own:
            visible_parents = [o for o in objects if o.kind == 'figure' and o.page_number == obj.page_number
                               and coverage(obj.bbox,[o.bbox]) >= .2
                               and any(c.kind == 'figure_caption' and _matches(o,c) for c in captions)]
            if visible_window_inside_figure(obj,visible_parents,document):
                continue
        marks=[m for m in page.legend_marks if obj.bbox[0]<=(m[0]+m[2])/2<=obj.bbox[2]
               and obj.bbox[1]<=(m[1]+m[3])/2<=obj.bbox[3]]
        close_charts=[c for c in charts if c.page_number==obj.page_number and _horizontal_overlap(obj,c)>=.5
                      and 0<=c.bbox[1]-obj.bbox[3]<=20]
        text_rows=[]
        for line in page.lines:
            cx=(line.bbox[0]+line.bbox[2])/2;cy=(line.bbox[1]+line.bbox[3])/2
            if obj.bbox[0]<=cx<=obj.bbox[2] and obj.bbox[1]<=cy<=obj.bbox[3] and line.text.strip():
                if not any(abs(cy-y)<=4 for y in text_rows):text_rows.append(cy)
        aligned_marks=[m for m in marks if len(text_rows)==1 and m[1]-3<=text_rows[0]<=m[3]+3]
        if (not own and len(aligned_marks)>=2 and len(text_rows)==1 and obj.bbox[3]-obj.bbox[1]<=40 and close_charts
                and obj.text.strip() and not re.search(r'\d',obj.text)):continue
        graphic_parts=[c for c in charts if c.page_number==obj.page_number and _horizontal_overlap(obj,c)>=.5
                       and coverage(obj.bbox,[c.bbox])>=.05]
        graphic_coverage=coverage(obj.bbox,[c.bbox for c in graphic_parts])
        inside_figure_title=any(c.kind=='figure_caption' and c.page_number==obj.page_number
            and _horizontal_overlap(obj,c)>=.25 and obj.bbox[1]<c.bbox[1]<c.bbox[3]<obj.bbox[3] for c in captions)
        if obj.role=='native_table' and not own:
            if (graphic_coverage>=.6 and (len(marks)>=2 or inside_figure_title)):
                continue
            # A figure title inside a native rule window identifies a window
            # crossing chart axes and their caption. Mere edge overlap with two
            # charts cannot discard a real table in the intervening space.
            plot_window = (inside_figure_title and bool(graphic_parts)) or (len(graphic_parts)>=2 and graphic_coverage>=.4)
            if plot_window and not any(coverage(obj.bbox,[body.bbox])>=.2 for body in bodies):
                continue

        figure=replace(obj,kind='figure')
        other=[c for c in captions if c.kind=='figure_caption' and _matches(figure,c)]
        # A raster table retains its identity when it has a table title. Only
        # switch a table-shaped diagram with figure-title plus image evidence.
        images=page.images
        if (not own and other
                and any(not any(c.kind=='figure' and coverage(c.bbox,[obj.bbox]) < .93
                                and c.page_number==obj.page_number and _matches(c,title)
                                for c in objects) for title in other)):
            result.append(replace(obj,kind='figure',role='captioned_native_diagram'));continue
        # UML class/enum boxes are diagrams, even when no title was provided.
        if (len(re.findall(r'\b(?:Class|Enum)\s+[A-Za-z_]\w*\s*\{',obj.text,re.I))>=2
                and re.search(r'\w+\s*:\s*(?:String|Integer|Double|Set|Map|Vector|boolean)',obj.text,re.I)):
            result.append(replace(obj,kind='figure',role='uml_diagram'));continue
        result.append(obj)
    for page in document.pages:
        for line in page.lines:
            if GLOSSARY.fullmatch(normalize_text(line.text).strip()):
                result.append(LayoutObject('table_caption',page.number,line.bbox,line.text,page.width,page.height,role='unnumbered_heading'))
    return result


def source_title_window(obj, objects, captions, page, own):
    """Consume a rule window crossing the verified title of one source table.

    A parser parent is supporting evidence, not permission to merge all its
    children. The native text must confirm the external title, and every text
    row outside the source body must belong to that title. Separate table
    titles, cells above the body, mismatched source parents and uncertain
    native text retain their ordinary table obligation.
    """
    if obj.role != 'native_table' or own:
        return False
    def text(value):return re.sub(r'\s+', '', normalize_text(value))
    bodies=[body for body in objects if body.kind=='table' and body.role=='table_body'
            and body.page_number==obj.page_number and body.parent_id
            and body.parent_kind=='table' and body.parent_bbox is not None
            and coverage(body.bbox,[body.parent_bbox])>=.9
            and _horizontal_overlap(obj,body)>=.85
            and 0<coverage(obj.bbox,[body.bbox])<.93]
    for body in bodies:
        titles=[title for title in captions if title.kind=='table_caption'
                and title.page_number==body.page_number
                and title.parent_id==body.parent_id and title.parent_kind=='table'
                and _matches(body,title)
                and obj.bbox[1]<title.bbox[1]<title.bbox[3]<obj.bbox[3]
                and title.bbox[3]<=body.bbox[1]]
        for title in titles:
            confirmed=[line for line in page.lines if line.source=='native'
                       and text(line.text)==text(title.text)
                       and coverage(line.bbox,[title.bbox])>=.8]
            if not confirmed:
                continue
            # Even a partly intersecting data row is evidence against removing
            # a native window. A broad parser caption box is not text ownership.
            outside=[line for line in page.lines if line.text.strip()
                     and coverage(line.bbox,[obj.bbox])>0
                     and coverage(line.bbox,[body.bbox])<.8]
            if outside and all(any(text(line.text)==text(native.text)
                                   and coverage(line.bbox,[native.bbox])>=.8
                                   for native in confirmed) for line in outside):
                return True
    return False


def visible_window_inside_figure(obj, parents, document):
    """Discard a native rule window only when all its visible ink is a figure.

    PDF drawing commands can extend past an XObject clipping path. Rendering
    checks the original visible page, so invisible vector geometry cannot
    invent an extra table in the whitespace beside a diagram.
    """
    from pathlib import Path
    if not parents or not Path(document.path).is_file():
        return False
    import pymupdf
    import numpy as np
    with pymupdf.open(document.path) as pdf:
        page = pdf[obj.page_number-1]
        page.set_rotation(0)
        clip = pymupdf.Rect(obj.bbox) & page.rect
        if clip.is_empty:
            return False
        scale = min(2, 800/max(clip.width,clip.height))
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),clip=clip,colorspace=pymupdf.csGRAY,alpha=False)
        ink = np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width) < 180
        total = int(ink.sum())
        if total < 20:
            return False
        inside = np.zeros(ink.shape,dtype=bool)
        for parent in parents:
            b=parent.bbox
            left=max(0,int((b[0]-2)*scale)-pix.x)
            top=max(0,int((b[1]-2)*scale)-pix.y)
            right=min(pix.width,int((b[2]+2)*scale)-pix.x+1)
            bottom=min(pix.height,int((b[3]+2)*scale)-pix.y+1)
            if left<right and top<bottom:
                inside[top:bottom,left:right]=True
        return int((ink & ~inside).sum()) <= max(5,total*.01)


def _code_syntax(lines):
    """Count executable syntax and structured data, not ordinary prose words."""
    texts = [normalize_text(line).strip() for line in lines]
    properties = sum(bool(re.match(r'^[\"\'][^\"\']+[\"\']\s*:', text)) for text in texts)
    statements = sum(bool(re.match(
        r'^(?:\d+\s+)?(?:async\s+def\b|def\s+\w+\s*\(|(?:if|elif|while|for)\b.+:|return\s+\w+|\w[\w.]*\s*=\s*.+|[\w.]+\(.*\)[;,]?$)', text)) for text in texts)
    braces = sum(text in {'{','}','},','[',']','],'} for text in texts)
    return properties >= 3 and braces >= 2 or statements >= 3


def prompt_instruction_frame(obj,page):
    """Verify a single-column instruction template in its physical envelope.

    A parser can separate a shaded heading from the body. The envelope owning
    both supplies its identity; wrapped short lines do not create columns.
    """
    frames=[box for box in page.graphics if coverage(obj.bbox,[box])>=.85
            and coverage(box,[obj.bbox])>=.8]
    for frame in sorted(frames,key=area):
        lines=[l for l in page.lines if coverage(l.bbox,[frame])>=.9 and l.text.strip()]
        heads=[l for l in lines if 0<=l.bbox[1]-frame[1]<=40
               and re.search(r'提示词|\bprompt\b',normalize_text(l.text),re.I)]
        if not heads:continue
        body=[l for l in lines if l.bbox[1]>min(h.bbox[3] for h in heads)]
        width=frame[2]-frame[0]
        wide=[l for l in body if l.bbox[2]-l.bbox[0]>=width*.6
              and len(re.findall(r'[A-Za-z\u4e00-\u9fff]',l.text))>=12]
        if len(wide)<3:continue
        lefts=[l.bbox[0] for l in body]
        single_column=max(lefts)-min(lefts)<=width*.12
        if not single_column:continue
        text=' '.join(normalize_text(l.text) for l in body)
        instructions=re.findall(r'你是|你的任务|请(?:检查|验证|分析|输出|回答)|'
                                r'\bYou are\b|\bYour task\b|\bPlease\b|\bAct as\b',text,re.I)
        headers=sum(bool(re.search(pattern,text,re.I)) for pattern in
                    (r'Core Task\s*:',r'(?:Judging |Evaluation )?Criteria\s*:',r'Workflow\s*:'))
        imperatives=sum(bool(re.match(r'^\s*\d+[.]\s*(?:Ensure|Prioritize|Focus|Strictly follow|Avoid|Exclude|Request|Analyze|Identify)\b',normalize_text(l.text),re.I)) for l in body)
        if len(instructions)>=2 or (instructions and headers==3 and imperatives>=3):return True
    return False


def code_listing(obj, page, objects, captions):
    """Explicit listings and native line windows around code are not figures/tables."""
    def title_gap(body,title):
        return min(abs(body.bbox[1]-title.bbox[3]),abs(title.bbox[1]-body.bbox[3]))
    own_titles = [c for c in captions if c.kind == obj.kind+'_caption' and _matches(obj,c)
                  and not any(peer != obj and peer.kind == obj.kind and _matches(peer,c)
                              and title_gap(peer,c) < title_gap(obj,c) for peer in objects)]
    if own_titles:
        return False  # A deliberately illustrated code screenshot remains a figure.
    from .program_identity import typed_program_listing
    if typed_program_listing(obj,page,objects):
        return True
    if prompt_instruction_frame(obj,page):
        return True
    from .formal_protocols import formal_protocol_frame
    if formal_protocol_frame(obj,page):
        return True
    inside = [l for l in page.lines if coverage(l.bbox,[obj.bbox]) >= .85]
    text = normalize_text(obj.text).strip()
    if not text:
        text = next((normalize_text(peer.text).strip() for peer in objects
                     if peer.page_number == obj.page_number and peer.text.strip()
                     and coverage(peer.bbox,[obj.bbox]) >= .9
                     and coverage(obj.bbox,[peer.bbox]) >= .9), '')
    definitions = re.fullmatch(r'(?:\s*(?:class|enum|struct)\s+[A-Za-z_]\w*\s*\{[^{}]+\}\s*;?)+', text, re.I)
    if definitions and len(re.findall(r'\b\w+\s*:\s*[A-Za-z_]\w*',text)) >= 3:
        return True  # Braced declarations, without relationship edges, are code.
    local_texts = [normalize_text(l.text).strip() for l in inside if l.text.strip()]
    syntax = re.compile(r'^(?:auto\s+(?:\w+|\[[^]]+\])\s*=|(?:if|for|while)\s*\(|[\w.]+\([^;]*\);\s*$|\w+\s+\w+\{[^;]+\};\s*$|[\w:]+\s*,.+\);\s*$|\([^;]+\);\s*$)',re.I)
    code_lines = sum(bool(syntax.search(t)) for t in local_texts)
    if obj.role != 'table_body' and code_lines >= 3 and code_lines >= len(local_texts)*.7:
        return True
    listing = [l for l in page.lines if re.fullmatch(r'Listing\s*\d+(?:[.\-]\d+)*(?:\s*(?:[:：.]\s*)?\S.*)?',normalize_text(l.text).strip(),re.I)
               and (0 <= l.bbox[1]-obj.bbox[3] <= 50 or 0 <= obj.bbox[1]-l.bbox[3] <= 50)
               and l.bbox[0] < obj.bbox[2] and l.bbox[2] > obj.bbox[0]]
    log = any(re.fullmatch(r'[=\-]{5,}',l.text.strip()) for l in inside) and any(
        re.match(r'^\s*[\[【].+[\]】]',l.text) for l in inside)
    if listing and obj.role != 'table_body' and (_code_syntax([l.text for l in inside]) or log):
        return True
    if obj.role != 'native_table':
        return False
    bodies = [o for o in objects if o.kind == 'table' and o.role == 'table_body'
              and o.page_number == obj.page_number and coverage(o.bbox,[obj.bbox]) >= .2]
    if bodies:
        return False
    code = [o for o in objects if o.role == 'code_body' and o.page_number == obj.page_number
            and coverage(o.bbox,[obj.bbox]) >= .9 and coverage(obj.bbox,[o.bbox]) >= .3
            and (_code_syntax(o.text.splitlines()) or _literal_template(o.text))]
    if not code:
        return False
    outside = [l for l in inside if not any(coverage(l.bbox,[o.bbox]) >= .8 for o in code)]
    # A native sliding rule window may begin at the previous code frame's
    # bottom border, including its short introductory sentence and whitespace.
    return len(outside) <= 2 and all(l.bbox[3] <= min(o.bbox[1] for o in code) for l in outside)


def _literal_template(text):
    """A parsed code frame with placeholders and instructions is a template."""
    placeholder=bool(re.search(r'\{[A-Za-z_][A-Za-z0-9_ ]{0,50}\}|<[A-Za-z_][A-Za-z0-9_]*>',text))
    instruction=bool(re.search(r'(?m)^\s*(?:Please\b|You (?:are|will|should)\b|请)',text,re.I))
    return placeholder and instruction
