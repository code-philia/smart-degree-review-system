"""Bind a version-conflict illustration to its independent worked example."""
from hashlib import sha256
from pathlib import Path
import re

from .usage_text_cache import normalize_text
from .usage_network_relations import _center, _distinct_ink


def _text(value):
    return re.sub(r'\s+','',normalize_text(value)).casefold()


def transaction_conflict_title(title):
    return bool(re.search(r'(?:区块|事务|交易|读写).{0,8}冲突|(?:transaction|block|read.write).{0,12}conflict',
                          normalize_text(title),re.I))


def transaction_content_candidate(title,passages):
    if not transaction_conflict_title(title):return False
    value=_text(' '.join(text for rows,text in passages))
    return all(re.search(pattern,value) for pattern in
               (r'模拟.{0,70}(?:锁定|快照|读写集)',r'排序',r'验证',
                r'(?:并发|同时).{0,100}(?:读取|读写)',r'更新.{0,30}(?:版本|v\d)',r'不匹配|冲突'))


def _observed(fields,area,document):
    from .usage_graphic_ocr import _json,_valid_facts
    try:pdf_sha=sha256(Path(document.path).read_bytes()).hexdigest()
    except OSError:return []
    context=dict(pdf_sha=pdf_sha,page_number=area['page_number'],bbox=area['bbox'])
    context['region_identity']=sha256(_json(context)).hexdigest()
    anchors={(row.page_number,tuple(row.bbox),row.text) for page in document.pages for row in page.lines if row.source=='native'}
    roi=area['bbox']
    result=[]
    for field in fields:
        b=field.get('bbox',[])
        if (len(b)!=4 or field.get('page_number')!=area['page_number']
                or not roi[0]<=b[0]<b[2]<=roi[2] or not roi[1]<=b[1]<b[3]<=roi[3]):continue
        if ((field.get('source')=='native' and (field['page_number'],tuple(b),field.get('text')) in anchors)
                or _valid_facts([field],context)):result.append(field)
    return result


def _version_example(fields):
    rows=[];updates=[];validations={}
    for field in fields:
        text=_text(field['text'])
        match=re.fullmatch(r'([a-z]\d+)\(版本([a-z]\d+)\)',text)
        if match:rows.append((field,*match.groups()))
        match=re.fullmatch(r'更新([a-z]\d+)为([a-z]\d+)',text)
        if match:updates.append((field,*match.groups()))
        match=re.fullmatch(r'([a-z]\d+)验证[:：]?',text)
        if match:validations.setdefault(match.group(1),[]).append(field)
    pairs={(key,old,new) for f,key,old in rows for u,other,new in updates if key==other and old!=new}
    if len(pairs)!=1 or len(validations)!=2:return None
    key,old,new=pairs.pop()
    top=sorted([(name,_distinct_ink(values,re.escape(name)+r'\s*验证\s*[:：]?')) for name,values in validations.items()],
               key=lambda item:_center(item[1][0],1) if item[1] else 0)
    if any(len(values)!=1 for name,values in top):return None
    a,b=top[0][1][0],top[1][1][0]
    if abs(_center(a,0)-_center(b,0))>20 or _center(b,1)-_center(a,1)<30:return None
    update=_distinct_ink([f for f,k,v in updates if k==key and v==new],r'更新\s*'+re.escape(key)+r'\s*为\s*'+re.escape(new))
    initial=_distinct_ink([f for f,k,v in rows if k==key and v==old],re.escape(key)+r'\s*\(版本\s*'+re.escape(old)+r'\)')
    if len(update)!=1 or len(initial)!=1:return None
    if not (a['bbox'][3]<=update[0]['bbox'][1]<update[0]['bbox'][3]<b['bbox'][1]
            and _center(initial[0],0)<a['bbox'][0]):return None
    return dict(key=key,old=old,new=new,first=top[0][0],second=top[1][0],
                initial=initial[0],update=update[0],validations=[a,b])


def _body_example(example,passages):
    key,old,new,first,second=[re.escape(example[name]) for name in ('key','old','new','first','second')]
    for rows,value in passages:
        text=_text(value)
        patterns=(first+r'.{0,20}和'+second+r'.{0,60}同一个键值对象'+key,
                  r'读取到的'+key+r'版本均为'+old,
                  first+r'.{0,120}率先.{0,60}排序',
                  r'当前版本.{0,12}为'+old+r'.{0,30}通过验证.{0,20}'+key+r'更新为新版本'+new,
                  second+r'.{0,120}随后.{0,120}读取版本.{0,20}旧版本'+old,
                  r'读取版本'+old+r'.{0,30}当前最新版本'+new)
        if not all(re.search(pattern,text) for pattern in patterns):continue
        if '不匹配' in text:return rows
        # Retain the actual unfinished native clause and its next-page suffix.
        last=max(rows,key=lambda row:(row.page_number,row.bbox[3]))
        for continuation,joined in passages:
            if not any(row.page_number==last.page_number and row.bbox==last.bbox for row in continuation):continue
            after=[row for row in continuation if row.page_number==last.page_number+1]
            if after and re.match(r'^不匹配[。.]?$',_text(after[0].text)):
                return [*rows,*after]
        # An unfinished symbolic comparison ends in the new version rather
        # than a Chinese glyph. Match only its literal next-page suffix, with
        # independent paragraph geometry; do not join arbitrary body text.
        if not _text(last.text).endswith(example['new']):continue
        endings={(row.page_number,row.bbox,row.text):row for other,value in passages for row in other
                 if row.page_number==last.page_number+1}
        if not endings:continue
        after=min(endings.values(),key=lambda row:(row.bbox[1],row.bbox[0]))
        if (re.fullmatch(r'不匹配[。.]?',_text(after.text))
                and last.source==after.source=='native' and not last.bold and not after.bold
                and last.direction==after.direction==(1.0,0.0)
                and last.font_size and after.font_size and abs(last.font_size-after.font_size)<=.2
                and last.bbox[3]>=last.page_height*.78 and last.bbox[2]>=last.page_width*.75
                and after.bbox[1]<=after.page_height*.25):return [*rows,after]
    return []


def transaction_relation_proposals(context,groups,nearby,observed_fields=None):
    answer=[]
    for ordinal,areas in context['regions'].items():
        if len(areas)!=1:continue
        area=areas[0];passages=nearby(ordinal)
        if not transaction_content_candidate(area['title'],passages):continue
        fields=_observed((observed_fields or context['native_fields']).get(ordinal,[]),area,context['_document'])
        stages=[_distinct_ink(fields,pattern) for pattern in (r'背书\s*/\s*模拟',r'排序',r'验证与提交')]
        conflicts=_distinct_ink(fields,r'读写冲突')
        if any(len(stage)!=1 for stage in stages) or len(conflicts)!=1:continue
        stages=[stage[0] for stage in stages]
        if (not stages[0]['bbox'][2]<stages[1]['bbox'][0]<stages[1]['bbox'][2]<stages[2]['bbox'][0]
                or max(_center(f,1) for f in stages)-min(_center(f,1) for f in stages)>12):continue
        example=_version_example(fields)
        if example is None:continue
        if not example['validations'][0]['bbox'][3]<conflicts[0]['bbox'][1]<example['validations'][1]['bbox'][3]:continue
        body=_body_example(example,passages)
        if not body:continue
        answer.append((ordinal,'shared_snapshot_before_serial_validation_conflict',body,
                       dict(stages=stages,conflict=conflicts[0],version_example=example,
                            criterion='Bound physical stages and key/version/validation roles match the independent two-transaction worked example.')))
    return answer
