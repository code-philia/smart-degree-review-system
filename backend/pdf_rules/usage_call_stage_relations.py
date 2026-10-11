"""Own the native before/during/after stages of a tool-call explanation."""
import re
from .usage_text_cache import normalize_text
from .usage_roadmap_relations import _owned_passages,_denied_operation

def _compact(value):return re.sub(r'\s+','',normalize_text(value))

def call_stage_native_candidate(title,fields):
    return bool(re.search(r'(?:函数|工具)调用.{0,10}(?:过程|流程)',_compact(title)))

def _role(text):
    return {'意图识别':'intent','检索工具':'tool','填写参数':'parameters',
            '信息提取':'extract','获取信息':'result','回答用户':'answer'}.get(_compact(text))

def _layout(fields):
    phases=[];operations=[];actors=[]
    for field in fields:
        if field.get('source')!='native':return None
        value=_compact(field['text']);match=re.fullmatch(r'(.{1,8})(前|中|后)',value)
        if match:phases.append((match.group(1),match.group(2),field))
        elif _role(value):operations.append((_role(value),field))
        else:actors.append(field)
    phases.sort(key=lambda row:row[2]['bbox'][1])
    if len(phases)!=3 or [r[1] for r in phases]!=['前','中','后'] or len({r[0] for r in phases})!=1:return None
    if phases[0][0]!='调用' or len(actors)!=1:return None
    actor=actors[0]
    if actor['bbox'][3]>=phases[0][2]['bbox'][1] or len(_compact(actor['text']))<3:return None
    centers=[(r[2]['bbox'][0]+r[2]['bbox'][2])/2 for r in phases]
    if max(centers)-min(centers)>5 or len(operations)!=6:return None
    expected=[{'intent','tool'},{'extract','parameters'},{'result','answer'}];stages=[]
    for i,(prefix,phase,anchor) in enumerate(phases):
        begin=anchor['bbox'][1];end=phases[i+1][2]['bbox'][1] if i<2 else begin+(begin-phases[i-1][2]['bbox'][1])*1.5
        owned=[(role,field) for role,field in operations if begin<=field['bbox'][1]<field['bbox'][3]<=end
               and (field['bbox'][0]+field['bbox'][2])/2>centers[i]+20]
        if len(owned)!=2 or {role for role,field in owned}!=expected[i]:return None
        stages.append(dict(label=prefix+phase,anchor_bbox=list(anchor['bbox']),
                           steps=[dict(role=role,text=field['text'],bbox=list(field['bbox'])) for role,field in owned]))
    return dict(actor=actor['text'],actor_bbox=list(actor['bbox']),stages=stages)

def _actor_operation(piece,actor,operation):
    match=re.search(re.escape(actor)+r'(?:则|就)?(?:会|将|通过|从|能够|负责|需要?|准确).{0,140}?'+operation,piece)
    if not match:return False
    between=match.group()
    return not re.search(r'(?:另[一个]*|其他|别的).{0,8}(?:模型|设备|系统|处理器|引擎).{0,5}(?:会|将|则|负责|执行|识别|提取|回答|填)|'
                         r'[A-Za-z][A-Za-z0-9_-]{2,25}(?:会|将|则|负责|执行|识别|提取|回答|填)',between)

def _explained(rows,value,physical):
    if _denied_operation(value):return False
    text=_compact(value);actor=_compact(physical['actor'])
    positions=[]
    for stage in physical['stages']:
        hits=list(re.finditer(re.escape(stage['label']),text))
        if not hits:return False
        positions.append(hits[-1].start())
    if positions!=sorted(positions):return False
    pieces=[text[a:(positions[i+1] if i<2 else len(text))] for i,a in enumerate(positions)]
    if any(actor not in piece for piece in pieces):return False
    if not all(_actor_operation(piece,actor,operation) for piece,operation in zip(pieces,[
            r'识别.{0,10}(?:用户)?意图',r'提取.{0,25}(?:信息|参数)',r'自然语言.{0,20}(?:呈现|回答).{0,10}用户'])):return False
    # Selection and parameter construction also belong to the physical caller.
    # Merely mentioning that caller before a different device acts is insufficient.
    if not _actor_operation(pieces[0],actor,r'(?:选取|选择|检索).{0,25}(?:工具|函数|API)'):return False
    if not _actor_operation(pieces[1],actor,r'参数.{0,40}(?:填充|填写|联合|生成.{0,15}调用命令)'):return False
    return (bool(re.search(r'识别.{0,10}(?:用户)?意图',pieces[0]))
            and bool(re.search(r'(?:选取|选择|检索).{0,25}(?:工具|函数|API)',pieces[0],re.I))
            and bool(re.search(r'提取.{0,25}(?:信息|参数)',pieces[1]))
            and bool(re.search(r'参数.{0,40}(?:填充|填写|联合|生成.{0,15}调用命令)',pieces[1]))
            and bool(re.search(r'(?:对应|相应|所选(?:择|取)?|选定|被选(?:择|取)?)(?:的)?(?:工具|API).{0,20}返回.{0,20}(?:信息|数据)',pieces[2],re.I))
            and bool(re.search(r'自然语言.{0,20}(?:呈现|回答).{0,10}用户',pieces[2])))

def call_stage_relation_proposals(context,groups,nearby):
    answer=[]
    for ordinal,areas in context['regions'].items():
        if len(areas)!=1 or not call_stage_native_candidate(areas[0]['title'],[]):continue
        physical=_layout(context['native_fields'].get(ordinal,[]))
        if physical is None:continue
        for rows,value in _owned_passages(ordinal,groups,nearby):
            if _explained(rows,value,physical):
                answer.append((ordinal,'owned_before_during_after_call_steps',rows,physical));break
    return answer
