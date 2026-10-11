"""Native visual regions for citation scope; no OCR/API is required here."""
import re
from .mineru_layout import LayoutObject
from .numbering import FIGURE_CAPTION,TABLE_CAPTION,normalize_text
from .caption_context import contextual_caption


def _detached_sentence(line,page):
    """Short prose between visuals is a boundary even below a full-line width."""
    text=normalize_text(line.text).rstrip()
    if (len(re.findall(r'[A-Za-z\u4e00-\u9fff]',text))<8
            or not text.endswith(('。','！','？','.','!','?'))):return False
    box=line.bbox;area=max(1,(box[2]-box[0])*(box[3]-box[1]))
    return not any(max(0,min(box[2],b[2])-max(box[0],b[0]))
                   *max(0,min(box[3],b[3])-max(box[1],b[1]))>=area*.5
                   for b in (*getattr(page,'graphics',()),*page.images))


def native_figure_regions(document,directory_lines):
    result=[]
    for page in document.pages:
        captions=[l for l in page.lines if (page.number,l.bbox) not in directory_lines
                  and contextual_caption(l,page,'figure')]
        # Actual paragraph text separates a diagram from a neighbouring diagram;
        # never extend a visual region over it merely because it is near a title.
        barriers=[l for l in page.lines
                  if ((l.bbox[2]-l.bbox[0]>page.width*.4
                       and len(re.findall(r'[A-Za-z\u4e00-\u9fff]',l.text))>=18)
                      or _detached_sentence(l,page))
                  and not contextual_caption(l,page,'figure')
                  and not contextual_caption(l,page,'table')]
        for caption in captions:
            top=max([page.height*.085]+[l.bbox[3] for l in barriers if l.bbox[3]<caption.bbox[1]])
            bottom=min([page.height*.94]+[l.bbox[1] for l in barriers if l.bbox[1]>caption.bbox[3]])
            # Other numbered titles are independent logical-object boundaries.
            for other in page.lines:
                m=FIGURE_CAPTION.search(normalize_text(other.text)) or TABLE_CAPTION.search(normalize_text(other.text))
                if not m or other==caption:continue
                n=FIGURE_CAPTION.search(normalize_text(caption.text))
                if n and m.group('number')==n.group('number'):continue
                if other.bbox[3]<caption.bbox[1]:top=max(top,other.bbox[3])
                if other.bbox[1]>caption.bbox[3]:bottom=min(bottom,other.bbox[1])
            sides=[]
            for upper,lower in ((top,caption.bbox[1]),(caption.bbox[3],bottom)):
                shapes=[box for box in (*getattr(page,'graphics',()),*page.images)
                        if box[1]>=upper-2 and box[3]<=lower+2
                        and box[0]>=page.width*.05 and box[2]<=page.width*.95
                        and not any(max(0,min(box[2],t[2])-max(box[0],t[0]))*
                                    max(0,min(box[3],t[3])-max(box[1],t[1]))
                                    >=(box[2]-box[0])*(box[3]-box[1])*.8 for t in page.tables)]
                if not shapes:continue
                x1=min(b[0] for b in shapes);y1=min(b[1] for b in shapes)
                x2=max(b[2] for b in shapes);y2=max(b[3] for b in shapes)
                gap=min(abs(caption.bbox[1]-y2),abs(y1-caption.bbox[3]))
                if x2-x1<60 or y2-y1<30 or gap>65:continue
                # Include detached panel labels between vector ink and the title.
                if y2<=caption.bbox[1]:y2=caption.bbox[1]-2
                if y1>=caption.bbox[3]:y1=caption.bbox[3]+2
                sides.append((gap,LayoutObject('figure',page.number,(x1,y1,x2,y2),'',page.width,page.height,role='native_visual_region')))
            if sides:result.append(min(sides,key=lambda item:item[0])[1])
    return result


def detached_from_native_figure(line,page,region,native_regions):
    """A parser's oversized box cannot absorb prose outside the actual visual.

    Require an independently recovered native visual inside the parsed box,
    a full native sentence, and no covering native graphic. Text genuinely
    inside the recovered visual remains diagram content.
    """
    if line.source!='native' or not _detached_sentence(line,page):return False
    same=[obj for obj in native_regions if obj.page_number==line.page_number]
    if any(obj.bbox[0]<=line.bbox[0] and obj.bbox[2]>=line.bbox[2]
           and obj.bbox[1]<=line.bbox[1] and obj.bbox[3]>=line.bbox[3] for obj in same):return False
    for obj in same:
        box=obj.bbox;parsed=region.bbox
        overlap=max(0,min(box[2],parsed[2])-max(box[0],parsed[0]))*max(0,min(box[3],parsed[3])-max(box[1],parsed[1]))
        if (overlap>=max(1,(box[2]-box[0])*(box[3]-box[1]))*.8
                and (line.bbox[3]<box[1] or line.bbox[1]>box[3])):return True
    return False
