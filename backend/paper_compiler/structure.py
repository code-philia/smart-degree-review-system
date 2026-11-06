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


def _rows(page, *, with_source=False):
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
            values.append((index, text))
    # Join positioned short glyphs once, rather than generating overlapping
    # 摘/要 or 关/键/词 pairs that could masquerade as keyword values.
    groups = []
    for index, line in enumerate(lines):
        short = re.sub(r'\s+', '', line['text'])
        joined = ''.join(item['text'] for _, item in groups[-1]) + line['text'] if groups else ''
        keyword_tail = bool(re.match(r'^(?:关\s*键\s*[词字]|key\s*words?\b|index\s+terms\b)', joined, re.I))
        if not (line.get('bbox') and (0 < len(short) <= 2 or short.lower() in {'key', 'index'} or keyword_tail)):
            continue
        box = line['bbox']
        if groups and abs(groups[-1][-1][1]['bbox'][1] - box[1]) <= 3 and 0 <= box[0] - groups[-1][-1][1]['bbox'][2] <= 50:
            groups[-1].append((index, line))
        else:
            groups.append([(index, line)])
    for group in groups:
        if len(group) > 1:
            indices = {index for index, _ in group}
            values = [(index, text) for index, text in values if index not in indices]
            values.append((group[0][0], ''.join(line['text'] for _, line in group)))
    normalized = [{**lines[index], 'text': unicodedata.normalize('NFKC', text).strip()}
                  for index, text in sorted(values, key=lambda value: value[0])]
    return normalized if with_source else [line['text'] for line in normalized]


def has_bilingual_abstract_bodies(pages):
    """Recover paired abstracts whose titles do not identify their language.

    Require separate front-matter pages with substantial language-specific prose
    and matching keyword lines. Covers, contents and body quotations cannot
    provide the missing abstract merely by containing English text.
    """
    found = {'zh': set(), 'en': set()}
    for index, page in enumerate(pages):
        texts = _rows(page)
        compact = {re.sub(r'\s+', '', text).lower() for text in texts}
        if compact & {'目录', '目次', 'contents', 'tableofcontents'} or sum(bool(_LEADER.search(text)) for text in texts) >= 4:
            break
        if any(_INTRO.fullmatch(_NUMBER.sub('', text).strip()) for text in texts):
            break
        if not compact & {'摘要', '中文摘要', '英文摘要', 'abstract'}:
            continue
        markers = [order for order, text in enumerate(texts)
                   if re.sub(r'\s+', '', text).lower() in {'摘要', '中文摘要', '英文摘要', 'abstract'}]
        for keyword, label in enumerate(texts):
            if not re.match(r'^(?:关键词|关键字|key\s*words?|index\s+terms)\s*[:：—–-]', label, re.I):
                continue
            start = max((marker for marker in markers if marker < keyword), default=-1)
            if start < 0:
                continue
            prose = '\n'.join(texts[start + 1:keyword])
            han = len(re.findall(r'[\u3400-\u9fff]', prose))
            words = len(re.findall(r'\b[A-Za-z]{2,}\b', prose))
            if han >= 80 and han >= words * 2 and re.match(r'^(?:关键词|关键字)', label):
                found['zh'].add(index)
            if words >= 60 and words >= han * 2 and re.match(r'^(?:key\s*words?|index\s+terms)', label, re.I):
                found['en'].add(index)
    return any(chinese != english for chinese in found['zh'] for english in found['en'])


def abstract_sections(pages, profile):
    """Bound native abstract evidence before building any typed Paper nodes.

    Keywords close a thesis abstract; a later abstract/chapter cannot supply its
    missing tail. This checks structure, not prose length or semantic coverage.
    """
    sections = []
    current = None
    for index, page in enumerate(pages):
        texts = []
        for source in _rows(page, with_source=True):
            if (texts and texts[-1]['text'].lower() in {'key', 'index'}
                    and re.match(r'^(?:words?|terms)\b', source['text'], re.I)):
                texts[-1]['text'] += ' ' + source['text']
            else:
                texts.append(source)
        if sum(bool(_LEADER.search(row['text'])) for row in texts) >= 4:
            break
        for source in texts:
            text = source['text']
            compact = re.sub(r'\s+', '', text).lower()
            size, box = source.get('font_size', 0), source.get('bbox', [])
            heading = _NUMBER.sub('', text).strip()
            chapter = re.match(r'^(?:第\s*[一二三四五六七八九十百\d\s]+章|chapter\s*\d+\b)(?:\s|[:：]|$)', text, re.I)
            chapter_heading = chapter and len(text) <= 100 and not re.search(r'[，。；;!?！？]', text)
            if (compact in {'目录', '目次', 'contents', 'tableofcontents', '参考文献',
                            'references', 'bibliography', '致谢', 'acknowledgements'}
                    or _INTRO.fullmatch(heading)
                    or chapter_heading):
                return _abstract_statuses(sections, profile)
            title = re.match(r'^(摘要|中文摘要|英文摘要|abstract)(?:(?:\s*[:：—–-]\s*|\s+)(.*))?$', text, re.I)
            if compact in {'摘要', '中文摘要', '英文摘要', 'abstract'}:
                title = re.match(r'(.*)', compact)
            if title:
                label = re.sub(r'\s+', '', title[1]).lower()
                # A smaller running header on a continuation page is not a new
                # abstract, including when the preceding page closed keywords.
                if (current and label == current['label'] and index > current['page_index']
                        and size and current['heading_size'] and size < current['heading_size'] * .88
                        and box and box[1] < page.get('height', 842) * .12):
                    continue
                current = {'label': label, 'page_index': index, 'heading_size': size,
                           'at_top': bool(box and box[1] < page.get('height', 842) * .12),
                           'body': [], 'keywords': None, 'keyword_language': None, 'keyword_groups': []}
                sections.append(current)
                if title.lastindex and title.lastindex >= 2 and title[2]:
                    current['body'].append(title[2])
                continue
            if not current or re.fullmatch(r'[\d\sivxlcdmIVXLCDM-]+', text):
                continue
            if len(compact) < 50 and re.search(r'(?:博士|硕士|学位)论文$', compact):
                continue
            keyword = re.match(r'^(?:关\s*键\s*[词字]|key\s*words?\b|index\s+terms\b)\s*[:：—–-]?\s*(.*)$', text, re.I)
            # Retain positional observations: small text at the physical edge
            # cannot prove abstract prose or supply an empty keyword list.
            height = page.get('height')
            if (not keyword and box and height and size and size <= 10
                    and (box[3] <= height * .06 or box[1] >= height * .95)):
                continue
            if keyword:
                if current['keywords'] is not None:
                    current['keyword_groups'].append((current['keyword_language'], current['keywords']))
                current['keywords'] = [keyword[1]]
                current['keyword_language'] = 'zh' if re.match(r'^关', text) else 'en'
            elif current['keywords'] is not None:
                current['keywords'].append(text)
            else:
                current['body'].append(text)
    return _abstract_statuses(sections, profile)


def _abstract_statuses(sections, profile):
    def language(body):
        text = '\n'.join(body)
        han = len(re.findall(r'[\u3400-\u9fff]', text))
        words = len(re.findall(r'\b[A-Za-z]+\b', text))
        return 'en' if words > han * 2 else 'zh' if han else None

    continued = []
    for section in sections:
        previous = continued[-1] if continued else None
        if (previous and previous['label'] == section['label']
                and section['page_index'] > previous['page_index'] and section['at_top']
                and previous['keywords'] is None
                and (not section['body'] or language(section['body']) == language(previous['body']))):
            previous['body'].extend(section['body'])
            previous['keywords'] = section['keywords']
            previous['keyword_language'] = section['keyword_language']
            previous['keyword_groups'].extend(section['keyword_groups'])
        else:
            continued.append(section)
    result = {}
    for section in continued:
        prose = '\n'.join(section['body'])
        han = len(re.findall(r'[\u3400-\u9fff]', prose))
        words = len(re.findall(r'\b[A-Za-z]+\b', prose))
        english = section['label'] in {'英文摘要', 'abstract'} or (words > 0 and words > han * 2)
        name = '英文摘要' if english and profile == 'chinese-thesis' else '摘要'
        issues = []
        if not re.search(r'[\u3400-\u9fff]|[A-Za-z]', prose):
            issues.append('未识别到摘要正文')
        expected_language = 'en' if english else 'zh'
        groups = section['keyword_groups'] + [(section['keyword_language'], section['keywords'] or [])]
        has_keywords = any(any(char.isalnum() for char in '\n'.join(values))
                           and (label_language == expected_language or language(values) == expected_language)
                           for label_language, values in groups)
        if profile != 'research-article' and not has_keywords:
            issues.append('未识别到本摘要的非空关键词收尾，无法确认摘要完整')
        evidence = {'status': 'incomplete' if issues else 'complete',
                    'page_number': section['page_index'] + 1, 'has_keywords': has_keywords, 'issues': issues}
        # Repeated labels/noisy empty headings cannot override an independently
        # complete abstract; an incomplete duplicate cannot invent completeness.
        if name not in result or result[name]['status'] != 'complete':
            result[name] = evidence
    return result


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
    keywords = any(re.match(r'^(?:关键词|关键字|key\s*words?|index\s+terms)(?:\s*[:：—–-]\s*|\s+)\S', text, re.I)
                   or re.match(r'^(?:关键词|关键字)[:：]\S', compact(text)) for _, _, text in source_rows)
    intro = [(order, text) for order, _, text, heading in headings if _INTRO.fullmatch(heading)]
    references = [(order, text) for order, _, text, heading in headings if compact(heading) in {'参考文献', '參考文獻', 'references', 'bibliography'}]
    first_body = min((order for order, _ in intro), default=-1)
    intro_key = _section_key(intro[0][1]) if intro else None
    intro_source = next(((index, text) for order, index, text in source_rows if order == first_body), None)
    intro_style = styles.get(intro_source, (0, False))
    def core_conclusion(index, text):
        size, _ = styles.get((index, text), (0, False))
        # A conclusion label in an introductory diagram or a summary subsection
        # is not the paper's final section and cannot close its body scope.
        if size and intro_style[0] and size < intro_style[0] * .88:
            return False
        key = _section_key(text)
        return not (key and intro_key and (key[0] != intro_key[0] or key[2] != intro_key[2]))
    conclusion = [(order, text) for order, index, text, heading in headings
                  if order > first_body and _CONCLUSION.fullmatch(heading) and core_conclusion(index, text)]
    body_end = min((order for order, _ in conclusion + references if order > first_body), default=len(rows))
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
    abstracts = abstract_sections(pages, profile)
    chinese_abstract = '摘要' in abstracts
    english_abstract = '英文摘要' in abstracts if profile == 'chinese-thesis' else chinese_abstract
    keywords = keywords or any(value['has_keywords'] for value in abstracts.values())
    observed = {'摘要': chinese_abstract if profile == 'chinese-thesis' else chinese_abstract or english_abstract,
                '英文摘要': english_abstract, '关键词': keywords, '目录': bool(contents_pages),
                '引言': bool(intro), '主体': body, '结论': bool(conclusion), '参考文献': bool(references)}
    required = (['摘要', '英文摘要', '关键词', '目录', '引言', '主体', '结论', '参考文献'] if profile == 'chinese-thesis' else
                ['摘要', '关键词', '目录', '引言', '主体', '结论', '参考文献'] if profile == 'english-thesis' else
                ['摘要', '引言', '主体', '结论', '参考文献'])
    missing = [name for name in required if not observed[name]]
    incomplete = [name for name in required if abstracts.get(name, {}).get('status') == 'incomplete']
    return {'profile': profile, 'status': 'rejected' if missing or incomplete else 'accepted',
            'required_sections': required, 'observed_sections': observed, 'missing_sections': missing,
            'incomplete_sections': incomplete, 'abstract_sections': abstracts}
