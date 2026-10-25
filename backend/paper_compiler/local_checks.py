"""Three native-text checks over the shared Paper Model / Paper IR. No network."""
import re

RULES = (31, 34, 35)  # execution keys only; public titles have no rule numbers
_CHAPTER = re.compile(r'^(?:第[一二三四五六七八九十百0-9]+[章篇]|chapter\d+|\d+(?:[.．]\d+)*[.．、]?)', re.I)
_INTRO = re.compile(r'^(?:绪论|绪言|引言|引论|introduction)$', re.I)
_CONCLUSION = re.compile(r'^(?:(?:课题|全文|研究|工作|论文)?(?:总结|结论)(?:[与和及](?:未来)?(?:展望|工作|建议|讨论))?|总结|结论|总结[与和及](?:未来)?展望|结论[与和及](?:未来)?展望|总结[与和及]未来工作|研究结论|全文总结|研究总结|总结展望|结论及建议|结束语|conclusions?(?:andfuturework)?|summary(?:and(?:futurework|outlook))?)$', re.I)
_TYPE = re.compile(r'[\[［]\s*([A-Za-z]{1,3})(?:\s*/\s*([A-Za-z]{1,2}))?\s*[\]］]')
_CODES = set('M J N C D R S P EB A CM DS PP G GI CP DB Z'.split())
_MEDIA = {'MT', 'DK', 'CD', 'OL', 'MM'}
_YEAR = re.compile(r'(?<!\d)(?:1[5-9]|20)\d{2}(?!\d)')
_PUNCT = re.compile(r'(?<=[\u4e00-\u9fff])\s*([,;:!?])\s*(?=[\u4e00-\u9fff])')


def compact(text):
    return re.sub(r'\s+', '', text or '').casefold()


def _source(span):
    if span.get('kind') == 'source':
        return span
    ancestors = span.get('ancestor_provenance', span.get('input_provenance', []))
    return next((source for item in ancestors if (source := _source(item))), None)


def rows(ir):
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
                continue
            if span.get('kind') == 'synthetic' or len(node['provenance']) == 1:
                text = node['text']
            else:
                text = node['text'][span.get('node_text_start', 0):span.get('node_text_end', len(node['text']))]
            pieces.append((source['page_index'], source['bbox'], text, node))
    grouped = []
    for page, box, text, node in sorted(pieces, key=lambda p: (p[0], p[1][1], p[1][0])):
        if grouped and page == grouped[-1][0] and abs(box[1] - grouped[-1][1][1]) <= 3 and box[0] >= grouped[-1][1][2] and box[0] - grouped[-1][1][2] <= 60:
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
        rect = dict(x1=x0, y1=y0, x2=x1, y2=y1, width=page['width'], height=page['height'], page_number=source['page_index'] + 1)
        location = {'type': 'pdf_bbox', 'page_number': source['page_index'] + 1,
                    'bounding_rect': rect, 'rects': [rect], 'text_excerpt': node['text'][:600]}
    return {'rule_id': str(rule), 'node_id': node['id'], 'token': token, 'message': message,
            'suggestion': suggestion, 'location': location, 'text_excerpt': (node['text'] or '')[:600]}


def title_page_evidence(ir, visual_rows):
    if any(n['kind'] == 'TitlePage' for n in ir['nodes']):
        return True
    grouped = {}
    for page, box, text, node in visual_rows:
        grouped.setdefault(page, []).append(compact(text))
    uncertain = False
    for page in sorted(grouped)[:6]:
        texts = grouped[page]
        if any(t in {'摘要', 'abstract', '目录', '目次', 'contents'} or re.match(r'^(?:关键词|关键字|keywords?)(?:[:：]|$)', t) or _INTRO.fullmatch(_CHAPTER.sub('', t)) for t in texts):
            break
        if any(re.search(r'(?:\.\s*){3,}\s*\d+\s*$', t) for t in texts):
            break  # A contents continuation cannot be an unfamiliar title page.
        declaration = any(re.search(r'(?:原创性|独创性|原创|使用授权|版权授权|版权使用).{0,8}(?:声明|说明|书)$', t) for t in texts if len(t) < 45)
        if declaration:
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


def core_parts(ir):
    visual_rows = rows(ir)
    texts = [compact(text) for _, _, text, _ in visual_rows]
    intro_pages = [page for page, _, text, _ in visual_rows if _INTRO.fullmatch(_CHAPTER.sub('', compact(text)))]
    toc_pages = [page for page, _, text, _ in visual_rows if re.search(r'(?:\.\s*){3,}\s*\d+\s*$', text)]
    body_start = max(max(toc_pages, default=-1)+1, min(intro_pages, default=0))
    body_end = min((page for page,_,text,node in visual_rows if page >= body_start and (_CONCLUSION.fullmatch(_CHAPTER.sub('',compact(text))) or compact(text) in {'参考文献','references','bibliography'})), default=len(ir['layout']['pages']))
    headings = [_CHAPTER.sub('', text) for text in texts]
    kinds = {node['kind'] for node in ir['nodes']}
    all_text = '\n'.join(t for t in texts if len(t) <= 55 and not re.search(r'[，。；]', t))
    by_id = {node['id']: node for node in ir['nodes']}
    return {
        '题名页': title_page_evidence(ir, visual_rows),
        '原创性声明': bool(re.search(r'原创性声明|独创性声明|原创声明|学术诚信声明', all_text)),
        '使用授权说明': bool(re.search(r'(?:使用|版权)授权(?:书|说明|声明)?|授权使用|版权使用(?:说明|声明|书)', all_text)),
        '摘要': 'Abstract' in kinds or any(t in {'摘要', '中文摘要', 'abstract'} for t in texts),
        '关键词': any(re.match(r'^(?:关键词|关键字|keywords?)(?:[:：]|$)', text) for text in texts),
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
    pending = [node['id'] for node in ir['nodes'] if node['kind'] in {'BackMatter', 'Bibliography', 'Biography'}]
    excluded = set()
    while pending:
        nid = pending.pop()
        excluded.add(nid)
        pending.extend(by_id[nid]['children'])
    return [node for node in ir['nodes'] if node['kind'] == 'Paragraph' and node['text'] and node['id'] not in excluded]


def detect_ir(ir, selected_rules=RULES):
    results = {str(rule): {'status': 'completed', 'findings': []} for rule in selected_rules}
    anchor = next((n for n in ir['nodes'] if n['text'] and n['provenance']), None)
    if 34 in selected_rules and anchor:
        # Absence is justified only after a complete native-text pass. A scanned
        # statement or blank page is not evidence that a required part is absent.
        if ir['coverage']['pages']['status'] == 'complete':
            results['34']['findings'] = [_finding(ir, 34, anchor, f'未发现国标必备部分“{part}”', part,
                f'请补齐或核对{part}；依据 GB/T 7713.1—2025 附录 A、表 A.1。')
                for part, present in core_parts(ir).items() if present is False]
    if 35 in selected_rules:
        for node in prose_nodes(ir):
            if node['kind'] != 'Paragraph' or not node['text']:
                continue
            text = node['text']
            if re.search(r'https?://|www\.|[`=<>{}|]|[A-Za-z_]\w*\s*:\s*(?:true|false|null|None)\b|(?:代码|配置|模板|示例|提示词)\s*[:：]|\b(?:print|def|return|import|if|while)\s*\(', text):
                continue
            for match in _PUNCT.finditer(text):
                if re.search(r'(?:字符|符号|终止符|分隔符|标点|运算符)\s*$', text[:match.start(1)]):
                    continue
                if any(m.start() <= match.start(1) < m.end() for m in re.finditer(r'"[^"\n]*"|“[^”\n]*”', text)):
                    continue
                mark = match.group(1)
                replacement = dict(zip(',;:!?', '，；：！？'))[mark]
                results['35']['findings'].append(_finding(ir, 35, node,
                    f'中文文字之间使用了半角标点“{mark}”', mark, f'将此处“{mark}”改为“{replacement}”。', offset=match.start(1)))
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
    if ir['coverage']['pages']['status'] != 'complete':
        for result in results.values(): result['reason'] = '仅检查可读取文字；未将扫描或不可读内容判为缺失。'
    return results
