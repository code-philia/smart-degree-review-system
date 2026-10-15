"""Bind bare alphanumeric panel citations to source-painted row namespaces.

Only a candidate bare panel reference starts pixel recognition. The cache holds
original OCR observations, keyed by exact PDF content and physical crop, never
an exclusion or a repaired detector decision.
"""
from dataclasses import replace
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import re
from .numbering import normalize_text,normalize_label

_PANEL=re.compile(r'[A-Z][0-9]+')
_ROWS=re.compile(r'第[一二三四五六七八九十0-9]+行\s*[(（]\s*图\s*'
                 r'(?P<parent>[0-9]+(?:\s*[.\-]\s*[0-9]+)*)\s*'
                 r'(?P<letter>[A-Z])\s*(?P<first>[0-9]+)\s*[-—–至到]\s*'
                 r'(?P=letter)\s*(?P<last>[0-9]+)\s*[)）]')

@lru_cache(maxsize=256)
def _painted_labels(path,digest,page_number,box,scale=4):
    import pymupdf,numpy as np
    from .local_ocr import _read_tile
    # A source may change between stat/hash and rendering. Never retain an
    # observation under a digest that does not identify the bytes actually read.
    if sha256(Path(path).read_bytes()).hexdigest()!=digest:return ()
    with pymupdf.open(path) as source:
        page=source[page_number-1];page.set_rotation(0)
        pix=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),clip=pymupdf.Rect(box),
                            colorspace=pymupdf.csGRAY,alpha=False)
        gray=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width)
    return tuple((normalize_text(h.text).strip(),h.score,h.detection_score,
                  tuple((v+(pix.x if i%2==0 else pix.y))/scale for i,v in enumerate(h.bbox)))
                 for h in _read_tile(gray))

def _row_namespaces(document,page,reference):
    # Original native body wraps establish the row declaration. The source
    # marker proof below remains mandatory even when the prose says A1 exists.
    from .usage_paragraphs import usage_paragraphs
    paragraphs=[l for l,_ in usage_paragraphs([(l,'panel') for l in page.lines if l.source=='native'],document)]
    candidates=[l for l in paragraphs if normalize_text(l.text)==normalize_text(reference.line.text)
                and l.bbox[0]<=reference.line.bbox[0] and l.bbox[1]<=reference.line.bbox[1]
                and reference.line.bbox[2]<=l.bbox[2] and reference.line.bbox[3]<=l.bbox[3]]
    if len(candidates)!=1:return []
    candidate=candidates[0]
    bare=re.search(r'(?:图|Figures?|Figs?\.?)\s*'+re.escape(reference.number)+r'(?![A-Za-z0-9])',
                   normalize_text(candidate.text),re.I)
    if not bare:return []
    context=normalize_text(candidate.text)[:bare.start()]
    declaration=candidate
    if not _ROWS.search(context):
        preceding=[l for l in paragraphs if l is not candidate and l.bbox[3]<=candidate.bbox[1]]
        if not preceding:return []
        declaration=max(preceding,key=lambda l:l.bbox[3])
        # A row explanation owns only its directly adjacent native paragraph.
        # Typography, column and physical barriers constrain that continuity;
        # neither a distant declaration nor a later appendix can inherit it.
        size=candidate.font_size
        if (not size or not declaration.font_size or candidate.bold or declaration.bold
                or candidate.direction!=declaration.direction or candidate.direction!=(1.0,0.0)
                or abs(size-declaration.font_size)>size*.05
                or not 0<=candidate.bbox[1]-declaration.bbox[3]<=size*1.5):return []
        overlap=min(candidate.bbox[2],declaration.bbox[2])-max(candidate.bbox[0],declaration.bbox[0])
        if overlap<min(candidate.bbox[2]-candidate.bbox[0],declaration.bbox[2]-declaration.bbox[0])*.75:return []
        from .usage_paragraphs import _intervening_content
        if _intervening_content(declaration,candidate,page):return []
        context=normalize_text(declaration.text)
    groups={}
    for m in _ROWS.finditer(context):
        first,last=int(m.group('first')),int(m.group('last'))
        if not 1<=first<last or last-first>11:continue
        parent=normalize_label(re.sub(r'\s+','',m.group('parent')))
        row=(m.group('letter'),tuple(f'{m.group("letter")}{n}' for n in range(first,last+1)))
        groups.setdefault(parent,[]).append(row)
    return [(parent,rows,declaration.bbox,candidate.bbox) for parent,rows in groups.items()
            if len(rows)>=2 and len({letter for letter,_ in rows})==len(rows)
            and reference.number in {n for _,numbers in rows for n in numbers}]

def _grid_markers(observations,rows,box):
    wanted={n for _,numbers in rows for n in numbers}
    found={}
    for text,score,detection,rect in observations:
        if not _PANEL.fullmatch(text) or score<.98 or detection<.5:continue
        if not (box[0]<=rect[0]<rect[2]<=box[2] and box[1]<=rect[1]<rect[3]<=box[3]):continue
        if text in found:return None
        found[text]=rect
    if set(found)!=wanted:return None
    geometry=[]
    for letter,numbers in rows:
        rects=[found[n] for n in numbers]
        heights=[r[3]-r[1] for r in rects]
        centres=[((r[0]+r[2])/2,(r[1]+r[3])/2) for r in rects]
        if max(y for _,y in centres)-min(y for _,y in centres)>max(heights)*1.5:return None
        if any(a[0]>=b[0] for a,b in zip(centres,centres[1:])):return None
        if centres[-1][0]-centres[0][0]<(box[2]-box[0])*.25:return None
        geometry.append((centres,max(heights)))
    for (a,ha),(b,hb) in zip(geometry,geometry[1:]):
        if min(y for _,y in b)-max(y for _,y in a)<max(ha,hb)*2:return None
        if len(a)==len(b) and any(abs(x-z)>(box[2]-box[0])*.08 for (x,_),(z,_) in zip(a,b)):return None
    return tuple((n,found[n]) for _,numbers in rows for n in numbers)

def _physical_parents(index,page,reference,declaration_bbox):
    owners={}
    for target in index.figures:
        if target.line.page_number!=page.number or target.scope!=reference.scope:continue
        caption=target.line
        height=max(1,caption.bbox[3]-caption.bbox[1])
        for box in page.images:
            if box[2]-box[0]<page.width*.18 or box[3]-box[1]<height*3:continue
            if not 0<=caption.bbox[1]-box[3]<=height*3:continue
            if abs((box[0]+box[2]-caption.bbox[0]-caption.bbox[2])/2)>(box[2]-box[0])*.15:continue
            if box[3]>reference.line.bbox[1] or caption.bbox[3]>reference.line.bbox[1]:continue
            if caption.bbox[3]>declaration_bbox[1]:continue
            # A different independent title inside the raster or its title gap
            # defeats the claim that it is one shared physical parent.
            if any(t is not target and t.number!=target.number and t.line.page_number==page.number
                   and box[1]<t.line.bbox[1]<caption.bbox[3]
                   and min(box[2],t.line.bbox[2])>max(box[0],t.line.bbox[0]) for t in index.figures):continue
            owners[(box,target.number,target.scope)]=target
    return owners

def bind_source_panel_references(index,layout_objects=()):
    candidates=[r for r in index.figure_refs if _PANEL.fullmatch(r.number) and r.target_scope is None]
    index.r11_panel_reference_evidence=[]
    if not candidates:return index
    pages={p.number:p for p in index.document.pages}
    path=Path(index.document.path)
    if not path.is_file():return index
    digest=None
    for reference in candidates:
        # An independently titled literal A1 remains that real figure identity.
        if any(t.number==reference.number and t.scope==reference.scope for t in index.figures):continue
        page=pages[reference.line.page_number]
        groups=_row_namespaces(index.document,page,reference)
        if len(groups)!=1:continue
        literal_parent,rows,declaration_bbox,candidate_bbox=groups[0]
        owners=_physical_parents(index,page,reference,declaration_bbox)
        if len(owners)!=1:continue
        (box,number,scope),target=next(iter(owners.items()))
        if page.display_rotation:continue
        if digest is None:digest=sha256(path.read_bytes()).hexdigest()
        try:markers=_grid_markers(_painted_labels(str(path.resolve()),digest,page.number,box),rows,box)
        except Exception:markers=None
        if markers is None:continue
        replacement=replace(reference,number=target.number,target_scope=target.scope)
        position=next(i for i,r in enumerate(index.figure_refs) if r is reference)
        index.figure_refs[position]=replacement
        index.r11_panel_reference_evidence.append(dict(
            original_number=reference.number,parent_number=number,parent_scope=scope,
            page=page.number,reference_bbox=reference.line.bbox,physical_parent_bbox=box,
            parent_caption_bbox=target.line.bbox,literal_row_parent=literal_parent,
            declaration_bbox=declaration_bbox,candidate_paragraph_bbox=candidate_bbox,
            source_pdf_sha256=digest,markers=markers,
            criterion='complete source-painted labels in distinct aligned declared rows; unique physical parent caption; same or directly adjacent native paragraph'))
    return index
