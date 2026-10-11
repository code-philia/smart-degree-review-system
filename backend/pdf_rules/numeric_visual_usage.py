"""Bind explicit type-omitted numbers to actual visual identity, not distance."""
import re
from .model import Label
from .numbering import normalize_text,normalize_label
from .reference_context import local_reference
from .usage_paragraphs import span_anchor

NUMBER=r'(?:[A-Z]\.?)?[0-9]+(?:[.\-][0-9]+)+'
USAGE=re.compile(r'(?P<cue>可见|结合|参见|详见|参阅|参照)\s*(?P<number>'+NUMBER+r')(?![A-Za-z0-9]|[.\-]\d)')
COMPONENTS=re.compile(r'(?:下文|下面|如下|以下)[^。！？；\d]{0,50}?(?P<category>函数|组件|模块|步骤|阶段|流程|节点)[^。！？；\d]{0,10}?(?P<number>'+NUMBER+r')(?![A-Za-z0-9]|[.\-]\d)')
COUNT=re.compile(r'[一二三四五六七八九十两0-9]+\s*(?:个|种|类|项)')
FOLLOW=re.compile(r'^\s*(?:[，,。.;；:：]|所示|所述|可以|能够|可(?:以|见|知|得)|中(?:的|[，,。]))')


def nonvisual_number_identity(text,match):
    """Explicit value/type declarations outrank accidental visual-number overlap."""
    after=text[match.end():match.end()+120].lstrip(' \t，,.。;；')
    first=re.split(r'[。！？；;]',after,maxsplit=1)[0]
    # These statements name this very numeric entity; axis units describe a
    # visual instead and do not match scalar or nonvisual declarations.
    if re.match(r'^(?:(?:其中|其)\s*)?单位(?:为|是|[:：])',first):return True
    quantity=re.match(r'^(?:这个|该|此)(?:数值|测量值|观测值|量值|平均值|值)',first)
    if quantity and re.search(r'单位|(?:等于|换算为|折算为|相当于|达到)',first):return True
    if re.match(r'^(?:换算为|折算为|相当于)\s*[+\-]?[0-9]',first):return True
    if re.match(r'^(?:这个|该|此)(?:编号|序号|数字)',first) and re.search(
            r'脚注|注释|章节|小节|公式|方程|算法|定理|条款',first):return True
    before=text[max(0,match.start()-120):match.start()]
    same=re.escape(match.group('number'))
    unit=r'(?:毫秒|微秒|秒|分钟|小时|米|厘米|毫米|度|倍|[A-Za-zμµ℃°%][A-Za-z0-9μµ℃°%/^-]*)'
    declaration=re.search(r'(?:为|等于|达到|取值(?:为)?|均值(?:为)?)\s*'+same+r'\s*'+unit+r'(?![A-Za-z0-9])',before)
    arithmetic=re.match(r'^\s*(?:可以|可|能够|用于|用来)?(?:计算|求得|求出|换算|折算|相乘|相除)',text[match.end():])
    return bool(declaration and arithmetic)


def add_numeric_usage(index,eligible_lines,targets,offsets,boundaries,title_fn,shared_phrase):
    def where(line):return offsets[line.page_number]+(line.bbox[1]+line.bbox[3])/2
    def compact(value):return re.sub(r'\s+','',normalize_text(value))
    for line,scope in eligible_lines:
        text=normalize_text(line.text)
        for pattern in (USAGE,COMPONENTS):
            for match in pattern.finditer(text):
                suffix=text[match.end():]
                if not FOLLOW.match(suffix) or not local_reference(text,match):continue
                if nonvisual_number_identity(text,match):continue
                component=pattern is COMPONENTS
                if component and not COUNT.search(match.group(0)):continue
                anchor=span_anchor(line,match.start('number'),match.end('number'))
                position=where(anchor)
                clause=re.split(r'[。！？；]',text[:match.start()])[-1][-100:]
                if not component:
                    clause+=text[match.end():].split('。')[0][:100]
                subject=compact(clause);choices={}
                for kind,target in targets:
                    if target.scope!=scope or target.number!=normalize_label(match.group('number')):continue
                    if abs(target.line.page_number-line.page_number)>1:continue
                    destination=where(target.line)
                    if any(min(position,destination)<boundary<max(position,destination) for boundary in boundaries):continue
                    title=compact(title_fn(target,kind))
                    score=shared_phrase(subject,title)
                    if component:
                        if match.group('category') not in title:continue
                        score=max(score,4)
                    if score<4:continue
                    key=(kind,target.scope,target.number)
                    if key not in choices or score>choices[key][0]:choices[key]=(score,target)
                ranked=sorted(choices.items(),key=lambda pair:-pair[1][0])
                if not ranked or len(ranked)>1 and ranked[0][1][0]<ranked[1][1][0]+2:continue
                (kind,_,_),(_,target)=ranked[0]
                refs=index.graphic_figure_refs if kind=='figure' else index.graphic_table_refs
                value=Label(target.number,anchor,target.scope)
                if not any(r.number==value.number and r.scope==value.scope and r.line==anchor for r in refs):refs.append(value)
