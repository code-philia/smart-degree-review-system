"""Restore an explicitly broken typed number across native prose page edges.

This is separate from same-page paragraph inheritance. A complete number never
borrows the next page's digits, and the target need not exist. Both pieces retain
their original glyph observations; the first piece anchors a missing citation.
"""
import re
from dataclasses import replace,asdict
from .model import Label
from .numbering import normalize_text,normalize_label,FIGURE_REFERENCE,TABLE_REFERENCE,APPENDIX_QUALIFIER,toc_line_keys
from .reference_context import local_reference

_DANGLING=re.compile(r'(?P<kind>图|表格?|(?<![A-Za-z])Figures?|(?<![A-Za-z])Figs?\.?|(?<![A-Za-z])Tables?)\s*'
    r'(?P<prefix>(?:[A-Z]\.)?[0-9]+(?:\s*[.\-]\s*[0-9]+)*)\s*(?P<separator>[.\-])\s*$',re.I)
_CONTINUED=re.compile(r'^\s*(?P<number>[0-9]+(?:\s*[.\-]\s*[0-9]+)*)'
    r'(?P<panel>\s*[(（]\s*[a-z]\s*[)）])?\s*'
    r'(?=所示|所述|展示|显示|中|[、，,。;；:：])',re.I)
_NONBODY_ROLES={'header','footer','page_number','figure','table','figure_caption','table_caption','equation','title','list'}

def _key(line):return (line.page_number,line.bbox)
def _num(value):return normalize_label(re.sub(r'\s+','',value))
def _overlap(a,b):return max(a[0],b[0])<min(a[2],b[2]) and max(a[1],b[1])<min(a[3],b[3])

def _glyph_span(line,start,end):
    """Each non-space numeric character must have its own real native box."""
    text=normalize_text(line.text);boxes=[]
    for pos in range(start,end):
        if text[pos].isspace():continue
        found=[box for a,b,box in line.text_regions if a==pos and b==pos+1
               and box[0]<box[2] and box[1]<box[3]
               and line.bbox[0]-.5<=box[0]<box[2]<=line.bbox[2]+.5
               and line.bbox[1]-.5<=box[1]<box[3]<=line.bbox[3]+.5]
        if len(found)!=1:return None
        boxes.append(found[0])
    if not boxes:return None
    return (min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes))

def _margin(line,page,size):
    if line.role in {'header','footer','page_number'}:return True
    if line.bbox[3]<=page.height*.115 and line.font_size and line.font_size<=size*.85:return True
    return bool(line.bbox[1]>=page.height*.88 and line.font_size and line.font_size<=size*.85
                and re.fullmatch(r'\s*(?:[-—]\s*)?\d+(?:\s*[-—])?\s*',normalize_text(line.text)))

def _body_ink(line,page,excluded):
    if (_key(line) in excluded or line.source!='native' or line.bold or not line.font_size
            or line.direction!=(1.0,0.0) or line.role in _NONBODY_ROLES):return False
    from .caption_context import body_font
    typical=body_font(page)
    if typical and line.font_size<typical*.95:return False
    box=line.bbox
    return not any(b[0]<=box[0] and b[1]<=box[1] and b[2]>=box[2] and b[3]>=box[3]
                   for b in (*page.images,*page.tables,*page.graphics))

def _clear_edge(line,page,last):
    """Only smaller native headers/page numbers may lie between body and edge."""
    for other in page.lines:
        if other is line or not other.text.strip() or _margin(other,page,line.font_size):continue
        above=other.bbox[3]<=line.bbox[1] if not last else other.bbox[1]>=line.bbox[3]
        if above and max(line.bbox[0],other.bbox[0])<min(line.bbox[2],other.bbox[2]):return False
    for box in (*page.images,*page.tables,*page.graphics):
        # A masthead rule/barcode lives in the same known smaller-header margin.
        if box[3]<=page.height*.115 or box[1]>=page.height*.90:continue
        above=box[3]<=line.bbox[1] if not last else box[1]>=line.bbox[3]
        if above and max(line.bbox[0],box[0])<min(line.bbox[2],box[2]):return False
    return True

def _column_start(line,eligible):
    """Other native body rows establish the column's unindented left edge."""
    peers=[other for other in eligible.values() if other is not line
           and other.page_number==line.page_number
           and abs(other.font_size-line.font_size)<=line.font_size*.05
           and other.bbox[2]-other.bbox[0]>=other.page_width*.35
           and min(other.bbox[2],line.bbox[2])-max(other.bbox[0],line.bbox[0])
               >=min(other.bbox[2]-other.bbox[0],line.bbox[2]-line.bbox[0])*.7]
    return min((other.bbox[0] for other in peers),default=None)

def recover_cross_page_typed_references(index,layout_objects=(),*,eligible_lines=None,evidence=None):
    """Repair proven page-edge fragments in-place and preserve all other refs.

    Can also run after reference identity repair, whose independent native-line
    parser may otherwise reintroduce the same incomplete prefix. No source
    document fields are replaced or mutated.
    """
    document=index.document;pages={p.number:p for p in document.pages}
    candidates=list(eligible_lines) if eligible_lines is not None else [(l,'body') for l in document.lines]
    candidates_with_prefix=[l for l,scope in candidates if l.page_number+1 in pages
                            and l.bbox[1]>=l.page_height*.80 and _DANGLING.search(normalize_text(l.text))]
    if not candidates_with_prefix:
        index.cross_page_typed_reference_evidence=[]
        return index
    from .caption_context import caption_region_lines,contextual_caption
    from .reference_identity_repair import _scope_map
    directories=toc_line_keys(document)
    scopes,nonbody=_scope_map(document,directories)
    excluded=set(directories)|set(nonbody)|caption_region_lines(document,layout_objects)
    eligible={_key(l):l for l,scope in candidates if scope!='_nonbody'
              and _body_ink(l,pages[l.page_number],excluded)
              and not contextual_caption(l,pages[l.page_number],'figure',layout_objects)
              and not contextual_caption(l,pages[l.page_number],'table',layout_objects)}
    events=[]
    for a in candidates_with_prefix:
        if _key(a) not in eligible:continue
        text=normalize_text(a.text);m=_DANGLING.search(text)
        p=pages[a.page_number];next_page=pages.get(a.page_number+1)
        if not m or next_page is None or a.bbox[1]<p.height*.80 or not _clear_edge(a,p,True):continue
        starts=[b for b in next_page.lines if _key(b) in eligible and b.bbox[1]<=next_page.height*.22
                and _CONTINUED.match(normalize_text(b.text))]
        for b in starts:
            tail=normalize_text(b.text);n=_CONTINUED.match(tail)
            first_column=_column_start(a,eligible);second_column=_column_start(b,eligible)
            if (abs(a.font_size-b.font_size)>a.font_size*.05
                    or abs(p.width-next_page.width)>p.width*.01 or abs(p.height-next_page.height)>p.height*.01
                    or a.bbox[2]-a.bbox[0]<p.width*.35
                    or abs(a.bbox[0]-b.bbox[0])>a.font_size*1.5
                    or abs(a.bbox[2]-b.bbox[2])>a.font_size*1.5
                    or first_column is None or second_column is None
                    or abs(a.bbox[0]-first_column)>a.font_size*.5
                    or abs(b.bbox[0]-second_column)>b.font_size*.5
                    or scopes.get(_key(a),'body')!=scopes.get(_key(b),'body')
                    or not _clear_edge(b,next_page,False)):continue
            first=_glyph_span(a,m.start('prefix'),m.end('separator'))
            second=_glyph_span(b,n.start('number'),n.end('number'))
            if first is None or second is None:continue
            is_table=m.group('kind').lower().startswith(('表','table'))
            pattern=TABLE_REFERENCE if is_table else FIGURE_REFERENCE
            combined=text+tail.lstrip();match=pattern.match(combined,m.start())
            expected=_num(m.group('prefix')+m.group('separator')+n.group('number'))
            if not match or _num(match.group('number'))!=expected or not local_reference(combined,match):continue
            prefix=text[max(0,m.start()-16):m.start()];qualifier=APPENDIX_QUALIFIER.search(prefix)
            scope=scopes.get(_key(a),'body')
            target_scope=normalize_label(qualifier.group('number')) if qualifier else (expected[0] if re.match(r'^[A-Z]\.',expected) else None)
            restored=replace(a,text=combined,bbox=first,
                reference_regions=((match.start('number'),match.end('number'),first),))
            label=Label(expected,restored,scope,target_scope)
            refs=index.table_refs if is_table else index.figure_refs
            stale=[r for r in refs if r.number==_num(m.group('prefix')) and r.line.page_number==a.page_number
                   and _overlap(r.line.bbox,first) and (old:=_DANGLING.search(normalize_text(r.line.text)))
                   and _num(old.group('prefix'))==_num(m.group('prefix'))]
            position=min((refs.index(r) for r in stale),default=len(refs))
            for r in stale:refs.remove(r)
            if not any(r.number==label.number and r.scope==label.scope and r.target_scope==label.target_scope
                       and r.line.page_number==a.page_number and r.line.bbox==first for r in refs):refs.insert(position,label)
            events.append({'action':'restore_cross_page_typed_number','kind':'table' if is_table else 'figure',
                'number':expected,'scope':scope,'target_scope':target_scope,'first_line':asdict(a),'continuation_line':asdict(b),
                'first_number_glyph_bbox':first,'continuation_number_glyph_bbox':second,
                'removed_prefix_references':[asdict(r) for r in stale],
                'criterion':'原生正文页末类型词及未完编号、相邻页首编号与引用尾词、同列字号、两端真实字框且无间隔正文或图题'})
            break
    index.cross_page_typed_reference_evidence=events
    if evidence is not None:evidence.extend(events)
    return index
