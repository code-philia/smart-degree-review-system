"""Bind long chapter-labelled research methods to their own concrete outline."""
import re
from .numbering import normalize_label
from .usage_text_cache import normalize_text
from .usage_scope import is_body_usage_scope
from .usage_figure_evidence import _epoch

_CHAPTER=re.compile(r'^[（(]?第([一二三四五六七八九十\d]+)章[）)]?$')
_TITLE=re.compile(r'研究(?:内容|框架)|主要研究|(?:关键|共性)(?:问题|挑战).*解决方法|research.*(?:content|framework)|challenges.*methods',re.I)
_REFERENCE=re.compile(r'(?:图|Figures?|Fig\.?)\s*([A-Z]?\d+(?:[.\-–]\d+)*)',re.I)
_OPERATIONS=re.compile(r'注入|预处理|递归|偏移|扫描|预测|对齐|提取|映射|编码|构建|重构|计算|训练|优化|渲染|引导|聚合|\b(?:extract|predict|encode|align|reconstruct)\w*',re.I)

def _text(value):return re.sub(r'\s+','',normalize_text(value)).casefold()
def _cx(field):return (field['bbox'][0]+field['bbox'][2])/2

def chapter_plan_title_candidate(title):return bool(_TITLE.search(title))

def _method_terms(text):
    # Split grammatical scaffolding and goals while retaining every noun.
    text=_text(text)
    pieces=re.split(r'基于|架构|研究|方法|的|与|以及|(?=加速|泛化)|(?<=加速)|(?<=泛化)',text)
    return [part for part in pieces if len(part)>=2]

def _method_lines(anchor,fields,direction):
    chosen=[];edge=anchor['bbox'][3] if direction>0 else anchor['bbox'][1]
    candidates=sorted((f for f in fields if f is not anchor and f['page_number']==anchor['page_number']
                       and abs(_cx(f)-_cx(anchor))<=9),key=lambda f:f['bbox'][1],reverse=direction<0)
    for field in candidates:
        box=field['bbox'];gap=box[1]-edge if direction>0 else edge-box[3]
        if gap < -2:continue
        if gap>5:break
        if _CHAPTER.fullmatch(_text(field['text'])):break
        if box[3]-box[1]>23 or len(_text(field['text']))<3:break
        chosen.append(field);edge=box[3] if direction>0 else box[1]
        if len(chosen)>5:return []
    return sorted(chosen,key=lambda f:f['bbox'][1])

def _layout(title,fields):
    if not chapter_plan_title_candidate(title):return None
    anchors=[f for f in fields if _CHAPTER.fullmatch(_text(f['text']))]
    if not 2<=len(anchors)<=6:return None
    branches=[]
    for anchor in anchors:
        alternatives=[]
        for direction in (1,-1):
            rows=_method_lines(anchor,fields,direction)
            name=''.join(row['text'] for row in rows)
            terms=_method_terms(name)
            if len(rows)>=2 and len(_text(name))>=20 and len(terms)>=2 and sum(map(len,terms))>=16:
                alternatives.append((rows,name,terms))
        if len(alternatives)!=1:return None
        rows,name,terms=alternatives[0]
        branches.append(dict(chapter=_CHAPTER.fullmatch(_text(anchor['text'])).group(1),
                             chapter_field=anchor,method=name,method_fields=rows,method_terms=terms))
    if len({tuple(branch['method_terms']) for branch in branches})!=len(branches):return None
    claimed={(f['page_number'],tuple(f['bbox']),f['text']) for b in branches for f in b['method_fields']}
    for field in fields:
        if not re.match(r'^(?:基于|面向|融合|采用)',_text(field['text'])):continue
        block=[field]+_method_lines(field,fields,1)
        value=_text(''.join(f['text'] for f in block))
        if len(value)>=20 and value.endswith(('研究','方法')) and any(
                (f['page_number'],tuple(f['bbox']),f['text']) not in claimed for f in block):return None
    return dict(branches=branches)

def chapter_plan_native_candidate(title,fields):return _layout(title,fields) is not None

def _eligible_body(context,target):
    target_epoch=_epoch(context,target);chapter=context['chapters'].get((target.line.page_number,target_epoch))
    for rows in context['body_passages']:
        if any(abs(r.page_number-target.line.page_number)>6 or _epoch(context,r)!=target_epoch
               or context['chapters'].get((r.page_number,target_epoch))!=chapter for r in rows):continue
        if any(r.source!='native' or not r.font_size or r.direction[0]<.9 or abs(r.direction[1])>.05 for r in rows):continue
        yield rows

def chapter_plan_content_candidate(context,groups,ordinal):
    if not chapter_plan_title_candidate(context['regions'][ordinal][0]['title']):return False
    target=groups[ordinal][0];numbers={l.number for l in groups[ordinal]};chapters=set()
    if not is_body_usage_scope(context['usage_scope_map'],target):return False
    for chapter,method,text,end in _declarations(context,target,numbers):
        if _owned_mechanism(method,text,end):chapters.add(chapter)
    return 2<=len(chapters)<=6


# Negation can have an intervening chapter/preposition: 未在本章采用.
_DENIED=re.compile(r'(?:不|未|没有|并非).{0,12}(?:采用|使用|实现|提出|讨论|解释|属于|对应|执行|运用|开展)|(?:无需|无须).{0,8}(?:上述|这些|该)(?:方法|策略|机制|技术)|(?:另一(?:个|种|篇)|其他|其它)(?:研究|论文|系统|方法|模型)|\b(?:not|never)\b',re.I)
_PROCESS=re.compile(r'注入|预处理|递归|偏移|扫描|预测|对齐|提取|映射|编码|重构|渲染|引导|聚合|变换|迁移|融合')
_SUBJECT=re.compile(r'(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9_-]{2,})\s*[\u4e00-\u9fff]{0,8}?(?:模型|网络|架构)\s*(?:采用|使用|通过|进行|实现|具有|的)')
_NAMED_PROCESS_SUBJECT=re.compile(r'(?:^|[。！？,，:：;；])(?:基于)?([A-Za-z0-9_\u4e00-\u9fff-]{2,40}?(?:模型|网络|架构))(?:采用|使用|通过|进行|实现|具有|的)')


def _owner_matches(method,subject):
    name=_text(method);owner=_text(subject)
    owner=re.sub(r'^(?:本论文|本文|本章)(?:提出|设计|采用|构建|使用|选用)(?:了)?','',owner)
    if owner.startswith('基于'):
        declared_subject=re.match(r'^基于(.+?)(?:架构|的|方法)',owner)
        if declared_subject:owner=declared_subject.group(1)
        else:owner=owner[2:]
    owner=re.sub(r'(?:模型|网络|架构|方法)$','',owner)
    names=re.findall(r'[a-z][a-z0-9_-]{2,}',name)
    if re.fullmatch(r'[a-z][a-z0-9_-]{2,}',owner):return owner in names
    # The initial 'based on ...' phrase supplies the concrete subject;
    # task words later in the method title are not model identities.
    declared=re.match(r'^基于(.+?)(?:架构|的)',name)
    if not declared:return False
    core=re.sub(r'(?:模型|网络|架构|方法)$','',declared.group(1))
    return owner==core


def _same_declared_owner(method,rest):
    """Do not transfer a later method's actions to the initial chapter topic."""
    name=_text(method);text=_text(rest)
    # A newly selected backbone is an owner even without a 'model' suffix.
    for match in re.finditer(r'(?:基于|(?:骨干|基础架构|主体).{0,8}(?:采用|使用|选用)|选用)([a-z][a-z0-9_-]{2,})',text):
        if not _owner_matches(method,match.group(1)):return False
    for match in re.finditer(r'以([a-z][a-z0-9_-]{2,})为(?:骨干|基础架构|主体)',text):
        if not _owner_matches(method,match.group(1)):return False
    # An anaphor can refer to a new intervening method, rather than to the
    # earlier complete chapter declaration. Keep that ambiguity uncredited.
    if '该方法' in text:
        before=text.split('该方法',1)[0]
        introduced=re.finditer(r'(?:介绍|采用|使用|选用|实现)(?:了)?([^。！？;；]{1,45}?(?:方法|模型|网络|架构))',before)
        if any(not _owner_matches(method,match.group(1)) for match in introduced):return False
    # An explicit change of the implementation's subject also breaks the
    # declaration-to-contribution link; this is independent of its name.
    selections=re.finditer(r'(?:实际(?:骨干|实现|方法)?(?:采用|使用|选用|为)|(?:骨干|主体|基础架构)(?:为|选用|采用|使用))([^。！？,，;；]{2,40})',text)
    if any(not _owner_matches(method,match.group(1)) for match in selections):return False
    return True


def _declarations(context,target,numbers):
    """Enumerate complete chapter-method declarations from original paragraphs."""
    seen=set()
    pattern=re.compile(r'第([一二三四五六七八九十\d]+)章(?:主要)?(?:介绍|研究|围绕|提出|论述)[^。！？;；]{0,30}?(基于[^。！？，,;；]{8,100}?(?:研究|方法))')
    for rows in _eligible_body(context,target):
        for row in rows:
            key=(row.page_number,row.bbox,row.text)
            if key in seen:continue
            seen.add(key);text=_text(row.text)
            if {normalize_label(m.group(1)) for m in _REFERENCE.finditer(text)}-numbers:continue
            matches=list(pattern.finditer(text))
            if len(matches)==1:
                match=matches[0]
                yield match.group(1),match.group(2),text,match.end()


def _linked_content(method,mechanism):
    """A concrete process must still belong to the pictured method's subject."""
    name=_text(method);body=_text(mechanism)
    if '分类' not in name and re.search(r'分类(?:器|模型|模块|标签|网络)',body):return False
    if any(not _owner_matches(method,subject) for subject in _NAMED_PROCESS_SUBJECT.findall(body)):return False
    names=re.findall(r'[a-z][a-z0-9_-]{2,}',name)
    words=re.findall(r'[a-z][a-z0-9_-]{2,}',body)
    if any(not any(subject.casefold()==n for n in names) for subject in _SUBJECT.findall(mechanism)):
        return False
    # A module such as an attention kernel can retain the architecture's
    # printed suffix; this is additional identity evidence, never enough use.
    identity=any(len(min(a,b,key=len))>=3 and (a.endswith(b) or b.endswith(a)) for a in names for b in words)
    if len(set(_PROCESS.findall(body)))<2:return False
    if names:return identity
    # Chinese model identities still need an actual operative operand. A
    # shared task word such as style/image cannot credit a different method.
    if '扩散模型' in name:
        return (bool(re.search(r'(?:潜在|初始|随机).{0,8}噪声',body))
                and bool(re.search(r'白化|着色|去噪|噪声.{0,25}(?:变换|预处理|引导)',body))
                and '风格' in body)
    if '光流驱动几何变形' in name:
        return ('光流' in body and '几何' in body and '风格' in body
                and bool(re.search(r'光流(?:场)?.{0,25}(?:引导|驱动|对齐)',body)))
    return False


def _owned_mechanism(method,own,identity_end):
    """Topic sentences alone do not own a later author's/model's actions."""
    rest=own[identity_end:]
    if _DENIED.search(own):return False
    if not _same_declared_owner(method,rest):return False
    if re.search(r'综述|回顾|文献\s*\[|(?:作者|他人|其他研究).{0,12}提出|仅(?:列|介绍|讨论)',rest):return False
    # Own contributions must be tied back to the complete named method.
    # A generic computing/training verb, or a quoted list, is insufficient.
    contribution=re.search(r'(?:为此|为(?:在)?(?:保障|保证|提升|提高|解决|增强|实现)[^。！？;；]{4,80}|针对(?:上述|这些|该)(?:问题|挑战)?)[,，]?本(?:论文|文|章)(?:提出|设计|采用|构建)(?:了)?',_text(rest))
    if contribution:
        compact=_text(rest);start=contribution.end()
        mechanism=re.split(r'大量|多维实验|实验表明|实验结果',compact[start:],maxsplit=1)[0]
        return _linked_content(method,mechanism)
    # An explicit method anaphor can explain the actual composition and its
    # directed operation rather than introducing another named model.
    compact=_text(rest)
    if not re.search(r'该方法(?:主要)?由.{4,100}(?:构成|组成)',compact):return False
    if not re.search(r'(?:通过|利用).{4,100}(?:引导|对齐|映射|迁移|变换|重构)',compact):return False
    return _linked_content(method,compact)


def _witness(branch,context,target,numbers):
    # Preserve an original native paragraph as its evidence object; never
    # return a window containing several independently numbered chapters.
    seen=set()
    for rows in _eligible_body(context,target):
        for row in rows:
            key=(row.page_number,row.bbox,row.text)
            if key in seen:continue
            seen.add(key)
            text=normalize_text(row.text)
            if _DENIED.search(text):continue
            if {normalize_label(m.group(1)) for m in _REFERENCE.finditer(text)}-numbers:continue
            matches=list(re.finditer(r'第\s*([一二三四五六七八九十\d]+)\s*章',text))
            if len(matches)!=1 or matches[0].group(1)!=branch['chapter']:continue
            own=text[matches[0].start():]
            if not re.match(r'^第\s*[一二三四五六七八九十\d]+\s*章(?:主要)?(?:介绍|研究|围绕|提出|论述)',own):continue
            compact=_text(own);start=0
            for term in branch['method_terms']:
                position=compact.find(term,start)
                if position<0:break
                start=position+len(term)
            else:
                if _owned_mechanism(branch['method'],compact,start):return [row]
    return []


def chapter_plan_relation_proposals(context,groups,nearby,fields=None):
    actual=context['native_fields'] if fields is None else fields;answer=[]
    for ordinal,areas in context['regions'].items():
        topology=_layout(areas[0]['title'],actual.get(ordinal,[]))
        if topology is None:continue
        target=groups[ordinal][0]
        if not is_body_usage_scope(context['usage_scope_map'],target):continue
        numbers={label.number for label in groups[ordinal]}
        declared={chapter for chapter,method,text,end in _declarations(context,target,numbers)}
        if declared!={branch['chapter'] for branch in topology['branches']}:continue
        witnesses=[_witness(branch,context,target,numbers) for branch in topology['branches']]
        if not all(witnesses):continue
        rows=list({(r.page_number,r.bbox,r.text):r for owned in witnesses for r in owned}.values())
        answer.append((ordinal,'chapter_owned_research_methods',rows,topology))
    return answer
