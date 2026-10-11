"""Native panel-description blocks belong to their actual numbered total title."""
from dataclasses import replace
from .numbering import FIGURE_CAPTION, normalize_text, normalize_label
from .layout_context import PANEL, union, _panel_match
from .logical_objects import panel_label_lines, axis_unit


def extend_panel_description_titles(targets,captions,document):
    pages={p.number:p for p in document.pages}
    result=[]
    for title in captions:
        printed=FIGURE_CAPTION.search(normalize_text(title.text))
        if title.kind!='figure_caption' or not printed:
            result.append(title);continue
        page=pages[title.page_number]
        fonts={round(l.font_size,1) for l in page.lines if l.source=='native'
               and l.font_size and l.bold and title.bbox[1]-3<=l.bbox[1]<=title.bbox[3]
               and (m:=FIGURE_CAPTION.search(normalize_text(l.text)))
               and normalize_label(m.group('number'))==normalize_label(printed.group('number'))}
        if len(fonts)!=1:
            result.append(title);continue
        font=next(iter(fonts));chains=[]
        for parent in targets:
            if parent.kind!='figure' or parent.page_number!=title.page_number or parent.bbox[3]>=title.bbox[1]:continue
            if abs((title.bbox[0]+title.bbox[2]-parent.bbox[0]-parent.bbox[2])/2)>(parent.bbox[2]-parent.bbox[0])*.12:continue
            lines=panel_label_lines(page,[parent],captions)
            tags=[_panel_match(l.text).group(1).lower() for l in lines
                  if parent.bbox[0]-15<=(l.bbox[0]+l.bbox[2])/2<=parent.bbox[2]+15
                  and parent.bbox[1]<=l.bbox[1]<=parent.bbox[3]+35
                  and not axis_unit(l,[parent],page)]
            if len(tags)<2 or len(tags)!=len(set(tags)):continue
            block=[];low=title.bbox[1]
            for line in sorted(page.lines,key=lambda l:(l.bbox[1],l.bbox[0]),reverse=True):
                if line.bbox[1]>=title.bbox[1] or line.bbox[3]<=parent.bbox[3]:continue
                if line.bbox[2]<=parent.bbox[0] or line.bbox[0]>=parent.bbox[2]:continue
                if (line.source!='native' or not line.bold or not line.font_size
                        or abs(line.font_size-font)>font*.05
                        or low-line.bbox[3]>max(18,font*1.8)
                        or FIGURE_CAPTION.search(normalize_text(line.text))):break
                block.append(line);low=min(low,line.bbox[1])
            mentioned={m.group(1).lower() for line in block for m in PANEL.finditer(normalize_text(line.text))}
            if len(mentioned)<2 or not mentioned.issubset(set(tags)) or not block:continue
            if min(l.bbox[1] for l in block)-parent.bbox[3]>35:continue
            if any(c is not title and c.page_number==title.page_number
                   and parent.bbox[3]<c.bbox[1]<title.bbox[1]
                   and min(c.bbox[2],parent.bbox[2])>max(c.bbox[0],parent.bbox[0])
                   for c in captions):continue
            if any(o is not parent and o.kind in {'figure','table'} and o.page_number==title.page_number
                   and parent.bbox[3]<o.bbox[1]<title.bbox[1]
                   and min(o.bbox[2],parent.bbox[2])>max(o.bbox[0],parent.bbox[0])
                   for o in targets):continue
            chains.append(block)
        if len(chains)==1:
            title=replace(title,bbox=union([title.bbox]+[l.bbox for l in chains[0]]),role='native_panel_description_title')
        result.append(title)
    return result
