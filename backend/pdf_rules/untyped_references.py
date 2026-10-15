"""Resolve a type-omitted deictic only to one immediately adjacent real visual."""
import re
from .model import Label
from .mineru_layout import LayoutObject
from .caption_rules import _matches
from .caption_context import contextual_caption
from .numbering import normalize_text
from .usage_paragraphs import span_anchor

CUE=re.compile(r'如下(?:所示)?\s*[:：。.]?\s*$')


def add_untyped_references(index,eligible_lines,objects):
    pages={p.number:p for p in index.document.pages}
    offsets={};cursor=0
    for page in index.document.pages:offsets[page.number]=cursor;cursor+=page.height
    from .implicit_references import section_boundaries
    boundaries=section_boundaries(index.document,objects,offsets)
    for line,scope in eligible_lines:
        text=normalize_text(line.text)
        match=CUE.search(text)
        if not match:continue
        anchor=span_anchor(line,match.start(),match.end())
        choices={}
        for obj in objects:
            if obj.kind not in {'figure','table'} or obj.page_number!=line.page_number:continue
            if not 0<=obj.bbox[1]-anchor.bbox[3]<=140:continue
            page=pages[line.page_number]
            intervening=[l for l in page.lines if anchor.bbox[3]+1<=l.bbox[1] and l.bbox[3]<=obj.bbox[1]
                         and len(l.text.strip())>=8 and l.page_width*.08<l.bbox[0]
                         and not contextual_caption(l,page,'figure') and not contextual_caption(l,page,'table')]
            if intervening:continue
            targets=index.figures if obj.kind=='figure' else index.tables
            for target in targets:
                if target.scope!=scope or target.line.page_number!=obj.page_number:continue
                t=target.line
                title=LayoutObject(obj.kind+'_caption',t.page_number,t.bbox,t.text,t.page_width,t.page_height)
                if _owns_caption(obj,title,objects):choices[(obj.kind,target.scope,target.number)]=target
        if not choices:
            # A float can move past intervening prose or onto the next page.
            # Require an exact, specific four-character header phrase and one
            # target in the same section; distance alone is never evidence.
            from .descriptive_references import _shared_phrase
            subject=re.sub(r'\s+','',text[:match.start()])
            position=offsets[line.page_number]+anchor.bbox[3]
            for obj in objects:
                if obj.kind!='table' or not 0<=obj.page_number-line.page_number<=1:continue
                destination=offsets[obj.page_number]+obj.bbox[1]
                if not 0<=destination-position<=line.page_height*.9:continue
                if any(position<b<destination for b in boundaries):continue
                header=re.sub(r'\s+','',normalize_text(obj.text[:160]))
                if _shared_phrase(subject,header)<4:continue
                for target in index.tables:
                    if target.scope!=scope or target.line.page_number!=obj.page_number:continue
                    t=target.line
                    title=LayoutObject('table_caption',t.page_number,t.bbox,t.text,t.page_width,t.page_height)
                    if _owns_caption(obj,title,objects):choices[('table',target.scope,target.number)]=target
        if len(choices)!=1:continue
        (kind,_,_),target=next(iter(choices.items()))
        refs=index.graphic_figure_refs if kind=='figure' else index.graphic_table_refs
        refs.append(Label(target.number,anchor,scope,target.scope))


def _owns_caption(body,title,objects):
    """A neighbour's closer physical body owns its title.

    Keep ties ambiguous. This guards a floated reference from being attached
    to both the caption above its table and the next table's caption below.
    """
    if not _matches(body,title):return False
    def gap(obj):return min(abs(obj.bbox[1]-title.bbox[3]),abs(title.bbox[1]-obj.bbox[3]))
    return not any(peer!=body and peer.kind==body.kind and peer.page_number==body.page_number
                   and _matches(peer,title) and gap(peer)+1<gap(body) for peer in objects)
