"""Resolve explicitly composed visuals when their repeated type prefix is omitted."""
import re
from .model import Label
from .numbering import normalize_text,normalize_label
from .usage_paragraphs import span_anchor

NUMBER=r'(?:[A-Z]\.)?\d+(?:[.\-]\d+)*'
COMPOSITION=re.compile(r'(?P<subject>[^。；;！？!?，,：:\n]{2,80})由\s*(?P<numbers>'+NUMBER+r'(?:\s*(?:和|与|及|、|,|，)\s*'+NUMBER+r'){1,7})\s*(?:拼接而成|合并而成|组合而成|组成|构成)',re.I)


def add_composed_references(index,eligible_lines,targets,title_of,shared_phrase):
    for line,scope in eligible_lines:
        text=normalize_text(line.text)
        for match in COMPOSITION.finditer(text):
            subject=re.sub(r'\s+','',match.group('subject'))
            if re.search(r'章节|小节|公式|方程',subject):
                continue
            numbers=[normalize_label(v.group()) for v in re.finditer(NUMBER,match.group('numbers'),re.I)]
            choices=[]
            for number in numbers:
                options={}
                for kind,target in targets:
                    if target.scope!=scope or target.number!=number:
                        continue
                    if abs(target.line.page_number-line.page_number)>1:
                        continue
                    title=title_of(target,kind)
                    if shared_phrase(subject,title)<4 and not any(subject[i:i+3] in title for i in range(len(subject)-2)):
                        continue
                    options.setdefault(kind,target)
                if len(options)!=1:
                    break
                choices.append(next(iter(options.items())))
            if len(choices)!=len(numbers) or len({kind for kind,_ in choices})!=1:
                continue
            anchor=span_anchor(line,match.start('numbers'),match.end('numbers'))
            for kind,target in choices:
                refs=index.graphic_figure_refs if kind=='figure' else index.graphic_table_refs
                refs.append(Label(target.number,anchor,scope,target.scope))
