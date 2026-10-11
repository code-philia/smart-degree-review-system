"""Native, physically owned comparisons whose complete types are defined in prose.

The gate only selects candidates.  A usage proposal needs every printed panel,
independent original body ink, defining operations, and unique physical ownership.
No PDF/OCR reads, parser changes, source-specific numbers, or index mutation occur.
"""
import re
import unicodedata
from .numbering import normalize_label
from .usage_scope import usage_scope_identity

_BAD={'header','footer','toc','reference','figure_caption','table_caption','heading','equation','code'}
_FIG=re.compile(r'(?:图|figures?|fig\.?)\s*([a-z]?\d+(?:[.\-–]\d+)*)',re.I)
_DENIED=re.compile(r'(?:未|不|没有|无需)(?:采用|使用|实现|定义|讨论|解释|介绍|说明)|\b(?:not|never|without)\b',re.I)
_FOREIGN=re.compile(r'(?:另一|其他|另一个|other|another).{0,30}(?:模型|方法|算法|网络|model|method).{0,12}(?:执行|采用|使用|实现|映射|构造|perform|use|implement)',re.I)
_FOREIGN_NAME=re.compile(r'(?<![a-z0-9_-])([a-z][a-z0-9_-]{1,}(?:\s+[a-z][a-z0-9_-]*){0,3})\s*(?:模型|方法|算法|网络|架构|model|method|algorithm|network|architecture)\s*(?:执行|采用|使用|实现|映射|构造|performs?|uses?|implements?)',re.I)
_CHINESE_NAME=re.compile(r'(?:^|[。！？；：，,\n])(?:本文|本章|本节|我们)?(?:采用|使用)?([a-z\u4e00-\u9fff][a-z0-9_\-\u4e00-\u9fff]*(?:\s+[a-z][a-z0-9_-]*){0,3})\s*(?:模型|方法|算法|网络|架构)\s*(?:执行|采用|使用|实现|映射|构造)',re.I)
_COMMON_ACTOR=re.compile(r'^(?:这些|那些|上述|前述|这种|这类|此类|该|本|此|其|不同|各类|相关|当前|所有|各|本文|本研究)$')
_EXTERNAL=re.compile(r'(?:文献(?:\[[^]]+\])?|另一(?:篇)?论文|其他论文|(?:another|other|external)\s+(?:paper|article)).{0,15}(?:图|figures?)',re.I)
_ALIASES={
 'color':r'颜色场|color\s*field', 'mls':r'移动最小二乘(?:法)?|mls(?:-based\s*point\s*surface)?',
 'power':r'power\s*diagram', 'tensor':r'张量并行|tensor\s*parallel(?:ism)?',
 'data':r'数据并行|data\s*parallel(?:ism)?', 'pipeline':r'流水线并行|pipeline\s*parallel(?:ism)?',
 'voxel':r'体素|voxels?', 'octree':r'八叉树|octree', 'point':r'点云|point\s*cloud',
 'mesh':r'网格|mesh', 'nerf':r'神经辐射场|nerf',
 'gaussian':r'三维高斯泼溅|3d\s*gaussian\s*splatting|3dgs',
}
_OPS={
 'color':(r'界面|interface',r'识别|描述|represent|identify',r'表面张力|surface\s*tension'),
 'mls':(r'核加权|kernel.{0,12}weight',r'局部多项式.{0,3}拟合|local.{0,15}polynomial.{0,10}fit',r'连续流形|continuous.{0,8}manifold',r'微分算子|differential.{0,8}operator'),
 'power':(r'粒子|particle',r'构造.{0,8}显式控制体积|construct.{0,20}control.{0,8}volume',r'通量守恒|flux.{0,10}conserv'),
 'tensor':(r'(?:张量|模型).{0,8}参数|tensor.{0,8}parameter',r'拆分.{0,8}(?:多个)?设备|split.{0,20}device',r'聚合|aggregat'),
 'data':(r'输入.{0,8}(?:批量|批次).{0,8}(?:拆分|分发)|input.{0,15}batch.{0,15}(?:split|distribut)',r'每个设备.{0,8}存储完整.{0,8}模型参数|each.{0,8}device.{0,15}complete.{0,10}model',r'不同批次|different.{0,8}batch'),
 'pipeline':(r'按层.{0,8}(?:划分|拆分).{0,15}(?:连续)?层组|partition.{0,20}layer',r'层序.{0,12}(?:流转|执行)|layer.{0,10}order',r'不同设备|different.{0,8}device'),
 'voxel':(r'规则.{0,8}立方体|regular.{0,8}cub',r'网格单元.{0,8}存储|cell.{0,8}stor',r'物理属性|physical.{0,8}propert'),
 'octree':(r'递归.{0,15}八个子|recurs.{0,20}eight',r'表面.{0,15}细分|surface.{0,20}subdiv',r'空旷.{0,8}粗粒度|empty.{0,12}coarse'),
 'point':(r'无序.{0,12}空间坐标点|unordered.{0,15}coordinate',r'激光雷达|深度相机|lidar|depth.{0,8}camera',r'缺乏.{0,20}拓扑连接|without.{0,15}topolog'),
 'mesh':(r'顶点.{0,20}(?:多边形)?面片|vertic.{0,20}face',r'构成|consist|compos',r'光栅化|rasteriz',r'渲染|render'),
 'nerf':(r'多层感知机|mlp',r'空间坐标.{0,15}观测视角.{0,12}映射.{0,12}体密度.{0,8}颜色|coordinate.{0,20}view.{0,20}density.{0,12}colou?r',r'体渲染|volume.{0,8}render',r'视线.{0,12}积分|ray.{0,12}integrat'),
 'gaussian':(r'各向异性.{0,8}高斯|anisotropic.{0,8}gaussian',r'协方差|covariance',r'不透明度|opacity',r'光栅化|rasteriz',r'投影.{0,8}二维|project.{0,12}2d'),
}

def _text(value):return unicodedata.normalize('NFKC',value).casefold()
def _compact(value):return re.sub(r'\s+','',_text(value))
def _inside(a,b):return b[0]-1<=a[0] and b[1]-.5<=a[1] and a[2]<=b[2]+1 and a[3]<=b[3]+.5
def _center(f,axis):return (f['bbox'][axis]+f['bbox'][axis+2])/2
def _ink(row):
    if row.source!='native' or not row.font_size or row.font_size<=0 or row.direction[0]<.9 or abs(row.direction[1])>.05:return False
    covered={i for start,end,b in row.text_regions if b[2]>b[0] and b[3]>b[1] for i in range(start,end)}
    return all(i in covered for i,c in enumerate(row.text) if not c.isspace())

def comparison_title_candidate(title):
    return bool(re.search(r'比较|对比|表示|表达|表征|并行策略|comparison|representation|parallel.{0,10}strateg',_text(title)))

def _type(value):
    value=re.sub(r'^\([a-z]\)\s*','',_text(value).strip())
    found=[name for name,pattern in _ALIASES.items() if re.fullmatch(pattern,value)]
    return found[0] if len(found)==1 else None

def _layout(title,fields):
    if not comparison_title_candidate(title):return None
    labels=[(f,_type(f['text'])) for f in fields if _type(f['text'])]
    # A short unknown header may be resolved only by its own column geometry
    # and printed defining properties; the word "network" alone is insufficient.
    for field in fields:
        if _compact(field['text']) not in {'网络','network'}:continue
        column=sorted((f for f in fields if abs(_center(f,0)-_center(field,0))<15 and f['bbox'][1]>field['bbox'][3]),key=lambda f:f['bbox'][1])
        if not column or any(b['bbox'][1]-a['bbox'][3]>6 for a,b in zip(column,column[1:])):continue
        value=_compact(''.join(f['text'] for f in column))
        if all(re.search(p,value) for p in (r'顶点.{0,6}面片|vertic.{0,8}face',r'构成.{0,8}几何表面|geometric.{0,8}surface',r'渲染|render')):labels.append((field,'mesh'))
    if not 2<=len(labels)<=8:return None
    if len({kind for f,kind in labels})!=len(labels):return None
    if max(_center(f,1) for f,k in labels)-min(_center(f,1) for f,k in labels)>5:return None
    labels.sort(key=lambda pair:_center(pair[0],0))
    if any(a['bbox'][2]>=b['bbox'][0] for (a,ka),(b,kb) in zip(labels,labels[1:])):return None
    # Every short alphabetic/header item on this same row must have a type.
    for f in fields:
        if abs(_center(f,1)-_center(labels[0][0],1))>3 or any(f is a for a,k in labels):continue
        if not re.search(r'[a-z\u4e00-\u9fff]',f['text']):continue
        stub=(f['bbox'][2]<labels[0][0]['bbox'][0] and any(
            abs(_center(other,0)-_center(f,0))<15 and other['bbox'][1]>f['bbox'][3]
            and re.fullmatch(r'说明|示例图像|description|example(?:image)?',_compact(other['text'])) for other in fields))
        if not stub:return None
    panel_letters={}
    for f,kind in labels:
        match=re.match(r'^\(([a-z])\)',_text(f['text']))
        if match:panel_letters[match.group(1)]=kind
    hybrids=[]
    for field in fields:
        match=re.fullmatch(r'\(([a-z])\)\+\(([a-z])\)',_compact(field['text']))
        if not match:continue
        if not all(letter in panel_letters for letter in match.groups()):return None
        kinds=tuple(sorted(panel_letters[letter] for letter in match.groups()))
        if len(set(kinds))!=2 or 'pipeline' not in kinds or not set(kinds)<={'pipeline','tensor','data'}:return None
        if field['bbox'][1]<=max(f['bbox'][3] for f,k in labels):return None
        hybrids.append((field,'+'.join(kinds)))
    if len({kind for f,kind in hybrids})!=len(hybrids):return None
    return dict(kind='complete_typed_comparison',panels=[dict(identity=k,text=f['text'],page_number=f['page_number'],bbox=f['bbox']) for f,k in labels+hybrids])

def comparison_native_candidate(title,fields):
    return _layout(title,[f for f in fields if f.get('source')=='native']) is not None

def _physical(context,areas,fields):
    if _layout(areas[0]['title'],[f for f in fields if f.get('source')=='native']) is None:return None
    document=context.get('_document')
    if document is None:return None
    native=[]
    for page in document.pages:
        matching=[a for a in areas if a['page_number']==page.number]
        if not matching:continue
        native.extend(r for r in page.lines if _ink(r) and any(_inside(r.bbox,a['bbox']) for a in matching))
    actual=[]
    for field in fields:
        if field.get('source')!='native' or not any(field.get('page_number')==a['page_number'] and _inside(field['bbox'],a['bbox']) for a in areas):continue
        if not any(r.page_number==field['page_number'] and _inside(field['bbox'],r.bbox) and _compact(field['text'])==_compact(r.text) for r in native):return None
        actual.append(field)
    expected=_layout(areas[0]['title'],[dict(text=r.text,bbox=list(r.bbox),page_number=r.page_number,source='native') for r in native])
    supplied=_layout(areas[0]['title'],actual)
    if expected is None or supplied is None or expected['panels']!=supplied['panels']:return None
    return supplied

def _owned(value,target,owners):
    named=[m.group(1) for m in _FOREIGN_NAME.finditer(value)]
    for match in _CHINESE_NAME.finditer(value):
        # Naming and explicit local-author framing precede the actor identity;
        # they are not part of a Chinese or mixed-script method name.
        name=re.split(r'(?:本文|本章|本节|我们)(?:采用|使用)|称为|称作|叫作',match.group(1))[-1]
        if not _COMMON_ACTOR.fullmatch(name):named.append(name)
    # Actors retain native row boundaries; an explicit veto may wrap between
    # rows, so also inspect its contiguous ink and ordinary spaced rendering.
    veto_values=(value,_compact(value),re.sub(r'\s+',' ',value))
    return not (any({normalize_label(m.group(1)) for m in _FIG.finditer(v)}-{normalize_label(target.number)}
                   or _DENIED.search(v) or _FOREIGN.search(v) or _EXTERNAL.search(v) for v in veto_values)
                or any(_type(name) is None or (owners is not None and _type(name) not in owners) for name in named))

def _body(context,target,passages,owners=None):
    document=context.get('_document');scopes=context.get('usage_scopes') or context.get('usage_scope_map')
    if document is None or scopes is None:return []
    state=usage_scope_identity(scopes,target)
    if state[0]!='body' or state[1]<0:return []
    areas=[a for values in context['regions'].values() for a in values]
    eligible={}
    for anchors,value in passages:
        if not anchors or any(not _ink(r) or r.role in _BAD or usage_scope_identity(scopes,r)!=state for r in anchors):continue
        for page in document.pages:
            same=[r for r in anchors if r.page_number==page.number]
            if not same:continue
            for row in page.lines:
                if not any(_inside(row.bbox,a.bbox) and _compact(row.text) in _compact(a.text) for a in same):continue
                if (not _ink(row) or row.role in _BAD or usage_scope_identity(scopes,row)!=state
                    or (row.page_number,row.bbox) in context.get('caption_keys',set())
                    or any(a['page_number']==row.page_number and _inside(row.bbox,a['bbox']) for a in areas)):continue
                eligible[row.page_number,row.bbox,row.text]=row
    ordered=sorted(eligible.values(),key=lambda r:(r.page_number,r.bbox[1],r.bbox[0]))
    # A citation font can lower a native row's recorded font_size even while
    # its Chinese body ink has the same height as the preceding line. Recover
    # only that original unfinished line's geometrically adjacent continuation.
    for prev in list(ordered):
        if not re.search(r'[\u4e00-\u9fff]$',prev.text.strip()):continue
        page=next((p for p in document.pages if p.number==prev.page_number),None)
        if page is None:continue
        following=[r for r in page.lines if 0<r.bbox[1]-prev.bbox[1]<=32 and abs(r.bbox[0]-prev.bbox[0])<1]
        if not following:continue
        row=min(following,key=lambda r:r.bbox[1])
        if (not _ink(row) or row.role in _BAD or row.bold!=prev.bold or row.font_size>prev.font_size
                or not re.match(r'[\u4e00-\u9fff]',row.text.strip())
                or row.bbox[3]-row.bbox[1]<(prev.bbox[3]-prev.bbox[1])*.9
                or usage_scope_identity(scopes,row)!=state
                or (row.page_number,row.bbox) in context.get('caption_keys',set())
                or any(a['page_number']==row.page_number and _inside(row.bbox,a['bbox']) for a in areas)):continue
        eligible[row.page_number,row.bbox,row.text]=row
    ordered=sorted(eligible.values(),key=lambda r:(r.page_number,r.bbox[1],r.bbox[0]))
    paragraphs=[]
    for row in ordered:
        if not paragraphs:paragraphs.append([row]);continue
        prev=paragraphs[-1][-1]
        same=(row.page_number==prev.page_number and 0<=row.bbox[1]-prev.bbox[1]<=32
              and row.bbox[0]-prev.bbox[0]<1.5*row.font_size)
        continuation=(row.page_number==prev.page_number+1 and prev.bbox[3]>=prev.page_height*.78
                      and prev.bbox[2]>=prev.page_width*.75 and row.bbox[1]<=row.page_height*.45
                      and re.search(r'[\u4e00-\u9fff]$',prev.text.strip()) and re.match(r'[\u4e00-\u9fff]',row.text.strip()))
        if same or continuation:paragraphs[-1].append(row)
        else:paragraphs.append([row])
    # A genuine native continuation carries its own ownership and denial ink;
    # it cannot bypass the checks applied to the prepared paragraph anchors.
    # Keep real ink row boundaries when identifying an operation's actor.
    # Compact joining is useful for wrapped definitions, but would otherwise
    # manufacture names from an unfinished row and the next row's pronoun.
    return [(rows,_compact(''.join(r.text for r in rows))) for rows in paragraphs
            if _owned('\n'.join(r.text for r in rows),target,owners)]

def _sections(value):
    matches=[]
    for name,pattern in _ALIASES.items():
        for match in re.finditer(pattern,_text(value)):
            # Argument/comparison mentions do not change the operation subject.
            if re.search(r'针对$|与$|媲美$|结合了$|立方体$|背景$',value[max(0,match.start()-3):match.start()]):continue
            if name=='mesh' and re.match(r'单元|划分',value[match.end():]):continue
            matches.append((match.start(),match.end(),name))
    matches.sort();answer=[]
    for pos,end,name in matches:
        stop=next((s for s,e,k in matches if s>=end and k!=name),len(value))
        answer.append((name,value[pos:stop]))
    return answer

def _defined(identity,value):
    if '+' in identity:
        kinds=identity.split('+');other=next(k for k in kinds if k!='pipeline')
        pattern='(?:'+_ALIASES['pipeline']+r')\+(?:'+_ALIASES[other]+')|(?:'+_ALIASES[other]+r')\+(?:'+_ALIASES['pipeline']+')'
        if not re.search(pattern,value):return False
        common=(r'按层.{0,12}拆分.{0,12}层组',r'层组间.{0,8}(?:并行执行|协同推理)')
        specific=(r'每个层组内部',r'层参数.{0,8}张量并行拆分') if other=='tensor' else (r'针对每个层组',r'输入数据.{0,8}小批量拆分',r'数据并行.{0,12}层组内')
        return all(re.search(p,value) for p in common+specific)
    # Hybrid definitions cannot supply a missing pure-type definition.
    if re.search(r'(?:流水线并行|pipelineparallel)\+(?:张量并行|数据并行|tensorparallel|dataparallel)',value):return False
    owned=' '.join(v for kind,v in _sections(value) if kind==identity)
    return all(re.search(pattern,owned) for pattern in _OPS[identity])

def comparison_relation_proposals(context,groups,nearby,fields=None):
    actual=context['native_fields'] if fields is None else fields;answer=[]
    scopes=context.get('usage_scopes') or context.get('usage_scope_map')
    if scopes is None:return []
    for ordinal,areas in context['regions'].items():
        target=groups[ordinal][0];state=usage_scope_identity(scopes,target)
        if state[0]!='body' or state[1]<0:continue
        topology=_physical(context,areas,actual.get(ordinal,[]))
        if topology is None:continue
        # An overlapping independently captioned region cannot be selected by
        # the same prose, even when its printed type list happens to be equal.
        if any(other!=ordinal and usage_scope_identity(scopes,groups[other][0])==state and any(
                a['page_number']==b['page_number'] and min(a['bbox'][2],b['bbox'][2])>max(a['bbox'][0],b['bbox'][0])
                and min(a['bbox'][3],b['bbox'][3])>max(a['bbox'][1],b['bbox'][1]) for a in areas for b in values)
                for other,values in context['regions'].items()):continue
        owners={kind for panel in topology['panels'] for kind in panel['identity'].split('+')}
        paragraphs=_body(context,target,nearby(ordinal),owners);proof=[];operations=[]
        for panel in topology['panels']:
            found=[(rows,value) for rows,value in paragraphs if _defined(panel['identity'],value)]
            if not found:break
            rows,value=found[0];proof.extend(rows);operations.append(dict(identity=panel['identity'],body=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text) for r in rows]))
        else:
            topology['independent_definitions']=operations
            answer.append((ordinal,'comparison_complete_typed_relations',list({(r.page_number,r.bbox,r.text):r for r in proof}.values()),topology))
    return [entry for entry in answer if not any(other[0]!=entry[0] and {(r.page_number,r.bbox,r.text) for r in entry[2]}&{(r.page_number,r.bbox,r.text) for r in other[2]} for other in answer)]
