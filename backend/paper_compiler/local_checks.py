"""Six native-text checks over the shared Paper Model / Paper IR. No network."""
import re
from statistics import median
from .structure import abstract_sections, section_display_name, _contents_page

RULES = (31, 34, 35, 36, 37, 38)  # execution keys only; public titles have no rule numbers
_CHAPTER = re.compile(r'^(?:第[一二三四五六七八九十百0-9]+[章篇]|chapter\d+|\d+(?:[.．]\d+)*[.．、]?)(?:[:：]|[-–—])?', re.I)
_INTRO = re.compile(r'^(?:绪论|绪言|引言|引论|简介|introduction(?:andcontextualization)?)$', re.I)
_CONCLUSION = re.compile(r'^(?:(?:课题|全文|研究|工作|论文)?(?:总结|结论)(?:[与和及](?:未来)?(?:展望|工作|建议|讨论))?|总结|结论|总结[与和及](?:未来)?展望|结论[与和及](?:未来)?展望|总结[与和及]未来工作|研究结论|全文总结|研究总结|研究成果总结|总结展望|结论及建议|结语|结束语|conclusions?(?:andfuturework)?|summary(?:and(?:futurework|outlook))?)$', re.I)
_TYPE = re.compile(r'[\[［]\s*([A-Za-z]{1,3})(?:\s*/\s*([A-Za-z]{1,2}))?\s*[\]］]')
_CODES = set('M J N C D R S P EB A CM DS PP G GI CP DB Z'.split())
_MEDIA = {'MT', 'DK', 'CD', 'OL', 'MM'}
_YEAR = re.compile(r'(?<!\d)(?:1[5-9]|20)\d{2}(?!\d)')
_PUNCT = re.compile(r'(?<=[\u4e00-\u9fff])\s*([,;:!?])\s*(?=[\u4e00-\u9fff])')
_ZH_PERIOD = re.compile(r'(?<=[\u4e00-\u9fff])\s*(\.)(?!\s*\.)(?=[\u4e00-\u9fff\s”’"）)]|$)')
_KEYWORD_LABEL = re.compile(r'(?:关键词|关键字)\s*[:：]\s*(.*)', re.I | re.S)
_TERM_SPLIT = re.compile(r'[；;，,、]')
_FRONT_TEXT = {'摘要', '中文摘要', 'abstract', '目录', '目次', 'contents', 'tableofcontents'}
_ABSTRACT_HEADING = {'摘要', '中文摘要', '英文摘要', 'abstract'}
_ABSTRACT_KEYWORDS = re.compile(r'^(?:关键词|关键字|key\s*words?|index\s+terms)(?:\s*[:：]|\s*$)', re.I)
_ABSTRACT_END_HEADING = {'目录', '目次', 'contents', 'tableofcontents', '插图', '插图目录',
                         '表格', '表格目录', '图表目录', '算法', '算法目录', '符号对照表',
                         'listoffigures', 'listoftables', 'ccsconcepts', 'acmreferenceformat',
                         '参考文献', 'references', 'bibliography'}
# Numbered objects a self-contained abstract must not cite. Each pattern needs a
# digit so prose words such as 表明, 表达, 表决 and 形式 are never treated as 图/表/式.
_OBJECT_NUMBERS = (
    ('图', re.compile(r'图\s*\d{1,3}(?:\s*[-–—.．]\s*\d{1,3})*')),
    ('表', re.compile(r'表\s*\d{1,3}(?:\s*[-–—.．]\s*\d{1,3})*')),
    ('公式', re.compile(r'公式\s*[（(]?\s*\d{1,3}(?:\s*[-–—.．]\s*\d{1,3})*\s*[)）]?')),
    ('公式', re.compile(r'(?<![公方形模程仪范格款版])式\s*[（(]?\s*\d{1,3}(?:\s*[-–—.．]\s*\d{1,3})*\s*[)）]?')),
    ('参考文献', re.compile(r'[\[［]\s*\d{1,3}(?:\s*[-–—,，]\s*\d{1,3})*\s*[\]］]')),
    ('图', re.compile(r'(?<![A-Za-z])fig(?:ure)?s?\.?\s*\d{1,3}(?:\s*[.．]\s*\d{1,3})?(?!\d)', re.I)),
    ('表', re.compile(r'(?<![A-Za-z])tab(?:le)?s?\.?\s*\d{1,3}(?:\s*[.．]\s*\d{1,3})?(?!\d)', re.I)),
    ('公式', re.compile(r'(?<![A-Za-z])eq(?:uation|n)?s?\.?\s*[(（]?\s*\d{1,3}(?:\s*[-–—.．]\s*\d{1,3})*\s*[)）]?(?!\d)', re.I)),
)
# A chapter label must be a whole visual row: 第4 章 alone, or the number followed
# by an optionally spaced title of at most 40 chars without sentence punctuation.
# Prose such as 第三章的… or 第一章是绪论，… therefore never becomes a chapter label.
_CHAPTER_LABEL = re.compile(r'^第\s*[一二三四五六七八九十百零〇0-9]{1,4}\s*章(?:\s*[^\s，。；：！？、,;:!?]{1,40})?$')
_NUMBERED_CHAPTER_LABEL = re.compile(r'^(?:chapter\s*\d+(?:\s+[^，。；：！？,;:!?]{1,100})?|\d{1,3}[.．、]?\s+[^\d\W][^，。；：！？,;:!?]{0,99})$', re.I)
_LEADER_LINE = re.compile(r'\.{3,}|…')
# Page furniture above the top margin (running headers, page numbers) is not prior
# chapter content; rows() drops small ones, but 12.6 pt headers survive its 12.5 cut.
_TOP_MARGIN = 0.12
# Running headers live in the very top strip.  Keep this deliberately smaller
# than _TOP_MARGIN: the wider margin is useful when deciding whether a chapter
# heading itself is genuinely in the page body, but using it for *prior prose*
# hid a real 12pt carry-over line placed between the header and the chapter.
_RUNNING_HEADER_MARGIN = 0.09
# A chapter heading is typeset larger than body text. Body-size rows that start with
# 第x章 are 论文组织结构 prose or figure cells, never a chapter opening.
_HEADING_SCALE = 1.25
_EN_PUNCT = re.compile(r'(?<=[A-Za-z0-9%)\]])([，；：！？。])(?=\s|[A-Za-z0-9]|$)')


def compact(text):
    return re.sub(r'\s+', '', text or '').casefold()


def _source(span):
    if span.get('kind') == 'source':
        return span
    ancestors = span.get('ancestor_provenance', span.get('input_provenance', []))
    return next((source for item in ancestors if (source := _source(item))), None)


def _node_page_index(node):
    """Smallest source page for a node, resolving synthetic mutations."""
    pages = [(_source(span) or {}).get('page_index', 10**9) for span in node.get('provenance', [])]
    return min(pages, default=10**9)


def _column_gutters(ir):
    """Require repeated, overlapping prose on both sides of a native gutter."""
    gutters = {}
    for page in ir['layout']['pages']:
        width = page['width']
        boxes, all_boxes = [], []
        for node in ir['nodes']:
            if node['kind'] != 'Paragraph' or not node['text']:
                continue
            for span in node['provenance']:
                source = _source(span)
                if not source or source['page_index'] != page['page_index']:
                    continue
                box = source['bbox']
                text = node['text'][span.get('node_text_start', 0):span.get('node_text_end', len(node['text']))]
                if text.strip() and 0 < box[3] - box[1] < 40 and page['height'] * .09 <= box[1] and box[3] <= page['height'] * .94:
                    all_boxes.append(box)
                if len(compact(text)) >= 20 and width * .25 <= box[2] - box[0] and 0 < box[3] - box[1] < 40:
                    boxes.append(box)
        left = [b for b in boxes if b[2] <= width / 2]
        right = [b for b in boxes if b[0] >= width / 2]
        if len(left) < 3 or len(right) < 3:
            continue
        a, b = max(v[2] for v in left), min(v[0] for v in right)
        overlap = min(max(v[3] for v in left), max(v[3] for v in right)) - max(min(v[1] for v in left), min(v[1] for v in right))
        if b - a >= width * .015 and overlap > 30:
            # Short final lines still belong to their columns; only long
            # lines are required to establish the gutter itself.
            column_boxes = [v for v in all_boxes if v[2] <= width / 2 or v[0] >= width / 2]
            gutters[page['page_index']] = ((a + b) / 2, max(v[3] for v in column_boxes or left + right))
    return gutters


def _reading_position(page, box, gutters):
    gutter = gutters.get(page)
    # Content below the native columns resumes page-wide reading order.
    column = (2 if box[1] > gutter[1] else int(box[0] >= gutter[0])) if gutter else 0
    return page, column, box[1]


def rows(ir, *, retain_top_body=False, column_gutters=None):
    """Join horizontally split glyphs by their PDF baseline, never by semantics."""
    pieces = []
    pages = {page['page_index']:page for page in ir['layout']['pages']}
    for node in ir['nodes']:
        if not node['text'] or node['kind'] in {'UnknownBlock', 'ToCEntry', 'BibliographyEntry'}:
            continue
        for span in node['provenance']:
            source = _source(span)
            if not source or 'bbox' not in source:
                continue
            page = pages[source['page_index']]
            box = source['bbox']
            if box[3]-box[1] <= 12.5 and (box[1] < page['height']*.12 or box[3] > page['height']*.94):
                # Rule 38 needs to distinguish a real carry-over body line
                # just below a running header from the header itself.  Other
                # rules retain the previous conservative header/footer filter.
                if not (retain_top_body and page['height'] * _RUNNING_HEADER_MARGIN <= box[1] < page['height'] * _TOP_MARGIN):
                    continue
            if span.get('kind') == 'synthetic' or len(node['provenance']) == 1:
                text = node['text']
            else:
                text = node['text'][span.get('node_text_start', 0):span.get('node_text_end', len(node['text']))]
            pieces.append((source['page_index'], source['bbox'], text, node))
    grouped = []
    position = lambda page, box: _reading_position(page, box, column_gutters or {})
    for page, box, text, node in sorted(pieces, key=lambda p: (*position(p[0], p[1]), p[1][0])):
        if grouped and position(page, box)[:2] == position(grouped[-1][0], grouped[-1][1])[:2] and abs(box[1] - grouped[-1][1][1]) <= 3 and box[0] >= grouped[-1][1][2] and box[0] - grouped[-1][1][2] <= 60:
            previous = grouped[-1]
            grouped[-1] = (page, [previous[1][0], min(previous[1][1], box[1]), box[2], max(previous[1][3], box[3])], previous[2] + ' ' + text, previous[3])
        else:
            grouped.append((page, list(box), text, node))
    return grouped


def _finding(ir, rule, node, message, token, suggestion, offset=0):
    selected = next((span for span in node['provenance'] if span.get('node_text_start', 0) <= offset < span.get('node_text_end', len(node['text']))), node['provenance'][0])
    source = _source(selected)
    location = None
    if source:
        page = next(p for p in ir['layout']['pages'] if p['page_index'] == source['page_index'])
        x0, y0, x1, y1 = source['bbox']
        if rule == 35:
            line = next((line for line in page.get('lines', []) if line['id'] == source.get('line_id')), None)
            char_offset = offset - selected.get('node_text_start', 0) + source.get('text_offsets', [0])[0]
            char = next((char for char in (line or {}).get('chars', []) if char['start'] <= char_offset < char['end']), None)
            if char:
                x0, y0, x1, y1 = char['bbox']
        rect = dict(x1=x0, y1=y0, x2=x1, y2=y1, width=page['width'], height=page['height'], page_number=source['page_index'] + 1)
        location = {'type': 'pdf_bbox', 'page_number': source['page_index'] + 1,
                    'bounding_rect': rect, 'rects': [rect], 'text_excerpt': node['text'][:600]}
    return {'rule_id': str(rule), 'node_id': node['id'], 'token': token, 'message': message,
            'suggestion': suggestion, 'location': location, 'text_excerpt': (node['text'] or '')[:600]}


def _declaration_title_parts(text, *, displayed=False):
    """Only complete declaration titles supply these parts; prose mentions do not."""
    prefix = r'(?:(?:(?:硕士|博士)?研究生|硕士|博士)?(?:学位|毕业)?论文)?'
    originality = r'(?:(?:原创性|独创性)(?:声明书?|说明书?)|原创声明书?|学术诚信声明书?)'
    usage = (r'(?:(?:(?:版权)?使用|版权)授权(?:书|说明书?|声明书?)?|'
             r'授权使用(?:书|说明书?|声明书?)?|版权使用(?:说明书?|声明书?|书)|'
             r'使用权限(?:说明书?|声明书?)?|使用许可(?:说明书?|声明书?|书)?)')
    separator = r'(?:[和与及暨、]|以及)'
    title = compact(text)
    # A real institution-prefixed heading is still a declaration, without
    # enumerating universities or dropping arbitrary prose before an alias.
    if displayed and not re.match(r'^(?:详见|参见|未提供|未提交|未签署|缺少|缺失|本章|本文|关于|有关)', title):
        institution = re.match(r'^[\u3400-\u9fffA-Za-z·]{1,35}(?:大学|学院|研究生院|研究院|研究所|学校)', title)
        if institution:
            title = title[institution.end():]
    if re.fullmatch(prefix + originality, title):
        return {'原创性声明'}
    if re.fullmatch(prefix + usage, title):
        return {'使用授权说明'}
    if (re.fullmatch(prefix + originality + separator + prefix + usage, title)
            or re.fullmatch(prefix + usage + separator + prefix + originality, title)):
        return {'原创性声明', '使用授权说明'}
    return set()


def _declaration_titles(ir, visual_rows):
    """Recover one short horizontal title band, including skewed native glyphs.

    This is deliberately local to declarations: the stricter rows() geometry
    remains unchanged for chapter, punctuation and abstract checks.
    """
    by_id = {node['id']: node for node in ir['nodes']}
    pending = [node['id'] for node in ir['nodes'] if node['kind'] in {
        'ToC', 'ToCEntry', 'Bibliography', 'BibliographyEntry', 'UnknownBlock',
        'Figure', 'Table', 'Caption', 'Equation', 'MathExpression'}]
    excluded = set()
    while pending:
        node_id = pending.pop()
        if node_id not in excluded:
            excluded.add(node_id)
            pending.extend(by_id[node_id]['children'])
    pages = {}
    page_layout = {page['page_index']: page for page in ir['layout']['pages']}
    # Shared rows() may already have joined alternate glyph baselines in the
    # wrong horizontal order. Recover declarations directly from live IR spans;
    # immutable layout text must not restore a deleted or edited declaration.
    for node in ir['nodes']:
        if node['id'] in excluded or not node['text']:
            continue
        for span in node['provenance']:
            source = _source(span)
            if not source or 'bbox' not in source:
                continue
            page, box = source['page_index'], source['bbox']
            layout = page_layout[page]
            if box[3] - box[1] <= 12.5 and (box[1] < layout['height'] * .12
                                          or box[3] > layout['height'] * .94):
                continue
            if span.get('kind') == 'synthetic' or len(node['provenance']) == 1:
                text = node['text']
            else:
                text = node['text'][span.get('node_text_start', 0):span.get('node_text_end', len(node['text']))]
            if not compact(text):
                continue
            width = layout.get('width', 0)
            displayed = node['kind'] == 'Heading' or bool(width and box[3] - box[1] >= 14
                and abs((box[0] + box[2]) / 2 - width / 2) <= width * .12)
            pages.setdefault(page, []).append((box, compact(text), displayed))
    found = {}
    for page, entries in pages.items():
        groups = []
        for box, text, displayed in sorted(entries, key=lambda entry: (entry[0][0], entry[0][1])):
            compatible = []
            for group in groups:
                previous = group['pieces'][-1][0]
                heights = [piece[0][3] - piece[0][1] for piece in group['pieces']] + [box[3] - box[1]]
                overlap = min(previous[3], box[3]) - max(previous[1], box[1])
                gap = box[0] - previous[2]
                band = max(group['bottom'], box[3]) - min(group['top'], box[1])
                if (min(heights) > 0 and 0 <= gap <= 3 * min(heights)
                        and overlap >= .2 * min(previous[3] - previous[1], box[3] - box[1])
                        and max(heights) <= 1.5 * min(heights)
                        and band <= 2 * median(heights)):
                    compatible.append(group)
            if len(compatible) == 1:
                group = compatible[0]
                group['pieces'].append((box, text, displayed))
                group['top'] = min(group['top'], box[1])
                group['bottom'] = max(group['bottom'], box[3])
            else:
                # Ambiguous bands cannot provide a title by dropping a neighbor.
                for group in compatible:
                    group['ambiguous'] = True
                groups.append({'pieces': [(box, text, displayed)], 'top': box[1],
                               'bottom': box[3], 'ambiguous': bool(compatible)})
        for group in groups:
            # Do not select an alias substring from a longer physical text band.
            title = ''.join(text for _, text, _ in group['pieces'])
            if group['ambiguous'] or len(group['pieces']) > 32 or len(title) > 45:
                continue
            parts = _declaration_title_parts(title, displayed=any(piece[2] for piece in group['pieces']))
            if parts:
                found.setdefault(page, set()).update(parts)
    return found


def title_page_evidence(ir, visual_rows):
    if any(n['kind'] == 'TitlePage' for n in ir['nodes']):
        return True
    grouped = {}
    for page, box, text, node in visual_rows:
        grouped.setdefault(page, []).append(compact(text))
    declarations = _declaration_titles(ir, visual_rows)
    uncertain = False
    for page in sorted(grouped)[:6]:
        texts = grouped[page]
        if any(t in {'摘要', 'abstract', '目录', '目次', 'contents'} or re.match(r'^(?:关键词|关键字|keywords?)(?:[:：]|$)', t) or _INTRO.fullmatch(_CHAPTER.sub('', t)) for t in texts):
            break
        if any(re.search(r'(?:\.\s*){3,}\s*\d+\s*$', t) for t in texts):
            break  # A contents continuation cannot be an unfamiliar title page.
        if declarations.get(page):
            continue
        metadata = sum(bool(re.match(r'^(?:作者|姓名|学号|导师|指导教师|学科|专业|学院|申请学位|student|supervisor|department)', t)) for t in texts)
        if metadata >= 2:
            return True
        # Dense prose without a large centered title cannot serve as a title page.
        centered = any(box[3]-box[1] >= 14 and abs((box[0]+box[2])/2 - ir['layout']['pages'][page]['width']/2) < 80 for index,box,_,_ in visual_rows if index==page)
        if sum(map(len,texts)) > 250 and not centered:
            continue
        # A readable but unfamiliar front-page layout remains unconfirmed.
        uncertain = True
    return None if uncertain else False


def current_abstract_sections(ir, visual_rows=None):
    # Use current IR text so deleted/edited nodes cannot be restored from the
    # immutable original PDF observations retained in layout.
    visible_pages = {page['page_index']: {'height': page['height'], 'lines': []} for page in ir['layout']['pages']}
    for page, box, text, node in (visual_rows if visual_rows is not None else rows(ir)):
        visible_pages[page]['lines'].append({'text': text, 'bbox': box, 'font_size': box[3] - box[1],
                                            'is_heading': node['kind'] == 'Heading'})
    profile = ir.get('metadata', {}).get('document_admission', {}).get('structure', {}).get('profile', 'chinese-thesis')
    return abstract_sections([visible_pages[index] for index in sorted(visible_pages)], profile)


def core_parts(ir, *, abstracts=None):
    visual_rows = rows(ir)
    abstracts = current_abstract_sections(ir, visual_rows) if abstracts is None else abstracts
    profile = ir.get('metadata', {}).get('document_admission', {}).get('structure', {}).get('profile', 'chinese-thesis')
    texts = [compact(text) for _, _, text, _ in visual_rows]
    intro_pages = [page for page, _, text, _ in visual_rows if _INTRO.fullmatch(_CHAPTER.sub('', compact(text)))]
    toc_pages = [page for page, _, text, _ in visual_rows if re.search(r'(?:\.\s*){3,}\s*\d+\s*$', text)]
    body_start = max(max(toc_pages, default=-1)+1, min(intro_pages, default=0))
    body_end = min((page for page,_,text,node in visual_rows if page >= body_start and node['kind'] == 'Heading' and (_CONCLUSION.fullmatch(_CHAPTER.sub('',compact(text))) or compact(text) in {'参考文献','references','bibliography'})), default=len(ir['layout']['pages']))
    headings = [_CHAPTER.sub('', text) for text in texts]
    kinds = {node['kind'] for node in ir['nodes']}
    declarations = set().union(*_declaration_titles(ir, visual_rows).values())
    by_id = {node['id']: node for node in ir['nodes']}
    return {
        '题名页': title_page_evidence(ir, visual_rows),
        '原创性声明': '原创性声明' in declarations,
        '使用授权说明': '使用授权说明' in declarations,
        '摘要': abstracts.get('摘要', {}).get('status') == 'complete',
        '英文摘要': profile != 'chinese-thesis' or abstracts.get('英文摘要', {}).get('status') == 'complete',
        '关键词': any(value['has_keywords'] for value in abstracts.values()) or any(re.match(r'^(?:关键词|关键字|keywords?)(?:[:：]|$)', text) for text in texts),
        '目录': 'ToC' in kinds or any(t in {'目录', '目次', 'contents', 'tableofcontents'} for t in texts),
        '引言': any(_INTRO.fullmatch(text) for text in headings),
        '主体': any(node['kind'] == 'Section' and node['attrs'].get('level', 1) == 1 and
                    any(child['kind'] == 'Heading' and any(body_start <= (_source(span) or {}).get('page_index', -1) < body_end for span in child['provenance']) and not _INTRO.fullmatch(_CHAPTER.sub('', compact(child['text']))) and
                        not _CONCLUSION.fullmatch(_CHAPTER.sub('', compact(child['text'])))
                        for child in (by_id[nid] for nid in node['children'])) for node in ir['nodes']),
        '结论': any(_CONCLUSION.fullmatch(text) for text in headings),
        '参考文献': 'Bibliography' in kinds,
    }


def prose_nodes(ir):
    by_id = {node['id']: node for node in ir['nodes']}
    pending = [node['id'] for node in ir['nodes'] if node['kind'] in {'BackMatter', 'Bibliography', 'Biography', 'Figure', 'Table', 'Equation', 'MathExpression'}]
    excluded = set()
    while pending:
        nid = pending.pop()
        excluded.add(nid)
        pending.extend(by_id[nid]['children'])
    return [node for node in ir['nodes'] if node['kind'] == 'Paragraph' and node['text'] and node['id'] not in excluded]


def english_prose(text):
    return (not re.search(r'[\u4e00-\u9fff]', text)
            and len(re.findall(r'\b[A-Za-z]{2,}\b', text)) >= 4
            and bool(re.search(r'\b[A-Za-z]+(?:\s+[A-Za-z]+){2}\b', text))
            and bool(re.search(r'[.!?。！？](?:\s|$)', text))
            and not re.search(r'(?m:^\s*(?:USER|SYS|ASSISTANT|SYSTEM|HUMAN)\s*[:：])|'
                              r'\b[\w.-]+\.(?:pdf|docx?|xlsx?|pptx?|txt|csv|json)\b', text, re.I))


def punctuation_prose(node, pages):
    """Require sentence evidence; fragments and scanned text are not violations."""
    text = node['text']
    front_label = re.match(r'^(?:姓名|名|导师|师|学院|院系|系|学科(?:/专业)?(?:名称)?|学位类型|申请学位)[:：]', compact(text))
    declaration = re.match(r'^本人(?:郑重声明|同意学校)', compact(text))
    if not (front_label or declaration or re.search(r'[。！？]', text) or _ZH_PERIOD.search(text) or english_prose(text)):
        return False
    if re.search(r'https?://|www\.|[`<>{}|⊲▹]|//|(?m:^\s*(?:#|\d+\s*[:：]))|'
                 r'(?m:^\s*[\[［]\d+[\]］])|[A-Za-z_]\w*\s*:\s*(?:true|false|null|None)\b|'
                 r'(?m:^\s*(?:Input|Output|Require|Ensure)\s*[:：])|'
                 r'(?m:^\s*(?:foreach|end\s+for)\b)|'
                 r'(?:输入|输出|参数|初始化|扩展|相关性)\s*[:：]|'
                 r'(?:系统指令|初始问题|角色设定|角色目标)\s*[:：]|\bCase\s*\d+|'
                 r'(?:原告|被告).{0,12}诉称|本院认为|书记员|'
                 r'命名空间|标识符.{0,8}格式|'
                 r'(?:代码|配置|模板|示例|提示词)\s*[:：]|'
                 r'\b(?:print|def|import|if|while)\s*\(', text, re.I):
        return False
    if _TYPE.search(text) and _YEAR.search(text):
        return False
    for span in node['provenance']:
        source = _source(span)
        if not source:
            continue
        box = source['bbox']
        area = (box[2]-box[0]) * (box[3]-box[1])
        for image in pages[source['page_index']].get('images', []):
            overlap = max(0, min(box[2], image[2])-max(box[0], image[0])) * max(0, min(box[3], image[3])-max(box[1], image[1]))
            if area and overlap >= area * .8:
                return False
    return True


def punctuation_literals(text):
    """Quoted data and bracketed technical notation retain their separators."""
    ranges = [(m.start(), m.end()) for m in re.finditer(r'"[^\"]*"|[“”][^“”]*[“”]|‘[^’]*’|错误[!！]\s*未定义书签[。.]?', text)]
    ranges.extend((m.start(), m.end()) for m in re.finditer(r'“[^”\n]*”', text))
    ranges.extend((m.start(), m.end()) for m in re.finditer(r'(?m:^\s*[一二三四五六七八九十]+\.)', text))
    # Inline mathematics does not make later sentences in a merged paragraph code.
    # Keep the existing operator exclusion within its Chinese sentence instead.
    ranges.extend(m.span() for m in re.finditer(r'[^。！？]*[=←→][^。！？]*(?:[。！？]|$)', text))
    pairs = dict(zip('([（［⟨〈', ')]）］⟩〉'))
    stack = []
    for index, char in enumerate(text):
        if char in pairs:
            stack.append((char, index))
        elif stack and char == pairs[stack[-1][0]]:
            opening, start = stack.pop()
            inside = text[start+1:index]
            if opening in '⟨〈[［' or (len(re.findall(r'[\u4e00-\u9fff]', inside)) <= 24 and not re.search(r'[。！？]', inside)):
                ranges.append((start, index+1))
    return ranges


def _keyword_terms(text):
    """Join wrapped continuations then split on keyword delimiters."""
    m = _KEYWORD_LABEL.search(text or '')
    if not m:
        return None
    merged = re.sub(r'[\r\n]+', '', m.group(1))
    return [t for t in (x.strip(' \t。.；;，,、:：') for x in _TERM_SPLIT.split(merged)) if t]


def _keyword_block(ir, node):
    """Include adjacent hanging-indent lines that the frontend split into nodes."""
    sources = [_source(span) for span in node['provenance'] if _source(span)]
    if not sources:
        return node
    last = max(sources, key=lambda source: (source['page_index'], source['bbox'][1]))
    page, box = last['page_index'], last['bbox']
    following = sorted((((_source(other['provenance'][0]) or {}).get('bbox'), other)
                       for other in ir['nodes'] if other['id'] != node['id'] and other['text']
                       and other['provenance'] and _node_page_index(other) == page
                       and (_source(other['provenance'][0]) or {}).get('bbox', [0, -1])[1] >= box[3] - 1),
                       key=lambda item: (item[0][1], item[0][0]))
    text = node['text']
    for next_box, other in following:
        if (other['kind'] != 'Paragraph' or next_box[1] - box[3] > (box[3] - box[1]) * 1.5
                or next_box[0] < sources[0]['bbox'][0] - 2
                or re.search(r'[。!?！？:：]|\.\s*$', other['text'])):
            break
        text += '\n' + other['text']
        box = max((_source(span)['bbox'] for span in other['provenance'] if _source(span)),
                  key=lambda value: value[3])
    return {**node, 'text': text}


def _current_contents_pages(ir, visual_rows):
    """Contents evidence from current IR text, including split native entries."""
    pages = {page['page_index']: {'lines': []} for page in ir['layout']['pages']}
    for page, box, text, _ in visual_rows:
        pages[page]['lines'].append({'text': text, 'bbox': box})
    return {page for page, evidence in pages.items() if _contents_page(evidence)}


def _body_start_page(ir):
    """First page after front matter, mirroring core_parts' body boundary."""
    visual_rows = rows(ir)
    contents_pages = _current_contents_pages(ir, visual_rows)
    # A native ToC may split its entry title, leader and number into separate
    # nodes. Its "chapter 1 introduction" entry is not the actual body opening.
    intro_pages = [page for page, _, text, _ in visual_rows if page not in contents_pages
                   and _INTRO.fullmatch(_CHAPTER.sub('', compact(text)))]
    toc_pages = list(contents_pages) + [page for page, _, text, _ in visual_rows
                                      if re.search(r'(?:\.\s*){3,}\s*\d+\s*$', text)]
    # Dotted leaders also occur in figure/table captions and body diagrams.
    # Once the first body introduction is visible, such lines must not push the
    # body boundary forward (R09 consequently skipped whole early chapters).
    if intro_pages:
        first_intro = min(intro_pages)
        toc_pages = [page for page in toc_pages if page < first_intro]
    body_start = max(max(toc_pages, default=-1) + 1, min(intro_pages, default=0))
    if intro_pages or body_start:
        return body_start  # Page index zero is a valid introduction boundary.
    # Some papers have no detectable introduction/ToC heading. Fall back to the
    # last front-matter page so appendix/template mentions are still excluded.
    front_pages = [page for page, _, text, _ in visual_rows if compact(text) in _FRONT_TEXT]
    front_pages += [_node_page_index(node) for node in ir['nodes']
                    if node['kind'] in {'TitlePage', 'Abstract', 'ToC'}]
    front_pages = [page for page in front_pages if page < 10**9]
    return max(front_pages) + 4 if front_pages else 0


def chapter_labels(ir):
    """Body chapter opening labels with the visual rows that precede them on the page.

    A label is a whole visual row such as 第4 章 or 第4 章 系统设计 that is typeset as a
    heading. Pages holding three or more labels are 目录/章节安排 lists, dot-leader rows
    are 目录 entries, and rows above the top margin are running headers; all are skipped
    before any geometry is judged.
    """
    body_start = _body_start_page(ir)
    page_height = {page['page_index']: page.get('height', 0) for page in ir['layout']['pages']}
    gutters = _column_gutters(ir)
    visual = list(rows(ir, retain_top_body=True, column_gutters=gutters))
    contents_pages = _current_contents_pages(ir, visual)
    directions = {line['id']: line.get('direction', [1, 0])
                  for page in ir['layout']['pages'] for line in page.get('lines', [])}

    def horizontal(node, box):
        # A rotated table cell's bounding-box height is its text length, not a
        # heading font size. Use the source baseline before judging its height.
        for span in node['provenance']:
            source = _source(span)
            if source and source['bbox'][1] <= box[3] and source['bbox'][3] >= box[1]:
                if abs(directions.get(source.get('line_id'), [1, 0])[1]) > .1:
                    return False
        return True

    prose = sorted(box[3] - box[1] for _, box, text, _ in visual
                   if len(compact(text)) >= 15 and 0 < box[3] - box[1] < 40)
    body = prose[len(prose) // 2] if prose else 0
    # The retained top band can contain both real carry-over prose and headers.
    # Recognize furniture by repeated native rows, rather than hiding the band:
    # small text must recur on different pages at a stable top position and size.
    header_candidates = {}
    for page, box, text, node in visual:
        height = page_height.get(page, 0)
        if (not body or not height or box[1] >= height * _TOP_MARGIN
                or not 0 < box[3] - box[1] < body * .9
                or node['kind'] in {'TableCell', 'Caption'} or not horizontal(node, box)):
            continue
        header_candidates.setdefault(compact(text), []).append((page, box, node))
    running_headers = set()
    for candidates in header_candidates.values():
        for page, box, node in candidates:
            peer_pages = {other_page for other_page, other_box, _ in candidates
                          if abs(other_box[1] / page_height[other_page]
                                 - box[1] / page_height[page]) <= .003
                          and abs((other_box[3] - other_box[1])
                                  - (box[3] - box[1])) <= 1.5}
            if len(peer_pages) >= 2:
                running_headers.add((page, node['id'], tuple(box)))
    profile = ir.get('metadata', {}).get('document_admission', {}).get('structure', {}).get('profile')
    native_headings = [(source['page_index'], source['bbox'])
                       for node in ir['nodes'] if node['kind'] == 'Heading'
                       for span in node['provenance'] if (source := _source(span))]

    def numbered_heading(page, box, text):
        # Numeric first-level headings need native heading typography. Neither
        # subsection numbers (2.1) nor body-size numbered prose qualify.
        return (_NUMBERED_CHAPTER_LABEL.fullmatch(text.strip())
                and (text.strip().lower().startswith('chapter') or profile == 'research-article')
                and not re.search(r'[=<>≤≥←→{}\[\];]', text)
                and re.search(r'[A-Za-z]{3,}|[\u3400-\u9fff]{2,}', text)
                and body and box[3] - box[1] >= body * 1.15
                and any(p == page and abs(b[1] - box[1]) <= 3
                        and box[0] <= b[0] and b[2] <= box[2] + 2
                        for p, b in native_headings))

    by_page = {}
    for page, box, text, node in visual:
        by_page.setdefault(page, []).append((box, text, node))
    found = []
    for page, items in sorted(by_page.items()):
        if page < body_start or page in contents_pages:
            continue
        margin = page_height.get(page, 0) * _TOP_MARGIN
        items.sort(key=lambda row: (row[0][1], row[0][0]))
        labels = [row for row in items
                  if (_CHAPTER_LABEL.match(row[1].strip()) or numbered_heading(page, row[0], row[1]))
                  and not _LEADER_LINE.search(row[1])
                  and row[2]['kind'] not in {'TableCell', 'Caption'}
                  and horizontal(row[2], row[0])
                  and row[0][3] > margin
                  and (not body or row[0][3] - row[0][1] >= body * _HEADING_SCALE
                       or numbered_heading(page, row[0], row[1]))]
        if len(labels) >= 3 and all(_CHAPTER_LABEL.match(row[1].strip()) for row in labels):
            continue
        for box, text, node in labels:
            # Same-baseline heading fragments end at this row's own baseline; only
            # text whose bottom stays above the label is prior content.
            header_margin = page_height.get(page, 0) * _RUNNING_HEADER_MARGIN
            prior = [row for row in items
                     if (_reading_position(page, row[0], gutters)[:2] < _reading_position(page, box, gutters)[:2]
                         or (_reading_position(page, row[0], gutters)[:2] == _reading_position(page, box, gutters)[:2]
                             and row[0][3] <= box[1] + 2))
                     and row[0][1] >= header_margin
                     and (page, row[2]['id'], tuple(row[0])) not in running_headers]
            found.append((page, box, text, node, prior))
    return found


def _abstract_nodes(ir):
    """Front-matter abstract prose, including split headings and both languages."""
    body_start = _body_start_page(ir)
    gutters = _column_gutters(ir)
    position = lambda page, box: _reading_position(page, box, gutters)

    def boundary_position(page, box):
        gutter = gutters.get(page)
        if gutter and box[0] < gutter[0] < box[2]:
            return page, 2, box[1]  # A full-width ending closes both columns.
        return position(page, box)

    def within(source, start, end):
        page, box = source['page_index'], source['bbox']
        return (start <= position(page, box) < end
                and not (page == end[0] and end[1] == 2 and box[1] >= end[2]))

    visual = rows(ir, column_gutters=gutters)
    contents_pages = _current_contents_pages(ir, visual)
    introductions = [boundary_position(page, box) for page, box, text, _ in visual
                     if page not in contents_pages and _INTRO.fullmatch(_CHAPTER.sub('', compact(text)))]
    body_boundary = min(introductions, default=(body_start, 0, 0) if body_start else (10**9, 0, 0))
    starts = sorted(position(page, box) for page, box, text, _ in visual
                    if compact(text) in _ABSTRACT_HEADING and page not in contents_pages
                    and position(page, box) < body_boundary)
    if starts:
        # Abstract/body boundaries may share a page in different columns.
        # Keywords and publisher metadata end prose at their actual source row.
        shared_page = any(start[0] == body_boundary[0] for start in starts)
        article = ir.get('metadata', {}).get('document_admission', {}).get('structure', {}).get('profile') == 'research-article'
        endings = [boundary_position(page, box) if shared_page or article else (page + 1, 0, 0)
                   for page, box, text, _ in visual if _ABSTRACT_KEYWORDS.match(text.strip())]
        endings += [boundary_position(page, box) for page, box, text, _ in visual
                    if compact(text).rstrip(':：') in _ABSTRACT_END_HEADING]
        endings += starts + [body_boundary]
        ranges = [(start, min((end for end in endings if end > start), default=(10**9, 0, 0)))
                  for start in starts]
        found = []
        for node in ir['nodes']:
            if not node['text'] or node['kind'] not in {'Paragraph', 'Abstract'}:
                continue
            selected = [span for span in node['provenance'] if (source := _source(span))
                        and source['page_index'] not in contents_pages
                        and any(within(source, start, end) for start, end in ranges)]
            if not selected or _ABSTRACT_KEYWORDS.match(node['text'].strip()):
                continue
            if len(selected) == len(node['provenance']):
                found.append(node)
            else:
                # Selected spans can be disjoint in an interleaved two-column
                # paragraph. Do not restore excluded text between min/max offsets.
                fragments, spans, offset = [], [], 0
                for span in selected:
                    text = node['text'][span.get('node_text_start', 0):span.get('node_text_end', len(node['text']))]
                    fragments.append(text)
                    spans.append({**span, 'node_text_start': offset, 'node_text_end': offset + len(text)})
                    offset += len(text) + 1
                found.append({**node, 'text': '\n'.join(fragments), 'provenance': spans})
        return found
    # Retain typed abstract evidence when its source heading is unavailable.
    pages = {page for page, _, text, _ in visual if compact(text) in _ABSTRACT_HEADING}
    pages |= {_node_page_index(node) for node in ir['nodes'] if node['kind'] == 'Abstract'}
    pages = {page for page in pages if page < 10**9 and page not in contents_pages
             and (not body_start or page < body_start)}
    by_id = {node['id']: node for node in ir['nodes']}
    pending = [node['id'] for node in ir['nodes'] if node['kind'] == 'Abstract']
    abstract_ids = set()
    while pending:
        nid = pending.pop()
        if nid not in abstract_ids:
            abstract_ids.add(nid)
            pending.extend(by_id[nid]['children'])
    return [node for node in ir['nodes'] if node['text'] and node['kind'] in {'Paragraph', 'Abstract'}
            and not _KEYWORD_LABEL.match(node['text'])
            and (node['id'] in abstract_ids or any((_source(span) or {}).get('page_index') in pages for span in node['provenance']))
            and _node_page_index(node) not in contents_pages
            and (not body_start or _node_page_index(node) < body_start)
            # A contents page repeats "摘要" as an entry; its dot leaders are not abstract prose.
            and not re.search(r'(?:\.\s*){5,}', node['text'])]


def _technical_bracket(text, start, end):
    """Exclude explicit numeric intervals and W[1]-hard complexity notation."""
    after = re.sub(r'\s+', '', text[end:end+12])
    if re.match(r'[-–—]?(?:困难|hard|complete|完备)', after, re.I):
        return True
    return bool(re.search(r'[,，]', text[start:end]) and (
        re.match(r'(?:区间|范围|interval|range)', after, re.I)
        or re.search(r'(?:区间|范围|\binterval|\brange)\s*$', text[max(0, start-24):start], re.I)))


def detect_ir(ir, selected_rules=RULES):
    results = {str(rule): {'status': 'completed', 'findings': []} for rule in selected_rules}
    anchor = next((n for n in ir['nodes'] if n['text'] and n['provenance']), None)
    if 34 in selected_rules and anchor:
        # Scanned back forms cannot hide readable core chapters. Declarations
        # can be placed at the back, so their absence still requires all pages.
        coverage = ir['coverage']['pages']
        complete = coverage['status'] == 'complete'
        core_complete = coverage.get('core_sections_status') == 'complete'
        abstracts = current_abstract_sections(ir)
        parts = core_parts(ir, abstracts=abstracts)
        profile = ir.get('metadata', {}).get('document_admission', {}).get('structure', {}).get('profile', 'chinese-thesis')
        checked = [part for part, present in parts.items() if present is True or complete
                   or (core_complete and part not in {'原创性声明', '使用授权说明'})]
        results['34']['checked_parts'] = checked
        results['34']['findings'] = [_finding(ir, 34, anchor,
            f'{section_display_name(part, profile)}不完整：' + '；'.join(abstracts[part]['issues']) + '。'
            if abstracts.get(part, {}).get('status') == 'incomplete'
            else f'缺少{section_display_name(part, profile)}：未在论文正文中识别到该章节。', part,
            f'请补齐或核对{section_display_name(part, profile)}；依据 GB/T 7713.1—2025 附录 A、表 A.1。')
            for part, present in parts.items() if present is False and part in checked]
    if 35 in selected_rules:
        pages = {page['page_index']: page for page in ir['layout']['pages']}
        for node in prose_nodes(ir):
            if not punctuation_prose(node, pages):
                continue
            text = node['text']
            literals = punctuation_literals(text)
            matches = [(match, False) for match in _PUNCT.finditer(text)]
            matches.extend((match, False) for match in _ZH_PERIOD.finditer(text))
            if english_prose(text):
                matches.extend((match, True) for match in _EN_PUNCT.finditer(text))
            for match, english in matches:
                # A standalone label (e.g. Q： or a model name) is data, not an English clause.
                if english and match.group(1) == '：' and re.fullmatch(r'\s*[A-Za-z][\w-]*', text[:match.start(1)]):
                    continue
                if re.search(r'(?:字符|符号|终止符|分隔符|标点|运算符)\s*$', text[:match.start(1)]):
                    continue
                if any(start <= match.start(1) < end for start, end in literals):
                    continue
                mark = match.group(1)
                replacements = dict(zip('，；：！？。', ',;:!?.')) if english else dict(zip(',;:!?.', '，；：！？。'))
                replacement = replacements[mark]
                name = dict(zip(',;:!?.', ['逗号', '分号', '冒号', '感叹号', '问号', '句号']))[replacement if english else mark]
                source_language, target_language = ('中文', '英文') if english else ('英文', '中文')
                context = text[max(0, match.start(1)-8):match.end(1)+8].replace('\n', '')
                results['35']['findings'].append(_finding(ir, 35, node,
                    f'“{context}”中误用了{source_language}{name}“{mark}”，应使用{target_language}{name}“{replacement}”。',
                    mark, f'将此处{source_language}{name}“{mark}”改为{target_language}{name}“{replacement}”。', offset=match.start(1)))
    if 31 in selected_rules:
        entries = [n for n in ir['nodes'] if n['kind']=='BibliographyEntry' and n['text']]
        alternatives = sum(bool(re.search(r'\((?:19|20)\d{2}[a-z]?\)|\b(?:vol\.|pp\.|no\.)|[\"“].+[\"”]', n['text'], re.I)) for n in entries)
        typed = sum(bool(_TYPE.search(n['text'])) for n in entries)
        alternate_style = bool(entries) and alternatives/len(entries) >= .6 and typed/len(entries) < .3
        for node in ir['nodes']:
            if node['kind'] != 'BibliographyEntry' or not node['text']:
                continue
            text = node['text']
            if re.search(r'[\x00\ufffd\ud800-\udfff]', text):
                continue
            markers = list(_TYPE.finditer(text))
            reason = None
            if not markers and not alternate_style and not re.search(r'[\[［](?:硕士|博士|学位).{0,4}论文[\]］]', text) and _YEAR.search(re.sub(r'https?://\S+', '', text)) and len(compact(text)) >= 25:
                reason = '缺少完整的方括号文献类型标记'
            elif markers and not any(m.group(1).upper() in _CODES and (not m.group(2) or m.group(2).upper() in _MEDIA) for m in markers):
                reason = '文献类型或载体标记不在国标代码表中'
            if reason:
                results['31']['findings'].append(_finding(ir, 31, node, reason, '文献类型标记',
                    '请按实际著录资源核对并补齐类型标记；期刊用[J]、会议论文用[C]等，不能仅凭访问网址改变资源类型。'))
    if 36 in selected_rules:
        body_start = _body_start_page(ir)
        keyword_blocks = 0
        for node in ir['nodes']:
            if not _KEYWORD_LABEL.search(node.get('text') or ''):
                continue
            if body_start and _node_page_index(node) >= body_start:
                continue
            keyword_blocks += 1
            node = _keyword_block(ir, node)
            terms = _keyword_terms(node['text'])
            if not 3 <= len(terms) <= 8:
                results['36']['findings'].append(_finding(ir, 36, node,
                    f'关键词共 {len(terms)} 个，国标要求 3—8 个。', '关键词数量',
                    '请将关键词调整为 3—8 个，并用分号分隔；依据 GB/T 7713.1—2025 附录 A、表 A.1。'))
        if not keyword_blocks:
            results['36'].update(status='unsupported', reason='未能检测：未可靠识别摘要中的关键词，无法检查关键词数量。')
    if 37 in selected_rules:
        for node in _abstract_nodes(ir):
            text = node['text']
            for label, pattern in _OBJECT_NUMBERS:
                for match in pattern.finditer(text):
                    if label == '参考文献' and _technical_bracket(text, match.start(), match.end()):
                        continue
                    context = text[max(0, match.start()-6):match.end()+6].replace('\n', '')
                    results['37']['findings'].append(_finding(ir, 37, node,
                        f'摘要中出现了{label}编号“{match.group()}”（“…{context}…”）；摘要应独立成文，不引用图表、公式或参考文献编号。',
                        match.group(),
                        f'请删除摘要中的{label}编号“{match.group()}”，改用文字概括相应内容。',
                        offset=match.start()))
    if 38 in selected_rules:
        for page, box, text, node, prior in chapter_labels(ir):
            if not prior:
                continue
            label = compact(text)
            results['38']['findings'].append(_finding(ir, 38, node,
                f'{label}未从新页开始：该章标题上方仍有上一章内容。', label,
                f'请在“{label}”前插入分页符，使该章标题从新页页首开始。'))
    if ir['coverage']['pages']['status'] != 'complete':
        for result in results.values(): result['reason'] = '仅检查可读取文字；未将扫描或不可读内容判为缺失。'
    return results
