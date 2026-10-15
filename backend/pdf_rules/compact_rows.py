"""Physical multi-sample rows whose collective caption can be very short."""
from dataclasses import replace
import re
from .layout_context import union, containment
from .caption_rules import _matches


COLLECTIVE = re.compile(r'(?:部分|多个|若干|不同|多种).{0,12}(?:样本|示例|图像|图片)|\b(?:samples|examples|specimens|images|photos)\b',re.I)


def merge_compact_sample_rows(targets,captions,document):
    targets=list(targets);pages={p.number:p for p in document.pages}
    for caption in captions:
        if caption.kind!='figure_caption' or not COLLECTIVE.search(caption.text):
            continue
        page=pages[caption.page_number]
        candidates=[o for o in targets if o.kind=='figure' and o.page_number==caption.page_number
                    and o.role=='image_body' and o.bbox[3]<=caption.bbox[1]+3
                    and any(containment(o.bbox,b)>=.9 and containment(b,o.bbox)>=.9 for b in page.images)]
        rows=[]
        for obj in sorted(candidates,key=lambda o:(o.bbox[1],o.bbox[0])):
            row=next((r for r in rows if all(min(obj.bbox[3],a.bbox[3])-max(obj.bbox[1],a.bbox[1])
                       >=.9*max(obj.bbox[3]-obj.bbox[1],a.bbox[3]-a.bbox[1]) for a in r)),None)
            if row is None:rows.append([obj])
            else:row.append(obj)
        for row in sorted(rows,key=lambda r:max(o.bbox[3] for o in r),reverse=True):
            row=sorted(row,key=lambda o:o.bbox[0])
            if len(row)<3:
                continue
            widths=[o.bbox[2]-o.bbox[0] for o in row]
            if min(widths)<max(widths)*.9 or any(not 0<=b.bbox[0]-a.bbox[2]<=min(widths)*.08 for a,b in zip(row,row[1:])):
                continue
            box=union([o.bbox for o in row]);width=box[2]-box[0]
            parent=replace(row[0],bbox=box)
            if (not _matches(parent,caption) or caption.bbox[1]-box[3]>min(o.bbox[3]-o.bbox[1] for o in row)*.25
                    or abs((caption.bbox[0]+caption.bbox[2]-box[0]-box[2])/2)>width*.04):
                continue
            # Other captions, including a title spanning a subgroup, retain
            # their independently titled object boundaries.
            if any(c is not caption and c.kind=='figure_caption' and c.page_number==page.number
                   and any(_matches(o,c) for o in row) for c in captions):
                continue
            if any(box[3]<=l.bbox[1] and l.bbox[3]<=caption.bbox[1] and l.text.strip()
                   and len(re.findall(r'[A-Za-z\u4e00-\u9fff]',l.text))>=12 for l in page.lines):
                continue
            from .logical_objects import panel_label_conflict
            if panel_label_conflict(row,document,captions):
                continue
            parent=replace(parent,role='shared_caption_panels',panel_boxes=tuple(o.bbox for o in row))
            targets=[o for o in targets if o not in row]+[parent]
            break
    return targets
