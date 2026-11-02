"""Source-level structural grammar; this runs before any typed Paper is built."""
import re
import unicodedata

_NUMBER = re.compile(r'^(?:第\s*[一二三四五六七八九十百\d\s]+[章篇节]|chapter\s*\d+|[ivxlcdm]+\.\s*|\d+(?:[.．]\d+)*[.．、]?)[\s:：-]*', re.I)
_INTRO = re.compile(r'^(?:绪论|绪言|引言|引论|简介|introduction(?:\s+and\s+contextualization)?)$', re.I)
_CONCLUSION = re.compile(r'^(?:(?:课题|全文|研究|工作|论文)?(?:总结|结论)(?:[与和及](?:未来)?(?:展望|工作|建议|讨论))?|总结展望|结论及建议|结语|结束语|conclusions?(?:\s+and\s+(?:future\s+(?:work|directions|research)|discussion|outlook))?|concluding\s+remarks|summary(?:\s+and\s+(?:future\s+work|outlook|conclusions?))?)$', re.I)
_BODY = re.compile(r'^(?:相关工作|研究方法|方法|实验(?:评估|结果|分析)?|结果(?:与讨论)?|背景|related\s+work|background|methods?|methodology|experiments?(?:\s+and\s+evaluation)?|evaluation|results?(?:\s+and\s+discussion)?|discussion)$', re.I)
_LEADER = re.compile(r'(?:\.\s*){3,}|…|·{3,}')
_BARE_CHAPTER = re.compile(r'^(?:第\s*[一二三四五六七八九十百\d\s]+章|chapter\s*\d+)$', re.I)


def _section_key(text):
    chapter = re.match(r'^(第\s*[一二三四五六七八九十百\d\s]+章|chapter\s*\d+)', text, re.I)
    if chapter:
        return 'chapter', re.sub(r'\s+', '', chapter[0]).lower(), 1
    section = re.match(r'^(\d+(?:\.\d+)*|[ivxlcdm]+\.)(?:\s|[.、]|$)', text, re.I)
    if section:
        number = section[1].rstrip('.')
        return 'section', number.lower(), number.count('.') + 1
    return None


def _rows(page):
    lines = page.get('lines', [])
    values = []
    for index, line in enumerate(lines):
        text = line['text'].strip()
        if _BARE_CHAPTER.fullmatch(text) and line.get('bbox'):
            for right in lines[index + 1:index + 5]:
                other = right['text'].strip()
                if not other or len(other) > 80 or not right.get('bbox'):
                    continue
                a, b = line['bbox'], right['bbox']
                size, other_size = line.get('font_size', 0), right.get('font_size', 0)
                peer_style = not size or not other_size or .9 <= other_size / size <= 1.1
                same_row = abs(a[1] - b[1]) <= 3 and 0 <= b[0] - a[2] <= 150
                next_row = 0 <= b[1] - a[3] <= max(24, size * 1.6)
                if peer_style and (same_row or next_row) and not _LEADER.search(other):
                    text += ' ' + other
                    break
        if text:
            values.append(text)
    # PDFs sometimes split 摘/要 or 目/录 into separate positioned source lines.
    tiny = [line for line in lines if 0 < len(re.sub(r'\s+', '', line['text'])) <= 2 and line.get('bbox')]
    for index, left in enumerate(tiny):
        for right in tiny[index + 1:]:
            a, b = left['bbox'], right['bbox']
            if abs(a[1] - b[1]) <= 3 and 0 <= b[0] - a[2] <= 50:
                values.append(left['text'] + right['text'])
    return [unicodedata.normalize('NFKC', text).strip() for text in values]


def assess_structure(pages, identity):
    rows = [(index, text) for index, page in enumerate(pages) for text in _rows(page)]
    styles = {(index, unicodedata.normalize('NFKC', line['text']).strip()):
              (line.get('font_size', 0), bool(line.get('is_bold') or any(char.get('flags', 0) & 16 for char in line.get('chars', []))))
              for index, page in enumerate(pages) for line in page.get('lines', [])}
    for index, text in rows:
        if (index, text) not in styles:
            prefix = next((line['text'].strip() for line in pages[index].get('lines', [])
                           if _BARE_CHAPTER.fullmatch(line['text'].strip()) and text.startswith(line['text'].strip())), None)
            if prefix:
                styles[index, text] = styles.get((index, prefix), (0, False))
    compact = lambda text: re.sub(r'\s+', '', text).lower()
    contents_pages = {index for index, text in rows if compact(text) in {'目录', '目次', 'contents', 'tableofcontents'}}
    for index, page in enumerate(pages):
        if sum(bool(_LEADER.search(text)) for text in _rows(page)) >= 4:
            contents_pages.add(index)
    def heading_text(text):
        value = _NUMBER.sub('', text).strip()
        return re.sub(r'\s+', '', value) if re.search(r'[\u3400-\u9fff]', value) else value
    source_rows = [(order, index, text) for order, (index, text) in enumerate(rows) if index not in contents_pages]
    headings = [(order, index, text, heading_text(text)) for order, index, text in source_rows
                if index not in contents_pages and len(text) <= 120 and not _LEADER.search(text)]
    abstracts = {compact(text) for _, _, text in source_rows}
    chinese_abstract = any(re.match(r'^(?:中文)?摘要(?:[:：\s]|$)', text) for _, _, text in source_rows) or bool(abstracts & {'摘要', '中文摘要'})
    english_abstract = any(re.match(r'^(?:英文摘要|abstract)(?:[:：—–\s-]|$)', text, re.I) for _, _, text in source_rows) or bool(abstracts & {'abstract', '英文摘要'})
    keywords = any(re.match(r'^(?:关键词|关键字|key\s*words?|index\s+terms)(?:\s*[:：—–-]\s*|\s+)\S', text, re.I)
                   or re.match(r'^(?:关键词|关键字)[:：]\S', compact(text)) for _, _, text in source_rows)
    intro = [(order, text) for order, _, text, heading in headings if _INTRO.fullmatch(heading)]
    conclusion = [(order, text) for order, _, text, heading in headings if _CONCLUSION.fullmatch(heading)]
    references = [(order, text) for order, _, text, heading in headings if compact(heading) in {'参考文献', '參考文獻', 'references', 'bibliography'}]
    first_body = min((order for order, _ in intro), default=-1)
    body_end = min((order for order, _ in conclusion + references if order > first_body), default=len(rows))
    intro_key = _section_key(intro[0][1]) if intro else None
    intro_source = next(((index, text) for order, index, text in source_rows if order == first_body), None)
    intro_style = styles.get(intro_source, (0, False))
    def body_heading(index, text, heading):
        if re.search(r'[。；;]|[.!?]$', heading):
            return False
        size, bold = styles.get((index, text), (0, False))
        if intro_style[0] and (size < intro_style[0] * .88
                              or (intro_style[1] and not bold and size <= intro_style[0])):
            return False
        key = _section_key(text)
        if intro_key:
            # Introduction subsections and its numbered lists are not a main
            # chapter. A separate peer chapter/section must exist after it.
            return bool(key and key[0] == intro_key[0] and key[2] == intro_key[2]
                        and key[1] != intro_key[1] and heading)
        return bool((key and key[2] == 1 and heading) or (not key and _BODY.fullmatch(heading)))
    body = any(first_body < order < body_end and not _INTRO.fullmatch(heading)
               and not _CONCLUSION.fullmatch(heading)
               and compact(heading) not in {'参考文献', 'references', 'bibliography'}
               and len(heading) <= 80 and body_heading(index, text, heading)
               for order, index, text, heading in headings)
    # A required section may not select its own grammar: deleting Contents must
    # never downgrade a thesis, and adding Contents must not upgrade an article.
    chapter_cue = any(re.match(r'^(?:第\s*[一二三四五六七八九十百\d\s]+章|chapter\s*\d+\b)', text, re.I)
                      for _, _, text in source_rows)
    degree_cue = any(index < 8 and re.search(r'指导教师|博士生|硕士生|博士研究生|硕士研究生|submitted.*degree|degree\s+of\s+(?:doctor|master)', text, re.I)
                     for index, text in rows)
    is_thesis = identity['signals']['academic_cover'] or chapter_cue or degree_cue
    joined = ''.join(text for _, text in rows)
    chinese = len(re.findall(r'[\u3400-\u9fff]', joined)) > len(re.findall(r'[A-Za-z]+', joined))
    profile = ('chinese-thesis' if chinese else 'english-thesis') if is_thesis else 'research-article'
    observed = {'摘要': chinese_abstract if profile == 'chinese-thesis' else chinese_abstract or english_abstract,
                '英文摘要': english_abstract, '关键词': keywords, '目录': bool(contents_pages),
                '引言': bool(intro), '主体': body, '结论': bool(conclusion), '参考文献': bool(references)}
    required = (['摘要', '英文摘要', '关键词', '目录', '引言', '主体', '结论', '参考文献'] if profile == 'chinese-thesis' else
                ['摘要', '关键词', '目录', '引言', '主体', '结论', '参考文献'] if profile == 'english-thesis' else
                ['摘要', '引言', '主体', '结论', '参考文献'])
    missing = [name for name in required if not observed[name]]
    return {'profile': profile, 'status': 'rejected' if missing else 'accepted',
            'required_sections': required, 'observed_sections': observed, 'missing_sections': missing}
