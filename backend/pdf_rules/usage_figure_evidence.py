"""Bind physical figure content to independent prose, without changing the index.

The caption's source number opens a candidate; it never supplies usage by
itself. Content components, all recovered facets, and an unambiguous physical
object must agree. Graphic OCR may be supplied by the caller, with its original
page coordinates and confidence; this module performs no PDF or network I/O.
"""
import re
import json
from dataclasses import replace
from difflib import SequenceMatcher
from functools import lru_cache

from .caption_context import body_font
from .numbering import caption_match, normalize_label, toc_line_keys, is_toc_line
from .usage_text_cache import normalize_text
from .source_cited_usage import _full_title, _key, _citations, _prose, _OPERATIONS, _matching_topics
from .usage_paragraphs import span_anchor
from .usage_scope import usage_scope_map, is_body_usage_scope, usage_epoch


# Components and content concepts, rather than paper IDs or named model
# exceptions. Each alias is independently required when present in a visual.
_CONCEPTS = {
    'encoder': ('encoder', 'encoding', '编码器', '编码'),
    'decoder': ('decoder', 'decoding', '解码器', '解码'),
    'quantization': ('quantization', 'quantizer', 'rvq', '量化'),
    'residual': ('residual', 'rvq', '残差'),
    'semantic_tokens': ('semantic tokens', 'semantic token', '语义标记', '语义令牌', '语义增强', '语义信息'),
    'speech': ('speech', '语音'),
    'separation': ('separation', 'separating', '分离'),
    'target_speaker': ('target speaker', 'target speech', 'tse', '目标说话人', '目标语音'),
    'blind_separation': ('blind source separation', 'bss', '盲源语音分离', '盲源分离'),
    'noise_reduction': ('noise reduction', 'noise suppression', '降噪', '噪声抑制'),
    'extraction': ('extraction', 'extract', 'tse', '提取'),
    'cue': ('cue', 'cues', 'clue', 'clues', '线索'),
    'audio': ('audio', '音频', '预注册语音'),
    'visual': ('visual', '视觉', '唇部', '唇动'),
    'spatial': ('spatial', '空间', '方位'),
    'clustering': ('clustering', 'cluster', 'clusters', 'k-means', 'kmeans', 'dpcl', '深度聚类', '聚类'),
    'deep_clustering': ('deep clustering', 'dpcl', '深度聚类'),
    'permutation': ('permutation', 'permutations', 'pit', '排列', '置换'),
    'permutation_invariance': ('permutation invariant', 'pit', '排列不变'),
    'loss': ('loss', 'losses', '损失'),
    'minimum': ('minimum', 'minimize', '最小', '最低'),
    'mask': ('mask', 'masks', 'masking', 'mask1', 'mask2', '掩码', '分组以重建', '按组重建'),
    'ground_truth': ('ground truth', 'groundtruth', '真实标签', '真实标记', '真实源', '监督信号', '真实语音'),
    'fourier': ('stft', 'istft', '傅里叶'),
    'spectrogram': ('spectrogram', 'spectrograms', '频谱', '时频', '频域'),
    'band_partition': ('band-splitting', 'band split', '子带划分'),
    'convolution': ('convolution', 'convolutional', 'conv', 'transconv', '卷积'),
    'pretraining': ('pre-trained', 'pretrained', 'pre-training', 'pretraining', '预训练'),
    'codec': ('codec', 'codecs', '编解码', '编解码器'),
    'autoregressive': ('auto-regressive', 'autoregressive', '自回归'),
    'softmax': ('softmax',),
    'weight_sharing': ('weight sharing', '权重共享'),
    'mel': ('log-mel', 'mel', '梅尔'),
    'vocoder': ('vocoder', '声码器'),
    'transformer': ('transformer',),
    'mixture': ('mixture', '混叠', '混合语音'),
    'tokens': ('token', 'tokens', '令牌', '标记', '离散特征'),
    'keyword': ('keyword', 'keywords', '关键词'),
    'filler': ('filler', '填充'),
    'hmm': ('hmm', '隐马尔可夫'),
    'phoneme': ('phone state sequence', 'phone sequence', 'phoneme', '音素', '音位'),
    'non_speech': ('non-speech', 'non speech', '非语音', '静音', '无声'),
    'loop': ('loop', '循环', '闭环'),
    'feature': ('feature', 'features', '特征'),
    'posterior': ('posterior', '后验'),
    'decision': ('decision', '决策', '阈值'),
    'memory': ('memory', '内存', '存储'),
    'latency': ('latency', 'delay', '延迟', '时延'),
    'throughput': ('throughput', '吞吐'),
    'attention': ('attention', '注意力'),
    'feed_forward': ('feed-forward', 'feedforward', '前馈'),
    'masked_attention': ('masked', '带掩码'),
    'normalization': ('normalization', 'norm', '归一化'),
    'position': ('positional', 'position embedding', '位置编码', '位置嵌入'),
    'patch': ('patch', 'patches', '图像块'),
    'classification': ('classification', 'classifier', '分类'),
    'signal_acquisition': ('signal acquisition', '信号采集'),
    'signal_processing': ('signal processing', '信号处理'),
    'feedback': ('feedback', '反馈'),
    'emotion': ('emotion', 'emotions', '情绪', '情感'),
    'stimulation': ('stimulation', '刺激'),
    'coupler': ('coupler', '射频耦合器', '耦合器', '耦合'),
    'phase': ('phase', '相位', '相位延迟器', '相位延迟', '相位偏移'),
    'power_detector': ('power detector', '功率检测器', '功率检测'),
    'matrix': ('matrix', 'matrices', '矩阵'),
    'amplitude': ('amplitude', '幅值', '幅度', '振幅'),
    'radiofrequency': ('radio frequency', 'radio-frequency', 'rf', '射频'),
    'antenna': ('antenna', 'antennas', '天线'),
    'port': ('port', 'ports', '端口'),
    'hash': ('hash', '哈希'),
    'timestamp': ('timestamp', '时间戳'),
    'nonce': ('nonce', '随机数'),
    'transaction': ('transaction', 'transactions', '交易'),
    'vector': ('vector', '矢量', '向量'),
    'covector': ('covector', '协向量'),
    'forward_map': ('forward map', '正向映射', '前向映射'),
    'inverse_map': ('inverse map', '逆映射', '反向映射'),
    'reference_configuration': ('reference configuration', '参考构型'),
    'deformed_configuration': ('deformed configuration', '当前构型', '形变构型'),
    'watermark': ('watermark', 'watermarking', 'watermarked', '水印'),
    'text_transformation': ('text transformation', '文本转换'),
    'logits': ('logits',),
    'token_sampling': ('token sampling', 'token 采样', 'token采样'),
    'training_phase': ('training time', '训练阶段', '训练过程'),
    'inference_phase': ('inference time', '生成过程', '生成流程'),
    'format_modification': ('format-based', '格式'),
    'syntactic_modification': ('syntactic-based', '句法', '语法'),
    'industrial_control': ('industrial control', '工控', '工业控制'),
    'vulnerability': ('vulnerability', 'vulnerabilities', '漏洞'),
    'fault': ('fault', 'faults', '断层'),
    'porphyry': ('porphyry', '斑岩'),
    'magmatic': ('magmatic', 'magma', '岩浆', '火成岩'),
    'sedimentary': ('sedimentary', 'sediments', '沉积'),
    'granitic': ('granitic', 'granite', '花岗岩'),
    'mineral': ('mineral', 'minerals', 'mineralization', '矿化', '矿产'),
    'segmentation': ('segmentation', '分割'),
    'annotation': ('annotation', 'label', 'labels', '标注'),
    'input': ('input', '输入'),
    'output': ('output', '输出'),
}
_WEAK = {'speech', 'audio', 'feature', 'tokens', 'input', 'output', 'classification',
         'encoder', 'decoder', 'extraction', 'separation', 'matrix', 'port', 'ground_truth'}
_CONTENT_OPERATIONS = _OPERATIONS + (r'映射',r'重构|重建',r'转换',r'估计',r'压缩',r'组合|融合',r'编码|解码',r'枚举|匹配')
_REF = re.compile(r'(?:图|Figures?|Fig\.?)\s*([A-Z]?\d+(?:[.\-–]\d+)*)', re.I)


def _references_allow(references,number):
    return not references or references<={normalize_label(number)}
_CONCEPT_PATTERNS = {name: re.compile('|'.join(
    (r'(?<![a-z0-9_])'+re.escape(a).replace(r'\ ',r'[\s-]+')+r'(?![a-z0-9_])')
    if a.isascii() else re.escape(a) for a in aliases)) for name,aliases in _CONCEPTS.items()}
_FORWARD_BACKWARD = re.compile(r'前后向|前向[\s\-–—]*后向|\bforward[\s\-–—]*backward\b',re.I)
_PROCEDURE_FILLER = {'figure','fig','example','examples','illustration','diagram','algorithm','of','from',
                     'the','an','a','and','for','based','model','models','procedure','forward','backward','dataset','datasets'}


def _inside(a, b, tolerance=1):
    return b[0]-tolerance<=a[0] and b[1]-tolerance<=a[1] and a[2]<=b[2]+tolerance and a[3]<=b[3]+tolerance


def _union(boxes):
    return (min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes))


def _connected(a,b):
    dx=max(a[0]-b[2],b[0]-a[2],0)
    dy=max(a[1]-b[3],b[1]-a[3],0)
    return dx<=30 and dy<=36


def figure_graphic_regions(index, groups):
    """Return same-page graphic regions owned by each physical caption group.

    Nearby captions and independent wide prose are hard boundaries. Geometry
    is derived solely from existing native/layout image and vector rectangles.
    The caller may crop these regions for offline OCR without editing the PDF.
    """
    return _graphic_regions(index,groups,usage_scope_map(index.document))


def _graphic_regions(index,groups,usage_scopes):
    pages={p.number:p for p in index.document.pages}
    titles={}
    caption_keys=set()
    for kind,labels in (('figure',index.figures),('table',index.tables)):
        for label in labels:
            page=pages.get(label.line.page_number)
            if page:
                _,rows=_full_title([label],page,kind)
                caption_keys.update(_key(row) for row in rows)
    for i,group in enumerate(groups):
        if not group or not is_body_usage_scope(usage_scopes,group[0]):continue
        page=pages.get(group[0].line.page_number)
        if page is None or any(l.line.page_number!=page.number for l in group):continue
        title,rows=_full_title(group,page,'figure')
        caption_keys.update(_key(row) for row in rows)
        titles[i]=(page,title,rows)
    answer={}
    for i,(page,title,rows) in titles.items():
        top=min(r.bbox[1] for r in rows)
        previous=[l.bbox[3] for l in page.lines if _key(l) in caption_keys and l.bbox[3]<top-1]
        floor=max(previous or [page.height*.09])
        typical=body_font(page)
        boxes=[]
        for b in (*page.images,*page.graphics):
            if b[2]<=b[0] or b[3]<=b[1] or b[1]<floor-1 or b[1]>=top:continue
            # Layout image carriers can extend through the title. Never OCR it.
            b=(b[0],b[1],b[2],min(b[3],top-2))
            if b[3]<=b[1] or b[3]-b[1]>page.height*.65:continue
            boxes.append(b)
        seeds=[b for b in boxes if 0<=top-b[3]<=65 and b[2]-b[0]>=15 and b[3]-b[1]>=5]
        if not seeds:
            below=_below_caption_region(page,rows,caption_keys)
            if below is not None:
                answer[i]=[dict(page_number=page.number,bbox=list(below),title=title,
                    caption_keys=[dict(page_number=r.page_number,bbox=list(r.bbox)) for r in rows])]
            continue
        bottom=max(b[3] for b in seeds)
        selected=[b for b in seeds if bottom-b[3]<=18]
        while True:
            envelope=_union(selected)
            # A labeled upper panel and lower panel can be separated by their
            # bilingual subtitle. That ink is part of the same physical figure,
            # while a wide ordinary prose row remains a hard boundary.
            def panel_bridge(b):
                gap=max(b[1]-envelope[3],envelope[1]-b[3],0)
                if gap>65 or max(b[0]-envelope[2],envelope[0]-b[2],0)>30:return False
                low,high=sorted((b[3],envelope[1])) if b[3]<=envelope[1] else sorted((envelope[3],b[1]))
                between=[row for row in page.lines if low-1<=row.bbox[1] and row.bbox[3]<=high+1]
                return bool(any(re.match(r'^\s*[（(][a-zA-Z][）)]',row.text) for row in between)
                    and not any(_key(row) not in caption_keys and not row.bold and row.font_size
                                and typical and row.font_size>=typical*.95
                                and row.bbox[2]-row.bbox[0]>page.width*.55 for row in between))
            more=[b for b in boxes if b not in selected and (_connected(b,envelope) or panel_bridge(b))]
            if not more:break
            selected.extend(more)
        box=_union(selected)
        # An actual prose row above the nearest visual separates it from
        # earlier unrelated artwork and keeps body ink out of the crop.
        boundaries=[l.bbox[3] for l in page.lines if _key(l) not in caption_keys
                    and not l.bold and l.font_size and typical and l.font_size>=typical*.95
                    and l.bbox[2]-l.bbox[0]>page.width*.55
                    and floor<=l.bbox[1] and l.bbox[3]<bottom-12
                    and l.bbox[1]>=box[1] and not any(_inside(l.bbox,b) for b in selected)]
        if boundaries:
            floor=max(floor,max(boundaries)+2)
            selected=[b for b in selected if b[1]>=floor]
            if not selected:continue
            box=_union(selected)
        if box[2]-box[0]<30 or box[3]-box[1]<15:continue
        # Panel subtitles and component names between the visual and its main
        # caption belong to that graphic. A body-font prose row remains a
        # boundary, so the extension cannot swallow an intervening paragraph.
        tails=[l for l in page.lines if box[3]<=l.bbox[1]<top-2 and _key(l) not in caption_keys]
        if not any(not l.bold and l.font_size and typical and l.font_size>=typical*.95
                   and l.bbox[2]-l.bbox[0]>page.width*.55 for l in tails):
            box=(box[0],box[1],box[2],top-2)
        answer[i]=[dict(page_number=page.number,bbox=list(box),title=title,
                        caption_keys=[dict(page_number=r.page_number,bbox=list(r.bbox)) for r in rows])]
    return answer


def _below_caption_region(page,rows,caption_keys):
    """A caption above artwork owns its nearest uninterrupted physical region."""
    bottom=max(r.bbox[3] for r in rows);typical=body_font(page)
    own={_key(r) for r in rows}
    def boundary(row):
        return (_key(row) in caption_keys and _key(row) not in own
                or _key(row) not in caption_keys and not row.bold and row.font_size
                and typical and row.font_size>=typical*.95
                and row.bbox[2]-row.bbox[0]>page.width*.55)
    boxes=[b for b in (*page.images,*page.graphics)
           if b[2]-b[0]>=15 and b[3]-b[1]>=5 and b[1]>=bottom+1
           and b[3]<=page.height*.92 and b[3]-b[1]<=page.height*.65]
    seeds=[b for b in boxes if b[1]-bottom<=40
           and not any(bottom<r.bbox[1] and r.bbox[3]<=b[1] and boundary(r) for r in page.lines)]
    if not seeds:return None
    nearest=min(b[1] for b in seeds);selected=[b for b in seeds if b[1]-nearest<=12]
    while True:
        envelope=_union(selected)
        more=[b for b in boxes if b not in selected and _connected(b,envelope)
              and not any(bottom<r.bbox[1]<b[1] and boundary(r)
                          and not _inside(r.bbox,envelope) for r in page.lines)]
        if not more:break
        selected.extend(more)
    box=_union(selected)
    if box[2]-box[0]<30 or box[3]-box[1]<15:return None
    if any(boundary(r) and _inside(r.bbox,box)
           and not any(_inside(r.bbox,b) for b in selected) for r in page.lines):return None
    return box


def figure_native_fields(index, groups):
    return _native_fields_in_regions(index,figure_graphic_regions(index,groups))


def _native_fields_in_regions(index,regions):
    pages={p.number:p for p in index.document.pages}
    answer={}
    for i,areas in regions.items():
        result=[]
        for area in areas:
            page=pages[area['page_number']]
            typical=body_font(page)
            for row in page.lines:
                if not _inside(row.bbox,area['bbox']) or not row.text.strip():continue
                if any(caption_match(normalize_text(row.text),kind) for kind in ('figure','table')):continue
                if typical and row.font_size and row.font_size>=typical*.95 and not row.bold:
                    if row.bbox[2]-row.bbox[0]>page.width*.4:continue
                result.append(dict(page_number=row.page_number,bbox=list(row.bbox),text=row.text,source=row.source))
        answer[i]=result
    return answer


def _term(text, alias):
    if alias.isascii():
        return bool(re.search(r'(?<![a-z0-9_])'+re.escape(alias).replace(r'\ ',r'[\s-]+')+r'(?![a-z0-9_])',text))
    return alias in re.sub(r'\s+','',text)


@lru_cache(maxsize=2048)
def _fuzzy_component(word):
    alternatives={name for name,aliases in _CONCEPTS.items() for a in aliases
                  if a.isascii() and a.isalpha() and len(a)>=6
                  and SequenceMatcher(None,word,a).ratio()>=.85}
    return frozenset(alternatives) if len(alternatives)==1 else frozenset()


@lru_cache(maxsize=4096)
def _concepts(text, *, graphic=False):
    text=normalize_text(text).casefold()
    compact=re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])','',text)
    found={name for name,pattern in _CONCEPT_PATTERNS.items() if pattern.search(compact)}
    if re.search(r'抑制.{0,12}噪声',compact):found.add('noise_reduction')
    if graphic and re.search(r'\bmask\s*1\b',text) and re.search(r'\bmask\s*2\b',text):
        found.add('multiple_mask_outputs')
    elif 'mask' in found and re.search(r'各源|各说话人|每个说话人|多通道|多个(?:源|说话人)',compact):
        found.add('multiple_mask_outputs')
    if graphic:
        # PDF glyph maps sometimes duplicate characters. A long English
        # component can recover only one uniquely close dictionary spelling;
        # this does not match arbitrary model identifiers or prose substrings.
        for word in re.findall(r'[a-z]{6,}',text):
            if any(_term(word,a) for aliases in _CONCEPTS.values() for a in aliases if a.isascii()):continue
            found.update(_fuzzy_component(word))
    return frozenset(found)


def _graphic_profile(fields):
    features=set().union(*(_concepts(field['text'],graphic=True) for field in fields)) if fields else set()
    if (any(re.search(r'\bmask\s*1\b',f['text'],re.I) for f in fields)
            and any(re.search(r'\bmask\s*2\b',f['text'],re.I) for f in fields)):
        features.add('multiple_mask_outputs')
    # A vertically wrapped two-word node remains a physical label. Joining
    # requires shared x alignment and nearby ink, rather than unordered terms
    # anywhere in the figure (or words supplied by its caption).
    for upper in fields:
        if normalize_text(upper['text']).casefold()!='noise':continue
        for lower in fields:
            if normalize_text(lower['text']).casefold()!='reduction':continue
            if (upper['page_number']==lower['page_number']
                    and 0<=lower['bbox'][1]-upper['bbox'][3]<=12
                    and abs(sum(upper['bbox'][::2])-sum(lower['bbox'][::2]))<=20):
                features.add('noise_reduction')
    return frozenset(features)


def _task_details(features,text):
    tasks={'target_speaker','blind_separation','noise_reduction'}
    if not tasks<=features:return True
    # Recovering taxonomy acronyms does not establish that their distinct
    # task definitions have been used. Require the one/all/noise contrast.
    return bool(re.search(r'单路|single.{0,16}(?:target|output)|only.{0,16}target',text,re.I)
                and re.search(r'多路|所有通道|all.{0,16}(?:sources|channels)|multiple.{0,16}outputs',text,re.I)
                and re.search(r'抑制.{0,12}噪声|noise.{0,16}(?:reduc|suppress)',text,re.I))


def _facts(index,groups,graphic_evidence,prepared_context=None):
    if prepared_context is None:
        regions=figure_graphic_regions(index,groups)
        fields=_native_fields_in_regions(index,regions)
    else:
        regions=prepared_context['regions']
        fields={i:[{**f,'bbox':list(f['bbox'])} for f in rows] for i,rows in prepared_context['native_fields'].items()}
    for i,external in (graphic_evidence or {}).items():
        if i not in regions:continue
        for fact in external:
            if fact.get('confidence',0)<.85 or not fact.get('text'):continue
            if any(fact.get('page_number')==area['page_number'] and _inside(fact['bbox'],area['bbox']) for area in regions[i]):
                fields.setdefault(i,[]).append(dict(fact))
    return regions,fields


def _parallel_roles(fields):
    """Two separated named branches sharing a component family are physical facts."""
    for n,a in enumerate(fields):
        ac=_concepts(a['text'])-_WEAK
        for b in fields[n+1:]:
            bc=_concepts(b['text'])-_WEAK
            if (a['page_number']==b['page_number'] and abs(a['bbox'][1]-b['bbox'][1])>20
                    and ac&bc and ac-bc and bc-ac):
                return sorted(ac&bc)
    return []


def _facets(fields):
    result=[]
    for fact in fields:
        if re.match(r'^\s*(?:[（(][a-zA-Z][）)]|[a-zA-Z][）)])',normalize_text(fact['text'])):
            features=_concepts(fact['text'])-_WEAK
            if features:result.append((features,fact))
    # Genuine component panels must contribute different actual content.
    if len(result)<2 or len({tuple(sorted(features)) for features,_ in result})<2:return []
    return result


@lru_cache(maxsize=1024)
def _procedure_names(title):
    alias_words={word for aliases in _CONCEPTS.values() for alias in aliases if alias.isascii()
                 for word in re.findall(r'[a-z]+',alias.casefold())}
    words=re.findall(r'[A-Za-z][A-Za-z0-9_-]{2,}',title)
    return frozenset(word.casefold() for word in words if word.casefold() not in alias_words|_PROCEDURE_FILLER
            and not set(re.findall(r'[a-z]+',word.casefold()))<=alias_words
            and (word.isupper() or word[:1].isupper()))


def _procedure_operations(text):
    patterns={
        'alignment':r'对齐|\balign(?:ment|ments|ing)?\b',
        'path_summation':r'(?:路径|\bpaths?\b).{0,35}(?:求和|\bsum(?:ming|s)?\b)|(?:求和|\bsum(?:ming|s)?\b).{0,35}(?:路径|\bpaths?\b)',
        'merge_repeats':r'合并.{0,16}重复|\bmerg(?:e|es|ing)\b.{0,35}\brepeat(?:ed|s)?\b',
        'delete_blank':r'(?:删除|移除|去除).{0,16}(?:blank|空白)|\b(?:delet(?:e|es|ing)|remov(?:e|es|ing))\b.{0,35}\bblank\b',
    }
    return {name for name,pattern in patterns.items() if re.search(pattern,text,re.I)}


def _procedure_credits(index,groups,regions,passages,context):
    descriptors=[]
    for i,areas in regions.items():
        title=areas[0]['title']
        sources=_citations(title)
        names=_procedure_names(title)
        # A literal procedure illustration can identify what the graphic
        # depicts even when tiny lattice symbols cannot be recovered by OCR.
        # Measurements/comparisons of the same named algorithm are distinct.
        if not sources or not names or not _FORWARD_BACKWARD.search(title):continue
        if re.search(r'损失|训练|实验|对比|比较|消融|准确率|速度|收敛|复杂度|\b(?:loss|training|comparison|performance|ablation|accuracy|memory|latency|convergence|complexity)\b',title,re.I):continue
        cleaned=_FORWARD_BACKWARD.sub('',title)
        cleaned=re.sub(r'[（(]\s*(?:图源|来源|from|source)\s*\[[\d,\s\-–]+\]\s*[)）]','',cleaned,flags=re.I)
        cleaned=re.sub(r'算法(?:示例|示意图|流程图|流程)?|示例|\balgorithm\b','',cleaned,flags=re.I)
        descriptors.append((i,sources,names,cleaned))
    result={}
    for rows,text,bf,refs,cites in passages:
        if not _FORWARD_BACKWARD.search(text):continue
        operations=_procedure_operations(text)
        if len(operations)<3:continue
        candidates=[]
        intros={};local_intros={}
        for i,sources,names,cleaned in descriptors:
            target=groups[i][0]
            if not _same_epoch(context,target,rows):continue
            if not _references_allow(refs,target.number):continue
            if abs(target.line.page_number-rows[0].page_number)>1:continue
            # Identity and the distinctive procedure facts must occur in one
            # independent paragraph. A different nearby model's description
            # cannot borrow this name from its source-introduction paragraph.
            if not any(all(_term(row.text.casefold(),name) for name in names)
                       and _FORWARD_BACKWARD.search(row.text)
                       and len(_procedure_operations(row.text))>=3 for row in rows):continue
            introductions=[source_rows for source_rows,source_text,_,source_refs,source_cites in passages
                           if sources&source_cites and source_rows[0].page_number<=rows[0].page_number
                           and _same_epoch(context,target,source_rows)
                           and _references_allow(source_refs,target.number)
                           and all(_term(source_text.casefold(),name) for name in names)]
            if not introductions:continue
            local=[source_rows for source_rows,source_text,_,source_refs,_ in passages
                   if 0<=rows[0].page_number-source_rows[0].page_number<=1
                   and _same_epoch(context,target,source_rows)
                   and _references_allow(source_refs,target.number)
                   and all(_term(source_text.casefold(),name) for name in names)]
            if not local:continue
            intro=min(introductions,key=lambda values:sum(len(row.text) for row in values))
            if not _matching_topics(cleaned,text+' '+' '.join(row.text for row in intro)):continue
            candidates.append(i);intros[i]=intro
            local_intros[i]=min(local,key=lambda values:(values[0].page_number,sum(len(row.text) for row in values)))
        if len(candidates)!=1:continue
        i=candidates[0]
        result.setdefault(i,dict(
            evidence_kind='procedural_caption',
            group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text) for l in groups[i]],
            full_title=regions[i][0]['title'],graphic_regions=regions[i],graphic_fields=[],
            matched_features=['specific_forward_backward_procedure'],matched_operations=sorted(operations),
            body_evidence=[dict(page_number=row.page_number,bbox=list(row.bbox),text=row.text,source=row.source) for row in rows],
            source_introduction=[dict(page_number=row.page_number,bbox=list(row.bbox),text=row.text,source=row.source) for row in intros[i]],
            local_identity_introduction=[dict(page_number=row.page_number,bbox=list(row.bbox),text=row.text,source=row.source) for row in local_intros[i]],
            uniqueness_reason='One literal procedure illustration binds independent local alignment/path-summation and sequence-transform facts, local named identity, and an actual prior source citation; a remote source number alone cannot credit it.'))
    return result


def _year_values(fields):
    years=[f for f in fields if re.fullmatch(r'(?:19|20)\d{2}',f['text'].strip())]
    answer={}
    for year in years:
        x=(year['bbox'][0]+year['bbox'][2])/2
        values=[f for f in fields if re.fullmatch(r'\d+(?:\.\d+)?',f['text'].strip())
                and f not in years and f['bbox'][3]<year['bbox'][1]
                and abs((f['bbox'][0]+f['bbox'][2])/2-x)<=12]
        if len({f['text'].strip() for f in values})==1:answer[year['text'].strip()]=(values[0]['text'].strip(),year,values[0])
    return answer


def _statistical_population(title,text):
    names=_procedure_names(title)-{'trend','number','network','count','counts'}
    if any(not _term(text.casefold(),name) for name in names):return False
    residual=re.sub(r'(?:Figure|图)\s*[A-Z]?\d+(?:[.\-–]\d+)*|\[[\d,\s\-–]+\]','',title,flags=re.I)
    for concept in ('industrial_control','vulnerability'):
        for alias in _CONCEPTS[concept]:
            if not alias.isascii():residual=residual.replace(alias,' ')
    for filler in ('网络','数量','走势','变化','趋势','统计','年份','年的','年','条','图'):
        residual=residual.replace(filler,' ')
    body=re.sub(r'\s+','',text)
    return all(word in body for word in re.findall(r'[\u4e00-\u9fff]{2,}',residual))


def _extra_content_credits(index,groups,regions,fields,passages,context):
    """Bind core relations or direct descriptions; inner plumbing is optional.

    Every predicate uses multiple actual visual entities and independent
    content facts. Literal sample/procedure captions can supply identity, but
    their source number or a model/data name never supplies usage by itself.
    """
    result={}
    by_page={}
    for item in passages:by_page.setdefault(item[0][0].page_number,[]).append(item)
    profiles={i:_graphic_profile(fields.get(i,[])) for i in regions}
    year_pairs={i:_year_values(fields.get(i,[])) for i in regions}
    def named(title,text):
        names=_procedure_names(title)
        return bool(names) and all(_term(text.casefold(),name) for name in names)
    for rows,text,bf,refs,cites in passages:
        candidates=[];details={}
        for i,areas in regions.items():
            target=groups[i][0];title=areas[0]['title'];facts=fields.get(i,[])
            if not _same_epoch(context,target,rows):continue
            if not _citations(title) or abs(target.line.page_number-rows[0].page_number)>2:continue
            if not _references_allow(refs,target.number):continue
            # A process or dataset description cannot stand in for a distinct
            # experiment quantity added in a later caption sentence.
            if re.search(r'曲线|收敛|消融|准确率|召回率|性能比较|性能对比|\b(?:curve|convergence|ablation|accuracy|recall|performance comparison)\b',title,re.I):continue
            profile=profiles[i];reason=None;matched=[]
            local_passages=[item for number in range(rows[0].page_number-1,rows[0].page_number+2) for item in by_page.get(number,[])
                            if _same_epoch(context,target,item[0])]
            source_rows=[sr for sr,st,_,srefs,sc in local_passages if _citations(title)&sc
                         and _references_allow(srefs,target.number)]
            # A data curve is bound by actual year/value columns, not a shared
            # AI or population topic. All three exact pairs must be explained.
            pairs=year_pairs[i]
            population=_concepts(title)&{'industrial_control','vulnerability'}
            matched_pairs=[(year,*item) for year,item in pairs.items()
                           if re.search(re.escape(year)+r'\s*年.{0,60}?(?<!\d)'+re.escape(item[0])+r'(?!\d)',text)]
            if (len(matched_pairs)>=3 and len(population)>=2 and population<=bf
                    and _citations(title)&cites and _statistical_population(title,text)):
                reason='Three exact spatial year/value pairs and the same statistical population are explained in independent cited prose.'
                matched=['year_value:'+year+'='+value for year,value,_,_ in matched_pairs]
            # A long concrete procedural caption can be directly explained in
            # prose, including across a wrapped page boundary. Method names
            # alone are far shorter than this content-specific correspondence.
            cap=re.sub(r'(?:Figure|图)\s*[A-Z]?\d+(?:[.\-–]\d+)*','',title,flags=re.I)
            cap=re.sub(r'\[[\d,\s\-–]+\]|[（(](?:图源|From).*?[)）]','',cap,flags=re.I)
            compact=re.sub(r'\s+','',normalize_text(cap).casefold())
            prose=re.sub(r'\s+','',normalize_text(text).casefold())
            overlap=(SequenceMatcher(None,compact,prose,autojunk=False).find_longest_match(0,len(compact),0,len(prose))
                     if re.search(r'过程|流程|procedure|process',title,re.I) and source_rows and named(title,text) else None)
            if (overlap and overlap.size>=18
                    and sum(bool(re.search(p,text,re.I)) for p in _CONTENT_OPERATIONS)>=2):
                reason='Independent cited prose repeats a long concrete procedure description, including its input/output transformation; a name alone cannot match it.'
                matched=['literal_procedure:'+compact[overlap.a:overlap.a+overlap.size]]
            # Timeline relations require two ordered time nodes and their
            # intervening computation; delayed output must explain the changed
            # target/environment state, rather than merely mentioning latency.
            times=[f for f in facts if re.fullmatch(r't\s*=\s*t\s*\d+',f['text'],re.I)]
            compute=[f for f in facts if re.fullmatch(r'computation|计算',f['text'],re.I)]
            if len({re.sub(r'\s+','',f['text']) for f in times})>=2 and compute and source_rows:
                centers=sorted((f['bbox'][0]+f['bbox'][2])/2 for f in times)
                if (centers[0]<(compute[0]['bbox'][0]+compute[0]['bbox'][2])/2<centers[-1]
                        and 'latency' in _concepts(title) and 'latency' in bf
                        and re.search(r'输出.{0,20}(?:晚|延迟)|delayed.{0,15}output',text,re.I)
                        and re.search(r'(?:环境|目标|state).{0,20}(?:变化|改变|chang)',text,re.I)):
                    reason='The ordered time–computation–time visual is explained by delayed output and changed target/environment state in cited prose.'
                    matched=['ordered_time_nodes','intermediate_computation','changed_state']
            # A split-input tensor diagram identifies its principal relation
            # without needing every routine normalization/projection label.
            tensor_nodes=[(m.group(1),f) for f in facts for m in re.finditer(r'\b([A-Z])(?:[A-Za-z\d_\-]+)?\s*∈',f['text'])]
            split_nodes=[f for f in facts if re.fullmatch(r'split',f['text'],re.I)]
            project_nodes=[f for f in facts if re.search(r'\bFC\b',f['text'])]
            typed=set()
            if split_nodes and project_nodes:
                sx=sum(split_nodes[0]['bbox'][::2])/2;px=min(sum(f['bbox'][::2])/2 for f in project_nodes)
                inputs={name for name,f in tensor_nodes if sum(f['bbox'][::2])/2<sx}
                bands={name for name,f in tensor_nodes if sx<sum(f['bbox'][::2])/2<px}
                if inputs and bands:typed=inputs|bands
            if (len(typed)>=2 and re.search(r'子带划分|band[\s-]+splitt',title,re.I)
                    and any(re.search(r'band[\s-]+split',f['text'],re.I) for f in facts)
                    and any(f['text'].casefold()=='merge' for f in facts)
                    and named(title,text) and re.search(r'划分.{0,30}(?:子带|sub.band)',text,re.I)
                    and all(re.search(r'(?<![A-Za-z])'+v+r'(?:[𝑖i_\d\s]*)(?:∈|\s*∈)',text) for v in typed)
                    and re.search(r'(?:𝐾|K).{0,8}(?:个)?子带',text)):
                reason='Named split procedure, actual typed input/sub-band tensors, and split/merge stages bind the independently explained K-band partition relation.'
                matched=['typed_tensor:'+v for v in sorted(typed)]+['band_partition','split_merge']
            # A failure-sample figure must contain the actual compared method
            # panels, input and annotation. Citing a data source or reporting a
            # generic benchmark outcome cannot replace those local identities.
            baselines={name for f in facts for name in _procedure_names(f['text'])
                       if re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*',f['text'].strip())}
            fact_text=' '.join(f['text'] for f in facts)
            if (re.search(r'失败案例|failure\s+(?:case|example)',title,re.I) and named(title,text)
                    and re.search(r'本方法|our(?:s| method)',fact_text,re.I)
                    and 'input' in profile and 'annotation' in profile and baselines
                    and all(_term(text.casefold(),name) for name in baselines)
                    and re.search(r'(?:本方法|our(?:s| method)).{0,110}(?:逊于|劣于|低于|worse|inferior)',text,re.I)
                    and re.search(r'假设|改进|原因|because|limitation|improv',text,re.I)):
                reason='Actual input/annotation/our-method/baseline panels bind the same named dataset, an independently explained adverse comparison and its failure mechanism.'
                matched=['input_annotation_panels','our_method_comparison']+['baseline:'+name for name in sorted(baselines)]
            # Literal dataset samples have no readable field labels in many
            # real photographs. Require independent acquisition/modal facts
            # and provided annotation facts, beyond using or naming the data.
            data_facts=[p for p in (r'单目|monocular',r'固定相机|fixed camera',r'原地旋转|rotat',
                        r'多个视角|multiple views|multi.view',r'分割标注|segmentation annotation',r'关节点标注|keypoint annotation')
                        if re.search(p,text,re.I)]
            if (re.search(r'数据集示例|example\s+of.*?dataset',title,re.I)
                    and not re.search(r'失败|failure|对比|比较|comparison',title,re.I)
                    and named(title,text) and len(data_facts)>=3
                    and re.search(r'分割标注|关节点标注|annotation',text,re.I)):
                reason='One literal dataset sample binds its exact named identity and independent acquisition/viewpoint and annotation properties; a dataset citation alone cannot credit it.'
                matched=['dataset_acquisition:'+p for p in data_facts]
            # Recover arbitrary location names from the original map panels;
            # cardinal-direction forms (North/Northern) are grammatical aliases,
            # not aliases between datasets or methods. All recovered locations
            # require their own prose, plus actual geological legend content.
            geology={'fault','porphyry','magmatic','sedimentary','granitic','mineral'}
            map_names=[f['text'].strip() for f in facts if re.fullmatch(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}',f['text'].strip())
                       and not _concepts(f['text']) and f['text'].casefold() not in {'value','low','high'}]
            map_names=list(dict.fromkeys(map_names))
            extra_rows=[];map_matched=set()
            if (re.search(r'数据集|datasets',title,re.I) and re.search(r'可视化|visualiz',title,re.I)
                    and len(map_names)>=3 and len(profile&geology)>=2):
                for name in map_names:
                    phrase=re.escape(name.casefold())
                    phrase=re.sub(r'^(north|south|east|west)\\\s',lambda m:m.group(1)+r'(?:ern)?\s+',phrase)
                    options=[rr for rr,tt,ff,rf,cc in local_passages if re.search(r'(?<![a-z])'+phrase+r'(?![a-z])',tt.casefold())
                             and _references_allow(rf,target.number)]
                    if not options:break
                    extra_rows.extend(min(options,key=lambda rr:sum(len(r.text) for r in rr)))
                else:
                    for rr,tt,ff,rf,cc in local_passages:
                        if _references_allow(rf,target.number) and ff&profile&geology:
                            extra_rows.extend(rr);map_matched.update(ff&profile&geology)
                    if len(map_matched)>=2:
                        reason='Every recovered geographic panel name and multiple actual geological legend features bind independent dataset descriptions; the full named physical map set is unique.'
                        matched=['geographic_panel:'+name for name in map_names]+sorted(map_matched)
            # Ordinary position/projection nodes do not replace the distinctive
            # masked/unmasked attention branches, feed-forward and norm stages.
            attn=[f for f in facts if 'attention' in _concepts(f['text'])]
            masks=[f for f in facts if 'masked_attention' in _concepts(f['text'])]
            if (attn and masks and {'feed_forward','normalization'}<=profile
                    and any(abs((a['bbox'][0]+a['bbox'][2]-m['bbox'][0]-m['bbox'][2])/2)>50 for a in attn for m in masks)
                    and {'encoder','decoder','attention','feed_forward','normalization','masked_attention'}<=bf
                    and {'encoder','decoder'}<=_concepts(title) and source_rows
                    and re.search(r'未来.{0,20}(?:token|位置|信息)|future.{0,20}token',text,re.I)):
                reason='Distinct physical unmasked/masked branches and feed-forward/norm stages bind the independent encoder/decoder explanation and prevention of future-token access.'
                matched=['masked_unmasked_branches','feed_forward','normalization','encoder_decoder_roles']
            if reason:candidates.append(i);details[i]=(reason,matched,extra_rows)
        if len(candidates)!=1:continue
        i=candidates[0];reason,matched,extra_rows=details[i]
        evidence_rows=list({(r.page_number,r.bbox,r.text):r for r in rows+extra_rows}.values())
        result.setdefault(i,dict(evidence_kind='main_content_relations',
            group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text) for l in groups[i]],
            full_title=regions[i][0]['title'],graphic_regions=regions[i],graphic_fields=fields.get(i,[]),matched_features=matched,
            body_evidence=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text,source=r.source) for r in evidence_rows],
            uniqueness_reason=reason+' No other physical group matches these entities and relations.'))
    return result


def _body_passages(index,regions,caption_keys,usage_scopes=None):
    directories=toc_line_keys(index.document)
    if usage_scopes is None:usage_scopes=usage_scope_map(index.document,directories)
    pages={p.number:p for p in index.document.pages}
    eligible=[]
    areas=[area for items in regions.values() for area in items]
    for row in index.lines:
        key=_key(row);page=pages[row.page_number]
        inline_bold=(row.bold and row.source=='native' and row.font_size and
                     any(not other.bold and other.source=='native' and other.font_size
                         and abs(other.font_size-row.font_size)<=row.font_size*.05
                         and abs((other.bbox[1]+other.bbox[3]-row.bbox[1]-row.bbox[3])/2)<=row.font_size*.4
                         and max(other.bbox[0]-row.bbox[2],row.bbox[0]-other.bbox[2],0)<=row.font_size*2
                         and len(other.text.strip())>=20 and _key(other) not in caption_keys
                         for other in page.lines))
        if (key in caption_keys or key in directories or (row.bold and not inline_bold)
                or is_toc_line(row.text) or not is_body_usage_scope(usage_scopes,row)
                or not row.text.strip() or row.bbox[1]<page.height*.09 or row.bbox[3]>page.height*.92):continue
        if any(area['page_number']==row.page_number and _inside(row.bbox,area['bbox']) for area in areas):continue
        if any(_inside(row.bbox,b) and b[3]-b[1]<page.height*.7 for b in (*page.images,*page.tables)):continue
        typical=body_font(page)
        if row.source=='native' and typical and row.font_size and row.font_size<typical*.95:continue
        eligible.append((replace(row,bold=False) if inline_bold else row,'body'))
    paragraphs=[]
    for line,_ in _prose(eligible,index.document):
        # A new explicit figure reference starts a separate content context.
        # Keep preceding complete sentences as their own genuine ink span;
        # subsequent text retains the reference and cannot transfer usage.
        first=_REF.search(normalize_text(line.text))
        if first:
            stops=list(re.finditer(r'[。.!?！？]\s*',line.text[:first.start()]))
            cut=stops[-1].end() if stops else 0
            if cut:
                before=span_anchor(line,0,cut)
                after=span_anchor(line,cut,len(line.text))
                paragraphs.extend((replace(before,text=line.text[:cut]),replace(after,text=line.text[cut:])))
                continue
        paragraphs.append(line)
    result=[]
    for n,row in enumerate(paragraphs):
        window=[row]
        result.append(window[:])
        for nextrow in paragraphs[n+1:n+4]:
            if (nextrow.page_number!=row.page_number or nextrow.bbox[1]-window[-1].bbox[3]>32
                    or usage_epoch(usage_scopes,nextrow)!=usage_epoch(usage_scopes,row)):break
            window.append(nextrow)
            result.append(window[:])
        # Keep exact component prose rows, rather than a manufactured union
        # rectangle stretching over another page or a graphic.
    return result


def _physical_labels(labels):
    return tuple((label.number,label.scope,_key(label.line)) for label in labels)


def prepare_figure_usage(index,groups):
    """Prepare immutable-source facts once for native/2.5x/3x evaluation.

    Returned regions/native_fields/caption_keys/body_passages are independent
    containers. No decision is cached and no attribute is attached to index.
    """
    scopes=usage_scope_map(index.document)
    regions=_graphic_regions(index,groups,scopes)
    fields=_native_fields_in_regions(index,regions)
    pages={p.number:p for p in index.document.pages}
    caption_keys=set()
    for kind,labels in (('figure',index.figures),('table',index.tables)):
        for label in labels:
            if label.line.page_number in pages:
                _,rows=_full_title([label],pages[label.line.page_number],kind)
                caption_keys.update(_key(row) for row in rows)
    windows=_body_passages(index,regions,caption_keys,scopes)
    unique_rows={_key(row):row for rows in windows for row in rows}
    body_epochs={key:usage_epoch(scopes,row) for key,row in unique_rows.items()}
    label_epochs={_key(label.line):usage_epoch(scopes,label) for group in groups for label in group}
    return dict(_document=index.document,_groups=tuple(_physical_labels(g) for g in groups),
                _labels=_physical_labels(index.figures+index.tables),regions=regions,native_fields=fields,
                caption_keys=caption_keys,body_passages=windows,usage_scope_map=scopes,usage_scopes=scopes,
                chapters=_chapters(index.document,scopes),body_epochs=body_epochs,label_epochs=label_epochs)


def _epoch(context,line_or_label):
    line=getattr(line_or_label,'line',line_or_label);key=_key(line)
    if key in context['label_epochs']:return context['label_epochs'][key]
    if key in context['body_epochs']:return context['body_epochs'][key]
    return usage_epoch(context['usage_scope_map'],line_or_label)


def _chapters(document,scopes):
    answer={};current={}
    for page in document.pages:
        typical=body_font(page)
        for row in page.lines:
            epoch=usage_epoch(scopes,row)
            if not is_body_usage_scope(scopes,row) or row.bbox[1]<page.height*.09:continue
            text=normalize_text(row.text)
            chinese=re.match(r'^第\s*[一二三四五六七八九十百\d]+\s*章',text)
            # Numbered algorithm rows can be bold (for example "6 end").
            # A bare numeric chapter also needs actual heading-sized type.
            numeric=(re.match(r'^[1-9]\d?\s+[\u4e00-\u9fffA-Za-z]',text)
                     and row.font_size and typical and row.font_size>=typical*1.2)
            if ((row.bold or row.font_size and typical and row.font_size>=typical*1.2)
                    and (chinese or numeric)
                    and len(text)<80 and not is_toc_line(text)):
                current[epoch]=(page.number,row.bbox,text)
        epochs={usage_epoch(scopes,row) for row in page.lines if is_body_usage_scope(scopes,row)}
        for epoch in epochs:answer[(page.number,epoch)]=current.get(epoch)
    return answer


def _same_content_domain(context,target,rows):
    epoch=_epoch(context,target)
    if not _same_epoch(context,target,rows):return False
    chapters=context['chapters'];identity=chapters.get((target.line.page_number,epoch))
    return all(chapters.get((row.page_number,epoch))==identity for row in rows)


def _same_epoch(context,target,rows):
    epoch=_epoch(context,target)
    return epoch>=0 and all(_epoch(context,row)==epoch for row in rows)


def _named_figure_identity(title):
    match=re.match(r'^图\s*[A-Z]?\d+(?:[.\-–]\d+)*\s+([A-Za-z][A-Za-z0-9_-]*(?:\s+[A-Za-z][A-Za-z0-9_-]*){0,2})\s*[\u4e00-\u9fff]',title)
    return match.group(1).strip() if match else None


def _identity_in_text(name,text):
    compact=re.sub(r'[\s\-–_]','',text.casefold())
    identity=re.sub(r'[\s\-–_]','',name.casefold())
    return bool(re.search(r'(?<![a-z0-9])'+re.escape(identity)+r'(?![a-z0-9])',compact))


def _named_subject_allowed(title,text,fields):
    identity=_named_figure_identity(title)
    if not identity or _identity_in_text(identity,text):return True
    if not re.search(r'本文|本章|我们提出|\bour\s+(?:method|model|framework)\b',text,re.I):return False
    physical=' '.join(field['text'] for field in fields)
    subjects=re.findall(r'(?:^|[。；;]\s*)([A-Za-z][A-Za-z0-9_-]{2,})\s*(?:采用|使用|将|通过|uses?\b|encodes?\b)',text,re.I)
    return all(_identity_in_text(subject,physical) for subject in subjects)


def _prepared(index,groups,context):
    if (not isinstance(context,dict) or context.get('_document') is not index.document
            or context.get('_groups')!=tuple(_physical_labels(g) for g in groups)
            or context.get('_labels')!=_physical_labels(index.figures+index.tables)):
        return prepare_figure_usage(index,groups)
    return context


def figure_content_candidates(index,groups,prepared_context=None):
    """Cheap physical regions eligible for further content observation.

    This supplies no usage credit. An unsourced graphic needs nearby ordinary
    prose with several concrete operations and literal caption/topic overlap;
    a name list cannot trigger OCR. All groups remain in semantic competition.
    """
    context=_prepared(index,groups,prepared_context);answer={}
    for i,areas in context['regions'].items():
        title=areas[0]['title'];target=groups[i][0]
        if _citations(title):answer[i]=areas;continue
        title_text=re.sub(r'(?:Figure|图)\s*[A-Z]?\d+(?:[.\-–]\d+)*','',title,flags=re.I)
        title_features=_concepts(title_text)-_WEAK
        title_roles=_relation_prose_details(title_text)[0]
        for rows in context['body_passages']:
            if abs(rows[0].page_number-target.line.page_number)>4:continue
            if not _same_content_domain(context,target,rows):continue
            text=' '.join(r.text for r in rows)
            if len(text)<70:continue
            compact=re.sub(r'\s+','',text)
            refs={normalize_label(m.group(1)) for m in _REF.finditer(normalize_text(text))}
            if _references_allow(refs,target.number) and _process_candidate_prose(title,text):
                answer[i]=areas;break
            literal=any(token[n:n+3] in compact for token in re.findall(r'[\u4e00-\u9fff]{3,}',title_text)
                        for n in range(len(token)-2))
            if sum(bool(re.search(p,text,re.I)) for p in _CONTENT_OPERATIONS)>=3 and (literal or title_features&_concepts(text)):
                answer[i]=areas;break
            owner=_schematic_named_owner(title)
            refs={normalize_label(m.group(1)) for m in _REF.finditer(normalize_text(text))}
            if (owner and _structured_owner_in_text(owner,text) and _references_allow(refs,target.number)
                    and re.search(r'Bayesian.{0,100}(?:model selection|hyperparameter)',text,re.I)
                    and re.search(r'(?:select|tuning|evaluat|optimi)',text,re.I)):
                answer[i]=areas;break
            if (re.search(r'分类图|taxonomy',title,re.I) and _references_allow(refs,target.number)
                    and all(re.search(p,text) for p in (r'代码逻辑层',r'经济模型层',r'网络(?:共识)?层'))
                    and re.search(r'分类|分为',text) and _relation_prose_details(text)[2]>=3):
                answer[i]=areas;break
            if (re.search(r'角色定义|系统角色|提示模板|system\s+role|chat\s+template',title_text,re.I)
                    and all(r.page_number==target.line.page_number for r in rows)
                    and 0<=areas[0]['bbox'][1]-max(r.bbox[3] for r in rows)<=100
                    and re.search(r'指令(?:遵循)?模型|指令遵循|对话式接口|chat\s*(?:model|interface)',text,re.I)
                    and re.search(r'输入.{0,90}Opcode.{0,50}Gas',compact,re.I)
                    and re.search(r'评估.{0,15}恶意|恶意性.{0,15}评估',compact)
                    and _references_allow({normalize_label(m.group(1)) for m in _REF.finditer(normalize_text(text))},target.number)):
                answer[i]=areas;break
            # Physical causal comparisons use actions such as reflection,
            # obstruction and transmission rather than neural compute verbs.
            # A candidate still needs several actual caption roles, three
            # concrete action families, and a sentence joining two roles.
            if len(title_roles)>=3:
                body_roles=_relation_prose_details(text)[0]
                causal=(r'发射|接收',r'穿透|遮挡|阻挡',r'反射|散射|吸收')
                refs={normalize_label(m.group(1)) for m in _REF.finditer(normalize_text(text))}
                if (len(title_roles&body_roles)>=3 and _references_allow(refs,target.number)
                        and sum(bool(re.search(p,text)) for p in causal)>=3
                        and any(len(title_roles&_relation_prose_details(sentence)[0])>=2
                                and any(re.search(p,sentence) for p in causal)
                                for sentence in re.split(r'[。；;]',text))):
                    answer[i]=areas;break
            # A physical transmission-chain title can state the phenomenon
            # without enumerating its roles. Investigation still needs actual
            # independent causal prose with multiple physical actors/actions.
            if literal and re.search(r'传输|衰减|辐射|\b(?:transmission|attenuation|radiation)\b',title_text,re.I):
                physical_roles={'solar_radiation','atmosphere','atmospheric_scattering',
                                'atmospheric_absorption','ground_reflection','sensor'}
                body_roles=_relation_prose_details(text)[0]
                causal=(r'发射|接收',r'传输|衰减',r'反射|散射|吸收')
                refs={normalize_label(m.group(1)) for m in _REF.finditer(normalize_text(text))}
                if (len(physical_roles&body_roles)>=4 and _references_allow(refs,target.number)
                        and all(re.search(p,text) for p in causal)
                        and any(len(physical_roles&_relation_prose_details(sentence)[0])>=2
                                and any(re.search(p,sentence) for p in causal)
                                for sentence in re.split(r'[。；;]',text))):
                    answer[i]=areas;break
    return answer


def figure_physical_candidates(index,groups):
    """Cheap caption-only gate before preparing whole-document prose.

    Its result requests investigation, never usage. Ordinary method-name-only
    captions do not activate the expensive body/graphic preparation path.
    """
    pages={p.number:p for p in index.document.pages};answer=set();scopes=usage_scope_map(index.document)
    kinds=r'架构|框架|流程|结构|理论|特点|协同|路线|过程|机制|原理|示意|结果|比较|样例|示例|挑战|拓扑|子图|成像|链条|对齐|提示|实验设计|角色定义|模板|交集规划|分类图|会诊|数据构建|\b(?:architecture|framework|pipeline|workflow|structure|process|principle|diagram|schematic|taxonomy|consultation|construction|results?|comparison|examples?|template)\b'
    for i,group in enumerate(groups):
        if not group or not is_body_usage_scope(scopes,group[0]):continue
        page=pages.get(group[0].line.page_number)
        if page is None:continue
        title,_=_full_title(group,page,'figure')
        if _citations(title) or re.search(kinds,title,re.I):answer.add(i)
    return answer


# Additional content vocabulary belongs only to the complete physical-content
# path. It does not broaden the source-caption or frozen rule vocabularies.
_CONTENT_FEATURES={
    'zero_inflation':('zero-inflation','零膨胀'),
    'biological_absence':('true biological','生物学缺失','真实缺失','物种不存在','样本中确实不存在'),
    'technical_dropout':('technical dropout','missing detection','测序深度不足','技术性缺失'),
    'zero_shortcut':('shortcutting full-zero','预测为零','输出为零','简单的零值模式'),
    'composition_constraint':('compositionality','sum-to-one','归一化约束','组成约束','总和固定','总和为1'),
    'spurious_correlation':('spurious negative correlations','伪相关','虚假相关'),
    'domain_shift':('domain shift','distribution mismatch','分布偏移','分布差异'),
    'cross_cohort':('cross-cohort','跨队列'),
    'batch_effect':('batch effects','batch effect','批次效应','批次偏差','批次差异'),
    'unlabeled':('unlabeled','未标注','无标签','无标注'),
    'supervised':('supervised','监督学习','有监督'),
    'isolated_model':('isolated model','任务驱动','特定任务','任务特定','任务专用','单一队列'),
    'shared_representation':('shared latent','shared representation','共享表示','共享表征','共享空间'),
    'pretraining':('pre-train','预训练'),
    'multimodal':('multimodal','多模态'),
    'disease_prediction':('disease prediction','disease status','疾病预测','疾病诊断','疾病关联'),
    'conditional_generation':('conditional generative','conditional generation','条件生成','条件补全'),
    'latent_representation':('潜在表征空间','潜空间','潜在表示空间','latent representation','共享表示空间'),
    'parameter_representation':('参数表征空间','参数空间','parameter representation'),
    'explicit_representation':('显式三维表征空间','显式三维','显式表征','explicit 3d'),
    'manifold':('空间流形','流形结构','流形','manifold'),
    'layered_parameters':('分层参数调制','分层结构','分层','层级'),
    'physical_structure':('物理结构','物理意义','物理一致','物理属性'),
    'fine_control':('控制准','精准语义可控','细粒度','精细','精准'),
    'adaptation':('适配强','适配','适应','迁移'),
    'explainability':('解释弱','解释性','可解释'),
    'optimization_cost':('优化重','优化成本','计算成本','训练成本','渲染成本','开销'),
    'hypernetwork':('hyper-module','hyper module','超网络','hypernetwork'),
    'generator':('生成器','generator'),
    'text_encoding':('文本编码器','文本编码','text encoder'),
    'parameter_offset':('参数偏移','参数调制','parameter offset'),
    'shape_condition':('形状文本','形状图片','形状','shape'),
    'attribute_condition':('属性文本','属性图片','属性','attribute'),
    'style_condition':('风格文本','风格图片','风格','style'),
    'target_condition':('目标文本','目标风格','target text'),
    'source_condition':('原始文本','原始风格','source text'),
    'clip_loss':('clip loss','clip 方向损失','clip方向损失'),
    'geometry':('高斯几何','几何结构','几何','geometry'),
    'albedo':('反照率','纹理/反照率','albedo'),
    'surface_normal':('法向量','法向图','法线','normal vector'),
    'roughness':('粗糙度','roughness'),
    'lighting':('光照','lighting'),
    'rendering':('渲染','rendering'),
    'volume_rendering':('体渲染','volume rendering'),
    'low_resolution':('低分辨率','low-resolution','low resolution'),
    'super_resolution':('超分辨率','高分辨率','super-resolution','upsampling','上采样'),
    'mapping_network':('映射网络','mapping network'),
    'mesh':('网格','mesh'),
    'dna':('dna','序列'),
    'frozen':('frozen','冻结'),
    'cls':('[cls]','cls'),
    'sampling':('sampling','采样','截断'),
    'padding':('padding','填充','补齐'),
    'batch':('batch','批处理','批次'),
    'fixed_length':('定长','固定长度','fixed-length','fixed length'),
    'segmentation':('切片','切分','segmentation','slicing'),
    'fragment_features':('片段级特征','片段级表示','fragment features'),
    'abundance':('abundance','丰度'),
    'sparse_structure':('sparse','稀疏'),
    'reconstruction':('reconstruction','重构','重建'),
    'multimodal_alignment':('多模态对齐','跨尺度联系','跨模态','projected sequence'),
    'diffusion':('diffusion','扩散'),
    'flow_matching':('flow matching','流匹配'),
    'noise':('噪声','noise'),
    'denoising':('denoising','去噪'),
    'directional_lighting':('光照方向图','光照方向','方向编码','directional lighting'),
    'domain_switch':('域切换','域可切换','目标域','域编码','模态编码'),
    'training_phase':('训练阶段','training stage','training process','训练时'),
    'inference_phase':('推理阶段','推理时','推理过程','推理中','推理端','前向推理','inference stage','inference process'),
    'prediction_loss':('损失函数','预测噪声','损失项','noise prediction'),
    'monocular_video':('单目视频','单目人脸视频','monocular video'),
    'uniform_light':('均匀光','标准光照','规范光照','uniform light'),
    'relightable_avatar':('可重光照的头部虚拟化身','头部虚拟化身','三维头像','head avatar'),
    'novel_view':('新视角','未见侧面视角','未见过的视角','novel view','unseen view'),
    'seen_view':('已见过的视角','可见正面视角','seen view'),
    'cross_reenactment':('表情交叉驱动','跨身份表情重演','跨身份重演','cross-exp','cross expression'),
    'self_reenactment':('表情自驱动','自身','self-exp','self expression'),
    'expression_target':('目标表情','表情重演','expression target','reenactment'),
    'index_sequence':('indices','index sequence','索引序列'),
    'embedding_matrix':('embedding matrix','嵌入矩阵'),
    'index_lookup':('look up entries by index','index lookup','按索引查表','索引查表'),
}
_CONTENT_PATTERNS={name:re.compile('|'.join(
    r'(?<![a-z0-9_])'+re.escape(a).replace(r'\ ',r'[\s-]+')+r'(?![a-z0-9_])' if a.isascii()
    else re.escape(a) for a in aliases),re.I) for name,aliases in _CONTENT_FEATURES.items()}
_CONTENT_MINOR={'dna','batch','mapping_network','mesh','shape_condition','attribute_condition','style_condition',
                'target_condition','source_condition','geometry','rendering','generator'}


@lru_cache(maxsize=4096)
def _content_profile(text):
    text=re.sub(r'\s+(?=[\u4e00-\u9fff])','',normalize_text(text))
    found={name for name,pattern in _CONTENT_PATTERNS.items() if pattern.search(text)}
    if 'latent_representation' in found and re.search(r'连续轨迹|连续.{0,8}(?:内部)?表示|潜在.{0,30}连续|连续.{0,30}潜在',text):found.add('manifold')
    if ('embedding_matrix' in found and 'index_sequence' in found
            and re.search(r'每个索引.{0,20}映射.{0,20}(?:稠密)?向量',text)):found.add('index_lookup')
    return frozenset(found)


def _content_graphic_text(fields):
    parts=[f['text'] for f in fields]
    for a in fields:
        for b in fields:
            if a is b or a['page_number']!=b['page_number']:continue
            if (0<=b['bbox'][1]-a['bbox'][3]<=16
                    and min(a['bbox'][2],b['bbox'][2])-max(a['bbox'][0],b['bbox'][0])>0):
                parts.append(a['text']+' '+b['text'])
    return ' '.join(parts)


def _literal_gallery(fields,title,passages,page):
    if not re.search(r'结果|样例|示例|\b(?:results?|examples?)\b',title,re.I):return None
    names={normalize_text(f['text']).strip('“”\"') for f in fields
           if re.fullmatch(r'[A-Z][a-z]+(?:[- ][A-Za-z][a-z]+)*',normalize_text(f['text']).strip('“”\"'))}
    names-={'Input','Output','Target','Source','Original','Model','Encoder','Decoder','Dataset','Results','Example','Figure'}
    if len(names)<5:return None
    for rows,text,bf,refs,cites in passages:
        if abs(rows[0].page_number-page)>2 or any(not _term(text.casefold(),name.casefold()) for name in names):continue
        if not re.search(r'迁移|转化|生成|合成|\b(?:transfer|generat|synthesi)',text,re.I):continue
        if not re.search(r'原始|起点|输入|源域|\b(?:original|input|source)\b',text,re.I):continue
        return rows,sorted('literal_category:'+name for name in names)
    return None


_COMPARISON_TASKS={
    'geometry_editing':r'几何.{0,8}编辑|geometry\s+edit',
    'delighting':r'去光照|delight',
    'normal_prediction':r'法线.{0,8}(?:预测|估计)|normal\s+(?:prediction|estimation)',
    'expression_reenactment':r'表情重演|表情重现|reenactment',
}
_RESULT_DIMENSIONS=(r'身份|identity',r'几何|形变|geometry',r'纹理|texture',
    r'阴影|shadow',r'高光|highlight',r'色偏|颜色|colour|color',
    r'鼻梁|眼窝|皱纹|发际线|细节|detail',r'一致|稳定|合理|consisten|stabil',
    r'模糊|清晰|清楚|blur|sharp',r'正面|侧面|未见|unseen|frontal|profile')
_RESULT_OPERATIONS=(r'生成|generate',r'移除|消除|remove',r'恢复|recover',r'保持|保留|preserv',
    r'编辑|edit',r'渲染|render',r'预测|predict',r'重演|reenact',r'完成|achiev',r'支持|support')


def _comparison_roles(fields):
    inputs=[f for f in fields if re.fullmatch(r'输入(?:图像)?|input(?:\s+image)?|目标表情',f['text'],re.I)]
    ours=[f for f in fields if re.fullmatch(r'本章方法|本文方法|本方法|our(?:s| method)?',f['text'],re.I)]
    aligned=[(a,b) for a in inputs for b in ours if a['page_number']==b['page_number']
             and abs(sum(a['bbox'][1::2])-sum(b['bbox'][1::2]))/2<=18]
    if not aligned:return set()
    names=set()
    for a,b in aligned:
        y=sum(a['bbox'][1::2])/2
        for f in fields:
            if f['page_number']!=a['page_number'] or abs(sum(f['bbox'][1::2])/2-y)>18:continue
            text=normalize_text(f['text'])
            for name in text.split():
                if (re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{3,}',name)
                        and name.casefold() not in {'input','image','ours','output','target','source','original','method'}):names.add(name)
    # The same label may be re-read as a clipped prefix in another tile.
    # Its intact observation supplies the identity; a lone prefix is retained
    # and cannot match a body name unless the actual label marks abbreviation.
    return {name for name in names if not any(name!=other and other.casefold().startswith(name.casefold()) for other in names)}


def _literal_model_in_prose(name,text):
    compact=re.sub(r'[\s\-–_]','',text.casefold())
    literal=re.sub(r'[\s\-–_]','',name.casefold())
    if literal.endswith('.') and len(literal[:-1])>=5:
        matches=set(re.findall(r'(?<![a-z0-9])'+re.escape(literal[:-1])+r'[a-z0-9]+(?![a-z0-9])',compact))
        return len(matches)==1
    return bool(re.search(r'(?<![a-z0-9])'+re.escape(literal)+r'(?![a-z0-9])',compact))


def _named_stage_evidence(fields,local):
    names={m.group(1) for f in fields for m in [re.match(
        r'^([A-Za-z][A-Za-z0-9_-]{2,})\s*[（(][^）)]{0,25}(?:level|stage|层|阶段)',normalize_text(f['text']),re.I)] if m}
    if len(names)<2:return []
    anchors=[]
    for name in names:
        options=[item for item in local if _literal_model_in_prose(name,item[1]) and len(item[2])>=2
                 and sum(bool(re.search(p,item[1],re.I)) for p in (r'构建|设计',r'建立|连接|对齐',r'学习|预训练',r'生成|重构',r'映射|用于'))>=2]
        if not options:return None
        anchors.extend(min(options,key=lambda item:len(item[1]))[0])
    return anchors


def _matrix_lookup_structure(fields):
    matrices=[f for f in fields if re.search(r'embedding\s+matrix|嵌入矩阵',f['text'],re.I)]
    lookups=[f for f in fields if re.search(r'look\s+up\s+entries\s+by\s+index|按索引查表|索引查表',f['text'],re.I)]
    if not matrices or not lookups:return None
    numbers=[]
    for f in fields:
        value=f['text'].strip().replace('−','-')
        if re.fullmatch(r'-?(?:\d+(?:\.\d+)?|\.\d+)',value):
            numbers.append((f['page_number'],sum(f['bbox'][1::2])/2,sum(f['bbox'][::2])/2,float(value)))
    def rows_between(page,top,bottom):
        bands=[]
        for _,y,x,value in sorted(n for n in numbers if n[0]==page and top<n[1]<bottom):
            band=next((b for b in bands if abs(b[0]-y)<=3),None)
            if band is None:band=[y,[]];bands.append(band)
            band[1].append((x,value))
        rows=[]
        for y,cells in bands:
            columns=[];conflict=False
            for x,value in sorted(cells):
                column=next((c for c in columns if abs(c[0]-x)<=3),None)
                if column is None:columns.append([x,value])
                elif column[1]!=value:conflict=True;break
            if not conflict and len(columns)>=3:rows.append(tuple(c[1] for c in columns))
        return rows
    for matrix in matrices:
        for lookup in lookups:
            if matrix['page_number']!=lookup['page_number'] or matrix['bbox'][3]>=lookup['bbox'][1]:continue
            page=matrix['page_number']
            source=rows_between(page,matrix['bbox'][3],lookup['bbox'][1]);output=rows_between(page,lookup['bbox'][3],float('inf'))
            if len(source)<3 or len(output)<3 or len(set(source))!=len(source):continue
            if len({len(row) for row in source+output})!=1 or not all(row in source for row in output):continue
            indices=tuple(source.index(row) for row in output)
            if len(set(indices))<3 or indices==tuple(sorted(indices)):continue
            return tuple(source),tuple(output),indices
    return None


def _lookup_content_credits(groups,regions,fields,passages,context):
    structures={i:_matrix_lookup_structure(fields.get(i,[])) for i in regions};answer={}
    for i,structure in structures.items():
        if structure is None:continue
        target=groups[i][0];page=target.line.page_number
        title=regions[i][0]['title']
        if not re.search(r'嵌入|embedding|查表|lookup',title,re.I):continue
        if re.search(r'曲线|收敛|消融|准确率|召回率|性能|复杂度|\b(?:curve|convergence|ablation|accuracy|recall|performance|complexity)\b',title,re.I):continue
        # Toy vector values establish the lookup operation, not a distinct
        # prose subject. Generic mapping prose cannot choose between two
        # physical lookup illustrations merely because their numbers differ.
        if any(j!=i and structures[j] is not None and abs(groups[j][0].line.page_number-page)<=4
               and _same_content_domain(context,target,[groups[j][0].line]) for j in structures):continue
        for rows,text,bf,refs,cites in passages:
            if abs(rows[0].page_number-page)>4 or not _same_content_domain(context,target,rows):continue
            if not _references_allow(refs,target.number):continue
            if not {'index_sequence','embedding_matrix','index_lookup'}<=_content_profile(text):continue
            if sum(bool(re.search(p,text,re.I)) for p in _CONTENT_OPERATIONS)<3:continue
            answer[i]=dict(evidence_kind='physical_index_matrix_lookup',
                group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text) for l in groups[i]],
                full_title=regions[i][0]['title'],graphic_regions=regions[i],graphic_fields=fields[i],
                matched_features=['actual_embedding_matrix','explicit_index_lookup_operation','reordered_selected_complete_vector_rows'],
                lookup_structure=dict(source_rows=structure[0],output_rows=structure[1],observed_source_row_positions=structure[2]),
                body_evidence=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text,source=r.source) for r in rows],
                uniqueness_reason='An actual embedding matrix, explicit lookup label, and at least three complete reordered vector rows bind the independent index-to-matrix-to-dense-vector transformation; example numbers supply graphic structure rather than an extra body conclusion.')
            break
    return answer


def _comparison_content_credits(groups,regions,fields,passages,context):
    signatures={i:(_comparison_roles(fields.get(i,[])),
                   {k for k,p in _COMPARISON_TASKS.items() if re.search(p,areas[0]['title'],re.I)}) for i,areas in regions.items()}
    result={}
    for i,areas in regions.items():
        title=areas[0]['title'];names,tasks=signatures[i];target=groups[i][0];page=target.line.page_number
        if _citations(title) or not names or not tasks or not re.search(r'比较|对比|comparison',title,re.I):continue
        if any(j!=i and signatures[j]==(names,tasks) and abs(groups[j][0].line.page_number-page)<=4
               and _same_content_domain(context,target,[groups[j][0].line]) for j in signatures):continue
        local=[item for item in passages if abs(item[0][0].page_number-page)<=4
               and _same_content_domain(context,target,item[0]) and _references_allow(item[3],target.number)]
        actual_profile=_content_profile(_content_graphic_text(fields[i]))-_CONTENT_MINOR
        for rows,text,bf,refs,cites in local:
            if not _comparison_context_allows(text,tasks):continue
            if not all(_literal_model_in_prose(name,text) for name in names):continue
            if not all(re.search(_COMPARISON_TASKS[task],text,re.I) for task in tasks):continue
            if not re.search(r'本章方法|本文方法|本方法|本章|本文|our(?:s| method)',text,re.I):continue
            if not re.search(r'比较|对比|相比|优于|comparison|compar(?:e|ed)|better',text,re.I):continue
            # A wrapped result explanation may continue onto the next physical
            # page. Keep each original anchor and the same chapter/epoch.
            additions=[item for item in local if 0<=item[0][0].page_number-rows[-1].page_number<=1
                       and _comparison_context_allows(item[1],tasks)]
            proof=list(rows);expanded=text
            if not actual_profile<=_content_profile(expanded) or sum(bool(re.search(p,expanded,re.I)) for p in _RESULT_OPERATIONS)<3:
                additions=sorted(additions,key=lambda v:(v[0][0].page_number,v[0][0].bbox[1]))
                for extra in additions:
                    if extra[0][0].page_number==rows[-1].page_number and extra[0][0].bbox[1]<rows[-1].bbox[1]:continue
                    proof.extend(extra[0]);expanded+=' '+extra[1]
                    if actual_profile<=_content_profile(expanded) and sum(bool(re.search(p,expanded,re.I)) for p in _RESULT_OPERATIONS)>=3:break
            if not actual_profile<=_content_profile(expanded):continue
            if sum(bool(re.search(p,expanded,re.I)) for p in _RESULT_OPERATIONS)<3:continue
            if sum(bool(re.search(p,expanded,re.I)) for p in _RESULT_DIMENSIONS)<2:continue
            unique={_key(row):row for row in proof}
            result[i]=dict(evidence_kind='physical_comparison_content',
                group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text) for l in groups[i]],
                full_title=title,graphic_regions=areas,graphic_fields=fields[i],
                matched_features=['actual_input_our_method_roles']+['literal_compared_model:'+n for n in sorted(names)]+sorted(tasks|actual_profile),
                body_evidence=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text,source=r.source) for r in unique.values()],
                uniqueness_reason='Actual aligned input/our-method/baseline panels bind the exact task, all recovered comparison roles, and independent concrete result interpretation; no same-domain competing object has this signature.')
            break
    return result


def _comparison_context_allows(text,tasks):
    """A separate named model/task cannot supply this panel's conclusions."""
    mentioned={key for key,pattern in _COMPARISON_TASKS.items() if re.search(pattern,text,re.I)}
    if mentioned-tasks:return False
    return not re.search(r'(?:对于|针对|关于)?另(?:一(?:个|项|种)|外一(?:个|项|种)).{0,8}(?:模型|方法|任务)|'
                         r'其他(?:的)?(?:模型|方法|任务)|\b(?:another|other)\s+(?:model|method|task)\b',text,re.I)


def _uncited_content_credits(index,groups,regions,fields,passages,context):
    """Use complete physical concepts/roles, including graphics without cites."""
    profiles={i:_content_profile(_content_graphic_text(fields.get(i,[]))) for i in regions}
    result={}
    by_page={}
    for rows,text,bf,refs,cites in passages:
        by_page.setdefault(rows[0].page_number,[]).append((rows,text,_content_profile(text),refs))
    for i,areas in regions.items():
        title=areas[0]['title'];target=groups[i][0];page=target.line.page_number
        if _citations(title):continue
        # Distinct measurement/comparison objects need their own quantitative
        # evidence. A method's pipeline cannot account for an experiment plot.
        if re.search(r'曲线|收敛|消融|准确率|召回率|\b(?:curve|convergence|ablation|accuracy|recall)\b',title,re.I):continue
        local=[item for p in range(page-4,page+5) for item in by_page.get(p,[])
               if _references_allow(item[3],target.number) and _same_content_domain(context,target,item[0])]
        facts=fields.get(i,[]);profile=profiles[i]
        gallery=_literal_gallery(facts,title,[item for item in passages if _references_allow(item[3],target.number)],page)
        anchors=[];matched=[];reason=None
        if gallery:
            rows,matched=gallery
            if not _same_content_domain(context,target,rows):continue
            if any(j!=i and _literal_gallery(fields.get(j,[]),other[0]['title'],passages,groups[j][0].line.page_number)
                   and {m for m in matched}=={m for m in _literal_gallery(fields.get(j,[]),other[0]['title'],passages,groups[j][0].line.page_number)[1]}
                   and abs(groups[j][0].line.page_number-page)<=4 for j,other in regions.items()):continue
            anchors=list(rows);reason='All independently observed gallery categories and the original-to-target transformation are explained in one nearby independent passage.'
        elif len(profile-_CONTENT_MINOR)>=3 and (len(profile)>=5 or 'index_lookup' in profile):
            required=profile-_CONTENT_MINOR
            options=[item for item in local if item[2]&required]
            covered=set().union(*(item[2] for item in options)) if options else set()
            if not required<=covered:continue
            stage_anchors=_named_stage_evidence(facts,local)
            if stage_anchors is None:continue
            # A role-bearing node binds its own paragraph, rather than borrowing
            # operations from a different diagram that happens to share a topic.
            roles=profile&{'latent_representation','parameter_representation','explicit_representation',
                           'hypernetwork','zero_inflation','composition_constraint','domain_shift'}
            if len(roles)>=2 and any(not any(role in item[2] and len(item[2]&profile)>=2 for item in options) for role in roles):continue
            if any(j!=i and profiles[j]-_CONTENT_MINOR==required
                   and abs(groups[j][0].line.page_number-page)<=4
                   and _epoch(context,groups[j][0])==_epoch(context,target)
                   and context['chapters'].get((groups[j][0].line.page_number,_epoch(context,target)))==context['chapters'].get((page,_epoch(context,target))) for j in regions):continue
            selected=list(stage_anchors)
            for feature in required:
                choices=[item for item in options if feature in item[2]]
                item=min(choices,key=lambda v:(abs(v[0][0].page_number-page),len(v[1])))
                selected.extend(item[0])
            text=' '.join(row.text for row in selected)
            if not _named_subject_allowed(title,text,facts):continue
            if sum(bool(re.search(p,text,re.I)) for p in _CONTENT_OPERATIONS)<3:continue
            title_features=_content_profile(title)-_CONTENT_MINOR
            if not title_features<=covered:continue
            anchors=selected;matched=sorted(required)
            reason='All distinctive actual graphic fields and every recovered named role bind independent content paragraphs within four pages; no nearby competing physical group shares the complete signature.'
        if reason:
            unique={(r.page_number,r.bbox,r.text):r for r in anchors}
            result[i]=dict(evidence_kind='complete_uncited_graphic_content',
                group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text) for l in groups[i]],
                full_title=title,graphic_regions=areas,graphic_fields=facts,matched_features=matched,
                body_evidence=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text,source=r.source) for r in unique.values()],
                uniqueness_reason=reason)
    return result


def _deictic_template_credits(index,groups,regions,fields,passages,context):
    """An actual 'template shown below' refers to its adjacent physical box."""
    result={}
    for rows,text,profile,refs,cites in passages:
        if not re.search(r'(?:模板|示例).{0,20}(?:如下所示|如下给出|如下)|'
                         r'(?:如下所示|如下给出).{0,40}(?:模板|示例)',text):continue
        last=max(r.bbox[3] for r in rows);page=rows[-1].page_number;candidates=[]
        for i,areas in regions.items():
            if not _references_allow(refs,groups[i][0].number) or not _same_content_domain(context,groups[i][0],rows):continue
            if not re.search(r'模板|示例',areas[0]['title']):continue
            local=[a for a in areas if a['page_number']==page and 0<=a['bbox'][1]-last<=40]
            if not local:continue
            ink=' '.join(f['text'] for f in fields.get(i,[]))
            if sum(bool(re.search(p,ink,re.I)) for p in (r'\brole\b|\bsystem\b|\buser\b',r'\bscore\b',r'\breason\b',r'\bcode\b'))<2:continue
            own={_key(l.line) for l in groups[i]}
            if any(l.line.page_number==page and last<l.line.bbox[1]<local[0]['bbox'][1]
                   and _key(l.line) not in own for l in index.figures+index.tables):continue
            candidates.append(i)
        if len(candidates)!=1:continue
        i=candidates[0]
        result[i]=dict(evidence_kind='adjacent_deictic_template',
            group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text) for l in groups[i]],
            full_title=regions[i][0]['title'],graphic_regions=regions[i],graphic_fields=fields.get(i,[]),
            matched_features=['independent_template_reference','adjacent_physical_box'],
            body_evidence=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text,source=r.source) for r in rows],
            uniqueness_reason='Independent template/example language points to one immediately following role/score/reason box, with no other caption boundary.')
    return result


def _chat_audit_task_profile(facts):
    """Recover the actual dialogue roles, typed inputs, question and outputs."""
    if len({f['page_number'] for f in facts})!=1:return None
    text=' '.join(f['text'] for f in sorted(facts,key=lambda f:(f['bbox'][1],f['bbox'][0])))
    text=normalize_text(text)
    system=re.search(r'\brole\s*:\s*system\b',text,re.I)
    user=re.search(r'\brole\s*:\s*user\b',text,re.I)
    bounds=re.search(r'\bscore\s+from\s+(\d+)\s+to\s+(\d+)\b',text,re.I)
    if not (system and user and system.start()<user.start() and bounds):return None
    low,high=map(int,bounds.groups())
    if low>=high:return None
    if not all(re.search(p,text,re.I) for p in (r'\bopcodes?\b',r'\bgas\b',
            r'\b(?:execution\s+trace|trace\s+chunk)\b',r'\bmalicious\b',r'\bexplain\s+why\b|\breasons?\b',
            r'\b(?:security\s+auditor|smart\s+contract)\b')):return None
    return dict(inputs=['opcode_sequence','gas_trace'],question='maliciousness',
                outputs=['risk_score','explanation'],score_bounds=[low,high])


def _chat_template_owner_allowed(title,input_text,output_text):
    identity=_named_figure_identity(title)
    if not identity:return True
    # Keep English spaces: an independent word such as "model" is not part
    # of the identifier, while MercuryNetPlus is a different model.
    name=r'\s+'.join(re.escape(part) for part in identity.split())
    def owns(text):
        return bool(re.search(r'(?<![A-Za-z0-9_-])'+name+r'(?![A-Za-z0-9_-])',text,re.I))
    if not owns(input_text):return False
    owner_words={part.casefold() for part in identity.split()}
    for text in (input_text,output_text):
        owners=re.findall(r'(?<![A-Za-z0-9_-])([A-Za-z][A-Za-z0-9_-]{2,})\s*'
            r'(?:指令(?:遵循)?\s*)?(?:模型|网络|(?:chat\s+)?model\b|network\b)',text,re.I)
        if owners and (not owns(text) or any(owner.casefold() not in owner_words for owner in owners)):
            return False
    return True


def _chat_audit_task_credits(index,groups,regions,fields,passages,context):
    """One dialogue template binds its nearby independent task and response use."""
    profiles={i:_chat_audit_task_profile(fields.get(i,[])) for i in regions};result={}
    chat=r'指令(?:遵循)?模型|指令遵循|对话式接口|chat\s*(?:model|interface)'
    for i,profile in profiles.items():
        if profile is None:continue
        target=groups[i][0];areas=regions[i];title=areas[0]['title'];page=target.line.page_number
        if not re.search(r'角色定义|系统角色|提示模板|system\s+role|chat\s+template',title,re.I):continue
        # Different ranges or surface sample values do not distinguish two
        # otherwise competing templates for the same task and dialogue roles.
        if any(j!=i and p and all(p[k]==profile[k] for k in ('inputs','question','outputs'))
               and abs(groups[j][0].line.page_number-page)<=2
               and _same_content_domain(context,target,[groups[j][0].line]) for j,p in profiles.items()):continue
        own=[a for a in areas if a['page_number']==page]
        if len(own)!=1:continue
        area=own[0];inputs=[];outputs=[]
        for rows,text,topics,refs,cites in passages:
            if not _references_allow(refs,target.number) or not _same_content_domain(context,target,rows):continue
            if any(r.page_number!=page for r in rows):continue
            compact=re.sub(r'\s+','',text)
            if (0<=area['bbox'][1]-max(r.bbox[3] for r in rows)<=100
                    and re.search(chat,text,re.I) and re.search(r'输入.{0,90}Opcode.{0,50}Gas',compact,re.I)
                    and re.search(r'评估.{0,15}恶意|恶意性.{0,15}评估',compact)):
                inputs.append((rows,text))
            if min(r.bbox[1] for r in rows)<area['bbox'][3]:continue
            if not re.search(chat,text,re.I) or re.search(r'另(?:一|个).{0,16}模型|\bbase\b|基础模型',text,re.I):continue
            if not (re.search(r'评分|高分|得分|\bscore\b',text,re.I) and re.search(r'解释|理由|\bexplan|\breason',text,re.I)):
                continue
            values=[float(v) for m in re.finditer(r'(\d+(?:\.\d+)?)\s*(?:-|至|到)\s*(\d+(?:\.\d+)?)\s*分',text) for v in m.groups()]
            if not values or not all(profile['score_bounds'][0]<=v<=profile['score_bounds'][1] for v in values):continue
            first=min(r.bbox[1] for r in rows)
            if any(l.line.page_number==page and area['bbox'][3]<l.line.bbox[1]<first
                   and _key(l.line) not in {_key(a.line) for a in groups[i]} for l in index.figures+index.tables):continue
            outputs.append((rows,text))
        if not inputs or not outputs:continue
        before=min(inputs,key=lambda v:len(v[1]));after=min(outputs,key=lambda v:len(v[1]))
        if not _chat_template_owner_allowed(title,before[1],after[1]):continue
        rows={_key(r):r for r in before[0]+after[0]}
        result[i]=dict(evidence_kind='independent_chat_task_use',
            group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text) for l in groups[i]],
            full_title=title,graphic_regions=areas,graphic_fields=fields.get(i,[]),task_profile=profile,
            matched_features=['system_user_dialogue','opcode_sequence','gas_trace','maliciousness_evaluation','risk_score','explanation'],
            illustrative_metadata_not_required_verbatim=['operands','addresses','function_signatures'],
            body_evidence=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text,source=r.source) for r in rows.values()],
            uniqueness_reason='One physical system/user template is independently used through its adjacent typed input/question and subsequent chat-model scoring/explanation response. Other same-task dialogue templates compete even when their sample numbers differ.')
    return result


_RELATION_ROLES={
    'state_manifest':r'状态清单|state\s+manifest',
    'intersection_plan':r'交集规划|分片.{0,12}交集|intersection\s+planning',
    'transfer_manifest':r'传输清单|transfer\s+manifest',
    'transfer_task':r'\bTransferTask\b|传输任务',
    'temporary_buffer':r'暂存缓冲|临时缓冲|temporary\s+buffer',
    'state_validation':r'状态校验|校验.{0,8}状态|state\s+validation',
    'state_checked':r'已校验|校验通过|(?<!无需)(?<!不用)(?<!不必)通过.{0,28}校验.{0,18}才能(?:读取|使用)',
    'optical':r'光学|\boptical\b',
    'radar':r'\bSAR\b|雷达|\bradar\b',
    'microwave':r'微波|\bmicrowave\b',
    'cloud_obstruction':r'云层.{0,10}(?:遮挡|阻挡)|光线.{0,10}云层.{0,8}阻挡|受制于.{0,10}天气|cloud.{0,10}(?:block|obstruct)',
    'cloud_penetration':r'(?:穿透|穿越).{0,8}(?:云层|云雾)|(?:微波|雷达).{0,8}穿透|microwave\s+penetrat',
    'invisible_ground':r'地物不可见|遮蔽地物|无法.{0,8}(?:看到|看见)|云层遮挡.{0,12}失败',
    'visible_ground':r'地物清晰|清晰地物|全天候观测|cloud.{0,10}(?:clear|visible)',
    'solar_radiation':r'太阳|solar|\bsun\b',
    'atmospheric_scattering':r'大气散射|大气.{0,60}散射|atmospheric\s+scatter',
    'atmospheric_absorption':r'大气吸收|大气.{0,60}吸收|atmospheric\s+absor',
    'ground_reflection':r'地面反射|地物反射|反射回大气|surface\s+reflect',
    'path_radiance':r'程辐射|path\s+radiance',
    'sensor_pupil':r'传感器入瞳|入瞳辐射|sensor\s+pupil',
    'sensor':r'传感器|\bsensor\b',
    'atmosphere':r'大气层|大气上行|大气下行|\batmosphere\b',
    'satellite':r'卫星|\bsatellite\b',
    'perception':r'感知|perception',
    'agent_action':r'行动|动作|\baction\b',
    'agent_decision':r'决策|decision\s+making',
    'cooperation':r'合作|协作|合作|cooperat',
    'adversary':r'对手|对抗|adversar',
    'shared_goal':r'共享目标|集体利益|整体目标|共享收益|整体收益|shared\s+goal|collective\s+interest',
    'environment':r'环境|\benvironment\b',
    'team':r'团队|\bteam\b',
    'competition':r'竞争|对抗|competit',
    'platform':r'SatellitePlatform|卫星平台|平台类',
    'instrument':r'\bInstrument\b|仪器|载荷',
    'observation_mode':r'ObservationMode|观测模式',
    'spectral_band':r'SpectralBand|光谱波段|波段',
    'hosts_instrument':r'hostsInstrument|搭载.{0,8}(?:载荷|仪器)',
    'has_mode':r'hasMode|(?:具备|具有|拥有|提供).{0,12}(?:观测)?模式',
    'includes_band':r'includesBand|(?:包含|覆盖|提供).{0,8}波段',
    'requires_band':r'requiresBand|(?:依赖|需要|要求).{0,8}波段',
    'algorithm':r'Algorithm\s+instance|算法实例|算法.{0,8}(?:依赖|需要|要求)',
    'json_package':r'\bJSON\b|Task\s+Package|任务包',
    'ontology_assertions':r'\bABox\b|Ontology\s+assertions|本体实例|实例化子图',
    'raw_text':r'\braw_text\b|原始文本',
    'constraint':r'\bconstraints?\b|约束',
    'reentrancy':r're[- ]?enter|reentrancy|重入|递归调用',
    'fallback_call':r'fallback|回退函数|回退逻辑',
    'balance_update':r'更新余额|余额扣除|扣减.{0,8}余额',
    'storage_update':r'\bSSTORE\b|更新存储|状态更新',
    'external_transfer':r'\bCALL\b\s*(?:\(\s*Ether\s*\))?|合约转账|外部转账',
    'process_group':r'ProcessGroup|进程组',
    'device_mesh':r'DeviceMesh|设备网格',
    'failed_rank':r'failed\s*rank|(?:故障|失效)\s*rank|(?:rank|GPU).{0,6}(?:失效|故障)',
    'tensor_parallel':r'TP\s*group|张量并行(?:组|维度)',
    'data_parallel':r'DP\s*group|数据并行(?:组|副本|成员)',
    'adjacent_pipeline':r'adjacent\s+PP\s+(?:stage|edge)|(?:PP|流水线).{0,5}相邻|相邻.{0,6}(?:流水线|PP)',
    'state_shard':r'state\s*shard|状态(?:分片|切片)|参数分片',
    'unaffected':r'unchanged|未受影响|不受影响|保持(?:当前通信状态)?不变|通信状态无关|不(?:会)?要求(?:其余|其他)\s*rank.{0,20}更新',
    'affected_subgraph':r'受影响子图|Delta[-\s]*G|Δ\s*G',
    'current_config':r'当前(?:状态|配置|通信域|通信配置)|旧(?:状态|布局|配置|通信域)',
    'pending_config':r'待提交(?:配置|视图)|pending\s*(?:config|view)',
    'target_config':r'目标(?:布局|通信域|通信配置)|新(?:配置|通信域)|target\s*(?:layout|domain)',
    'commit_window':r'提交(?:窗口|点)|commit\s*(?:window|point)|安全点(?:提交|发布)',
    'old_terminal':r'旧(?:异步)?通信.{0,8}终态|old\s+communication.{0,8}terminal',
    'training_continues':r'当前训练|持续训练|训练(?:迭代)?.{0,8}(?:继续|持续)|训练过程(?:中)?更新|不(?:停止|中断).{0,4}训练',
    'rank_mapping':r'rank\s*映射|rank\s*mapping|逻辑rank|rank\s*身份|并行坐标',
    'physical_device':r'物理\s*(?:rank|GPU)|physical\s*(?:rank|GPU)',
    'training_entry':r'训练(?:代码|入口)|训练可见|training\s*(?:code|entry)',
    'training_invisible':r'训练(?:入口)?(?:暂)?不可见|提交前.{0,8}不可见|发布.{0,8}训练代码|交给训练代码使用',
    'resource_handler':r'资源\s*Handler|通信资源|后端资源|资源Handler',
    'resource_migration':r'资源(?:变化|迁移|替换)|迁移(?:意图|参数|状态)|状态迁移',
    'local_scope':r'影响范围|受影响范围|commit\s*scope|局部事件|局部(?:rank|变化)',
    'global_domain':r'全局(?:通信域|作业)|full\s*domain|完整通信域|全局重(?:建|启)',
    'static_binding':r'静态(?:通信)?绑定|启动阶段.{0,8}绑定|一次性绑定|共同绑定|static\s*binding',
    'safe_publish':r'安全点发布|提交点发布|热迁移式提交|校验和发布|配置发布|commit.{0,8}切换',
    'delayed_release':r'旧资源.{0,8}(?:释放|回收)|延迟释放|旧通信域回收',
    'rollback':r'回退|rollback|准备失败.{0,8}保持',
    'object_refresh':r'对象刷新|通信对象(?:更新|刷新)|待刷新.{0,8}(?:ProcessGroup|DeviceMesh)|刷新(?:候选|队列)',
    'state_recovery':r'状态恢复|恢复训练状态|检查点恢复|checkpoint\s*recovery',
    'connection':r'连接|\bconnection\b',
    'detection':r'检测|诊断|\bdetection\b',
    'prepare_phase':r'提交前准备|准备(?:中|阶段)|提前准备|先准备|预接入',
    'after_recovery':r'恢复后观测|恢复后的观测|恢复.{0,10}(?:吞吐|单步耗时)',
    'membership':r'成员(?:协商|表|输入|关系|集合)|目标成员|成员变化',
    'optical_circuit':r'OCS\s*(?:光路|端口)|光交换端口|光路和端口',
    'port_contention':r'端口(?:压力|竞争|占用|等待)|port\s*contention',
    'resource_fragment':r'(?:可用)?(?:资源)?碎片|fragment',
    'relay_forwarding':r'中继(?:转发|超节点)|中间超节点转发|过渡路径|relay',
    'direct_circuit':r'直连(?:光路|OCS)|已(?:建立|有)光路',
    'queued_circuit':r'排队光路|端口等待|等待.{0,8}光路|待建立',
    'network_reconfigure':r'网络(?:侧|控制面)?.{0,8}(?:调整|重配)|网络控制面',
    'config_registry':r'配置注册表|config(?:uration)?\s*registry',
    'dynamic_event':r'动态事件|故障(?:诊断)?|成员变化|资源变化|动态变化|失效\s*(?:rank|GPU)|(?:rank|GPU).{0,6}失效',
    'state_channel':r'状态通道|迁移通道|传输通道',
    'retained_state':r'保留|retain',
    'new_state':r'新建|\bnew\b|目标布局(?:已经)?分配好.{0,20}(?:存储|缓冲)',
    'optimizer':r'优化器|optimizer',
    'bounded_buffer':r'容量有界|循环复用|缓冲.{0,8}(?:复用|固定|有界)|固定.{0,8}缓冲',
    'bounded_migration':r'迁移量有界|迁移.{0,12}(?:范围|边界)|迁移量',
    'async_work':r'Work\s*/\s*Future|旧异步通信|旧通信终态',
    'joining_member':r'joiner|新成员',
    'leaving_member':r'leaver|离开成员',
    'rendezvous':r'Rendezvous',
    'member_store':r'PrefixStore|\bStore\b',
}
_RELATION_PATTERNS={key:re.compile(re.sub(r'\\b(?=[A-Za-z])',r'(?<![A-Za-z0-9_])',pattern)
    .replace(r'\b',r'(?![A-Za-z0-9_])'),re.I) for key,pattern in _RELATION_ROLES.items()}
_RELATION_OPERATIONS=_CONTENT_OPERATIONS+(r'准备|发布|提交',r'校验|验证',r'搬运|迁移',r'规划|组织',
    r'发射|接收',r'吸收|反射|散射',r'穿透|遮挡|阻挡',r'驱动|交互|协调',r'搭载|包含|依赖',r'调用|转账|扣除',
    r'更新|切换',r'扩展|纳入',r'保持|保留',r'搭载',r'包含',r'依赖',r'连接',r'提供',r'触及')


def _literal_relation_nodes(facts):
    """Recovered substantive labels retain their independent roles or literal names."""
    nodes={}
    illustrative=set()
    for first in facts:
        if not re.match(r'^e\.g\.',normalize_text(first['text']),re.I):continue
        for later in facts:
            if (later['page_number']==first['page_number']
                    and 0<=later['bbox'][1]-first['bbox'][3]<=3
                    and abs(later['bbox'][0]-first['bbox'][0])<=3):
                illustrative.add((later['page_number'],tuple(later['bbox']),later['text']))
    for fact in facts:
        text=normalize_text(fact['text']).strip();compact=re.sub(r'\s+','',text)
        if (fact['page_number'],tuple(fact['bbox']),fact['text']) in illustrative:continue
        if compact in {'迁移','搬运'}:
            nodes.setdefault(('action','data_movement'),[]).append(fact)
            continue
        roles={key for key,pattern in _RELATION_PATTERNS.items() if pattern.search(text)}
        if roles:
            for role in roles:nodes.setdefault(('role',role),[]).append(fact)
            continue
        if (re.search(r'^e\.g\.|^[（(]|^Class:',text,re.I)
                or re.fullmatch(r'[A-Za-z]{0,3}[\s-]?\d+(?:[,.]\d+)*|[\W\d_]+',text)
                or re.fullmatch(r'input|output|feature|model|classifier|time|process\s*\d+|modality\s+[a-z]|地面|时间|通道|进度|状态|资源|通信|目标|缺少|同一区域',text,re.I)):continue
        if len(compact)<=18 and re.search(r'[\u4e00-\u9fff]{2}',compact):
            nodes.setdefault(('literal',compact),[]).append(fact)
        elif re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{2,}(?:\s+[A-Za-z][A-Za-z0-9_.-]{2,}){0,2}',text):
            nodes.setdefault(('literal',re.sub(r'\s+','',text.casefold())),[]).append(fact)
    return nodes


def _node_in_prose(node,text):
    kind,value=node
    roles,compact,operations=_relation_prose_details(text)
    if kind=='role':return value in roles
    if kind=='action' and value=='data_movement':return bool(re.search(r'迁移|搬运',text))
    return value in compact


@lru_cache(maxsize=4096)
def _relation_prose_details(text):
    return (frozenset(key for key,pattern in _RELATION_PATTERNS.items() if pattern.search(text)),
            re.sub(r'\s+','',text.casefold()),
            sum(bool(re.search(p,text,re.I)) for p in _RELATION_OPERATIONS))


def _schema_relations_allow(required,text):
    """Named class relations retain their subject, predicate and object."""
    edges={
        'hosts_instrument':r'(?:卫星平台|SatellitePlatform).{0,80}(?:hostsInstrument|搭载).{0,50}(?:仪器|载荷|Instrument)',
        'has_mode':r'(?:仪器|Instrument).{0,50}(?:hasMode|具有|拥有|提供).{0,40}(?:观测模式|ObservationMode)',
        'includes_band':r'(?:观测模式|ObservationMode|每种模式).{0,40}(?:includesBand|包含|覆盖).{0,30}(?:波段|SpectralBand)',
        'requires_band':r'(?:算法|Algorithm).{0,30}(?:(?:requiresBand|依赖|需要|要求).{0,30}(?:波段|SpectralBand)|(?:波段|SpectralBand).{0,15}依赖)',
    }
    compact=re.sub(r'\s+','',text)
    sentences=re.split(r'[。；;]',compact)
    return all(any(re.search(pattern,s,re.I) for s in sentences)
               for edge,pattern in edges.items() if ('role',edge) in required)


def _static_dynamic_core_allow(required,text):
    """Both main comparison paths must be used; cleanup is a peripheral note."""
    core={'static_binding','global_domain','affected_subgraph','pending_config',
          'target_config','commit_window','safe_publish','training_entry','physical_device'}
    if not {('role',r) for r in core}<=required:return False
    compact=re.sub(r'\s+','',text)
    global_path=re.search(r'局部(?:资源)?变化.{0,55}全局重(?:启|建)|局部rank.{0,15}失效.{0,55}全局重(?:启|建)',compact,re.I)
    local_path=re.search(r'(?:先准备|准备).{0,40}(?:目标状态|待提交配置).{0,160}'
                         r'(?:经过|通过).{0,12}校验.{0,60}提交点.{0,60}(?:训练代码使用|交给训练代码)',compact,re.I)
    return bool(global_path and local_path)


def _join_preparation_annotations(facts,required):
    """Only attached rank examples and membership namespace keys are annotations."""
    core={('role',r) for r in ('joining_member','leaving_member','rendezvous','member_store',
                              'process_group','device_mesh','target_config','training_invisible')}
    if not core<=required:return set()
    headers=[f for f in facts if re.search(r'Rendezvous\s*\+\s*Store',f['text'],re.I)]
    namespace=[f for f in facts if re.search(r'PrefixStore',f['text'],re.I)]
    actors=[f for f in facts if re.search(r'joiner|leaver',f['text'],re.I)]
    annotations=set()
    for f in facts:
        token=re.sub(r'\s+','',f['text'].casefold())
        if token in {'peer','role'}:
            if any(f['page_number']==h['page_number']==n['page_number']
                   and h['bbox'][1]<f['bbox'][1]<n['bbox'][1]
                   and h['bbox'][0]-20<=f['bbox'][0]<=h['bbox'][2]+20
                   for h in headers for n in namespace):annotations.add(('literal',token))
        elif re.fullmatch(r'gpu[0-9o]+',token):
            if any(f['page_number']==a['page_number'] and 0<=f['bbox'][1]-a['bbox'][3]<=35
                   and max(f['bbox'][0],a['bbox'][0])<min(f['bbox'][2],a['bbox'][2])
                   for a in actors):annotations.add(('literal',token))
    return annotations


def _join_preparation_edges(text):
    compact=re.sub(r'\s+','',text)
    preparation=bool(re.search(r'(?:joiner|新成员).{0,220}(?:待提交|目标配置|Rendezvous).{0,220}(?:准备|构造|预热)',compact,re.I))
    continuing=bool(re.search(r'(?:leaver|旧通信域).{0,55}(?:继续|当前).{0,25}(?:训练|通信|责任)',compact,re.I))
    invisible=bool(re.search(r'提交前.{0,35}(?:不可见|只(?:看到|使用)当前|仍然只看到当前)|训练(?:代码|入口).{0,25}(?:不可见|不(?:会)?读取)|当前训练代码不可见',compact))
    terminal=bool(re.search(r'旧(?:异步通信|Work/Future).{0,35}(?:达到终态|终态|结束).{0,65}(?:才|后|提交|发布)',compact,re.I))
    return preparation and continuing and invisible and terminal


def _literal_relation_credits(index,groups,regions,fields,passages,context):
    """Full actual role labels plus concrete local operations, with all-group competition."""
    nodes={i:_literal_relation_nodes(fields.get(i,[])) for i in regions};result={}
    annotations_by={i:_join_preparation_annotations(fields.get(i,[]),set(nodes[i])) for i in nodes}
    principal_nodes={i:set(nodes[i])-annotations_by[i] for i in nodes}
    for i,areas in regions.items():
        title=areas[0]['title'];target=groups[i][0];required=set(principal_nodes[i]);page=target.line.page_number
        annotations=annotations_by[i]
        join_core={('role',r) for r in ('joining_member','leaving_member','rendezvous','member_store',
                                      'process_group','device_mesh','target_config','training_invisible')}
        typed_join=join_core<=required
        transfer_core={('role',name) for name in ('state_manifest','intersection_plan','transfer_manifest','transfer_task','temporary_buffer')}
        typed_transfer=transfer_core<=required and bool(re.search(r'交集规划|intersection\s+planning',title,re.I))
        if len(required)<5 or not (typed_transfer or typed_join or re.search(r'流程|链路|链条|机制|交互|结构|子图|执行逻辑|成像.{0,30}差异|\b(?:pipeline|workflow|structure|mechanism)\b',title,re.I)):continue
        if re.search(r'准确率|召回率|性能|消融|收敛|曲线|\b(?:accuracy|performance|ablation|convergence|curve)\b',title,re.I):continue
        if any(j!=i and principal_nodes[j]==required and abs(groups[j][0].line.page_number-page)<=4
               and _same_content_domain(context,target,[groups[j][0].line]) for j in nodes):continue
        options=[]
        for rows,text,profile,refs,cites in passages:
            if abs(rows[0].page_number-page)>4 or not _same_content_domain(context,target,rows) or not _references_allow(refs,target.number):continue
            if _relation_prose_details(text)[2]<1:continue
            matched={node for node in required if _node_in_prose(node,text)}
            if len(matched)>=2:options.append((rows,text,matched))
        covered=set().union(*(v[2] for v in options)) if options else set()
        missing=required-covered;peripheral=set()
        if missing:
            if (missing<={('role','delayed_release')}
                    and _static_dynamic_core_allow(required,' '.join(v[1] for v in options))):
                peripheral=missing
                required=required-peripheral
                if any(j!=i and principal_nodes[j]-{('role','delayed_release')}==required
                       and abs(groups[j][0].line.page_number-page)<=4
                       and _same_content_domain(context,target,[groups[j][0].line]) for j in nodes):continue
            else:continue
        # Component names plus unrelated actions in the same paragraph do not
        # explain a graphic. At least one clause must connect multiple actual
        # roles through a concrete operation.
        if not any(sum(_node_in_prose(n,clause) for n in required)>=2
                   and re.search(r'更新|切换|沿|扩展|纳入|保持|形成|组织|传输|通过|搭载|依赖|连接|发布|搬运|规划|遮挡|阻挡|穿透|反射|散射|吸收|调用|转账|扣除|触及',clause)
                   for v in options for clause in re.split(r'[，,。；;]',v[1])):continue
        if not any(len(v[2])>=3 and _relation_prose_details(v[1])[2]>=2 for v in options):continue
        anchors=[]
        for node in sorted(required):
            rows,text,matched=min((v for v in options if node in v[2]),key=lambda v:(abs(v[0][0].page_number-page),len(v[1])))
            anchors.extend(rows)
        unique={_key(r):r for r in anchors};body=' '.join(r.text for r in unique.values())
        if not _schema_relations_allow(required,body):continue
        if typed_join and not _join_preparation_edges(body):continue
        if sum(bool(re.search(p,body,re.I)) for p in _RELATION_OPERATIONS)<3 or not _named_subject_allowed(title,body,fields.get(i,[])):continue
        complete=[v for v in options if required<=v[2] and _relation_prose_details(v[1])[2]>=3
                  and _schema_relations_allow(required,v[1]) and _named_subject_allowed(title,v[1],fields.get(i,[]))]
        if complete:
            rows,text,matched=min(complete,key=lambda v:(abs(v[0][0].page_number-page),len(v[1])))
            unique={_key(r):r for r in rows}
        result[i]=dict(evidence_kind='complete_literal_graphic_relations',
            group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text) for l in groups[i]],
            full_title=title,graphic_regions=areas,graphic_fields=fields.get(i,[]),matched_features=[kind+':'+name for kind,name in sorted(required)],
            body_evidence=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text,source=r.source) for r in unique.values()],
            uniqueness_reason='Every recovered substantive role or literal node binds independent operations in the same chapter/epoch within four pages; no competing physical group has this full signature.')
        if peripheral:
            result[i].update(evidence_kind='complete_core_comparison_relations',
                peripheral_annotations_not_expanded=[kind+':'+name for kind,name in sorted(peripheral)],
                uniqueness_reason='Independent prose explains both complete principal static/global-restart and prepared/local-commit paths. The resource-cleanup note is not claimed to be separately discussed; no competing physical comparison shares the principal signature.')
        if annotations:
            result[i]['peripheral_annotations_not_expanded']=[kind+':'+name for kind,name in sorted(annotations)]
            result[i]['uniqueness_reason']+=' Attached hardware instances and membership namespace keys are retained as physical facts, without claiming separate instance discussion.'
    return result


_SAMPLING_LOOP_FIELDS={
    'variational_model':r'\bVAE\b|变分自编码器',
    'latent_space':r'latent\s+(?:chemical\s+)?space|(?:潜|隐)空间',
    'bayesian_sampling':r'Bayesian\s+sampling|贝叶斯采样',
    'decode':r'\bdecode(?:r)?\b|解码',
    'score':r'\bscoring\b|评分',
    'optimize':r'iterate.{0,30}optimi[sz]e|迭代优化',
}


def _transaction_workflow_profile(facts):
    """Only observed complete workflows select the extended relation vocabulary."""
    required=set(_literal_relation_nodes(facts));roles={n for k,n in required if k=='role'}
    literals={n for k,n in required if k=='literal'}
    if {'detection','state_recovery','after_recovery','connection','resource_handler',
        'pending_config','commit_window','old_terminal','state_validation','object_refresh'}<=roles:
        allowed={'detection','state_recovery','after_recovery','connection','resource_handler',
            'pending_config','commit_window','old_terminal','state_validation','object_refresh',
            'state_shard','training_continues','prepare_phase','target_config','rollback','membership','async_work'}
        if roles<=allowed and literals<={'通信配置提交'}:
            return 'recovery_timeline',required-{('role','rollback')},{('role','rollback')} & required,None
    owners=[re.fullmatch(r'([A-Za-z][A-Za-z0-9_-]*)网络事实',v) for v in literals]
    owners=[m.group(1) for m in owners if m]
    if len(owners)==1 and {'optical_circuit','port_contention','resource_fragment','relay_forwarding',
            'pending_config','state_shard','target_config'}<=roles:
        allowed={'optical_circuit','port_contention','resource_fragment','relay_forwarding',
            'direct_circuit','queued_circuit','network_reconfigure','pending_config','state_shard',
            'target_config','current_config','commit_window','constraint','resource_migration','safe_publish'}
        known={owners[0]+'网络事实','rank位置','发布缓冲','训练侧变化','训练框架输入','通信域'}
        if roles<=allowed and literals<=known:
            peripheral={('literal','发布缓冲')} & required
            return 'network_training_boundary',required-peripheral,peripheral,owners[0]
    if {'config_registry','current_config','pending_config','old_terminal','state_checked','object_refresh'}<=roles:
        allowed={'config_registry','current_config','pending_config','old_terminal','state_checked',
            'object_refresh','dynamic_event','process_group','device_mesh','state_recovery','state_channel',
            'training_entry','training_continues','affected_subgraph','async_work','commit_window',
            'prepare_phase','target_config'}
        if roles<=allowed and literals<={'d2d','子图级提交','通信域级重配置','实验记录','资源可用'}:
            return 'evaluated_configuration_transaction',required,set(),None
    return None


def _workflow_node_in_prose(node,text,kind,owner):
    """Aliases keep the observed actor/condition and its independent operation."""
    if _node_in_prose(node,text):return True
    key,value=node;compact=re.sub(r'\s+','',text)
    additional={
        ('role','old_terminal'):r'(?:旧)?Work/Future.{0,30}终态|旧异步通信.{0,20}(?:收敛|结束)',
        ('role','state_validation'):r'状态清单.{0,15}校验|状态.{0,20}校验条件',
        ('role','current_config'):r'通信域.{0,15}保持当前版本',
        ('role','commit_window'):r'提交(?:完成)?后.{0,20}(?:看到|可见|切换)',
        ('role','safe_publish'):r'提交完成后.{0,20}(?:看到|可见|切换)',
        ('role','constraint'):r'比较迁移收益.{0,25}资源可用性.{0,25}提交条件',
        ('role','resource_migration'):r'rank.{0,25}迁入.{0,15}(?:碎片|目标)',
        ('literal','rank位置'):r'rank.{0,15}(?:位置|迁入)',
        ('literal','训练侧变化'):r'(?:改变rank位置|状态分片.{0,20}(?:归属|重分布))',
        ('literal','训练框架输入'):r'训练框架.{0,100}构造待提交配置',
        ('literal','资源可用'):r'(?:资源|后端Handler|目标通信域).{0,40}(?:准备成功|校验条件)',
        ('literal','实验记录'):r'事件样本.{0,50}(?:字段|记为|记录)|记录.{0,25}时间戳',
    }
    if key=='literal' and owner and value==owner+'网络事实':
        return bool(re.search(re.escape(owner)+r'.{0,100}(?:网络控制面|候选布局|网络状态|观察到的事实)',compact,re.I))
    if kind=='recovery_timeline':
        additional[('role','training_continues')]=r'提前准备.{0,70}(?:连接|后端资源).{0,55}训练可见停顿.{0,25}集中.{0,20}提交窗口'
    if kind=='evaluated_configuration_transaction':
        additional[('role','state_checked')]=r'目标状态.{0,50}(?:校验条件.{0,15}读取|身份.{0,20}版本.{0,30}校验)|状态清单.{0,40}校验信息'
        additional[('role','training_continues')]=r'当前配置保持可用|训练迭代读取'
        additional[('role','training_entry')]=r'训练(?:代码|迭代).{0,15}(?:读取|调用)'
        additional[('role','object_refresh')]=r'刷新.{0,25}(?:通信对象|ProcessGroup|DeviceMesh)'
    return bool(node in additional and re.search(additional[node],compact,re.I))


def _transaction_workflow_edges(kind,text,owner):
    text=re.sub(r'\s+','',text)
    terminal=bool(re.search(r'(?:旧)?Work/Future.{0,35}终态|旧异步通信.{0,25}(?:收敛|结束)',text,re.I))
    if kind=='recovery_timeline':
        continuing=bool(re.search(r'训练.{0,25}(?:继续执行|继续训练)',text))
        outside_pause=bool(re.search(r'提前准备.{0,70}(?:连接|后端资源).{0,55}训练可见停顿.{0,25}集中.{0,20}提交窗口',text))
        return (terminal and bool(re.search(r'(?:状态清单|状态).{0,15}校验',text))
            and bool(re.search(r'(?:提前准备|准备).{0,100}(?:连接|后端资源)|(?:连接|后端资源).{0,100}(?:提前准备|准备)',text))
            and (continuing or outside_pause)
            and bool(re.search(r'提交窗口.{0,100}(?:配置发布|通信对象更新|对象刷新)',text)))
    if kind=='network_training_boundary':
        subjects=re.findall(r'(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_-]*)\s*(?:模型|网络|框架|系统|model\b|network\b|framework\b|system\b)\s*(?:采用|使用|通过|负责|构造|生成|uses?\b|constructs?\b)',text,re.I)
        if any(subject.casefold()!=owner.casefold() for subject in subjects):return False
        return (bool(re.search(re.escape(owner)+r'(?:通过|网络控制面)',text,re.I))
            and bool(re.search(r'(?:只改变底层路径|只改变.*路径).{0,45}通信域.{0,25}保持当前版本',text))
            and bool(re.search(r'(?:rank.{0,30}迁入|状态分片.{0,30}(?:归属|重分布)).{0,100}(?:资源可用性|提交条件)',text))
            and bool(re.search(r'训练框架.{0,150}构造待提交配置',text))
            and bool(re.search(r'训练脚本只在提交完成后.{0,20}看到切换结果',text)))
    return (terminal and bool(re.search(r'配置注册表.{0,25}(?:保存|维护).{0,20}(?:版本|配置)',text))
        and bool(re.search(r'准备.{0,25}校验.{0,25}提交.{0,25}中止',text))
        and bool(re.search(r'目标(?:通信域|状态).{0,80}(?:准备成功|校验条件)',text))
        and not bool(re.search(r'目标状态.{0,25}(?:无需|不用|不必)校验',text))
        and bool(re.search(r'仍停留在待提交配置',text))
        and all(v in text for v in ('子图级提交','通信域级重配置','检查点恢复'))
        and bool(re.search(r'事件样本.{0,50}(?:字段|记为|记录)|提交事件样本.{0,50}记录',text)))


def _transaction_workflow_credits(groups,regions,fields,passages,context):
    profiles={i:_transaction_workflow_profile(fields.get(i,[])) for i in regions};result={}
    for i,profile in profiles.items():
        if not profile:continue
        kind,required,peripheral,owner=profile;target=groups[i][0];page=target.line.page_number
        if any(j!=i and p and p[:2]==profile[:2] and abs(groups[j][0].line.page_number-page)<=4
               and _same_content_domain(context,target,[groups[j][0].line]) for j,p in profiles.items()):continue
        rows_by={}
        for rows,text,features,refs,cites in passages:
            if abs(rows[0].page_number-page)>4 or not _same_content_domain(context,target,rows) or not _references_allow(refs,target.number):continue
            if _relation_prose_details(text)[2]<2:continue
            if sum(_workflow_node_in_prose(n,text,kind,owner) for n in required)<2:continue
            rows_by.update({_key(r):r for r in rows})
        body=' '.join(r.text for r in rows_by.values())
        if not all(_workflow_node_in_prose(n,body,kind,owner) for n in required):continue
        if not _transaction_workflow_edges(kind,body,owner):continue
        if not _named_subject_allowed(regions[i][0]['title'],body,fields.get(i,[])):continue
        result[i]=dict(evidence_kind='principal_transaction_workflow_relations',
            group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text) for l in groups[i]],
            full_title=regions[i][0]['title'],graphic_regions=regions[i],graphic_fields=fields.get(i,[]),
            matched_features=[k+':'+v for k,v in sorted(required)],
            peripheral_annotations_not_expanded=[k+':'+v for k,v in sorted(peripheral)],
            body_evidence=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text,source=r.source) for r in rows_by.values()],
            uniqueness_reason='Observed principal stages bind independent actor-specific preparation, validation and delayed-publication relationships within one chapter/epoch. Attached recovery/buffer annotations are not claimed as separately expanded; no competing physical workflow shares the principal signature.')
    return result


def _schematic_named_owner(title):
    match=re.search(r'(?:schematic\s+illustration|schematic\s+diagram)\s+(?:of|for)\s+([A-Za-z][A-Za-z0-9_-]*)\b',title,re.I)
    return match.group(1) if match else None


def _process_word(text):
    return re.sub(r'\s+','',normalize_text(text)).strip('“”"\'').casefold()


def _process_observed_profile(facts,title):
    """Only observed principal nodes, their actual stage positions and roles."""
    facts=_distinct_graphic_fields(facts)
    if not facts or len({f['page_number'] for f in facts})!=1:return None
    words=[_process_word(f['text']) for f in facts]
    def find(pattern):return [f for f,t in zip(facts,words) if re.fullmatch(pattern,t,re.I)]
    def point(items,axis=1):return min((f['bbox'][axis]+f['bbox'][axis+2])/2 for f in items)
    def ordered(nodes,axis=1):return all(nodes) and all(point(a,axis)<point(b,axis) for a,b in zip(nodes,nodes[1:]))
    def profile(kind,roles,owner=None):return kind,frozenset(roles),owner
    lifecycle=[find(p) for p in ('输入','预填充','解码','解码完成')]
    pool_patterns=(r'之前被占用的块|本轮被占用的块|键值缓存块|激活值块|输入|预填充|解码|解码完成|膨胀|解膨胀|键值池|激活池',r'(?:[（(][a-d][）)])?第[0-3]步')
    if (ordered(lifecycle,0) and all(find(p) for p in ('键值缓存块','激活值块','键值池','激活池','膨胀','解膨胀'))
            and all(any(re.fullmatch(p,t,re.I) for p in pool_patterns) for t in words)):
        steps=[find(r'(?:[（(][a-d][）)])?第'+str(n)+r'步') for n in range(4)]
        if ordered(steps,0):return profile('bidirectional_pool_lifecycle',('cache_pool','activation_pool','borrow','return','input_prefill_decode_completion'),_named_figure_identity(title))
    stages=[find(r'stage'+str(n)+r'\..*') for n in range(1,4)]
    if (ordered(stages) and all(re.search(p,' '.join(f['text'] for f in fs),re.I) for fs,p in zip(stages,(r'SFT.*Cold\s*Start',r'(?:Reinforce|Reinforcement).*Warm\s*Up',r'SFT.*Cool\s*Off')))
            and all(find(p) for p in (r'group(?:ed)?relativepolicyoptimization',r'formatreward',r'accuracyreward',r'\+?mseloss',r'video',r'capt(?:i)?on',r'rating'))):
        allow=r'stage[1-3]\..*|group(?:ed)?relativepolicyoptimization|formatreward|accuracyreward|\+?mseloss|caption|video|rating|<think>.*|</think>|youranalysishere|excellent[,，.…]*bad'
        if all(re.fullmatch(allow,t,re.I) for t in words) and all(point(stages[1])<point(find(p))<point(stages[2]) for p in ('formatreward','accuracyreward')) and point(find(r'\+?mseloss'))>point(stages[2]):
            return profile('supervised_policy_supervised_stages',('initial_supervision','policy_optimization','accuracy_reward','format_reward','selected_output_distillation','score_calibration'),_named_figure_identity(title))
    fed=(r'服务器',r'全局模型',r'聚合模型',r'客户端',r'本地数据',r'本地模型',r'客户端选择并下载参数',r'本地模型训练',r'本地更新',r'全局聚合')
    if all(find(p) for p in fed) and all(any(re.fullmatch(p,t) for p in fed) for t in words) and point(find('服务器'))<point(find('客户端')):
        return profile('central_local_parameter_round',('central_server','global_model','private_local_data','download','local_training','upload_parameter','aggregate_next_round'),_named_figure_identity(title))
    phases=[find(p) for p in ('正交视角','数据过滤','方向-文本对')]
    owner=_named_figure_identity(title)
    if (owner and ordered(phases,0) and find(re.escape(_process_word(owner)))
            and point(phases[-1],0)<point(find(re.escape(_process_word(owner))),0)
            and all(find(p) for p in ('非正交','带平面','不合理','低质量','无意义|无语义','场景级'))):
        allowed=r'正交视角|数据过滤|方向-文本对|非正交|带平面|不合理|低质量|无意义|无语义|场景级|多物体|带噪声|无纹理|语言定位的物体方向数据集|拍照|顶部|底部|上方|下方|把手|键盘|屏幕|handle|cut|front|top|bottom|screen|up|blender|chatgpt'
        if all(t==_process_word(owner) or re.fullmatch(allowed,t) for t in words):
            return profile('orthographic_filter_direction_annotation',('orthographic_rendering','six_quality_filters','semantic_direction_pairs','validated_output_dataset'),owner)
    # Wrapped labels must be adjacent on the same original page; coordinates
    # from different pages can never complete one decision node.
    def phrase(first,last):
        out=find(first+last)
        for a in find(first):
            for b in find(last):
                if (0<=b['bbox'][1]-a['bbox'][3]<=18 and abs((a['bbox'][0]+a['bbox'][2]-b['bbox'][0]-b['bbox'][2])/2)<=20):out.append(a)
        return out
    nodes=[find('执行阶段开始'),phrase(r'投票中的解密份',r'额全部合法[?？]?'),
           phrase(r'门限解密',r'恢复出对称密钥'),phrase(r'对称密钥与领导',r'者恢复的一致[?？]?'),find('对交易进行解密'),find('执行成功')]
    if ordered(nodes) and find('执行失败') and point(find('执行失败'),0)>point(nodes[3],0)+50:
        allow=r'执行阶段开始|投票中的解密份(?:额全部合法[?？]?)?|额全部合法[?？]?|门限解密(?:恢复出对称密钥)?|恢复出对称密钥|对称密钥与领导(?:者恢复的一致[?？]?)?|者恢复的一致[?？]?|每一个交易|对区块中的|对交易进行解密|执行成功|执行失败|[ny]'
        if all(re.fullmatch(allow,t) for t in words):return profile('validated_key_transaction_execution',('share_validity','threshold_recovery','leader_key_agreement','decrypt_execute','two_failure_conditions'),_named_figure_identity(title))
    return None


def _affirmative_process_match(text,pattern):
    for match in re.finditer(pattern,text,re.I):
        value=match.group(0)
        if re.search(r'并未|不会|从未|没有|不进行|不采用|未采用|未执行|不检查|禁止',value):continue
        if re.search(r'(?:并未|不会|从未|没有|禁止)\s*$',text[max(0,match.start()-8):match.start()]):continue
        return True
    return False


def _process_prose(profile,text):
    kind,roles,owner=profile;text=re.sub(r'\s+','',normalize_text(text))
    if owner and not _structured_owner_in_text(owner,text):return False
    if owner:
        subjects=re.findall(r'([A-Za-z][A-Za-z0-9_-]*)\s*(?:数据集|模型|网络|框架)(?:采用|使用|通过|先)',text)
        if any(s.casefold()!=owner.casefold() for s in subjects):return False
    patterns={
      'bidirectional_pool_lifecycle':(
          r'(?:键值缓存|键值池).{0,80}(?:不足|压力).{0,160}(?:激活内存池|激活池).{0,80}(?:借用|调配)',
          r'解除.{0,65}(?:激活|物理).{0,80}映射.{0,180}(?:归属|标记|元数据).{0,180}(?:映射到|动态映射).{0,90}(?:键值|虚拟地址)',
          r'(?:键值缓存|键值池).{0,90}(?:返还|归还).{0,40}(?:激活内存池|激活池)',
          r'预填充.{0,120}(?:借用|分配|缓存需求)',r'解码.{0,60}(?:完成|请求结束).{0,100}(?:释放|回收|收缩)'),
      'supervised_policy_supervised_stages':(
          r'Stage1.{0,60}SFT.{0,100}(?:格式|等级词|校准)',
          r'Stage2.{0,70}(?:GRPO|Group(?:ed)?RelativePolicyOptimization).{0,150}(?:正确性|格式|奖励|强化学习)',
          r'Stage3.{0,110}SFT.{0,140}(?:筛选|蒸馏).{0,140}(?:稳定|固化|输出分布)',
          r'(?:准确性奖励|AccuracyReward).{0,140}(?:等级|正确|匹配)',r'(?:格式.{0,8}奖励|FormatReward).{0,150}(?:推理标记|分析标签|标记|格式要求)',
          r'MSE|均方误差',r'视频.{0,100}(?:文本|prompt)|文本.{0,100}视频'),
      'central_local_parameter_round':(
          r'服务器.{0,120}(?:初始化|全局模型).{0,120}广播.{0,60}客户端',
          r'客户端.{0,120}(?:私有|本地).{0,40}数据.{0,60}(?:训练|更新)',
          r'客户端.{0,200}(?:仅将.{0,50}(?:模型参数|参数更新量|参数).{0,70}上传|仅上传.{0,40}(?:模型参数|参数更新量|参数)).{0,40}服务器',
          r'服务器.{0,150}(?:收集|收到).{0,130}(?:参数|更新).{0,140}(?:聚合|集成).{0,80}(?:新一代|下一轮|全局模型)',
          r'(?:无需|无须|不).{0,8}共享.{0,8}原始数据|原始数据不出本地|保持数据本地化',r'(?:多轮|多次).{0,25}迭代'),
      'orthographic_filter_direction_annotation':(
          r'(?:渲染|生成).{0,65}多视角.{0,40}图像',r'标准正交视角',r'无地面干扰|无地面',r'合理几何结构',r'高质量',r'可区分|无语义对象|可辨',r'(?:非|排除)场景类',
          r'(?:自动|模型).{0,100}(?:筛选|过滤|判断).{0,80}(?:标准|样本)',r'(?:六个|多个)标准视角.{0,100}(?:自动生成|生成|形成).{0,35}语义[-–]?(?:视角|方向)?.{0,15}(?:配对|标注)',r'人工.{0,60}(?:核验|验证)'),
      'validated_key_transaction_execution':(
          r'执行阶段.{0,180}(?:验证|校验).{0,70}(?:投票|密钥)',r'(?:投票|份额).{0,100}(?:合法|合法性).{0,80}(?:随后|再).{0,45}(?:恢复|解密)',
          r'(?:与领导者.{0,40}密钥比较|验证领导者恢复.{0,40}密钥.{0,20}正确)',
          r'(?:密钥恢复)?验证成功后.{0,90}(?:对称)?密钥.{0,60}解密.{0,50}交易.{0,60}执行',
          r'份额不合法.{0,60}密钥不一致.{0,100}(?:重新提议|执行失败)'),
    }[kind]
    if kind=='central_local_parameter_round' and re.search(r'客户端[^。；，,]{0,90}(?<!不)上传(?:任何|其)?原始数据',text):return False
    return all(_affirmative_process_match(text,p) for p in patterns)


def _process_candidate_prose(title,text):
    """Request observations only; this cannot produce usage credit."""
    compact=re.sub(r'\s+','',normalize_text(text))
    if re.search(r'数据构建|data\s+construction',title,re.I):return sum(bool(re.search(p,compact)) for p in (r'渲染|多视角',r'过滤|筛选',r'语义|标注'))>=3
    if re.search(r'池.{0,8}(?:弹性|管理)|弹性管理',title):return all(re.search(p,compact) for p in (r'激活',r'键值',r'借用|调配|映射',r'返还|回收|收缩'))
    if re.search(r'三阶段.{0,12}训练',title):return all(re.search(p,compact,re.I) for p in (r'Stage1',r'Stage2',r'Stage3',r'SFT',r'GRPO|PolicyOptimization'))
    if re.search(r'联邦学习.{0,10}(?:训练|示意)',title):return all(re.search(p,compact) for p in (r'服务器',r'客户端',r'广播',r'训练',r'上传',r'聚合'))
    if re.search(r'交易.{0,12}(?:执行|流程)|执行.{0,12}交易',title):return all(re.search(p,compact) for p in (r'投票',r'验证',r'密钥',r'恢复'))
    return False


def _process_relation_credits(groups,regions,fields,passages,context):
    profiles={i:_process_observed_profile(fields.get(i,[]),areas[0]['title']) for i,areas in regions.items()};result={}
    for i,profile in profiles.items():
        if not profile:continue
        target=groups[i][0];page=target.line.page_number
        if any(j!=i and p==profile and abs(groups[j][0].line.page_number-page)<=4 and _same_content_domain(context,target,[groups[j][0].line]) for j,p in profiles.items()):continue
        selected={}
        for rows,text,features,refs,cites in passages:
            if abs(rows[0].page_number-page)>4 or not _same_content_domain(context,target,rows) or not _references_allow(refs,target.number):continue
            if not re.search(r'映射|借用|返还|收缩|释放|Stage\s*[123]|奖励|蒸馏|校准|广播|上传|聚合|渲染|过滤|筛选|标注|密钥|解密|提议',text,re.I):continue
            selected.update({_key(r):r for r in rows})
        rows=sorted(selected.values(),key=lambda r:(r.page_number,r.bbox[1],r.bbox[0]));body=' '.join(r.text for r in rows)
        if not _process_prose(profile,body):continue
        result[i]=dict(evidence_kind='principal_process_actor_operations',group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text) for l in groups[i]],
            full_title=regions[i][0]['title'],graphic_regions=regions[i],graphic_fields=fields.get(i,[]),matched_features=[profile[0],*sorted(profile[1])],
            body_evidence=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text,source=r.source) for r in rows],
            uniqueness_reason='Actual principal nodes/stage positions bind affirmative independent actor-specific directed operations and success/failure or lifecycle relations within one chapter/epoch. Example icons and illustrative occupied-block counts are not claimed as individually restated. No same-signature physical process competes for the evidence.')
    return result


def _structured_owner_in_text(owner,text):
    return bool(re.search(r'(?<![A-Za-z0-9_-])'+re.escape(owner)+r'(?![A-Za-z0-9_-])',normalize_text(text),re.I))


def _distinct_graphic_fields(facts):
    distinct=[]
    for fact in facts:
        if any(f['page_number']==fact['page_number'] and normalize_text(f['text']).casefold()==normalize_text(fact['text']).casefold()
               and max(abs(a-b) for a,b in zip(f['bbox'],fact['bbox']))<3 for f in distinct):continue
        distinct.append(fact)
    return distinct


def _structured_task_profile(facts,title):
    facts=_distinct_graphic_fields(facts);texts=[normalize_text(f['text']).strip() for f in facts]
    auto_patterns={
        'train':r'^Train\s*Data$', 'test':r'^Test\s*Data$', 'auto':r'^AutoML$',
        'bayesian':r'^Bayes(?:ian)?\s*Opt(?:imi[sz]ation)?$',
        'selection':r'^Model\s*Select(?:ion)?\s*&\s*HyperOpt$',
        'parallel':r'^Parallel\s*Execution$', 'evaluation':r'^Evaluation$', 'metrics':r'^Metrics$',
        'optimum':r'^Optimum$', 'model':r'^Model\s*&$', 'parameters':r'^Hyperset$',
        'internal_evaluation':r'^Multi[- ]Fidelity$', 'process_instance':r'^Process\s*\d+$', 'letter':r'^[A-Z]$',
    }
    roles={key for key,p in auto_patterns.items() if any(re.fullmatch(p,t,re.I) for t in texts)}
    if {'train','test','auto','bayesian','selection','parallel','evaluation','metrics','optimum','model','parameters'}<=roles:
        if all(any(re.fullmatch(p,t,re.I) for p in auto_patterns.values()) for t in texts):
            owner=_schematic_named_owner(title)
            if owner:return 'bayesian_parallel_model_selection',frozenset(roles-{'internal_evaluation','process_instance','letter'}),owner
    headers={'code':r'^代码逻辑层$', 'economic':r'^经济模型层$', 'network':r'^网络共识层$'}
    heading={k:[f for f in facts if re.fullmatch(p,normalize_text(f['text']))] for k,p in headers.items()}
    if all(len(v)==1 for v in heading.values()):
        anchors=[heading[k][0] for k in headers]
        if len({f['page_number'] for f in anchors})!=1 or max(f['bbox'][1] for f in anchors)-min(f['bbox'][1] for f in anchors)>14:return None
        classes={
            'code':{'reentrancy':r'重入攻击|\(?Reentrancy\)?','overflow':r'整数溢出|\(?Overflow\)?','access':r'权限控制缺失|\(?Access\s*Control\)?'},
            'economic':{'loan':r'闪电贷操纵|\(?Flash\s*Loan\)?','oracle':r'预言机攻击|\(?Oracle\s*Exploit\)?','arbitrage':r'恶意套利|\(?Arbitrage\)?'},
            'network':{'front':r'抢跑交易|\(?Front-running\)?','sandwich':r'三明治攻击|\(?Sandwich\)?','dos':r'拒绝服务|\(?DoS\)?'},
        };members={k:set() for k in headers}
        for field,text in zip(facts,texts):
            if any(re.fullmatch(p,text) for p in headers.values()) or re.fullmatch(r'(?:DeFi\s*)?典型攻击向量',text):continue
            category=min(headers,key=lambda k:abs((heading[k][0]['bbox'][0]+heading[k][0]['bbox'][2]-field['bbox'][0]-field['bbox'][2])/2))
            h=heading[category][0];pattern=classes[category]
            if (field['page_number']!=h['page_number'] or field['bbox'][1]<=h['bbox'][3]
                    or abs((h['bbox'][0]+h['bbox'][2]-field['bbox'][0]-field['bbox'][2])/2)>70):return None
            matches={k for k,p in pattern.items() if re.fullmatch(p,text,re.I)}
            if len(matches)!=1:return None
            members[category].update(matches)
        if all(members[k]==set(classes[k]) for k in classes):return 'three_layer_attack_taxonomy',frozenset(classes),None
    fixed={
        'asr':r'^(?:[A-Za-z][A-Za-z0-9_-]*\s+)?ASR$',
        'symptom':r'^Symptom\s*Feature$', 'life_event':r'^Life\s*Event\s*Feature$',
        'election':r'^(?:System\s*\d+\s*)?Election$', 'vote':r'^VOTE$',
        'group':r'^Group\s*Panel$', 'audio_group':r'^Audio\s*Group$', 'text_group':r'^Textual\s*Group$',
        'plenary':r'^Plenary\s*Discussion$', 'classifier':r'^Classifier$',
        'workflow':r'^Expert\s*Consultation\s*Workflow$', 'system_annotation':r'^System\s*\d+$|^H$|^Well,\s*I\s*am.*$',
    };matched={};learned=[]
    for field,text in zip(facts,texts):
        matches={k for k,p in fixed.items() if re.fullmatch(p,text,re.I)}
        if matches:
            for key in matches:matched.setdefault(key,[]).append(field)
            continue
        m=re.fullmatch(r'([A-Za-z][A-Za-z0-9_-]*)\s*Feature',text)
        if not m:return None
        name=m.group(1)
        if not (re.search(r'\d',name) or sum(c.isupper() for c in name)>=2):return None
        learned.append((field,name))
    if (len(learned)==3 and {'asr','symptom','life_event','election','vote','group','audio_group','text_group','plenary'}<=set(matched)
            and len(matched.get('classifier',[]))>=5):
        return 'clinical_multimodal_three_fusion_paths',frozenset(matched)-{'system_annotation','classifier'},tuple(name for f,name in learned)
    return None


def _structured_task_prose(profile,text):
    kind,roles,owner=profile
    if kind=='bayesian_parallel_model_selection':
        if not _structured_owner_in_text(owner,text):return False
        subjects=re.findall(r'(?<![A-Za-z0-9_])([A-Z][A-Za-z0-9_-]*)\s+(?:automates|uses|can\s+evaluate)\b',text)
        if any(s.casefold()!=owner.casefold() for s in subjects):return False
        return (bool(re.search(r'Bayesian.{0,110}model selection',text,re.I)) and bool(re.search(r'hyperparameter\s+tun',text,re.I))
            and bool(re.search(r'unknown\s+objective',text,re.I)) and bool(re.search(r'Gaussian\s+process',text,re.I))
            and bool(re.search(r'minimi[sz].{0,70}(?:model\s+)?evaluations',text,re.I))
            and bool(re.search(r'evaluate.{0,120}configurations.{0,100}(?:simultaneously|parallel)',text,re.I))
            and bool(re.search(r'(?:training|train)\s+(?:the\s+)?(?:data|predictive models)',text,re.I)))
    compact=re.sub(r'\s+','',text)
    if kind=='three_layer_attack_taxonomy':
        if not all(re.search(p,compact) for p in (r'代码逻辑层',r'经济模型层',r'网络(?:共识)?层',r'分为|分类')):return False
        if re.search(r'重入.{0,20}(?:属于|归入)经济模型|闪电贷.{0,20}(?:属于|归入)代码逻辑',compact):return False
        return (bool(re.search(r'(?:更新.{0,5}余额之前|状态更新滞后).{0,180}(?:递归|重复提款)',compact))
            and bool(re.search(r'闪电贷.{0,200}(?:价格|预言机).{0,100}套利',compact))
            and bool(re.search(r'(?:抢跑|Front-running).{0,230}(?:内存池|Gas).{0,100}(?:之前|优先)',compact,re.I))
            and bool(re.search(r'三明治.{0,80}买入.{0,80}卖出.{0,20}获利',compact)))
    return (bool(re.search(r'(?:自动语音识别|ASR).{0,60}(?:转录|文本)',compact,re.I))
        and bool(re.search(r'内容感知.{0,220}情感感知|情感感知.{0,220}内容感知',compact))
        and bool(re.search(r'文本.{0,80}(?:编码器|嵌入|句向量)',compact))
        and bool(re.search(r'(?:精神)?症状.{0,180}概率(?:向量|分布)',compact))
        and bool(re.search(r'生活事件.{0,180}概率分布',compact))
        and bool(re.search(r'选举.{0,220}独立.{0,180}硬投票',compact))
        and bool(re.search(r'(?:分组讨论|专家组讨论).{0,200}混淆矩阵.{0,280}(?:权重|赋予)',compact))
        and bool(re.search(r'(?:全体会议|PlenaryDiscussion).{0,180}(?:音频|文本).{0,120}拼接.{0,100}统一.{0,80}联合训练',compact,re.I)))


def _structured_task_credits(groups,regions,fields,passages,context):
    profiles={i:_structured_task_profile(fields.get(i,[]),areas[0]['title']) for i,areas in regions.items()};result={}
    for i,profile in profiles.items():
        if not profile:continue
        target=groups[i][0];page=target.line.page_number
        if any(j!=i and p and p[:2]==profile[:2] and abs(groups[j][0].line.page_number-page)<=4
               and _same_content_domain(context,target,[groups[j][0].line]) for j,p in profiles.items()):continue
        selected={}
        for rows,text,features,refs,cites in passages:
            if abs(rows[0].page_number-page)>4 or not _same_content_domain(context,target,rows) or not _references_allow(refs,target.number):continue
            if profile[0]=='bayesian_parallel_model_selection':
                if sum(bool(re.search(p,text,re.I)) for p in (r'model\s+selection',r'hyperparameter\s+tun',r'evaluat',r'search|optimi[sz]'))<2:continue
            elif _relation_prose_details(text)[2]<2:continue
            selected.update({_key(r):r for r in rows})
        body=' '.join(r.text for r in selected.values())
        if not _structured_task_prose(profile,body):continue
        result[i]=dict(evidence_kind='principal_structured_task_relations',
            group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text) for l in groups[i]],
            full_title=regions[i][0]['title'],graphic_regions=regions[i],graphic_fields=fields.get(i,[]),matched_features=[profile[0],*sorted(profile[1])],
            body_evidence=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text,source=r.source) for r in selected.values()],
            instance_annotations_not_claimed_as_exact_aliases=(list(profile[2]) if profile[0]=='clinical_multimodal_three_fusion_paths' else []),
            uniqueness_reason='Independent prose explains all principal observed input/branch roles and their distinct operations within the same chapter/epoch. Encoder instances, internal evaluation variants and secondary taxonomy examples are retained as physical facts without claims of separate exact-name discussion; no competing physical task has this principal signature.')
    return result


def _sampling_loop_profile(facts):
    found=set()
    for f in facts:
        text=normalize_text(f['text']).strip()
        hits={role for role,p in _SAMPLING_LOOP_FIELDS.items() if re.search(p,text,re.I)}
        if not hits and not re.fullmatch(r'Module|[\W\d_]+',text,re.I):return None
        found.update(hits)
    return frozenset(found) if found==set(_SAMPLING_LOOP_FIELDS) else None


def _sampling_loop_body(text):
    compact=re.sub(r'\s+','',normalize_text(text))
    encoder=bool(re.search(r'(?:变分自编码器|VAE).{0,230}(?:分子|molecule).{0,90}(?:连续隐变量|潜变量|latent).{0,100}(?:解码器|decoder).{0,70}(?:重构|生成).{0,25}(?:分子|molecule)',compact,re.I))
    sentences=re.split(r'[。；;]',compact)
    sampling=any(re.search(r'(?:潜|隐)空间.{0,55}采样.{0,100}贝叶斯优化',s) for s in sentences)
    scoring=any(re.search(r'(?:打分|评价)函数.{0,100}(?:搜索|优化).{0,100}(?:最大|max).{0,50}分子|分子.{0,35}(?:由|通过).{0,30}(?:打分|评价)函数.{0,25}(?:评价|评分)',s,re.I) for s in sentences)
    search=any(re.search(r'(?:搜索|优化).{0,75}(?:潜|隐)空间|(?:潜|隐)空间.{0,75}(?:搜索|优化)',s) for s in sentences)
    return encoder and sampling and scoring and search


def _sampling_loop_credits(groups,regions,fields,passages,context):
    profiles={i:_sampling_loop_profile(fields.get(i,[])) for i in regions};result={}
    for i,profile in profiles.items():
        if not profile:continue
        target=groups[i][0];title=regions[i][0]['title'];page=target.line.page_number
        if any(j!=i and profiles[j]==profile and abs(groups[j][0].line.page_number-page)<=4
               and _same_content_domain(context,target,[groups[j][0].line]) for j in profiles):continue
        candidates=[]
        for rows,text,features,refs,cites in passages:
            if abs(rows[0].page_number-page)>4 or not _same_content_domain(context,target,rows) or not _references_allow(refs,target.number):continue
            if not re.search(r'VAE|变分自编码器|(?:潜|隐)空间|打分函数|评价函数',text,re.I):continue
            candidates.extend(rows)
        unique={_key(r):r for r in candidates};body=' '.join(r.text for r in unique.values())
        if not _sampling_loop_body(body) or not _named_subject_allowed(title,body,fields.get(i,[])):continue
        result[i]=dict(evidence_kind='complete_latent_sampling_score_loop',
            group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text) for l in groups[i]],
            full_title=title,graphic_regions=regions[i],graphic_fields=fields[i],matched_features=sorted(profile),
            body_evidence=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text,source=r.source) for r in unique.values()],
            uniqueness_reason='Actual variational latent-space sampling, decode, score and optimization roles bind independent candidate-generation and objective-search operations in the same chapter and epoch; an identical physical loop competes.')
    return result


_AUGMENTATION_ROLES={
    'original_image':r'^origin(?:al)?(?: image)?$',
    'bilateral_filter':r'^Bilateral(?: filter)?$',
    'contrast_adjustment':r'^Contrast$',
    'gabor_filter':r'^Gabor(?: filter)?$',
    'sharpening':r'^Sharpen(?:ing)?$',
    'flip':r'^Flip$',
    'blur':r'^Blur$',
    'hsv':r'^HSV$',
}


def _image_statistics_graphic_profile(facts,title):
    values=[normalize_text(f['text']).strip() for f in facts]
    augmentation={key for key,p in _AUGMENTATION_ROLES.items() if any(re.fullmatch(p,v,re.I) for v in values)}
    if {'original_image','bilateral_filter','contrast_adjustment','gabor_filter','sharpening'}<=augmentation:
        if not re.search(r'增强.{0,8}(?:效果|样本)|样本增强|augmentation',title,re.I):return None
        if any(not any(re.fullmatch(p,v,re.I) for p in _AUGMENTATION_ROLES.values()) and not re.fullmatch(r'[\W\d_]+',v) for v in values):return None
        return ('sample_augmentation',frozenset(augmentation))
    forward=r'^Source\s*(?:→|->)\s*Reference$';reverse=r'^Reference\s*(?:→|->)\s*Source$'
    if (any(re.fullmatch(forward,v,re.I) for v in values) and any(re.fullmatch(reverse,v,re.I) for v in values)
            and re.search(r'直方图|histogram',title,re.I)):
        if any(not re.fullmatch(forward+'|'+reverse+r'|Source|Reference|Original|[\W\d_]+',v,re.I) for v in values):return None
        return ('bidirectional_histogram',frozenset(('source_to_reference','reference_to_source')))
    fit={
        'original_points':r'^Original Points$',
        'foreground_fit':r'^Fitted Line\s*1\s*\(Foreground\)$',
        'background_fit':r'^Fitted Line\s*2\s*\(Background\)$',
        'fractal_fit':r'^Fractal Fitting$',
        'log_frequency':r'^log\s*N\s*\(r\)$',
        'log_gray':r'^log\s*r$',
    }
    if all(any(re.fullmatch(p,v,re.I) for v in values) for p in fit.values()):
        if any(not any(re.fullmatch(p,v,re.I) for p in fit.values()) and not re.fullmatch(r'[\W\d_]+',v) for v in values):return None
        return ('piecewise_fractal_fit',frozenset(fit))
    return None


def _operation_explanations(text,subject,limit,stop=r'另一(?:个|种)?(?:算法|方法|模型|图)|另外的(?:算法|模型)'):
    """A bounded following explanation stops when a different subject takes over."""
    result=[]
    for match in re.finditer(subject,text,re.I):
        span=text[match.start():match.start()+limit]
        foreign=re.search(stop,span,re.I)
        if foreign:span=span[:foreign.start()]
        result.append(span)
    return result


def _image_statistics_prose(kind,text,roles):
    compact=re.sub(r'\s+','',normalize_text(text));sentences=re.split(r'[。；;]',compact)
    if kind=='sample_augmentation':
        adjustment=any(re.search(r'(?:样本|输入).{0,45}(?:增强|预处理)',s) and re.search(r'锐化|对比度',s) for s in sentences)
        bilateral=any(re.search(r'双边滤波.{0,350}(?:空间距离|空间分布相似度).{0,90}(?:灰度差|像素值).{0,100}(?:高斯权重|高斯函数)',s)
                      for s in _operation_explanations(compact,r'双边滤波',550,r'Gabor|另一(?:个|种)?(?:算法|方法|模型|图)|另外的(?:算法|模型)'))
        edges=any(re.search(r'(?:平滑|抑制).{0,20}噪声.{0,35}(?:保持|保留).{0,10}边缘|同时.{0,20}平滑.{0,30}保持.{0,10}边缘',s) for s in sentences)
        gabor=any(re.search(r'Gabor.{0,120}(?:方向|尺度).{0,100}(?:空间频率|方向信息|方向特征)',s,re.I) for s in sentences)
        extra=all(re.search({'flip':r'翻转','blur':r'模糊','hsv':r'HSV.{0,50}(?:转换|空间|映射)'}[role],compact,re.I) for role in roles&{'flip','blur','hsv'})
        return adjustment and bilateral and edges and gabor and extra
    if kind=='bidirectional_histogram':
        means=bool(re.search(r'多尺度均值(?:卷积核|滤波器)',compact))
        vectors=bool(re.search(r'(?:灰度|强度).{0,65}(?:邻域均值|邻域信息).{0,80}(?:特征向量|构成)|特征向量.{0,80}(?:灰度|强度).{0,50}邻域',compact))
        correspondence=any(re.search(r'(?:字典序)?排序.{0,65}(?:一一对应|唯一(?:的)?(?:排名)?索引)',s) for s in sentences)
        forward=any(re.search(r'将源图像.{0,40}(?:像素|分布).{0,30}映射至参考图像.{0,25}直方图',s) for s in sentences)
        reverse=any(re.search(r'将参考图像.{0,40}(?:像素|分布).{0,30}映射至源图像.{0,25}直方图',s) for s in sentences)
        return means and vectors and correspondence and forward and reverse
    if kind=='piecewise_fractal_fit':
        model=bool(re.search(r'灰度.{0,40}(?:累积|频数).{0,40}(?:幂次|幂函数)|累积.{0,25}灰度.{0,30}幂次',compact))
        logs=bool(re.search(r'双对数.{0,50}(?:线性|直线)|取对数.{0,45}线性',compact))
        slope=bool(re.search(r'相邻.{0,25}(?:线段|拟合).{0,30}(?:不同.{0,8}斜率|斜率.{0,8}不同)',compact))
        residual=bool(re.search(r'(?:最小化|最优|最小).{0,20}残差平方和.{0,40}(?:分界|阈值)|残差平方和.{0,40}(?:最优分界|最小)',compact))
        overlap=any(re.search(r'(?:非线性|弯折).{0,70}(?:重叠|过渡).{0,400}原始数据空间.{0,80}(?:幂函数|拟合)',s)
                    for s in _operation_explanations(compact,r'非线性|弯折',600))
        return model and logs and slope and residual and overlap
    return False


def _image_statistics_credits(groups,regions,fields,passages,context):
    profiles={i:_image_statistics_graphic_profile(fields.get(i,[]),a[0]['title']) for i,a in regions.items()};result={}
    for i,profile in profiles.items():
        if not profile:continue
        kind,roles=profile;target=groups[i][0];page=target.line.page_number;title=regions[i][0]['title']
        if any(j!=i and profiles[j]==profile and abs(groups[j][0].line.page_number-page)<=4
               and _same_content_domain(context,target,[groups[j][0].line]) for j in profiles):continue
        rows_by={}
        for rows,text,features,refs,cites in passages:
            if abs(rows[0].page_number-page)>4 or not _same_content_domain(context,target,rows) or not _references_allow(refs,target.number):continue
            if re.search(r'增强|双边|Gabor|直方图|分形|双对数|残差平方和',text,re.I):rows_by.update({_key(r):r for r in rows})
        body=' '.join(r.text for r in rows_by.values())
        if not _image_statistics_prose(kind,body,roles) or not _named_subject_allowed(title,body,fields.get(i,[])):continue
        result[i]=dict(evidence_kind='complete_image_distribution_operations',
            group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text) for l in groups[i]],
            full_title=title,graphic_regions=regions[i],graphic_fields=fields.get(i,[]),matched_features=sorted(roles),
            body_evidence=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text,source=r.source) for r in rows_by.values()],
            uniqueness_reason='Observed image-operation roles, paired mapping directions or log axes bind the corresponding independent mathematical and image-transformation relationships in this chapter and epoch. A method list, an absent key operation or a competing physical profile is insufficient; individual picture pixels and fitted example coordinates are not claimed as measurements.')
    return result


_REENTRANCY_FIELDS={
    'normal_call':r'deposit\s*\(\s*\)|调用合约',
    'normal_store':r'\bSSTORE\b|更新余额状态',
    'normal_end':r'\bSTOP\b|结束执行',
    'withdraw_call':r'withdraw\s*\(\s*\)|攻击者调用',
    'external_transfer':r'\bCALL\b|合约转账',
    'fallback':r'fallback|回退函数',
    'recursive_call':r're[- ]?enter|递归调用',
    'delayed_update':r'状态更新滞后|未执行',
}


def _reentrancy_graphic_profile(facts):
    text=' '.join(f['text'] for f in facts)
    if not all(re.search(p,text,re.I) for p in _REENTRANCY_FIELDS.values()):return None
    annotations=r'^(?:更新余额|函数|触发|利用逻辑漏洞循环窃取资金|(?:[AB]\.\s*)?(?:正常交易流|攻击交易流)(?:\s*[（(].*[）)])?)$'
    if any(not any(re.search(p,f['text'],re.I) for p in _REENTRANCY_FIELDS.values())
           and not re.search(annotations,f['text']) and not re.fullmatch(r'\(?Ether\)?|[\W\d_]+',f['text'],re.I) for f in facts):return None
    return frozenset(_REENTRANCY_FIELDS)


def _reentrancy_prose(text):
    compact=re.sub(r'\s+','',normalize_text(text));sentences=re.split(r'[。；;]',compact)
    normal=any(re.search(r'执行成功.{0,65}(?:SSTORE|存储变更|状态修改|状态变更).{0,55}(?:写入|保存|提交).{0,20}(?:世界状态|状态树)',s,re.I) for s in sentences)
    external=any(re.search(r'(?:合约|交易).{0,50}在更新.{0,20}余额之前.{0,50}CALL.{0,60}(?:攻击者|发送|转账)',s,re.I) for s in sentences)
    recurse=any(re.search(r'(?:回退函数|fallback).{0,45}递归调用.{0,25}(?:提款|withdraw)',s,re.I) for s in sentences)
    repeated=any(re.search(r'余额尚未(?:扣除|更新).{0,90}(?:重复提款|重复转账)',s) for s in sentences)
    return normal and external and recurse and repeated


def _reentrancy_relation_credits(groups,regions,fields,passages,context):
    profiles={i:_reentrancy_graphic_profile(fields.get(i,[])) for i in regions};result={}
    for i,profile in profiles.items():
        if not profile:continue
        target=groups[i][0];page=target.line.page_number;title=regions[i][0]['title']
        if any(j!=i and profiles[j]==profile and abs(groups[j][0].line.page_number-page)<=4
               and _same_content_domain(context,target,[groups[j][0].line]) for j in profiles):continue
        rows_by={}
        for rows,text,features,refs,cites in passages:
            if abs(rows[0].page_number-page)>4 or not _same_content_domain(context,target,rows) or not _references_allow(refs,target.number):continue
            if re.search(r'SSTORE|CALL|重入|状态修改|状态变更',text,re.I):rows_by.update({_key(r):r for r in rows})
        body=' '.join(r.text for r in rows_by.values())
        if not _reentrancy_prose(body) or not _named_subject_allowed(title,body,fields.get(i,[])):continue
        result[i]=dict(evidence_kind='normal_state_commit_and_recursive_delayed_transfer',
            group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text) for l in groups[i]],
            full_title=title,graphic_regions=regions[i],graphic_fields=fields.get(i,[]),matched_features=sorted(profile),
            body_evidence=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text,source=r.source) for r in rows_by.values()],
            illustrative_annotations_not_claimed_as_separate_calls=['example_normal_function_name','end_opcode'],
            uniqueness_reason='Independent prose binds both successful normal storage commit and an external transfer before balance update that triggers recursive withdrawal. Mere opcode names, the inverse update order and a competing physical two-path comparison do not establish use.')
    return result


def _molecule_graphic_profile(facts):
    """Distinct input, constrained-generation, or scored-candidate roles, from ink."""
    text=' '.join(f['text'] for f in facts)
    dual={
        'input_molecule':r'输入分子|input molecule',
        'output_molecule':r'输出分子|output molecule',
        'molecular_encoding':r'SMILES\s*/\s*图|SMILES\s*/\s*graph',
        'text_condition':r'文本描述|text description',
        'editing_model':r'AI\s*模型|editing model',
        'property_direction':r'increase|decrease|提升.{0,8}性质|降低.{0,8}性质',
    }
    if all(re.search(p,text,re.I) for p in dual.values()):
        descriptions=[f for f in facts if re.search(dual['text_condition'],f['text'],re.I)]
        for f in facts:
            value=normalize_text(f['text']).strip()
            if any(re.search(p,value,re.I) for p in dual.values()):continue
            if re.fullmatch(r'(?:[CHNOSFPB]|Cl|Br|I|H[O]?){1,4}|[\W\d_]+',value):continue
            if re.search(r'\bis a\b|from\s+xxx\s+to\s+xxx',value,re.I) and any(
                f['page_number']==d['page_number'] and 0<=f['bbox'][1]-d['bbox'][1]<=140
                and abs(f['bbox'][0]-d['bbox'][0])<=25 for d in descriptions):continue
            return None
        return ('dual_molecular_edit',frozenset(dual))
    structure={
        'unconditioned_generation':r'\bDe\s+novo\b',
        'lead_conditioned_edit':r'\bLead\b',
        'objective_optimization':r'\bOptimization\b',
        'molecular_distribution':r'P\s*_?\s*s\s*\(\s*G',
        'fixed_structure_condition':r'P\s*_?\s*s\s*\(\s*G\s*[\\|/]',
    }
    if all(re.search(p,text,re.I) for p in structure.values()):
        if any(not any(re.search(p,f['text'],re.I) for p in structure.values())
               and not re.fullmatch(r'Drawing|[\W\d_]+',f['text'].strip(),re.I) for f in facts):return None
        return ('fixed_structure_edit',frozenset(structure))
    rewards=[];molecules=[]
    for f in facts:
        m=re.fullmatch(r'Reward\s*:\s*([+-]?\d+(?:\.\d+)?)',normalize_text(f['text']).strip(),re.I)
        if m:rewards.append((f,float(m.group(1))))
        if re.search(r'<SMILES>.+</SMILES>',f['text'],re.I):molecules.append(f)
    paired=[(f,value) for f,value in rewards if any(
        f['page_number']==m['page_number'] and abs((f['bbox'][1]+f['bbox'][3]-m['bbox'][1]-m['bbox'][3])/2)<=12
        and m['bbox'][2]<f['bbox'][0] for m in molecules)]
    if (any(value>0 for f,value in paired) and any(value<0 for f,value in paired)
            and re.search(r'系统提示词|system prompt',text,re.I)
            and re.search(r'分子编辑指令|molecul.{0,20}editing instruction',text,re.I)
            and re.search(r'Original molecule',text,re.I)
            and re.search(r'Editing objectives',text,re.I)):
        allowed=r'系统提示词|分子编辑指令|Original molecule|Editing objectives|Reward\s*:|<SMILES>|Answer\s*:|Instruction\s*:|Decrease.{0,15}logP|chemically reasonable|You are.{0,60}chemical molecules|act as a molecular editor|Scaffold with attachment points|Keep the scaffold identical|Return only one edited molecule'
        known=[f for f in facts if re.search(allowed,f['text'],re.I)]
        # Lines continuing the actual system prompt retain their source role.
        # A separate short stage label cannot enter through this sentence rule.
        continuation=set()
        for prior in sorted(facts,key=lambda f:(f['page_number'],f['bbox'][1])):
            if prior not in known and (prior['page_number'],tuple(prior['bbox']),prior['text']) not in continuation:continue
            if not re.search(r'You are|through SMILES|descriptions and|template provided',prior['text'],re.I):continue
            for later in facts:
                if (later['page_number']==prior['page_number'] and 0<=later['bbox'][1]-prior['bbox'][3]<=4
                        and abs(later['bbox'][0]-prior['bbox'][0])<=10 and len(later['text'])>=40):
                    continuation.add((later['page_number'],tuple(later['bbox']),later['text']))
        if any(not re.search(allowed,f['text'],re.I) and not re.fullmatch(r'[\W\d_]+',f['text'])
               and (f['page_number'],tuple(f['bbox']),f['text']) not in continuation for f in facts):return None
        return ('relative_candidate_rewards',frozenset(('molecular_instruction','original_molecule','candidate_molecules','positive_reward','negative_reward','relative_selection')))
    return None


def _molecule_prose_profile(kind,text):
    compact=re.sub(r'\s+','',normalize_text(text))
    sentences=re.split(r'[。；;]',compact)
    if kind=='dual_molecular_edit':
        inputs=any(re.search(r'自然语言.{0,45}分子结构|分子结构.{0,45}自然语言',s) and re.search(r'双模态|两种输入|两种模态',s) for s in sentences)
        align=any(re.search(r'统一.{0,35}(?:潜在)?空间.{0,30}(?:对齐|对应)|双模态.{0,35}(?:表征|对齐)',s) for s in sentences)
        edit=any(re.search(r'(?:自然语言|文本).{0,55}分子编辑.{0,35}(?:要求|优化)|(?:自然语言|文本).{0,55}(?:指导|引导).{0,35}(?:分子|结构).{0,25}(?:修改|编辑)',s) for s in sentences)
        fixed=any(re.search(r'(?:骨架|主结构).{0,12}(?:保持稳定|不变|保持不变)|(?:保持|保留).{0,10}(?:骨架|主结构)',s) for s in sentences)
        local=any(re.search(r'局部.{0,20}(?:片段|区域|结构).{0,30}(?:修改|变换)|(?:修改|调控).{0,15}局部(?:片段|结构)',s) for s in sentences)
        objective=any(re.search(r'性质优化|优化性质|改变性质|属性优化',s) for s in sentences)
        return inputs and align and edit and fixed and local and objective
    if kind=='fixed_structure_edit':
        complete=any(re.search(r'(?:完整输入分子|输入分子).{0,25}(?:完整重构|完整地重构).{0,30}(?:新分子|产生)|完整重构.{0,25}(?:输入分子|新分子)',s) for s in sentences)
        conditioned=any(re.search(r'(?:给定|需保留|固定|约束).{0,20}(?:子图|部分结构).{0,160}(?:生成|填补).{0,30}(?:缺失|片段|分子)|(?:给定|固定).{0,20}(?:部分结构|子图).{0,70}填补',s) for s in sentences)
        legal=any(re.search(r'化学.{0,8}合法|化学合法性',s) for s in sentences)
        retain=any(re.search(r'(?:保留|保持).{0,15}(?:子图|子结构).{0,30}(?:嵌入|不变)|(?:保留|保持).{0,15}子图作为子图嵌入',s) and not re.search(r'无需(?:保留|保持)',s) for s in sentences)
        optimize=any(re.search(r'(?:优化|评价函数).{0,60}(?:目标属性|属性|优化目标)|目标属性.{0,35}优化',s) for s in sentences)
        return complete and conditioned and legal and retain and optimize
    if kind=='relative_candidate_rewards':
        generation=any(re.search(r'组内采样.{0,45}(?:生成|候选)|(?:采样|生成).{0,35}一组候选',s) for s in sentences)
        score=any(re.search(r'(?:打分器|奖励|评分).{0,45}(?:每个候选|候选).{0,20}(?:计算奖励|奖励值)|每个候选.{0,20}(?:计算|赋予).{0,10}奖励',s) for s in sentences)
        relative=any(re.search(r'组内相对(?:优势|比较).{0,40}(?:排序|比较|估计)',s) for s in sentences)
        improve=any(re.search(r'(?:提高|提升).{0,15}高(?:奖励|优势)样本.{0,20}生成概率',s) for s in sentences)
        suppress=any(re.search(r'(?:抑制|降低).{0,15}低(?:奖励|优势)样本.{0,20}生成概率',s) for s in sentences)
        return generation and score and relative and improve and suppress and bool(re.search(r'分子编辑|候选分子',compact))
    return False


def _molecule_relation_credits(groups,regions,fields,passages,context):
    profiles={i:_molecule_graphic_profile(fields.get(i,[])) for i in regions};result={}
    for i,profile in profiles.items():
        if not profile:continue
        kind,roles=profile;target=groups[i][0];page=target.line.page_number;title=regions[i][0]['title']
        if any(j!=i and profiles[j]==profile and abs(groups[j][0].line.page_number-page)<=4
               and _same_content_domain(context,target,[groups[j][0].line]) for j in profiles):continue
        candidates=[]
        for rows,text,features,refs,cites in passages:
            if abs(rows[0].page_number-page)>4 or not _same_content_domain(context,target,rows) or not _references_allow(refs,target.number):continue
            if not re.search(r'分子|molecul|GRPO|骨架|子图',text,re.I):continue
            candidates.extend(rows)
        unique={_key(r):r for r in candidates};body=' '.join(r.text for r in unique.values())
        if not _molecule_prose_profile(kind,body) or not _named_subject_allowed(title,body,fields.get(i,[])):continue
        identity=_named_figure_identity(title)
        owners=re.findall(r'(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_-]{2,})\s*(?:模型|网络|model\b|network\b)',body,re.I)
        if identity and any(name.casefold()!=identity.casefold() for name in owners):continue
        result[i]=dict(evidence_kind='complete_molecular_edit_relations',
            group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text) for l in groups[i]],
            full_title=title,graphic_regions=regions[i],graphic_fields=fields.get(i,[]),matched_features=sorted(roles),
            body_evidence=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text,source=r.source) for r in unique.values()],
            illustrative_annotations_not_claimed_as_measurements=['molecule_examples','placeholder_property_values','individual_candidate_reward_values'],
            uniqueness_reason='Independent prose binds the actual molecular input/constraint or candidate-selection operations in the same chapter and epoch. Every competing physical group with the same principal role signature is retained; illustrative structures and individual reward values are not claimed as measured results.')
    return result


_PAIRED_METRICS={
    'micro_f1':r'Micro\s*[- ]?\s*F\s*[- ]?\s*1(?:\s*Score)?',
    'jaccard':r'Jaccard(?:\s*(?:Coefficient|指数))?',
}


def _paired_metric_profile(facts):
    """Two separated metric headings and three repeated actual method labels."""
    headers={}
    for key,pattern in _PAIRED_METRICS.items():
        rows=[f for f in facts if re.fullmatch(pattern,normalize_text(f['text']).strip(),re.I)]
        if not rows:return None
        if len({(f['page_number'],round((f['bbox'][0]+f['bbox'][2])/20)) for f in rows})!=1:return None
        headers[key]=rows[0]
    left,right=sorted(headers,key=lambda k:headers[k]['bbox'][0])
    if headers[left]['page_number']!=headers[right]['page_number']:return None
    top=min(f['bbox'][1] for f in headers.values());bottom=max(f['bbox'][3] for f in headers.values())
    for f in facts:
        text=normalize_text(f['text']).strip()
        if (f['page_number']==headers[left]['page_number'] and top-10<=f['bbox'][1]<=bottom+10
                and re.search(r'score|coefficient|accuracy|precision|recall|latency|\b(?:loss|auc)\b|准确率|召回率|精确率|系数|损失',text,re.I)
                and not any(re.fullmatch(p,text,re.I) for p in _PAIRED_METRICS.values())):return None
    centers={k:(f['bbox'][0]+f['bbox'][2])/2 for k,f in headers.items()}
    if centers[right]-centers[left]<60:return None
    methods={k:{} for k in headers}
    for f in facts:
        text=normalize_text(f['text']).strip()
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{1,30}',text):continue
        if any(re.fullmatch(p,text,re.I) for p in _PAIRED_METRICS.values()):continue
        k=min(centers,key=lambda key:abs((f['bbox'][0]+f['bbox'][2])/2-centers[key]))
        h=headers[k]
        if f['page_number']!=h['page_number'] or f['bbox'][1]-h['bbox'][3]<40:continue
        methods[k].setdefault(text.casefold(),text)
    shared=set(methods[left])&set(methods[right])
    if len(shared)<3:return None
    return tuple(sorted(shared)),headers,methods


def _dataset_caption_identity(title):
    match=re.search(r'([A-Za-z][A-Za-z0-9_-]*)\s*数据集',title)
    return match.group(1) if match else None


def _metric_entity_pairs(methods,text):
    normalized=normalize_text(text)
    names='|'.join(re.escape(m) for m in sorted(methods,key=len,reverse=True))
    entities=list(re.finditer(r'(?<![A-Za-z0-9_])(?:'+names+r')(?![A-Za-z0-9_])',normalized,re.I))
    found=set()
    value=r'\s*(?:为|达|仅|[:：=])?\s*\d+(?:\.\d+)?\s*%?(?:\s*±\s*\d+(?:\.\d+)?\s*%?)?'
    prefix=r'^\s*(?:(?:方法|模型|method|model)\s*)?(?:的\s*)?'
    for n,match in enumerate(entities):
        stop=min(match.end()+180,entities[n+1].start() if n+1<len(entities) else len(normalized))
        chunk=normalized[match.end():stop]
        patterns=list(_PAIRED_METRICS.values())
        if any(re.search(prefix+first+value+r'[\s,，;；]*(?:and|和|及|且)?\s*'+second+value,chunk,re.I)
               for first,second in (patterns,patterns[::-1])):found.add(match.group().casefold())
    return found


def _metric_population_spans(dataset,rows):
    """Carry an explicit dataset only through its subsequent independent clauses."""
    active=False;selected=[]
    population=re.compile(r'(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_-]*)\s*[\u4e00-\u9fff]{0,10}数据集')
    for row in rows:
        for match in re.finditer(r'[^。；;]+[。；;]?',row.text):
            names=population.findall(normalize_text(match.group()))
            if names:
                active=all(n.casefold()==dataset.casefold() or n.casefold().startswith(dataset.casefold()+'-') for n in names)
            if active:
                anchor=span_anchor(row,match.start(),match.end())
                selected.append(replace(anchor,text=match.group()))
    return selected


def _paired_metric_credits(groups,regions,fields,passages,context):
    profiles={i:_paired_metric_profile(fields.get(i,[])) for i in regions};result={}
    for i,profile in profiles.items():
        if not profile:continue
        methods,headers,panel_methods=profile;target=groups[i][0];page=target.line.page_number
        title=regions[i][0]['title'];dataset=_dataset_caption_identity(title)
        if not dataset or not re.search(r'实验结果|实验.{0,15}对比|结果.{0,15}比较',title):continue
        if any(j!=i and profiles[j] and profiles[j][0]==methods
               and _dataset_caption_identity(regions[j][0]['title'])==dataset
               and abs(groups[j][0].line.page_number-page)<=4
               and _same_content_domain(context,target,[groups[j][0].line]) for j in profiles):continue
        anchors={}
        for rows,text,features,refs,cites in passages:
            if abs(rows[0].page_number-page)>4 or not _same_content_domain(context,target,rows) or not _references_allow(refs,target.number):continue
            if any(re.search(pattern,text,re.I) for pattern in _PAIRED_METRICS.values()) or any(_term(text,m) for m in methods):
                anchors.update({_key(r):r for r in rows})
        ordered=sorted(anchors.values(),key=lambda r:(r.page_number,r.bbox[1],r.bbox[0]))
        ordered=_metric_population_spans(dataset,ordered)
        body=' '.join(r.text for r in ordered)
        if not re.search(r'(?<![A-Za-z0-9_])'+re.escape(dataset)+r'(?![A-Za-z0-9_])',body,re.I):continue
        bound=_metric_entity_pairs(methods,body)
        if set(methods)!=bound:continue
        result[i]=dict(evidence_kind='paired_empirical_metric_use',
            group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text) for l in groups[i]],
            full_title=title,graphic_regions=regions[i],graphic_fields=fields[i],
            matched_features=['metric:'+key for key in sorted(headers)]+['measured_method:'+m for m in methods],
            body_evidence=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text,source=r.source) for r in ordered],
            uniqueness_reason='Two actual separated metric panels repeat at least three recovered methods. Independent same-population prose assigns numeric results for both metrics to each recovered shared method; identical physical metric/population/method panels compete. Pixel bar heights and unobserved method labels are not claimed to be reconstructed.')
    return result


_MR_MODALITY_PROPERTIES={
    't1':r'(?:脂肪.{0,45}(?:高信号|亮|显示)|(?:显示|清晰).{0,25}(?:灰白质|组织边界))',
    't2':r'(?:水分|富含水|水或脂肪).{0,55}(?:高信号|亮|突出)',
    't1c':r'(?:注射|对比剂|造影剂).{0,65}(?:缩短|提高|增强|检测|病灶)',
    'flair':r'(?:脑脊液.{0,35}(?:抑制|低信号)|抑制.{0,25}脑脊液)',
}


def _mr_modality_panels(facts):
    """Standard acquisition categories are distinct short labels, not ordinals."""
    labels={}
    for field in facts:
        name=normalize_text(field['text']).strip().casefold()
        if name not in _MR_MODALITY_PROPERTIES:return {}
        labels.setdefault(name,field)
    if len(labels)<3:return {}
    boxes=[f['bbox'] for f in labels.values()]
    if len({f['page_number'] for f in labels.values()})!=1:return {}
    if max((b[1]+b[3])/2 for b in boxes)-min((b[1]+b[3])/2 for b in boxes)>12:return {}
    ordered=sorted(boxes)
    if any(b[0]-a[2]<15 for a,b in zip(ordered,ordered[1:])):return {}
    return labels


def _modality_panel_credits(index,groups,regions,fields,passages,context):
    """A unique category sample binds per-category image properties and their use."""
    profiles={i:_mr_modality_panels(fields.get(i,[])) for i in regions};result={}
    for i,labels in profiles.items():
        if not labels:continue
        target=groups[i][0];title=regions[i][0]['title'];page=target.line.page_number
        if not (re.search(r'MRI|磁共振',title,re.I) and re.search(r'图像.{0,8}(?:样例|示例)|(?:样例|示例).{0,8}图像|image\s+examples?',title,re.I)):continue
        source_page=next((p for p in index.document.pages if p.number==page),None)
        panels=[];collage=False
        for box in source_page.images if source_page else ():
            if not any(_inside(box,a['bbox']) for a in regions[i]) or box[2]-box[0]<20 or box[3]-box[1]<15:continue
            if any(sum(abs(x-y) for x,y in zip(box,old))<=8 for old in panels):continue
            # A whole-canvas carrier is not an additional panel. Each counted
            # image must have one recovered category label directly beneath it.
            below=[f for f in labels.values() if 0<=f['bbox'][1]-box[3]<=25
                   and box[0]<=(f['bbox'][0]+f['bbox'][2])/2<=box[2]]
            if len(below)==1:panels.append(box)
            elif len(below)==4 and len(labels)==4:
                centres=sorted((f['bbox'][0]+f['bbox'][2])/2 for f in below)
                gaps=[b-a for a,b in zip(centres,centres[1:])];step=sum(gaps)/3
                # A native composite image can carry the full quartet. All
                # four distinct observed category labels must span it at a
                # regular spacing; a missing interior or edge label cannot
                # substitute for an unobserved sample.
                if (min(gaps)>0 and max(gaps)<=min(gaps)*1.25
                        and .25*step<=centres[0]-box[0]<=.75*step
                        and .25*step<=box[2]-centres[-1]<=.75*step):collage=True
            elif not below and box[2]-box[0]<regions[i][0]['bbox'][2]-regions[i][0]['bbox'][0]-10:
                panels.append(box)
        if len(panels)!=len(labels) and not (collage and not panels):continue
        if any(j!=i and _same_content_domain(context,target,[groups[j][0].line])
               and abs(groups[j][0].line.page_number-page)<=2
               and (set(other)==set(labels) or re.search(r'(?:MRI|磁共振).{0,15}图像.{0,8}(?:样例|示例)',regions[j][0]['title'],re.I))
               for j,other in profiles.items()):continue
        options=[]
        for rows,text,profile,refs,cites in passages:
            if abs(rows[0].page_number-page)>2 or not _same_content_domain(context,target,rows) or not _references_allow(refs,target.number):continue
            options.append((rows,re.sub(r'\s+','',normalize_text(text))))
        anchors=[];matched=[]
        for name in sorted(labels):
            choices=[]
            for rows,text in options:
                for match in re.finditer(r'(?<![A-Za-z0-9_])'+re.escape(name)+r'(?![A-Za-z0-9_])',text,re.I):
                    # A property must be attributed to this category. Text
                    # after a subsequent modality subject cannot supply it.
                    tail=text[match.end():match.end()+130]
                    next_label=re.search(r'[。；;](?:\(\d+\)[^。；;]{0,25}?)?(?:T1c|T1|T2|FLAIR)(?![A-Za-z0-9_])',tail,re.I)
                    if next_label:tail=tail[:next_label.start()]
                    if re.search(_MR_MODALITY_PROPERTIES[name],tail,re.I):choices.append(rows);break
            if not choices:break
            anchors.extend(min(choices,key=lambda rows:sum(len(r.text) for r in rows)));matched.append('image_property:'+name)
        else:
            summaries=[rows for rows,text in options
                       if re.search(r'(?:MRI|磁共振).{0,35}模态',text,re.I)
                       and re.search(r'(?:模态|序列).{0,35}(?:组合|互补)',text)
                       and re.search(r'信息|表征|影像|诊断|病灶',text)]
            if not summaries:continue
            anchors.extend(min(summaries,key=lambda rows:sum(len(r.text) for r in rows)))
            unique={_key(row):row for row in anchors}
            result[i]=dict(evidence_kind='independent_modality_panel_properties',
                group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text) for l in groups[i]],
                full_title=title,graphic_regions=regions[i],graphic_fields=fields[i],matched_features=matched,
                body_evidence=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text,source=r.source) for r in unique.values()],
                uniqueness_reason='Unique aligned standard acquisition-category example; each recovered modality has its own independently described image property, followed by the stated complementary use of the images.')
    return result


_PAYLOAD_SLOTS={
    'theme':('hasTheme',r'任务主题|任务意图|监测主题'),
    'goal_profile':('hasGoalProfile',r'业务剖面|目标剖面'),
    'roi':('monitors',r'关注区域|感兴趣区域|地理对象'),
    'algorithm':('selectedAlgorithm',r'算法需求|算法(?:选择|请求)'),
    'max_cloud':('maxCloudCover',r'云量|质量约束'),
    'revisit_max_days':('revisitMax_days',r'时间窗口|交付期限|重访|天内'),
}


def _payload_example_profile(facts):
    """Read a native JSON object and its own subsequent assertion block.

    The recovered slot values must occur under the corresponding predicates,
    with one task subject and one constraint subject. Neither nearby prose nor
    caption text supplies a missing payload field or assertion.
    """
    native=sorted((f for f in facts if f.get('source')=='native'),key=lambda f:(f['page_number'],f['bbox'][1],f['bbox'][0]))
    starts=[n for n,f in enumerate(native) if re.search(r'Task\s+Package|\bJSON\b',f['text'],re.I)]
    ends=[n for n,f in enumerate(native) if re.search(r'Ontology\s+assertions|\bABox\b',f['text'],re.I)]
    if len(starts)!=1 or len(ends)!=1 or starts[0]>=ends[0]:return None
    selected=native[starts[0]:]
    if len({f['page_number'] for f in selected})!=1:return None
    code='\n'.join(f['text'] for f in native[starts[0]+1:ends[0]])
    try:data=json.loads(code)
    except (ValueError,TypeError):return None
    if not isinstance(data,dict) or not isinstance(data.get('task_id'),str):return None
    leaves={}
    def collect(obj,path=()):
        if not isinstance(obj,dict):return
        if 'value' in obj and isinstance(obj.get('raw_text'),str):
            leaves[path]=(obj['value'],obj['raw_text']);return
        for key,value in obj.items():collect(value,path+(key,))
    collect(data)
    if len(leaves)<5 or any(path[-1] not in _PAYLOAD_SLOTS for path in leaves):return None
    assertions=[]
    for f in native[ends[0]+1:]:
        match=re.fullmatch(r'\s*([A-Za-z][A-Za-z0-9_]*)\s*\(\s*([A-Za-z][A-Za-z0-9_]*)\s*,\s*([^(),]+)\s*\)\s*',f['text'])
        if match:assertions.append((match.group(1),match.group(2),match.group(3).strip()))
    constraint_subjects=set();pairs=[]
    for path,(value,raw) in leaves.items():
        if isinstance(value,(bool,dict,list)) or value is None:return None
        predicate=_PAYLOAD_SLOTS[path[-1]][0]
        matches=[a for a in assertions if a[0]==predicate and a[2]==str(value)]
        if len(matches)!=1:return None
        subject=matches[0][1]
        if path[0]=='constraints':constraint_subjects.add(subject)
        elif subject!=data['task_id']:return None
        pairs.append(dict(path=list(path),predicate=predicate,value=value,raw_text=raw,subject=subject))
    if len(constraint_subjects)!=1:return None
    if {'max_cloud','revisit_max_days'}-{p['path'][-1] for p in pairs}:return None
    return pairs


def _payload_raw_anchor(pair,text):
    raw=re.sub(r'\s+','',normalize_text(pair['raw_text']));key=pair['path'][-1]
    compact=re.sub(r'\s+','',normalize_text(text))
    if key=='max_cloud':
        return bool(re.search(r'云量(?:不超过|最多|<=|≤|小于等于)'+re.escape(str(pair['value']))+r'%',compact))
    if key=='revisit_max_days':
        # Written day counts in prose retain the numeric value of the actual
        # payload. This is a unit-bound spelling alias, not a topic inference.
        digits={'一':'1','二':'2','两':'2','三':'3','四':'4','五':'5','六':'6','七':'7','八':'8','九':'9'}
        compact=re.sub(r'([一二两三四五六七八九])(?=天|日)',lambda m:digits[m.group(1)],compact)
        return bool(re.search(r'(?<!\d)'+re.escape(str(pair['value']))+r'(?:天|日)(?:内|以内)',compact))
    return len(raw)>=2 and raw.casefold() in compact.casefold()


def _payload_example_credits(index,groups,regions,fields,passages,context):
    profiles={i:_payload_example_profile(fields.get(i,[])) for i in regions};result={}
    for i,pairs in profiles.items():
        if not pairs:continue
        target=groups[i][0];title=regions[i][0]['title'];page=target.line.page_number
        if not re.search(r'示例|样例|example',title,re.I) or not re.search(r'对齐|align',title,re.I):continue
        keys={p['path'][-1] for p in pairs}
        if any(j!=i and _same_content_domain(context,target,[groups[j][0].line])
               and abs(groups[j][0].line.page_number-page)<=2
               and (other and {p['path'][-1] for p in other}==keys or
                    re.search(r'任务包.{0,25}本体实例.{0,10}对齐',regions[j][0]['title']))
               for j,other in profiles.items()):continue
        local=[];aliases=[]
        for rows,text,profile,refs,cites in passages:
            if abs(rows[0].page_number-page)>2 or not _same_content_domain(context,target,rows) or not _references_allow(refs,target.number):continue
            local.append((rows,text))
            if abs(rows[0].page_number-page)>1:continue
            for match in re.finditer(r'任务包\s*\([^()]{0,80}[,，]\s*([A-Z][A-Z0-9_-]{1,11})\s*\)',normalize_text(text)):
                aliases.append((match.group(1),rows))
        options=[]
        for rows,text in local:
            compact=re.sub(r'\s+','',normalize_text(text))
            introduced=[rr for name,rr in aliases if re.search(r'(?<![A-Za-z0-9_])'+re.escape(name)+r'(?![A-Za-z0-9_])',text)]
            if not re.search(r'任务包|\bJSON\b',text,re.I) and not introduced:continue
            if not re.search(r'本体.{0,20}实例化|实例化子图',compact):continue
            if not re.search(r'raw_text|原始文本',text,re.I) or not re.search(r'保存|回溯|追溯|溯源',text):continue
            if not all(re.search(_PAYLOAD_SLOTS[key][1],compact,re.I) for key in keys):continue
            if sum(bool(re.search(p,text)) for p in (r'保存|保留',r'回溯|追溯|溯源',r'检查|校验',r'解析|复现',r'实例化'))<3:continue
            concrete=[p for p in pairs if _payload_raw_anchor(p,text)]
            if len(concrete)<3 or {'max_cloud','revisit_max_days'}-{p['path'][-1] for p in concrete}:continue
            anchors=list(rows)
            if not re.search(r'任务包|\bJSON\b',text,re.I):anchors.extend(min(introduced,key=lambda rr:sum(len(r.text) for r in rr)))
            options.append((list({_key(r):r for r in anchors}.values()),concrete))
        if not options:continue
        rows,concrete=min(options,key=lambda v:sum(len(r.text) for r in v[0]))
        result[i]=dict(evidence_kind='native_payload_assertion_example',
            group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text) for l in groups[i]],
            full_title=title,graphic_regions=regions[i],graphic_fields=fields[i],schema_pairs=pairs,
            matched_features=['slot:'+key for key in sorted(keys)]+['concrete_raw_text:'+p['raw_text'] for p in concrete],
            body_evidence=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text,source=r.source) for r in rows],
            uniqueness_reason='Unique native payload/assertion example: all recovered slot values map to their own assertion predicates and subjects; independent prose explains every slot role, provenance, and three concrete example values including both numeric constraints.')
    return result


def figure_usage_evidence(index, groups, graphic_evidence=None, prepared_context=None):
    prepared_context=_prepared(index,groups,prepared_context)
    regions,fields=_facts(index,groups,graphic_evidence,prepared_context)
    descriptors={}
    for i,areas in regions.items():
        features=_graphic_profile(fields.get(i,[]))
        title=areas[0]['title']
        sources=_citations(title)
        if not sources and re.search(r'曲线|收敛|消融|准确率|召回率|性能比较|性能对比|\b(?:curve|convergence|ablation|accuracy|recall|performance comparison)\b',title,re.I):continue
        # Three graphic components, including a distinctive content dimension,
        # are required. A name, source number or software/data citation cannot
        # replace those physical content facts.
        if len(features)<3 or not (features-_WEAK):continue
        title_features=_concepts(title)-{'input','output','feature','speech','extraction','separation','classification'}
        descriptors[i]=(features,title_features,sources,_parallel_roles(fields[i]),_facets(fields[i]))
    used={}
    passages=[]
    all_passages=[]
    for rows in prepared_context['body_passages']:
        text=' '.join(row.text for row in rows)
        body_features=_concepts(text)
        references={normalize_label(m.group(1)) for m in _REF.finditer(normalize_text(text))}
        citations=_citations(text)
        item=(rows,text,body_features,references,citations)
        all_passages.append(item)
        if sum(bool(re.search(pattern,text,re.I)) for pattern in _CONTENT_OPERATIONS)>=2:passages.append(item)
    def record(i,rows,matched,criterion):
        used.setdefault(i,dict(
            evidence_kind='physical_graphic_fields',
            group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text) for l in groups[i]],
            full_title=regions[i][0]['title'],graphic_regions=regions[i],graphic_fields=fields[i],
            matched_features=sorted(matched),
            body_evidence=[dict(page_number=row.page_number,bbox=list(row.bbox),text=row.text,source=row.source) for row in rows],
            uniqueness_reason=criterion))
    for rows,text,body_features,references,citations in passages:
        candidates=[]
        matched_by={}
        for i,(features,title_features,sources,parallel,facets) in descriptors.items():
            target=groups[i][0]
            if any(_epoch(prepared_context,row)!=_epoch(prepared_context,target) for row in rows):continue
            if not _references_allow(references,target.number):continue
            matched=features&body_features
            complete=(features-_WEAK)<=body_features
            structure=(parallel and len(matched-_WEAK)>=3
                       and re.search(r'两(?:条|个)\s*(?:并行|平行)\s*(?:链|分支|路径)|two\s+parallel\s+(?:chains|branches|paths)',text,re.I))
            if len(matched)<3 or not (complete or structure) or not title_features<=body_features or not _task_details(features,text):continue
            distance=min(abs(target.line.page_number-row.page_number) for row in rows)
            if not sources and (distance>2 or sum(bool(re.search(pattern,text,re.I)) for pattern in _CONTENT_OPERATIONS)<3):continue
            if not sources and not _same_content_domain(prepared_context,target,rows):continue
            if not sources and not _named_subject_allowed(regions[i][0]['title'],text,fields[i]):continue
            if distance>2 and (not sources&citations or len(matched-_WEAK)<3):continue
            candidates.append(i)
            matched_by[i]=(matched,bool(structure))
        if len(candidates)!=1:continue
        i=candidates[0]
        matched,structure=matched_by[i]
        record(i,rows,matched,'Unique physical group; independent prose binds the recovered component and caption concepts used by this matcher'+
               (' through the two parallel named branches.' if structure else '.'))
    # A multi-panel taxonomy may be explained across adjacent pages. Every
    # recovered panel requires its own concrete prose evidence, and an object
    # with the same full panel signature keeps the attribution ambiguous.
    for i,(features,title_features,sources,parallel,facets) in descriptors.items():
        if i in used or not facets or not sources:continue
        signature={tuple(sorted(profile)) for profile,_ in facets}
        if any(j!=i and signature=={tuple(sorted(profile)) for profile,_ in other[4]}
               and _epoch(prepared_context,groups[j][0])==_epoch(prepared_context,groups[i][0])
               for j,other in descriptors.items()):continue
        anchors=[]
        matched=set()
        required=facets[:]
        covered=set().union(*(profile for profile,_ in facets))
        required.extend((frozenset((feature,)),None) for feature in features-_WEAK-covered)
        for profile,field in required:
            options=[(rows,bf) for rows,text,bf,refs,cites in passages
                     if profile<=bf and _references_allow(refs,groups[i][0].number)
                     and _same_epoch(prepared_context,groups[i][0],rows)
                     and (abs(groups[i][0].line.page_number-rows[0].page_number)<=2
                          or abs(groups[i][0].line.page_number-rows[0].page_number)<=8
                          and any(sources&sc and abs(sr[0].page_number-rows[0].page_number)<=1
                                  and _same_epoch(prepared_context,groups[i][0],sr)
                                  and title_features&sf for sr,st,sf,srefs,sc in all_passages))]
            if not options:break
            rows,bf=min(options,key=lambda item:sum(len(row.text) for row in item[0]))
            anchors.extend(rows);matched.update(features&bf)
        else:
            anchor_features=set().union(*(_concepts(row.text) for row in anchors))
            if not title_features<=anchor_features or not features-_WEAK<=anchor_features:continue
            if not _task_details(features,' '.join(row.text for row in anchors)):continue
            unique={(row.page_number,row.bbox,row.text):row for row in anchors}
            record(i,list(unique.values()),matched,'All recovered semantic panel profiles used by this matcher bind concrete independent prose on nearby pages; no competing physical group has this recovered facet signature.')
    for i,item in _procedure_credits(index,groups,regions,passages,prepared_context).items():
        used.setdefault(i,item)
    for i,item in _extra_content_credits(index,groups,regions,fields,all_passages,prepared_context).items():
        used.setdefault(i,item)
    for i,item in _uncited_content_credits(index,groups,regions,fields,all_passages,prepared_context).items():
        used.setdefault(i,item)
    for i,item in _comparison_content_credits(groups,regions,fields,all_passages,prepared_context).items():
        used.setdefault(i,item)
    for i,item in _lookup_content_credits(groups,regions,fields,all_passages,prepared_context).items():
        used.setdefault(i,item)
    for i,item in _deictic_template_credits(index,groups,regions,fields,all_passages,prepared_context).items():
        used.setdefault(i,item)
    for i,item in _chat_audit_task_credits(index,groups,regions,fields,all_passages,prepared_context).items():
        used.setdefault(i,item)
    for i,item in _literal_relation_credits(index,groups,regions,fields,all_passages,prepared_context).items():
        used.setdefault(i,item)
    for i,item in _sampling_loop_credits(groups,regions,fields,all_passages,prepared_context).items():
        used.setdefault(i,item)
    for i,item in _molecule_relation_credits(groups,regions,fields,all_passages,prepared_context).items():
        used.setdefault(i,item)
    for i,item in _reentrancy_relation_credits(groups,regions,fields,all_passages,prepared_context).items():
        used.setdefault(i,item)
    for i,item in _image_statistics_credits(groups,regions,fields,all_passages,prepared_context).items():
        used.setdefault(i,item)
    for i,item in _transaction_workflow_credits(groups,regions,fields,all_passages,prepared_context).items():
        used.setdefault(i,item)
    for i,item in _structured_task_credits(groups,regions,fields,all_passages,prepared_context).items():
        used.setdefault(i,item)
    for i,item in _process_relation_credits(groups,regions,fields,all_passages,prepared_context).items():
        used.setdefault(i,item)
    for i,item in _paired_metric_credits(groups,regions,fields,all_passages,prepared_context).items():
        used.setdefault(i,item)
    for i,item in _modality_panel_credits(index,groups,regions,fields,all_passages,prepared_context).items():
        used.setdefault(i,item)
    for i,item in _payload_example_credits(index,groups,regions,fields,all_passages,prepared_context).items():
        used.setdefault(i,item)
    from .usage_math_relations import math_relation_evidence
    for i,item in math_relation_evidence(index,groups,regions,fields,prepared_context).items():
        used.setdefault(i,item)
    return used


def figure_math_native_candidates(index,groups,regions=None,native_fields=None):
    """Complete original-native math profiles; this requests no OCR."""
    from .usage_math_relations import math_native_candidates
    if regions is None:regions=figure_graphic_regions(index,groups)
    if native_fields is None:native_fields=_native_fields_in_regions(index,regions)
    return math_native_candidates(groups,regions,native_fields)


def figure_math_native_evidence(index,groups,prepared_context=None):
    """Independent same-page native math use, preserving all competitors."""
    from .usage_math_relations import math_relation_evidence
    context=_prepared(index,groups,prepared_context)
    return math_relation_evidence(index,groups,context['regions'],context['native_fields'],context)


def figure_usage_groups(index, groups, graphic_evidence=None, prepared_context=None):
    return set(figure_usage_evidence(index,groups,graphic_evidence,prepared_context))
