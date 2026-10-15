"""Keep author-declared code figures when native title and parser ownership agree.

A code observation alone never creates a figure. The parser's independent
code-caption child, exclusive body child and native smaller bold title jointly
prove ownership. Original geometry, text and parser observations are retained.
"""
import re
from dataclasses import replace
from .numbering import FIGURE_CAPTION, normalize_text, normalize_label
from .caption_context import body_font


def _container(obj):
    # Leaf body/caption children must actually share an observed container.
    if not obj.parent_id:return None
    match=re.fullmatch(r'(.+):blocks:[0-9]+',obj.parent_id)
    return match.group(1) if match else None


def _area(box):return max(0,box[2]-box[0])*max(0,box[3]-box[1])


def _coverage(a,b):
    overlap=(max(a[0],b[0]),max(a[1],b[1]),min(a[2],b[2]),min(a[3],b[3]))
    return _area(overlap)/max(_area(a),1e-9)


def _native_title(caption,page):
    declared=FIGURE_CAPTION.match(normalize_text(caption.text))
    typical=body_font(page)
    if not declared or not typical:return None
    choices=[]
    for line in page.lines:
        match=FIGURE_CAPTION.match(normalize_text(line.text))
        if (line.source!='native' or not line.bold or not line.font_size
                or line.font_size>=typical*.95 or abs(line.direction[0])<.9
                or not match or normalize_label(match.group('number'))!=normalize_label(declared.group('number'))
                or _coverage(line.bbox,caption.bbox)<.85):continue
        tail=normalize_text(line.text)[match.end('number'):].strip()
        if len(re.findall(r'[A-Za-z\u4e00-\u9fff]',tail))<3:continue
        if abs((line.bbox[0]+line.bbox[2])/2-page.width/2)>page.width*.12:continue
        choices.append(line)
    return choices[0] if len(choices)==1 else None


def recover_declared_code_figures(objects,document):
    result=list(objects);pages={p.number:p for p in document.pages}
    for ci,caption in enumerate(objects):
        if caption.kind!='text' or caption.role!='code_caption':continue
        container=_container(caption);page=pages.get(caption.page_number)
        if not container or page is None:continue
        title=_native_title(caption,page)
        if title is None:continue
        bodies=[(bi,body) for bi,body in enumerate(objects) if body.kind=='text'
                and body.role=='code_body' and body.page_number==caption.page_number
                and _container(body)==container]
        if len(bodies)!=1:continue
        bi,body=bodies[0];box=body.bbox
        if (box[2]-box[0]<page.width*.15 or box[3]-box[1]<40
                or not 0<=title.bbox[1]-box[3]<=60):continue
        overlap=max(0,min(box[2],title.bbox[2])-max(box[0],title.bbox[0]))
        if overlap<min(box[2]-box[0],title.bbox[2]-title.bbox[0])*.65:continue
        if any(line.source=='native' and line is not title and not line.bold
               and box[3]+1<=line.bbox[1] and line.bbox[3]<=title.bbox[1]-1
               and len(line.text.strip())>=12 and line.bbox[2]-line.bbox[0]>page.width*.45
               for line in page.lines):continue
        # More than one independent native figure title on this same child
        # would leave the ownership ambiguous, even with parser lineage.
        if any(line!=title and (m:=FIGURE_CAPTION.match(normalize_text(line.text)))
               and normalize_label(m.group('number'))!=normalize_label(FIGURE_CAPTION.match(normalize_text(title.text)).group('number'))
               and _coverage(line.bbox,caption.bbox)>.65 for line in page.lines):continue
        result[bi]=replace(body,kind='figure',role='author_declared_code_figure')
        result[ci]=replace(caption,kind='figure_caption',role='author_declared_code_figure_title')
    return result
