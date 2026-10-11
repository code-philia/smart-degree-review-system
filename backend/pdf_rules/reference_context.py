"""Distinguish local figure/table citations from terms and external sources."""
import re


_GRAPH_NOUN = r'(?:结构|合成|同质|异质|随机|二部|完全|有向|无向|知识|计算|关系)'
_PROPORTION = r'(?:0\.\d+|1\.0+)'
# A mathematical name must be consumed completely. In particular G2.1 is
# never evidence for G2, and mathematical operands remain case-sensitive.
_SYMBOL = r'[A-Z]\s*[0-9]+(?![A-Za-z0-9_.\-])(?!\s*[._\-]\s*[A-Za-z0-9])'
_PAIR = re.compile(r'图\s*[(（]?\s*(?P<first>'+_SYMBOL+r')\s*[,，、和与]\s*(?P<second>'+_SYMBOL+r')\s*[)）]?')


def _explicit_graph_reference(text, match):
    before=text[:match.start()];after=text[match.end():]
    return bool(re.search(r'(?:参见|详见|参照|参阅|见|如)\s*[\u4e00-\u9fff]{0,8}$',before)
                or re.match(r'\s*(?:[,，、和与]\s*(?:图\s*)?'+_SYMBOL+r')*\s*[)）]?\s*(?:所示|所述|展示|显示)',after))


def _non_reference_quantity(text, match):
    before=text[:match.start()];after=text[match.end():]
    if _explicit_graph_reference(text,match):return False
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',match.group('number')):return False
    # Compound graph-model names attached to percentages denote measurements.
    if re.search(r'(?:同构|异构|同质|异质)\s*$',before) and re.match(r'\s*[%％]',after):return True
    # An ablation label and a terminal scalar constitute a table result row.
    # Neither a bare position-map figure nor an explicit citation has this form.
    return bool(re.fullmatch(r'\s*(?:w/o|without)\s+[\u4e00-\u9fff]+',before,re.I)
                and re.fullmatch(r'\s*(?:[%％])?\s*',after)
                and re.fullmatch(r'[0-9]+\.[0-9]+',match.group('number')))


def _library_room(text, match):
    if _explicit_graph_reference(text,match):return False
    before=text[:match.start()];after=text[match.end():]
    library=bool('图书馆' in before or
                 (re.search(r'(?:包|主)图\s*[一二三四五六七八九十0-9]+\s*楼',before)
                  and re.search(r'[,，、]\s*[\u4e00-\u9fff]+(?:院|楼|馆|室|中心)\s*[A-Z]?[0-9]{3,4}\s*(?:的)?(?:深夜|角落|房间)',after)))
    return bool(re.search(r'主\s*$',before)
                and re.fullmatch(r'[A-Z][0-9]{3,4}',match.group('number'))
                and re.match(r'\s*(?:的)?(?:角落|房间|阅览室|自习室|大厅)',after)
                and library)


def _mask_composition_use(text, match):
    if _explicit_graph_reference(text,match):return False
    pattern=re.compile(r'掩码图\s*(?P<items>'+_SYMBOL+r'(?:\s*[,，、]\s*'+_SYMBOL+r')+)'
                       r'(?:\s*[,，、]\s*[·.\s]+\s*[,，、]\s*[A-Z]\s*[A-Z])?\s*合并以(?:创建|构建|生成)掩码图')
    for declaration in pattern.finditer(text):
        if declaration.start('items')<=match.start('number')<match.end('number')<=declaration.end('items'):
            return True
    return False


def _math_graph_pairs(text):
    """Own each complete graph-pair declaration with its exact operands."""
    for declaration in _PAIR.finditer(text):
        prefix=text[:declaration.start()]
        tail=re.split(r'[。！？!?;；]',text[declaration.end():],maxsplit=1)[0]
        if re.search(r'(?:参见|详见|参照|参阅|见|如)\s*[\u4e00-\u9fff]{0,8}$',prefix):continue
        if re.match(r'\s*(?:所示|所述|展示|显示)',tail):continue
        first,second=[re.sub(r'\s+','',declaration.group(name)) for name in ('first','second')]
        if first==second:continue
        operand=lambda value:r'\s*'.join(map(re.escape,value))
        distance=(r'd\s*_?\s*(?:[A-Z]\s*)?\(\s*'+operand(first)+r'\s*[,，]\s*'+operand(second)+r'\s*\)')
        network=bool(re.search(r'(?:及其|与其|和其|对应的)\s*网络$',prefix)
                     and re.search(r'[≤≥<>=]',tail) and re.search(distance,tail))
        hom=(r'hom\(\s*(?P<domain>[A-Z][0-9]*)\s*[,，]\s*'+operand(first)+r'\s*\)\s*'
             r'[≠=<>≤≥]\s*hom\(\s*(?P=domain)\s*[,，]\s*'+operand(second)+r'\s*\)')
        if network or re.search(hom,tail):yield declaration


def _graph_parameter(before, contents, after):
    """Graph-model proportions in parentheses are not illustration numbers.

    Use the graph noun, quantitative notation and sentence attachment together.
    Explicit cross-reference wording still wins, including chapter-zero IDs.
    """
    if not re.search(_GRAPH_NOUN+r'\s*$', before):
        return False
    if re.search(r'(?:参见|详见|参照|参阅|见|如)\s*[\u4e00-\u9fff]{0,8}$',before):
        return False
    return (bool(re.fullmatch(rf'\s*{_PROPORTION}(?:\s*[-~至到]\s*{_PROPORTION})?\s*',contents))
            and bool(re.match(r'\s*(?:上|中)(?!所示|展示|显示|画出)',after)))


def _image_scale_quantity(before, number, after):
    # Original/source/input image sizes use a complete fraction or percentage.
    # Explicit reference language still resolves to actual illustration IDs.
    noun=r'(?:原始|原|输入|输出|参考|源)'
    if not re.search(noun+r'\s*$',before):return False
    if re.search(r'(?:参见|详见|参照|参阅|见|如)\s*'+noun+r'\s*$',before):return False
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',number):return False
    if re.match(r'\s*[%％]',after):return True
    ratio=re.match(r'\s*/\s*(?P<denominator>[0-9]+(?:\.[0-9]+)?)(?![0-9.])',after)
    return bool(ratio and float(ratio.group('denominator'))>0)


def local_reference(text, match):
    before = text[:match.start()]
    after = text[match.end():]
    if match.group(0).startswith('图') and (_non_reference_quantity(text,match) or _library_room(text,match)):
        return False
    if match.group(0).startswith('图') and _image_scale_quantity(before,match.group('number'),after):
        return False
    # English citation words embedded in paths, identifiers or email names
    # belong to that resource. Check this occurrence, preserving later real
    # citations in the same sentence and standalone 'Figure9' references.
    if re.match(r'(?:figure|fig|table)',match.group(0),re.I):
        if re.search(r'[A-Za-z0-9_/\\]$',before):
            return False
    prefix=text[match.start():match.start('number')]
    if prefix.rfind('(')>prefix.rfind(')'):
        opening=match.start()+prefix.rfind('(')
        closing=text.find(')',opening)
        number=r'(?:[A-Z]\.?)?\d+(?:[.\-]\d+)*(?:[a-z])?'
        if closing<0 or not re.fullmatch(rf'\s*{number}(?:\s*[,，、和及与至到~\-]\s*{number})*\s*',text[opening+1:closing],re.I):
            return False
        if match.group(0).startswith('图') and _graph_parameter(before,text[opening+1:closing],text[closing+1:]):
            return False
    # An alphanumeric tensor name after a compound map noun identifies a
    # computed quantity. Explicit citation language still names illustrations.
    tensor_noun=r'(?:特征|响应|注意力|激活)'
    if (match.group(0).startswith('图') and re.fullmatch(r'[A-Z][0-9]+',match.group('number'),re.I)
            and re.search(tensor_noun+r'\s*$',before)
            and not _explicit_graph_reference(text,match)):
        return False
    # The final character of a technical noun is not the citation word 图/表.
    if match.group(0).startswith('图') and re.search(r'视$', before):
        return False
    if match.group(0).startswith('表') and re.search(r'(?:代|列|仪|码|哈希)$', before):
        return False
    if re.match(r'\s*(?:个|张|幅|种|维|次|层|倍)', after):
        return False
    if re.search(r"\[[0-9,，、\s–—-]+\]\s*(?:中|里)?的\s*$", before):
        return False
    # An author's numeric citation directly owns the following appendix.
    # A clause boundary ends that ownership; later local appendices survive.
    if (match.group(0).startswith('附录') and re.search(
            r'[A-Za-z\u4e00-\u9fff][A-Za-z0-9_.\-\u4e00-\u9fff]*\s*'
            r'\[[0-9,，、\s–—-]+\]\s*(?:中|里)?(?:的)?\s*$',before)):
        return False
    # Limit source qualification to this reference, never the whole sentence.
    if re.search(r'(?:文献|参考文献|研究|论文)\s*\[[^\]]+\]\s*(?:中|里)?\s*(?:的|所示的)?\s*$', before, re.I):
        return False
    if re.search(r'(?:引自|摘自|改编自|转载自|引用自)\s*\[[^\]]+\]\s*(?:的)?\s*$', before):
        return False
    if re.search(r'(?:cited|adapted|reproduced|taken)\s+from\s*$', before, re.I):
        return False
    if re.match(r'\s*(?:in|of)\s*(?:Ref\.?\s*)?\[\d', after, re.I):
        return False
    return True


def defined_graph_symbols(document):
    """Graph variables require a typed declaration or exact mathematical use."""
    from .numbering import normalize_text,normalize_label
    from .typed_subgraph_terms import GraphSymbols
    symbols=GraphSymbols(document)
    definition=re.compile(r'(?:[\u4e00-\u9fff]{1,12}图|graph)\s*(?:为|记为|表示为|denoted\s+by)?\s*'
                          r'(?P<symbol>[A-Z]\s*[0-9]+)\s*=\s*\(\s*V\s*[0-9]*\s*[,，]\s*E\s*[0-9]*\s*\)',re.I)
    from .usage_paragraphs import usage_paragraphs
    texts=[normalize_text(l.text) for l,_ in usage_paragraphs([(l,'definition') for l in document.lines])]
    # A theorem ending in a colon owns its immediately following mathematical
    # bullets. This adds evidence text only; original lines and offsets survive.
    lines=document.lines
    for i,line in enumerate(lines):
        text=normalize_text(line.text)
        if not re.search(r'(?:以下|下列).{0,12}等价\s*[:：]\s*$',text):continue
        bullets=[]
        for other in lines[i+1:i+4]:
            if other.page_number!=line.page_number or other.source!=line.source or not other.text.lstrip().startswith('•'):break
            bullets.append(normalize_text(other.text))
        if bullets:texts.append(text+' '+' '.join(bullets))
    for first,second in zip(document.lines,document.lines[1:]):
        a,b=normalize_text(first.text),normalize_text(second.text)
        height=max(1,first.bbox[3]-first.bbox[1])
        if (a.rstrip().endswith('=') and re.match(r'^\s*\(\s*V\s*[0-9]*\s*[,，]\s*E',b)
                and first.page_number==second.page_number and first.source==second.source
                and 0<=second.bbox[1]-first.bbox[3]<=height*1.3
                and abs(second.bbox[0]-first.bbox[0])<=height*2.5):
            texts.append(a+' '+b)
    for text in texts:
        for match in definition.finditer(text):
            symbols.add_tuple_symbol(normalize_label(re.sub(r'\s+','',match.group('symbol'))))
            # A graph-pair definition declares both source and target. The
            # second variable often omits the already stated noun "graph".
            # Require its explicit vertex/edge tuple in the same declaration;
            # arbitrary tuples or later prose cannot declare new graph names.
            paired=re.compile(r'\s*(?:与|和|及|、|[,，]\s*(?:与|和|及)?|and)\s*(?:图\s*)?'
                              r'(?P<symbol>[A-Z]\s*[0-9]+)\s*=\s*'
                              r'\(\s*V\s*[0-9]*\s*[,，]\s*E\s*[0-9]*\s*\)',re.I)
            tail=text[match.end():]
            while candidate:=paired.match(tail):
                symbols.add_tuple_symbol(normalize_label(re.sub(r'\s+','',candidate.group('symbol'))))
                tail=tail[candidate.end():]
        # Program IRs and algorithm output graph types are declarations, not
        # illustrations. A type name without an introducing declaration is
        # insufficient, so an undeclared "计算图G0" still undergoes rule 11.
        typed=re.compile(r'(?:给定|设|令|(?:Input|Output|输入|输出)\s*[:：])\s*'
                         r'(?:一个|一张|一对|两个|初始|最终|输入|输出|活跃边|计算|\s)*'
                         r'(?:计算|活跃边)图\s*(?P<first>'+_SYMBOL+r')'
                         r'(?:\s*[,，、和与]\s*(?P<second>'+_SYMBOL+r'))?')
        for declaration in typed.finditer(text):
            if re.search(r'(?:参见|详见|参照|见|如)\s*$',text[:declaration.start()]):continue
            for name in ('first','second'):
                if declaration.group(name):symbols.add(re.sub(r'\s+','',declaration.group(name)))
        # A hidden graph pair is explicitly represented by attributed graphs
        # and their vertex/edge sets. Arbitrary parameter tuples cannot type it.
        container=re.compile(r'(?:隐藏|属性)图\s*[A-Z]\s*=\s*\(\s*(?P<first>'+_SYMBOL+r')\s*[,，]\s*(?P<second>'+_SYMBOL+r')\s*\)')
        for declaration in container.finditer(text):
            tail=text[declaration.end():]
            if '节点集' in tail and '边集' in tail:
                symbols.update(re.sub(r'\s+','',declaration.group(name)) for name in ('first','second'))
        construction=re.compile(r'图\s*(?P<symbol>'+_SYMBOL+r')\s*的(?:严格)?定义如下\s*[:：]')
        for declaration in construction.finditer(text):
            tail=text[declaration.end():]
            if re.search(r'(?:节点|顶点)',tail) and '边' in tail and re.search(r'(?:添加|替换|构造|连接|删除)',tail):
                symbols.add(re.sub(r'\s+','',declaration.group('symbol')))
        for declaration in _math_graph_pairs(text):
            symbols.update(re.sub(r'\s+','',declaration.group(name)) for name in ('first','second'))
    return symbols


def graph_variable_use(text,match,defined,*,line=None):
    """A defined graph noun plus its variable is not an illustration citation."""
    from .typed_subgraph_terms import local_subgraph_use
    if not match.group(0).startswith('图'):return False
    if _explicit_graph_reference(text,match):return False
    if line is not None and hasattr(defined,'contextual_subgraph_use') and defined.contextual_subgraph_use(text,match,line):return True
    if local_subgraph_use(text,match,defined):return True
    if _mask_composition_use(text,match):return True
    # This occurrence must belong to the declaration, not a later citation of
    # the same name. Identity ownership uses original normalized text offsets.
    for declaration in _math_graph_pairs(text):
        if any(declaration.start(name)<=match.start('number')<match.end('number')<=declaration.end(name) for name in ('first','second')):return True
    if not (defined.contains_number(match.group('number')) if hasattr(defined,'contains_number') else match.group('number') in defined):return False
    before=text[:match.start()];after=text[match.end():]
    qualified=bool(re.search(_GRAPH_NOUN+r'\s*$|(?:攻击|噪声|活跃边|对应)\s*$',before))
    declaration=bool(re.match(r'^\s*(?:=\s*(?:$|\(\s*V\s*[0-9]*\s*[,，]\s*E)|的(?:严格)?定义如下\s*[:：])',after,re.I))
    structural=bool(re.match(
        r'^\s*(?:[,，、和及与]\s*(?:目标|源)?(?:图\s*)?'+_SYMBOL+r')*'
        r'\s*(?:中(?:连接|的)?|的)?\s*(?:第[A-Za-z0-9]+个)?\s*(?:关键点|节点|顶点|邻接|拓扑|边(?:特征|集合|[\s(（]))',after))
    relational=bool(re.match(r'^\s*(?:[,，、和与]\s*'+_SYMBOL+r')*\s*[,，]?\s*(?:以下二者等价|在\s*[A-Za-z0-9]+\s*上不等价)',after))
    mapping=bool((re.search(r'(?:投影|映射)[^。；;]*将\s*$',before) and re.fullmatch(r'\s*中\s*',after))
                 or (re.search(r'映射回其在\s*$',before) and re.match(r'\s*中\s*的对应(?:真值)?索引',after)))
    membership=bool(re.search(r'属于\s*$',before))
    return qualified or declaration or structural or relational or mapping or membership
