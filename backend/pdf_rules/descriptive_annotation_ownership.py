"""Caption ownership for native annotations naming complete source rows."""
from dataclasses import replace
from pathlib import Path
import re

from .figure_identity_repair import _inside,_union,_join,_xover
from .caption_physical_ownership import _PageInk
from .source_native_caption_ownership import _owners,_source_labels,_combined_mask,_native,_canonical_tags,_declared
from .descriptive_caption_ownership import _declared_lines
from .mineru_layout import caption_identity
from .numbering import normalize_text
from .caption_rules import detect_caption_rules


def _row_namespace(group,owners,labels,title,ink):
    """A centered source annotation names a complete horizontal panel row."""
    if len(owners)!=1 or owners[0]['kind']!='form':return False
    owner=owners[0];box=owner['box'];tags=_canonical_tags(labels)
    tags.sort(key=lambda t:t[1].bbox[1]);letters=[t for t,l in tags]
    if not (len(letters)>=2 and letters==[chr(97+i) for i in range(len(letters))]
            and set(letters)==_declared(title)):return False
    top=box[1]
    for letter,line in tags:
        b=line.bbox
        # A row marker is small and centered on the full physical Form. A tag
        # attached to one corner of an independently observed chart cannot
        # lend that chart's title to an unlabelled neighbour.
        if not (b[2]-b[0]<=(box[2]-box[0])*.2
                and abs((b[0]+b[2]-box[0]-box[2])/2)<=max(18,(box[2]-box[0])*.07)
                and b[1]-top>=(b[3]-b[1])*1.5):return False
        x0,y0,x1,y1=[int(round(v*2)) for v in (box[0],top,box[2],b[1])]
        mask=owner['mask'][max(0,y0):min(ink.height,y1),max(0,x0):min(ink.width,x1)]
        yy,xx=ink.np.where(mask)
        if (len(xx)<64 or float(xx.max()-xx.min())/2<(box[2]-box[0])*.6
                or float(yy.max()-yy.min())/2<(b[3]-b[1])*1.5):return False
        top=b[3]
    return abs(tags[-1][1].bbox[3]-box[3])<=25


def repair_descriptive_annotation_ownership(objects,document):
    result=list(objects)
    if document is None or not Path(document.path).is_file():return result
    pending={f['page'] for f in detect_caption_rules(result,[13],document)['13']['findings']}
    if not pending:return result
    import pymupdf
    with pymupdf.open(document.path) as source:
        for page in document.pages:
            if page.number not in pending or page.display_rotation or not 1<=page.number<=len(source):continue
            caps=[o for o in result if o.kind=='figure_caption' and o.page_number==page.number]
            ink=None
            try:
                for cap in caps:
                    lines=_declared_lines(cap,page)
                    if not lines:continue
                    preceding=max((c.bbox[3] for c in caps if c is not cap and c.bbox[3]<cap.bbox[1]),default=page.height*.08)
                    group=[o for o in result if o.kind=='figure' and o.page_number==page.number
                           and o.bbox[1]>=preceding and o.bbox[3]<=cap.bbox[3]+2 and _xover(o.bbox,cap.bbox)>.2]
                    if len(group)<2:continue
                    envelope=_union([o.bbox for o in group])
                    if any(c is not cap and _inside(c.bbox,envelope)>.5 for c in caps):continue
                    if any(re.search(r'[（(][a-z]\d+[）)]',normalize_text(l.text),re.I)
                           and _inside(l.bbox,(envelope[0]-25,envelope[1]-25,envelope[2]+25,cap.bbox[3]))>.5 for l in page.lines):continue
                    if ink is None:ink=_PageInk(source,page.number)
                    if not ink.valid:continue
                    owners=_owners(group,cap,ink,False)
                    if not owners:continue
                    labels,_sequence=_source_labels(page,[],owners,group,False,ink)
                    title=' '.join(l.text for l in lines)
                    if not _row_namespace(group,owners,labels,title,ink):continue
                    mask=_combined_mask({n for w in owners for n in w['names']},labels+lines,ink)
                    if mask is None or not all(ink.owns(o,{'mask':mask}) for o in group):continue
                    if any((_native(l) or len(re.findall(r'[\u4e00-\u9fff]',l.text))>=18
                            or len(re.findall(r'[A-Za-z]{2,}',l.text))>=5) and _inside(l.bbox,envelope)>.8
                           and (not _native(l) or not ink.glyph_owned(l.bbox,{'mask':mask})) for l in page.lines):continue
                    joined=replace(_join(group,'figure'),role='source_native_annotation_owner',
                                   caption_owner_id=caption_identity(cap))
                    chosen={id(o) for o in group};result=[o for o in result if id(o) not in chosen]+[joined]
            except (ValueError,IndexError,RuntimeError):continue
            finally:
                if ink is not None:ink.close()
    return result
