"""Bind independent native display numbers to their own physical figure.

Only the usage view calls this module. It neither relabels shared targets nor
reads PDFs, caches, finding lists or paper identities. A number alone is never
evidence: the local clause must identify a visual display, a measured plot, or
a real native program listing, uniquely within the proved manuscript epoch.
"""
import re
from .numbering import normalize_text,normalize_label
from .reference_identity_repair import _label,_external
from .usage_paragraphs import span_anchor
from .bibliography_scope_resume import _native_glyphs

_NUMBER=r'[0-9]+(?:\s*[.\-]\s*[0-9]+)+'
_BARE=re.compile(r'(?<![A-Za-z0-9_.\-])(?P<number>'+_NUMBER+r')(?![A-Za-z0-9_.\-])')
_LISTING=re.compile(r'(?P<type>代码清单|程序清单|(?<![A-Za-z])(?:code\s+)?listing)\s*(?P<number>'+_NUMBER+r')(?![A-Za-z0-9_.\-])',re.I)
_NONBODY={'header','footer','figure_caption','table_caption','heading','toc','reference','equation','code'}
_VISUAL=re.compile(r'可视化|轨迹|曲线|散点|柱状|热图|截图|示意|visuali[sz]ation|trajectory|curve|scatter|heatmap|screenshot|diagram',re.I)
_TIME=re.compile(r'时延|延迟|耗时|开销|latency|overhead|elapsed\s*time',re.I)
_USE=re.compile(r'举例|示例|展示|显示|所示|给出|分析|比较|对比|illustrat|demonstrat|show|analys|compar',re.I)
_NEGATED=re.compile(r'(?:未|没有|并未|不)(?:被)?(?:使用|引用|讨论|展示|分析|给出)|(?:未|不)用于|\b(?:not|never)\s+(?:used|shown|referenced|discussed|analysed|analyzed)',re.I)
_OTHER_BEFORE=re.compile(r'(?:图|表|式|章|节|算法|协议|功能|定理|附录|第|参数为|实验编号|figure|fig\.?|table|equation|section|chapter|algorithm)\s*$',re.I)
_OTHER_AFTER=re.compile(r'^\s*(?:章|节|条|式|[%％]|ms\b|s\b|秒|毫秒|[x×*/=<>])',re.I)
_CODE=re.compile(r'[{};]|\b(?:def|class|return|import|include|public|void)\b|\b\w+\s*\(|\w+\s*(?:\[[^]]*\])?\s*=|/\*|\*/|^\s*#|^\s*(?:\.{3}|…)\s*$',re.I)
_IDENT=re.compile(r'(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_\-]{2,}(?![A-Za-z0-9_])')
_RESERVED={'void','int','char','return','for','else','if','public','unsigned','uint32_t','null','malloc','free','def','class','import','include'}

def _inside(a,b):return b[0]-.5<=a[0] and b[1]-.5<=a[1] and a[2]<=b[2]+.5 and a[3]<=b[3]+.5
def _identifiers(text):return {m.group().casefold() for m in _IDENT.finditer(text)}-_RESERVED
def _clause(text,start,end):
    left=max((i+1 for i in range(start) if text[i] in '。！？；!?;'),default=0)
    right=next((i for i in range(end,len(text)) if text[i] in '。！？；!?;'),len(text))
    return text[left:right]

def _visual_boxes(index,group,pages):
    caption=min((t.line for t in group),key=lambda l:(l.page_number,l.bbox[1]))
    page=pages.get(caption.page_number)
    if page is None:return []
    previous=max((t.line.bbox[3] for t in index.figures+index.tables if t not in group and
                  t.line.page_number==page.number and t.line.bbox[3]<caption.bbox[1]),default=page.height*.10)
    boxes=[b for b in (*page.images,*page.graphics) if b[2]-b[0]>=60 and b[3]-b[1]>=40
           and previous-1<=b[1] and 0<=caption.bbox[1]-b[3]<=70]
    if not boxes:return []
    union=(min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes))
    centre=(caption.bbox[0]+caption.bbox[2])/2
    return boxes if union[0]-10<=centre<=union[2]+10 else []

def _program(index,group,pages):
    caption=min((t.line for t in group),key=lambda l:(l.page_number,l.bbox[1]))
    page=pages.get(caption.page_number)
    if page is None:return []
    floor=max((t.line.bbox[3] for t in index.figures+index.tables if t not in group and
               t.line.page_number==page.number and t.line.bbox[3]<caption.bbox[1]),default=page.height*.10)
    rows=sorted((l for l in page.lines if _native_glyphs(l) and floor<=l.bbox[1]<l.bbox[3]<=caption.bbox[1]
                 and l.font_size and caption.font_size and l.font_size<=caption.font_size*1.02
                 and l.role not in _NONBODY-{'code'} and not l.bold),key=lambda l:(l.bbox[1],l.bbox[0]),reverse=True)
    code=[];bottom=caption.bbox[1]
    for row in rows:
        text=normalize_text(row.text).strip()
        if not text or text.isdecimal():continue
        if bottom-row.bbox[3]>max(40,row.font_size*3):break
        if not _CODE.search(text):break
        code.append(row);bottom=row.bbox[1]
    joined=' '.join(l.text for l in code)
    if len(code)<3 or not re.search(r'\b\w+\s*\([^)]*\)\s*[:{]|\b(?:def|class|void)\b',joined):return []
    return code

def _compatible_visual(title,clause):
    kinds={m.group().casefold() for m in _VISUAL.finditer(title)}
    return bool(kinds & {m.group().casefold() for m in _VISUAL.finditer(clause)})

def _bare_kind(title,clause,match,text):
    before=text[max(0,match.start()-24):match.start()]
    after=text[match.end():match.end()+24]
    if _OTHER_BEFORE.search(before) or _OTHER_AFTER.match(after):return None
    if not _USE.search(clause):return None
    if _compatible_visual(title,clause) and (
            re.match(r'\s*(?:中|内|所示|所展示|所给出|shows\b|illustrates\b|demonstrates\b)',after,re.I)
            or re.search(r'(?:如|见|参见|as\s+(?:shown|illustrated)\s+in)\s*$',before,re.I)):
        return 'visual'
    # A terminal number attached to a measured-display noun requires native
    # axes and actual named operands as well; arbitrary decimal values fail.
    if _TIME.search(title) and _TIME.search(clause) and re.search(r'(?:时延|延迟|耗时|开销|latency|overhead)\s*$',before,re.I) and re.match(r'\s*[。.;；]',after):return 'time_plot'
    return None

def display_references(index,groups,paragraphs,zone):
    """Yield (native reference, physical group, criterion) without mutation."""
    pages={p.number:p for p in index.document.pages}
    uses=[]
    for line,state in paragraphs:
        if state[0]!='body' or not _native_glyphs(line) or line.role in _NONBODY:continue
        text=normalize_text(line.text)
        typed=list(_LISTING.finditer(text));typed_spans=[m.span() for m in typed]
        matches=[(m,'code') for m in typed]+[(m,'bare') for m in _BARE.finditer(text) if not any(a<=m.start()<b for a,b in typed_spans)]
        for match,kind in matches:
            clause=_clause(text,match.start(),match.end())
            if _NEGATED.search(clause):continue
            number=normalize_label(re.sub(r'\s+','',match.group('number')))
            transformed=text[:match.start()]+'图 '+number+text[match.end():]
            prefix=text[max(0,match.start()-65):match.start()]
            if _external(transformed,'figure',number) or re.search(r'(?:文献|参考文献|论文|from|in)\s*\[[^]]+\][^。；;]{0,20}$',prefix,re.I):continue
            candidates=[g for g in groups if any(t.number==number and zone(t.line)==state for t in g)]
            if len(candidates)!=1:continue
            group=candidates[0];title=' '.join(normalize_text(t.line.text) for t in group)
            reference=_label(number,span_anchor(line,match.start('number'),match.end('number')),state[0])
            # Independent body ink inside a display/program is not promoted
            # by a wide line or another same-sized internal label.
            if any(_inside(reference.line.bbox,b) for b in (*pages[line.page_number].images,*pages[line.page_number].tables,*pages[line.page_number].graphics)
                   if b[2]-b[0]>=30 and b[3]-b[1]>=15):continue
            if kind=='code':
                rows=_program(index,group,pages)
                ownership=text[match.start():]
                # A following sentence can explain the same printed program.
                # Stop when it explicitly changes to another physical object.
                boundary=re.search(r'(?:另(?:一|一个|一段)|其他)(?:个|段)?(?:对象|程序|清单|代码)|(?:图|表|代码清单|程序清单)\s*'+_NUMBER,ownership[match.end()-match.start():],re.I)
                if boundary:ownership=ownership[:match.end()-match.start()+boundary.start()]
                if (not rows or len(_identifiers(' '.join(l.text for l in rows))&_identifiers(ownership))<2
                        or any(t.number==number and zone(t.line)==state and re.search(r'代码|程序|\b(?:listing|code|program)\b',t.line.text,re.I) for t in index.tables)):
                    continue
                program_box=(min(l.bbox[0] for l in rows),min(l.bbox[1] for l in rows),max(l.bbox[2] for l in rows),max(l.bbox[3] for l in rows))
                if _inside(reference.line.bbox,program_box):continue
                criterion='independent native code listing; unique physical program'
            else:
                visual_kind=_bare_kind(title,clause,match,text)
                boxes=_visual_boxes(index,group,pages)
                if not visual_kind or not boxes:continue
                competitors=[t for t in index.tables if t.number==number and zone(t.line)==state
                             and (_compatible_visual(normalize_text(t.line.text),clause) or visual_kind=='time_plot' and _TIME.search(t.line.text))]
                if competitors:continue
                if visual_kind=='time_plot':
                    box=(min(b[0] for b in boxes)-35,min(b[1] for b in boxes)-15,max(b[2] for b in boxes)+35,max(b[3] for b in boxes)+22)
                    native=[l.text for l in pages[group[0].line.page_number].lines if l.source=='native' and _inside(l.bbox,box)]
                    if not any(re.search(r'(?:latency|time|时延|延迟|耗时)\s*[（(]?\s*(?:ms|s|μs|秒|毫秒)',t,re.I) for t in native):continue
                    if len(_identifiers(' '.join(native))&_identifiers(text))<2:continue
                criterion='independent native bare display; unique physical visual'
            uses.append((reference,group,criterion))
    return uses
