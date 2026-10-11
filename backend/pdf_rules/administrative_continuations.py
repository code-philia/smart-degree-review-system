"""Prove the exact native grid occupied by continued committee signature rows."""
import re
from .numbering import normalize_text,FIGURE_REFERENCE,TABLE_REFERENCE,APPENDIX_REFERENCE


def _text(value):
 return normalize_text(value).replace(' ','').replace('（','(').replace('）',')')


def _inside(box,container,slack=2):
 return all((box[i]>=container[i]-slack if i<2 else box[i]<=container[i]+slack) for i in range(4))


def _rows(page):
 # Individual closed vector cells must have common top/bottom boundaries.
 # Paragraph backgrounds and an enclosing page rectangle are not a grid.
 boxes=[b for b in page.graphics if page.width*.05<b[2]-b[0]<page.width*.35 and 20<b[3]-b[1]<page.height*.2]
 groups=[]
 for b in sorted(boxes,key=lambda b:(b[1],b[0])):
  group=next((g for g in groups if abs(g[0][1]-b[1])<=.3 and abs(g[0][3]-b[3])<=.3),None)
  if group is None:groups.append([b])
  else:group.append(b)
 result=[]
 for group in groups:
  group=sorted(set(group),key=lambda b:b[0])
  if len(group)==5 and all(0<=right[0]-left[2]<=2 for left,right in zip(group,group[1:])):
   result.append(group)
 return result


def _cell_text(page,cell,slack=2):
 return ''.join(_text(l.text) for l in sorted(page.lines,key=lambda l:(l.bbox[1],l.bbox[0])) if l.source=='native' and _inside(l.bbox,cell,slack))


def native_continuation_regions(previous,page,objects):
 from .signature_ocr import _form_context
 if (page.number!=previous.number+1 or page.display_rotation%360 or previous.display_rotation%360
     or abs(page.width-previous.width)>2 or not _form_context(previous)):
  return []
 headings=['答辩委员会工作职务','姓名','职称','工作单位','签名']
 prior=[r for r in _rows(previous) if [_cell_text(previous,c,slack=5) for c in r]==headings]
 if len(prior)!=1:return []
 columns=prior[0];rows=_rows(page);objects=tuple(objects);result=[]
 references=(FIGURE_REFERENCE,TABLE_REFERENCE,APPENDIX_REFERENCE)
 for obj in objects:
  b=obj.bbox
  if (obj.kind!='table' or obj.page_number!=page.number or obj.role!='table_body'
      or not obj.source_id.startswith('mineru:') or not obj.parent_id
      or not obj.source_id.startswith(obj.parent_id+':') or obj.parent_kind!='table'
      or obj.parent_bbox is None or not _inside(b,obj.parent_bbox)
      or b[2]-b[0]<page.width*.6 or b[3]-b[1]>page.height*.2 or b[3]>page.height*.3):continue
  if any(o.page_number==page.number and o.kind.endswith('_caption') and _inside(o.bbox,b) for o in objects):continue
  # A native caption can be omitted by the parser. A separately printed table
  # title immediately above/below this grid retains its research obligation.
  from .numbering import TABLE_CAPTION
  def adjacent_title(line):
   q=line.bbox
   return (line.source=='native' and TABLE_CAPTION.match(normalize_text(line.text).strip())
           and (-3<=q[1]-b[3]<=60 or -3<=b[1]-q[3]<=60)
           and max(0,min(q[2],b[2])-max(q[0],b[0]))>=min(q[2]-q[0],b[2]-b[0])*.6)
  if any(adjacent_title(line) for line in page.lines):continue
  region_rows=[r for r in rows if all(_inside(c,b) for c in r)]
  if not region_rows:continue
  if any(any(abs(c[k]-old[k])>1.5 for k in (0,2)) for r in region_rows for c,old in zip(r,columns)):continue
  # The observed table cannot borrow a tiny grid from an enclosing envelope.
  grid_area=sum((c[2]-c[0])*(c[3]-c[1]) for r in region_rows for c in r)
  if grid_area<(b[2]-b[0])*(b[3]-b[1])*.9:continue
  native=[l for l in page.lines if l.source=='native' and _inside(l.bbox,b)]
  if not native or any(any(rx.search(_text(l.text)) for rx in references) for l in native):continue
  if any(not any(_inside(l.bbox,c) for r in region_rows for c in r[:4]) for l in native):continue
  labels=[];valid=True;raw=_text(obj.text)
  for row in region_rows:
   value=[_cell_text(page,c) for c in row]
   labels.append(value[0])
   if (value[0] not in {'委员','秘书'} or not re.fullmatch(r'[\u4e00-\u9fff]{2,12}',value[1])
       or value[2] not in {'','教授','副教授','研究员','副研究员','讲师'}
       or not re.search(r'大学|学院|研究所|研究院',value[3]) or len(value[3])>100
       or any(v and v not in raw for v in value[:4])
       or not any(_inside(image,row[4]) and (image[2]-image[0])*(image[3]-image[1])>100 for image in page.images)):
    valid=False;break
  if valid and '秘书' in labels and not any(rx.search(raw) for rx in references):result.append(b)
 return result


def native_continuation_table(obj,regions):
 # The proof names an observed table, never a partially overlapping figure or
 # an entire page carrier. Exact source coordinates preserve outside ink.
 return obj.kind=='table' and tuple(obj.bbox) in {tuple(b) for b in regions}
