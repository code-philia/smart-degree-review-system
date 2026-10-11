"""Classify native text carriers without changing extraction or figure ownership.

Call before repair_figure_identity. Only a figure's kind and role may change;
all parser lineage, geometry, native text, and document fields remain intact.
This module reads the supplied fields only and performs no file or PDF I/O.
"""
from dataclasses import replace
from statistics import median
import re

_FIGURE = re.compile(r'^\s*(?:图|Figure|Fig\.?)\s*[A-Z]?\d', re.I)
_TABLE = re.compile(r'^\s*(?:表|Table)\s*([A-Z]?\d+(?:[.．-]\d+)*)\s*(.*)', re.I)
_NUMBER = re.compile(r'^\s*-?\d+\.\d+\s*$')
_INSTRUCTION = re.compile(
    r'\b(?:you (?:need|are|should)|your task|reply in|please (?:rate|evaluate)|'
    r'return (?:the )?following|determine the next step|as travelers)\b|\bfollow\s*\[', re.I)
_DECLARATION = re.compile(r'(?:提示(?:词)?|指示|模板|如下|具体做法|做出.*决定)')


def _area(b):
    return max(0,b[2]-b[0])*max(0,b[3]-b[1])


def _intersection(a,b):
    return _area((max(a[0],b[0]),max(a[1],b[1]),min(a[2],b[2]),min(a[3],b[3])))


def _inside(a,b,tolerance=2):
    return a[0]>=b[0]-tolerance and a[1]>=b[1]-tolerance and a[2]<=b[2]+tolerance and a[3]<=b[3]+tolerance


def _same_envelope(a,b):
    return (min(_area(a),_area(b))>0 and
            _intersection(a,b)/max(_area(a),_area(b))>.90 and
            max(abs(a[i]-b[i]) for i in range(4))<=max(6,(b[3]-b[1])*.03))


def _glyphs(line):
    """Native per-character bounds are independent of reconstructed line text."""
    if line.source!='native' or not line.font_size or not line.text_regions:
        return False
    valid=set()
    for start,end,box in line.text_regions:
        if (0<=start<end<=len(line.text) and end-start<=2 and
            _area(box)>0 and _inside(box,line.bbox,3)):
            valid.update(range(start,end))
    return len(valid)>=.75*len(line.text)


def _inner(page,box):
    return [l for l in page.lines if l.text.strip() and _glyphs(l) and
            _intersection(l.bbox,box)>=.90*_area(l.bbox)]


def _caption_of(obj,page,objects):
    """A caption must physically abut this carrier, not an unrelated neighbour."""
    box=obj.bbox
    def abuts(b):
        horizontal=min(box[2],b[2])-max(box[0],b[0])
        vertical=min(box[3],b[3])-max(box[1],b[1])
        return ((horizontal>min(box[2]-box[0],b[2]-b[0])*.5 and
                 min(abs(b[1]-box[3]),abs(box[1]-b[3]))<22) or
                (vertical>min(box[3]-box[1],b[3]-b[1])*.5 and
                 min(abs(b[0]-box[2]),abs(box[0]-b[2]))<22))
    for other in objects:
        if other.page_number!=obj.page_number or other.kind!='figure_caption':continue
        if abuts(other.bbox):return True
    for l in page.lines:
        if l.source=='native' and _FIGURE.match(l.text) and (_inside(l.bbox,box,4) or abuts(l.bbox)):return True
    return False


def _prompt(obj,page,objects):
    b=obj.bbox
    if (b[2]-b[0]<page.width*.45 or b[3]-b[1]>page.height*.80 or
            _caption_of(obj,page,objects)):
        return False
    # A boxed raster text carrier has one native rectangular vector envelope.
    # Internal vector parts or embedded image panels retain their figure duty.
    if not any(_same_envelope(x,b) for x in page.images):return False
    frame=[x for x in page.graphics if _same_envelope(x,b)]
    if not frame:return False
    for x in (*page.graphics,*page.images):
        if _intersection(x,b)>.75*_area(x) and _area(x)>9 and not _same_envelope(x,b):
            return False
    lines=_inner(page,b)
    if len(lines)<5:return False
    size=median(l.font_size for l in lines)
    rows=[l for l in lines if abs(l.font_size-size)<.45 and l.direction[0]>.99 and abs(l.direction[1])<.02]
    if len(rows)<5 or sum(len(l.text) for l in rows)<220:return False
    body=[l.font_size for l in page.lines if _glyphs(l) and len(l.text)>24 and
          _intersection(l.bbox,b)==0 and l.font_size>size*1.25 and l.direction[0]>.99]
    if not body or median(body)<size*1.4:return False
    # Prose occupies regular aligned rows; the short native '6tg' artefact is
    # excluded by the independent font observation, not by its spelling.
    left=min(l.bbox[0] for l in rows)
    if sum(abs(l.bbox[0]-left)<=size*2 for l in rows)<len(rows)*.65:return False
    if sum(len(l.text)>=45 for l in rows)<2 or not any(len(l.text)>=80 for l in rows):return False
    text='\n'.join(l.text for l in sorted(rows,key=lambda l:(l.bbox[1],l.bbox[0])))
    if re.search(r'[→←↔⇒⇐⇔]|(?:--|==)>',text) or _FIGURE.search(text):return False
    if not _INSTRUCTION.search(text):return False
    template=bool(re.search(r'\{[A-Za-z_][^{}\n]{0,80}\}|\[(?:User Instruction|Available Information|Evaluation Criteria|Considerations)',text,re.I))
    numbered=len(re.findall(r'^\s*\d[.)]',text,re.M))>=3
    json_schema='json' in text.lower() and len(re.findall(r'"[A-Za-z][^"\n]{0,50}"\s*:',text))>=3
    local=' '.join(l.text for l in page.lines if l.source=='native' and
                   0<=b[1]-l.bbox[3]<70 and min(b[2],l.bbox[2])>max(b[0],l.bbox[0]))
    return template or json_schema or (numbered and bool(_DECLARATION.search(local)))


def _project(box,direction):
    dx,dy=direction
    corners=((box[0],box[1]),(box[2],box[1]),(box[0],box[3]),(box[2],box[3]))
    along=[x*dx+y*dy for x,y in corners]
    cross=[-x*dy+y*dx for x,y in corners]
    return min(along),min(cross),max(along),max(cross)


def _declared_header(obj,page,objects):
    if _caption_of(obj,page,objects):return False
    headers=_inner(page,obj.bbox)
    if len(headers)<6:return False
    captions=[o for o in objects if o.page_number==page.number and o.kind=='table_caption' and _TABLE.match(o.text)]
    bodies=[o for o in objects if o.page_number==page.number and o.kind=='table']
    for caption in captions:
        match=_TABLE.match(caption.text)
        native=[l for l in page.lines if _glyphs(l) and _TABLE.match(l.text) and
                _TABLE.match(l.text).group(1).replace('．','.')==match.group(1).replace('．','.') and
                _intersection(l.bbox,caption.bbox)>.70*_area(l.bbox)]
        for title in native:
            dx,dy=title.direction
            if abs(dx*dx+dy*dy-1)>.03 or max(abs(dx),abs(dy))<.99:continue
            direction=(dx,dy)
            h=_project(obj.bbox,direction);c=_project(caption.bbox,direction)
            if h[2]-h[0]<3*(h[3]-h[1]):continue
            if min(h[2],c[2])<=max(h[0],c[0]) or min(abs(c[1]-h[3]),abs(h[1]-c[3]))>40:continue
            for body in bodies:
                b=_project(body.bbox,direction)
                overlap=min(h[2],b[2])-max(h[0],b[0])
                if overlap<.85*min(h[2]-h[0],b[2]-b[0]):continue
                if min(abs(h[1]-b[3]),abs(b[1]-h[3]))>8:continue
                if min(h[3]-h[1],b[3]-b[1])<8:continue
                body_numbers=re.findall(r'(?<![\w.])-?\d+\.\d+(?![\w.])',body.text)
                if len(body_numbers)<12:continue
                cells=[l for l in _inner(page,body.bbox) if _NUMBER.fullmatch(l.text) and
                       sum(a*z for a,z in zip(l.direction,direction))>.99 and l.text.strip() in body_numbers]
                if len(cells)<12:continue
                size=median(l.font_size for l in cells)
                samefont=[l for l in headers if abs(l.font_size-size)<.5]
                if len(samefont)<6 or sum(not _NUMBER.fullmatch(l.text) for l in samefont)<6:continue
                # Repeated native data rows and matching vector rule bands
                # distinguish a table header from a neighbouring academic plot.
                grid=[_project(x,direction) for x in page.graphics if _inside(x,body.bbox,4)]
                if sum(g[2]-g[0]>.8*(b[2]-b[0]) and g[3]-g[1]<size*2 for g in grid)<3:continue
                groups=[]
                for l in cells:
                    cross=(_project(l.bbox,direction)[1]+_project(l.bbox,direction)[3])/2
                    group=next((g for g in groups if abs(g[0]-cross)<size*.6),None)
                    if group is None:groups.append([cross,1])
                    else:group[1]+=1
                if sum(g[1]>=4 for g in groups)<3:continue
                if any(_intersection(x,obj.bbox)>.6*_area(x) and _area(x)>size*size*2 for x in page.graphics):continue
                return True
    return False


def repair_nonfigure_caption_carriers(objects,document):
    """Return classifications proved by native glyphs and parser geometry."""
    objects=list(objects)
    pages={p.number:p for p in document.pages}
    out=[]
    for obj in objects:
        page=pages.get(obj.page_number)
        if obj.kind=='figure' and page is not None:
            if _declared_header(obj,page,objects):
                # This is the textual header of the existing, proved table,
                # rather than a second academic table competing for its title.
                obj=replace(obj,kind='text',role='declared_table_header_carrier')
            elif _prompt(obj,page,objects):
                obj=replace(obj,kind='text',role='prompt_text_carrier')
        out.append(obj)
    return out
