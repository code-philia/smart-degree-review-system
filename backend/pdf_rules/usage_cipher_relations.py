"""Bind an observed parallel substitution/permutation diagram to body use."""
import re
from .usage_text_cache import normalize_text
from .usage_formal_aliases import _rounded_rect
from .usage_roadmap_relations import _owned_passages,_denied_operation


def substitution_permutation_title(title):
    return bool(re.search(r'(?<![A-Za-z])SPN(?![A-Za-z])|代换[-–—、 ]?置换',title,re.I))


def _vectors(document,area):
    import pymupdf
    answer=[];roi=area['bbox']
    try:
        with pymupdf.open(document.path) as pdf:
            for drawing in pdf[area['page_number']-1].get_drawings():
                box=list(drawing['rect'])
                if not(roi[0]<=box[0]<=box[2]<=roi[2] and roi[1]<=box[1]<=box[3]<=roi[3]):continue
                items=[[item[0],*[[p.x,p.y] if isinstance(p,pymupdf.Point) else list(p)
                                  if isinstance(p,pymupdf.Rect) else p for p in item[1:]]]
                       for item in drawing['items']]
                answer.append(dict(bbox=box,type=drawing['type'],items=items,
                                   rounded_rectangle=_rounded_rect(drawing)))
    except (OSError,RuntimeError,ValueError,IndexError):return []
    return answer


def substitution_permutation_layout(vectors):
    cells=sorted([r['rounded_rectangle'] for r in vectors if r.get('rounded_rectangle')],key=lambda b:b[1])
    if len(cells)<3:return None
    left,_,right,_=cells[0];width=right-left;height=cells[0][3]-cells[0][1]
    if any(abs(b[0]-left)>.5 or abs(b[2]-right)>.5 or abs((b[3]-b[1])-height)>.5 for b in cells):return None
    if any(not 1<b[1]-a[3]<height*.5 for a,b in zip(cells,cells[1:])):return None
    segments=[]
    for row in vectors:
        if row.get('type')!='s' or len(row['items'])!=1 or row['items'][0][0]!='l':continue
        start,end=row['items'][0][1:]
        if start[0]<end[0]:segments.append((start,end))
    stubs=[(a,b) for a,b in segments if 0<=a[0]-right<=1.5 and abs(a[1]-b[1])<.1 and b[0]-a[0]>5]
    if not stubs or max(b[0] for a,b in stubs)-min(b[0] for a,b in stubs)>.1:return None
    transition=stubs[0][1][0]
    wires=[(a,b) for a,b in segments if abs(a[0]-transition)<.1 and b[0]-a[0]>width*1.5]
    if len(wires)!=len(stubs) or len({round(a[1],2) for a,b in wires})!=len(wires):return None
    if len({round(b[1],2) for a,b in wires})!=len(wires):return None
    ys={round(a[1],2) for a,b in stubs}
    if {round(a[1],2) for a,b in wires}!=ys or {round(b[1],2) for a,b in wires}!=ys:return None
    end_x=wires[0][1][0]
    if any(abs(b[0]-end_x)>.1 for a,b in wires):return None
    counts=[];mapping=[]
    for i,cell in enumerate(cells):
        owned=[(a,b) for a,b in wires if cell[1]<a[1]<cell[3]]
        if len(owned)<2:return None
        targets=set()
        for a,b in owned:
            destination=[j for j,other in enumerate(cells) if other[1]<b[1]<other[3]]
            if len(destination)!=1:return None
            targets.add(destination[0]);mapping.append(dict(source_cell=i,destination_cell=destination[0],
                                                            start=list(a),end=list(b)))
        if len(targets)<2:return None
        counts.append(len(owned))
    if len(set(counts))!=1 or sum(counts)!=len(wires):return None
    # Every permutation exit remains physically attached to an outgoing wire.
    exits=[(a,b) for a,b in segments if abs(a[0]-end_x)<.1 and abs(a[1]-b[1])<.1 and b[0]-a[0]>3]
    if {round(a[1],2) for a,b in exits}!=ys:return None
    return dict(cells=[list(c) for c in cells],parallel_bits_per_cell=counts[0],permutation=mapping)


def _body_rows(passages):
    for rows,value in passages:
        if _denied_operation(value):continue
        text=re.sub(r'\s+','',normalize_text(value))
        if not re.search(r'SPN|代换[-–—、]?置换',text,re.I):continue
        if not re.search(r'S盒.{0,45}(?:局部)?非线性',text,re.I):continue
        if not re.search(r'扩散.{0,70}局部.{0,30}(?:传播|扩散).{0,20}(?:整个|全部|全).{0,8}分组',text):continue
        return rows
    return []


def cipher_relation_proposals(context,groups,nearby):
    answer=[]
    for ordinal,areas in context['regions'].items():
        if len(areas)!=1 or not substitution_permutation_title(areas[0]['title']):continue
        rows=_body_rows(_owned_passages(ordinal,groups,nearby))
        if not rows:continue
        topology=substitution_permutation_layout(_vectors(context['_document'],areas[0]))
        if topology is None:continue
        answer.append((ordinal,'parallel_substitution_cross_block_permutation',rows,topology))
    return answer
