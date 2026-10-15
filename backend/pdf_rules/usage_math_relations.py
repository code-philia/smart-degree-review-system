"""Three bounded mathematical diagrams, bound to independent original ink.

No PDF edits, OCR, names as evidence, source IDs, or mutable index caches.
Only a complete same-page physical profile and affirmative relational prose
with the corresponding exact mathematical assignments supply usage evidence.
"""
import re
from .usage_text_cache import normalize_text
from .numbering import normalize_label,is_toc_line
from .usage_scope import is_body_usage_scope

def compact(text):
    text=normalize_text(text)
    return re.sub(r'[\s\x00-\x1f\uf8ee-\uf8ff]','',text).replace('：',':').casefold()

def inside(a,b):return b[0]<=a[0]<a[2]<=b[2] and b[1]<=a[1]<a[3]<=b[3]

def camera_equations(fields):
    """Read three exact signed assignments and actual fraction denominators."""
    if not fields or len({f['page_number'] for f in fields})!=1:return False
    def neighbors(f):
        b=f['bbox']
        return [g for g in fields if g is not f and abs(g['bbox'][1]-b[1])<=27
                and b[0]-3<=g['bbox'][0]<=b[2]+45]
    def denominator(numerator,near):
        b=numerator['bbox']
        return any(compact(g['text']) in {'2','2,','2)','2),'} and b[2]-18<=g['bbox'][0]<=b[2]+10
                   and b[1]+4<=g['bbox'][1]<=b[3]+18 for g in near)
    x=False;y=False;z=False
    for f in fields:
        text=compact(f['text']);near=neighbors(f)
        if re.fullmatch(r'x=u-w(?:/2[,;.]?)?',text):
            x=('/2' in text or denominator(f,near)) or x
        if re.fullmatch(r'y=-\(v-h(?:/2\)[,;.]?)?',text):
            y=('/2' in text or denominator(f,near)) or y
        if re.fullmatch(r'y=-',text):
            numerators=[g for g in near if compact(g['text'])=='v-h']
            y=any(denominator(g,fields) for g in numerators) or y
        if re.fullmatch(r'z=-f[.,;]?',text):z=True
    return x and y and z

def observed_profile(fields,title):
    if not fields or len({f['page_number'] for f in fields})!=1:return None
    words=[compact(f['text']) for f in fields];joined=' '.join(words)
    # Four disjoint channels have a fixed physical left-to-right high/low
    # ordering. Numeric examples and unrelated color names cannot satisfy it.
    channels=[]
    for f in fields:
        m=re.fullmatch(r'([rgba])\[(\d+):(\d+)\]',compact(f['text']))
        if m:channels.append((m.group(1),int(m[2]),int(m[3]),f))
    if channels:
        unique={c[:3]:c for c in channels}
        ordered=sorted(unique.values(),key=lambda c:c[3]['bbox'][0])
        expected=[('r',31,24),('g',23,16),('b',15,8),('a',7,0)]
        if (re.search(r'位域|bit.?field',title,re.I) and re.search(r'体素|voxel|RGBA',title,re.I)
                and [c[:3] for c in ordered]==expected and max(c[3]['bbox'][1] for c in ordered)-min(c[3]['bbox'][1] for c in ordered)<12):
            return ('rgba_bitfield',tuple(expected))
        return None
    if re.search(r'相机|camera',title,re.I) and all(w in joined for w in ('世界坐标系','图像平面','相机坐标系')) and camera_equations(fields):
        uv=any(re.fullmatch(r'\(u,v\)',w) for w in words)
        if uv:return ('perspective_coordinate_map',('world','image','camera','x=u-W/2','y=-(v-H/2)','z=-f'))
    # A time sequence sits above two aligned nonnegative count rows. The
    # legends align with those two rows and assign outgoing above incoming.
    names={w:f for w,f in zip(words,fields)}
    duration=next((f for f in fields if normalize_text(f['text']).strip()=='T'),None)
    if duration and re.search(r'时域|time.?domain',title,re.I) and all(w in names for w in ('torcell','序列','s','t','l','发送(上行)','接收(下行)','时域表征')):
        up=names['发送(上行)'];down=names['接收(下行)'];digits=[f for f in fields if re.fullmatch(r'\d+',compact(f['text']))]
        def row(legend):return sorted([f for f in digits if abs(f['bbox'][1]-legend['bbox'][1])<=8 and f['bbox'][2]<legend['bbox'][0]],key=lambda f:f['bbox'][0])
        a=row(up);b=row(down)
        if (up['bbox'][1]+12<down['bbox'][1] and len(a)==len(b)>=3
                and all(abs(x['bbox'][0]-y['bbox'][0])<=3 for x,y in zip(a,b))
                and names['torcell']['bbox'][3]<names['l']['bbox'][1]<up['bbox'][1]
                and names['s']['bbox'][3]<up['bbox'][1] and duration['bbox'][3]<up['bbox'][1]):
            return ('directional_window_counts',('cell_sequence','window_s','duration_T','columns_L','row1_up','row2_down'))
    return None

def prose_matches(profile,text,math_fields):
    value=compact(text);kind=profile[0]
    # A negated decisive transformation cannot supply a use relation.
    if re.search(r'(?:不(?:会|再|进行)?|未|无需|并非).{0,5}(?:打包|统计|转换|映射|划分|聚合|组合)',value):return False
    if kind=='rgba_bitfield':
        if not all(re.search(p,value) for p in (r'体素|voxel',r'rgba',r'打包(?:为|成)(?:一个)?32位整数',r'4字节')):return False
        for channel,high,low in profile[1]:
            if not re.search(r'bit'+str(low)+r'-'+str(high)+r':[^。；;]{0,24}\('+channel+r',8-bit\)',value):return False
        return bool(re.search(r'低8位到高8位.{0,18}a,b,g,r',value))
    if kind=='perspective_coordinate_map':
        return (all(re.search(p,value) for p in (r'像素坐标转换',r'图像中心为原点',r'归一化相机坐标',r'相机光心的射线',r'世界坐标到图像坐标.{0,8}(?:完整)?映射',r'内参和外参'))
                and camera_equations(math_fields))
    if kind=='directional_window_counts':
        required=(r'torcell序列.{0,12}时间片划分',r'每个时间片内分别统计上行与下行torcell的数量',
                  r'组合为矩阵形式',r'时间片数量为l',r's=t',r'm[∈=]r2×l',
                  r'区间.{0,12}j-1.{0,7}s,.{0,5}js',r'i=1时表征上行流量',r'i=2时表征下行流量')
        divided=False
        for f in math_fields:
            text=compact(f['text'])
            if re.search(r's=t/l(?:[。.,;]|$)',text):divided=True
            if not re.search(r's=t$',text):continue
            b=f['bbox']
            if any(compact(g['text']) in {'l','l。','l.'} and g['page_number']==f['page_number']
                   and b[2]-18<=g['bbox'][0]<=b[2]+15 and b[1]<=g['bbox'][1]<=b[3]+18 for g in math_fields):divided=True
        return divided and all(re.search(p,value) for p in required)
    return False

def candidate_prose(title,text):
    """Cheap investigation only: three roles and their actual operation."""
    value=compact(text)
    if re.search(r'相机模型|camera\s+model',title,re.I):
        return all(w in value for w in ('像素','世界坐标','相机光心','射线','映射'))
    if re.search(r'位域|bit.?field',title,re.I):return all(w in value for w in ('rgba','32位','打包','通道'))
    if re.search(r'时域|time.?domain',title,re.I):return all(w in value for w in ('torcell','时间片','上行','下行','矩阵','统计'))
    return False

def math_relation_evidence(index,groups,regions,fields,context):
    from . import usage_figure_evidence as F
    # This bounded branch uses native assignments only. An external OCR dict
    # cannot replace an unobserved channel, coordinate or directional role.
    fields=context['native_fields']
    profiles={i:observed_profile(fields.get(i,[]),areas[0]['title']) for i,areas in regions.items()}
    result={};all_areas=[a for values in regions.values() for a in values]
    pages={p.number:p for p in index.document.pages}
    for i,profile in profiles.items():
        if profile is None:continue
        target=groups[i][0];page_number=target.line.page_number
        if any(j!=i and p==profile and abs(groups[j][0].line.page_number-page_number)<=1
               and F._same_content_domain(context,target,[groups[j][0].line]) for j,p in profiles.items()):continue
        area=regions[i][0];chosen={}
        # Exact same-page independent paragraphs. A caption or foreign figure
        # reference in the owning context never becomes a mathematical proof.
        headings=[r for r in pages[page_number].lines if re.match(r'^第\s*[一二三四五六七八九十百\d]+\s*章|^chapter\s+[\divx]+\b',normalize_text(r.text),re.I)
                  and (r.bold or r.font_size and r.font_size>=14) and len(r.text)<80]
        center=(area['bbox'][1]+area['bbox'][3])/2
        for rows in context['body_passages']:
            if any(r.page_number!=page_number for r in rows) or not F._same_content_domain(context,target,rows):continue
            if any(min(center,min(r.bbox[1] for r in rows))<=h.bbox[1]<=max(center,max(r.bbox[3] for r in rows)) for h in headings):continue
            if min(abs(r.bbox[1]-area['bbox'][3]) for r in rows)>370 and min(abs(r.bbox[3]-area['bbox'][1]) for r in rows)>370:continue
            text=' '.join(r.text for r in rows)
            if not re.search(r'像素|相机|世界坐标|体素|RGBA|Bit\s*\d|Tor\s*Cell|时间片|表征|流量|矩阵',text,re.I):continue
            refs={normalize_label(m.group(1)) for m in F._REF.finditer(normalize_text(text))}
            if not F._references_allow(refs,target.number):continue
            chosen.update({F._key(r):r for r in rows})
        rows=sorted(chosen.values(),key=lambda r:(r.bbox[1],r.bbox[0]));body=' '.join(r.text for r in rows)
        if not rows:continue
        title=area['title'];owner=F._named_figure_identity(title) or F._schematic_named_owner(title)
        if owner and not F._structured_owner_in_text(owner,body):continue
        actors=re.findall(r'(?<![A-Za-z0-9_-])([A-Za-z][A-Za-z0-9_-]{2,})\s*(?:模型|网络|model\b|network\b)',normalize_text(body),re.I)
        actors+=re.findall(r'(?:^|[。；;])\s*([A-Za-z][A-Za-z0-9_-]{2,})\s*(?:采用|使用|通过|将|uses?\b|maps?\b)',normalize_text(body),re.I)
        graphic=' '.join([title]+[f['text'] for f in fields.get(i,[])])
        if any(not F._structured_owner_in_text(name,graphic) for name in actors):continue
        # Formula fragments retain their original page/bbox. They may supplement
        # genuine selected prose, but can never initiate a use by themselves.
        low=min(r.bbox[1] for r in rows)-15;high=max(r.bbox[3] for r in rows)+20
        native=[]
        for r in pages[page_number].lines:
            if (r.source!='native' or r.bold or F._key(r) in context['caption_keys'] or is_toc_line(r.text)
                    or not is_body_usage_scope(context['usage_scope_map'],r) or not F._same_content_domain(context,target,[r])
                    or not low<=r.bbox[1]<=high or any(a['page_number']==page_number and inside(r.bbox,a['bbox']) for a in all_areas)):continue
            if any(inside(r.bbox,b) and b[3]-b[1]<pages[page_number].height*.7 for b in (*pages[page_number].images,*pages[page_number].tables)):continue
            refs={normalize_label(m.group(1)) for m in F._REF.finditer(normalize_text(r.text))}
            if not F._references_allow(refs,target.number):native=[];break
            native.append(dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text,source=r.source))
        if not native or not prose_matches(profile,body,native):continue
        result[i]=dict(evidence_kind='independent_mathematical_assignments',group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text) for l in groups[i]],
            full_title=title,graphic_regions=regions[i],graphic_fields=fields.get(i,[]),matched_features=[profile[0],*[str(v) for v in profile[1]]],
            body_evidence=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text,source=r.source) for r in rows],formula_evidence=native,
            uniqueness_reason='Observed signed coordinate assignments, ordered channel bit intervals, or aligned direction-count rows bind their corresponding affirmative independent mathematical operations on the same physical page/chapter/epoch. All physical groups compete; illustrative matrix cell values are not claimed as separately restated.')
    return result

def math_native_candidates(groups,regions,native_fields):
    """Only complete native profiles request independent mathematical review."""
    return {i for i,areas in regions.items() if areas and i<len(groups)
            and observed_profile(native_fields.get(i,[]),areas[0]['title']) is not None}
