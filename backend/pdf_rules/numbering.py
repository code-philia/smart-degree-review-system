import re
import unicodedata
from functools import lru_cache


# Academic Arabic numerals are ASCII after NFKC normalization. Arbitrary
# Unicode decimal characters can be accent glyphs from embedded math fonts.
NUMBER_SEPARATOR = r"[^\S\r\n]*[.\-][^\S\r\n]*"
LABEL = rf"(?P<number>(?:[A-Z](?:{NUMBER_SEPARATOR})?)?[0-9]+(?:{NUMBER_SEPARATOR}[0-9]+)*)(?![A-Za-z0-9]|{NUMBER_SEPARATOR}\d)"
FIGURE_CAPTION = re.compile(rf"^\s*(?:图|Figure|Fig\.?)\s*{LABEL}(?:\s+|[、:：.]|(?=[\u4e00-\u9fff“‘「])|(?=\(\s*(?:续|continued)\s*\)))\s*\S", re.I)
TABLE_CAPTION = re.compile(rf"^\s*(?:表|Tab(?:le)?\.?)\s*{LABEL}(?:\s+|[、:：.]|(?=[\u4e00-\u9fff“‘「])|(?=\(\s*(?:续|continued)\s*\)))\s*\S", re.I)
# A numeric subpanel suffix refers to its parent figure. A bare letter-prefix
# label plus another letter (e.g. the variable F2D) is not a partial figure ID.
# Allow a glued English conjunction only when another complete citation
# label follows. Arbitrary identifier suffixes remain outside the grammar.
CITATION_AND = (r"and(?=\s*(?:图|表格?|Figures?|Figs?\.?|Tables?\.?)?\s*[(（]?\s*"
                rf"(?:[A-Z](?:{NUMBER_SEPARATOR})?)?[0-9]+(?:{NUMBER_SEPARATOR}[0-9]+)*(?:(?![A-Za-z0-9]|{NUMBER_SEPARATOR}\d)|and(?=\s*[0-9])))")
FIGURE_REFERENCE_LABEL = (rf"(?P<number>(?:(?P<bare_scope>[A-Z])|[A-Z]{NUMBER_SEPARATOR})?[0-9]+(?:{NUMBER_SEPARATOR}[0-9]+)*)"
                          rf"(?(bare_scope)(?![A-Za-z0-9]|{NUMBER_SEPARATOR}\d)|"
                          rf"(?:[a-z](?![A-Za-z0-9])|(?![A-Za-z0-9]|{NUMBER_SEPARATOR}\d)|(?={CITATION_AND})))")
FIGURE_REFERENCE = re.compile(rf"(?:图(?:\s*(?:所示|如))?|(?<![A-Za-z])Figures?|(?<![A-Za-z])Figs?\.?)\s*[(（]?\s*{FIGURE_REFERENCE_LABEL}", re.I)
TABLE_REFERENCE = re.compile(rf"(?:表(?:格)?|(?<![A-Za-z])Tables?\.?)\s*[(（]?\s*{FIGURE_REFERENCE_LABEL}", re.I)
APPENDIX_HEADING = re.compile(r"^\s*附录\s*(?P<number>[A-Z])(?:\s|[:：]|$)", re.I)
APPENDIX_REFERENCE = re.compile(r"附录\s*(?P<number>[A-Z])", re.I)
APPENDIX_QUALIFIER = re.compile(r"附录\s*(?P<number>[A-Z])\s*(?:中|内|里)?(?:的)?\s*$", re.I)
APPENDIX_NARRATIVE = re.compile(
    r"^(?:介绍|展示|讨论|描述|给出|包含|列出|参见|详见|可见|说明了|"
    r"使用了|分析了|在|中(?:的|有|给)|里(?:的|有)|所(?:示|述)|是|有|将|为|"
    r"见(?:图|表))"
)
DOT_LEADER = re.compile(r"(?:[.·…]\s*){2,}[\s\u200b\u2060\ufeff]*\d+\s*$")


_DASH_TRANSLATION = str.maketrans({
    "‐": "-", "－": "-", "–": "-", "—": "-", "−": "-", "‑": "-",
})


@lru_cache(maxsize=32768)
def normalize_text(text: str) -> str:
    # NFKC folds footnote markers (e.g. ① and ²) into ASCII digits.
    # Preserve them so they cannot become part of an adjacent target number.
    pieces = re.split(r"([①-⑳⁰¹²³⁴⁵⁶⁷⁸⁹]+)", text)
    return "".join(piece if i % 2 else unicodedata.normalize("NFKC", piece)
                   for i, piece in enumerate(pieces)).translate(_DASH_TRANSLATION)


def normalize_label(value: str) -> str:
    # Compact only separator whitespace in a parsed identity. Native prose
    # and its character offsets stay untouched; independent digits stay apart.
    return re.sub(r"[^\S\r\n]*([.\-])[^\S\r\n]*", r"\1", normalize_text(value)).upper().replace("-", ".")


def is_toc_line(text: str) -> bool:
    normalized = normalize_text(text).strip()
    return bool(DOT_LEADER.search(normalized)) or normalized.startswith(("图目录", "表目录", "插图目录"))


def _split_directory_entries(page, lines):
    """Recover repeated typed entries whose leaders/page numbers are separate runs."""
    rows = []
    for line in lines:
        if not page.height*.10 < line.bbox[1] < page.height*.94:
            continue
        if not rows or abs(line.bbox[1]-rows[-1][0].bbox[1]) > 3:
            rows.append([line])
        else:
            rows[-1].append(line)
    rows = [sorted(row,key=lambda line:line.bbox[0]) for row in rows]
    text = lambda row: ' '.join(normalize_text(line.text).strip() for line in row)
    typed = lambda row: bool(caption_match(text(row),'figure') or caption_match(text(row),'table'))
    entries = []
    for i,row in enumerate(rows):
        if not typed(row):
            continue
        entry = list(row)
        for j in range(i,min(i+4,len(rows))):
            current = rows[j]
            if j > i:
                previous = rows[j-1]
                height = max(line.bbox[3]-line.bbox[1] for line in previous)
                if (typed(current) or current[0].bbox[1]-max(l.bbox[3] for l in previous) > max(12,height*1.4)
                        or current[0].bbox[0] < row[0].bbox[0]-page.width*.08):
                    break
                entry.extend(current)
            last = current[-1]
            if (last.bbox[0] >= page.width*.75
                    and re.fullmatch(r'[.·…\s]*\d+',normalize_text(last.text).strip())
                    and DOT_LEADER.search(text(current))):
                entries.append(entry)
                break
    # One caption beside numeric ink is insufficient evidence for a directory.
    return {(page.number,line.bbox) for entry in entries for line in entry} if len(entries)>=2 else set()


def _split_contents_rows(page, lines):
    """Prove complete TOC rows from native titles and aligned page-number ink.

    A bibliography/appendix title can be extracted separately from its page
    number. Require a contents heading or multiple actual leader rows; a
    numerical cell in a table and a lone page-like number supply no proof.
    Only the proved rows are excluded, never the surrounding page's prose.
    """
    rows = []
    for line in lines:
        if (line.source != 'native' or abs(line.direction[1]) > .1
                or not page.height*.08 < line.bbox[1] < page.height*.92):
            continue
        height = max(1, line.bbox[3]-line.bbox[1])
        row = next((r for r in reversed(rows)
                    if abs(r[0].bbox[1]-line.bbox[1]) <= min(height, r[0].bbox[3]-r[0].bbox[1])*.25), None)
        if row is None:
            rows.append([line])
        else:
            row.append(line)
    rows = [sorted(row, key=lambda l: l.bbox[0]) for row in rows]
    text = lambda row: ' '.join(normalize_text(l.text).strip() for l in row)
    title_groups = []
    for row in rows:
        if row[0].bbox[1] >= page.height*.22:
            continue
        group = []
        for line in row:
            if group and line.bbox[0]-group[-1].bbox[2] > max(
                    line.bbox[3]-line.bbox[1], group[-1].bbox[3]-group[-1].bbox[1])*2.5:
                title_groups.append(group)
                group = []
            group.append(line)
        if group:
            title_groups.append(group)
    heading = any(re.fullmatch(r'(?:目录|contents|tableofcontents)',
                              re.sub(r'\s+', '', text(group)), re.I) for group in title_groups)
    candidates = []
    for row in rows:
        value = text(row)
        if (row[0].bbox[0] >= page.width*.65 or row[-1].bbox[2] < page.width*.75
                or len(re.findall(r'[A-Za-z\u4e00-\u9fff]', value)) < 2
                or any(t[0]-.5 <= l.bbox[0] and t[1]-.5 <= l.bbox[1]
                       and l.bbox[2] <= t[2]+.5 and l.bbox[3] <= t[3]+.5
                       for l in row for t in (*page.tables, *page.images))):
            continue
        leader = bool(DOT_LEADER.search(value))
        detached = (row[-1].bbox[0] >= page.width*.75
                    and re.fullmatch(r'[0-9]{1,4}', normalize_text(row[-1].text).strip()))
        if leader or detached:
            candidates.append((row, leader))
    aligned = [entry for entry in candidates if sum(
        abs(entry[0][-1].bbox[2]-peer[0][-1].bbox[2]) <= page.width*.025
        for peer in candidates) >= 3]
    if len(aligned) < 3 or (not heading and sum(leader for _, leader in aligned) < 3):
        return set()
    return {(page.number, l.bbox) for row, _ in aligned for l in row}



def toc_line_keys(document):
    """Identify full directory entries even when leaders end on a later row.

    Join only adjacent, aligned continuation lines and stop at a new numbered
    caption. The original PDF lines and their rectangles remain unchanged.
    """
    keys = set()
    for page in document.pages:
        lines = sorted(page.lines, key=lambda line: (line.bbox[1], line.bbox[0]))
        keys.update(_split_directory_entries(page,lines))
        keys.update(_split_contents_rows(page,lines))
        heading_rows = {}
        for line in lines:
            if line.bbox[1] < page.height*.22:
                heading_rows.setdefault(round(line.bbox[1]/8), []).append(line)
        directory_rows = [row for row in heading_rows.values() if re.fullmatch(r"(?:插图|图目录|表目录|插图目录|附表|ListofFigures|ListofTables)",
                       "".join(normalize_text(l.text).replace(" ", "") for l in sorted(row,key=lambda l:l.bbox[0])), re.I)]
        if directory_rows and sum(bool(DOT_LEADER.search(normalize_text(l.text))) for l in lines) >= 2:
            start = min(l.bbox[1] for row in directory_rows for l in row)
            # Only the directory region, never preceding or subsequent chapter prose.
            for item in lines:
                if item.bbox[1] < start:
                    continue
                if re.match(r"(?:第\s*[一二三四五六七八九十0-9]+\s*章|chapter\s+[0-9IVX]+)", normalize_text(item.text), re.I):
                    break
                keys.add((page.number,item.bbox))
        for index, line in enumerate(lines):
            key = (page.number, line.bbox)
            if is_toc_line(line.text):
                keys.add(key)
                continue
            if not (caption_match(line.text, "figure") or caption_match(line.text, "table")):
                continue
            entry = [line]
            for other in lines[index + 1:]:
                previous = entry[-1]
                height = max(1, previous.bbox[3] - previous.bbox[1])
                if (other.bbox[1] - previous.bbox[3] > max(12, height * 1.4)
                        or other.bbox[0] < line.bbox[0] - 8
                        or other.bbox[0] > line.bbox[2] + 20
                        or FIGURE_CAPTION.search(normalize_text(other.text))
                        or TABLE_CAPTION.search(normalize_text(other.text))):
                    break
                entry.append(other)
                if DOT_LEADER.search(normalize_text(" ".join(item.text for item in entry))):
                    keys.update((page.number, item.bbox) for item in entry)
                    break
    return keys


def is_appendix_heading(text: str, match: re.Match) -> bool:
    """Treat only a short standalone title as a heading, not a body sentence."""
    tail = text[match.end():].strip()
    return (len(text.strip()) <= 80 and
            not re.search(r"[。；;，,]", tail) and
            not APPENDIX_NARRATIVE.match(tail))


# Finite narrative predicates identify a prose reference, including coordinated
# subjects. Noun title phrases (e.g. "系统配置参数") remain captions.
CAPTION_NARRATIVE = re.compile(
    r"^(?:(?:和|与|及|、|and\b|&|,)\s*(?:图|表|Figures?|Figs?\.?|Tables?)?\s*(?:[A-Z][.\-]?)?[0-9]+(?:[.\-][0-9]+)*\s*)*"
    r"(?:(?:分别|系统性地|(?:清晰|直观|详细)(?:地)?|进一步|主要|也|则)\s*)*"
    r"(?:提供了|汇报了|汇总了|呈现了|介绍了|可视化了|展示|显示|说明|描述|给出|列出|列举|引用自|引自|来自|概括(?:为|了)|表示了|总结了|区分了|研究了|评估了|"
    r"绘制了|定义了|刻画了|描绘了|对比(?:了|展示)|比较了|详细介绍|可以看出|可见|为|是|"
    r"对[^。；;]{1,48}进行了|对上述|对以上|可视化地|中(?:的|所)|(?:中|内|里)(?=\s*[,，:：])|(?:中|内)(?=\s*[。.!?！？]\s*$)|所示|"
    r"(?:通过|以).{0,18}(?:展示|研究|比较|给出|说明)|"
    r"的(?:实验)?(?:数据|结果).{0,10}(?:反映|展示|说明)|"
    r"shows?\b|illustrates?\b|depicts?\b|presents?\b)", re.I)


def caption_match(text, kind):
    normalized = normalize_text(text)
    pattern = FIGURE_CAPTION if kind == "figure" else TABLE_CAPTION
    match = pattern.search(normalized)
    if match:
        # A leading enumeration comma can belong to a coordinated subject,
        # not just the punctuation separating a label from its title.
        tail=normalized[match.end("number"):].lstrip(" .:：")
        # A wrapped citation can consist solely of coordinated object IDs.
        # It supplies no nominal title and must remain body-reference ink.
        # Preserve real titles that continue after the coordinated subject.
        reference_only = re.fullmatch(
            r"(?:\s*(?:and\b|&|[,，、]|和|与|及)\s*"
            r"(?:图|表|Figures?|Figs?\.?|Tables?)?\s*"
            r"(?:[A-Z][.\-]?)?[0-9]+(?:[.\-][0-9]+)*)+\s*[。.]?", tail, re.I)
        if not (reference_only or CAPTION_NARRATIVE.match(tail) or CAPTION_NARRATIVE.match(tail.lstrip("、"))):
            return match
    return None
