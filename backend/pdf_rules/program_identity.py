"""Verify explicitly typed source listings against their physical contents."""
import re
from .numbering import normalize_text

_TITLE = re.compile(r"^(?:Listing|Code|代码(?:清单)?)\s*\d+(?:[.\-]\d+)*(?:\s*(?:[:：.]\s*)?\S.*)?$",re.I)
_NARRATIVE = re.compile(r"\b(?:shows?|illustrates?|describes?|presents?|is|are|was|were)\b",re.I)


def instruction_template(text):
    """An instruction schema requires task, input/output and real placeholders."""
    placeholders=re.findall(r"\{[A-Za-z_][A-Za-z0-9_ ]{0,50}\}",text)
    task=bool(re.search(r"当前任务|你的任务|你现在|任务要求|\b(?:Your task|You are|Task\s*:)\b",text,re.I))
    inputs=bool(re.search(r"[\[【]输入[\]】]|\bInput\s*:",text,re.I))
    outputs=bool(re.search(r"[\[【]输出(?:要求)?[\]】]|\bOutput\s*:",text,re.I))
    return len(set(placeholders))>=2 and task and inputs and outputs


def _c_declaration(text):
    match=re.fullmatch(r"\s*(?:typedef\s+)?struct\s+[A-Za-z_]\w*\s*\{(?P<body>[^{}]+)\}\s*(?:[A-Za-z_]\w*)?\s*;?\s*",text,re.I)
    if not match:return False
    fields=[field.strip() for field in match.group('body').split(';') if field.strip()]
    return len(fields)>=3 and all(re.fullmatch(r"(?:const\s+)?[A-Za-z_]\w*(?:::\w+)*(?:\s+|\s*[*&]\s*)[A-Za-z_]\w*(?:\s*\[\d*\])?",field) for field in fields)


def native_statement_frame(obj,page):
    """A one-row source statement explained in prose is not a result table."""
    from .layout_context import containment
    lines=[l for l in page.lines if l.text.strip() and containment(l.bbox,obj.bbox)>=.8]
    if len(lines)!=1 or lines[0].source!='native':return False
    line=lines[0]
    if obj.bbox[3]-obj.bbox[1]>max(24,(line.bbox[3]-line.bbox[1])*2):return False
    compact=lambda value:re.sub(r'\s+','',normalize_text(value))
    text=compact(line.text)
    if text!=compact(obj.text):return False
    match=re.fullmatch(r'(?P<name>[A-Za-z_]\w*)\((?:[&*]?[A-Za-z_]\w*|[0-9]+)(?:,(?:[&*]?[A-Za-z_]\w*|[0-9]+))+\);',text)
    if match is None:return False
    return any(l.source=='native' and 0<=obj.bbox[1]-l.bbox[3]<=100
               and l.bbox[2]-l.bbox[0]>=page.width*.6
               and match.group('name') in l.text
               and re.search(r'函数|调用|代码|语句|\b(?:function|call|code)\b',l.text,re.I)
               for l in page.lines)


def typed_program_listing(obj,page,objects):
    """A nearby mention cannot change identity: title plus body syntax is required."""
    titles=[]
    for line in page.lines:
        text=normalize_text(line.text).strip()
        if not _TITLE.fullmatch(text) or _NARRATIVE.search(text):continue
        if not (obj.bbox[0]<=(line.bbox[0]+line.bbox[2])/2<=obj.bbox[2]):continue
        inside=(obj.bbox[1]<=line.bbox[1]<=obj.bbox[1]+45)
        gap=min(abs(obj.bbox[1]-line.bbox[3]),abs(line.bbox[1]-obj.bbox[3]))
        if not inside and gap>45:continue
        nearer=any(peer is not obj and peer.kind in {'figure','table'}
                   and peer.page_number==obj.page_number
                   and peer.bbox[0]<=(line.bbox[0]+line.bbox[2])/2<=peer.bbox[2]
                   and min(abs(peer.bbox[1]-line.bbox[3]),abs(line.bbox[1]-peer.bbox[3]))<gap
                   for peer in objects)
        if not nearer:titles.append(line)
    if not titles:return False
    peers=[o.text for o in objects if o.page_number==obj.page_number and o.text.strip()
           and o.bbox[0]>=obj.bbox[0]-3 and o.bbox[2]<=obj.bbox[2]+3
           and o.bbox[1]>=obj.bbox[1]-3 and o.bbox[3]<=obj.bbox[3]+3]
    lines=[line.text for line in page.lines if obj.bbox[0]-3<=line.bbox[0]
           and line.bbox[2]<=obj.bbox[2]+3 and obj.bbox[1]<=line.bbox[1]
           and line.bbox[3]<=obj.bbox[3]]
    native=' '.join(re.sub(r'^\s*\d+\s*','',normalize_text(line)).strip() for line in lines)
    return any(_c_declaration(normalize_text(text).strip()) or instruction_template(text)
               for text in [obj.text,native,*peers])
