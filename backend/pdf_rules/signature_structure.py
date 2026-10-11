"""Read scanned signing structures in the PDF's displayed orientation.

Proof requires actual administrative text, ordered committee columns and
positive signature ink. Ink outside those exact regions remains unproved.
"""
from dataclasses import replace
from functools import lru_cache
from time import monotonic
import re
import pymupdf
from .model import PdfLine
from .numbering import normalize_text,FIGURE_REFERENCE,TABLE_REFERENCE,APPENDIX_REFERENCE,FIGURE_CAPTION,TABLE_CAPTION
from .local_ocr import _read_tile,signature_remainder_view

REFERENCES=(FIGURE_REFERENCE,TABLE_REFERENCE,APPENDIX_REFERENCE)
def compact(value):return normalize_text(value).replace(' ','')

@lru_cache(maxsize=24)
def _display_read(path,number,stamp,size):
    import numpy as np
    with pymupdf.open(path) as pdf:
        page=pdf[number-1]
        scale=min(2,2400/max(page.rect.width,page.rect.height))
        pix=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),colorspace=pymupdf.csGRAY,alpha=False)
        inverse=page.derotation_matrix
        transform=tuple(inverse)
    gray=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width).copy()
    hits=tuple(replace(h,bbox=tuple(v/scale for v in h.bbox)) for h in _read_tile(gray))
    return gray,scale,hits,transform

def display_read(document,page,deadline):
    if monotonic()>=deadline:raise TimeoutError('Signing structure OCR time limit reached')
    stat=document.path.stat()
    return _display_read(str(document.path),page.number,stat.st_mtime_ns,stat.st_size)

def _research(lines):
    from .layout_context import CHAPTER
    return any(CHAPTER.match(normalize_text(l.text).strip())
        or FIGURE_CAPTION.match(normalize_text(l.text).strip())
        or TABLE_CAPTION.match(normalize_text(l.text).strip())
        or any(rx.search(compact(l.text)) for rx in REFERENCES) for l in lines)

def _outside_ink(gray,scale,regions):
    # Reuse the established pale-glyph, textured-paper and graphic guards.
    # A decoded administrative form never licenses lowering their contrast
    # thresholds or treating arbitrary page-edge text as scan background.
    _,guards,artifacts=signature_remainder_view(gray,scale,regions,display_rotation=0)
    return guards,artifacts

def _declaration_regions(hits,width,height):
    from .page_policy import _title
    from .model import PdfPage
    readable=[h for h in hits if h.text.strip() and h.score>=.85]
    page=PdfPage(1,width,height,tuple(PdfLine(1,h.text,h.bbox,width,height) for h in readable))
    text=''.join(compact(h.text) for h in sorted(readable,key=lambda h:(h.bbox[1],h.bbox[0])))
    if _research(page.lines):return []
    titles=[h for h in readable if _title(PdfLine(1,h.text,h.bbox,width,height))]
    legal=('本人郑重声明' in text and '学位论文' in text and '法律' in text)
    authorization=('本学位论文作者' in text and '学校' in text and '保留' in text and '查阅' in text and '借阅' in text)
    signatures=[h for h in readable if '签名' in compact(h.text) or '签字' in compact(h.text)]
    if not titles or not (legal or authorization) or not signatures or '日期' not in text:return []
    # A legal paragraph followed by a signature field is a block, not a
    # license to erase a separate technical paragraph or a plotted object.
    allowed=('上海交通大学','学位论文','本人','所取得','究工作','个人或集体','和集体','经发表','以明确','承担',
             '向国家','允许论文','公开论文','内部论文','秘密论文','机密论文','解密后','保密','请在','日期','指导教师','年','月','日')
    for h in readable:
        t=compact(h.text)
        if h.bbox[3]<height*.065 and re.fullmatch(r'[\d\s-]{1,24}',t):continue
        if not any(v in t for v in allowed) and not any(abs(h.bbox[1]-s.bbox[1])<35 and h.bbox[0]>=s.bbox[0] for s in signatures):return []
    regions=[(h.bbox[0]-3,h.bbox[1]-3,h.bbox[2]+3,h.bbox[3]+3) for h in readable]
    for h in signatures:
        # Only the printed field's same baseline is allowed to own handwriting.
        regions.append((h.bbox[0]-4,h.bbox[1]-22,min(width*.95,h.bbox[2]+115),h.bbox[3]+24))
    return regions

def _roster_regions(previous_hits,hits,width,height,gray,scale):
    previous=[h for h in previous_hits if h.score>=.9 and h.bbox[1]>height*.5]
    headers=[]
    for word in ('答辩委员会','姓名','职称','工作单位','签名'):
        found=[h for h in previous if compact(h.text)==word]
        if len(found)!=1:return []
        headers.append(found[0])
    centers=[(h.bbox[0]+h.bbox[2])/2 for h in headers]
    if any(z-x<width*.07 for x,z in zip(centers,centers[1:])):return []
    if max(h.bbox[1] for h in headers)-min(h.bbox[1] for h in headers)>30:return []
    labels=sorted([h for h in hits if h.score>=.9 and compact(h.text) in {'主席','委员','秘书'}],key=lambda h:h.bbox[1])
    if not labels or '秘书' not in {compact(h.text) for h in labels}:return []
    if any(abs((h.bbox[0]+h.bbox[2])/2-centers[0])>width*.04 for h in labels):return []
    if labels[-1].bbox[3]>height*.38:return []
    # Names, positions, and institutions must occupy the same ordered columns
    # as the form heading. Printed prose cannot borrow a committee keyword.
    regions=[]
    left=max(0,centers[0]-(centers[1]-centers[0])*.65)
    right=min(width*.95,centers[4]+(centers[4]-centers[3])*.65)
    for index,label in enumerate(labels):
        middle=(label.bbox[1]+label.bbox[3])/2
        top=max(height*.06,middle-45 if index==0 else ((labels[index-1].bbox[1]+labels[index-1].bbox[3])/2+middle)/2)
        bottom=min(height*.4,middle+45 if index==len(labels)-1 else (middle+(labels[index+1].bbox[1]+labels[index+1].bbox[3])/2)/2)
        row=[h for h in hits if h.text.strip() and top-3<=(h.bbox[1]+h.bbox[3])/2<=bottom+3]
        names=[h for h in row if h.score>=.9 and abs((h.bbox[0]+h.bbox[2])/2-centers[1])<width*.04 and re.fullmatch(r'[\u4e00-\u9fff]{2,12}',compact(h.text))]
        institutions=[h for h in row if h.score>=.85 and abs((h.bbox[0]+h.bbox[2])/2-centers[3])<width*.075]
        if len(names)!=1 or not any(re.search('大学|学院|研究所|研究院|实验室|公司|中心|集团',compact(h.text)) for h in institutions):return []
        if compact(label.text)!='秘书' and not any(h.score>=.9 and abs((h.bbox[0]+h.bbox[2])/2-centers[2])<width*.04 and re.fullmatch(r'(?:副?教授|副?研究员|(?:正)?高级工程师|讲师)',compact(h.text)) for h in row):return []
        for h in row:
            x=(h.bbox[0]+h.bbox[2])/2
            if h.score>=.85 and x<centers[4]-width*.05 and h not in names and h not in institutions and h!=label and not abs(x-centers[2])<width*.04:return []
        # A nonempty ink island in the signature column must be more than
        # straight table borders. Handwriting need not be OCR-readable.
        import cv2,numpy as np
        a=int((centers[4]-width*.04)*scale);z=int(right*scale)
        b=int(top*scale);d=int(bottom*scale)
        ink=(gray[b:d,a:z]<180).astype('uint8')
        if not ink.size:return []
        lines=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((1,max(3,round(15*scale))),dtype='uint8'))
        lines|=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((max(3,round(15*scale)),1),dtype='uint8'))
        if np.count_nonzero(ink & (1-lines))<20*scale*scale:return []
        regions.append((left,top,right,bottom))
    # These intervals meet at the observed row midlines. Their union owns
    # only the same continuously proved rows and also contains handwriting
    # and parser table envelopes crossing an internal row boundary.
    return [(left,regions[0][1],right,regions[-1][3])]

def recover_structure(document,previous,page,deadline):
    """Return original OCR observations and a narrowly proved signing region."""
    if _research(page.lines):return None
    from .signature_ocr import _form_context
    gray,scale,hits,transform=display_read(document,page,deadline)
    height,width=gray.shape[0]/scale,gray.shape[1]/scale
    regions=_declaration_regions(hits,width,height);kind='declaration';prior=()
    if not regions and previous is not None and previous.number+1==page.number and _form_context(previous):
        if not any(l.role in {'table','table_body'} and re.search(r'委员|秘书|主席',compact(l.text)) for l in page.lines):return None
        _,_,prior,_=display_read(document,previous,deadline)
        regions=_roster_regions(prior,hits,width,height,gray,scale);kind='committee_continuation'
    if not regions:return None
    regions=regions+[(h.bbox[0]-2,h.bbox[1]-2,h.bbox[2]+2,h.bbox[3]+2) for h in hits
        if h.score>=.9 and h.bbox[3]<height*.065 and re.fullmatch(r'[\d\s-]{6,24}',h.text.strip())]
    guards,artifacts=_outside_ink(gray,scale,regions)
    # A full-page text proposal outside the proved rows is independent
    # content even if the paper-background classifier calls its pixels weak.
    from .page_policy import _inside
    class _TextGuard(tuple):pass
    guards.extend(_TextGuard(h.bbox) for h in hits if (h.text.strip() or h.detection_score>=.8)
        and not any(_inside(h.bbox,b,3) for b in regions))
    # Keep coherent visible ink in the residual view, including a vector or
    # raster plot that a text-only proposal stage cannot read.
    import cv2,numpy as np
    residual=(gray<=225).astype('uint8')
    for x1,y1,x2,y2 in regions:
        a=max(0,int(x1*scale));b=max(0,int(y1*scale));c=min(gray.shape[1],int(x2*scale)+1);d=min(gray.shape[0],int(y2*scale)+1)
        residual[b:d,a:c]=0
    _,_,components,_=cv2.connectedComponentsWithStats(residual,8)
    # This adds guards; it never removes any existing faint-content guard.
    class _VisibleInkGuard(tuple):pass
    for x,y,w,h,area in components[1:]:
        if area>=4*scale*scale and w>=scale and h>=scale:
            box=(float(x/scale),float(y/scale),float((x+w)/scale),float((y+h)/scale))
            if not any(_inside(box,b,3) for b in regions):guards.append(_VisibleInkGuard(box))
    from .signature_source_artifacts import source_artifacts
    guards,source_proofs=source_artifacts(document,page,regions,guards)
    artifacts.extend(source_proofs)
    # An ordered, signed roster establishes the page type. Its printed
    # columns also establish the writing span. Weak source proposals beyond
    # that span remain observations of its margin; they are not independent
    # body content. Read text, visible ink, graphics and separate PDF layers
    # retain their veto and cannot inherit administrative ownership.
    margin_observations=[]
    if kind=='committee_continuation' and guards:
        left=min(b[0] for b in regions);right=max(b[2] for b in regions)
        if all(type(b).__name__ not in {'_TextGuard','_VisibleInkGuard','_GraphicGuard','_IndependentInkGuard'}
               and (b[2]<left or b[0]>right) for b in guards):
            margin_observations=[list(b) for b in guards];guards=[]
    record={'page':page.number,'method':'displayed_signature_structure_cpu_ocr','display_rotation':page.display_rotation,
            'kind':kind,'administrative_display_regions':[list(b) for b in regions],
            'observations':[{'text':h.text,'score':h.score,'bbox':list(h.bbox),'detection_score':h.detection_score} for h in hits],
            'previous_page':previous.number if kind=='committee_continuation' else None,
            'previous_header_observations':[{'text':h.text,'score':h.score,'bbox':list(h.bbox)} for h in prior
                if h.score>=.9 and compact(h.text) in {'答辩委员会','工作职务','姓名','职称','工作单位','签名'}],
            'outside_ink':[list(b) for b in guards],'scan_artifacts':artifacts,
            'page_type_margin_observations':margin_observations}
    if guards:
        record['status']='unproved_outside_ink';return None,record
    inverse=pymupdf.Matrix(*transform)
    canonical=[tuple(pymupdf.Rect(b)*inverse) for b in regions]
    lines=[PdfLine(page.number,h.text,tuple(pymupdf.Rect(h.bbox)*inverse),page.width,page.height,
                   source='signature_structure_cpu',role='signature_structure_text') for h in hits if h.text.strip()]
    # The marker carries the proved geometry and observed text, not a page ID.
    for b in canonical:
        lines.append(PdfLine(page.number,' '.join(h.text for h in hits if h.text.strip()),b,page.width,page.height,
                     source='signature_structure_cpu',role='signature_verified_'+kind))
    record.update(status='proved_signature_structure',administrative_regions=[list(b) for b in canonical])
    return replace(page,lines=page.lines+tuple(lines)),record
