"""Exclude identified thesis signing pages consistently from all six rules.

Classification is content based: signed legal statements, formal defense
forms and proven committee continuations. Original page numbering survives.
"""
from dataclasses import replace
import re
from .model import PdfDocument
from .numbering import normalize_text
from .layout_context import ADMIN_TITLE,CHAPTER,decision_form,_complete_decision_schema
from .numbering import FIGURE_CAPTION,TABLE_CAPTION

def _text(page):
 return ''.join(normalize_text(line.text).replace(' ','') for line in page.lines)
def _title(line):
 value=normalize_text(line.text).replace(' ','')
 return bool(ADMIN_TITLE.fullmatch(value) or re.fullmatch(r'(?:[\u4e00-\u9fffA-Za-z]{2,30}大学)?(?:硕士|博士)?学位论文(?:使用授权声明|使用授权书|授权使用声明|原创性声明|版权使用授权书)',value))

def _research_caption(page):
 return any(FIGURE_CAPTION.match(normalize_text(l.text).strip()) or TABLE_CAPTION.match(normalize_text(l.text).strip()) for l in page.lines)

def _modern_decision(page,text):
 # The current official template records three voting counts and a decision
 # checkbox. Its verdict need not repeat the historical '无记名投票' wording.
 fields=('姓名','学号','所在学科','指导教师','答辩日期','答辩地点','论文题目','评语和决议','投票表决结果','同意票数','实到委员数','应到委员数','答辩结论','答辩委员会')
 return (not _research_caption(page) and all(v in text for v in fields)
         and any(_title(l) and '答辩' in normalize_text(l.text) and l.bbox[1]<page.height*.2 for l in page.lines)
         and bool(re.search(r'同意通过.{0,100}学位论文答辩',text))
         and bool(re.search(r'建议授予.{0,50}学位',text)))

def _inside(box,region,slack=3):
 return box[0]>=region[0]-slack and box[1]>=region[1]-slack and box[2]<=region[2]+slack and box[3]<=region[3]+slack

def _area(box):
 return max(0,box[2]-box[0])*max(0,box[3]-box[1])

def _display_box(page,box):
 x,y,z,w=box;rotation=page.display_rotation%360
 if rotation==90:return page.height-w,x,page.height-y,z
 if rotation==180:return page.width-z,page.height-w,page.width-x,page.height-y
 if rotation==270:return y,page.width-z,w,page.width-x
 return box

def _display_size(page):
 return (page.height,page.width) if page.display_rotation%180 else (page.width,page.height)

def _source_table(obj,page):
 return (obj.kind=='table' and obj.role=='table_body' and obj.page_number==page.number
         and obj.parent_kind=='table' and obj.parent_bbox is not None and _inside(obj.bbox,obj.parent_bbox)
         and bool(obj.parent_id) and obj.source_id.startswith(obj.parent_id+':')
         and bool(re.match(r'mineru:[0-9a-f]{64}:',obj.source_id)))

def _whole_admin_regions(page,objects,regions):
 # The observed form cannot exempt a separate research object or paragraph.
 # A full raster paper carrier and its narrow margin barcode are retained as
 # evidence of the same scanned page, rather than made into new tables.
 if _research_caption(page):return False
 def margin(box,text=''):
  b=_display_box(page,box);width,height=_display_size(page)
  return ((b[3]<height*.065 or b[2]-b[0]<width*.025 and (b[0]<width*.04 or b[2]>width*.96))
          and (not text.strip() or bool(re.fullmatch(r'[\d\s-]{1,24}',text.strip()))))
 for line in page.lines:
  if any(_inside(line.bbox,b) for b in regions) or margin(line.bbox,line.text):continue
  if line.text.strip():return False
 for obj in objects:
  if obj.page_number!=page.number:continue
  if any(_inside(obj.bbox,b) for b in regions) or margin(obj.bbox,obj.text):continue
  if obj.kind=='figure' and page.unreadable and _area(obj.bbox)>=page.width*page.height*.85 and not obj.text.strip():continue
  return False
 return True

def _scanned_columns(document,page,box,footer=False,allow_label_column=False):
 """Read original raster grid geometry only; no OCR, extraction or cache I/O."""
 try:
  import pymupdf
  b=_display_box(page,box)
  trimmed=footer and b[3]-b[1]>260
  if trimmed:b=(b[0],b[3]-220,b[2],b[3])
  with pymupdf.open(document.path) as pdf:
   source=pdf[page.number-1]
   width,height=_display_size(page)
   if abs(source.rect.width-width)>3 or abs(source.rect.height-height)>3:return ()
   clip=pymupdf.Rect(b[0]-4,b[1]-4,b[2]+4,b[3]+4)&source.rect
   pix=source.get_pixmap(matrix=pymupdf.Matrix(1,1),colorspace=pymupdf.csGRAY,alpha=False,clip=clip)
  w,h=pix.width,pix.height;pixels=pix.samples
  if min(w,h)<16:return ()
  columns=[sum(pixels[y*w+x]<210 for y in range(h)) for x in range(w)]
  rows=[sum(v<210 for v in pixels[y*w:(y+1)*w]) for y in range(h)]
  def groups(values,threshold):
   bins=[]
   for i,v in enumerate(values):
    if v<threshold:continue
    if bins and i-bins[-1][-1]<=2:bins[-1].append(i)
    else:bins.append([i])
   return [sum(g)/len(g) for g in bins]
  x=groups(columns,h*(.45 if trimmed else .68));y=groups(rows,w*.55)
  if allow_label_column and len(x)==7 and x[1]-x[0]<w*.05:
   x=x[1:]  # A narrow vertical committee label precedes the six roster borders.
  if allow_label_column and len(y)<5:return ()
  if len(x)!=6 or len(y)<2 or x[-1]-x[0]<w*.85:return ()
  if any(right-left<w*.065 for left,right in zip(x,x[1:])):return ()
  return tuple(pix.x+a for a in x)
 except (OSError,ValueError,RuntimeError,IndexError,ImportError):return ()

def _scanned_roster_continuation(document,previous,page,objects):
 candidates=[o for o in objects if _source_table(o,page)]
 prior=[o for o in objects if _source_table(o,previous) and all(v in normalize_text(o.text).replace(' ','') for v in ('答辩委员会','工作职务','姓名','职称','工作单位','签名','主席'))]
 if not prior:return False
 width,height=_display_size(page)
 for obj in candidates:
  b=_display_box(page,obj.bbox);text=normalize_text(obj.text).replace(' ','')
  if b[2]-b[0]<width*.6 or b[1]>height*.25 or b[3]>height*.4:continue
  if text:
   if not re.match(r'(?:委员|秘书)',text) or '秘书' not in text or not re.search(r'大学|学院|研究所|研究院|实验室|公司',text):continue
  elif not page.unreadable or page.lines:
   continue
  if not _whole_admin_regions(page,objects,(obj.bbox,)):continue
  columns=_scanned_columns(document,page,obj.bbox)
  if not columns:continue
  for old in prior:
   old_box=_display_box(previous,old.bbox);old_width,old_height=_display_size(previous)
   if abs(old_width-width)>width*.04 or old_box[3]<old_height*.7:continue
   if abs(old_box[0]-b[0])>width*.025 or abs(old_box[2]-b[2])>width*.025:continue
   if not text and '秘书' not in normalize_text(old.text):continue
   old_columns=_scanned_columns(document,previous,old.bbox,footer=True)
   if old_columns and all(abs(a/width-z/old_width)<.025 for a,z in zip(columns,old_columns)):
    return True
 return False

def _signed_verdict_continuation(page,objects):
 text=_text(page)
 fields=('投票表决结果','同意票数','实到委员数','应到委员数','答辩结论','答辩委员会主席')
 if not all(v in text for v in fields) or not re.search(r'主席[（(]?(?:签字|签名)',text):return False
 if not re.search(r'建议授予.{0,30}学位',text):return False
 lines=[l for l in page.lines if any(v in normalize_text(l.text).replace(' ','') for v in ('投票表决结果','答辩结论','答辩委员会主席'))]
 if len(lines)<3:return False
 return _whole_admin_regions(page,objects,tuple(l.bbox for l in lines))

def _verified_scan_regions(page,objects,kind):
 regions=tuple(l.bbox for l in page.lines if l.source=='signature_structure_cpu' and l.role=='signature_verified_'+kind)
 if not regions:return False
 # Original parser text from a wrongly oriented scan is superseded only by
 # the pixel-backed OCR proof. Native paragraphs and independent objects keep
 # their obligations, including objects whose pixels the parser separated.
 lines=tuple(l for l in page.lines if l.source!='mineru')
 nontext=tuple(o for o in objects if o.kind!='text')
 return _whole_admin_regions(replace(page,lines=lines),nontext,regions)

def _source_scanned_decision(document,page,objects):
 # Hidden OCR on an old full-page scan can be illegible while the table
 # parser reads the visible form. Require the complete form and raster grid.
 if (_research_caption(page) or any(o.page_number==page.number and o.kind in {'figure_caption','table_caption'} for o in objects)
     or not any(_area(b)>=page.width*page.height*.85 for b in page.images)):return False
 fields=('姓名','学号','所在学科','指导教师','答辩日期','答辩地点','论文题目',
         '投票表决结果','同意票数','实到委员数','应到委员数','答辩结论',
         '答辩委员会','职务','职称','单位','签名','主席','秘书')
 for obj in objects:
  if obj.kind!='table' or obj.role!='table_body' or obj.page_number!=page.number:continue
  if _area(obj.bbox)<page.width*page.height*.45:continue
  text=normalize_text(obj.text).replace(' ','')
  if (not all(v in text for v in fields) or text.count('委员')<3
      or not re.search(r'同意通过.{0,12}论文答辩',text)
      or not re.search(r'建议授予.{0,20}学位',text)):continue
  if _scanned_columns(document,page,obj.bbox,footer=True,allow_label_column=True):return True
 return False
def signature_page_reasons(document,objects=()):
 objects=tuple(objects);reasons={};defense=set()
 for page in document.pages:
  if any(CHAPTER.match(normalize_text(line.text).strip()) for line in page.lines):continue
  text=_text(page);title=any(_title(line) for line in page.lines)
  legal=(('本人郑重声明' in text and '学位论文' in text and '法律' in text)
         or ('本学位论文作者' in text and '学校' in text and '保留' in text and '查阅' in text and '借阅' in text))
  signed=any(value in text for value in ('签名','签字','作者签','日期'))
  if _verified_scan_regions(page,objects,'declaration'):
   reasons[page.number]='pixel_proved_scanned_declaration_or_authorization'
  elif _verified_scan_regions(page,objects,'decision'):
   reasons[page.number]='pixel_proved_scanned_thesis_defense_form';defense.add(page.number)
  elif title and legal and signed and not any(l.source=='signature_structure_cpu' for l in page.lines):
   reasons[page.number]='signed_thesis_declaration_or_authorization'
  elif (_complete_decision_schema(text) or decision_form(page) or _modern_decision(page,text)
        or _source_scanned_decision(document,page,objects)):
   reasons[page.number]='formal_thesis_defense_form';defense.add(page.number)
 for previous,page in zip(document.pages,document.pages[1:]):
  if previous.number not in defense or page.number!=previous.number+1:continue
  if any(CHAPTER.match(normalize_text(line.text).strip()) for line in page.lines):continue
  table_text=''.join(normalize_text(line.text).replace(' ','') for line in page.lines if line.role in {'table','table_body'})
  roster=(all(value in table_text for value in ('答辩委员会','工作职务','姓名','职称','工作单位','签名','主席','秘书')) and table_text.count('委员')>=3)
  from .administrative_continuations import native_continuation_regions
  native=bool(native_continuation_regions(previous,page,objects))
  if _verified_scan_regions(page,objects,'committee_continuation'):
   reasons[page.number]='pixel_proved_scanned_committee_signature_continuation'
  elif roster or native:reasons[page.number]='proven_committee_signature_continuation'
  elif _scanned_roster_continuation(document,previous,page,objects):
   reasons[page.number]='proven_scanned_committee_signature_continuation'
  elif _signed_verdict_continuation(page,objects):
   reasons[page.number]='proven_signed_defense_verdict_continuation'
  if page.number in reasons:defense.add(page.number)
 return reasons

def exclude_signature_pages(document,objects=()):
 reasons=signature_page_reasons(document,objects)
 if not reasons:return document,list(objects),reasons
 pages=tuple(replace(page,lines=(),unreadable=False,images=(),tables=(),graphics=(),legend_marks=(),ink_bottom=None) if page.number in reasons else page for page in document.pages)
 return PdfDocument(document.path,pages),[obj for obj in objects if obj.page_number not in reasons],reasons
