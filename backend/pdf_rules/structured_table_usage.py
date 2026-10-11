"""Exclusive structured table use without rewriting literal citation identity."""
import re
from decimal import Decimal
from dataclasses import replace
from .model import DocumentIndex
from .reference_identity_repair import (_usage_owner,_usage_title,_contained,_semantic_text,
 _semantic_contexts,_scope_map,_directory_keys,_key,_is_body,_add_indirect)


def compact(text):return re.sub(r'\s+','',_semantic_text(text)).casefold()
def semantic_view(text):
 # Retain English word boundaries while removing mathematical/OCR spacing.
 # Every retained character maps to the NFKC source and to compact offsets;
 # subject spans never infer a split inside an already joined model token.
 source=_semantic_text(text);chars=[];positions=[];n=0
 while n<len(source):
  if source[n].isspace():
   end=n+1
   while end<len(source) and source[end].isspace():end+=1
   if n and end<len(source) and re.match(r'[A-Za-z]',source[n-1]) and re.match(r'[A-Za-z]',source[end]):chars.append(' ');positions.append(n)
   n=end;continue
  folded=source[n].casefold();chars.extend(folded);positions.extend([n]*len(folded));n+=1
 phrase=''.join(chars);compact_offsets=[0]
 for char in phrase:compact_offsets.append(compact_offsets[-1]+(not char.isspace()))
 return dict(source_text=source,phrase=phrase,phrase_to_source=positions,phrase_to_compact=compact_offsets)


def subject_scope_trace(text,records):
 view=semantic_view(text);marks=occurrences(view['phrase'],records);out=[]
 for start,end,name in marks:
  out.append(dict(identity=name,phrase_span=[start,end],source_span=[view['phrase_to_source'][start],view['phrase_to_source'][end-1]+1],compact_span=[view['phrase_to_compact'][start],view['phrase_to_compact'][end]]))
 return dict(source_text=view['source_text'],phrase=view['phrase'],subjects=out)


NUM=r'-?\d+(?:\.\d+)?'
NUMBER=re.compile(r'^\s*('+NUM+r')(%?)\s*$')
FIELDS={
 'vina_score':r'Vina\s*Score', 'vina_min':r'Vina\s*Min', 'vina_dock':r'Vina\s*Dock',
 'qed':r'(?<![a-z])QED(?![a-z])','sa':r'(?<![a-z])SA(?![a-z])',
 'diversity':r'Diversity|(?:分子)?多样性', 'connected':r'Connected|化学结构完整率|结构完整率',
 'affinity':r'High\s*Affinity|高亲和力',
 'mae':r'(?<![a-z])MAE(?![a-z])','rmse':r'(?<![a-z])RMSE(?![a-z])','psnr':r'(?<![a-z])PSNR(?![a-z])',
}


def cells(page,box):
 result=[]
 for l in sorted((l for l in page.lines if _contained(l,box)),key=lambda l:(l.bbox[1],l.bbox[0])):
  y=(l.bbox[1]+l.bbox[3])/2
  row=next((r for r in reversed(result) if abs(r[0]-y)<=max(2,(l.bbox[3]-l.bbox[1])*.3)),None)
  if row is None:result.append([y,[l]])
  else:row[1].append(l)
 return [sorted(r,key=lambda l:l.bbox[0]) for y,r in result]


def owner(target,pages,objects):
 b=_usage_owner(target,'table',pages,objects)
 if b is None:return None
 observed=list(pages[target.line.page_number].tables)+[o.bbox for o in objects if o.kind=='table' and o.page_number==target.line.page_number]
 return b if any(all(abs(a-z)<=2 for a,z in zip(b,q)) for q in observed) else None


def numeric(value):
 m=NUMBER.fullmatch(_semantic_text(value))
 return (Decimal(m.group(1)),bool(m.group(2))) if m else None


def method_name(text):
 t=compact(text);t=re.sub(r'\[[0-9,，\-]+\]|等','',t)
 t=re.sub(r'^[0-9\u20dd]+','',t);return t.strip(' :：')


def metric_profile(rows):
 # Metric headers own their actual columns, including Avg./Med. subdivisions.
 headers=[]
 for row in rows:
  if sum(numeric(l.text) is not None for l in row)>=2:break
  for l in row:
   found=[f for f,rx in FIELDS.items() if re.search(rx,_semantic_text(l.text),re.I)]
   if len(found)==1:headers.append((found[0],l))
 if len({f for f,l in headers})<3:return None
 headers.sort(key=lambda x:x[1].bbox[0]);records=[];previous=None
 for row in rows:
  vals=[l for l in row if numeric(l.text) is not None]
  if len(vals)<3:continue
  first=headers[0][1].bbox[0]
  labels=[l.text for l in row if l.bbox[0]<first-3 and compact(l.text) not in {'gen.','opt.','ours'} and not NUMBER.fullmatch(l.text)]
  name=method_name(''.join(labels))
  if not name:continue
  if name.startswith('+'):
   if previous is None:continue
   name=previous+'('+name+')'
  else:previous=name
  data={}
  for n,(field,head) in enumerate(headers):
   right=headers[n+1][1].bbox[0] if n+1<len(headers) else max(l.bbox[2] for l in row)+5
   col=[l for l in vals if head.bbox[0]-3<=(l.bbox[0]+l.bbox[2])/2<right-1]
   if not col:continue
   # Multiple numeric cells require visible Avg/Med subheader ownership. A
   # bare metric in prose means Avg only when that label is explicitly printed.
   if len(col)>1:
    subs=[l for r in rows for l in r if head.bbox[0]-3<=l.bbox[0]<right and head.bbox[3]-1<=l.bbox[1]<row[0].bbox[1] and compact(l.text).strip('.') in {'avg','med','mean','median'}]
    avg=[l for l in subs if compact(l.text).strip('.') in {'avg','mean'}]
    if not avg:continue
    h=avg[0];l=min(col,key=lambda l:abs((l.bbox[0]+l.bbox[2])/2-(h.bbox[0]+h.bbox[2])/2))
   else:l=col[0]
   data[field]=numeric(l.text)
  if len(data)>=3:records.append(dict(name=name,cells=data))
 if len({r['name'] for r in records})!=len(records):return None
 return records if len(records)>=2 else None


def occurrences(text,records):
 # A complete reporting subject owns its values. In particular an unknown
 # multiword method cannot lend a known suffix row that method's metrics.
 matches=[]
 for record in records:
  for m in re.finditer(r'(?<![a-z0-9_])'+re.escape(record['name'])+r'(?![a-z0-9_])',text):matches.append((m.start(),m.end(),record['name']))
 for m in re.finditer(r'实验\d+',text):matches.append((m.start(),m.end(),m.group()))
 verbs=r'reports?\b|achieves?\b|has\b|obtains?\b|attains?\b|scores?\b|uses?\b|employs?\b'
 metrics=r'qed\b|sa\b|diversity\b|vina\b|mae\b|rmse\b|psnr\b'
 word=r'(?!(?:'+verbs+'|'+metrics+r'))[a-z][a-z0-9_+\-]*(?:\([^()]*\))?'
 phrase=r'(?<![a-z0-9_])(?P<name>'+word+r'(?:\s+'+word+r')*)'
 predicate=r'\s*(?:(?:所提出的|所采用的|的)(?:模型|方法|实验|测试|测量|评估)(?:结果|指标)?)?\s*(?:(?:的)?(?:(?:模型|方法|实验|测试|测量|评估)(?:结果|指标)?)?(?:qed|sa|diversity|vina|mae|rmse|psnr|多样性)|(?:报告|获得|取得|达到|实现|采用|使用|利用|通过|引入|提出|生成|提供|'+verbs+r'))'
 for m in re.finditer(phrase+r'(?P<close>\))?(?='+predicate+r')',text,re.I):
  start,end=m.span('name');value=m.group('name')
  if m.group('close') and (start==0 or text[start-1]!='(' or start>1 and re.match(r'[a-z0-9_]',text[start-2])):continue
  # These are explicit grammatical introductions, not arbitrary modifiers
  # of a method name. "New Vega" remains a separate complete identity.
  introduction=re.match(r'(?:(?:a|an|the|our|this)\s+)?(?:(?:separate|proposed|new)\s+)?(?:model|method|algorithm|system)\s+(?:named\s+|called\s+)?',value,re.I)
  if introduction:start+=introduction.end();value=value[introduction.end():]
  identity=compact(value)
  if identity:matches.append((start,end,identity))
 kept=[]
 for m in sorted(set(matches),key=lambda m:(m[0],-(m[1]-m[0]))):
  if kept and m[0]<kept[-1][1]:continue
  kept.append(m)
 return kept


def owned_tail(text,start,end,identity=None):
 # A row may own an explicitly anaphoric next sentence, not an arbitrary
 # subsequent sentence whose independent subject has not been resolved.
 tail=text[start:end]
 for m in re.finditer(r'[。!?！？]|\.(?![0-9])',tail):
  following=tail[m.end():].lstrip(' ,，;；:：')
  repeated=identity and re.match(r'^(?:模型|方法)?\(?'+re.escape(identity)+r'\)?(?![a-z0-9_])',following)
  if following and not repeated and not re.match(r'(?:其|该|其中|但|然而|同时|分别|否则|实现上|并|it(?:s)?\b|this\b|however\b)',following):return tail[:m.end()]
 return tail


def owned_fragments(text,records):
 marks=occurrences(text,records)
 for n,(start,end,name) in enumerate(marks):
  limit=marks[n+1][0] if n+1<len(marks) else len(text)
  yield name,text[max(0,start-80):start],owned_tail(text,end,limit)


def role_contexts(text,records):
 # A role's leading definition can precede its variable (e.g. a verifier's
 # verdict mapped to RC). Other named actors terminate that leading scope.
 marks=occurrences(text,records);groups=[]
 for start,end,name in marks:
  if groups and groups[-1][2]==name:groups[-1][1]=end
  else:groups.append([start,end,name])
 known={r['name'] for r in records}
 for n,(start,end,name) in enumerate(groups):
  if name not in known:continue
  left=0
  if n:
   previous=groups[n-1]
   between=text[previous[1]:start]
   boundaries=list(re.finditer(r'[。!?！？;；]|\.(?![0-9])',between))
   left=previous[1]+boundaries[-1].end() if boundaries else start
  right=groups[n+1][0] if n+1<len(groups) else len(text)
  yield name,text[left:start]+owned_tail(text,start,right,name)


def metric_proof(text,records):
 t=semantic_view(text)['phrase'];byname={r['name']:r for r in records};hits=set();bad=False;baseline=None
 for name,prefix,tail in owned_fragments(t,records):
  # An unnamed primary compared with a table row is not that row's result.
  if re.search(r'(?:与|相比|comparedwith|comparedto)$',compact(prefix)):continue
  if name not in byname:baseline=None;continue
  if re.search(r'作为(?:基线|基准)|as\s*(?:the\s*)?baseline',tail):baseline=name
  record=byname[name]
  for field,(value,percent) in record['cells'].items():
   # Compact the regex's literal spaces without changing regex syntax.
   rx='(?:'+FIELDS[field].casefold()+')'
   transitions=list(re.finditer(rx+r'(?:指标)?(?:从|由)(?P<a>'+NUM+r')(?P<pa>%?)(?:提升至|提高至|增加至|下降至|降低至|提升到|提高到|大幅下降至|大幅降低至)(?P<b>'+NUM+r')(?P<pb>%?)',tail,re.I))
   for m in transitions:
    a=(Decimal(m.group('a')),bool(m.group('pa')));b=(Decimal(m.group('b')),bool(m.group('pb')))
    if b!=(value,percent):bad=True;continue
    hits.add((name,field,str(value),percent))
    if baseline and baseline!=name and field in byname[baseline]['cells']:
     if a!=byname[baseline]['cells'][field]:bad=True
     else:hits.add((baseline,field,str(a[0]),a[1]))
   if transitions:continue
   direct=re.finditer(rx+r'(?:指标)?\s*(?:为|是|达到|达到了|较低|较高|最高|达|is\b|of\b|at\b|equals?\b|:|：|=)?\s*[（(]?(?P<v>'+NUM+r')(?P<p>%?)(?![0-9]|\.[0-9])',tail,re.I)
   for m in direct:
    observed=(Decimal(m.group('v')),bool(m.group('p')))
    if observed!=(value,percent):bad=True
    else:hits.add((name,field,str(value),percent))
 if bad or len(hits)<5 or len({h[0] for h in hits})<2 or len({h[1] for h in hits})<3:return None
 return dict(kind='named_metric_cells',assignments=[dict(row=name,field=f,value=v,percent=p) for name,f,v,p in sorted(hits)],subject_scopes=subject_scope_trace(text,records))


def length_profile(rows):
 if not rows:return None
 header=' '.join(l.text for l in rows[0])
 if '参数' not in header or not re.search(r'取值|默认值',header):return None
 result=[]
 for row in rows[1:]:
  if len(row)<3:continue
  name=compact(row[0].text);values=re.findall(NUM,_semantic_text(row[1].text));desc=compact(' '.join(l.text for l in row[2:]))
  if len(values)<3:continue
  kind='input' if re.search(r'输入.*(?:历史|序列)|历史序列',desc) else 'label' if '起始标记' in desc else 'prediction' if re.search(r'预测.*(?:未来|时序)|未来时序',desc) else None
  if kind:result.append(dict(name=name,kind=kind,values=values))
 return result if {r['kind'] for r in result}=={'input','label','prediction'} else None


def length_proof(text,records):
 t=compact(text);patterns={'input':r'(?:窗口的)?输入长度(?:[a-z])?','label':r'起始标记长度(?:[a-z])?','prediction':r'预测长度(?:[a-z])?(?:\(预测步长\))?'};proof=[]
 for r in records:
  m=re.search(patterns[r['kind']]+r'分别设置为(?P<values>[0-9、,，和及.\-]+)',t)
  if not m or re.findall(NUM,m.group('values'))!=r['values']:return None
  proof.append(r)
 return dict(kind='ordered_parameter_vectors',parameters=proof)


def senses(text):
 t=compact(text);out=set()
 for k,rx in {'recurrent':r'循环神经网络|recurrent|\brnn\b','workload':r'工作负载|workload','autoencoder':r'自动编码器|autoencoder|(?<![a-z])ae(?![a-z])','labels':r'(?:少量|降低|减少|标注数据|标记样本|label)[^。；]{0,15}(?:标|需求|依赖|样本)|(?:标注|标记)(?:数据|样本)','active_learning':r'主动学习|activelearning'}.items():
  if re.search(rx,t):out.add(k)
 return out


def method_profile(rows):
 if not rows:return None
 method=next((l for l in rows[0] if compact(l.text) in {'方法名称','method','methods'}),None)
 desc=next((l for l in rows[0] if compact(l.text) in {'核心亮点','说明','description'}),None)
 if method is None or desc is None:return None
 result=[]
 for row in rows[1:]:
  names=[l for l in row if abs((l.bbox[0]+l.bbox[2])/2-(method.bbox[0]+method.bbox[2])/2)<50 and l.bbox[0]<desc.bbox[0]-10 and re.search(r'[a-z]',l.text,re.I)]
  if not names:continue
  label=min(names,key=lambda l:abs(l.bbox[0]-method.bbox[0]));name=method_name(label.text)
  features=senses(' '.join(l.text for l in row if l.bbox[0]>=desc.bbox[0]-3))
  if len(features)>=2:result.append(dict(name=name,features=features))
 return result if len(result)>=2 else None


def method_proof(text,records):
 t=semantic_view(text)['phrase'];byname={r['name']:r for r in records};hits=[]
 for name,prefix,fragment in owned_fragments(t,records):
  if name not in byname:continue
  if re.search(r'(?:与|相比|comparedwith)$',compact(prefix)):continue
  if re.search(r'(?:没有|未|不)(?:使用|采用|利用)(?:ae|自动编码器|循环神经网络|主动学习)',fragment):continue
  required=byname[name]['features']
  if len(required&senses(fragment))>=2:hits.append(dict(row=name,features=sorted(required&senses(fragment))))
 return dict(kind='named_functional_rows',rows=hits,subject_scopes=subject_scope_trace(text,records)) if len({h['row'] for h in hits})>=2 else None


def rule_profile(rows):
 if not rows or [compact(l.text) for l in rows[0]]!=['rule','pattern','action']:return None
 hits=[]
 for row in rows[1:]:
  if len(row)<3:continue
  name=compact(row[0].text);action=compact(' '.join(l.text for l in row[2:]));pattern=compact(row[1].text)
  if name=='projectionpruning' and 'eliminateunusedcolumns' in action and 'proj(' in pattern:hits.append('projection')
  if name=='predicatepushdown' and 'pushfiltersclosertodatasources' in action and 'filteraboveoperators' in pattern:hits.append('predicate')
 return hits if set(hits)=={'projection','predicate'} else None


def rule_proof(text,records):
 t=compact(text)
 if re.search(r'(?:没有|未|不)(?:采用|使用|应用|集成|支持)?(?:列裁剪|点边谓词下推|projectionpruning|predicatepushdown)',t):return None
 if not re.search(r'rbo|rule-basedoptimization',t):return None
 if not re.search(r'预定义[^。；]{0,30}规则[^。；]{0,20}查询计划[^。；]{0,15}(?:转换|优化)',t):return None
 if not (re.search(r'列裁剪|projectionpruning',t) and re.search(r'谓词下推|predicatepushdown',t) and re.search(r'(?:已被|采用|应用|集成)',t)):return None
 return dict(kind='operational_query_rules',rules=records)


def reward_profile(rows):
 if not rows or '奖励项' not in ''.join(l.text for l in rows[0]):return None
 result=[]
 for row in rows[1:]:
  if len(row)<3:continue
  m=re.match(r'([a-z][a-z0-9_]*)[（(]',compact(row[0].text))
  domain=compact(row[1].text)
  if not m or not domain.startswith('{') or not domain.endswith('}'):continue
  values={str(Decimal(x).normalize()) for x in re.findall(NUM,domain)}
  desc=compact(' '.join(l.text for l in row[2:]));kind='format' if '字段完整' in desc and '标签合法' in desc else 'reasoning' if re.search(r'推理.?结论一致',desc) else None
  if kind:result.append(dict(name=m.group(1),values=values,kind=kind))
 return result if len(result)>=2 else None


def reward_hits(text,records):
 hits=[];byname={r['name']:r for r in records}
 for identity,t in role_contexts(semantic_view(text)['phrase'],records):
  r=byname[identity];name=re.escape(identity);values=set()
  for m in re.finditer(r'(?<![a-z0-9_])'+name+r'(?:=|∈)(?P<set>\{[^}]+\}|'+NUM+r')',t):values.update(str(Decimal(x).normalize()) for x in re.findall(NUM,m.group('set')))
  if values!=r['values']:continue
  format_owner=re.search(r'格式奖励'+name+r'(?![a-z0-9_])',t) or re.search(r'格式奖励[:：]当[^。；]{0,200}'+name+r'=',t) or re.search(name+r'(?:为|是)(?:结构化)?格式奖励',t)
  if r['kind']=='format' and format_owner and ('字段完整' in t or '字段完整性' in t) and re.search(r'合法|候选集合约束',t):hits.append(r)
  purpose=r'(?:推理[-—]?结论)?一致性奖励'
  reasoning_owner=(re.search(r'推理[-—]?结论一致性奖励'+name+r'(?![a-z0-9_])',t)
                   or re.search(name+r'(?:的|为|是)?'+purpose,t))
  # A named verdict mapping owns its preceding verifier operations only
  # within this same actor scope, with the printed three-way NLI outcomes.
  mapping=re.search(r'映射为(?:离散)?(?:奖励|回报)'+name+r'(?![a-z0-9_])',t)
  if mapping and all(word in t for word in ('entailment','neutral','contradiction')):reasoning_owner=True
  if r['kind']=='reasoning' and reasoning_owner and re.search(r'nli',t) and 'reasoning' in t and 'diagnosis' in t and re.search(r'蕴含|entail',t):hits.append(r)
 return hits


SOURCE_OBJECT=r'(?:结果|指标|数据|奖励|定义|参数|results?|metrics?|data|rewards?|definitions?|parameters?)'
SOURCE_CITATION=r'(?:文献|参考文献|previous(?:study|work)|prior(?:study|work)|\[[0-9,;–\-]+\])'
SOURCE_RELATION=r'(?:中(?:的|所示)?|的|所给(?:出)?|所定义|给出|提出|定义|介绍|描述|来自|reported|defined|given|from|accordingto)'


def source_owned_clause(value):
 # Source ownership needs the actual result/definition object. Citing the
 # method or algorithm used for initialization does not own later metrics.
 chinese=re.search(r'(?:文献|参考文献)(?:\[[0-9,;–\-]+\])?'+SOURCE_RELATION+r'[^。!?！？;；]{0,50}'+SOURCE_OBJECT,value)
 english=(re.search(SOURCE_OBJECT+r'[^。!?！？;；]{0,70}(?:reported|defined|given|from)[^。!?！？;；]{0,35}'+SOURCE_CITATION,value)
          or re.search(r'accordingto[^。!?！？;；]{0,70}'+SOURCE_OBJECT+r'[^。!?！？;；]{0,70}'+SOURCE_CITATION,value))
 return bool(chinese or english)


def locally_owned_clause(value):
 # Own adoption resets only the adopted semantic object, not an unrelated
 # model, initialization procedure, seed, or network structure.
 subject=r'(?:本文|本研究|我们)(?:的)?'
 own_result=re.search(subject+r'(?:实验)?(?:结果|指标|数据|奖励|参数)(?:为|是|如下|显示|表明|采用|设置|定义|:|：)?',value)
 citation=r'(?:文献|参考文献)(?:\[[0-9,;–\-]+\])?(?:中)?(?:的|所给(?:出)?|所定义)?'
 modifiers=r'(?:'+citation+r'|该|此|上述|以下|下列|一种|新的)*'
 adopted=re.search(subject+r'(?:明确)?(?:采用|使用|定义|设置|引入|提出|设计)(?:了)?'+modifiers+SOURCE_OBJECT,value)
 english=re.search(r'(?:our|thisstudy[’\']?s|thiswork[’\']?s)(?:experimental)?(?:results?|metrics?|rewards?|definitions?|parameters?)',value)
 return bool(own_result or adopted or english)


def locally_owned_use(text):
 # Forward source framing persists until an explicit local result/adoption.
 # Backward attribution ("上述/these results") owns preceding clauses too.
 # Punctuation is retained so deleting a foreign clause cannot join actors.
 result=[];foreign=False
 pending_source=False
 for clause in re.split(r'(?<=[。!?！？;；，,:：])|(?<=\.)(?![0-9])',text):
  value=compact(clause)
  source=source_owned_clause(value);own=locally_owned_clause(value)
  if pending_source:
   source=source or bool(re.search(SOURCE_OBJECT,value))
   pending_source=False
  header=bool(re.search(r'(?:accordingto|据|根据)(?:文献|参考文献)?\[[0-9,;–\-]+\]',value))
  if header and not source and not own:pending_source=True
  backward=source and bool(re.search(r'(?:上述|以上|这些|前述|these|above|foregoing)'+r'[^。!?！？;；]{0,20}'+SOURCE_OBJECT,value))
  if backward:result=[]
  if source and not own:foreign=True
  elif own:foreign=False
  if not foreign:result.append(clause)
  elif result and result[-1]!='。引用来源限定。':result.append('。引用来源限定。')
 return ''.join(result)


def blocked(text):return bool(re.search(r'没有采用|没有使用|未采用|(?:我们|本文|本研究)(?:不采用|不使用)(?:下列|以下|上述|该|此)|并未|并非|未报告|notused|notadopted|doesnotuse|didnotuse',compact(text)))


def chapter_boundaries(document):
 from .caption_context import body_font
 result=[]
 for p in document.pages:
  typical=body_font(p)
  for l in p.lines:
   if l.font_size and l.font_size>=14 and (l.bold or typical and l.font_size>=typical*1.2) and re.match(r'^(?:第[一二三四五六七八九十0-9]+章|chapter\d+)',compact(l.text)):
    result.append((p.number,l.bbox[1]))
 return tuple(result)


def chapter_barrier(document,line,target,sources,boundaries=None):
 points=[(x['page'],x['bbox'][1]) for x in sources]+[(line.page_number,line.bbox[1]),(target.line.page_number,target.line.bbox[1])];low,high=min(points),max(points)
 if boundaries is None:boundaries=chapter_boundaries(document)
 return any(low<point<high for point in boundaries)


def repair_structured_table_usage(index,layout_objects=(),*,evidence=None):
 out=replace(index,**{n:list(getattr(index,n)) for n in DocumentIndex.__dataclass_fields__ if n!='document'})
 out.indirect_reference_targets={k:set(v) for k,v in getattr(index,'indirect_reference_targets',{}).items()}
 objects=tuple(layout_objects);pages={p.number:p for p in index.document.pages};profiles=[]
 for target in index.tables:
  b=owner(target,pages,objects)
  if b is None:continue
  rows=cells(pages[target.line.page_number],b)
  profiles.append((target,b,dict(metrics=metric_profile(rows),lengths=length_profile(rows),methods=method_profile(rows),rules=rule_profile(rows),reward=reward_profile(rows))))
 dirs=_directory_keys(index.document);scopes,nonbody=_scope_map(index.document,dirs);keys={_key(t.line) for t in (*index.figures,*index.tables,*index.appendices)}
 body=[(l,scopes.get(_key(l),'body')) for l in index.document.lines if _key(l) not in nonbody and _is_body(l,keys,dirs,pages) and not any(o.page_number==l.page_number and o.kind.endswith('_caption') and _contained(l,o.bbox) for o in objects) and not any(t.line.page_number==l.page_number and _contained(l,b) for t,b,p in profiles)]
 contexts=_semantic_contexts(body,index.document);reward_evidence={};boundaries=chapter_boundaries(index.document)
 for line,scope,sources in contexts:
  if blocked(line.text):continue
  use_text=locally_owned_use(line.text)
  if not use_text:continue
  choices={}
  for target,b,profile in profiles:
   if scope!=target.scope or chapter_barrier(index.document,line,target,sources,boundaries):continue
   proof=None
   for key,check in [('metrics',metric_proof),('lengths',length_proof),('methods',method_proof),('rules',rule_proof)]:
    if profile[key]:proof=check(use_text,profile[key])
    if proof:break
   physical=(target.scope,target.number,target.line.page_number,tuple(b))
   if proof:choices.setdefault(physical,[]).append((target,proof))
   if profile['reward'] and abs(target.line.page_number-line.page_number)<=1:
    for hit in reward_hits(use_text,profile['reward']):reward_evidence.setdefault(physical,[]).append((target,hit,line,scope,sources))
  if len(choices)!=1:continue
  for target,proof in next(iter(choices.values())):
   if abs(target.line.page_number-line.page_number)>1:continue
   before=len(evidence) if evidence is not None else 0
   _add_indirect(out,'table',target,line,scope,evidence,'独占物理表命名行的逐项字段/有序赋值/具体操作证明；保留原literal编号与类型')
   if evidence is not None and len(evidence)>before:evidence[-1].update(structured_table_proof=proof,body_sources=sources)
 # Discrete reward roles may be defined in separate native paragraphs. At
 # least two unique named roles with both their own domains and meanings must
 # resolve to one physical table, not a bag of repeated 0/1 constants.
 complete={k:v for k,v in reward_evidence.items() if len({h['name'] for t,h,l,s,b in v})>=2}
 if len(complete)==1:
  for target,hit,line,scope,sources in next(iter(complete.values())):
   before=len(evidence) if evidence is not None else 0
   _add_indirect(out,'table',target,line,scope,evidence,'两个奖励角色各自离散取值域和格式/推理语义对应唯一物理表')
   if evidence is not None and len(evidence)>before:evidence[-1].update(structured_table_proof=dict(kind='named_discrete_roles',role=hit['name'],domain=sorted(hit['values']),meaning=hit['kind']),body_sources=sources)
 return out
