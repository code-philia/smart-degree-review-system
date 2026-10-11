"""Recover typographically distinct panel titles and bound cloud table captions."""
import re
from dataclasses import replace
from statistics import median
from .mineru_layout import LayoutObject
from .layout_context import containment,union
from .numbering import normalize_text,caption_match,normalize_label,CAPTION_NARRATIVE

PANEL=re.compile(r'^\s*[（(][a-z][）)]\s*(?P<title>\S.*)',re.I)


def recover_table_titles(targets,captions,document):
    pages={p.number:p for p in document.pages}
    result=[]
    for caption in captions:
        if caption.kind!='table_caption':
            result.append(caption);continue
        page=pages[caption.page_number]
        declared=caption_match(caption.text,'table')
        anchors=[l for l in page.lines if containment(l.bbox,caption.bbox)>=.8
                 and (m:=caption_match(l.text,'table')) and declared
                 and normalize_label(m.group('number'))==normalize_label(declared.group('number'))]
        panels=[l for l in page.lines if PANEL.match(normalize_text(l.text))
                and containment(l.bbox,caption.bbox)>=.8
                and any(t.kind=='table' and t.page_number==page.number and containment(l.bbox,t.bbox)>=.8 for t in targets)]
        if anchors and panels:
            anchor=min(anchors,key=lambda l:l.bbox[1]);edge=min(l.bbox[1] for l in panels)
            if anchor.bbox[3]<=edge and any(l.block_id!=anchor.block_id for l in panels):
                own=[l for l in page.lines if containment(l.bbox,caption.bbox)>=.8 and l.bbox[3]<=edge+1]
                caption=replace(caption,bbox=union([l.bbox for l in own]),text=' '.join(l.text for l in own))
        result.append(caption)
    for table in targets:
        if table.kind!='table':continue
        page=pages[table.page_number]
        cells=[l for l in page.lines if l.font_size and containment(l.bbox,table.bbox)>=.8
               and re.search(r'\d',l.text) and not PANEL.match(normalize_text(l.text))]
        if len(cells)<3:continue
        cell_font=median(l.font_size for l in cells)
        for line in page.lines:
            match=PANEL.match(normalize_text(line.text))
            if not match or not line.font_size or line.font_size<cell_font*1.15:continue
            title=match.group('title')
            if len(re.findall(r'[A-Za-z\u4e00-\u9fff]',title))<6 or re.search(r'[。；;!?！？]',title) or CAPTION_NARRATIVE.match(title):continue
            vertical=abs(line.direction[0])<.1
            axis=1 if vertical else 0
            if abs((line.bbox[axis]+line.bbox[axis+2]-table.bbox[axis]-table.bbox[axis+2])/2)>(table.bbox[axis+2]-table.bbox[axis])*.15:continue
            if containment(line.bbox,table.bbox)<.8:
                from .caption_rules import _matches
                probe=LayoutObject('table_caption',page.number,line.bbox,line.text,page.width,page.height)
                if not _matches(table,probe):continue
            result.append(LayoutObject('table_caption',page.number,line.bbox,line.text,page.width,page.height,'unnumbered_panel_title'))
    return result
