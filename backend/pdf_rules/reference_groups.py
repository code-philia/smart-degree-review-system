"""Expand explicit citation ranges/lists while retaining their original ink spans."""
import re
from dataclasses import dataclass
from .numbering import normalize_label, FIGURE_REFERENCE_LABEL, CITATION_AND

@dataclass(frozen=True)
class ReferenceMatch:
    text: str
    number: str
    word_start: int
    number_start: int
    number_end: int
    end_offset: int
    def group(self,key=0):
        return self.number if key=='number' else self.text[self.word_start:self.end_offset]
    def start(self,key=0):
        return self.number_start if key=='number' else self.word_start
    def end(self,key=0):
        return self.number_end if key=='number' else self.end_offset

# A hyphen within 7-2 is a chapter separator; between two complete chapter
# labels (7.2-7.4 or 7-2-7-4) it denotes a range. Bare 2-4 stays ambiguous.
RANGE=re.compile(r'^([A-Z]?\d+[.\-]\d+)\s*[-~至到]\s*([A-Z]?\d+[.\-]\d+)$',re.I)
# Use the same complete label grammar at each endpoint. A numeric panel
# suffix can precede a range separator, but identifiers such as F2D cannot.
NEXT=re.compile(rf'\s*[)）]?\s*(?P<sep>以及|{CITATION_AND}|[,，、和及与]|至|到|[-~]|\bto\b|\s+)\s*(?P<word>图|表格?|Figures?|Figs?\.?|Tables?)?\s*[(（]?\s*'+FIGURE_REFERENCE_LABEL,re.I)

def expand_range(first,last):
    a,b=normalize_label(first),normalize_label(last)
    prefix,start=a.rsplit('.',1) if '.' in a else ('',a)
    other,end=b.rsplit('.',1) if '.' in b else ('',b)
    if prefix==other and start.isdigit() and end.isdigit() and 0<=int(end)-int(start)<=100:
        return [f'{prefix}.{n}' if prefix else str(n) for n in range(int(start),int(end)+1)]
    return [a,b]

def reference_matches(pattern,text):
    emitted=set()
    for match in pattern.finditer(text):
        start,end=match.span('number');number=match.group('number')
        span=RANGE.fullmatch(number)
        numbers=expand_range(*span.groups()) if span else [number]
        for n in numbers:
            identity=(start,end,normalize_label(n))
            if identity not in emitted:
                emitted.add(identity)
                yield ReferenceMatch(text,n,match.start(),start,end,match.end())
        cursor=match.end();previous=numbers[-1]
        while extra:=NEXT.match(text,cursor):
            # Repeated labels at a range endpoint must identify the same kind.
            # A figure followed by a table never implies intermediate figures.
            if extra.group('word') and not pattern.match(text,extra.start('word')):
                break
            n=extra.group('number')
            tail=text[extra.end():]
            if extra.group('sep').isspace():
                # An unpunctuated list needs a shared chapter prefix and a
                # complete citation terminator, not an adjacent decimal result.
                first=normalize_label(previous);next_label=normalize_label(n)
                if '.' not in first or first.rsplit('.',1)[0]!=next_label.rsplit('.',1)[0]:break
                rest=text[cursor:]
                prefix=re.escape(first.rsplit('.',1)[0])+r'[.\-][0-9]+'
                if not re.match(r'(?:\s+'+prefix+r')+\s*(?:[，,。:：;；)）]|结果所示|所示|所述|展示|显示|给出)',rest,re.I):break
            # A list conjunction can introduce a quantity, not another
            # academic object. ASCII unit boundaries also allow following
            # Chinese prose (e.g. 'ms的'), which Unicode word boundaries do not.
            quantity_tail=text[extra.end('number'):]
            suffix=text[extra.end('number'):extra.end()].strip()
            panel_pointer=bool(suffix and re.match(r'\s*(?:所示|所述|中的?|显示|展示|给出|表明|说明|[，,。;；:：)）]|$)',tail))
            if (not panel_pointer and re.match(
                    r'\s*(?:[%％‰°℃]|倍|个|次|秒|小时|毫秒|分钟|'
                    r'(?:千克|公斤|毫克|克|千米|厘米|毫米|纳米|米|牛顿|焦耳|瓦特|伏特|安培|帕斯卡|赫兹)(?=的|每|[ /,，。；;:：)）]|$)|'
                    r'[yzafpnumcdhkMGTPEZYμµ]?(?:mol|Hz|Pa|cd|s|g|m|N|J|W|V|A|B|F|H|K|C|L)(?![A-Za-z0-9]))',quantity_tail)):
                break
            # An elided prefix must keep the same numbering depth. This avoids
            # consuming a neighbouring numeric measurement as another figure.
            if normalize_label(previous).count('.')!=normalize_label(n).count('.'):
                break
            start,end=extra.span('number')
            ns=expand_range(previous,n)[1:] if extra.group('sep').lower() in {'-','~','至','到','to'} else [n]
            for value in ns:
                identity=(start,end,normalize_label(value))
                if identity not in emitted:
                    emitted.add(identity)
                    yield ReferenceMatch(text,value,match.start(),start,end,extra.end())
            previous=n;cursor=extra.end()
