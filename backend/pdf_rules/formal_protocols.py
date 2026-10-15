"""Identify framed operational definitions independently of parser block labels."""
import re
from .numbering import normalize_text

HEADER=re.compile(r'^(?:Protocol|Functionality|Procedure|协议|理想功能|子例程)\s*(?:[A-Z][.]?)?[0-9]+(?:[.\-][0-9]+)*\s*[:：]',re.I)
OPERATIONS=(r'收到|\breceive\b',r'设置|\bset\b',r'检查|\bcheck\b',
            r'计算|\bcompute\b',r'发送|\bsend\b',r'选择|\bselect\b',
            r'返回|\breturn\b',r'拒绝|\breject\b',r'令|\blet\b')


def fraction(a,b):
    area=max(0,a[2]-a[0])*max(0,a[3]-a[1])
    overlap=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    return overlap/max(1,area)


def physical_frame(obj,page):
    return any(fraction(obj.bbox,frame)>=.85 and fraction(frame,obj.bbox)>=.7
               for frame in page.graphics)


def formal_header(obj,page):
    return next((line for line in page.lines
                 if obj.bbox[0]-20<=line.bbox[0]<=obj.bbox[2]
                 and obj.bbox[1]-35<=line.bbox[1]<=obj.bbox[1]+35
                 and HEADER.match(normalize_text(line.text).strip())),None)


def formal_protocol_frame(obj,page):
    if not physical_frame(obj,page) or not formal_header(obj,page):return False
    lines=[l for l in page.lines if fraction(l.bbox,obj.bbox)>=.85]
    text=' '.join(normalize_text(l.text) for l in lines)
    operations=sum(bool(re.search(pattern,text,re.I)) for pattern in OPERATIONS)
    bindings=text.count('=')+text.count('←')
    interface=bool(re.search(r'输入|输出|\bInput\b|\bOutput\b',text,re.I))
    return operations>=3 and bindings>=2 and interface



def formal_protocol_continuation(obj,page,objects,pages,captions):
    """A framed tail retains a proved preceding operational definition.

    Require matching widths, printable margins and the symbolic definition
    name. A local table title establishes a new identity instead.
    """
    from .caption_rules import _matches
    if page.number-1 not in pages or obj.bbox[1]>page.height*.18 or not physical_frame(obj,page):return False
    if any(c.kind==obj.kind+'_caption' and _matches(obj,c) for c in captions):return False
    previous=pages[page.number-1]
    width=obj.bbox[2]-obj.bbox[0]
    text=''.join(normalize_text(l.text).replace(' ','') for l in page.lines if fraction(l.bbox,obj.bbox)>=.8)
    for candidate in objects:
        if (candidate.kind not in {'figure','table'} and not (candidate.kind=='text' and candidate.role=='code_body')) or candidate.page_number!=previous.number:continue
        if candidate.bbox[3]<previous.height*.8 or not formal_protocol_frame(candidate,previous):continue
        if any(c.kind==candidate.kind+'_caption' and _matches(candidate,c) for c in captions):continue
        other_width=candidate.bbox[2]-candidate.bbox[0]
        if min(width,other_width)/max(width,other_width)<.9:continue
        if abs((obj.bbox[0]+obj.bbox[2]-candidate.bbox[0]-candidate.bbox[2])/2)>page.width*.06:continue
        heading=normalize_text(formal_header(candidate,previous).text)
        tail=HEADER.sub('',heading).strip()
        identifiers=re.findall(r'[A-Za-zΠπ][A-Za-z0-9_ΠπΣ\-]{2,}',tail)
        if identifiers and identifiers[-1] in text:return True
    return False
