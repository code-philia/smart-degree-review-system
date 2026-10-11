"""Explicit total-caption layout declarations, not proximity-only merging."""
from dataclasses import replace
import re
from .layout_context import union
from .caption_rules import _matches,_horizontal_overlap

def merge_declared_rows(targets,captions,document):
    """Explicit upper/lower row descriptions own a physically aligned grid."""
    from .object_identity import coverage
    from .logical_objects import panel_label_conflict
    pages={p.number:p for p in document.pages};targets=list(targets)
    for title in captions:
        if title.kind!='figure_caption':continue
        if not (re.search(r'上(?:排|行(?=\s*(?:为|是|[:：])))|(?:upper|top)\s+row',title.text,re.I)
                and re.search(r'下(?:排|行(?=\s*(?:为|是|[:：])))|(?:lower|bottom)\s+row',title.text,re.I)):continue
        page=pages[title.page_number]
        candidates=[o for o in targets if o.kind=='figure' and o.page_number==title.page_number
                    and o.role in {'image_body','chart_body'} and o.bbox[3]<=title.bbox[1]+3
                    and coverage(o.bbox,page.images+page.graphics)>=.85]
        rows=[]
        for obj in sorted(candidates,key=lambda o:(o.bbox[1],o.bbox[0])):
            row=next((r for r in rows if all(min(obj.bbox[3],a.bbox[3])-max(obj.bbox[1],a.bbox[1])
                     >=.75*min(obj.bbox[3]-obj.bbox[1],a.bbox[3]-a.bbox[1]) for a in r)),None)
            if row is None:rows.append([obj])
            else:row.append(obj)
        if len(rows)<2:continue
        top,bottom=[sorted(row,key=lambda o:o.bbox[0]) for row in rows[-2:]]
        if len(top)<2 or len(top)!=len(bottom):continue
        if any(max(abs(a.bbox[0]-b.bbox[0]),abs(a.bbox[2]-b.bbox[2]))
               >min(15,(a.bbox[2]-a.bbox[0])*.12) for a,b in zip(top,bottom)):continue
        if any(b.bbox[0]-a.bbox[2]>80 for row in (top,bottom) for a,b in zip(row,row[1:])):continue
        low=min(o.bbox[1] for o in bottom);high=max(o.bbox[3] for o in top)
        if not 0<=low-high<=max(40,min(o.bbox[3]-o.bbox[1] for o in top+bottom)*.4):continue
        members=top+bottom;box=union([o.bbox for o in members]);parent=replace(top[0],bbox=box)
        if not _matches(parent,title) or panel_label_conflict(members,document,captions):continue
        width=box[2]-box[0]
        if title.bbox[2]-title.bbox[0]<width*.75 or abs((title.bbox[0]+title.bbox[2]-box[0]-box[2])/2)>width*.12:continue
        if any(c is not title and c.page_number==title.page_number and box[1]<c.bbox[1]<box[3]
               and min(c.bbox[2],box[2])>max(c.bbox[0],box[0]) for c in captions):continue
        # A separately titled member retains its own obligation even when
        # that title sits above the total grid rather than inside its envelope.
        def separate_upper_title(c):
            if (c is title or c.kind!='figure_caption' or c.page_number!=title.page_number
                    or not box[0]-15<=(c.bbox[0]+c.bbox[2])/2<=box[2]+15):
                return False
            owned=[o for o in members if _matches(o,c) and c.bbox[3]<=o.bbox[1]+3]
            if not owned:
                return False
            gap=min(max(o.bbox[1]-c.bbox[3],0) for o in owned)
            # A title above any separately titled subgroup is a boundary.
            # A preceding figure's closer bottom title is not this group's title.
            return not any(o not in members and o.kind=='figure' and o.page_number==c.page_number
                           and o.role in {'image_body','chart_body','native_figure'}
                           and coverage(o.bbox,page.images+page.graphics)>=.85
                           and _matches(o,c)
                           and max(c.bbox[1]-o.bbox[3],o.bbox[1]-c.bbox[3],0)<gap-3
                           for o in targets)
        if any(separate_upper_title(c) for c in captions):continue
        title_lines=[l for l in page.lines if l.bold and l.font_size
                     and min(l.bbox[2],title.bbox[2])>max(l.bbox[0],title.bbox[0])
                     and min(l.bbox[3],title.bbox[3])>max(l.bbox[1],title.bbox[1])]
        def row_subtitle(line):
            return (line.bold and line.font_size and title_lines
                    and any(abs(line.font_size-l.font_size)<=.5 for l in title_lines)
                    and line.bbox[2]-line.bbox[0]<=width*.8
                    and abs((line.bbox[0]+line.bbox[2]-box[0]-box[2])/2)<=width*.05
                    and not re.search(r'[。.!?！？;；:：]\s*$',line.text))
        if any(high<=l.bbox[1] and l.bbox[3]<=low and len(re.findall(r'[A-Za-z\u4e00-\u9fff]',l.text))>=12
               and min(l.bbox[2],box[2])>max(l.bbox[0],box[0]) and not row_subtitle(l)
               for l in page.lines):continue
        parent=replace(parent,role='declared_row_panels',panel_boxes=tuple(o.bbox for o in members))
        targets=[o for o in targets if o not in members]+[parent]
    return targets


def merge_declared_stacks(targets,captions,document):
 targets=merge_declared_rows(targets,captions,document);pages={p.number:p for p in document.pages}
 for title in captions:
  if title.kind!='figure_caption':continue
  text=title.text
  if not (re.search(r'[（(]\s*(?:top|upper|上)\s*[）)]',text,re.I)
          and re.search(r'[（(]\s*(?:bottom|lower|下)\s*[）)]',text,re.I)):continue
  candidates=[o for o in targets if o.kind=='figure' and o.page_number==title.page_number
              and o.role in {'chart_body','image_body'} and _matches(o,title)
              and o.bbox[3]<=title.bbox[1]+3]
  if not candidates:continue
  bottom=min(candidates,key=lambda o:title.bbox[1]-o.bbox[3])
  upper=[o for o in targets if o is not bottom and o.kind=='figure' and o.page_number==bottom.page_number
         and o.role in {'chart_body','image_body'} and 0<=bottom.bbox[1]-o.bbox[3]<=40
         and _horizontal_overlap(o,bottom)>=.95
         and min(o.bbox[2]-o.bbox[0],bottom.bbox[2]-bottom.bbox[0])/max(o.bbox[2]-o.bbox[0],bottom.bbox[2]-bottom.bbox[0])>=.9]
  if len(upper)!=1:continue
  top=upper[0];box=union([top.bbox,bottom.bbox])
  if any(c is not title and c.kind.endswith('_caption') and c.page_number==title.page_number
         and box[1]<c.bbox[1]<box[3] and _horizontal_overlap(top,c)>=.25 for c in captions):continue
  if any(top.bbox[3]+2<l.bbox[1] and l.bbox[3]<bottom.bbox[1]-2
         and len(re.findall(r'[A-Za-z\u4e00-\u9fff]',l.text))>=12 for l in pages[top.page_number].lines):continue
  targets=[o for o in targets if o is not top and o is not bottom]+[replace(top,bbox=box,role='declared_stacked_panels')]
 return targets
