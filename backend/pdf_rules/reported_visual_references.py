"""Resolve explicit visual reporting statements with distinct subject evidence.

A reporting predicate plus an object number can omit the word figure/table.
An explicit visualization statement can name a nearby floating figure instead.
Topic overlap or an arbitrary numeric result alone never supplies a citation.
"""
import re
from difflib import SequenceMatcher
from .model import Label
from .numbering import normalize_text,normalize_label
from .usage_paragraphs import span_anchor

NUMBER=r'(?:[A-Z]\.?)?[0-9]+(?:[.\-][0-9]+)*'
REPORT=re.compile(r'(?P<subject>[^。！？；:：]{2,80}?(?:结果|统计|分析))\s*(?P<number>'+NUMBER+r')(?![A-Za-z0-9]|[.\-]\d)(?=\s*(?:显示|表明|反映|揭示|展示))')
VISUAL=re.compile(r'(?:通过|采用|利用|借助)(?P<subject>[^。！？；]{2,100}?(?:示意图|流程图|架构图|趋势图|拓扑图|曲线|图)[^。！？；]{0,100}?(?:可视化(?:分析|展示)?|直观(?:展示|呈现)))')
GENERIC=re.compile(r'实验|结果|分析|统计')


def add_reported_references(index,eligible_lines,targets,offsets,boundaries,title_fn):
 def where(line):return offsets[line.page_number]+(line.bbox[1]+line.bbox[3])/2
 def specific(text):return GENERIC.sub('',re.sub(r'\s+','',normalize_text(text)))
 def same_section(a,b):return not any(min(a,b)<x<max(a,b) for x in boundaries)
 def add(kind,target,anchor):
  refs=index.graphic_figure_refs if kind=='figure' else index.graphic_table_refs
  value=Label(target.number,anchor,target.scope)
  if not any(r.number==value.number and r.scope==value.scope and r.line==anchor for r in refs):refs.append(value)
 def winner(options):
  ordered=sorted(options.items(),key=lambda pair:-pair[1][0])
  return ordered[0] if ordered and (len(ordered)==1 or ordered[0][1][0]>=ordered[1][1][0]+2) else None
 for line,scope in eligible_lines:
  text=re.sub(r'\s+','',normalize_text(line.text))
  for pattern,minimum in ((REPORT,2),(VISUAL,4)):
   for match in pattern.finditer(text):
    anchor=span_anchor(line,match.start(),match.end(),True)
    position=where(anchor);subject=specific(match.group('subject'));choices={}
    for kind,target in targets:
     if target.scope!=scope or abs(target.line.page_number-line.page_number)>1:continue
     if pattern is VISUAL and kind!='figure':continue
     if pattern is REPORT and target.number!=normalize_label(match.group('number')):continue
     destination=where(target.line)
     if not same_section(position,destination) or abs(destination-position)>line.page_height*.9:continue
     title=specific(title_fn(target,kind));score=SequenceMatcher(None,subject,title,autojunk=False).find_longest_match(0,len(subject),0,len(title)).size
     threshold=minimum if re.search(r'[\u4e00-\u9fff]',subject) and re.search(r'[\u4e00-\u9fff]',title) else max(4,minimum)
     if score<threshold:continue
     key=(kind,target.scope,target.number)
     if key not in choices or score>choices[key][0]:choices[key]=(score,target)
    chosen=winner(choices)
    if chosen:
     (kind,_,_),(_,target)=chosen;add(kind,target,anchor)
