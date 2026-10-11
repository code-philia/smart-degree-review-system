"""Recover observed source geometry when title text polluted a parser crop."""
from dataclasses import replace
from pathlib import Path
import re
from .numbering import FIGURE_CAPTION,normalize_text,normalize_label
from .figure_identity_repair import _area,_inside,_union,_xover,_join
from .caption_physical_ownership import _PageInk,_source_native_group
from .mineru_layout import caption_identity

def _declared_lines(cap,page):
 match=FIGURE_CAPTION.match(normalize_text(cap.text))
 if match is None:return []
 number=normalize_label(match.group('number'));lines=[]
 for line in page.lines:
  m=FIGURE_CAPTION.match(normalize_text(line.text))
  if line.source!='native' or m is None or normalize_label(m.group('number'))!=number:continue
  if _inside(line.bbox,cap.bbox)<.65:continue
  needed={n for n,c in enumerate(line.text[:m.end('number')]) if c.strip()}
  covered={a for a,z,b in line.text_regions if z-a==1 and _area(b)>0}
  if not needed<=covered:continue
  lines.append(line)
 if not lines:return []
 # Title continuations retain native typography and lie in the retained
 # caption's original envelope; arbitrary body text cannot supply geometry.
 for line in page.lines:
  if line in lines or line.source!='native' or not line.font_size:continue
  inside=_inside(line.bbox,cap.bbox)>=.75
  linked=False
  for first in tuple(lines):
   if not first.bold or not line.bold:continue
   if FIGURE_CAPTION.match(normalize_text(line.text)):continue
   if not first.font_size or abs(first.font_size-line.font_size)>first.font_size*.08:continue
   if first.direction!=line.direction:continue
   if abs(first.direction[0])<.2 and abs(first.direction[1])>.8:
    linked=0<=line.bbox[0]-first.bbox[2]<=first.font_size*1.5 and abs(line.bbox[3]-first.bbox[3])<2
   else:
    linked=0<=line.bbox[1]-first.bbox[3]<=first.font_size*1.5 and abs(line.bbox[0]-first.bbox[0])<first.font_size*2
   if linked:break
  if not inside and not linked:continue
  if not any(l.font_size and abs(l.font_size-line.font_size)<l.font_size*.08 for l in lines):continue
  if line.bold or any(l.bold and l.block_id is not None and l.block_id==line.block_id for l in lines):lines.append(line)
 return lines

def _glyph_mask(ink,lines):
 # Every disappearing source character must match retained native evidence.
 # An envelope that also deletes unrelated source text supplies no proof.
 from .native_text_paint import native_text_paint
 return native_text_paint(ink,lines)


def _near(box,cap):
 if cap.bbox[3]-cap.bbox[1]>3*(cap.bbox[2]-cap.bbox[0]):
  overlap=min(box[3],cap.bbox[3])-max(box[1],cap.bbox[1])
  gap=max(cap.bbox[0]-box[2],box[0]-cap.bbox[2],0)
  return gap<=cap.page_width*.25 and overlap>=min(box[3]-box[1],cap.bbox[3]-cap.bbox[1])*.6
 overlap=_xover(box,cap.bbox)
 return overlap>.35 and -32<=cap.bbox[1]-box[3]<=80

def _overlap_observations(group):
 # Disjoint plots within the same Form retain independent obligations.
 return all(any(o is not q and (_inside(o.bbox,q.bbox)>.85 or _inside(q.bbox,o.bbox)>.85) for q in group) for o in group)


def _header_mask(ink,page,owner):
 # Explain only original margin header glyphs and actual thin rule paths.
 # A white gap or an unrelated plot cannot be explained by its envelope.
 headers=[l for l in page.lines if l.source=='native' and l.bbox[3]<page.height*.13
  and (re.fullmatch(r'第[一二三四五六七八九十0-9]+章',normalize_text(l.text).replace(' ',''))
       or re.fullmatch(r'.{2,25}大学.{0,12}学位论文',normalize_text(l.text).replace(' ','')))]
 if not headers:return ink.np.zeros_like(ink.base,dtype=bool)
 baseline=min(l.bbox[1] for l in headers)
 headers += [l for l in page.lines if l.source=='native' and abs(l.bbox[1]-baseline)<3
             and l.bbox[3]<owner['box'][1] and l.font_size<=11]
 from .native_text_paint import native_text_paint
 mask=native_text_paint(ink,headers,source_names=owner['names'])
 selected=[]
 for d in ink.page.get_drawings():
  b=tuple(d['rect']);width=d.get('width') or .5
  if not (b[1]>=baseline and b[3]<owner['box'][1] and b[2]-b[0]>page.width*.5 and b[3]-b[1]<3 and width<=3):continue
  if all(i[0] in {'re','l'} for i in d['items']):selected.append(d)
 if selected:
  from .vector_strip_caption_ownership import _path_mask
  painted=_path_mask(selected,ink,page)
  if painted is not None:mask|=painted

 return mask

def _raster_owned(group,source_page,page,resource,lines=()):
 # A source image rectangle alone cannot explain an independent overlay.
 # Every visible pixel of each observation must vanish when the actual
 # named original image operator is removed in a disposable PDF copy.
 from .source_native_caption_ownership import _OriginalPageInk
 ink=_PageInk(source_page.parent,page.number)
 try:
  if not ink.valid:
   ink.close()
   import pymupdf
   with pymupdf.open(source_page.parent.name) as original:
    ink=_OriginalPageInk(original,page.number,source_page.parent.name)
  if not ink.valid:return False
  owner=ink.removal({resource})
  if owner is None:return False
  mask=owner['mask']|_glyph_mask(ink,lines)
  return all(ink.owns(o,{'mask':mask}) for o in group)
 finally:ink.close()

def _raster_duplicates(figures,caps,page,source_page):
 # Nested observations of the very same original image have one physical
 # obligation. Keep the complete image, with every visible pixel retained.
 output=list(figures)
 for record in source_page.get_images(full=True):
  for rect in source_page.get_image_rects(record[0]):
   box=tuple(rect)
   if _area(box)>page.width*page.height*.55 or min(rect.width,rect.height)<25:continue
   group=[o for o in output if _inside(o.bbox,box)>.985]
   native=[o for o in group if o.role=='native_figure' and all(abs(a-b)<.15 for a,b in zip(o.bbox,box))]
   if not native or len(group)<2 or not _overlap_observations(group):continue
   candidates=[c for c in caps if _near(box,c) and _declared_lines(c,page)]
   if len(candidates)!=1:continue
   cap=candidates[0]
   if not _raster_owned(group,source_page,page,record[7],_declared_lines(cap,page)):continue
   if any(c is not cap and _inside(c.bbox,box)>.5 for c in caps):continue
   # A second independently titled or disjoint source picture is retained.
   joined=replace(_join(group,'figure'),bbox=box,panel_boxes=(),role='same_original_image_observation',caption_owner_id=caption_identity(cap))
   gone={id(o) for o in group};output=[o for o in output if id(o) not in gone]+[joined]
 return output


def _declared_position_pair(group,cap,page,ink,owners,lines):
 if len(group)!=2:return None
 title=' '.join(l.text for l in lines)
 if not (re.search(r'上图(?:为|[：:])|\bTop\s*:',title,re.I)
         and re.search(r'下图(?:[^。;；]{0,10})(?:为|[：:]|散点|曲线)|\bBottom\s*:',title,re.I)):return None
 a,b=sorted(group,key=lambda o:o.bbox[1])
 if _xover(a.bbox,b.bbox)<.75 or not -2<=b.bbox[1]-a.bbox[3]<=40:return None
 selected=[]
 for o in group:
  candidates=[w for w in owners if ink.owns(o,w) and _inside(o.bbox,w['box'])>.7]
  if len(candidates)!=1:return None
  selected.append(candidates[0])
 if selected[0]['names']==selected[1]['names']:return None
 mask=selected[0]['mask']|selected[1]['mask']|_glyph_mask(ink,lines)
 if not all(ink.owns(o,{'mask':mask}) for o in group):return None
 return group


def _declared_source_sequence(group,cap,page,ink,lines):
 # The full crop may contain title glyphs or duplicate one central panel.
 # Native component tags and actual joint paint establish the namespace;
 # parser envelope overlap alone supplies no ownership evidence.
 if not group:return None
 box=_union([o.bbox for o in group])
 if any(re.search(r'[（(][a-z]\d+[）)]',normalize_text(l.text),re.I)
        and _inside(l.bbox,(box[0]-25,box[1]-25,box[2]+25,cap.bbox[3]))>.5 for l in page.lines):return None
 from .source_native_caption_ownership import _owners,_source_labels,_combined_mask,_declared
 owners=_owners(group,cap,ink,False)
 if not owners:return None
 labels,sequence=_source_labels(page,[],owners,group,False,ink)
 if not sequence:return None
 declared=_declared(' '.join(l.text for l in lines))
 actual={re.match(r'\s*[（(]([a-z])[）)]',normalize_text(l.text)).group(1) for l in labels}
 if declared and actual!=declared:return None
 mask=_combined_mask({n for o in owners for n in o['names']},labels+lines,ink)
 if mask is None or not all(ink.owns(o,{'mask':mask}) for o in group):return None
 return group

class _CaptionInk:
 def __init__(self,ink,lines):
  self.ink=ink;self.title_glyphs=_glyph_mask(ink,lines)
 def __getattr__(self,name):return getattr(self.ink,name)
 def owns(self,obj,owner):
  return self.ink.owns(obj,dict(mask=owner['mask']|self.title_glyphs))

def repair_descriptive_caption_ownership(objects,document):
 result=list(objects)
 if document is None or not Path(document.path).is_file():return result
 from .caption_rules import detect_caption_rules
 pending={f['page'] for f in detect_caption_rules(result,[13],document)['13']['findings']}
 if not pending:return result
 import pymupdf
 with pymupdf.open(document.path) as source:
  for page in document.pages:
   if page.number not in pending:continue
   caps=[c for c in result if c.kind=='figure_caption' and c.page_number==page.number]
   figures=[o for o in result if o.kind=='figure' and o.page_number==page.number]
   if not caps or not figures:continue
   recovered=_raster_duplicates(figures,caps,page,source[page.number-1])
   if recovered!=figures:
    gone={id(o) for o in figures};result=[o for o in result if id(o) not in gone]+recovered;figures=recovered
   # A single observed raster object needs no grouping. Bind its nearby
   # native title using the real source-image rectangle when parser crop
   # margins or mathematical glyph bounds displaced conventional matching.
   for record in source[page.number-1].get_images(full=True):
    for rect in source[page.number-1].get_image_rects(record[0]):
     box=tuple(rect)
     group=[o for o in figures if _inside(o.bbox,box)>.95 and _inside(box,o.bbox)>.95]
     if len(group)!=1:continue
     if not _raster_owned(group,source[page.number-1],page,record[7]):continue
     candidates=[c for c in caps if _near(box,c) and _declared_lines(c,page)]
     if len(candidates)!=1:continue
     cap=candidates[0];o=group[0]
     if any(c is not cap and _inside(c.bbox,box)>.5 for c in caps):continue
     new=replace(o,caption_owner_id=caption_identity(cap))
     result=[new if q is o else q for q in result];figures=[new if q is o else q for q in figures]
   ink=None
   try:
    ink=_PageInk(source,page.number)
    if not ink.valid:
     from .source_native_caption_ownership import _OriginalPageInk
     ink.close()
     with pymupdf.open(document.path) as original:
      ink=_OriginalPageInk(original,page.number,document.path)
    if not ink.valid:continue
    names={name for name,a,b in ink.spans};owners=[]
    for name in names:
     owned=ink.removal({name})
     if owned is None:continue
     b=owned['box']
     if min(b[2]-b[0],b[3]-b[1])<25 or _area(b)>page.width*page.height*.7:continue
     owners.append(owned)
    # Caption-declared native subpanel namespaces can also be inside one
    # parser crop. The same source/glyph proof applies to that single crop.
    for cap in caps:
     lines=_declared_lines(cap,page)
     if not lines:continue
     preceding=max((c.bbox[3] for c in caps if c is not cap and c.bbox[3]<cap.bbox[1]),default=page.height*.08)
     group=[o for o in figures if preceding<=o.bbox[1] and o.bbox[3]<=cap.bbox[3]+2 and _xover(o.bbox,cap.bbox)>.2]
     if not group:continue
     selected=_source_native_group(group,cap,page,_CaptionInk(ink,lines))
     if not selected:selected=_declared_position_pair(group,cap,page,ink,owners,lines)
     if not selected:selected=_declared_source_sequence(group,cap,page,ink,lines)
     if not selected:continue
     joined=replace(_join(selected,'figure'),role='source_geometry_caption_owner',caption_owner_id=caption_identity(cap))
     removed={id(o) for o in selected};result=[o for o in result if id(o) not in removed]+[joined]
     figures=[o for o in figures if id(o) not in removed]+[joined]
    for owner in owners:
     candidates=[(cap,_declared_lines(cap,page)) for cap in caps if _near(owner['box'],cap)]
     candidates=[(cap,ls) for cap,ls in candidates if ls]
     if len(candidates)!=1:continue
     cap,lines=candidates[0]
     explained=dict(mask=owner['mask']|_glyph_mask(ink,lines)|_header_mask(ink,page,owner))
     group=[o for o in figures if ink.owns(o,explained) and _inside(o.bbox,owner['box'])>.4]
     if not group or len(group)>1 and not _overlap_observations(group):continue
     # An unrelated retained title inside the resource makes a single source
     # paint operation insufficient to establish a single academic figure.
     if any(c is not cap and _inside(c.bbox,owner['box'])>.5 for c in caps):continue
     if len(group)==1:
      obj=group[0]
      if _area(owner['box'])>_area(obj.bbox)*1.3:continue
      joined=replace(obj,bbox=owner['box'],panel_boxes=(),role='source_geometry_caption_owner',caption_owner_id=caption_identity(cap))
     else:joined=replace(_join(group,'figure'),bbox=owner['box'],panel_boxes=(),role='source_geometry_caption_owner',caption_owner_id=caption_identity(cap))
     removed={id(o) for o in group};result=[o for o in result if id(o) not in removed]+[joined]
     figures=[o for o in figures if id(o) not in removed]+[joined]
   except (ValueError,IndexError,RuntimeError):pass
   finally:
    if ink is not None:ink.close()
 return result
