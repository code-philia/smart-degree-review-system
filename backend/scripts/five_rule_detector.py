"""Local, PDF-only detectors for mutation rules 6, 18, 22, 24 and 28.

The detector never receives a mother PDF or mutation plan. PyMuPDF is used only
for text and geometry extraction; it does not modify or rasterize the input.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median

import pymupdf

RULES = (6, 18, 22, 24, 28)
TITLES = {6: '摘要连续内容重复', 18: '公式引用目标不存在', 22: '文献引用目标不存在',
          24: '参考文献未被全文引用', 28: '目录页码与正文不一致'}
_CITATION = re.compile(r'\[(\d+(?:(?:\s*[-–—－,，、;；]\s*|\s+)\d+)*)\]')
_FORMULA_REFERENCE = re.compile(r'(?:公式|(?<!公)式|equation|eq\.?)[\s:：]*[（(]\s*(\d+(?:\s*[.．–—－−-]\s*\d+)+[a-z]?)\s*[)）]', re.I)
_DISPLAY_FORMULA = re.compile(r'^[（(]\s*(\d+(?:\s*[.．–—－−-]\s*\d+)+[a-z]?)\s*[)）]$', re.I)
_DISPLAY_FORMULA_TAIL = re.compile(r'[（(]\s*(\d+(?:\s*[.．–—－−-]\s*\d+)+[a-z]?)\s*[)）]\s*$', re.I)
_TOC_ENTRY = re.compile(r'^\s*(.+?)(?:(?:\.\s*){2,}|…{2,}|⋯{2,}|·{2,})\s*(\d{1,4})\s*$')
_TOC_HEADING = re.compile(r'^(?:第\s*[一二三四五六七八九十\d]+\s*章|[1-9]\d*(?:[.．]\d+)*(?=\s|[\u4e00-\u9fff])|chapter\s+[1-9]\d*|致谢|参考文献|附录|acknowledg(?:e)?ments?|references|bibliography|学术论文|科研成果|研究成果|攻读.{0,20}期间|发表.{0,12}论文|个人简历|作者简介|publications?|research\s+(?:outputs?|achievements?))', re.I)
_REF_LABEL = re.compile(r'^\s*\[(\d+)\]')
_CHAPTER = re.compile(r'^(?:第\s*(?:\d+|[一二三四五六七八九十]+)\s*章|chapter\s+[1-9]\d*|1[\s.．]+[^0-9]|introduction|引言|绪论)', re.I)


@dataclass(frozen=True)
class Line:
    page: int  # one based physical PDF page
    text: str
    bbox: tuple[float, float, float, float]
    page_width: float
    page_height: float
    span_sizes: tuple[tuple[int, int, float], ...] = ()


def extract_lines(pdf_path: Path) -> tuple[list[Line], int]:
    lines = []
    with pymupdf.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf, 1):
            for block in page.get_text('dict', sort=True)['blocks']:
                if block['type'] != 0:
                    continue
                for raw in block['lines']:
                    untrimmed = ''.join(span['text'] for span in raw['spans'])
                    content = untrimmed.strip()
                    if content:
                        left_trim = len(untrimmed) - len(untrimmed.lstrip())
                        cursor = 0
                        span_sizes = []
                        for span in raw['spans']:
                            start = max(0, cursor - left_trim)
                            end = min(len(content), cursor + len(span['text']) - left_trim)
                            if end > start:
                                span_sizes.append((start, end, float(span['size'])))
                            cursor += len(span['text'])
                        lines.append(Line(page_number, content, tuple(raw['bbox']),
                                          page.rect.width, page.rect.height, tuple(span_sizes)))
        return lines, len(pdf)


def _compact(text: str) -> str:
    return re.sub(r'[^\w\u4e00-\u9fff]', '', text).casefold()


def _heading(text: str) -> str:
    return re.sub(r'\s+', '', text).casefold()


def _finding(rule: int, line: Line, message: str, token: str = '', **extra) -> dict:
    x0, y0, x1, y1 = (round(v, 2) for v in line.bbox)
    rect = {'x1': x0, 'y1': y0, 'x2': x1, 'y2': y1,
            'width': round(line.page_width, 2), 'height': round(line.page_height, 2),
            'page_number': line.page}
    return {'rule_id': str(rule), 'page': line.page, 'bbox': [x0, y0, x1, y1],
            'text_excerpt': line.text[:220], 'token': token, 'message': message,
            'location': {'type': 'pdf_bbox', 'page_number': line.page,
                         'bounding_rect': rect, 'rects': [rect], 'text_excerpt': line.text[:220]},
            **extra}


def _result(findings: list[dict] | None = None, reason: str = '') -> dict:
    if reason:
        return {'status': 'unsupported', 'reason': reason, 'findings': []}
    return {'status': 'completed', 'findings': findings or []}


def _visual_rows(lines: list[Line]) -> list[Line]:
    """Join PDF fragments on the same visual row using geometry, then x order."""
    by_page = defaultdict(list)
    for line in lines:
        by_page[line.page].append(line)
    rows = []
    for page, page_lines in by_page.items():
        groups = []
        for line in sorted(page_lines, key=lambda item: (item.bbox[1] + item.bbox[3]) / 2):
            center = (line.bbox[1] + line.bbox[3]) / 2
            group = next((group for group in groups if abs(center - sum((item.bbox[1] + item.bbox[3]) / 2 for item in group) / len(group)) <= 8), None)
            if group is None:
                groups.append([line])
            else:
                group.append(line)
        for group in groups:
            group.sort(key=lambda item: item.bbox[0])
            bbox = (min(item.bbox[0] for item in group), min(item.bbox[1] for item in group),
                    max(item.bbox[2] for item in group), max(item.bbox[3] for item in group))
            rows.append(Line(page, ' '.join(item.text for item in group), bbox,
                             group[0].page_width, group[0].page_height))
    return rows


def _toc_pages(lines: list[Line], page_count: int) -> set[int]:
    by_page = defaultdict(list)
    for row in _visual_rows(lines):
        by_page[row.page].append(row.text)
    pages = set()
    max_candidate = min(60, max(2, int(page_count * .5)))
    headings_by_page = {}
    for page, texts in by_page.items():
        if page > max_candidate:
            continue
        entries = [_TOC_ENTRY.match(text) for text in texts]
        headings = [match.group(1).strip() for match in entries if match]
        headings_by_page[page] = headings
        chapter_like = sum(bool(re.match(r'^(?:第\s*(?:\d+|[一二三四五六七八九十]+)\s*章|\d+(?:[.．]\d+)*\s+)', text)) for text in headings)
        if len(headings) >= 3 and chapter_like >= 2:
            pages.add(page)
    if pages:
        groups = []
        for page in sorted(pages):
            if not groups or page > groups[-1][-1] + 1:
                groups.append([page])
            else:
                groups[-1].append(page)
        pages = set(max(groups, key=lambda group: (len(group), -group[0])))
        for direction, boundary in ((-1, min(pages)), (1, max(pages))):
            page = boundary + direction
            while 1 <= page <= max_candidate:
                headings = headings_by_page.get(page, [])
                if not headings or all(re.match(r'^[图表]\s*\d', text) for text in headings):
                    break
                pages.add(page)
                page += direction
    return pages


def _body_start(lines: list[Line], toc_pages: set[int]) -> int:
    after_toc = max(toc_pages, default=0)
    for line in lines:
        if line.page > after_toc and _CHAPTER.match(line.text.strip()):
            return line.page
    return after_toc + 1


def _reference_start(lines: list[Line], body_start: int, page_count: int) -> int | None:
    by_page = defaultdict(list)
    for line in lines:
        by_page[line.page].append(line)
    for line in lines:
        if line.page < body_start:
            continue
        if _heading(line.text) not in {'参考文献', 'references', 'bibliography'}:
            continue
        nearby = by_page[line.page] + by_page[line.page + 1]
        if sum(bool(_REF_LABEL.match(item.text)) for item in nearby) >= 2:
            return line.page
    return None


def _body_lines(lines: list[Line], body_start: int, ref_start: int | None,
                toc_pages: set[int]) -> list[Line]:
    return [line for line in lines if line.page >= body_start
            and (ref_start is None or line.page < ref_start) and line.page not in toc_pages]


def _abstract_lines(lines: list[Line], body_start: int) -> list[Line]:
    start = None
    for i, line in enumerate(lines):
        if line.page >= body_start:
            break
        if _heading(line.text) in {'摘要', '中文摘要', 'abstract'} or (line.text.strip() == '摘' and i + 1 < len(lines) and lines[i + 1].page == line.page and lines[i + 1].text.strip() == '要'):
            start = i + (2 if line.text.strip() == '摘' else 1)
            break
    if start is None:
        return []
    extracted = []
    for line in lines[start:]:
        compact = _heading(line.text)
        if line.page >= body_start or re.match(r'^(关键词|关键字|keywords?|abstract|英文摘要)', compact):
            break
        if compact not in {'摘要', '中文摘要', '摘', '要'}:
            extracted.append(line)
    return extracted


def _rule_6(abstract: list[Line], body: list[Line]) -> dict:
    if len(abstract) < 3 or not body:
        return _result(reason='未可靠识别中文摘要或正文')
    normalized_body = ''.join(_compact(line.text) for line in body)
    findings = []
    last_matched_end = -1
    for i in range(len(abstract) - 2):
        window = abstract[i:i + 3]
        if any(_compact(line.text).startswith('摘要') or '学位论文' in line.text for line in window):
            continue
        chunk = ''.join(_compact(line.text) for line in window)
        if len(chunk) < 55 or chunk not in normalized_body:
            continue
        source = next((line for line in body if len(_compact(line.text)) >= 12
                       and _compact(line.text) in chunk), None)
        if source is None:
            continue
        if i > last_matched_end:
            findings.append(_finding(6, abstract[i], '摘要中连续三行与正文文字完全重复',
                                     token=chunk[:30], related_page=source.page))
        last_matched_end = i + 2
    return _result(findings)


def _formula_key(number: str) -> str:
    return re.sub(r'\s+', '', number).translate(str.maketrans({'．': '.', '-': '.', '–': '.', '—': '.', '－': '.', '−': '.'})).casefold()


def _formula_targets(number: str) -> list[str]:
    compact = re.sub(r'\s+', '', number)
    interval = re.fullmatch(r'(\d+)[.．−-](\d+)[-–—－−](\d+)[.．−-](\d+)', compact)
    if interval:
        first_chapter, first, last_chapter, last = map(int, interval.groups())
        if first_chapter == last_chapter and first <= last and last - first <= 50:
            return [f'{first_chapter}.{index}' for index in range(first, last + 1)]
    return [_formula_key(compact)]


def _external_formula_reference(text: str, formula_start: int) -> bool:
    """Ignore a formula number explicitly attributed to another cited work."""
    clause = re.split(r'[。！？；;]', text[:formula_start])[-1]
    attribution = re.search(
        r'(?:参考)?文献\s*\[[0-9,，\s–—－-]+\]\s*'
        r'(?:中|所|的|给出|提出)(?:[^。！？；;]{0,30})$', clause)
    if not attribution:
        return False
    return not re.search(r'(?:本文|本研究|本论文|我们)(?:的|中|提出|使用)?$', attribution.group())


def _rule_18(body: list[Line]) -> dict:
    displayed = set()
    for line in body:
        content = line.text.strip()
        marker = _DISPLAY_FORMULA.match(content)
        if marker and (line.bbox[0] > line.page_width * .55 or len(content) < 20):
            displayed.add(_formula_key(marker.group(1)))
            continue
        trailing = _DISPLAY_FORMULA_TAIL.search(content)
        formula_like = line.bbox[0] > line.page_width * .45 or (
            line.bbox[0] > line.page_width * .25
            and bool(re.search(r'[=+−×∙∑<>≤≥]', content[:trailing.start()] if trailing else '')))
        if trailing and formula_like and line.bbox[2] > line.page_width * .7:
            displayed.add(_formula_key(trailing.group(1)))
    if not displayed:
        if not any(_FORMULA_REFERENCE.search(line.text) for line in body):
            return _result()
        return _result(reason='有公式引用，但未可靠识别独立公式编号')
    displayed_groups = {key[:-1] for key in displayed if key[-1].isalpha()}
    findings = []
    for index, line in enumerate(body):
        context = line.text
        context_offset = 0
        if index:
            previous = body[index - 1]
            if (previous.page == line.page
                    and 0 <= line.bbox[1] - previous.bbox[1] <= 35
                    and abs(line.bbox[0] - previous.bbox[0]) <= 80):
                context = previous.text + ' ' + line.text
                context_offset = len(previous.text) + 1
        for match in _FORMULA_REFERENCE.finditer(line.text):
            if _external_formula_reference(context, context_offset + match.start()):
                continue
            number = re.sub(r'\s+', '', match.group(1)).replace('．', '.')
            targets = _formula_targets(number)
            for target in targets:
                if target in displayed or target in displayed_groups:
                    continue
                token = number if len(targets) == 1 else target
                findings.append(_finding(18, line, f'公式引用 {number} 的目标 {target} 在公式编号中不存在',
                                         token=token, text_range=[match.start(), match.end()]))
    return _result(findings)


def _reference_bounds(lines: list[Line], ref_start: int | None) -> tuple[int, int]:
    """Return only the bibliography, preserving every later section for citations."""
    if ref_start is None:
        return len(lines), len(lines)
    start = next((i for i, line in enumerate(lines)
                  if line.page == ref_start
                  and _heading(line.text) in {'参考文献', 'references', 'bibliography'}),
                 next((i for i, line in enumerate(lines) if line.page >= ref_start), len(lines)))
    end = next((i for i in range(start + 1, len(lines))
                if re.match(r'^(?:致谢|附录|acknowledg(?:e)?ments?|appendix|学术论文和科研成果|学术论文|科研成果|研究成果|research(?:outputs?|achievements?)|攻读.{0,20}(?:期间|发表)|作者简介|个人简历)',
                            _heading(lines[i].text), re.I)), len(lines))
    # Some converted PDFs retain a "参考文献" running header on appendix pages
    # and lose the appendix label, leaving only a numbered subsection such as
    # ".1 核函数". The first new subsection after the final numbered reference
    # marks the end of the bibliography; the entire page returns to citation scope.
    label_indexes = [i for i in range(start + 1, end) if _REF_LABEL.match(lines[i].text)]
    if label_indexes:
        last_label_page = lines[label_indexes[-1]].page
        for i in range(label_indexes[-1] + 1, end):
            line = lines[i]
            if line.page <= last_label_page or line.bbox[1] > line.page_height * .35:
                continue
            heading = _heading(line.text).replace('．', '.')
            if not re.fullmatch(r'(?:\.\d+|[a-z]\.?(?:\d+)(?:\.\d+)*|\d+\.\d+(?:\.\d+)*)', heading, re.I):
                continue
            following = [item for item in lines[i + 1:end] if item.page == line.page][:5]
            if len(following) < 2 or not any(len(item.text.strip()) >= 10 for item in following):
                continue
            if any(_REF_LABEL.match(item.text) for item in following):
                continue
            end = next(j for j in range(start + 1, i + 1) if lines[j].page == line.page)
            break
    return start, end

def _references(lines: list[Line], ref_start: int | None) -> list[tuple[int, Line]]:
    if ref_start is None:
        return []
    entries = []
    start, end = _reference_bounds(lines, ref_start)
    reference_lines = lines[start + 1:end]
    for line in reference_lines:
        match = _REF_LABEL.match(line.text)
        if match:
            number = int(match.group(1))
            tail = line.text[match.end():]
            if 1900 <= number <= 2099 and re.match(r'\s*[.)）]\s*https?://', tail, re.I):
                continue
            entries.append((number, line))
    # PDF extraction can leave only numbered placeholders and punctuation. In
    # that case the bibliography itself is unreadable, so an uncited-reference
    # verdict would be unjustified. Labels may be on separate lines from real
    # entries, so inspect the entire reference section rather than label tails.
    def meaningful(line: Line) -> bool:
        text = _REF_LABEL.sub('', line.text, count=1).strip()
        heading = _heading(text)
        if heading in {'参考文献', 'references', 'bibliography'}:
            return False
        if re.fullmatch(r'[^\W\d_]{2,}大学.*学位论文', heading):
            return False  # running university header
        return bool(re.search(r'[A-Za-z]{2,}|[\u4e00-\u9fff]', text))

    if entries and not any(meaningful(line) for line in reference_lines):
        return []
    return entries

def _is_array_index(text: str, match: re.Match[str]) -> bool:
    if not match.group(1).isdigit():
        return False
    before = text[max(0, match.start() - 32):match.start()]
    after = text[match.end():match.end() + 8]
    if re.search(r'=\s*$', before) or re.match(r'\s*=', after):
        return True
    return bool(re.search(r'=\s*\w+\s*$', before))


def _numeric_bracket_is_data(text: str, match: re.Match[str], numbers: list[int], max_ref: int,
                             marker_ratio: float | None, citation_style: float | None) -> bool:
    """Reject common numeric arrays, years and subscripts before citation lookup."""
    before = text[max(0, match.start() - 45):match.start()]
    after = text[match.end():match.end() + 12]
    # A short metric row with an attached numeric annotation is table data,
    # including single cells and labels such as F1-score or Top-1.
    decimal_marks = list(re.finditer(r'(?<![\w.])[+-]?\d+\.\d+\[\d+\]', text))
    if (any(item.start() <= match.start() < item.end() for item in decimal_marks)
            and not (marker_ratio is not None and marker_ratio < .82
                     and citation_style is not None and citation_style < .82)
            and re.fullmatch(
                r'\s*(?:[A-Za-z\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff%+/_ -]{0,14}\s+)?'
                r'[+-]?\d+\.\d+(?:\[\d+\])?(?:\s+[+-]?\d+\.\d+(?:\[\d+\])?)*\s*',
                text)):
        return True
    if not numbers:
        return True
    # Numeric brackets also occur in regular expressions, code, vector shapes,
    # parameter intervals and binary strings.  These are syntax, not citations.
    if '(?:' in text or r'\d' in text or r'\w' in text:
        return True
    if (len(numbers) == 1 and len(match.group(1)) >= 8
            and set(match.group(1)) <= {'0', '1'}):
        return True
    if (re.search(r'\b(?:char|int|float|double|byte)\s+[A-Za-z_]\w*\s*$', before, re.I)
            and re.match(r'\s*;', after)):
        return True
    if (len(numbers) == 1 and not text[:match.start()].strip()
            and re.match(r'\s*[,，]\s*[^，。]{0,18}=', after)):
        return True
    if (len(numbers) > 1 and re.search(r'[-–—－]', match.group(1))
            and re.search(r'(?:片段|数组|字节|字符|序列|位置|代码|指令)(?:索引|偏移)(?:范围)?\s*$', before)):
        return True
    comma_list = any(char in match.group(1) for char in ',，、;；')
    if len(numbers) > 1 and comma_list:
        if (len(set(numbers)) < len(numbers)
                and re.fullmatch(r'\s*\[\d+(?:\s*[,，]\s*\d+)+\]\s*', text)):
            return True
        if (re.search(r'(?:∈|(?:维数|维度|尺寸|大小|形状)(?:为|是|设为)?|(?:隐藏层|网络层|神经元)?(?:配置为|设置为|设为)|range|size|shape)\s*$', before, re.I)
                or re.search(r'\b(?:ranges?|sizes?|dimensions?|intervals?)\b',
                             text[:match.start()], re.I)
                or re.match(r'\s*(?:range\b|维数|维度|尺寸)', after, re.I)):
            return True
        if (min(numbers) >= 30 and before.endswith(' ')
                and re.fullmatch(r'\s*[A-Z][A-Z0-9 _-]{1,30}\s*', before)):
            return True
    if len(numbers) == 1 and numbers[0] == 0:
        if re.search(r'(?<![A-Za-z0-9_])(?:[a-z_][A-Za-z_0-9]*|[A-Z])$', before):
            return True
        if re.search(r'(?:文献|研究|引用|参见|另见|方法|工作|作者)\s*$', before):
            return False
        chinese_before = len(re.findall(r'[\u4e00-\u9fff]', before))
        prose_prefix = chinese_before or re.search(r'[）】]\s*$', before)
        if prose_prefix and (re.match(r'\s*[，。；：）】\u4e00-\u9fff]', after)
                             or (not after.strip() and chinese_before >= 4)):
            return False
        return True
    if (len(numbers) == 1 and numbers[0] > max_ref
            and re.fullmatch(r'\s*(?:[A-Za-z_][A-Za-z_0-9]*\[\d+\]\s*)+', text)):
        return True
    if len(numbers) == 1 and 1900 <= numbers[0] <= 2099 and max_ref < 1900:
        if re.match(r'\s*年', after) or re.search(r'(?:年|于|发表于|年份|20\d\d)\s*$', before):
            return True
        if not re.search(r'(?:文献|研究|引用|参见|另见)\s*$', before):
            return True
    if comma_list and len(numbers) > 1 and max(numbers) > max(max_ref * 1.4, max_ref + 30):
        if not re.search(r'(?:文献|研究|引用|参见|另见)\s*$', before):
            return True
    return False


def _marker_size_ratio(line: Line, match: re.Match[str]) -> float | None:
    if not line.span_sizes:
        return None
    marker_sizes = []
    body_sizes = []
    for start, end, size in line.span_sizes:
        if start < match.end() and end > match.start():
            marker_sizes.append(size)
            if start < match.start() or end > match.end():
                body_sizes.append(size)
        else:
            body_sizes.append(size)
    if not marker_sizes or not body_sizes:
        return None
    return median(marker_sizes) / median(body_sizes)


def _body_citation_style(body: list[Line], labels: set[int]) -> float | None:
    ratios = []
    for line in body:
        for match in _CITATION.finditer(line.text):
            number = match.group(1)
            if number.isdigit() and int(number) in labels:
                ratio = _marker_size_ratio(line, match)
                if ratio is not None:
                    ratios.append(ratio)
        if len(ratios) >= 80:
            break
    return median(ratios) if len(ratios) >= 5 else None


def _citation_numbers(line: Line, max_ref: int, citation_style: float | None) -> list[tuple[int, str, list[int]]]:
    text = line.text
    found = []
    for match in _CITATION.finditer(text):
        if _is_array_index(text, match):
            continue
        numbers = []
        raw_numbers = match.group(1)
        space_separated = bool(re.fullmatch(r'\d+(?:\s+\d+)+', raw_numbers))
        if space_separated:
            # PDF extraction may omit separators between superscript references.
            # Ordinary brackets such as vector shapes remain data.
            ratio = _marker_size_ratio(line, match)
            if ratio is None or ratio >= .82:
                continue
        parts = re.split(r'\s+' if space_separated else r'[,，、;；]', raw_numbers)
        for part in parts:
            interval = re.fullmatch(r'\s*(\d+)\s*[-–—－]\s*(\d+)\s*', part)
            if interval:
                first, last = map(int, interval.groups())
                if last < first or last - first > 50:
                    numbers = []
                    break
                numbers.extend(range(first, last + 1))
            elif re.fullmatch(r'\s*\d+\s*', part):
                numbers.append(int(part.strip()))
            else:
                numbers = []
                break
        # A bracketed numeric interval such as [0,500] is not a citation.
        if len(numbers) > 1 and 0 in numbers:
            continue
        if numbers == [0]:
            before = text[:match.start()]
            variable = re.search(r'([A-Za-z_][A-Za-z0-9_]*)$', before)
            if variable and re.search(
                    r'(?<![A-Za-z0-9_])' + re.escape(variable.group(1)) + r'\[[1-9]\d*\]',
                    text[match.end():]):
                continue  # repeated indices of the same variable, e.g. V[0], V[1]
            ratio = _marker_size_ratio(line, match)
            math_line = bool(re.search(r'[=∈∉←⊙∑{}]', text))
            if ratio is not None and ratio < .82 and not math_line:
                found.append((0, match.group(0), [match.start(), match.end()]))
                continue
            if ratio is not None and ratio >= .92:
                if citation_style is not None and citation_style < .82:
                    continue
                before = text[:match.start()]
                if (re.search(r'[A-Z][A-Z0-9_]{1,}$', before)
                        and not re.search(r'(?:提出|采用|模型|方法|研究|技术|等人)[^，。；]{0,18}$', before)):
                    continue
        if _numeric_bracket_is_data(text, match, numbers, max_ref,
                                    _marker_size_ratio(line, match), citation_style):
            continue
        found.extend((number, match.group(0), [match.start(), match.end()])
                     for number in numbers)
    return found


def _continued_citations(body: list[Line], max_ref: int,
                         citation_style: float | None):
    """Recover bracketed citations broken by PDF line wrapping."""
    opener = re.compile(r'\[\s*\d[\d\s,\uFF0C\u3001;\uFF1B\-\u2013\u2014\uFF0D]*$')
    for index, first in enumerate(body):
        if not opener.search(first.text):
            continue
        parts = [first]
        for next_line in body[index + 1:index + 4]:
            gap = next_line.bbox[1] - parts[-1].bbox[3]
            if (next_line.page != first.page or not -2 <= gap <= 55
                    or abs(next_line.bbox[0] - parts[-1].bbox[0]) > 80):
                break
            parts.append(next_line)
            joined = ' '.join(part.text for part in parts)
            bbox = (min(part.bbox[0] for part in parts),
                    min(part.bbox[1] for part in parts),
                    max(part.bbox[2] for part in parts),
                    max(part.bbox[3] for part in parts))
            synthetic = Line(first.page, joined, bbox, first.page_width, first.page_height)
            split = len(first.text)
            for number, marker, span in _citation_numbers(synthetic, max_ref, citation_style):
                if span[0] < split < span[1]:
                    yield first, number, marker, span, tuple(parts)
            if ']' in next_line.text:
                break


def _rules_22_24(body: list[Line], entries: list[tuple[int, Line]]) -> tuple[dict, dict]:
    if len(entries) < 2:
        reason = '未可靠识别编号参考文献表'
        return _result(reason=reason), _result(reason=reason)
    labels = {number for number, _ in entries}
    citation_style = _body_citation_style(body, labels)
    citations = set()
    missing_targets = []
    occurrences = ((line, number, marker, span, ())
                   for line in body
                   for number, marker, span in _citation_numbers(line, max(labels), citation_style))
    for line, number, marker, text_range, parts in list(occurrences) + list(_continued_citations(body, max(labels), citation_style)):
        citations.add(number)
        if number not in labels:
            finding = _finding(22, line, f'正文引用 {marker} 无对应参考文献',
                               token=str(number), text_range=text_range)
            if parts:
                rects = [_finding(22, part, '')['location']['bounding_rect'] for part in parts]
                finding['location']['rects'] = rects
                finding['location']['bounding_rect'] = {
                    **rects[0],
                    'x1': min(rect['x1'] for rect in rects),
                    'y1': min(rect['y1'] for rect in rects),
                    'x2': max(rect['x2'] for rect in rects),
                    'y2': max(rect['y2'] for rect in rects),
                }
                finding['bbox'] = [finding['location']['bounding_rect'][key]
                                   for key in ('x1', 'y1', 'x2', 'y2')]
                finding['text_excerpt'] = ' '.join(part.text for part in parts)[:220]
                finding['location']['text_excerpt'] = finding['text_excerpt']
            missing_targets.append(finding)
    uncited = [_finding(24, line, f'参考文献 [{number}] 未在全文引用', token=str(number))
               for number, line in entries if number not in citations]
    return _result(missing_targets), _result(uncited)


def _heading_candidates(body: list[Line]) -> dict[str, dict[int, float]]:
    by_page = defaultdict(list)
    for line in body:
        by_page[line.page].append(line)
    normal_heights = [line.bbox[3] - line.bbox[1] for line in body
                      if line.bbox[1] < line.page_height * .85
                      and 6 <= line.bbox[3] - line.bbox[1] <= 30]
    typical_height = median(normal_heights) if normal_heights else 12
    candidates = {}
    for page, page_lines in by_page.items():
        for i, line in enumerate(page_lines):
            if line.bbox[1] > line.page_height * .9 or re.match(r'^\s*§', line.text):
                continue
            for width in (1, 2, 3):
                seq = page_lines[i:i + width]
                if len(seq) != width or any(seq[j].bbox[1] - seq[j - 1].bbox[1] > 45 for j in range(1, len(seq))):
                    break
                if any(not _compact(item.text) for item in seq):
                    continue  # math glyphs or ornament marks cannot extend a heading
                chapter_like = re.match(r'^\s*(?:第\s*[\d一二三四五六七八九十]+\s*章|\d+\s+)', line.text)
                title_height = max(item.bbox[3] - item.bbox[1] for item in seq)
                if title_height > typical_height * 2.5:
                    continue  # corrupted merged text boxes are not reliable headings
                if chapter_like and line.bbox[1] > line.page_height * .28:
                    if title_height < typical_height * 1.2:
                        continue
                key = _compact(''.join(item.text for item in seq))
                if 2 <= len(key) <= 110:
                    score = title_height / max(typical_height, 1) + (0.25 if chapter_like and line.bbox[1] < line.page_height * .28 else 0)
                    scores = candidates.setdefault(key, {})
                    scores[page] = max(scores.get(page, 0), score)
    return candidates


def _printed_page_numbers(body: list[Line]) -> dict[int, int]:
    """Read a standalone page number from the centered bottom margin."""
    candidates = defaultdict(set)
    for line in body:
        text = line.text.strip()
        if (re.fullmatch(r'\d{1,4}', text)
                and line.bbox[1] >= line.page_height * .85
                and line.page_width * .35 <= line.bbox[0] <= line.page_width * .65):
            candidates[line.page].add(int(text))
    return {page: next(iter(numbers)) for page, numbers in candidates.items()
            if len(numbers) == 1}


def _rule_28(lines: list[Line], toc_pages: set[int], body: list[Line]) -> dict:
    entries = []
    for line in _visual_rows([item for item in lines if item.page in toc_pages]):
        match = _TOC_ENTRY.match(line.text)
        if match and _TOC_HEADING.match(match.group(1).strip()):
            heading = _compact(match.group(1))
            if len(heading) >= 2:
                entries.append((heading, int(match.group(2)), line))
    if len(entries) < 5:
        return _result(reason='未可靠识别至少五条目录页码')
    headings = _heading_candidates(body)
    matches = []
    for heading, shown, line in entries:
        pages = dict(headings.get(heading, {}))
        if not pages:
            for key, choices in headings.items():
                if len(heading) >= 4 and key.startswith(heading) and len(key) - len(heading) <= 12:
                    for page, score in choices.items():
                        pages[page] = max(pages.get(page, 0), score)
        if pages:
            best_score = max(pages.values())
            # A true chapter heading is normally its first strong occurrence;
            # subsequent running headers repeat the same words on later pages.
            best_page = min(page for page, score in pages.items()
                            if score >= best_score * .8)
            matches.append((shown, best_page, line))
    if len(matches) < 5:
        return _result(reason='目录与正文匹配的标题不足五条')
    printed = _printed_page_numbers(body)
    printed_matches = sum(physical in printed for _, physical, _ in matches)
    offsets = Counter(physical - shown for shown, physical, _ in matches)
    offset, support = offsets.most_common(1)[0]
    offset_reliable = support >= max(3, int(len(matches) * .6))
    if printed_matches < 5 and not offset_reliable:
        return _result(reason='未可靠识别正文印刷页码或目录物理页偏移')
    findings = []
    for shown, physical, line in matches:
        if physical in printed:
            actual = printed[physical]
        elif offset_reliable:
            actual = physical - offset
        else:
            continue
        if shown != actual:
            findings.append(_finding(28, line, f'目录页码 {shown} 与正文实际页码 {actual} 不一致',
                                     token=str(shown), actual_page=actual, body_pdf_page=physical))
    return _result(findings)


def detect_lines(lines: list[Line], selected_rules=RULES, page_count: int | None = None) -> dict:
    selected = tuple(dict.fromkeys(int(rule) for rule in selected_rules))
    invalid = set(selected) - set(RULES)
    if invalid:
        raise ValueError(f'未知规则: {sorted(invalid)}')
    page_count = page_count or max((line.page for line in lines), default=0)
    ordered = sorted(lines, key=lambda line: line.page)  # retain PDF reading order within a page
    toc_pages = _toc_pages(ordered, page_count)
    body_start = _body_start(ordered, toc_pages)
    ref_start = _reference_start(ordered, body_start, page_count)
    body = _body_lines(ordered, body_start, ref_start, toc_pages)
    results = {}
    if 6 in selected:
        results['6'] = _rule_6(_abstract_lines(ordered, body_start), body)
    if 18 in selected:
        results['18'] = _rule_18(body)
    if 22 in selected or 24 in selected:
        ref_first, ref_last = _reference_bounds(ordered, ref_start)
        citation_scope = []
        in_academic_outputs = False
        for index, line in enumerate(ordered):
            if index >= ref_last and re.match(
                    r'^(?:学术论文和科研成果|学术论文|科研成果|研究成果|research(?:outputs?|achievements?)|攻读.{0,20}(?:期间|发表)|作者简介|个人简历)',
                    _heading(line.text)):
                in_academic_outputs = True
            if ref_first <= index < ref_last or line.page in toc_pages:
                continue
            if in_academic_outputs and _REF_LABEL.match(line.text):
                continue  # numbered patents/publications are not literature citations
            citation_scope.append(line)
        r22, r24 = _rules_22_24(citation_scope, _references(ordered, ref_start))
        if 22 in selected:
            results['22'] = r22
        if 24 in selected:
            results['24'] = r24
    if 28 in selected:
        toc_body = [line for line in ordered if line.page > max(toc_pages, default=0)
                    and line.page not in toc_pages]
        results['28'] = _rule_28(ordered, toc_pages, toc_body)
    return results


def detect_pdf(pdf_path: Path, selected_rules=RULES) -> dict:
    lines, pages = extract_lines(Path(pdf_path))
    return {'pdf': str(pdf_path), 'pages': pages,
            'rules': detect_lines(lines, selected_rules, pages)}


def main() -> None:
    parser = argparse.ArgumentParser(description='本地 PDF 五规则检测器')
    parser.add_argument('--pdf', type=Path, required=True)
    parser.add_argument('--rule', action='append', type=int, choices=RULES)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = detect_pdf(args.pdf, args.rule or RULES)
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding='utf-8')
    else:
        print(serialized)


if __name__ == '__main__':
    main()
