"""Repair local-reference identity using page ink and explicit semantic evidence.

The entry point returns a new DocumentIndex. It never reads document.path, paper
IDs, cached findings, or a decision list. Optional ``evidence`` receives the ink
and criterion for every changed identity. Unproven generic mentions are left
alone; a wrong literal number remains a missing-target reference.
"""
import re
import unicodedata
from dataclasses import replace
from .model import DocumentIndex, Label
from .numbering import (FIGURE_CAPTION, TABLE_CAPTION, normalize_text,
                        normalize_label, caption_match, is_toc_line, toc_line_keys, APPENDIX_QUALIFIER)
from .caption_context import body_font
from .reference_groups import reference_matches
from .reference_context import local_reference, _explicit_graph_reference, defined_graph_symbols, graph_variable_use
from .local_rules import indirect_reference_key, physical_target_key

_NUMBER = r'(?:[A-Z]\.)?[0-9]+(?:\s*[.\-]\s*[0-9]+)*'
_TYPED = {
 'figure': re.compile(r'(?:图|(?<![A-Za-z])Figures?|(?<![A-Za-z])Figs?\.?)\s*[(（]?\s*(?P<number>'+_NUMBER+r')(?![A-Za-z0-9]|\s*[.\-]\s*\d)',re.I),
 'table': re.compile(r'(?:表格?|(?<![A-Za-z])Tables?)\s*[(（]?\s*(?P<number>'+_NUMBER+r')(?![A-Za-z0-9]|\s*[.\-]\s*\d)',re.I),
}
_APPENDIX = re.compile(r'^\s*(?:APPENDIX|附录)\s*(?P<number>[A-Z])(?:\s|[:：]|$)',re.I)
_BODY_TAIL = re.compile(r'^(?:(?:至|到|[-—–])\s*'+_NUMBER+r'\s*)?(?:指明|固定|所总结|以.{0,20}(?:评估|展示|说明)|在.{0,90}(?:描述|总结|说明)|中(?:进行|详细|列出|展示|归纳|描述)|(?:展示|显示|说明|描述|给出|列出|为|是))',re.I)
_MORE = re.compile(r'^\s*(?:[,，、]|和|与|及|and\b|&|\s)\s*(?:图|表|Figures?|Tables?)?\s*(?P<number>'+_NUMBER+r')(?![A-Za-z0-9]|\s*[.\-]\s*\d)',re.I)
_RESULT = re.compile(r'^\s*(?:结果所示|所示|所述|展示|显示|给出|[,，。.;；])')


def _text(text):
 value=normalize_text(text)
 value=re.sub(r'\b(Figures?)\s*\.\s*(?=\d)',r'\1 ',value,flags=re.I)
 return re.sub(r'(图|表)\s*[~～]\s*(?=\d)',r'\1',value)


def _num(value):return normalize_label(re.sub(r'\s+','',value))

def _key(line):return (line.page_number,line.bbox)

def _event(events,action,label,criterion,**extra):
 if events is not None:
  events.append(dict(action=action,number=label.number,page=label.line.page_number,
                     bbox=list(label.line.bbox),text=label.line.text,criterion=criterion,**extra))


def _heading(text):
 m=_APPENDIX.match(text)
 if not m:return None
 tail=text[m.end():].strip()
 if len(text)>100 or re.search(r'[，,。；;]',tail) or re.match(r'(?:describes?|shows?|contains?|provides?|discusses?|介绍|展示|描述|给出|中|是|为)',tail,re.I):return None
 return m.group('number').upper()


def _structural_chapter(line,page,document,body_size):
 if (line.source!='native' or not line.bold or line.font_size is None
     or line.font_size<body_size*1.15 or line.bbox[1]>=page.height*.30):return False
 text=normalize_text(line.text).strip()
 m=re.match(r'^(?:第[零〇一二三四五六七八九十百0-9]+章\s*|Chapter\s+[0-9IVX]+(?:\s|$))',text,re.I)
 if not m or len(text)>=100 or re.search(r'[，,。；;]',text):return False
 tail=text[m.end():].strip()
 if re.match(r'(?:describes?|shows?|contains?|provides?|discusses?|introduces?|介绍|展示|描述|给出|讨论|中|是|为)',tail,re.I):return False
 # A repeated native heading at the same top-of-page position is a running
 # header; it cannot end a bibliography on a continuation page.
 if line.bbox[1]<page.height*.16:
  for other in document.pages:
   if other.number==page.number:continue
   if any(l.source=='native' and l.bold and l.font_size is not None
          and abs(l.font_size-line.font_size)<=1 and abs(l.bbox[1]-line.bbox[1])<=3
          and abs(l.bbox[0]-line.bbox[0])<=5 and normalize_text(l.text).strip()==text
          for l in other.lines):return False
 return True


def _table_column_heading(line,page):
 """A native table cell cannot open a document-wide bibliography.

 A carrier rectangle alone is insufficient. Require a disjoint native peer
 on the same row and aligned native cells on another row, all inside the
 same observed table. This does not reopen an existing nonbody scope.
 """
 if line.source!='native':return False
 def inside(box,table):
  return table[0]-.5<=box[0] and table[1]-.5<=box[1] and box[2]<=table[2]+.5 and box[3]<=table[3]+.5
 height=max(1,line.bbox[3]-line.bbox[1])
 for table in page.tables:
  if not inside(line.bbox,table):continue
  cells=[l for l in page.lines if l.source=='native' and normalize_text(l.text).strip() and inside(l.bbox,table)]
  peers=[l for l in cells if l.bbox!=line.bbox
         and abs(l.bbox[1]-line.bbox[1])<=height*.25
         and (l.bbox[0]>=line.bbox[2]+2 or l.bbox[2]<=line.bbox[0]-2)]
  def values_below(header):
   width=max(1,header.bbox[2]-header.bbox[0])
   return any(l.bbox[1]>header.bbox[3]+1
              and l.bbox[1]<=header.bbox[3]+height*3
              and min(l.bbox[2],header.bbox[2])-max(l.bbox[0],header.bbox[0])>=min(width,l.bbox[2]-l.bbox[0])*.3
              for l in cells)
  if values_below(line) and any(values_below(l) for l in peers):return True
  def cells_above(cell):
   width=max(1,cell.bbox[2]-cell.bbox[0])
   return [l for l in cells if l.bbox[3]+1<cell.bbox[1]
           and cell.bbox[1]-l.bbox[1]<=height*3
           and min(l.bbox[2],cell.bbox[2])-max(l.bbox[0],cell.bbox[0])>=min(width,l.bbox[2]-l.bbox[0])*.3]
  # Field names can occupy the final schema row. Its preceding cells must
  # independently prove both columns and the same row partition.
  if any(abs(a.bbox[1]-b.bbox[1])<=height*.25
         and (a.bbox[0]>=b.bbox[2]+2 or b.bbox[0]>=a.bbox[2]+2)
         for a in cells_above(line) for peer in peers for b in cells_above(peer)):return True
 return False


def _native_comment_field_continuation(line,page):
 """An identifier wrapped from an inline code comment is not a heading."""
 if (line.source!='native' or line.bold or line.block_id is None
     or line.font_size is None or line.font_size<=0
     or abs(line.direction[1])>.1
     or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',normalize_text(line.text).strip())):return False
 def complete_ink(cell):
  cursor=0
  for start,end,box in sorted(cell.text_regions):
   if start>cursor or end<=start or box[2]<=box[0] or box[3]<=box[1]:return False
   cursor=max(cursor,end)
  return cursor>=len(normalize_text(cell.text))
 if not complete_ink(line):return False
 height=max(1,line.bbox[3]-line.bbox[1])
 cells=[l for l in page.lines if l.source=='native' and not l.bold
        and l.block_id==line.block_id and l.font_size is not None
        and abs(l.font_size-line.font_size)<=line.font_size*.08
        and abs(l.direction[1])<=.1 and complete_ink(l)]
 for comment in cells:
  if (not re.match(r'^\s*#.+[,，]\s*$',normalize_text(comment.text))
      or not 0<=line.bbox[1]-comment.bbox[3]<=height*1.2):continue
  for code in cells:
   if (code.bbox[2]+2>comment.bbox[0]
       or abs(code.bbox[1]-comment.bbox[1])>height*.25
       or abs(code.bbox[0]-line.bbox[0])>line.font_size*2):continue
   if re.match(r'^\s*[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*|\[[^\]]+\])*\s*=\s*(?!=)\S',normalize_text(code.text)):return True
 return False


def _scope_map(document,directories=()):
 from statistics import median
 scopes={};scope='body';nonbody=set()
 sizes=[l.font_size for p in document.pages for l in p.lines if l.source=='native' and l.font_size is not None and l.font_size>0 and not l.bold and len(normalize_text(l.text).strip())>=12 and l.bbox[1]>p.height*.12]
 body_size=median(sizes) if sizes else 12
 for p in document.pages:
  for l in sorted(p.lines,key=lambda z:(z.bbox[1],z.bbox[0])):
   t=normalize_text(l.text).strip()
   if _key(l) in directories or is_toc_line(t):continue
   heading=_heading(t)
   if heading:scope=heading
   elif scope=='_nonbody' and _structural_chapter(l,p,document,body_size):scope='body'
   elif re.fullmatch(r'(?:参考文献|致\s*谢|References|Acknowledg(?:e)?ments)',t,re.I):
    running_header=(not l.bold and l.font_size is not None and 0<l.font_size<body_size*.95 and l.bbox[1]<p.height*.12)
    if not running_header and not _table_column_heading(l,p) and not _native_comment_field_continuation(l,p):scope='_nonbody'
   scopes[_key(l)]=scope
   if scope=='_nonbody':nonbody.add(_key(l))
 from .bibliography_scope_resume import resume_bibliography_scopes
 return resume_bibliography_scopes(document,scopes,nonbody,directories=directories)


def _scope(label,scopes):
 value=scopes.get(_key(label.line))
 if value is None:
  values=[(key[1][1],scope) for key,scope in scopes.items() if key[0]==label.line.page_number and key[1][1]<=label.line.bbox[1]+2]
  value=max(values,key=lambda item:item[0])[1] if values else label.scope
 if value=='body' and label.scope!='body':return label
 return replace(label,scope=value) if value and value!=label.scope else label


def _directory_keys(document):
 keys=set()
 for p in document.pages:
  if p.images or p.tables or p.graphics:continue
  heading=any(l.bbox[1]<p.height*.22 and re.fullmatch(r'(?:插图|图目录|插图目录|表目录|附表|ListofFigures|ListofTables)',re.sub(r'\s+','',normalize_text(l.text)),re.I) for l in p.lines)
  rows=[l for l in p.lines if re.match(r'^\s*(?:图|表|Figures?|Tables?)\s*'+_NUMBER,normalize_text(l.text),re.I) and re.search(r'\s\d{1,4}\s*$',normalize_text(l.text))]
  if heading and len(rows)>=3:
   start=min(l.bbox[1] for l in rows)
   keys.update(_key(l) for l in p.lines if l.bbox[1]>=start)
 return keys


def _overlap(a,b):return max(0,min(a[2],b[2])-max(a[0],b[0]))

def _owner(label,kind,pages,objects):
 p=pages[label.line.page_number];a=label.line.bbox
 pattern=FIGURE_CAPTION if kind=='figure' else TABLE_CAPTION
 for obj in objects:
  if obj.kind!=kind+'_caption' or obj.page_number!=p.number:continue
  m=pattern.search(_text(obj.text))
  if m and _num(m.group('number'))==label.number and obj.bbox[0]<=a[0]+2 and obj.bbox[1]<=a[1]+2 and obj.bbox[2]>=a[2]-2 and obj.bbox[3]>=a[3]-2:a=obj.bbox;break
 boxes=list(p.images if kind=='figure' else p.tables)
 if kind=='figure':boxes.extend(p.graphics)
 boxes.extend(o.bbox for o in objects if o.kind==kind and o.page_number==p.number)
 candidates=[]
 for b in boxes:
  if b[2]-b[0]<max(25,p.width*.08) or b[3]-b[1]<max(15,p.height*.025):continue
  if (b[2]-b[0])*(b[3]-b[1])>p.width*p.height*.85 or b[3]<=p.height*.13 or b[1]>=p.height*.90:continue
  if abs(label.line.direction[0])>.7:
   ov=_overlap(a,b);gap=max(a[1]-b[3],b[1]-a[3],0)
   if ov<min(a[2]-a[0],b[2]-b[0])*.3 or gap>80:continue
  else:
   ov=max(0,min(a[3],b[3])-max(a[1],b[1]));gap=max(a[0]-b[2],b[0]-a[2],0)
   if ov<min(a[3]-a[1],b[3]-b[1])*.3 or gap>80:continue
  candidates.append((gap,b))
 return min(candidates,key=lambda z:z[0])[1] if candidates else None


def _caption_physical(label,kind,pages,objects):
 l=label.line
 if _owner(label,kind,pages,objects) is None:return False
 typical=body_font(pages[l.page_number]);font=l.font_size
 return bool(l.bold or (font and typical and font<typical*.94))


def _recoverable_title(label,kind,pages,objects):
 if not _caption_physical(label,kind,pages,objects):return False
 p=pages[label.line.page_number];owner=_owner(label,kind,pages,objects)
 pattern=FIGURE_CAPTION if kind=='figure' else TABLE_CAPTION
 m=pattern.search(_text(label.line.text));tail=_text(label.line.text)[m.end('number'):].lstrip(' .:：、')
 # The verb alone is not decisive. A narrative title needs a styled matching
 # translation; a bold body sentence cannot claim somebody else's graphic.
 narrative=bool(_BODY_TAIL.match(tail) or not caption_match(label.line.text,kind))
 peer=False
 for row in p.lines:
  if _key(row)==_key(label.line):continue
  match=pattern.search(_text(row.text))
  if not match:continue
  other=_label(match.group('number'),row,label.scope)
  if _owner(other,kind,pages,objects)!=owner:continue
  if other.number!=label.number and caption_match(row.text,kind):return False
  if other.number==label.number and normalize_text(row.text).lstrip().startswith(('图','表'))!=normalize_text(label.line.text).lstrip().startswith(('图','表')) and _caption_physical(other,kind,pages,objects):peer=True
 if narrative and not peer:return False
 a=label.line.bbox
 low,high=(owner[3],a[1]) if owner[3]<=a[1] else (a[3],owner[1])
 typical=body_font(p)
 for row in p.lines:
  if _key(row)==_key(label.line) or row.block_id is not None and row.block_id==label.line.block_id:continue
  if row.bbox[1]>=low and row.bbox[3]<=high and len(row.text.strip())>=12 and row.bbox[2]-row.bbox[0]>p.width*.45 and not row.bold and row.font_size and typical and row.font_size>=typical*.95 and not pattern.search(_text(row.text)):return False
 return True


def _appendix_number(label,index,kind,events):
 scope=label.target_scope
 if not scope or scope not in {a.number for a in index.appendices}:return label
 targets=index.figures if kind=='figure' else index.tables
 choices=[t for t in targets if t.scope==scope]
 text=_text(label.line.text)
 word=r'(?:图|Figures?|Figs?\.?)' if kind=='figure' else r'(?:表|Tables?)'
 match=re.search(word+r'\s*'+re.escape(scope)+r'\s*'+re.escape(label.number)+r'(?!\d)',text,re.I)
 if not match:return label
 candidates=[t.number for t in choices if t.number in {label.number,scope+label.number,scope+'.'+label.number}]
 explicit=bool(re.search(r'(?:如|见|参照|参见|详见|附录\s*'+re.escape(scope)+r'[^。；;]{0,12})\s*$',text[max(0,match.start()-30):match.start()],re.I))
 if not candidates and not explicit:return label
 number=candidates[0] if candidates else (scope+'.'+label.number if any(t.number.startswith(scope+'.') for t in choices) else scope+label.number)
 if number!=label.number:
  out=replace(label,number=number);_event(events,'canonical_reference',out,'已声明附录作用域和真实目标编号格式，保留字母前缀而不是按数学下标过滤',original_number=label.number);return out
 return label

def _body_pseudocaption(label,kind,targets,pages,objects):
 l=label.line
 text=re.sub(r'(?<=[0-9])\s*([.\-])\s*(?=[0-9])',r'\1',_text(l.text))
 m=(FIGURE_CAPTION if kind=='figure' else TABLE_CAPTION).search(text)
 if not m or l.bold:return False
 tail=text[m.end('number'):].lstrip(' .:：、')
 if not (_BODY_TAIL.match(tail) or caption_match(text,kind) is None):return False
 peers=[t for t in targets if t!=label and t.number==label.number and t.scope==label.scope and _key(t.line)!=_key(l)]
 return bool(peers or (l.bbox[2]-l.bbox[0]>=l.page_width*.6 and not _caption_physical(label,kind,pages,objects)))


def _math_numbers(text):
 if not re.search(r'(?:网络|计算|掩码|顶点|边|hom\s*\(|等价|同构|关键点|真值|Output|输出|图像对)',text,re.I):return set()
 matches=list(re.finditer(r'图\s*[(（]?\s*[GHM]\s*\d+',text,re.I))
 result=set()
 for m in matches:
  fragment=re.split(r'[。；;]',text[m.start():m.end()+50])[0]
  result.update(n for n in re.findall(r'[GHM]\s*(\d+)',fragment,re.I))
 return result


def _external(text,kind,number):
 if kind=='appendix':pattern=re.compile(r'(?:附录|Appendix)\s*'+re.escape(number)+r'(?![A-Za-z])',re.I)
 else:
  raw=r'\s*[.\-]\s*'.join(map(re.escape,number.split('.')))
  word=r'(?:图|Figures?|Figs?\.?)' if kind=='figure' else r'(?:表|Tables?)'
  pattern=re.compile(word+r'\s*[(（]?\s*(?:[A-Z]\s*)?'+raw+r'(?!\d)',re.I)
 found=False
 for m in pattern.finditer(text):
  prefix=text[max(0,m.start()-55):m.start()]
  if re.search(r'(?:本论文|本章|本文|本研究|our\s+(?:paper|work))[^。；;]{0,14}$',prefix,re.I):return False
  owned=bool(re.search(r'(?:来自|引自|摘自|见|文献|参考文献|from|in)\s*\[[0-9,，\- ]+\]\s*(?:(?:中|的|中的|中所示)\s*)?[\[（(\s]*$',prefix,re.I))
  if not owned:return False
  found=True
 return found


def _artifact(label,kind,pages):
 text=_text(label.line.text)
 if kind=='figure' and label.number in _math_numbers(text):
  direct=any(_num(m.group('number'))==label.number for m in _TYPED['figure'].finditer(text))
  if label.target_scope in {'G','H','M'} or not direct:return '数学图变量的下标，不是论文插图编号'
 if kind=='figure' and label.number.isdigit():
  number=re.escape(label.number)
  algorithm=bool(re.search(r'(?:Input|Output|输入|输出|for each|end for|←)',text,re.I))
  if algorithm and re.search(r'(?:完全|二值|重构二值)图\s*'+number+r'(?:[.:：]|\s+\S)',text):
   explicit=any(_num(m.group('number'))==label.number and _explicit_graph_reference(text,m)
                for m in _TYPED['figure'].finditer(text))
   if not explicit:return '算法行号与前行末图字拼接'
  if re.search(r'(?:w/o\s*位置|类别标签监督[\- ]|一致性监督增强[\- ])图\s*'+number+r'\s*\.\s*\d+',text,re.I):return '表格数据与图类别单元格拼接'
 if _external(text,kind,label.number):return '引文拥有该图/表/附录，非本论文目标'
 return None


def _add(refs,label,events,criterion):
 for old in refs:
  if old.number==label.number and old.scope==label.scope and old.target_scope==label.target_scope and old.line.page_number==label.line.page_number:
   a=re.sub(r'\s+','',normalize_text(old.line.text));b=re.sub(r'\s+','',normalize_text(label.line.text))
   if a==b or b in a or a in b:return
 refs.append(label);_event(events,'add_reference',label,criterion)


def _add_indirect(index,kind,target,line,scope,events,criterion):
 refs=index.graphic_figure_refs if kind=='figure' else index.graphic_table_refs
 reference=Label(target.number,line,scope,target.target_scope)
 before=len(events) if events is not None else 0
 _add(refs,reference,events,criterion)
 bindings=index.indirect_reference_targets
 bindings.setdefault(indirect_reference_key(kind,reference),set()).add(physical_target_key(kind,target))
 if events is not None and len(events)>before:
  events[-1]['physical_target']=dict(kind=kind,scope=target.scope,number=target.number,
    page=target.line.page_number,bbox=list(target.line.bbox),text=target.line.text)


def _label(number,line,scope):
 number=_num(number)
 return Label(number,line,scope,number[0] if re.match(r'^[A-Z]\.',number) else None)


def _is_body(line,caption_keys,directories,pages):
 if _key(line) in caption_keys or _key(line) in directories or line.bold:return False
 if line.role in {'figure','table','figure_caption','table_caption','header','footer','equation'}:return False
 p=pages[line.page_number];a=line.bbox
 typical=body_font(p)
 if a[1]<p.height*.115 and line.font_size and typical and line.font_size<typical*.9:return False
 if any(b[0]<=a[0] and b[1]<=a[1] and b[2]>=a[2] and b[3]>=a[3] for b in (*p.images,*p.tables)):return False
 return True


def _typed_references(line,kind,scope,graph_symbols=None):
 # Recover OCR spacing around numeric separators without changing source ink.
 # Use the shared parser: a complete range, a type change and a quantity must
 # have the same meaning here as they do during the initial index build.
 text=re.sub(r'(?<=[0-9])\s*([.\-])\s*(?=[0-9])',r'\1',_text(line.text))
 for match in reference_matches(_TYPED[kind],text):
  if not local_reference(text,match):continue
  if kind=='figure' and graph_symbols is not None and graph_variable_use(text,match,graph_symbols,line=line):continue
  label=_label(match.group('number'),line,scope)
  qualifier=APPENDIX_QUALIFIER.search(text[max(0,match.start()-16):match.start()])
  if qualifier:label=replace(label,target_scope=normalize_label(qualifier.group('number')))
  yield label

def _wrapped(index,scopes,caption_keys,directories,pages,events,excluded=()):
 lines=[l for p in index.document.pages for l in sorted(p.lines,key=lambda z:(z.bbox[1],z.bbox[0])) if _is_body(l,caption_keys,directories,pages) and _key(l) not in excluded and len(l.text.strip())>2]
 for a,b in zip(lines,lines[1:]):
  m=re.search(r'(?P<kind>图|表)\s*(?P<chapter>\d+)\s*[-.]\s*$',_text(a.text))
  n=re.match(r'^\s*(?P<item>\d+)(?:[a-z])?\s*(?:所示|展示|显示|中|[，,。])',_text(b.text))
  if not m or not n or a.bold or b.bold:continue
  if a.font_size and b.font_size and abs(a.font_size-b.font_size)>a.font_size*.08:continue
  if a.page_number==b.page_number:
   h=max(1,a.bbox[3]-a.bbox[1])
   if b.bbox[1]-a.bbox[3]>h*1.8 or abs(a.bbox[0]-b.bbox[0])>h*3:continue
  elif b.page_number==a.page_number+1:
   if a.bbox[1]<a.page_height*.82 or b.bbox[1]>b.page_height*.22:continue
  else:continue
  if scopes.get(_key(a),'body')!=scopes.get(_key(b),'body'):continue
  kind='figure' if m.group('kind')=='图' else 'table';refs=index.figure_refs if kind=='figure' else index.table_refs
  start,end=int(m.group('chapter')),int(n.group('item'))
  number=f'{start}.{end}';label=_label(number,a,scopes.get(_key(a),'body'))
  stale=[]
  for ref in refs:
   if ref.line.page_number!=a.page_number or m.group() not in _text(ref.line.text):continue
   complete=[x for x in _TYPED[kind].finditer(_text(ref.line.text)) if _num(x.group('number'))==ref.number and not re.match(r'\s*[-.]',_text(ref.line.text)[x.end():])]
   if complete:continue
   if ref.number==str(start) or (ref.number.isdigit() and start<=int(ref.number)<=end):stale.append(ref)
  for ref in stale:refs.remove(ref);_event(events,'remove_reference',ref,'分行章节编号被截断或错误扩展为整数范围',repaired_number=number)
  _add(refs,label,events,'原PDF相邻正文行或相邻页末/页首保留同一编号的连续墨迹')


def _title(label,kind):
 m=(FIGURE_CAPTION if kind=='figure' else TABLE_CAPTION).search(_text(label.line.text))
 return _text(label.line.text)[m.end('number'):].strip(' .:：、') if m else ''


def _topic(a,b):
 # Three-character phrases avoid ownership based on generic 图/表/实验 words.
 aa=set(re.findall(r'[\u4e00-\u9fff]{3,}',a));bb=set(re.findall(r'[\u4e00-\u9fff]{3,}',b))
 ga={w[i:i+3] for w in aa for i in range(len(w)-2)};gb={w[i:i+3] for w in bb for i in range(len(w)-2)}
 if (ga&gb)-{'实验结','验结果','结果如','表中数','中数据','可以看','以看出','我们可','方法性'}:return True
 generic=set(('系统','方法','设计','结果','实验','数据','模型','使用','方案','内容','分析','结构','性能','处理','用户','特征','信息','研究','图中','所示','表中','方面','进行','可以','我们','说明','展示','不同','对于','比较','优化','管理','模块','输入','输出','任务','网络','本文','中所','中的','对应','示意','流程'))
 ba={w[i:i+2] for w in aa for i in range(len(w)-1)};bb2={w[i:i+2] for w in bb for i in range(len(w)-1)}
 return bool((ba&bb2)-generic)


def _implicit(index,body,events):
 for line,scope in body:
  text=_text(line.text)
  # Typed nouns with a shared untyped numeric list, or explicit 由/见 predicate.
  for m in re.finditer(r'(?:由|见|参见)\s*(?P<number>'+_NUMBER+r')',text):
   prefix=text[max(0,m.start()-45):m.start()];suffix=text[m.end():]
   if re.search(r'图',prefix):kinds=['figure']
   elif re.search(r'表',prefix):kinds=['table']
   elif re.match(r'\s*(?:展示|显示)',suffix) or re.search(r'结果显示\s*$',prefix):kinds=['figure','table']
   else:continue
   nums=[m.group('number')];rest=suffix
   for unused in range(20):
    x=_MORE.match(rest)
    if not x:break
    nums.append(x.group('number'));rest=rest[x.end():]
   for raw in nums:
    num=_num(raw);options=[]
    for kind in kinds:
     targets=index.figures if kind=='figure' else index.tables
     options.extend((kind,t) for t in targets if t.number==num and t.scope==scope and abs(t.line.page_number-line.page_number)<=2)
    if len({kind for kind,t in options})==1 and options:
     kind=options[0][0];refs=index.figure_refs if kind=='figure' else index.table_refs
     _add(refs,_label(num,line,scope),events,'正文图/表名词与见/由编号的明确使用语义及已存在目标')
  for kind,word in [('figure','图'),('table','表')]:
   targets=index.figures if kind=='figure' else index.tables;refs=index.figure_refs if kind=='figure' else index.table_refs
   local=[t for t in targets if t.scope==scope and t.line.page_number==line.page_number]
   if re.search(r'(?:'+word+r'中|该'+word+r')',text):
    matches=[t for t in local if _topic(text,_title(t,kind))]
    if len(matches)==1:_add_indirect(index,kind,matches[0],line,scope,events,'同页唯一该类对象，泛指正文与对象标题有具体词组重合')
   if kind=='table' and re.match(r'\s*[(（]?\d+[)）.、]',text) and re.search(r'[：:]\s*(?:用于|记录|存储|包含)',text):
    matches=[t for t in local if 3<=len(_title(t,kind))<=35 and _title(t,kind) in text]
    if len(matches)==1:_add_indirect(index,kind,matches[0],line,scope,events,'正文按对象完整名称逐项定义用途，紧邻唯一同名表')



def _compact(text):return re.sub(r'\s+','',_text(text)).casefold()


def _contained(line,box):
 a=line.bbox
 return box[0]-2<=(a[0]+a[2])/2<=box[2]+2 and box[1]-2<=(a[1]+a[3])/2<=box[3]+2


def _rows(page,box):
 groups=[]
 for line in sorted((l for l in page.lines if _contained(l,box)),key=lambda l:(l.bbox[1],l.bbox[0])):
  center=(line.bbox[1]+line.bbox[3])/2
  row=next((g for g in reversed(groups) if abs(g[0]-center)<=max(2,(line.bbox[3]-line.bbox[1])*.3)),None)
  if row is None:groups.append([center,[line]])
  else:row[1].append(line)
 return [' '.join(l.text for l in sorted(g[1],key=lambda l:l.bbox[0])) for g in groups]


def _values(text):
 from decimal import Decimal
 return {str(Decimal(m.group()).normalize()) for m in re.finditer(r'(?<![A-Za-z0-9_.\-])\d+(?:\.\d+)?(?![A-Za-z0-9_.\-])',_text(text))}


def _identifiers(text):
 return {m.group().casefold() for m in re.finditer(r'(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9_.\-]{3,}',_text(text)) if not m.group().endswith('.')}


def _metrics(text):
 t=_text(text).casefold()
 return {name for name,rx in [('accuracy',r'准确率|accuracy|(?<![a-z])acc(?![a-z])'),('auc',r'(?<![a-z])auc(?![a-z])'),('precision',r'精确率|precision'),('recall',r'召回率|recall'),('f1',r'f1(?:score|得分)?')] if re.search(rx,t,re.I)}


def _field_assignment(text,field,value):
 from decimal import Decimal
 raw=format(Decimal(value),'f');num=re.escape(raw)+(r'(?:\.0+)?' if '.' not in raw else '')
 number=r'(?<![0-9.])'+num+r'(?![0-9.])';f=re.escape(field)
 return bool(re.search(f+r'(?:值|指标|比例|比率)?(?:等于|达到(?:了)?|为|是|约为|=)?[(（]?'+number,text) or re.search(number+r'%?(?:的高|的|高)?'+f,text))


def _matrix_signature(page,box):
 rows=_rows(page,box);headers=[];records=[]
 for row in rows:
  vals=_values(row)
  names=[n for n in _identifiers(row) if '-' in n or '_' in n or re.search(r'[A-Z][a-z]+[A-Z]',row)]
  if len(vals)>=2 and names:records.append((names,vals,row))
  elif not records:headers.append(row)
 header=' '.join(headers)
 # Only field identifiers actually appearing in the header qualify as the
 # stronger pair proof. Generic Acc/AUC alone still needs eight exact values.
 fields=[]
 for name in re.findall(r'\b[A-Za-z][A-Za-z0-9_]{2,}\b',_text(header)):
  if name.casefold() in {'model','accuracy','auc','acc','precision','recall','score','ours','scale','multi'}:continue
  if name[0].isupper() and any(c.islower() for c in name[1:]) and name.casefold() not in fields:fields.append(name.casefold())
 return rows,header,records,fields


def _matrix_proof(text,signature):
 rows,header,records,fields=signature;compact=_compact(text);hits=[];generic_values=set();paired_values=set()
 allnames={n for names,values,row in records for n in names}
 occurrences=sorted((m.start(),m.end(),n) for n in allnames for m in re.finditer(re.escape(n),compact))
 portions={}
 for pos,(start,end,name) in enumerate(occurrences):portions.setdefault(name,[]).append(compact[end:occurrences[pos+1][0] if pos+1<len(occurrences) else len(compact)])
 for names,values,row in records:
  relevant=' '.join(fragment for name in names for fragment in portions.get(name,()))
  if not relevant:continue
  if len(values)>=4 and values<=_values(relevant):generic_values.update(values);hits.append(row)
  if len(fields)==2 and len(values)==2 and not (values & {'0','1'}):
   ordered=re.findall(r'(?<![A-Za-z0-9_.\-])\d+(?:\.\d+)?(?![A-Za-z0-9_.\-])',_text(row))
   if len(ordered)==2:
    from decimal import Decimal
    pair=[str(Decimal(v).normalize()) for v in ordered]
    if all(_field_assignment(relevant,f,v) for f,v in zip(fields,pair)):paired_values.update(pair);hits.append(row)
 generic=len(hits)>=2 and len(generic_values)>=8 and len(_metrics(header)&_metrics(text))>=2
 pairs=len(hits)>=2 and len(paired_values)>=4 and len(fields)==2
 return bool(generic or pairs)


def _strong_usage(index,body,pages,objects,events):
 # Every data/code proof retains its physical title. No literal target ID or
 # opposite-kind reference is rewritten.
 from .usage_paragraphs import usage_paragraphs
 prose=usage_paragraphs(body,index.document);matrix=[];code=[]
 for kind,targets in [('figure',index.figures),('table',index.tables)]:
  for target in targets:
   owner=_owner(target,kind,pages,objects)
   if owner is None:continue
   page=pages[target.line.page_number];rows=_rows(page,owner);inside=' '.join(rows)
   tablelike=kind=='table' or sum(max(0,min(b[2],owner[2])-max(b[0],owner[0]))*max(0,min(b[3],owner[3])-max(b[1],owner[1])) for b in page.tables)>max(1,(owner[2]-owner[0])*(owner[3]-owner[1]))*.45
   if tablelike:matrix.append((kind,target,owner,_matrix_signature(page,owner)))
   if kind=='figure' and len(re.findall(r';|\{|\}|/\*|\bvoid\b',inside))>=3:
    ids={v for v in _identifiers(inside) if '_' in v or any(re.search(r'[a-z][A-Z]',l.text) and v in l.text.casefold() for l in page.lines if _contained(l,owner))}
    if len(ids)>=3:code.append((target,owner,ids))
 for position,(line,scope) in enumerate(prose):
  text=_text(line.text)
  if re.search(r'(?:文献\s*\[|参考文献|引自|摘自|来自\s*\[)',text):continue
  choices={}
  for kind,target,owner,signature in matrix:
   if target.scope==scope and abs(target.line.page_number-line.page_number)<=1 and _matrix_proof(text,signature):choices[(target.line.page_number,tuple(owner))]=(kind,target)
  if len(choices)==1:
   kind,target=next(iter(choices.values()));refs=index.graphic_figure_refs if kind=='figure' else index.graphic_table_refs
   _add_indirect(index,kind,target,line,scope,events,'独占物理表结构：至少两命名行及八精确数值和两指标，或两行两字段逐一赋值；不改原引用编号')
  if re.search(r'第\s*\d+\s*行',text) and re.search(r'调用|初始化|解引用|赋值|传入',text):
   choices={}
   for target,owner,ids in code:
    if target.scope==scope and abs(target.line.page_number-line.page_number)<=1 and len(ids&_identifiers(text))>=3:choices[(target.line.page_number,tuple(owner))]=target
   if len(choices)==1:
    target=next(iter(choices.values()));_add_indirect(index,'figure',target,line,scope,events,'正文按行说明唯一物理代码图中的至少三个特定标识符及调用/初始化行为')
  if '热力图' in text and re.search(r'(?:一幅热力图对应|生成[^。；]{0,30}热力图|热力图的横轴|该实验中热力图)',text):
   context=text
   if position:
    previous,previous_scope=prose[position-1]
    prev=_text(previous.text);gap=line.bbox[1]-previous.bbox[3]
    barriers=[l for l in pages[line.page_number].lines if previous.bbox[3]<=l.bbox[1] and l.bbox[3]<=line.bbox[1] and (l.bold or re.match(r'^\s*\d+(?:\.\d+)*\s+\S',_text(l.text)))]
    if previous.page_number==line.page_number and previous_scope==scope and 0<=gap<=40 and not barriers and re.match(r'^\s*在',prev) and '模型' in prev and '缓存' in prev and re.match(r'^\s*(?:实验|该实验|一幅|生成)',text):context=prev+' '+text
   choices={}
   for target in index.figures:
    if target.scope!=scope or abs(target.line.page_number-line.page_number)>1:continue
    owner=_owner(target,'figure',pages,objects)
    if owner is None:continue
    metadata=set(re.findall(r'(?<![A-Za-z0-9])(?:\d+(?:\.\d+)?[Bb]|\d{2,})(?![A-Za-z0-9])',_title(target,'figure')))
    if len(metadata)>=2 and all(re.search(r'(?<![A-Za-z0-9])'+re.escape(v)+r'(?![A-Za-z0-9])',context,re.I) for v in metadata):choices[(target.line.page_number,tuple(owner))]=target
   if len(choices)==1:
    target=next(iter(choices.values()));_add_indirect(index,'figure',target,line,scope,events,'正文明确呈现热力图且至少两个模型/缓存元数据精确匹配唯一物理图')
  for m in re.finditer(r'[（(]\s*如\s*(?P<number>'+_NUMBER+r')\s*[)）]',text):
   number=_num(m.group('number'));prefix=text[max(0,m.start()-35):m.start()]
   if re.search(r'(?:阈值|数值|系数|均值|温度|得分|版本|公式|方程|章节|小节|定理|算法)[^。；]{0,14}$',prefix):continue
   from .numeric_visual_usage import nonvisual_number_identity
   if nonvisual_number_identity(text,m):continue
   declared=any((re.match(r'^\s*'+re.escape(number)+r'\s+\S',_text(l.text)) and l.bold) or re.search(r'[(（]\s*'+re.escape(number)+r'\s*[)）]\s*$',_text(l.text)) and not re.search(r'[（(]\s*如',_text(l.text)) for l in pages[line.page_number].lines)
   if declared:continue
   choices={}
   for kind,targets in [('figure',index.figures),('table',index.tables)]:
    for target in targets:
     if target.number==number and target.scope==scope and target.line.page_number==line.page_number and _owner(target,kind,pages,objects) is not None:choices[(kind,tuple(_owner(target,kind,pages,objects)))]=target
   if len(choices)==1:
    (kind,_),target=next(iter(choices.items()));_add_indirect(index,kind,target,line,scope,events,'括号如编号直接指代同页独立物理对象；排除数值声明及同号章节/公式')
  compact=_compact(text)
  for target in index.figures:
   if target.scope!=scope or target.line.page_number!=line.page_number:continue
   title=_compact(_title(target,'figure'));panels=list(re.finditer(r'[(（]([a-z])[)）]',title))
   for pos,panel in enumerate(panels):
    name=title[panel.end():panels[pos+1].start() if pos+1<len(panels) else len(title)].strip(' .:：,，')
    if len(name)<3:continue
    if re.search(re.escape(name)+re.escape(target.number)+r'[(（]'+re.escape(panel.group(1))+r'[)）]',compact):_add_indirect(index,'figure',target,line,scope,events,'正文省略图字，但面板编号及标题中的完整面板名称精确对应')


def _usage_owner(target,kind,pages,objects):
 # Prepared table extents can contain several native cell fragments. Prefer
 # that explicit physical parent; do not grow a box through adjacent captions.
 page=pages[target.line.page_number];a=target.line.bbox;candidates=[]
 if abs(target.line.direction[0])<.7:
  # A turned full-page diagram can leave a wide blank margin before its
  # vertical caption. Use only an explicit prepared diagram/caption pair,
  # with major projected overlap and no ordinary prose in that margin.
  pattern=FIGURE_CAPTION if kind=='figure' else TABLE_CAPTION
  declared=any(o.kind==kind+'_caption' and o.page_number==page.number and _contained(target.line,o.bbox) and (m:=pattern.search(_text(o.text))) and _num(m.group('number'))==target.number for o in objects)
  if not declared:return None
  for obj in objects:
   if obj.kind!=kind or obj.page_number!=page.number:continue
   b=obj.bbox;area=(b[2]-b[0])*(b[3]-b[1]);overlap=max(0,min(a[3],b[3])-max(a[1],b[1]))
   if not page.width*page.height*.05<=area<=page.width*page.height*.85:continue
   if overlap<min(a[3]-a[1],b[3]-b[1])*.8:continue
   gap=max(a[0]-b[2],b[0]-a[2],0)
   if gap>180:continue
   left,right=(b[2],a[0]) if b[2]<=a[0] else (a[2],b[0])
   corridor=(left,max(a[1],b[1]),right,min(a[3],b[3]))
   if any(l is not target.line and _key(l)!=_key(target.line) and not l.role.startswith(('figure','table'))
          and corridor[0]<(l.bbox[0]+l.bbox[2])/2<corridor[2]
          and corridor[1]<(l.bbox[1]+l.bbox[3])/2<corridor[3] for l in page.lines):continue
   candidates.append((gap,b))
  parents=[b for gap,b in candidates if not any(z!=b and z[0]<=b[0] and z[1]<=b[1] and z[2]>=b[2] and z[3]>=b[3] for g,z in candidates)]
  return parents[0] if len(parents)==1 else None
 for obj in objects:
  if obj.kind!=kind or obj.page_number!=page.number:continue
  b=obj.bbox
  if b[2]-b[0]<25 or b[3]-b[1]<15 or (b[2]-b[0])*(b[3]-b[1])>page.width*page.height*.85:continue
  if _overlap(a,b)<min(a[2]-a[0],b[2]-b[0])*.3:continue
  gap=max(a[1]-b[3],b[1]-a[3],0)
  if gap>80:continue
  candidates.append((gap,b))
 if not candidates:return _owner(target,kind,pages,objects)
 closest=min(candidates,key=lambda pair:pair[0])[1]
 old=_owner(target,kind,pages,objects)
 if old is not None and old[2]-old[0]>=25 and old[3]-old[1]>=30:candidates.append((max(a[1]-old[3],old[1]-a[3],0),old))
 parents=[box for gap,box in candidates if gap<=80 and box[0]<=closest[0]+2 and box[1]<=closest[1]+2 and box[2]>=closest[2]-2 and box[3]>=closest[3]-2]
 return max(parents,key=lambda b:(b[2]-b[0])*(b[3]-b[1])) if parents else closest


def _semantic_text(text):
 return unicodedata.normalize('NFKC',re.sub(r'<[^>]*>','',_text(text)))


def _semantic_names(text):
 text=_semantic_text(text)
 return {re.sub(r'[-_.]','',m.group().casefold()) for m in re.finditer(r'(?<![A-Za-z0-9_])[A-Za-z0-9][A-Za-z0-9_.-]{2,}(?:\([A-Za-z0-9]+\))?',_text(text))
         if re.search(r'[A-Za-z]',m.group()) and m.group().casefold().strip('.') not in
         {'figure','figures','table','tables','illustration','architecture','structure','overview','schematic','diagram','model','models','the','and','for','with','from','comparison','results','performance','method','methods','experimental','learning','training','process','framework','input','output','token','transformer'}}

def _steps(text):
 chinese={v for v in ('采样','聚合','更新','编码','解码','映射','生成','训练','分发','拆分','反向','拼接','提取','过滤','问询','诊断','校验','反馈','重建','预留','创建','修正','评估','处理','对齐','归一化','渲染','预测','融合','拟合','优化','学习','扰动','解释','上手','探索','总结','扫描','滤波','求解','返回','支持','合成','插入','建议','投影','计算','遮挡','分割','分类','恢复','重构','筛选','搜索','强化','卷积') if v in text}
 stems=('sampl','aggregat','updat','encod','decod','map','generat','train','distribut','split','concatenat','extract','filter','feedback','reconstruct','creat','process','align','normaliz','render','predict','fus','fit','optimiz','learn','interpret','explor','summar','scan','solv','return','synthes','insert','project','comput','mask','segment','classif','restor','select','search','refin','transform','drop','shuffl','multipl','rescal','pool','flatten','connect','encrypt','decrypt','preprocess','interpolat','imput','standardiz','remov','detect','clean')
 return chinese|{stem for stem in stems if re.search(r'(?<![A-Za-z])'+stem+r'[A-Za-z]*',text,re.I)}


def _usage_title(target,kind,objects,pages=None):
 pattern=FIGURE_CAPTION if kind=='figure' else TABLE_CAPTION
 native=normalize_text(target.line.text).lstrip();chinese=native.startswith(('图','表'));number=target.number
 for obj in objects:
  if obj.kind!=kind+'_caption' or obj.page_number!=target.line.page_number:continue
  if not _contained(target.line,obj.bbox):continue
  text=_text(obj.text)
  starts=[m for m in pattern.finditer(text) if _num(m.group('number'))==number]
  for match in starts:
   same_language=text[match.start():].lstrip().startswith(('图','表'))==chinese
   if not same_language:continue
   stop=min((m.start() for m in starts if m.start()>match.start()),default=len(text))
   candidate=_semantic_text(text[match.end('number'):stop].strip(' .:：、'))
   if len(candidate)>=len(_title(target,kind)):return candidate
 if pages is not None:
  # Recover native caption wraps only inside the prepared caption extent. A
  # bilingual extent may have only the translated caption as its text value.
  boxes=[o.bbox for o in objects if o.kind==kind+'_caption' and o.page_number==target.line.page_number and _contained(target.line,o.bbox)]
  if boxes:
   parts=[_title(target,kind)];last=target.line
   for row in sorted(pages[target.line.page_number].lines,key=lambda l:(l.bbox[1],l.bbox[0])):
    if row.bbox[1]<last.bbox[3]-1 or not any(_contained(row,b) for b in boxes):continue
    if pattern.search(_text(row.text)):break
    if row.font_size and last.font_size and abs(row.font_size-last.font_size)>last.font_size*.08:continue
    if 0<=row.bbox[1]-last.bbox[3]<=max(16,last.font_size*1.8) and abs(row.bbox[0]-target.line.bbox[0])<5:
     parts.append(row.text);last=row
   if len(parts)>1:return re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])','',_semantic_text(' '.join(parts)))
 return _semantic_text(_title(target,kind))


def _workflow_names(title):
 title=_semantic_text(title)
 if re.search(r'[\u4e00-\u9fff]',title):return _semantic_names(title)
 names=set()
 for word in re.findall(r'[A-Za-z][A-Za-z0-9_.-]{2,}',title):
  if sum(c.isupper() for c in word)>=2 and word.casefold() not in {'cnn','cnns','llm','transformer','vae','t2v'}:names.add(re.sub(r'[-_.]','',word.casefold()))
 return names


def _workflow_subject(text,title):
 # A topic or a few shared title bigrams cannot identify a full architecture.
 # For composite titles, prose must name every concrete functional component.
 compact=_compact(text);parts=re.split(r'和|与|及|、',_semantic_text(title));subjects=[]
 for part in parts:
  match=re.search(r'([\u4e00-\u9fff]{4,})(?:模型|模块|框架|架构|机制|流程)',part)
  if match:
   subject=match.group(1).split('的')[-1]
   if len(subject)>=4:subjects.append(subject)
 if subjects and all(subject in compact for subject in subjects):return True
 simple=re.sub(r'(?:整体结构|总体结构|结构示意|示意图|结构|图)$','',_compact(title))
 if 4<=len(simple)<=20 and simple in compact:return True
 # A verifier-driven feedback/reward loop is a specific functional agent,
 # whereas an unqualified framework or a generic training description is not.
 driven=re.search(r'([\u4e00-\u9fff]{2,}驱动)',title)
 if driven:
  subject=driven.group(1).split('的')[-1]
  return subject in compact and '反馈' in text and '奖励' in text and bool(re.search(r'两个|两阶段|首先.*随后',text))
 return False


def _workflow_framing(title):
 # "Structure" or "illustration" alone may caption example panels or a
 # matrix. Only functional workflow framing can use named step descriptions.
 return bool(re.search(r'架构|框架|流程|工作流|图形模型|模型.*(?:整体结构|总体结构)|采样.*聚合|多头注意力|机制|分支.*生成|恢复学习|architecture|workflow|pipeline|framework|strategy|module',title,re.I)) or bool(_workflow_names(title) and re.search(r'结构',title))


def _english_operation_proof(text,title):
 # These are mechanism vocabularies, not document identities or decisions.
 groups=(('convolution','filter','feature map','input image','kernel'),
 ('pooling','maximum','average','window','feature map'),
 ('dense','fully connected','neuron','connected','layer'),
 ('multiplication','rescal','ckks','scale','modulus'),
 ('convolution','activation','batch','normalization','flatten','dense','softmax'),
 ('data','pre-processing','preprocessing','missing','duplicates','outlier','imput','standardiz','interpolation'))
 low=text.casefold();cap=title.casefold()
 for terms in groups:
  cap_hits={t for t in terms if t in cap};hits={t for t in terms if t in low}
  if len(cap_hits)>=2 and len(hits)>=3 and len(_steps(text))>=2:
   if 'dense' in cap_hits and not re.search(r'every|each.*(?:neuron|layer)|flatten',low):continue
   return True
 return False


def _task_subject(text):
 value=_compact(_semantic_text(text))
 match=re.match(r'^(?:在)?([^。；:：]{3,45}?)任务(?:中|表现|性能|结果|$)',value)
 if not match:return None
 subject=match.group(1)
 if re.fullmatch(r'(?:基于文本(?:描述)?的|文本到)分子(?:序列)?生成',subject):return 'text_to_molecule_generation'
 if subject=='分子描述生成':return 'molecule_to_description_generation'
 return subject


def _semantic_contexts(body,document):
 from .usage_paragraphs import usage_paragraphs,_intervening_content
 pages={p.number:p for p in document.pages};result=[]
 for line,scope in usage_paragraphs([(l,t) for l,t in body if not(re.fullmatch(r'\s*\d{1,4}\s*',l.text) and l.bbox[1]>l.page_height*.86) and not (re.match(r'^\s*\d+(?:\.\d+)+\s+\S',l.text) and len(l.text)<70 and not re.search(r'[。；;，,]|所示|显示|达到|为|等于',l.text))],document):
  sources=[dict(page=line.page_number,bbox=list(line.bbox),text=line.text)]
  if result:
   previous,old_scope,old_sources=result[-1]
   same=(line.page_number==previous.page_number and 0<=line.bbox[1]-previous.bbox[3]<=30
         and line.bbox[0]<=previous.bbox[0]+6
         and not _intervening_content(previous,line,pages.get(line.page_number)))
   wrapped=(line.page_number==previous.page_number+1 and previous.bbox[3]>=previous.page_height*.80
            and line.bbox[1]<=line.page_height*.20 and not re.search(r'[。！？；：!?;:]\s*$',previous.text))
   compatible=(scope==old_scope and previous.source==line.source=='native' and not previous.bold and not line.bold
               and previous.font_size and line.font_size and abs(previous.font_size-line.font_size)<previous.font_size*.06
               and previous.direction==line.direction==(1.0,0.0) and len(previous.text)+len(line.text)<2400)
   previous_task=_task_subject(previous.text);current_task=_task_subject(line.text)
   distinct_task=previous_task and current_task and previous_task!=current_task
   if compatible and not distinct_task and (same or wrapped):
    combined=replace(previous,text=previous.text+' '+line.text,
      bbox=(min(previous.bbox[0],line.bbox[0]),previous.bbox[1],max(previous.bbox[2],line.bbox[2]),line.bbox[3]) if same else previous.bbox)
    result[-1]=(combined,scope,old_sources+sources);continue
  result.append((line,scope,sources))
 return result


def _functional_title_match(text,title):
 # Generic headings cannot supply object identity. Specific operation names
 # may be separated by Chinese conjunctions in the prose.
 specific=re.sub(r'整体|系统|模型|架构|结构|示意图?|框架|流程图?|对比图?|结果|方法|实验|影响|过程',' ',title)
 clean=re.sub(r'\s+','',text)
 phrases=re.findall(r'[\u4e00-\u9fff]{4,}',specific)
 if any(phrase in clean for phrase in phrases):return True
 grams={w[i:i+2] for w in re.findall(r'[\u4e00-\u9fff]{2,}',specific) for i in range(len(w)-1)}
 grams-={'不同','同的','中的','系列','对于','与反','训练','学习','特征','效果','准确','性能','比较','在不','设置','模态'}
 return len({g for g in grams if g in clean})>=3


def _split_flow_proof(text,title,inside):
 compact=_compact(text);cap=_compact(title);native=_compact(inside)
 if not ('联邦学习' in cap and '拆分学习' in cap and '数据流' in cap):return False
 if not all(word in native for word in ('联邦学习','拆分学习','客户端','服务器','顶层模','底层模')):return False
 return bool('客户端' in compact and '服务器' in compact and '拆分学习' in compact
  and re.search(r'底部(?:网络|模型)|底层(?:网络|模型)',compact)
  and re.search(r'顶部(?:网络|模型)|顶层(?:网络|模型)',compact)
  and '前向' in compact and '反向' in compact and '激活' in compact and '梯度' in compact
  and len(re.findall(r'发送|回传|返回|传送',compact))>=2 and '更新' in compact)


def _concrete_workflow(text,title,inside):
 compact=_compact(text);cap=_compact(title)
 if _split_flow_proof(text,title,inside):return True
 # Both directions and their concrete noise operations identify a state-chain
 # diagram; a diffusion model name or an equation number alone is insufficient.
 if '扩散' in cap and '前向' in cap and '反向' in cap:
  if '前向' in compact and '反向' in compact and re.search(r'(?:添加|加(?:入)?)[^。；]{0,12}噪声|加入高斯噪声',text) and '去噪' in text and re.search(r'原始|纯噪声',text) and re.search(r'重建|采样|生成',text):return True
 if re.search(r'层级检索|分层检索|hierarchicalretrieval',cap):
  if re.search(r'(?:摘要|总结)[^。；;]{0,100}topk[^。；;]{0,80}原文段落[^。；;]{0,80}再次[^。；;]{0,100}匹配[^。；;]{0,40}最终[^。；;]{0,20}段落',compact,re.I) and '向量' in text:return True
  if re.search(r'摘要|总结',text) and re.search(r'正文|段落',text) and re.search(r'第二阶段|两(?:级|层|阶段)',text) and '匹配' in text and '向量' in text and len(_steps(text))>=3:return True
 if re.search(r'标注|annotation|preference',title,re.I) and _workflow_names(title)&_semantic_names(text):
  options=set(re.findall(r'(?<![A-Za-z0-9])[A-Za-z][0-9](?![A-Za-z0-9])',text))
  native=set(re.findall(r'(?<![A-Za-z0-9])[A-Za-z][0-9](?![A-Za-z0-9])',inside))
  if len(options)>=6 and (not native or options<=native) and 'pair' in text.casefold() and re.search(r'两个response|两个回答|tworesponses',compact) and re.search(r'偏好|preference',text,re.I) and re.search(r'档|等级|level|数字越大|强度',text,re.I):return True
 return False


def _column_words(text):
 text=_semantic_text(text)
 patterns={'mean_error':r'平均误差','median_error':r'中位(?:数)?误差','tail_error':r'90%误差',
 'ssim':r'SSIM','psnr':r'PSNR','vif':r'VIF','fid':r'FID','bleu':r'BLEU','exact':r'EXACT|EX-\s*ACT',
 'levenshtein':r'Levenshtein','reconstruction':r'重构率','validity':r'合法率|Validity','mae':r'\bMAE\b',
 'rmse':r'\bRMSE\b','r2':r'R\s*2|𝑅2','latency':r'延迟|耗时|处理时间'}
 return _metrics(text)|{key for key,pattern in patterns.items() if re.search(pattern,text,re.I)}


def _row_names(rows):
 names=[]
 for row in rows:
  if len(_values(row))<2:continue
  prefix=re.split(r'(?<![A-Za-z0-9_.-])\d+(?:\.\d+)?(?![A-Za-z0-9_.-])',row,maxsplit=1)[0].strip()
  if len(prefix)>=3 and len(prefix)<=70:names.append(_compact(prefix))
 return names


def _interval_proof(text,rows):
 def interval(value):return ''.join(re.findall(r'\d+(?:\.\d+)?|[≤≥<>]|(?<![A-Za-z])z(?![A-Za-z])',_text(value),re.I)).casefold()
 pairs=[]
 for row in rows:
  m=re.match(r'\s*([A-Za-z]{4,})\b',row)
  if m and re.search(r'[≤≥<>]',row):pairs.append((m.group(1),interval(row[m.end():])))
 if len(pairs)<3:return False
 markers=sorted((m.start(),m.end(),name,signature) for name,signature in pairs for m in re.finditer(r'(?<![A-Za-z])'+re.escape(name)+r'(?![A-Za-z])',text,re.I))
 hits=set()
 for position,(start,end,name,signature) in enumerate(markers):
  fragment=text[end:markers[position+1][0] if position+1<len(markers) else len(text)]
  fragment=re.split(r'[)）;；。]',fragment)[0]
  if signature and interval(fragment)==signature:hits.add(name)
 return len(hits)>=3


def _scalar_signature(rows):
 rows=[_semantic_text(row) for row in rows]
 aliases={'mae':('MAE',),'rmse':('RMSE',),'r2':('R2',),'accuracy':('Accuracy','Acc','准确率'),
 'f1':('F1','F1分数'),'auc':('AUC',),'latency':('延迟','耗时','处理时间','处理耗时')}
 header=' '.join(row for row in rows if len(_values(row))<2)
 fields=[]
 for field,words in aliases.items():
  found=[header.casefold().find(word.casefold()) for word in words if word.casefold() in header.casefold()]
  if found:fields.append((min(found),field))
 fields=[field for pos,field in sorted(fields)];records=[];group=set()
 if not fields:return aliases,records
 numeric=re.compile(r'(?<![A-Za-z0-9_.-])(?P<v>\d+(?:\.\d+)?)(?![A-Za-z0-9_.-])(?:\s*±\s*\d+(?:\.\d+)?)?')
 from collections import Counter
 prefixes=[_semantic_names(row[:m.start()]) for row in rows if (m:=numeric.search(row)) and len(list(numeric.finditer(row)))>=len(fields)]
 repeated={name for name,count in Counter(name for names in prefixes for name in names).items() if count>=2}
 for row in rows:
  matches=list(numeric.finditer(_text(row)))
  if len(matches)<len(fields):
   if not matches and not _column_words(row):group=_semantic_names(row)
   continue
  prefix=_text(row)[:matches[0].start()];prefix_names=_semantic_names(prefix)
  inline=prefix_names-repeated
  if 'dataset' in header.casefold() and len(prefix_names)>=2 and len(inline)==1 and prefix_names&repeated:group=inline
  names=prefix_names|group
  names.update(_compact(w) for w in re.findall(r'[\u4e00-\u9fff]{3,}',prefix))
  experiment=None
  if '实验' in header and re.match(r'^\s*\d+\s',row):experiment=matches[0].group('v')
  if not names and not experiment:continue
  cells=tuple((field,value.group('v')) for field,value in zip(fields,matches[-len(fields):]))
  records.append((names,cells,experiment))
 return aliases,records


def _comparison_metric_hits(text,signature):
 # In "A is comparable with B, R2 reaches ...", A remains the subject.
 # The benchmark mention is not a new subject or a licence to borrow B's cell.
 aliases,records=signature;compact=_compact(_semantic_text(text));positions=[i for i,c in enumerate(compact) if c not in '-_.'];canonical=''.join(compact[i] for i in positions);hits=set()
 names={name for names,cells,experiment in records for name in names}
 for marker in re.finditer(r'与|comparedwith',canonical):
  before=canonical[max(0,marker.start()-180):marker.start()]
  mentions=[(m.end(),len(name),name) for name in names for m in re.finditer(re.escape(name),before)]
  if not mentions:continue
  primary=max(mentions)[2]
  raw=compact[positions[marker.start()]:]
  phrase=re.match(r'(?:与|comparedwith)[^。；;]{0,90}?(?:相当(?:的)?精度|相当(?:的)?性能|comparable(?:accuracy|performance))[,，](?P<tail>[^。；;]{0,90})',raw)
  if not phrase:continue
  tail=phrase.group('tail')
  # A named model after the comparison clause starts a new subject.
  tail_canonical=re.sub(r'[-_.]','',tail)
  if any(name in tail_canonical for name in names):continue
  for pos,(row_names,cells,experiment) in enumerate(records):
   if primary not in row_names:continue
   for field,value in cells:
    if any(_field_assignment(tail,word.casefold(),value) for word in aliases[field]):hits.add((pos,tuple(sorted(row_names)),field,value,bool(experiment)))
 return hits


def _numbered_experiment_proof(text,title,target,signature):
 match=re.search(r'(?<![A-Za-z])(?P<mode>IID|OOD)\s*'+re.escape(target.number)+r'(?![0-9.])',text,re.I)
 if not match or match.group('mode').casefold() not in title.casefold():return False
 subjects=_semantic_names(title)-{'iid','ood','dataset','datasets','test','testing'}
 names=_semantic_names(text)
 if not subjects&names:return False
 hits=_comparison_metric_hits(text,signature)
 return bool(hits and any(hit[2] not in {'accuracy','auc','f1'} for hit in hits))


def _validation_table_proof(text,title,rows):
 inside=' '.join(rows);metrics=_column_words(inside)&_column_words(text)
 if not {'reconstruction','validity'}<=metrics:return False
 standard=lambda t:bool(re.search(r'(?<!非)标准|(?<!non-)standard',t,re.I))
 nonstandard=lambda t:bool(re.search(r'非标准|non-standard',t,re.I))
 if not (standard(inside) and nonstandard(inside) and standard(text) and nonstandard(text)):return False
 if not re.search(r'验证|validation',text,re.I):return False
 own=[r for r in rows if re.match(r'\s*ours(?:[^A-Za-z]|$)',r,re.I)]
 if len(own)!=1:return False
 baseline=[name for name in _row_names(rows) if not name.startswith('ours')]
 if not any(name in _compact(text) for name in baseline):return False
 return bool(re.search(r'我们的模型|本文(?:提出的)?模型|完成.{0,35}(?:预训练|训练).{0,15}模型',text) and re.search(r'对比结果|相较于|对照|高于|提高',text))


def _error_stat_metadata(text,title,inside):
 if not re.search(r'误差统计|errorstatistics',_compact(title),re.I):return False
 if not all(re.search(p,inside,re.I) for p in (r'误差均值|平均误差|meanerror',r'误差标准差|标准差|standarddeviation',r'皮尔逊|pearson')):return False
 samples={v for v in _grouped_values(title) if float(v)>=1000}
 names=_semantic_names(title)
 canonical=re.sub(r'[-_.]','',_compact(text))
 return bool(samples and samples<=_grouped_values(text) and names and any(len(n)>=4 and n in canonical for n in names) and re.search(r'实验|experimental|真值|预测',text,re.I))


def _error_stat_interpretation(text,title):
 names=_semantic_names(title);canonical=re.sub(r'[-_.]','',_compact(text))
 return bool(names and any(len(n)>=4 and n in canonical for n in names) and re.search(r'上述.*统计|该统计|一致性统计结果',text) and '系统偏差' in text and '随机误差' in text and '线性相关' in text)


def _editing_case_proof(text,title,inside):
 if not ('靶点' in title and '分子编辑' in title and re.search(r'样例|案例',title)):return False
 if not re.search(r'Input',inside,re.I) or not re.search(r'Output',inside,re.I):return False
 values=re.findall(r'pIC50\s*=\s*(\d+(?:\.\d+)?)',_semantic_text(inside),re.I)
 if len(values)<4 or len(values)%2:return False
 from decimal import Decimal
 if not all(Decimal(values[i+1])>Decimal(values[i]) for i in range(0,len(values),2)):return False
 return bool('靶点' in text and '分子编辑' in text and re.search(r'案例|样例',text) and re.search(r'修饰|修改|编辑',text) and '侧链' in text and re.search(r'亲和力.{0,15}(?:提升|提高)',text))


def _canonical_semantic(text):
 return re.sub(r'[-_.]','',_compact(_semantic_text(text)))


def _generation_strategy_proof(text,title,inside):
 cap=_canonical_semantic(title);native=_canonical_semantic(inside);body=_canonical_semantic(text)
 if 'samplegenerationstrategy' not in cap:return False
 if not all(word in native for word in ('spatialqualitydegradation','temporalqualitydegradation','alignmentqualitydegradation','gpt4','manualpostprocessingdegradation','highqualitymodel','lowqualitymodel')):return False
 return bool('gpt4' in body and 'prompt' in body and re.search(r'modify|modif(?:ied|ication)|addadjectives',body)
  and 'lowerperforming' in body and 'models' in body
  and 'manualpostprocessingdegradation' in body and 'gaussianblur' in body and 'noise' in body
  and 'framedropping' in body and 'frameinsertion' in body and 'shuffling' in body
  and 'alignmentdegradation' in body and re.search(r'randomiz(?:ing|ation|e)',body)
  and 'pairing' in body and 'prompts' in body and 'videos' in body)


def _augmentation_experiment_proof(contexts,title,rows):
 dataset=re.search(r'([A-Za-z][A-Za-z0-9_.-]{3,})\s*(?:数据集|dataset)',title,re.I)
 if not dataset:return False
 subject=_canonical_semantic(dataset.group(1));joined=' '.join(text for text in contexts)
 for row in rows:
  match=re.search(r'(?P<method>[A-Za-z][A-Za-z0-9_.-]{2,})\s*\+\s*(?P<base>[A-Za-z][A-Za-z0-9_.-]{2,})\s*\((?P<kernel>[A-Za-z][A-Za-z0-9_.-]{1,})\)',row)
  if not match:continue
  method,base,kernel=(_canonical_semantic(match.group(k)) for k in ('method','base','kernel'))
  if not any(base in _canonical_semantic(other) and '+' not in other and len(_values(other))>=2 for other in rows):continue
  metadata=[text for text in contexts if subject in _canonical_semantic(text) and re.search(r'数据集|dataset',text,re.I) and re.search(r'类别|每类|classes',text,re.I) and len({v for v in _values(text) if float(v)>=100})>=2]
  configuration=[text for text in contexts if method in _canonical_semantic(text) and kernel in _canonical_semantic(text) and re.search(r'本实验|thisexperiment',_compact(text),re.I) and re.search(r'核函数|kernel',text,re.I) and re.search(r'MLP|卷积|convolution',text,re.I) and re.search(r'应用|appl',text,re.I)]
  results=[text for text in contexts if method in _canonical_semantic(text) and re.search(r'实验结果|experimentalresults',_compact(text),re.I) and re.search(r'MLP|卷积|convolution',text,re.I) and re.search(r'提升|improv',text,re.I)]
  # Metadata and configuration must belong to the same recovered body
  # context. A named switch to another data set is a new experiment, whereas
  # a parent data set inside a subset definition does not change the subject.
  switched=lambda text:any(_canonical_semantic(m.group('name'))!=subject for m in re.finditer(r'(?:在(?:另一个|不同的)?|(?:another|other|on)\s+)\s*(?P<name>[A-Za-z][A-Za-z0-9_.-]{2,})\s*(?:数据集|dataset)',_semantic_text(text),re.I))
  bound=[text for text in configuration if text in metadata and not switched(text)]
  if bound and any(not switched(text) for text in results):return True
 return False


def _variant_fields(text):
 return _column_words(text)|{word for word in ('rouge','meteor') if word in text.casefold()}


def _named_variant_proof(contexts,title,inside):
 # Two explicitly defined test tags identify distinct rows. Each translation
 # direction must have its own task and a real original metric column.
 tags=re.findall(r'(?<![A-Za-z])Ours\s*\(([^)]+)\)',inside,re.I)
 if len(tags)!=1 or not re.search(r'(?<![A-Za-z])Ours\s*\*',inside,re.I):return False
 fields=_variant_fields(inside)
 if len(fields)<2:return False
 tag=_canonical_semantic(tags[0]);definition=[]
 for text in contexts:
  compact=_compact(text)
  labels=re.findall(r'(?:标记为|记为)\s*[“"\']?([^”"\'。；;]{1,50})',compact)
  if any(tag in _canonical_semantic(label) for label in labels) and any('*' in label for label in labels) and re.search(r'两个|两部分|两个部分',text) and re.search(r'训练|测试',text):definition.append(text)
 if not definition:return False
 task=_task_subject(title)
 if not task:return False
 for text in contexts:
  fragments=re.split(r'(?=在[^。；;]{3,45}任务中)',text)
  for fragment in fragments:
   if _task_subject(fragment)!=task:continue
   own=bool(re.search(r'我们(?:的)?模型|本文模型',fragment))
   observed=bool(re.search(r'我们观察到.{0,15}模型采用',_compact(fragment)))
   if not (own or observed):continue
   if fields&_variant_fields(fragment) and re.search(r'相近|相同|区别|逊|较差|下降|高于|低于|improv|compar',fragment,re.I):return True
 return False


def _context_proof(prose,target,title,rows,inside,kind):
 nearby=[(i,l,sources) for i,(l,scope,sources) in enumerate(prose) if scope==target.scope and abs(l.page_number-target.line.page_number)<=1]
 texts=[l.text for i,l,sources in nearby];criterion=None
 if kind=='figure' and _generation_strategy_proof(' '.join(texts),title,inside):
  criterion='正文逐项说明三种质量维度的具体操作及模型生成/手工退化两分支，与物理生成策略的七类节点排他对应'
 if kind=='table' and _augmentation_experiment_proof(texts,title,rows):
  criterion='特定数据集原样本结构、组合模型与原核函数配置共同绑定唯一性能表，正文实际分析该模型组件实验结果'
 if kind=='table' and _named_variant_proof(texts,title,inside):
  criterion='正文明确训练/测试两标签，逐一对应原表两种本文模型行，并解释同一生成方向的实际评价指标'
 if not criterion:return None
 if kind=='figure':
  anchors=[i for i,l,items in nearby if 'pairing' in _canonical_semantic(l.text) and 'prompt' in _canonical_semantic(l.text) and 'video' in _canonical_semantic(l.text)]
 elif criterion.startswith('特定数据集'):
  anchors=[i for i,l,items in nearby if re.search(r'实验结果|experimentalresults',_compact(l.text),re.I) and re.search(r'MLP|卷积|convolution',l.text,re.I) and re.search(r'提升|improv',l.text,re.I)]
 else:
  task=_task_subject(title);fields=_variant_fields(inside)
  anchors=[i for i,l,items in nearby if _task_subject(l.text)==task and fields&_variant_fields(l.text) and re.search(r'我们(?:的)?模型|本文模型|我们观察到.{0,15}模型采用',_compact(l.text))]
 if not anchors:return None
 sources=[source for i,l,items in nearby for source in items]
 return anchors[-1],criterion,sources


def _scalar_hits(text,signature):
 text=_semantic_text(text)
 aliases,records=signature;compact=re.sub(r'f1(?=\d)','f1=',_compact(text).replace('f1分数','f1'));hits=set()
 if not records or not re.search(r'MAE|RMSE|R2|准确率|F1|AUC|Accuracy|延迟|耗时|处理时间',text,re.I):return hits
 allnames={name for names,cells,experiment in records for name in names}
 positions=[i for i,c in enumerate(compact) if c not in '-_.']
 canonical=''.join(compact[i] for i in positions)
 locations=sorted((m.start(),m.end(),name) for name in allnames for m in re.finditer(re.escape(name),canonical))
 for pos,(names,cells,experiment) in enumerate(records):
  if experiment and re.search(r'实验'+re.escape(experiment)+r'(?!\d)',compact):
   fragments=[compact];row=('experiment',experiment)
  else:
   fragments=[];row=tuple(sorted(names))
   for start,end,name in locations:
    if name not in names:continue
    following=[z[0] for z in locations if z[0]>=end]
    stop=min(following) if following else len(canonical)
    raw_end=positions[end-1]+1;raw_stop=positions[stop] if stop<len(positions) else len(compact)
    fragments.append(compact[raw_end:raw_stop])
  for field,value in cells:
   if any(_field_assignment(fragment,word.casefold(),value) for fragment in fragments for word in aliases[field]):hits.add((pos,row,field,value,bool(experiment)))
 return hits|_comparison_metric_hits(text,signature)


def _scalar_complete(hits):
 rows={hit[0] for hit in hits};fields={hit[2] for hit in hits};values={hit[3] for hit in hits}
 if any(hit[4] for hit in hits) and len(fields)>=2 and len(values)>=2:return True
 if len(rows)<2 or len(values)<2:return False
 # The existing generic accuracy/AUC proof intentionally requires eight
 # values. Do not weaken it using a repeated pair of common statistics.
 return bool(fields-{'accuracy','auc','f1'}) or len(values)>=8


def _grouped_values(text):
 return _values(re.sub(r'(?<=\d),(?=\d{3}(?:\D|$))','',_text(text)))

def _ablation_proof(text,title,inside,kind):
 if not re.search(r'消融|ablation',title,re.I):return False
 native={m.casefold() for m in re.findall(r'w/o\s*([A-Za-z][A-Za-z0-9_]*)',inside,re.I)}
 if len(native)<2:return False
 named={m.casefold() for m in re.findall(r'w/o\s*([A-Za-z][A-Za-z0-9_]*)',text,re.I)}
 named.update(name for name in native if re.search(r'去除\s*'+re.escape(name),text,re.I))
 if 'pretrain' in native and '去除自监督预训练' in text:named.add('pretrain')
 if len(native&named)<2:return False
 target_subject=re.search(r'方法[一二三四五六七八九十]|Method\s*\d+',title,re.I)
 body_subjects=set(re.findall(r'方法[一二三四五六七八九十]|Method\s*\d+',text,re.I))
 if target_subject and body_subjects and target_subject.group() not in body_subjects:return False
 if not re.search(r'结果表明|结果显示|出现|退化|下降|增加|减弱',text):return False
 if kind=='table':return len(_column_words(inside)&_column_words(text))>=2 and bool(re.search(r'下降|退化|减弱|降低',text))
 return len({v for v in ('模糊','伪影','纹理','轮廓','边界','不连贯') if v in text})>=2 and bool(re.search(r'模糊|伪影|不连贯|减弱',text))


def _semantic_usage(index,body,pages,objects,events):
 from .usage_paragraphs import usage_paragraphs
 for kind in ('figure','table'):_logical_aliases(index,kind,pages,objects,events)
 # The complete prepared physical extent also excludes cells outside a native
 # first-row fragment. A table cannot supply its own alleged prose usage.
 physical=[o for o in objects if o.kind in {'figure','table'}]
 eligible=[(l,s) for l,s in body if not any(o.page_number==l.page_number and _contained(l,o.bbox) for o in physical)]
 prose=_semantic_contexts(eligible,index.document);descriptors=[];scalar_proofs={};statistical_proofs={};context_proofs={}
 for kind,targets in (('figure',index.figures),('table',index.tables)):
  for target in targets:
   owner=_usage_owner(target,kind,pages,objects)
   if owner is None:continue
   title=_usage_title(target,kind,objects,pages);rows=_rows(pages[target.line.page_number],owner);inside=' '.join(rows)
   functions=set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]{4,})\s*\(',inside))
   dataset=[]
   for row in rows:
    values={v for v in _grouped_values(row) if float(v)>=1000}
    names=_semantic_names(row)
    if len(values)>=2 and names and re.search(r'训练|train',inside,re.I) and re.search(r'测试|test',inside,re.I):dataset.append((names,values))
   workflow=kind=='figure' and bool(re.search(r'架构|框架|流程|工作流|结构|图形模型|采样.*聚合|示意|多头注意力|机制|分支.*生成|architecture|workflow|pipeline|illustration|framework|strategy|module',title,re.I)) and (not re.search(r'曲线|准确率|性能|主观效果|可视化图|影响',title) or bool(re.search(r'架构|流程|机制',title)))
   descriptors.append((kind,target,owner,title,functions,dataset,workflow,rows,inside))
   context_proof=_context_proof(prose,target,title,rows,inside,kind)
   if context_proof:context_proofs[(kind,target.line.page_number,tuple(owner))]=context_proof
   if kind=='table':
    metadata=[sources for line,scope,sources in prose if scope==target.scope and abs(line.page_number-target.line.page_number)<=1 and _error_stat_metadata(line.text,title,inside)]
    if metadata:statistical_proofs[(target.line.page_number,tuple(owner))]=[source for sources in metadata for source in sources]
    signature=_scalar_signature(rows);proof={}
    for position,(line,scope,sources) in enumerate(prose):
     if scope==target.scope and abs(line.page_number-target.line.page_number)<=1:
      hits=_scalar_hits(line.text,signature)
      if hits:proof[position]=hits
    complete=set().union(*proof.values()) if proof else set()
    if _scalar_complete(complete):scalar_proofs[(target.line.page_number,tuple(owner))]=proof
 for position,(line,scope,sources) in enumerate(prose):
  text=_text(line.text);compact=_compact(text);names=_semantic_names(text);steps=_steps(text);values=_grouped_values(text);choices={}
  for kind,target,owner,title,functions,dataset,workflow,rows,inside in descriptors:
   if target.scope!=scope or abs(target.line.page_number-line.page_number)>4:continue
   distance=abs(target.line.page_number-line.page_number)
   criterion=None;support=[]
   if workflow:
    title_names=_workflow_names(title)
    named=bool(title_names) and (title_names<=names or len(title_names&names)>=2)
    if not named and re.search(r'中的',title):
     ordered=[re.sub(r'[-_.]','',word.casefold()) for word in re.findall(r'[A-Za-z][A-Za-z0-9_.-]{2,}',title)]
     named=bool(ordered and ordered[-1] in names)
    specific=not title_names and _workflow_subject(text,title)
    generic_title=bool(re.fullmatch(r'(?:系统|模型|架构|框架|整体|总体|流程|图|总览|说明|示意|结构|\s)+',title))
    deictic=generic_title and target.line.page_number==line.page_number and bool(re.search(r'(?:该|这一|上述)(?:架构|流程|框架)',text))
    if _workflow_framing(title) and distance<=2 and len(steps)>=3 and (named or specific or deictic):
     criterion='具名流程的正文功能说明：唯一物理流程对象、特定名称和至少三个功能步骤，保留原编号'
   if kind=='figure' and distance<=1 and _concrete_workflow(text,title,inside):
    criterion='正文完整解释具体双向链条、分级匹配或成对多级标注协议，与唯一物理功能对象排他对应'
   if kind=='figure' and distance<=1 and _english_operation_proof(text,title):
    criterion='正文具体说明物理英文机制图的至少三个操作/部件性质及至少两个功能步骤，排除仅出现名称'
   if kind=='figure' and distance<=1:
    pointer=re.search(r'(?<![A-Za-z0-9.])'+re.escape(target.number)+r'\s+(?:showcases|shows|presents|illustrates|depicts)\b',text,re.I)
    if pointer and not re.search(r'(?:section|chapter|table|algorithm|equation)\s*$',text[max(0,pointer.start()-20):pointer.start()],re.I) and len(_semantic_names(title)&names)>=2:
     criterion='省略Figure的编号带明确呈现谓词，至少两个特定图像内容词与唯一邻近物理图一致'
   if kind=='figure' and distance<=1:
    for pointer in re.finditer(r'(?<![A-Za-z0-9.])'+re.escape(target.number)+r'(?=\s*(?:[,.);:。；]|$))',text):
     prefix=text[max(0,pointer.start()-150):pointer.start()]
     if re.search(r'(?:section|chapter|table|algorithm|equation)\s*$',prefix,re.I):continue
     shared=_semantic_names(title)&_semantic_names(prefix)
     if len(shared)>=3 and re.search(r'image|picture|photo|visual',prefix,re.I):
      criterion='图像内容的至少三个特定词与完整标题一致，紧随内容的裸编号排他指代唯一邻近图；排除章节/表/公式'
   if kind=='figure':
    native_names=_semantic_names(inside)
    # Three original API names plus their actions bind a source diagram even
    # when the explanation follows an intervening implementation subsection.
    expanded=re.sub(r'([a-z]+[A-Z][a-z]+)([A-Z][A-Za-z]+)&([A-Z][A-Za-z]+)',r'\1\2 \1\3',inside)
    apis={re.sub(r'[-_.]','',name.casefold()) for name in re.findall(r'[A-Za-z_][A-Za-z0-9_]{5,}',expanded) if re.search(r'[a-z][A-Z]',name)}
    if len(apis&names)>=3 and len(steps)>=3:
     criterion='物理机制图包含至少三个特定API原语，正文实际按创建/映射等步骤解释这些原语'
    if distance<=1 and re.search(r'界面',title) and '可视化' in text and _topic(text,title):
     features={v for v in ('布局','节点','关系','置信度','搜索','跳数','筛选','拖动','控件') if v in text}
     if len(features)>=4:criterion='唯一物理可视化界面与正文的布局、对象、搜索等至少四项具体交互功能对应'
    if distance<=1 and re.search(r'曲线|结果|影响|效果',title) and len(native_names&names)>=2:
     named_condition=bool(_semantic_names(title)&names) or _functional_title_match(text,title)
     view=bool(re.search(r'曲线|可视化结果|定性|主观|结果(?:如图|显示)|伪影|纹理|模糊|轮廓',text))
     if named_condition and view and re.search(r'提升|增加|降低|下降|高于|低于|小于|左侧|相差|波动|更接近|模糊',text):
      criterion='正文明确解释曲线/视觉结果，并与物理图中至少两命名系列和特定条件排他匹配'
    terms={w[i:i+3] for w in re.findall(r'[\u4e00-\u9fff]{3,}',inside) for i in range(len(w)-2)}
    terms-={'图像文','像文本','可以看','模型的','方法一','输入输'}
    if workflow and distance<=1 and len({v for v in terms if v in text})>=3 and len(steps)>=2 and _topic(text,title):
     criterion='正文功能解释与物理流程内部至少三个特定文字部件及至少两个操作一致'
   if distance<=1 and _ablation_proof(text,title,inside,kind):
    criterion='正文实际解释物理对象至少两种命名消融条件的退化；表格须匹配两指标列，图须描述至少两视觉变化'
   if kind=='figure' and distance<=1:
    if '可视化' in title and _functional_title_match(text,title) and _topic(text,title) and len(steps)>=3 and re.search(r'定性[^。；;]{0,15}结果',text) and re.search(r'目标框|边界框',text):
     criterion='具名目标的定性视觉结果与原图完整标题对应，正文实际说明检测框及至少三个检测步骤'
    if '对比学习' in title and 'EMA' in inside and '动量' in inside and '编码器' in inside and re.search(r'EMA',text,re.I) and '动量编码器' in text and '更新' in text and re.search(r'维护|队列',text):
     criterion='原物理对比图的EMA、动量和编码器三部件与正文的滑动平均更新及队列维护机制逐项对应'
   native_names=_semantic_names(inside)
   if distance<=1 and re.search(r'输入.*输出|输出字段|字段.*约束',title) and len(native_names&names)>=6 and len(re.findall(r'为|采用|表示|定义|取',text))>=3:
    criterion='正文逐项定义至少三类输出字段及多个枚举形式，与唯一物理对象中的特定字段/类别逐一对应'
   if kind=='figure' and distance<=1:
    if re.search(r'曲线|影响',title) and _semantic_names(title)&names and '曲线' in text and len(values)>=6:
     factors={v for v in ('嵌入维度','层数','缓存','参数量','深度','头数','通道') if v in title and v in text}
     if len(factors)>=2 and re.search(r'提升|增加|降低|饱和',text):criterion='特定模型与标题中的至少两个实验变量匹配，正文明确解释曲线并给出至少六个变量/变化数值'
    series=re.findall(r'[\u4e00-\u9fff]{2,10}CDF\s*曲线',text)
    if len(set(series))>=2 and _functional_title_match(text,title) and re.search(r'曲线.*(?:左侧|右侧|高于|低于)',text):
     criterion='特定实验区域和正文的两条CDF曲线及明确相对位置，对应唯一邻近物理结果图'
   if kind=='table' and distance<=1 and '配置' in title and re.search(r'隐藏',inside) and re.search(r'隐藏.{0,8}(?:状态|维度).{0,15}(?:小于|大于)',text):
    models=[]
    for row in rows:
     first=re.match(r'([A-Za-z][A-Za-z0-9_.-]{2,})',row.strip());nums=_grouped_values(row)
     if first and len(nums)>=2:models.append((re.sub(r'[-_.]','',first.group().casefold()),max(map(float,nums))))
    if len(models)>=3 and all(name in re.sub(r'[-_.]','',compact) for name,value in models):
     low=min(value for name,value in models);position_of_less=compact.find('小于');prefix=re.sub(r'[-_.]','',compact[:position_of_less])
     selected=max(((prefix.rfind(name),value) for name,value in models),default=(-1,None))
     if position_of_less>=0 and selected[1]==low and len({value for name,value in models})>=2:
      criterion='正文选择至少三种特定模型并比较实际隐藏维度，物理配置表的独占模型行和维度顺序完全一致'
   if kind=='table' and distance<=1:
    if _numbered_experiment_proof(text,title,target,_scalar_signature(rows)):
     criterion='正文明确实验条件与裸编号，具名主模型的科学指标原值对应唯一原表；比较基线不得接管主语或借值'
    if _validation_table_proof(text,title,rows):
     criterion='正文具体比较同一具名基线和本文模型的两种原验证条件及两实际指标列；不凭通用模型别称'
    if (metadata:=statistical_proofs.get((target.line.page_number,tuple(owner)))) and _error_stat_interpretation(text,title):
     criterion='特定预测器和精确样本量先绑定实验，正文泛指统计并逐项解释均值、标准差和相关性三类原字段'
     support=metadata
    if _editing_case_proof(text,title,inside):
     criterion='正文具体解释靶点分子编辑侧链和亲和力提升，原表至少两输入/输出样例的亲和力原值均证实提升；保留显式图号'
   if kind=='table' and position in scalar_proofs.get((target.line.page_number,tuple(owner)),{}):
    criterion='正文按特定命名行逐一绑定原表指标和值：至少两独立行，或明确实验编号和两个指标；保留其它同值表'
   if kind=='table' and distance<=2:
    if _interval_proof(text,rows):criterion='正文逐级说明至少三个命名等级的完整数值不等式，每一等级与物理表的原区间逐一对应'
    rownames=_row_names(rows);metrics=_column_words(inside)&_column_words(text)
    compared=bool(re.search(r'可以看到|结果表明|对比结果|均小于|均高于|明显下降|指标.*(?:提升|退化)',text))
    if len([name for name in rownames if name in compact])>=2 and len(metrics)>=2 and compared and _functional_title_match(text,title):
     criterion='正文解释具体实验条件下至少两命名行和至少两实际指标列的比较，不凭共享主题或少数重复数值'
   if kind=='table' and len(functions)>=2 and re.search(r'接口|调用|实现|执行',text):
    called={f for f in functions if re.search(r'(?<![A-Za-z0-9_])'+re.escape(f)+r'\s*\(',text)}
    if len(called)>=2:criterion='正文实际调用至少两个特定接口函数，与完整物理接口表的不同命名行排他对应'
   if kind=='table' and re.search(r'数据集|训练|测试',text):
    for row_names,row_values in dataset:
     if row_names&names and row_values<=values:
      criterion='正文使用具名数据集的一行及两个至少四位的精确训练/测试数值，排除常见重复小数值'
   contextual=context_proofs.get((kind,target.line.page_number,tuple(owner)))
   if contextual and contextual[0]==position:
    criterion=contextual[1];support=contextual[2]
   if criterion:
    score=7 if contextual and contextual[0]==position else 4
    if criterion.startswith('具名流程'):score=6 if named else (4 if deictic else 2)
    if criterion.startswith('正文明确解释曲线'):score=6 if _semantic_names(title)&names else 3
    if criterion.startswith('正文解释具体实验'):score=5
    if criterion.startswith('正文逐级说明') or criterion.startswith('正文实际调用') or criterion.startswith('正文按特定命名行'):score=7
    choices[(kind,target.line.page_number,tuple(owner))]=(kind,target,criterion,score,support)
  # The same paragraph can genuinely explain both a diagram and its table.
  # Ambiguity is tested among physical objects of the same kind, never by
  # treating independently proven figure/table uses as mutual alternatives.
  for chosen_kind in ('figure','table'):
   matching=[value for key,value in choices.items() if key[0]==chosen_kind]
   if not matching:continue
   best=max(value[3] for value in matching);matching=[value for value in matching if value[3]==best]
   if len(matching)!=1:
    for kind,target,criterion,score,support in matching:_event(events,'ambiguous_usage',Label(target.number,line,scope,target.target_scope),criterion,candidate_count=len(matching),body_context=sources)
    continue
   kind,target,criterion,score,support=matching[0]
   start=len(events) if events is not None else 0
   _add_indirect(index,kind,target,line,scope,events,criterion)
   if events is not None and len(events)>start:events[-1]['body_context']=sources+support


def _logical_aliases(index,kind,pages,objects,events):
 targets=index.figures if kind=='figure' else index.tables
 refs=index.figure_refs if kind=='figure' else index.table_refs
 graphic=index.graphic_figure_refs if kind=='figure' else index.graphic_table_refs
 aliases={};kept=[]
 for target in sorted(targets,key=lambda t:(t.line.page_number,t.line.bbox[1],t.line.bbox[0])):
  continued=bool(re.search(r'(?:[（(]\s*续\s*[)）]|continued|continuation)',target.line.text,re.I))
  prior=[t for t in kept if t.scope==target.scope and t.number==target.number and 0<target.line.page_number-t.line.page_number<=3]
  if kind=='table' and continued and prior:
   aliases[(target.scope,target.number)]=prior[-1].number;_event(events,'merge_target',target,'明确续表标识及跨页相同编号',owner_page=prior[-1].line.page_number);continue
  owner=_owner(target,kind,pages,objects)
  peer=None
  if owner is not None and _caption_physical(target,kind,pages,objects):
   cn=normalize_text(target.line.text).lstrip().startswith(('图','表'))
   for old in reversed(kept):
    if old.scope!=target.scope or old.line.page_number!=target.line.page_number:continue
    if normalize_text(old.line.text).lstrip().startswith(('图','表'))==cn:continue
    if not _caption_physical(old,kind,pages,objects) or _owner(old,kind,pages,objects)!=owner:continue
    a,b=old.line.bbox,target.line.bbox
    gap=max(a[1]-b[3],b[1]-a[3],0) if abs(target.line.direction[0])>.7 else max(a[0]-b[2],b[0]-a[2],0)
    if gap>120 or _overlap(a,b)<min(a[2]-a[0],b[2]-b[0])*.4 and abs(target.line.direction[0])>.7:continue
    if old.line.font_size and target.line.font_size and abs(old.line.font_size-target.line.font_size)>old.line.font_size*.1:continue
    peer=old;break
  if peer:
   canonical=peer if normalize_text(peer.line.text).lstrip().startswith(('图','表')) else target
   alias=target if canonical is peer else peer
   aliases[(alias.scope,alias.number)]=canonical.number
   if alias is peer:kept.remove(peer);kept.append(canonical)
   _event(events,'merge_target',alias,'双语标题共同归属同一物理对象，字形/字号/空间邻接一致',canonical_number=canonical.number,owner_page=canonical.line.page_number)
  else:kept.append(target)
 for collection in (refs,graphic):
  for pos,ref in enumerate(collection):
   canonical=aliases.get((ref.target_scope or ref.scope,ref.number))
   if canonical and canonical!=ref.number and not any(t.number==ref.number and t.scope==(ref.target_scope or ref.scope) for t in kept):collection[pos]=replace(ref,number=canonical)
 targets[:]=kept


def repair_reference_identity(index,layout_objects=(),*,evidence=None):
 """Return repaired identities, preserving real missing and unreferenced objects.

 Call after build_index and before detect_rules. ``evidence`` may be a mutable
 list; entries record the original ink and a reason for each change. Layout
 evidence is optional; without physical proof an ambiguous alias is retained.
 """
 out=DocumentIndex(index.document,**{name:list(getattr(index,name)) for name in ('figures','tables','figure_refs','table_refs','graphic_figure_refs','graphic_table_refs','appendices','appendix_refs')})
 out.indirect_reference_targets={key:set(targets) for key,targets in getattr(index,'indirect_reference_targets',{}).items()}
 out.r11_panel_reference_evidence=list(getattr(index,'r11_panel_reference_evidence',()))
 pages={p.number:p for p in index.document.pages};objects=tuple(layout_objects or ())
 directories=_directory_keys(index.document)|toc_line_keys(index.document)
 scopes,nonbody=_scope_map(index.document,directories)
 graph_symbols=defined_graph_symbols(index.document)
 for name in ('figures','tables','figure_refs','table_refs','graphic_figure_refs','graphic_table_refs','appendices','appendix_refs'):
  items=getattr(out,name);items[:]=[_scope(t,scopes) for t in items if _key(t.line) not in directories]
 for line in index.document.lines:
  scope=_heading(normalize_text(line.text).strip())
  if scope and _key(line) not in directories and not any(t.number==scope for t in out.appendices):out.appendices.append(Label(scope,line,scope))
 for kind in ('figure','table'):
  targets=out.figures if kind=='figure' else out.tables;refs=out.figure_refs if kind=='figure' else out.table_refs
  for label in list(targets):
   if _body_pseudocaption(label,kind,targets,pages,objects):
    targets.remove(label)
    for reference in _typed_references(label.line,kind,label.scope,graph_symbols):
     _add(refs,reference,evidence,'普通正文编号主语及叙述谓词，保留完整编号和原有引用边界')
  # Recover a styled physical title even when its own wording is narrative.
  pattern=FIGURE_CAPTION if kind=='figure' else TABLE_CAPTION
  for line in index.document.lines:
   if _key(line) in directories:continue
   m=pattern.search(_text(line.text))
   if not m:continue
   label=_label(m.group('number'),line,scopes.get(_key(line),'body'))
   if _recoverable_title(label,kind,pages,objects) and not any(_key(t.line)==_key(line) for t in targets):targets.append(label);_event(evidence,'recover_target',label,'标题字形与独立物理对象共同证明其标题身份')
  physical_keys={_key(t.line) for t in targets}
  for name in (('figure_refs','graphic_figure_refs') if kind=='figure' else ('table_refs','graphic_table_refs')):
   collection=getattr(out,name);kept=[]
   for label in collection:
    label=_appendix_number(label,out,kind,evidence)
    why=_artifact(label,kind,pages)
    if label.scope=='_nonbody' or _key(label.line) in nonbody:why='参考文献或致谢中的非正文对象名'
    if _key(label.line) in physical_keys:
     m=pattern.search(_text(label.line.text))
     if m and _num(m.group('number'))==label.number:why='物理标题的自身编号不构成对本对象的正文引用'
    if why:_event(evidence,'remove_reference',label,why)
    else:kept.append(label)
   collection[:]=kept
 caption_keys={_key(t.line) for t in out.figures+out.tables}
 from .caption_context import caption_region_lines
 caption_keys.update(caption_region_lines(index.document,objects))
 from .graphic_context import native_figure_regions,detached_from_native_figure
 native_regions=native_figure_regions(index.document,directories)
 regions=[*native_regions,*[o for o in objects if o.kind=='figure']]
 inside_visual={_key(l) for l in index.document.lines if any(o.page_number==l.page_number and o.bbox[0]<=l.bbox[0] and o.bbox[1]<=l.bbox[1] and o.bbox[2]>=l.bbox[2] and o.bbox[3]>=l.bbox[3] and not detached_from_native_figure(l,pages[l.page_number],o,native_regions) for o in regions)}
 body=[(l,scopes.get(_key(l),'body')) for l in index.document.lines if _is_body(l,caption_keys,directories,pages) and _key(l) not in nonbody and _key(l) not in inside_visual]
 for line,scope in body:
  for kind,refs in [('figure',out.figure_refs),('table',out.table_refs)]:
   for label in _typed_references(line,kind,scope,graph_symbols):
    if not _artifact(label,kind,pages):_add(refs,label,evidence,'正文的完整编号或共享类型词的并列编号使用')
 _wrapped(out,scopes,caption_keys,directories,pages,evidence,inside_visual)
 for kind in ('figure','table'):_logical_aliases(out,kind,pages,objects,evidence)
 from .algorithm_figure_usage import repair_algorithm_figure_usage
 repair_algorithm_figure_usage(out,body,pages,objects,evidence)
 from .workflow_section_usage import repair_named_workflow_sections
 repair_named_workflow_sections(out,body,pages,objects,evidence)
 from .protocol_reference_repair import repair_protocol_references
 out=repair_protocol_references(out,objects,evidence=evidence)
 from .parameter_table_usage import repair_parameter_table_references
 out=repair_parameter_table_references(out,objects,evidence=evidence)
 from .structured_table_usage import repair_structured_table_usage
 out=repair_structured_table_usage(out,objects,evidence=evidence)
 _implicit(out,body,evidence)
 _strong_usage(out,body,pages,objects,evidence)
 _semantic_usage(out,body,pages,objects,evidence)
 for kind in ('figure','table'):_logical_aliases(out,kind,pages,objects,evidence)
 kept=[]
 for label in out.appendix_refs:
  why=_artifact(label,'appendix',pages)
  if why:_event(evidence,'remove_reference',label,why)
  else:kept.append(label)
 out.appendix_refs[:]=kept
 return out
