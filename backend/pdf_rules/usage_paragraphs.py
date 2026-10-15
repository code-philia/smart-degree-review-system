"""Reconstruct native prose wraps for usage evidence, retaining ink coordinates."""
import re
from dataclasses import replace
from .numbering import normalize_text


def usage_paragraphs(lines, document=None):
    result=[]
    pages={p.number:p for p in document.pages} if document else {}
    for line,scope in lines:
        # Native character rectangles use normalized offsets even where the
        # stored text has a PDF ligature. Normalize before concatenation so
        # every shifted region remains in the same coordinate convention.
        normalized=normalize_text(line.text)
        if normalized!=line.text:line=replace(line,text=normalized)
        if not result:
            result.append((line,scope));continue
        previous,old_scope=result[-1]
        height=max(1,line.bbox[3]-line.bbox[1])
        old_height=max(1,previous.bbox[3]-previous.bbox[1])
        gap=line.bbox[1]-previous.bbox[3]
        join=(scope==old_scope and line.page_number==previous.page_number
              and line.source==previous.source=='native'
              and line.font_size and previous.font_size
              and abs(line.font_size-previous.font_size)<=previous.font_size*.05
              and not line.bold and not previous.bold
              and line.direction==previous.direction==(1.0,0.0)
              and previous.bbox[2]-previous.bbox[0]>=line.page_width*.6
              and 0<=gap<=height*1.3
              and abs(line.bbox[0]-previous.bbox[0])<=height*2.5
              and not re.search(r'[。！？；：!?;:]\s*$',previous.text)
              and not _intervening_content(previous,line,pages.get(line.page_number)))
        if not join:
            result.append((line,scope));continue
        separator='' if re.search(r'[\u4e00-\u9fff]$',previous.text) and re.match(r'[\u4e00-\u9fff]',line.text) else ' '
        offset=len(previous.text)+len(separator)
        def regions(name):
            a=getattr(previous,name)
            b=getattr(line,name)
            # Only actual split-reference regions have priority over exact
            # glyph rectangles. Fabricating a whole-line reference region
            # would replace the known number ink with a paragraph highlight.
            if name=='text_regions':
                a=a or ((0,len(previous.text),previous.bbox),)
                b=b or ((0,len(line.text),line.bbox),)
            return a+tuple((s+offset,e+offset,bbox) for s,e,bbox in b)
        combined=replace(previous,text=previous.text+separator+line.text,
            bbox=(min(previous.bbox[0],line.bbox[0]),previous.bbox[1],max(previous.bbox[2],line.bbox[2]),line.bbox[3]),
            text_regions=regions('text_regions'),reference_regions=regions('reference_regions'))
        result[-1]=(combined,scope)
    return result


def _intervening_content(previous,line,page):
    """Filtered-out titles, graphic labels and directories remain boundaries."""
    if page is None:return False
    low,high=previous.bbox[3],line.bbox[1]
    left,right=min(previous.bbox[0],line.bbox[0]),max(previous.bbox[2],line.bbox[2])
    for other in page.lines:
        if other is line or not other.text.strip():continue
        centre=(other.bbox[1]+other.bbox[3])/2
        if low<centre<high and max(left,other.bbox[0])<min(right,other.bbox[2]):return True
    return any(low<=b[1]<b[3]<=high and max(left,b[0])<min(right,b[2])
               for b in (*page.images,*page.tables,*page.graphics))


def span_anchor(line,start,end,compact=False):
    if compact:
        positions=[i for i,c in enumerate(line.text) if not c.isspace()]
        if start<len(positions) and end<=len(positions):start,end=positions[start],positions[end-1]+1
    boxes=[box for a,b,box in line.text_regions if a<end and b>start]
    if not boxes:return line
    return replace(line,bbox=(min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)))
