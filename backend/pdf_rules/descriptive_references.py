"""Resolve usage statements without inventing missing numeric targets.

These cues only add evidence for rules 15/16. They do not assert a type for
rule 11, and unrelated nearby content alone never counts as a reference.
"""
import re
from dataclasses import replace
from difflib import SequenceMatcher
from .model import Label
from .numbering import normalize_text,normalize_label,caption_match,APPENDIX_REFERENCE
from .reference_groups import reference_matches
from .reference_context import local_reference
from .usage_paragraphs import span_anchor

ELIDED=re.compile(r'(?:图表|如|见|为)\s*(?P<number>(?:[A-Z]\.?)?[0-9]+(?:[.\-][0-9]+)*)(?![A-Za-z0-9]|[.\-]\d)',re.I)
SUBJECT_NUMBER=re.compile(r'(?:汇总于|对应|如)\s*(?P<number>(?:[A-Z]\.?)?[0-9]+(?:[.\-][0-9]+)*)(?![A-Za-z0-9]|[.\-]\d)')
TABLE_SUBJECTS=('参数','配置','指标','标准','数据','取值','测量值')
PLURAL=re.compile(r'(?P<direction>下文|下列|下面|以下|上文|上述|上列|以上)[的\s]*(?P<kind>图表|表格|各表|各图)')
LOCAL=re.compile(r'(?:这张|该张|此张|这幅|该幅|此幅|这|该|此)(?:示意图|流程图|架构图|图|表)(?=反映|表示|展示|显示|描绘|呈现|给出|说明|中|内)')
NAMED=re.compile(r'([A-Za-z0-9\u4e00-\u9fff–—-]{2,40}(?:示意图|流程图|架构图|趋势图|变化图|结果图|曲线))(?=反映|表示|展示|显示|描绘|呈现|给出|说明|中|内)')

def _compact(text):return re.sub(r'\s+','',normalize_text(text))

def _title(target,kind):
 text=normalize_text(target.line.text);match=caption_match(text,kind)
 if not match:return ''
 text=text[match.end('number'):]
 text=re.split(r'(?:Figure|Fig[.]?|Table)\s*[A-Z]?\d',text,flags=re.I)[0]
 text=_compact(text)
 text=re.sub(r'\[\d+(?:[-,]\d+)*\]','',text)
 return text.strip('：:、.。')

def _reference_subject(text):
 # These two common structure nouns are interchangeable in explicit showing
 # statements. This is used only after a numeric reference cue is present;
 # discussing an architecture by itself never establishes figure usage.
 return _compact(text).replace('框架','架构')

def _shared_phrase(a,b):
 return max((n for n in range(4,min(len(a),len(b))+1) if any(a[i:i+n] in b for i in range(len(a)-n+1))),default=0)

def add_descriptive_references(index,eligible_lines,offsets,boundaries):
 targets=[('figure',t) for t in index.figures]+[('table',t) for t in index.tables]
 from .numeric_visual_usage import add_numeric_usage
 add_numeric_usage(index,eligible_lines,targets,offsets,boundaries,_title,_shared_phrase)
 from .coordinated_references import add_composed_references
 add_composed_references(index,eligible_lines,targets,_title,_shared_phrase)
 from .declared_visual_lists import add_declared_visual_lists
 add_declared_visual_lists(index,eligible_lines,targets,_title,_shared_phrase)
 from .reported_visual_references import add_reported_references
 add_reported_references(index,eligible_lines,targets,offsets,boundaries,_title)
 def where(line):return offsets[line.page_number]+(line.bbox[1]+line.bbox[3])/2
 def add(kind,target,line):
  ref=Label(target.number,line,target.scope)
  refs=index.graphic_figure_refs if kind=='figure' else index.graphic_table_refs
  if not any(r.number==ref.number and r.scope==ref.scope and r.line==line for r in refs):refs.append(ref)
 def in_section(a,b):return not any(min(a,b)<v<max(a,b) for v in boundaries)
 for line,scope in eligible_lines:
  text=normalize_text(line.text);position=where(line)
  groups={}
  for match in reference_matches(ELIDED,text):groups.setdefault(match.start(),[]).append(match)
  for start,matches in groups.items():
   end=max(m.end() for m in matches)
   if not text[start:].startswith('图表') and not re.match(r'\s*[)）]?\s*(?:所示|所述)',text[end:]):continue
   for match in matches:
    if not local_reference(text,match):continue
    options={}
    for kind,target in targets:
     if target.scope==scope and target.number==normalize_label(match.group('number')):
      dist=abs(where(target.line)-position)
      if kind not in options or dist<options[kind][0]:options[kind]=(dist,target)
    if len(options)==1:
     kind,(_,target)=next(iter(options.items()));add(kind,target,line);continue
    if len(options)!=2:continue
    lexical={kind:_shared_phrase(_reference_subject(re.split(r'[。，,！？；;:：]',text[:start])[-1][-80:]),_reference_subject(_title(target,kind))) for kind,(_,target) in options.items()}
    winner=sorted(options,key=lambda k:(-lexical[k],options[k][0]))
    first,second=winner
    if (lexical[first]>=4 and lexical[first]>=lexical[second]+2) or (options[first][0]<=line.page_height*.65 and options[first][0]+line.page_height*.2<options[second][0]):
     add(first,options[first][1],line)
  # A bare object number needs an explicit showing/summary cue, title overlap,
  # and local document scope. Section/formula suffixes cannot resolve a visual.
  for match in SUBJECT_NUMBER.finditer(text):
   suffix=text[match.end():]
   if not re.match(r'\s*[)）]?\s*[:：。.,，]',suffix):continue
   subject=_compact(text[:match.start()]);candidates={}
   for kind,target in targets:
    if target.scope!=scope or target.number!=normalize_label(match.group('number')):continue
    if abs(target.line.page_number-line.page_number)>1:continue
    title=_title(target,kind);score=_shared_phrase(subject,title)
    summary=(text[match.start():match.end()].startswith('汇总于') and 0<=target.line.bbox[1]-line.bbox[3]<=140 and target.line.page_number==line.page_number)
    if score>=4 or summary:candidates[(kind,target.scope,target.number)]=(max(score,4 if summary else 0),target)
   ordered=sorted(candidates.items(),key=lambda pair:-pair[1][0])
   if ordered and (len(ordered)==1 or ordered[0][1][0]>=ordered[1][1][0]+2):
    (kind,_,_),(_,target)=ordered[0];add(kind,target,span_anchor(line,match.start(),match.end()))
  compact=_compact(text)
  # Exact subject/title overlap connects a 'here are' statement to its table.
  if re.search(r'(?:如下|如下所示)[:：。.]?$',compact):
   candidates={}
   for kind,target in targets:
    if kind!='table' or target.scope!=scope or target.line.page_number!=line.page_number:continue
    distance=target.line.bbox[1]-line.bbox[3]
    title=_title(target,kind)
    shared=_shared_phrase(compact,title)>=4
    shared=shared or any(noun in compact and noun in title for noun in TABLE_SUBJECTS)
    shared=shared or ('选择依据' in compact and '选择标准' in title)
    if 0<=distance<=140 and shared:candidates[(target.scope,target.number)]=target
   if len(candidates)==1:add('table',next(iter(candidates.values())),line)
  for match in LOCAL.finditer(compact):
   evidence=span_anchor(line,match.start(),match.end(),True);local_position=where(evidence)
   kind='table' if match.group(0).endswith('表') else 'figure'
   nearest={}
   for target_kind,target in targets:
    if target_kind!=kind or target.scope!=scope or target.line.page_number!=line.page_number:continue
    distance=abs(where(target.line)-local_position)
    if distance<=100 and in_section(local_position,where(target.line)):
     key=(target.scope,target.number)
     if key not in nearest or distance<nearest[key][0]:nearest[key]=(distance,target)
   ordered=sorted(nearest.values(),key=lambda pair:pair[0])
   if ordered and (len(ordered)==1 or ordered[1][0]-ordered[0][0]>=60):add(kind,ordered[0][1],evidence)
  for match in NAMED.finditer(compact):
   phrase=match.group(1);scores={}
   evidence=span_anchor(line,match.start(),match.end(),True);named_position=where(evidence)
   if re.match(r'^(?:这|该|此|上述|下述)',phrase):continue
   for kind,target in targets:
    if kind!='figure' or target.scope!=scope or abs(target.line.page_number-line.page_number)>1:continue
    if not in_section(named_position,where(target.line)):continue
    title=_title(target,kind)
    if not title:continue
    score=SequenceMatcher(None,phrase,title).ratio()
    if title in phrase:score=1
    if (score>=.68 and _shared_phrase(phrase,title)>=4) or (score>=.55 and _shared_phrase(phrase,title)>=8):
     key=(target.scope,target.number)
     if key not in scores or score>scores[key][0]:scores[key]=(score,target)
   ordered=sorted(scores.values(),key=lambda pair:-pair[0])
   if ordered and (len(ordered)==1 or ordered[0][0]-ordered[1][0]>=.15):add('figure',ordered[0][1],evidence)
  # A directed reference to an appendix's contents covers its contained visuals.
  # Heading/running-header lines are excluded by the index before reaching here.
  for match in APPENDIX_REFERENCE.finditer(text):
   before=text[max(0,match.start()-45):match.start()];after=text[match.end():match.end()+45]
   if not (re.search(r'(?:参见|详见|见|如|在|于)\s*$',before) and re.search(r'内容|模板|详|给出|展示|所示|记录|结果|中|[。.]',after)):continue
   appendix=normalize_label(match.group('number'))
   if not any(a.number==appendix for a in index.appendices):continue
   for kind,target in targets:
    if target.scope==appendix:add(kind,target,span_anchor(line,match.start(),match.end()))
  for match in PLURAL.finditer(text):
   forward=match.group('direction').startswith(('下','以')) and match.group('direction')!='以上'
   kinds={'figure','table'} if match.group('kind')=='图表' else ({'figure'} if match.group('kind')=='各图' else {'table'})
   for kind,target in targets:
    if kind not in kinds or target.scope!=scope:continue
    destination=where(target.line)
    if (destination>position)!=forward:continue
    if not in_section(position,destination):continue
    if not boundaries and target.line.page_number!=line.page_number:continue
    add(kind,target,line)
