"""Bind independent experimental prose to the cells of one physical table.

No I/O, index mutation, fabricated number references or source-wide exemptions.
Unsupported paraphrases fail closed. Evidence is returned separately so every
new usage credit can be inspected against its retained source rectangles.
"""
import re
from decimal import Decimal, InvalidOperation

from .model import DocumentIndex, Label
from .numbering import caption_match, normalize_label, TABLE_REFERENCE, toc_line_keys, is_toc_line
from .usage_text_cache import normalize_text
from .source_cited_usage import _full_title, _prose, _primary_subjects
from .usage_paragraphs import span_anchor

_NUMBER = re.compile(r'(?<![A-Za-z\d.])([+-]?\d+(?:\.\d+)?)(%?)(?![A-Za-z\d]|\.\d)')
_WORDS = re.compile(r'[A-Za-z][A-Za-z0-9_-]*')
_GENERIC = {'table','a','an','the','and','or','of','on','in','for','to','with','without','by',
            'method','methods','model','models','proposed','ours','our','results','result','performance',
            'comparison','comparisons','accuracy','accuracies','evaluation','evaluations','experiment','harder',
            'experiments','experimental','task','tasks','average','avg','full','framework','prompt',
            'source','generation','detection','feature','analysis','first','second','stage','based',
            'dataset','datasets','simulator','simulators','zero-shot'}
_TOPICS = (
    (r'accuracy|准确率|精度', r'accuracy|准确率|精度'),
    (r'latency|时延|延迟', r'latency|时延|延迟'),
    (r'memory|内存|存储', r'memory|内存|存储'),
    (r'ablation|消融', r'ablation|消融'),
    (r'training\s+loss|训练损失', r'training\s+loss|训练损失'),
)


def _key(line):
    return line.page_number, line.bbox


def _norm(text):
    return re.sub(r'[\s._–—-]+', '', normalize_text(text)).casefold()


def _explicit_table_numbers(text):
    """Retain the local table pointers that own this independent body claim.

    Content evidence cannot silently fix a printed pointer to another table.
    The shared citation grammar preserves lists/ranges; external literature
    and figure pointers do not assert a local table's identity.
    """
    from .reference_groups import reference_matches
    from .reference_context import local_reference
    from .reference_identity_repair import _external
    text=re.sub(r'(?<=\d)\s*([.\-])\s*(?=\d)',r'\1',normalize_text(text))
    return {normalize_label(match.group('number')) for match in reference_matches(TABLE_REFERENCE,text)
            if local_reference(text,match) and not _external(text,'table',normalize_label(match.group('number')))}


def _table_pointer_agrees(descriptor,numbers):
    return not numbers or normalize_label(descriptor['target'].number) in numbers


def _inside(line, box):
    return (box[0] <= line.bbox[0]+1 and box[1] <= line.bbox[1]+1
            and line.bbox[2] <= box[2]+1 and line.bbox[3] <= box[3]+1)


def _table_title(group,page):
    """Add an unindexed adjacent translation, never an independent object."""
    title,rows=_full_title(group,page,'table')
    # A parsed multiline caption already owns its exact native ink. Recover
    # only those source lines, rather than treating its notes as intervening
    # body or extending the title to unrelated nearby prose.
    owned={_key(l):l for l in rows}
    for label in group:
        anchor=label.line
        if anchor.source!='native' or '\n' not in anchor.text:continue
        match=caption_match(anchor.text,'table')
        if not match or normalize_label(match['number'])!=normalize_label(label.number):continue
        for line in page.lines:
            if (line.source==anchor.source and line.block_id==anchor.block_id
                    and _inside(line,anchor.bbox) and _norm(line.text) in _norm(anchor.text)
                    and line.font_size and anchor.font_size
                    and abs(line.font_size-anchor.font_size)<=anchor.font_size*.1):
                owned[_key(line)]=line
    rows=sorted(owned.values(),key=lambda l:(l.bbox[1],l.bbox[0]))
    title=' '.join(l.text for l in rows)
    if not rows:
        return title,rows
    first=group[0].line
    chinese=normalize_text(first.text).lstrip().startswith('表')
    bottom=max(l.bbox[3] for l in rows)
    def number(value):
        return re.sub(r'[‐‑–—-]','.',normalize_text(value)).replace(' ','')
    def translated_number(value):
        candidate=number(value);target=number(group[0].number)
        if candidate==target:return True
        parts=candidate.split('.')
        # Some translated titles print both the chapter and the complete
        # local number. Only an immediately adjacent opposite-language title
        # with one exact repeated leading component has this form.
        return len(parts)>=3 and parts[0]==parts[1] and '.'.join(parts[1:])==target
    for line in sorted(page.lines,key=lambda l:(l.bbox[1],l.bbox[0])):
        if line in rows or line.bbox[1]<bottom-1:
            continue
        if line.bbox[1]-bottom>22:
            break
        match=caption_match(line.text,'table')
        if not match:
            # Any native ink between the titles is an object/body boundary.
            if line.text.strip():
                break
            continue
        if (not translated_number(match['number'])
                or normalize_text(line.text).lstrip().startswith('表')==chinese
                or line.source!=first.source
                or (not line.bold and first.bold)
                or (not line.bold and re.match(r'^\s*Table\s*\d+(?:[.‐‑–—-]\d+)*\s+(?:is|are|shows?|gives?|stores?|lists?|presents?|reports?|contains?|provides?|compares?|summari[sz]es?)\b',
                             normalize_text(line.text),re.I))
                or not first.font_size or not line.font_size
                or abs(first.font_size-line.font_size)>first.font_size*.1
                or abs((line.bbox[0]+line.bbox[2]-first.bbox[0]-first.bbox[2])/2)>max(10,first.font_size*2)
                or any(b[1]>=bottom and b[3]<=line.bbox[1] for b in (*page.images,*page.tables))):
            break
        _,extra=_full_title([Label(group[0].number,line,group[0].scope)],page,'table')
        rows=sorted({_key(l):l for l in (*rows,*extra)}.values(),key=lambda l:(l.bbox[1],l.bbox[0]))
        title=' '.join(l.text for l in rows)
        break
    return title,rows


def _cells(group, page, rows, caption_keys):
    """A caption's following compact table rows stop at real body typography.

    This also covers boxed single-column prompts and table rows omitted by a
    grid detector. It never consumes neighbouring body-font prose as cells.
    """
    from .caption_context import body_font
    typical = body_font(page)
    if not rows:
        return []
    top=min(r.bbox[1] for r in rows)
    own_caption_keys={_key(l) for l in rows}
    above=[b for b in page.tables if 0<=top-b[3]<=30 and b[3]-b[1]<page.height*.7
           and not any(_key(l) in caption_keys and b[3]+1<l.bbox[1]<top-1 for l in page.lines)
           and not any(_key(l) in caption_keys and caption_match(l.text,'table')
                       and _key(l) not in own_caption_keys
                       and 0<=b[1]-l.bbox[3]<=30
                       and min(b[2],l.bbox[2])>max(b[0],l.bbox[0]) for l in page.lines)]
    if len(above)==1:
        ink=[l for l in page.lines if _inside(l,above[0]) and _key(l) not in caption_keys and l.text.strip()]
        grid=_cell_rows(ink)
        # A real native grid with repeated sibling columns proves ownership.
        # A rectangle around an ordinary paragraph cannot supply table cells.
        if (len(grid)>=3 and len(grid[0])>=2 and sum(len(r)>=2 for r in grid[1:])>=2
                and all(l.source=='native' and l.font_size for l in ink)):
            return sorted(ink,key=lambda l:(l.bbox[1],l.bbox[0]))
    bottom = max(r.bbox[3] for r in rows)
    following = [l.bbox[1] for l in page.lines if _key(l) in caption_keys
                 and l.bbox[1] >= bottom-1 and l not in rows]
    stop = min(following) if following else page.height*.90
    candidates = sorted((l for l in page.lines if l.bbox[1] >= bottom-1
                         and l.bbox[3] <= stop+1
                         and _key(l) not in caption_keys and l.text.strip()),
                        key=lambda l:(l.bbox[1],l.bbox[0]))
    # Some native exporters join spaced column headings into one line.
    # Exact source character boxes, not estimated string widths, recover
    # those physical headings. Ordinary word spaces never qualify.
    from dataclasses import replace
    expanded=[]
    for line in candidates:
        if line.role=='usage_table_native_source_row':
            continue
        tokens=list(re.finditer(r'\S+',line.text));children=[]
        if (line.source=='native' and line.text_regions and len(tokens)>=3 and line.font_size
                and all(re.fullmatch(r'[A-Za-z][A-Za-z-]{1,14}|[+-]?\d+(?:\.\d+)?%?',m[0]) for m in tokens)):
            for token in tokens:
                ink=[box for a,b,box in line.text_regions if a<token.end() and b>token.start()]
                covered={j for a,b,_ in line.text_regions for j in range(max(a,token.start()),min(b,token.end()))}
                if not ink or covered!=set(range(token.start(),token.end())):children=[];break
                box=(min(b[0] for b in ink),min(b[1] for b in ink),max(b[2] for b in ink),max(b[3] for b in ink))
                children.append(replace(line,text=token[0],bbox=box,text_regions=(),reference_regions=(),role='usage_table_native_cell'))
            if (children and not all(b.bbox[0]-a.bbox[2]>=line.font_size*.4 for a,b in zip(children,children[1:]))):children=[]
        if children:
            expanded.append(replace(line,role='usage_table_native_source_row'))
            expanded.extend(children)
        else:expanded.append(line)
    candidates=sorted(expanded,key=lambda l:(l.bbox[1],l.bbox[0]))
    cells=[]
    last=bottom
    compact_header=next((row for row in _cell_rows(candidates)
                         if len(row)>=2 and all(l.font_size and
                            (l.font_size<typical*.95 if typical else l.bold) for l in row)),[])
    if not compact_header:
        native_rows=_cell_rows(candidates)
        header=next((row for row in native_rows if len(row)>=3 and
                     all(l.font_size and (not typical or l.font_size<=typical*1.05) and
                         l.bbox[2]-l.bbox[0]<page.width*.4 for l in row)),[])
        if header:
            bottom_header=max(l.bbox[3] for l in header)
            measured=[row for row in native_rows if min(l.bbox[1] for l in row)>bottom_header
                      and len(row)>=3 and sum(bool(_NUMBER.fullmatch(normalize_text(l.text).strip())) for l in row)>=2
                      and (typical or (not _NUMBER.fullmatch(normalize_text(sorted(row,key=lambda l:l.bbox[0])[0].text).strip())
                           and all(l.font_size and l.font_size<=max(h.font_size for h in header)*1.05 for l in row)))]
            # Real sibling values on repeated source rows prove tabular ink.
            # A body-font paragraph, or a lone pair of layout labels, cannot.
            if len(measured)>=2:compact_header=header
    if not compact_header:
        # A descriptive interface grid may occupy a page with no body-font
        # estimate. Repeated native function/typed-input/purpose siblings prove
        # both its cells and its status as a physical competitor.
        native_rows=_cell_rows(candidates)
        header=next((sorted(row,key=lambda l:l.bbox[0]) for row in native_rows if len(row)>=3
            and re.search(r'接口|\b(?:interface|function|method)\b',sorted(row,key=lambda l:l.bbox[0])[0].text,re.I)
            and re.search(r'输入|参数|方法|inputs?|parameters?|methods?',sorted(row,key=lambda l:l.bbox[0])[1].text,re.I)
            and re.search(r'说明|描述|用途|description|purpose',sorted(row,key=lambda l:l.bbox[0])[2].text,re.I)),None)
        if header:
            bottom_header=max(l.bbox[3] for l in header)
            ceiling=(typical or max((l.font_size or 0) for l in header))*1.05
            interface_rows=[]
            for row in native_rows:
                row=sorted(row,key=lambda l:l.bbox[0])
                if (min(l.bbox[1] for l in row)<=bottom_header or len(row)<3
                        or not all(l.font_size and l.font_size<=ceiling
                                   and l.bbox[2]-l.bbox[0]<page.width*.4 for l in row)):continue
                function=(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*\s*\([^)]*\)',normalize_text(row[0].text).strip())
                          and re.search(r'[A-Za-z_][A-Za-z0-9_]*\s*[:：]',row[1].text))
                endpoint=(re.fullmatch(r'/(?:[A-Za-z_][A-Za-z0-9_]*/)*[A-Za-z_][A-Za-z0-9_]*',normalize_text(row[0].text).strip())
                          and re.fullmatch(r'GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS',row[1].text.strip()))
                if ((function or endpoint)
                        and len(normalize_text(row[-1].text).strip())>=4):interface_rows.append(row)
            if len(interface_rows)>=2:compact_header=header
    if not compact_header:
        # Date strings are typed cells rather than scalar numbers. A page
        # containing only its native partition still remains a competitor.
        native_rows=_cell_rows(candidates)
        header=next((sorted(row,key=lambda l:l.bbox[0]) for row in native_rows if len(row)==3
            and re.search(r'数据集|dataset',sorted(row,key=lambda l:l.bbox[0])[0].text,re.I)
            and re.search(r'起始|开始|start',sorted(row,key=lambda l:l.bbox[0])[1].text,re.I)
            and re.search(r'结束|终止|end',sorted(row,key=lambda l:l.bbox[0])[2].text,re.I)),None)
        if header and all(h.font_size for h in header):
            ceiling=(typical or max(h.font_size for h in header))*1.05
            date_rows=[sorted(row,key=lambda l:l.bbox[0]) for row in native_rows if len(row)==3
                and min(l.bbox[1] for l in row)>max(h.bbox[3] for h in header)
                and all(l.font_size and l.font_size<=ceiling and l.bbox[2]-l.bbox[0]<page.width*.4 for l in row)
                and all(re.fullmatch(r'\d{4}-\d{2}-\d{2}',normalize_text(l.text).strip())
                        for l in sorted(row,key=lambda l:l.bbox[0])[1:])]
            if len(date_rows)>=2:compact_header=header
    centers=[(l.bbox[0]+l.bbox[2])/2 for l in compact_header]
    starts=[l.bbox[0] for l in compact_header]
    def column_band(line):
        if len(centers)<2 or line.bbox[2]-line.bbox[0]>page.width*.4:return False
        height=max(1,line.bbox[3]-line.bbox[1]);cy=(line.bbox[1]+line.bbox[3])/2
        owners=set()
        for candidate in candidates:
            if candidate.bbox[2]-candidate.bbox[0]>page.width*.4:continue
            if abs((candidate.bbox[1]+candidate.bbox[3])/2-cy)>max(2,height*.6):continue
            x=(candidate.bbox[0]+candidate.bbox[2])/2
            ordinal=min(range(len(centers)),key=lambda i:abs(centers[i]-x))
            if abs(centers[ordinal]-x)<=max(12,height*2):owners.add(ordinal)
            elif not typical:
                # A page occupied by a table has no body-font estimate.
                # Its long cells can be left aligned under short headers;
                # real same-row sibling columns still prove ownership.
                ordinal=min(range(len(starts)),key=lambda i:abs(starts[i]-candidate.bbox[0]))
                if abs(starts[ordinal]-candidate.bbox[0])<=max(12,height*2):owners.add(ordinal)
        return len(owners)>=2
    def column_wrap(line):
        if typical or line.bbox[2]-line.bbox[0]>page.width*.4:return False
        height=max(1,line.bbox[3]-line.bbox[1])
        previous=[l for l in cells if l.source==line.source and l.font_size==line.font_size
                  and abs(l.bbox[0]-line.bbox[0])<=max(2,height*.2)
                  and -1<=line.bbox[1]-l.bbox[3]<=height*1.3]
        if not previous:return False
        last=max(previous,key=lambda l:l.bbox[3])
        return not re.search(r'[。.!?；;:]\s*$',last.text)
    for line in candidates:
        if line.role=='usage_table_native_source_row':
            continue
        if caption_match(normalize_text(line.text),'table') or caption_match(normalize_text(line.text),'figure'):
            break
        if line.bbox[1] > page.height*.90:
            break
        if (not line.font_size or not typical and not (column_band(line) or column_wrap(line)) or
                (typical and line.font_size >= typical*.95 and not column_band(line))):
            break
        height=max(1,line.bbox[3]-line.bbox[1])
        if line.bbox[1]-last > max(30,height*3):
            break
        cells.append(line)
        last=max(last,line.bbox[3])
    for parent in candidates:
        if parent.role!='usage_table_native_source_row':continue
        children=[l for l in candidates if l.role=='usage_table_native_cell' and _inside(l,parent.bbox)]
        if children and all(l in cells for l in children):cells.append(parent)
    # Source-owned table boxes can supply same-size cells, but only in the
    # immediate caption band, ending before another caption/body paragraph.
    if not cells:
        boxes=[b for b in page.tables if 0<=b[1]-bottom<=30 and b[3]<=stop+1 and b[3]-b[1]<page.height*.7]
        if len(boxes)==1:
            cells=[l for l in page.lines if _inside(l,boxes[0]) and _key(l) not in caption_keys]
    return cells


def _chapter_map(document):
    from .usage_scope import _heading_style
    result={};current=None
    digits={c:i for i,c in enumerate('零一二三四五六七八九')}
    def value(word):
        if word.isdigit():return int(word)
        if '十' in word:
            a,b=word.split('十',1)
            return (digits.get(a,1) if a else 1)*10+(digits.get(b,0) if b else 0)
        return digits.get(word)
    grammar=r'^\s*(?:第\s*([0-9]+|[一二三四五六七八九十]+)\s*章|Chapter\s+([0-9]+)\b)'
    for page in sorted(document.pages,key=lambda p:p.number):
        headings=[]
        for line in page.lines:
            match=re.search(grammar,normalize_text(line.text),re.I)
            if match is None:continue
            # The newly supported Chinese words must be an actual heading.
            # Body chapter-arrangement clauses and small repeated headers
            # cannot start a chapter. Legacy Arabic/English behavior stays.
            chinese=match.group(1) and not match.group(1).isdigit()
            if chinese and not _heading_style(line,page):continue
            headings.append(line)
        if headings:
            m=re.search(grammar,normalize_text(headings[0].text),re.I)
            current=value(m.group(1) or m.group(2))
        result[page.number]=current
    return result


def _numbers(text):
    values=[]
    for match in _NUMBER.finditer(normalize_text(text)):
        try:
            value=Decimal(match.group(1))
        except InvalidOperation:
            continue
        values.append((value,match.group(2)=='%',match.group(1)))
    return values


def _field_names(cells):
    names=[]
    for line in cells:
        text=re.sub(r'\[\d+(?:[-,]\d+)*\]','',normalize_text(line.text)).strip(' .,:;。')
        if not text or _NUMBER.fullmatch(text):
            continue
        # Retain real multiword headers and named rows; generic isolated words
        # and long sentences are not distinctive measurement fields.
        if len(text)<=55 and any(c.isalpha() for c in text):
            normalized=_norm(text)
            if (normalized not in _GENERIC or normalized=='full') and len(normalized)>=3:
                names.append((text,normalized))
            for word in _WORDS.findall(text):
                if word.casefold() not in _GENERIC and len(word)>=3 and (word.isupper() or word[:1].isupper()):
                    names.append((word,_norm(word)))
    return dict((normalized,text) for text,normalized in names)


def _title_agrees(title, text, context=''):
    primary=' '.join(_primary_subjects(title))
    body=_norm(text)
    for word in _WORDS.findall(primary):
        if word.casefold() in _GENERIC or len(word)<3:
            continue
        if (word.isupper() or word[:1].isupper() or any(c.isdigit() for c in word)) and _norm(word) not in body:
            # A table explicitly covering a coordinated list can discuss one
            # of its rows in a sentence inside the same scoped paragraph.
            if not (re.search(r'、|以及|\band\b',primary,re.I) and _norm(word) in _norm(context)):
                return False
    for title_rx,body_rx in _TOPICS:
        # Only an actual nearby section heading can supply an ablation topic;
        # a previous sentence about accuracy cannot supply another claim's
        # experimental identity.
        topic_text=text+(' '+context if 'ablation' in title_rx else '')
        if re.search(title_rx,primary,re.I) and not re.search(body_rx,topic_text,re.I):
            return False
    return True


def _cell_rows(cells):
    rows=[]
    for cell in sorted((l for l in cells if l.role!='usage_table_native_source_row'),key=lambda l:((l.bbox[1]+l.bbox[3])/2,l.bbox[0])):
        cy=(cell.bbox[1]+cell.bbox[3])/2
        if not rows or abs(cy-rows[-1][0])>max(2,(cell.font_size or 10)*.6):
            rows.append((cy,[cell]))
        else:
            rows[-1][1].append(cell)
    return [row for _,row in rows]


def _columns(cells):
    """Keep values attached to their real source header and comparison row."""
    rows=_cell_rows(cells)
    header=next((row for row in rows if len(row)>=2
                 and not any(_NUMBER.fullmatch(normalize_text(l.text).strip()) for l in row)),None)
    if not header:
        return []
    numeric_cells=[l for l in cells if _NUMBER.fullmatch(normalize_text(l.text).strip())]
    if numeric_cells:
        data_top=min(l.bbox[1] for l in numeric_cells)
        # Native multi-line headers can stagger one column by half a line.
        # Retain a lower header only when real numeric cells align beneath
        # its own center; otherwise nearest-column assignment moves that
        # missing column's values into a neighbour.
        header=list(header)
        for line in cells:
            x=(line.bbox[0]+line.bbox[2])/2
            tolerance=max(6,(line.font_size or 10)*.9)
            if (line in header or line.bbox[1]>=data_top-1 or
                    _NUMBER.fullmatch(normalize_text(line.text).strip()) or
                    not any(abs((l.bbox[0]+l.bbox[2])/2-x)<=tolerance for l in numeric_cells) or
                    any(abs((l.bbox[0]+l.bbox[2])/2-x)<=tolerance for l in header)):
                continue
            header.append(line)
        header.sort(key=lambda l:l.bbox[0])
    columns=[]
    for line in header:
        text=normalize_text(line.text).strip(' .,:;。')
        aliases={_norm(text)}
        for word in _WORDS.findall(text):
            if len(word)>=3 and word.casefold() not in _GENERIC and (word.isupper() or word[:1].isupper()):
                aliases.add(_norm(word))
        if _norm(text)=='avg':
            aliases.update((_norm('平均'),_norm('整体平均'),_norm('average')))
        columns.append({'field':text,'x':(line.bbox[0]+line.bbox[2])/2,
                        'aliases':aliases,'values':set(),'rows':{}})
    # A shared alias cannot establish which of two physical columns is used.
    for column in columns:
        column['aliases']={a for a in column['aliases'] if a and
                           sum(a in c['aliases'] for c in columns)==1}
    for row in rows:
        if row is header:
            continue
        label=' '.join(l.text for l in row if not _NUMBER.fullmatch(normalize_text(l.text).strip()))
        for cell in row:
            values=_numbers(cell.text)
            if not _NUMBER.fullmatch(normalize_text(cell.text).strip()) or len(values)!=1:
                continue
            x=(cell.bbox[0]+cell.bbox[2])/2
            column=min(columns,key=lambda c:abs(c['x']-x))
            column['values'].add(values[0][0])
            if label:
                column['rows'][_norm(re.sub(r'\[\d+\]','',label))]=values[0][0]
    return [c for c in columns if c['values'] and c['aliases']]


def _mentions(text, columns):
    original=normalize_text(text);positions=[];parts=[]
    for position,char in enumerate(original):
        if re.match(r'[\s._–—-]',char):
            continue
        folded=char.casefold();parts.append(folded);positions.extend([position]*len(folded))
    normalized=''.join(parts);hits=[]
    for ordinal,column in enumerate(columns):
        for alias in column['aliases']:
            start=0
            while (position:=normalized.find(alias,start))>=0:
                a=positions[position];b=positions[position+len(alias)-1]+1
                left=original[a-1:a];right=original[b:b+1]
                if not (alias.isascii() and alias.isalnum() and
                        (re.match(r'[A-Za-z0-9]',left) or re.match(r'[A-Za-z0-9]',right))):
                    hits.append((position,position+len(alias),ordinal))
                start=position+len(alias)
    # Prefer the whole actual header over an acronym contained within it.
    accepted=[]
    for hit in sorted(hits,key=lambda h:(-(h[1]-h[0]),h[0])):
        if not any(hit[0]<other[1] and other[0]<hit[1] for other in accepted):
            accepted.append(hit)
    return original,[(positions[a],positions[b-1]+1,i) for a,b,i in sorted(accepted)]


def _numeric_claims(descriptor, text, context):
    title,cells=descriptor['title'],descriptor['cells']
    if not _title_agrees(title,text,context):
        return None
    if not re.search(r'提升|提高|降低|下降|达到|优于|表现|结果|性能|改进|\bimprov|\boutperform|\bresults?\b|\baccuracy\b',text,re.I):
        return None
    columns=_columns(cells)
    normalized,hits=_mentions(text,columns)
    compact=_norm(text)
    fields=[];matched=[];claim_evidence=[]
    title_normalized,title_hits=_mentions(title,columns)
    for n,(start,end,ordinal) in enumerate(hits):
        column=columns[ordinal]
        part=normalized[end:hits[n+1][0] if n+1<len(hits) else len(normalized)]
        numbers=_numbers(part)
        if not numbers:
            continue
        # Caption-derived percentages must name the same actual column; the
        # table's label number and bibliography numbers never supply values.
        caption_percent=set()
        for tn,(_,te,ti) in enumerate(title_hits):
            if ti==ordinal:
                tail=title_normalized[te:title_hits[tn+1][0] if tn+1<len(title_hits) else len(title_normalized)]
                caption_percent.update(v for v,p,_ in _numbers(tail) if p)
        named=[(name,value) for name,value in column['rows'].items()
               if name in compact or (name in ('our','ours','proposed') and
                   re.search(r'\bour\b|\bours\b|我们的方法|本文方法|所提方法',text,re.I))]
        derived=[]
        for a,av in named:
            for b,bv in named:
                if a!=b and av:
                    derived.extend((abs(bv-av)*100,abs((bv-av)/av)*100))
        good=[];bad=False
        for value,percent,raw in numbers:
            if not percent and value in column['values']:
                good.append(raw)
            elif percent and (value in caption_percent or any(abs(value-v)<=Decimal('.11') for v in derived)):
                good.append(raw+'% (same-column result)')
            else:
                bad=True
        # An explicitly named result row must contribute a claimed value.
        # Baseline cells alone cannot be relabelled as another method's result.
        if named and any(not p for _,p,_ in numbers):
            named_values={v for _,v in named}
            if not any(not p and v in named_values for v,p,_ in numbers):
                bad=True
        # A field with mixed correct and incorrect column values is not a
        # supported claim; another genuine field can still provide evidence.
        if good and not bad:
            fields.append(column['field']);matched.extend(good)
            claim_evidence.append({'field':column['field'],'body_values':good,
                                   'source_values':[str(v) for v in sorted(column['values'])]})
    fields=list(dict.fromkeys(fields));matched=list(dict.fromkeys(matched))
    if len(fields)<2:
        return None
    return {'kind':'specific_fields_and_quantitative_results','matched_fields':fields,
            'matched_values':matched,'column_claims':claim_evidence}


def _phase(text):
    value=normalize_text(text).casefold()
    matches=[]
    for number,word,chinese in ((1,'first','一'),(2,'second','二'),(3,'third','三'),(4,'fourth','四')):
        match=re.search(r'(?:第'+chinese+r'阶段|阶段'+chinese+r'|'+word+r'[- ]stage|'+word+r'\s+stage|stage\s*'+str(number)+r')',value)
        if match:
            matches.append((match.start(),number))
    return min(matches)[1] if matches else None


def _contract(descriptor,text,context):
    title=descriptor['title'];cells=' '.join(l.text for l in descriptor['cells'])
    if not re.search(r'prompt|提示',title,re.I) or not _phase(title) or _phase(title)!=_phase(text):
        return None
    if not re.search(r'输入|原始文本|input\s+text|takes?\s+.*text',text,re.I):
        return None
    if not re.search(r'文本|input\s+text',cells,re.I):
        return None
    analysis=r'特征分析|分析结果|结构化分析|feature\s+analysis'
    final=r'最终(?:来源)?判断|最终(?:判别)?结论|final\s+(?:source\s+)?decision|判别结论'
    prohibit=r'(?:不|不要|without|not)\s*(?:直接|directly)?[^。.!]{0,12}(?:判断|判别|结论|decision)'
    if re.search(prohibit,cells,re.I):
        if not re.search(prohibit,text,re.I) or not re.search(analysis,text,re.I) or not re.search(analysis,cells,re.I):
            return None
        return {'kind':'stage_input_output_contract','matched_fields':['input text','structured feature analysis','withheld final decision'],
                'matched_values':[],'stage':_phase(title)}
    prior=r'前一阶段|前一阶段生成|prior[- ]stage|previous\s+stage|阶段一.*(?:输出|分析)'
    if (re.search(prior,cells,re.I) and re.search(prior,text,re.I)
            and re.search(analysis,cells,re.I) and re.search(analysis,text,re.I)
            and re.search(final,cells,re.I) and re.search(final,text,re.I)):
        return {'kind':'stage_input_output_contract','matched_fields':['input text','prior-stage feature analysis','final source decision'],
                'matched_values':[],'stage':_phase(title)}
    return None


def _regime(descriptor,text,context):
    title=descriptor['title'];cells=' '.join(l.text for l in descriptor['cells'])
    # A caption's data/environment identity must be in independent prose.
    # The context here is restricted to a physically continuing prior-page
    # paragraph; table captions and unrelated earlier sections cannot supply it.
    if not _title_agrees(title,text+' '+context):
        return None
    primary=' '.join(_primary_subjects(title))
    for match in re.finditer(r'(?i:\bon\s+(?:the\s+)?)([A-Z][A-Za-z0-9_-]*)|'
                             r'(?i:\b(?:using|within)\s+(?:the\s+)?)([A-Z][A-Za-z0-9_-]*)\s+(?i:dataset|simulator)\b|'
                             r'(?:在|基于|使用)\s*([A-Za-z][A-Za-z0-9_-]*)\s*数据集',text):
        identity=next(s for s in match.groups() if s)
        if _norm(identity) not in _norm(primary):
            return None
    # Evaluation settings must describe actual independent results, not a
    # software/data citation or a generic statement of model capability.
    if not re.search(r'实验结果|性能提升|优于|\boutperform|\bresults?\b.*\bimprov',text,re.I):
        return None
    baselines=[w for w in _WORDS.findall(cells) if w.casefold() not in _GENERIC
               and (w.isupper() or any(c.isupper() for c in w[1:])) and _norm(w) in _norm(text)]
    if not baselines:
        return None
    settings=[]
    for name,title_rx,body_rx in (
        ('zero-shot',r'零样本|zero[- ]shot',r'零样本|zero[- ]shot'),
        ('independent of training/test split',r'训练.*测试|training.*test',r'(?:未|不|without)[^。.!]{0,30}(?:训练.*测试|training.*test)'),
        ('without fine-tuning',r'不微调|without\s+fine[- ]tuning',r'不微调|without\s+fine[- ]tuning'),
    ):
        if re.search(title_rx,title,re.I) and re.search(body_rx,text,re.I):
            settings.append(name)
    if len(settings)<2:
        return None
    # Different experimental topics using the same baseline remain separate.
    manip=r'对象操作|object\s+manipulation|articulate.*manipulation'
    if re.search(manip,title,re.I) and not re.search(r'对象操作|接触点|接触方向|运动方向|manipulation|contact\s+(?:point|direction)',text,re.I):
        return None
    if any(re.search(a,title,re.I) and not re.search(b,text+' '+context,re.I) for a,b in _TOPICS):
        return None
    return {'kind':'distinct_experiment_settings_and_baseline','matched_fields':list(dict.fromkeys(baselines))+settings,
            'matched_values':[]}


def _table_prose(eligible,document):
    """Native numbered section headings also bound independent table claims.

    A regular font is common in exported English section headings. Their
    printed number and short title remain a boundary even when bold metadata
    is absent. Sentence-start table numbers ending in a dot are not headings.
    """
    ordered=sorted(eligible,key=lambda item:(item[0].page_number,item[0].bbox[1],item[0].bbox[0]))
    headings=set()
    for line,_ in ordered:
        if not re.match(r'^\s*\d+(?:\.\d+){1,4}(?:\s+|$)',normalize_text(line.text)):
            continue
        siblings=[other for other,_ in ordered if other.page_number==line.page_number
                  and abs((other.bbox[1]+other.bbox[3]-line.bbox[1]-line.bbox[3])/2)<=max(2,(line.font_size or 10)*.4)]
        text=' '.join(l.text for l in sorted(siblings,key=lambda l:l.bbox[0]))
        # A decimal count with its quantity unit and an actual prose action
        # is not a numbered section. Units alone, heading typography, or
        # phrases such as "3.1 帧间..." / "3.1 样本..." do not qualify.
        if (not any(l.bold for l in siblings)
                and re.match(r'^\s*\d+(?:\.\d+)?\s*(?:万|千|百|亿)\s*(?:帧|条|个)',normalize_text(text))
                and re.search(r'[,，][^。!?]*?(?:包含|标注|采集|构成|产生|生成)[了的]?[^。!?]*\d',normalize_text(text))):
            continue
        if (len(text)<=100 and re.fullmatch(r'\s*\d+(?:\.\d+){1,4}\s+[A-Za-z\u4e00-\u9fff][^。.!?;；:：]*',normalize_text(text))):
            headings.update(_key(l) for l in siblings)
    section=0;rows=[];last_heading=None
    for line,identity in ordered:
        if _key(line) in headings:
            row=(line.page_number,round((line.bbox[1]+line.bbox[3])/2))
            if row!=last_heading:section+=1;last_heading=row
            continue
        rows.append((line,(*identity,section)))
    return [(paragraph,identity[:2]) for paragraph,identity in _prose(rows,document)]


def table_usage_evidence(index:DocumentIndex,groups:list[list[Label]]) -> dict[int,dict]:
    from .caption_context import body_font
    from .usage_scope import usage_scope_map, is_body_usage_scope, usage_epoch, usage_scope_identity
    pages={p.number:p for p in index.document.pages}
    fonts={number:body_font(page) for number,page in pages.items()}
    directories=toc_line_keys(index.document)
    scopes=usage_scope_map(index.document,directories)
    caption_keys=set();titles={}
    for kind,labels in (('table',index.tables),('figure',index.figures)):
        for label in labels:
            page=pages.get(label.line.page_number)
            if page:
                _,rows=(_table_title([label],page) if kind=='table' else _full_title([label],page,kind))
                caption_keys.update(_key(l) for l in rows)
    for i,group in enumerate(groups):
        if (group and group[0].line.page_number in pages
                and all(is_body_usage_scope(scopes,label) for label in group)
                and len({usage_epoch(scopes,label) for label in group})==1):
            title,rows=_table_title(group,pages[group[0].line.page_number])
            titles[i]=(title,rows)
            caption_keys.update(_key(l) for l in rows)
    descriptors=[];cell_keys=set()
    for i,(title,rows) in titles.items():
        target=groups[i][0];page=pages[target.line.page_number]
        cells=_cells(groups[i],page,rows,caption_keys)
        cell_keys.update(_key(l) for l in cells)
        if cells:
            descriptors.append({'i':i,'target':target,'title':title,'cells':cells,'fields':_field_names(cells),
                                'caption_rows':rows,'usage_epoch':usage_epoch(scopes,target)})
    if not descriptors:
        return {}
    excluded=caption_keys|cell_keys|directories
    eligible=[]
    for l in index.lines:
        page=pages[l.page_number]
        typical=fonts[l.page_number]
        if (_key(l) in excluded or l.bold or not l.text.strip() or is_toc_line(l.text)
                or not is_body_usage_scope(scopes,l)
                or typical and l.font_size and l.font_size<typical*.95):
            continue
        if any(_inside(l,b) and b[3]-b[1]<page.height*.7 for b in (*page.images,*page.tables)):
            continue
        eligible.append((l,usage_scope_identity(scopes,l)))
    chapters=_chapter_map(index.document)
    used={}
    prose_rows=_table_prose(eligible,index.document)
    paragraphs=[p for p,_ in prose_rows]
    paragraph_epochs={id(p):identity[1] for p,identity in prose_rows}
    for paragraph_ordinal,paragraph in enumerate(paragraphs):
        epoch=paragraph_epochs[id(paragraph)]
        paragraph_numbers=_explicit_table_numbers(paragraph.text)
        continuation=[]
        if paragraph_ordinal:
            previous=paragraphs[paragraph_ordinal-1]
            previous_page=pages[previous.page_number]
            section_barrier=any(l.bold and _key(l) not in excluded
                                and is_body_usage_scope(scopes,l) and usage_epoch(scopes,l)==epoch
                                and l.font_size and fonts[l.page_number]
                                and l.font_size>=fonts[l.page_number]*.95
                                and l.bbox[1]<=paragraph.bbox[1]+1
                                and not re.match(r'^\s*(?:第\s*\d+\s*章|Chapter\s+\d+)',normalize_text(l.text),re.I)
                                for l in pages[paragraph.page_number].lines)
            if (previous.page_number+1==paragraph.page_number
                    and paragraph_epochs[id(previous)]==epoch
                    and previous.bbox[3]>=previous_page.height*.75
                    and not re.search(r'[。.!?；;:]\s*$',previous.text)
                    and chapters.get(previous.page_number)==chapters.get(paragraph.page_number)
                    and not section_barrier):
                continuation=[previous]
        prose_context=' '.join(p.text for p in continuation)
        if (continuation and re.search(r'\bTables?\s*$',normalize_text(prose_context),re.I)
                and re.match(r'^\s*\d+(?:[.\-]\d+)+(?:\.|\b)',normalize_text(paragraph.text))
                and not re.search(r'(?:publication|literature|paper|study|文献|研究)[^。.!?]{0,80}\[[0-9,， -]+\][^。.!?]{0,120}\bTables?\s*$',normalize_text(prose_context),re.I)):
            numbers=_explicit_table_numbers(prose_context+' '+paragraph.text)
            for descriptor in descriptors:
                target=descriptor['target']
                if (target.number not in numbers or descriptor['usage_epoch']!=epoch
                        or chapters.get(target.line.page_number)!=chapters.get(paragraph.page_number)):
                    continue
                owners=[g for g in groups if g and normalize_label(g[0].number)==normalize_label(target.number)
                        and usage_epoch(scopes,g[0])==epoch
                        and chapters.get(g[0].line.page_number)==chapters.get(paragraph.page_number)]
                if len(owners)!=1:continue
                used.setdefault(descriptor['i'],{
                    'physical_key':{'number':target.number,'page':target.line.page_number,'caption_bbox':list(target.line.bbox),'scope':target.scope},
                    'usage_epoch':epoch,'title':descriptor['title'],
                    'body':{'page':paragraph.page_number,'bbox':list(paragraph.bbox),'text':paragraph.text},
                    'body_context':[{'page':p.page_number,'bbox':list(p.bbox),'text':p.text} for p in continuation],
                    'cell_evidence':[{'page':l.page_number,'bbox':list(l.bbox),'text':l.text} for l in descriptor['cells']],
                    'kind':'printed_local_table_reference_continues_across_page',
                    'matched_fields':[normalize_label(target.number)],'matched_values':[],
                    'uniqueness_reason':'The physically continuing independent prose prints a local reference to one same-epoch same-chapter physical table.'})
        # Different quantitative claims inside one paragraph may separately
        # identify different tables. Competition is per actual sentence claim.
        boundaries=[0]+[m.end() for m in re.finditer(r'[。!?]|(?<!\d)\.(?=\s+[A-Z]|$)',paragraph.text)]
        if boundaries[-1]!=len(paragraph.text):
            boundaries.append(len(paragraph.text))
        fragments=[(a,b,paragraph.text[a:b],False) for a,b in zip(boundaries,boundaries[1:]) if paragraph.text[a:b].strip()]
        fragments.append((0,len(paragraph.text),paragraph.text,True))
        headings=[l for l in pages[paragraph.page_number].lines
                  if l.bold and _key(l) not in excluded and l.font_size and l.font_size>=11
                  and is_body_usage_scope(scopes,l) and usage_epoch(scopes,l)==epoch
                  and l.bbox[1]<=paragraph.bbox[1]+1]
        heading=max(headings,key=lambda l:l.bbox[1]).text if headings else ''
        for start,end,text,whole in fragments:
            matches=[]
            claim_numbers=_explicit_table_numbers(text) or paragraph_numbers
            for descriptor in descriptors:
                target=descriptor['target'];pn=target.line.page_number
                if descriptor['usage_epoch']!=epoch:
                    continue
                if abs(pn-paragraph.page_number)>1 and not (chapters.get(pn) is not None and chapters.get(pn)==chapters.get(paragraph.page_number)):
                    continue
                if not _table_pointer_agrees(descriptor,claim_numbers):
                    continue
                # Multi-sentence contracts/regimes need a paragraph. Numeric
                # claims remain sentence-local, with only a real heading as
                # their topic context and the scoped paragraph for title IDs.
                match=(_contract(descriptor,text,heading)
                       or (not whole and _numeric_claims(descriptor,text,heading+' '+paragraph.text))
                       or _regime(descriptor,text,prose_context
                                  if _table_pointer_agrees(descriptor,_explicit_table_numbers(prose_context)) else ''))
                if match:
                    matches.append((descriptor,match))
            if len(matches)!=1:
                continue
            descriptor,match=matches[0];target=descriptor['target']
            body=span_anchor(paragraph,start,end)
            used.setdefault(descriptor['i'],{
                'physical_key':{'number':target.number,'page':target.line.page_number,'caption_bbox':list(target.line.bbox),'scope':target.scope},
                'usage_epoch':epoch,
                'title':descriptor['title'],'body':{'page':body.page_number,'bbox':list(body.bbox),'text':text},
                'body_context':[{'page':p.page_number,'bbox':list(p.bbox),'text':p.text} for p in continuation
                                if match['kind']=='distinct_experiment_settings_and_baseline'
                                and not _title_agrees(descriptor['title'],text)],
                'cell_evidence':[{'page':l.page_number,'bbox':list(l.bbox),'text':l.text} for l in descriptor['cells']],
                'uniqueness_reason':'One physical table matches this independent sentence/contract among all supplied physical groups.',
                **match,
            })
    from .usage_table_semantics import semantic_table_evidence
    for ordinal,evidence in semantic_table_evidence(index,descriptors,paragraphs,chapters,paragraph_epochs).items():
        used.setdefault(ordinal,evidence)
    return used


def table_usage_groups(index:DocumentIndex,groups:list[list[Label]]) -> set[int]:
    return set(table_usage_evidence(index,groups))
