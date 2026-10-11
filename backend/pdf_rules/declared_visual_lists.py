"""Recognize an explicit named series, including figures/tables floated later."""
import re
from .model import Label
from .numbering import normalize_text
from .usage_paragraphs import span_anchor

DECLARATION=re.compile(r'(?:本节|下文|以下|下面)\s*(?:给出|列出|展示|汇报)(?P<subject>[^。；;!?！？]{2,100})')


def add_declared_visual_lists(index,eligible_lines,targets,title_of,shared_phrase):
    for line,scope in eligible_lines:
        for match in DECLARATION.finditer(normalize_text(line.text)):
            subject=re.split(r'[（(]',match.group('subject'))[0]
            if not re.search(r'各|所有|全部|一系列',subject):continue
            subject=re.sub(r'\s+','',subject)
            candidates={}
            for kind,target in targets:
                if target.scope!=scope or not 0<=target.line.page_number-line.page_number<=2:continue
                if target.line.page_number==line.page_number and target.line.bbox[1]<=line.bbox[3]:continue
                score=shared_phrase(subject,title_of(target,kind))
                if score>=4:candidates[(kind,target.scope,target.number)]=(score,target)
            if not candidates:continue
            best=max(score for score,_ in candidates.values())
            candidates={key:target for key,(score,target) in candidates.items() if score==best}
            if len(candidates)<2 or len({key[0] for key in candidates})!=1:continue
            ordered=sorted(candidates.items(),key=lambda pair:(pair[1].line.page_number,pair[1].line.bbox[1]))
            numbers=[key[2].rsplit('.',1) for key,_ in ordered]
            if any(len(parts)!=2 or not parts[1].isdigit() for parts in numbers):continue
            if len({parts[0] for parts in numbers})!=1:continue
            if any(int(b[1])!=int(a[1])+1 for a,b in zip(numbers,numbers[1:])):continue
            anchor=span_anchor(line,match.start(),match.end())
            for (kind,_,_),target in ordered:
                refs=index.graphic_figure_refs if kind=='figure' else index.graphic_table_refs
                refs.append(Label(target.number,anchor,scope,target.scope))
