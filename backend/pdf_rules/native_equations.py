"""Numbered display equations misclassified as image bodies by a parser."""
from .numbering import normalize_text
from .native_label_carriers import native_text_only
from .layout_context import union, containment
import re


def _fraction_strokes(document,page,box,lines):
    """Return only original thin fraction bars paired with native math glyphs."""
    if not document.path.is_file() or page.display_rotation:return ()
    try:
        import pymupdf
        with pymupdf.open(document.path) as pdf:
            source=pdf[page.number-1];region=pymupdf.Rect(box);strokes=[]
            for drawing in source.get_drawings():
                rect=drawing['rect']
                if rect.y1<box[1] or rect.y0>box[3] or rect.x1<box[0] or rect.x0>box[2]:continue
                items=drawing['items']
                if (drawing['type']!='s' or len(items)!=1 or items[0][0]!='l'
                        or drawing.get('dashes') not in ('[] 0','[] 0.0')
                        or drawing.get('stroke_opacity',1)!=1
                        or max(drawing.get('lineCap',(0,0,0)))!=0):return ()
                _,start,end=items[0];length=abs(end.x-start.x)
                if abs(end.y-start.y)>.05 or not 2<length<(box[2]-box[0])*.65:return ()
                y=(start.y+end.y)/2;left=min(start.x,end.x);right=max(start.x,end.x)
                adjacent=[l for l in lines if not re.search(r'[=≡≤≥≈]',normalize_text(l.text))
                          and l.bbox[2]>left and l.bbox[0]<right
                          and l.bbox[2]-l.bbox[0]<=length*1.4
                          and abs((l.bbox[1]+l.bbox[3])/2-y)<=max(16,(l.font_size or 12)*1.5)]
                above=[l for l in adjacent if (l.bbox[1]+l.bbox[3])/2<y]
                below=[l for l in adjacent if (l.bbox[1]+l.bbox[3])/2>y]
                fonts=[l.font_size for l in adjacent if l.font_size]
                if not above or not below or not fonts or not 0<drawing['width']<=max(fonts)*.08:return ()
                if not region.contains(pymupdf.Rect(left,y-.1,right,y+.1)):return ()
                strokes.append((tuple(start),tuple(end),drawing['width'],drawing['color']))
            return tuple(strokes)
    except (OSError,ValueError,RuntimeError,IndexError):return ()


def native_numbered_equation(obj,page,document,captions):
    from .caption_rules import _matches
    if obj.kind not in {'figure','table'} or any(c.kind==obj.kind+'_caption' and _matches(obj,c) for c in captions):
        return False
    candidates=[l for l in page.lines if containment(l.bbox,obj.bbox)>=.65
                and l.bbox[2]<=obj.bbox[2]+3 and l.bbox[0]>=obj.bbox[0]-3]
    if not candidates:
        return False
    text=' '.join(normalize_text(l.text) for l in candidates)
    if re.search(r'[\u4e00-\u9fff]',text):
        return False
    words=re.findall(r'[A-Za-z]{2,}',text)
    if any(w.lower() not in {'mod','log','sin','cos','tan','exp','max','min','lim','arg','det','ln'} for w in words):
        return False
    relations=[l for l in candidates if re.search(r'[=≡≤≥≈]',normalize_text(l.text))]
    if len(relations)<2 or len(re.findall(r'[+*/∑∏−-]|\b(?:mod|log|sin|cos|exp)\b',text))<2:
        return False
    numbers=[l for l in page.lines if re.fullmatch(r'[（(][A-Z]?\d+(?:[.\-]\d+)*[）)]',normalize_text(l.text).strip())
             and l.bbox[0]>=obj.bbox[2] and l.bbox[0]-obj.bbox[2]<=page.width*.35
             and obj.bbox[1]<=(l.bbox[1]+l.bbox[3])/2<=obj.bbox[3]]
    if len(numbers)!=1:
        return False
    # Native operators and numbering establish identity. The original's actual
    # text layer must additionally explain all ink, including braces and any
    # pixels between glyphs; a genuine plot/diagram cannot pass this proof.
    box=union([obj.bbox]+[l.bbox for l in candidates])
    if native_text_only(document,page,box,candidates):return True
    strokes=_fraction_strokes(document,page,box,candidates)
    return bool(strokes) and native_text_only(document,page,box,candidates,allowed_strokes=strokes)
