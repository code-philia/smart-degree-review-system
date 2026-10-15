"""Recover annotation evidence from vector-outline or rasterized plot text.

This is local OCR of existing graphic regions. It never creates a title, changes
PDF content, or supplies prose citations to the text-rule index.
"""
from dataclasses import replace
from functools import lru_cache
from collections import Counter
import logging,re
from .model import PdfLine
from .layout_context import containment,union,_panel_match,_caption_aliases
from .caption_context import contextual_caption
from .mineru_layout import LayoutObject

@lru_cache(maxsize=128)
def _cached_region(path,mtime,number,box):
 import numpy as np,pymupdf
 from .local_ocr import _read_tile,OcrText
 with pymupdf.open(path) as pdf:
  page=pdf[number-1];page.set_rotation(0)
  clip=pymupdf.Rect(box)&page.rect
  pix=page.get_pixmap(matrix=pymupdf.Matrix(3,3),clip=clip,colorspace=pymupdf.csGRAY)
  gray=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width)
  # Pixmap origins are integer pixels, not necessarily exactly clip.x0*3.
  return tuple(OcrText(h.text,h.score,((pix.x+h.bbox[0])/3,(pix.y+h.bbox[1])/3,
         (pix.x+h.bbox[2])/3,(pix.y+h.bbox[3])/3),h.detection_score) for h in _read_tile(gray))

def _read_region(document,number,box):
 return _cached_region(str(document.path),document.path.stat().st_mtime_ns,number,tuple(box))

def _native_panel_sequence(page,bodies,captions=()):
 """Original glyphs already establish a complete nearby panel namespace."""
 # Adjacent plots can still belong to two independent numbered figures.
 # Geometry alone must not carry native label proof across their namespaces.
 # Reuse the prepared physical captions, including parser-read raster
 # titles, and the same bilingual alias grouping as the caption pipeline.
 # Equal numbers do not unite independent titles in different positions.
 titles=[c for c in captions if c.page_number==page.number and c.kind=='figure_caption']
 titles += [LayoutObject('figure_caption',page.number,line.bbox,line.text,page.width,page.height)
            for line in page.lines if line.source=='native'
            and contextual_caption(line,page,'figure')]
 if len(_caption_aliases(titles))>1:return False
 labels={};owners=set()
 for line in page.lines:
  match=_panel_match(line.text)
  if line.source!='native' or not match or abs(line.direction[0])<.9:continue
  required={i for i,c in enumerate(line.text[:match.end()]) if c.strip()}
  glyphs=[(a,b,box) for a,b,box in line.text_regions if b-a==1 and a in required]
  if {a for a,b,box in glyphs}!=required:continue
  box=union([b for a,z,b in glyphs])
  if not 0<box[2]-box[0]<40 or not 0<box[3]-box[1]<40:continue
  local=[i for i,o in enumerate(bodies) if o.bbox[0]-15<=(box[0]+box[2])/2<=o.bbox[2]+15
         and o.bbox[1]-15<=(box[1]+box[3])/2<=o.bbox[3]+20]
  if not local:continue
  owners.update(local);labels.setdefault(match.group(1).casefold(),[]).append(box)
 tags=set(labels)
 if len(tags)<2 or len(owners)<2 or tags!={chr(97+i) for i in range(len(tags))}:return False
 # Two actual occurrences of '(a)' mean independent namespaces, requiring
 # the existing recovery and ownership checks instead of this fast path.
 if not all(not any(abs(a[1]-b[1])>22 or abs(a[0]-b[0])>40 for a in boxes for b in boxes)
            for boxes in labels.values()):return False
 # Native labels may cover only one of several independent figures. Only
 # contiguous plot pieces belonging to a labelled component inherit coverage.
 # A distant bitmap namespace must still take the existing OCR recovery path.
 def neighbours(a,b):
  overlap_x=max(0,min(a[2],b[2])-max(a[0],b[0]))
  overlap_y=max(0,min(a[3],b[3])-max(a[1],b[1]))
  gap_x=max(0,max(a[0],b[0])-min(a[2],b[2]))
  gap_y=max(0,max(a[1],b[1])-min(a[3],b[3]))
  return ((gap_x<=20 and overlap_y>=.5*min(a[3]-a[1],b[3]-b[1]))
          or (gap_y<=20 and overlap_x>=.5*min(a[2]-a[0],b[2]-b[0])))
 covered=set(owners)
 while True:
  extra={i for i,o in enumerate(bodies) if i not in covered
         and any(neighbours(o.bbox,bodies[j].bbox) for j in covered)}
  if not extra:break
  covered.update(extra)
 return len(covered)==len(bodies)


def recover_graphic_annotations(document,targets):
 if not document.path.is_file():return document
 pages=[]
 for page in document.pages:
  bodies=[o for o in targets if o.page_number==page.number and o.kind=='figure'
          and o.role in {'chart_body','image_body'}]
  if len(bodies)<2 or _native_panel_sequence(page,bodies,targets):
   pages.append(page);continue
  def ink_lines(body):
   return [l for l in page.lines if containment(l.bbox,body.bbox)>=.7
           and re.search(r'[A-Za-z\u4e00-\u9fff]',l.text)]
  try:badges=_read_number_badges(document,page,bodies)
  except (ImportError,OSError,RuntimeError,ValueError) as exc:
   logging.getLogger(__name__).warning('Graphic badge OCR unavailable: %s',type(exc).__name__)
   badges=[]
  sparse=[o for o in bodies if len(ink_lines(o))<3]
  if len(sparse)<2 and not badges:
   pages.append(page);continue
  readings=[]
  if len(sparse)>=2:
   # Read only the graphic envelope and a small border for outside panel labels.
   box=union([o.bbox for o in sparse]);box=(max(0,box[0]-15),max(0,box[1]-15),
          min(page.width,box[2]+15),min(page.height,box[3]+20))
   try:readings=_read_region(document,page.number,box)
   except (ImportError,OSError,RuntimeError,ValueError) as exc:
    logging.getLogger(__name__).warning('Graphic annotation OCR unavailable: %s',type(exc).__name__)
   readings=[h for h in readings if h.score>=.92 and h.text.strip()
             and len(h.text)<=60 and not re.match(r'^(?:Figure|Fig\.?|Table|图|表)\s*\d',h.text,re.I)]
  for badge in badges:
   if not any(h.text==badge.text and containment(h.bbox,badge.bbox)>=.7 for h in readings):readings.append(badge)
  def owners(hit):
   return [i for i,o in enumerate(bodies) if o.bbox[0]-15<=(hit.bbox[0]+hit.bbox[2])/2<=o.bbox[2]+15
           and o.bbox[1]-15<=(hit.bbox[1]+hit.bbox[3])/2<=o.bbox[3]+20]
  repetitions={}
  for hit in readings:
   repetitions.setdefault(re.sub(r'\s+','',hit.text).casefold(),set()).update(owners(hit))
  numbered=[]
  for hit in readings:
   if not re.fullmatch(r'[1-9]',hit.text.strip()):continue
   local=[i for i,o in enumerate(bodies) if o.bbox[0]-5<=hit.bbox[0]<=o.bbox[0]+(o.bbox[2]-o.bbox[0])*.08
          and o.bbox[1]-12<=hit.bbox[1]<=o.bbox[1]+(o.bbox[3]-o.bbox[1])*.12]
   physical=any(containment(hit.bbox,b)>=.98 and containment(b,hit.bbox)>=.98 for b in page.images)
   if len(local)==1 and _dark_badge(document,page.number,hit.bbox,padding=0 if physical else 2):numbered.append((local[0],hit))
  numbered.sort(key=lambda pair:(bodies[pair[0]].bbox[1],bodies[pair[0]].bbox[0]))
  verified_numbers=(len(numbered)>=2 and len({i for i,h in numbered})==len(numbered)
                    and [int(h.text) for i,h in numbered]==list(range(1,len(numbered)+1)))
  number_hits={id(h):chr(96+int(h.text)) for i,h in numbered} if verified_numbers else {}
  extra=[]
  for hit in readings:
   text=hit.text.strip()
   if id(hit) in number_hits:text='('+number_hits[id(hit)]+')'
   key=re.sub(r'\s+','',text).casefold()
   if not owners(hit):continue
   panel=bool(re.fullmatch(r'[（(][a-zA-Z][）)]',text))
   repeated_axis=(len(repetitions.get(key,()))>=2 and re.search(r'[a-zA-Z\u4e00-\u9fff]',text)
                  and not re.search(r'[:：=]',text))
   if not (panel or repeated_axis):continue
   def same_native_ink(line):
    if containment(hit.bbox,line.bbox)<.65:return False
    if re.sub(r'\s+','',line.text).casefold()==key:return True
    # OCR may read only '(c)' while native text already contains '(c) Method'.
    # The physical overlap, not the letter alone, establishes one occurrence.
    native_tag=_panel_match(line.text)
    return panel and native_tag is not None and native_tag.group(1).casefold()==text[1].casefold()
   if any(same_native_ink(l) for l in page.lines):continue
   extra.append(PdfLine(page.number,text,hit.bbox,page.width,page.height,
                        source='local_graphic_ocr',role='graphic_annotation'))
  pages.append(replace(page,lines=page.lines+tuple(extra)))
 return replace(document,pages=tuple(pages))


def _dark_badge(document,number,box,*,padding=2):
 import numpy as np,pymupdf
 with pymupdf.open(document.path) as pdf:
  page=pdf[number-1];page.set_rotation(0)
  clip=pymupdf.Rect(box)+(-padding,-padding,padding,padding)
  pix=page.get_pixmap(matrix=pymupdf.Matrix(3,3),clip=clip,colorspace=pymupdf.csGRAY)
  gray=np.frombuffer(pix.samples,dtype=np.uint8)
  # A white digit on a compact dark badge differs from black axis ticks.
  return bool((gray<140).mean()>=.45 and (gray>205).mean()>=.08)


def _read_number_badges(document,page,bodies):
 import numpy as np,pymupdf,cv2
 from .local_ocr import _engine,OcrText
 from rapidocr.ch_ppocr_rec import TextRecInput
 readings=[]
 candidates=[box for box in page.images if 4<=box[2]-box[0]<=26 and 4<=box[3]-box[1]<=26
             and .7<=(box[2]-box[0])/(box[3]-box[1])<=1.4
             and any(o.bbox[0]-5<=box[0]<=o.bbox[0]+(o.bbox[2]-o.bbox[0])*.08
                 and o.bbox[1]-12<=box[1]<=o.bbox[1]+(o.bbox[3]-o.bbox[1])*.12 for o in bodies)]
 if not candidates:return readings
 with pymupdf.open(document.path) as pdf:
  source=pdf[page.number-1];source.set_rotation(0)
  for box in candidates:
   if not _dark_badge(document,page.number,box,padding=0):continue
   pix=source.get_pixmap(matrix=pymupdf.Matrix(8,8),clip=pymupdf.Rect(box),colorspace=pymupdf.csGRAY)
   gray=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width)
   ys,xs=np.nonzero(gray>205)
   if not len(xs):continue
   crop=255-gray[max(0,ys.min()-4):min(pix.height,ys.max()+5),max(0,xs.min()-4):min(pix.width,xs.max()+5)]
   rgb=cv2.cvtColor(cv2.copyMakeBorder(crop,5,5,5,5,cv2.BORDER_CONSTANT,value=255),cv2.COLOR_GRAY2BGR)
   result=_engine().text_rec(TextRecInput(img=[rgb]));text=result.txts[0].strip();score=result.scores[0]
   # The body corner, dark badge, glyph reading and sequence must all agree.
   # Recognition alone, particularly a plain axis digit, is insufficient.
   if score>=.85 and re.fullmatch(r'[1-9]',text):
    if not any(h.text==text and containment(h.bbox,box)>=.7 for h in readings):
     readings.append(OcrText(text,float(score),tuple(box)))
 return readings
