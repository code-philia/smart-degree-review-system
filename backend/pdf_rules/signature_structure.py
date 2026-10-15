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

def _legal_text(value):
    return re.sub(r'[^A-Za-z0-9\u4e00-\u9fff]','',compact(value))

def _complete_legal_paragraphs(rows):
    """Validate full legal prose across OCR wraps, including its final clause."""
    value=''.join(_legal_text(h.text) for h in sorted(rows,key=lambda h:(h.bbox[1],h.bbox[0])))
    declaration=(r'本人郑重声明所呈交的学位论文是本人在导师的指导下独立进行研究工作所取得的成果'
        r'除文中已经注明引用的内容外本论文不包含任何其他个人或集体已经发表或撰写过的作品成果'
        r'对本文的研究做出重要贡献的个人和集体均已在文中以明确方式标明'
        r'本人完全(?:意识到|知晓)本声明的法律(?:结果|后果|责任)由本人承担')
    authorization=(r'(?:本学位论文作者完全了解学校有关保留使用学位论文的规定同意学校保留并|本人同意学校保留并)'
        r'向国家有关部门或机构送交论文的复印件和电子版允许论文被查阅和借阅'
        r'(?:本人授权上海交通大学可以将本学位论文的全部或部分内容编入有关数据库进行检索'
        r'可以采用影印缩印或扫描等复制手段保存和汇编本学位论文)?')
    return bool(re.fullmatch(rf'(?:{declaration})(?:{authorization})?|(?:{authorization})',value))

def _declaration_regions(hits,width,height,barcode_regions=(),gray=None,scale=1):
    from .page_policy import _title
    from .model import PdfPage
    readable=[h for h in hits if h.text.strip() and (h.score>=.85 or
        (h.score>=.7 and h.detection_score>=.55 and
         re.match(r'^(?:学位论文作者|指导教师)(?:签名|签字)',_legal_text(h.text))))]
    page=PdfPage(1,width,height,tuple(PdfLine(1,h.text,h.bbox,width,height) for h in readable))
    text=''.join(compact(h.text) for h in sorted(readable,key=lambda h:(h.bbox[1],h.bbox[0])))
    if _research(page.lines):return []
    titles=[h for h in readable if _title(PdfLine(1,h.text,h.bbox,width,height))]
    signatures=[h for h in readable if '签名' in compact(h.text) or '签字' in compact(h.text)]
    if not titles or not signatures or '日期' not in text:return []
    # A legal paragraph followed by a signature field is a block, not a
    # license to erase a separate technical paragraph or a plotted object.
    from .page_policy import _inside
    body=[]
    for h in readable:
        t=compact(h.text)
        plain=_legal_text(t)
        if any(_inside(h.bbox,b,1) for b in barcode_regions):continue
        if h in titles or plain=='上海交通大学':continue
        if re.match(r'^(?:学位论文作者|指导教师)?(?:签名|签字)',plain) or re.match(r'^日期[0-9年月日]+$',plain):continue
        if any(abs(h.bbox[1]-s.bbox[1])<35 and h.bbox[0]>=s.bbox[0]
               and h.bbox[2]<=s.bbox[2]+118 for s in signatures):continue
        if re.fullmatch(r'(?:本学位论文属于(?:公开论文)?|公开论文|(?:内部|秘密|机密)论文[0-9年月不超过保密解密后过期适用本授权书]*|'
                        r'(?:不?保密)(?:在)?[0-9年月日]*|年解密后适用本授权书|请在以上方框内(?:选择)?打)',plain):continue
        body.append(h)
    if not _complete_legal_paragraphs(body):return []
    regions=[(h.bbox[0]-3,h.bbox[1]-3,h.bbox[2]+3,h.bbox[3]+3) for h in readable]
    for h in signatures:
        # Only the printed field's same baseline is allowed to own handwriting.
        regions.append((h.bbox[0]-4,h.bbox[1]-22,min(width*.95,h.bbox[2]+115),h.bbox[3]+24))
    if gray is not None:
        regions.extend(_declaration_source_fields(readable,signatures,width,height,gray,scale))
    return regions

def _declaration_source_fields(readable,signatures,width,height,gray,scale):
    """Own measured ink islands in independently printed signing fields.

    Regions follow source components, not a larger signing-page halo. A blank
    expiry underline needs both exact confidentiality anchors on its baseline.
    Separate PDF layers/native research keep their later independent veto.
    """
    import cv2,numpy as np
    regions=[]
    def components(box,threshold=180):
        a=max(0,int(box[0]*scale));b=max(0,int(box[1]*scale))
        c=min(gray.shape[1],int(box[2]*scale)+1);d=min(gray.shape[0],int(box[3]*scale)+1)
        if c<=a or d<=b:return []
        ink=(gray[b:d,a:c]<threshold).astype('uint8')
        _,_,parts,_=cv2.connectedComponentsWithStats(ink,8)
        return [((a+x)/scale,(b+y)/scale,(a+x+w)/scale,(b+y+h)/scale,area/(scale*scale))
                for x,y,w,h,area in parts[1:]]
    for left in readable:
        if not re.fullmatch(r'保密(?:在)?',_legal_text(left.text)):continue
        for right in readable:
            if _legal_text(right.text)!='年解密后适用本授权书':continue
            if right.bbox[0]<=left.bbox[2] or abs(right.bbox[1]-left.bbox[1])>5:continue
            gap=right.bbox[0]-left.bbox[2]
            for x1,y1,x2,y2,area in components((left.bbox[2],min(left.bbox[1],right.bbox[1]),right.bbox[0],max(left.bbox[3],right.bbox[3])+2)):
                if x2-x1>=gap*.7 and y2-y1<=3 and area>=gap*.5:
                    regions.append((x1-1,y1-1,x2+1,y2+1))
    dates=[h for h in readable if re.match(r'^日期[0-9年月日]+$',_legal_text(h.text))]
    for field in signatures:
        below=[h for h in dates if 0<=h.bbox[1]-field.bbox[3]<=45
               and abs(h.bbox[0]-field.bbox[0])<width*.08]
        if len(below)!=1:continue
        date=below[0];font=max(10,min(22,date.bbox[3]-date.bbox[1]))
        box=(field.bbox[2]-3,field.bbox[1]-2*font,width*.95,date.bbox[1]+3)
        for x1,y1,x2,y2,area in components(box,225):
            if (x1>=field.bbox[2]-3 and y1<=field.bbox[3] and y2>=field.bbox[1]
                    and 5<=x2-x1<=width*.3 and font*.5<=y2-y1<=font*4 and area>=15):
                regions.append((x1-1,y1-1,x2+1,y2+1))
    for field in readable:
        if not re.fullmatch(r'本学位论文属于公开论文',_legal_text(field.text)):continue
        font=field.bbox[3]-field.bbox[1]
        for x1,y1,x2,y2,area in components((field.bbox[0],field.bbox[1]-2*font,field.bbox[2],field.bbox[3]+2)):
            if (y1<field.bbox[1]-3 and y2>=field.bbox[1]-1 and
                    font*.2<=x2-x1<=font*2 and font*.5<=y2-y1<=font*2 and area>=5):
                regions.append((x1-1,y1-1,x2+1,y2+1))
    return regions

def _declaration_field_read(hits,width,height,gray,scale,deadline):
    """Retry a missing printed adviser label only in a paired legal date row."""
    dates=[h for h in hits if h.score>=.9 and re.match(r'^日期[0-9年月日]+$',_legal_text(h.text))]
    authors=[h for h in hits if h.score>=.85 and _legal_text(h.text).startswith('学位论文作者签名')]
    extra=[];facts=[]
    for date in dates:
        same=[h for h in dates if h is not date and abs(h.bbox[1]-date.bbox[1])<=15
              and width*.25<=date.bbox[0]-h.bbox[0]<=width*.55]
        if len(same)!=1:continue
        left=same[0]
        author=[h for h in authors if abs(h.bbox[0]-left.bbox[0])<width*.08
                and 0<=left.bbox[1]-h.bbox[3]<=45]
        if len(author)!=1:continue
        if any(_legal_text(h.text).startswith('指导教师签名') and h.score>=.7 and
               abs(h.bbox[0]-date.bbox[0])<width*.08 and
               0<=date.bbox[1]-h.bbox[3]<=45 for h in hits):continue
        box=(max(0,date.bbox[0]-width*.025),max(0,min(author[0].bbox[1]-15,date.bbox[1]-60)),
             min(width*.95,date.bbox[2]+80),min(height,date.bbox[1]+5))
        a,b,c,d=[int(v*scale) for v in box]
        if monotonic()>=deadline:raise TimeoutError('Signing field OCR time limit reached')
        proposals=[replace(h,bbox=tuple(v/scale+(a/scale if i%2==0 else b/scale)
                           for i,v in enumerate(h.bbox))) for h in _read_tile(gray[b:d,a:c])]
        fields=[h for h in proposals if h.score>=.85 and _legal_text(h.text).startswith('指导教师签名')]
        if len(fields)==1:
            extra.extend(proposals);facts.append({'kind':'paired_author_date_missing_adviser_field',
                'source_crop':list(box),'printed_field_score':fields[0].score})
    return tuple(extra),facts

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

def _decision_schema(hits,width,height):
    """Complete printed decision fields; values may be separate same-row OCR."""
    from .page_policy import _title
    printed=[h for h in hits if h.score>=.9 and h.text.strip()]
    lines=[PdfLine(1,h.text,h.bbox,width,height) for h in printed]
    if _research(lines) or not any(_title(l) and '答辩' in compact(l.text)
                                  and l.bbox[1]<height*.2 for l in lines):return []
    def field(word):
        limit=height*(.6 if word=='评语和决议' else .35)
        if any(word in compact(h.text) and h.bbox[1]<limit for h in printed):return True
        # Vertical template labels can be separate OCR rows in the same cell.
        for h in printed:
            t=compact(h.text)
            if len(t)<2 or not word.startswith(t) or h.bbox[1]>=limit:continue
            for peer in printed:
                if compact(peer.text)!=word[len(t):]:continue
                overlap=min(h.bbox[2],peer.bbox[2])-max(h.bbox[0],peer.bbox[0])
                if (-5<=peer.bbox[1]-h.bbox[3]<=15 and overlap>=min(h.bbox[2]-h.bbox[0],peer.bbox[2]-peer.bbox[0])*.7):return True
        return False
    if not all(field(w) for w in ('姓名','学号','所在学科','指导教师','答辩日期','答辩地点','论文题目',
                                  '投票表决结果','同意票数','实到委员数','应到委员数','答辩结论','评语和决议')):return []
    vote=[h for h in printed if '投票表决结果' in compact(h.text)]
    triplet=re.compile(r'\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{1,2}')
    def vote_value(label):
        if triplet.search(normalize_text(label.text)):return True
        middle=(label.bbox[1]+label.bbox[3])/2
        return any(triplet.search(normalize_text(h.text)) and h.bbox[0]>=label.bbox[2]-5
                   and h.bbox[2]<=width*.93 and abs((h.bbox[1]+h.bbox[3])/2-middle)<=8
                   for h in printed)
    if not any(vote_value(h) for h in vote):return []
    if not any(re.search(r'答[辩辨]委员会',compact(h.text)) for h in printed):return []
    return printed

def _decision_regions(hits,width,height,gray,scale,details=None):
    """Prove a complete decision grid, voting fields and signed committee.

    Handwritten review prose need not be transcribed correctly. Its ownership
    comes from the independently observed complete printed form and source
    grid, not an OCR guess at its scientific discussion or verdict wording.
    """
    from .page_policy import _title
    import cv2,numpy as np
    printed=_decision_schema(hits,width,height)
    if not printed:return []
    dark=(gray<180).astype('uint8')
    horizontal=cv2.morphologyEx(dark,cv2.MORPH_OPEN,np.ones((1,max(3,round(35*scale))),dtype='uint8'))
    vertical=cv2.morphologyEx(dark,cv2.MORPH_OPEN,np.ones((max(3,round(35*scale)),1),dtype='uint8'))
    grid=cv2.morphologyEx(horizontal|vertical,cv2.MORPH_CLOSE,np.ones((max(3,round(2*scale)),)*2,dtype='uint8'))
    _,_,parts,_=cv2.connectedComponentsWithStats(grid,8)
    frames=[(x/scale,y/scale,(x+w)/scale,(y+h)/scale) for x,y,w,h,area in parts[1:]
            if w>=width*.7*scale and h>=45*scale and y>=height*.07*scale
            and y+h<=height*.96*scale]
    headers=[]
    for name in [h for h in printed if compact(h.text)=='姓名' and h.bbox[1]>height*.4]:
        row=[]
        for aliases in ({'工作职务','职务'},{'姓名'},{'职称'},{'工作单位','单位'},{'签名'}):
            candidates=[h for h in printed if compact(h.text) in aliases and abs(h.bbox[1]-name.bbox[1])<20]
            if len(candidates)!=1:break
            row.append(candidates[0])
        if len(row)==5:headers.append(row)
    if len(headers)!=1:return []
    header=headers[0];centers=[(h.bbox[0]+h.bbox[2])/2 for h in header]
    if any(b-a<width*.055 for a,b in zip(centers,centers[1:])):return []
    labels=sorted([h for h in printed if compact(h.text) in {'主席','委员','秘书'}
                   and h.bbox[1]>max(p.bbox[1] for p in header)
                   and abs((h.bbox[0]+h.bbox[2])/2-centers[0])<width*.045],key=lambda h:h.bbox[1])
    if (len(labels)<5 or compact(labels[0].text)!='主席' or compact(labels[-1].text)!='秘书'
            or sum(compact(h.text)=='委员' for h in labels)<3):return []
    from .page_policy import _inside
    footers=[b for b in frames if all(_inside(h.bbox,b,3) for h in header+labels)]
    if len(footers)!=1:return []
    frame=footers[0]
    regions=[(frame[0]-2,frame[1]-2,frame[2]+2,frame[3]+2)]
    if frame[1]>height*.25 or frame[3]-frame[1]<height*.5:return []
    signed=[]
    for i,label in enumerate(labels):
        middle=(label.bbox[1]+label.bbox[3])/2
        top=max(h.bbox[3] for h in header) if i==0 else (labels[i-1].bbox[3]+label.bbox[1])/2
        bottom=frame[3] if i+1==len(labels) else (label.bbox[3]+labels[i+1].bbox[1])/2
        row=[h for h in printed if top-3<=(h.bbox[1]+h.bbox[3])/2<=bottom+3]
        def at_column(h,column,tolerance):return abs((h.bbox[0]+h.bbox[2])/2-centers[column])<width*tolerance
        if not any(at_column(h,1,.045) and re.fullmatch(r'[\u4e00-\u9fff]{2,12}',compact(h.text)) for h in row):return []
        if not any(at_column(h,3,.09) and re.search(r'大学|学院|研究所|研究院|实验室|公司|中心|集团|科学院',compact(h.text)) for h in row):return []
        if compact(label.text)!='秘书' and not any(at_column(h,2,.055) and re.search(r'教授|研究员|工程师|讲师',compact(h.text)) for h in row):return []
        left=(centers[3]+centers[4])/2
        a=max(0,int(left*scale));b=max(0,int(top*scale));c=min(gray.shape[1],int(frame[2]*scale));d=min(gray.shape[0],int(bottom*scale))
        ink=dark[b:d,a:c]
        if not ink.size:return []
        borders=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((1,max(3,round(15*scale))),dtype='uint8'))
        borders|=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((max(3,round(15*scale)),1),dtype='uint8'))
        signed.append(np.count_nonzero(ink & (1-borders))>=20*scale*scale)
    # A real decision sheet may have an unfilled committee signature cell.
    # It still needs the complete printed roster, chair ink and several actual
    # signed rows. Do not claim that a blank row was signed.
    if not signed[0] or sum(signed)<max(3,(len(signed)+1)//2):return []
    # Every printed header belongs inside the physically proved frame.
    if any(not (frame[0]-3<=h.bbox[0] and h.bbox[2]<=frame[2]+3
                and frame[1]-3<=h.bbox[1] and h.bbox[3]<=frame[3]+3) for h in header+labels):return []
    title=[h for h in printed if _title(PdfLine(1,h.text,h.bbox,width,height))]
    signatures=[h for h in hits if h.text.strip() and h.bbox[0]>=(centers[3]+centers[4])/2
                and h.bbox[2]<=frame[2]+10 and h.bbox[1]>=max(p.bbox[3] for p in header)
                and h.bbox[3]<=frame[3]+20]
    if details is not None:details.update(committee_rows=len(labels),signed_rows=int(sum(signed)),
                                        chair_has_signature_ink=True,source_grid_region=list(frame))
    return regions+[(h.bbox[0]-3,h.bbox[1]-3,h.bbox[2]+3,h.bbox[3]+3) for h in title+signatures]

def recover_structure(document,previous,page,deadline):
    """Return original OCR observations and a narrowly proved signing region."""
    if _research(page.lines):return None
    from .signature_ocr import _form_context
    gray,scale,hits,transform=display_read(document,page,deadline)
    height,width=gray.shape[0]/scale,gray.shape[1]/scale
    from .signature_source_artifacts import scan_barcode_regions
    barcodes=scan_barcode_regions(gray,scale,hits)
    regions=_declaration_regions(hits,width,height,barcodes,gray,scale);kind='declaration';prior=()
    field_reads=[]
    if regions:
        extra,field_reads=_declaration_field_read(hits,width,height,gray,scale,deadline)
        if extra:
            hits=hits+extra
            regions=_declaration_regions(hits,width,height,barcodes,gray,scale)
    decision_details={}
    if not regions:
        regions=_decision_regions(hits,width,height,gray,scale,decision_details);kind='decision'
    continuation_labels=[h for h in hits if h.score>=.9 and compact(h.text) in {'委员','秘书','主席'}
                         and h.bbox[1]<height*.38]
    source_continuation=(len(continuation_labels)>=3 and
                         any(compact(h.text)=='秘书' for h in continuation_labels))
    if not regions and previous is not None and previous.number+1==page.number and (_form_context(previous) or source_continuation):
        if not source_continuation and not any(l.role in {'table','table_body'} and re.search(r'委员|秘书|主席',compact(l.text)) for l in page.lines):return None
        _,_,prior,_=display_read(document,previous,deadline)
        # A source-only attempt still needs the preceding full decision schema;
        # an arbitrary preceding column-heading table is not a decision sheet.
        if source_continuation and not _form_context(previous) and not _decision_schema(prior,width,height):return None
        regions=_roster_regions(prior,hits,width,height,gray,scale);kind='committee_continuation'
    if not regions:return None
    regions=regions+barcodes
    guards,artifacts=_outside_ink(gray,scale,regions)
    # A full-page text proposal outside the proved rows is independent
    # content even if the paper-background classifier calls its pixels weak.
    from .page_policy import _inside
    class _TextGuard(tuple):pass
    guards.extend(_TextGuard(h.bbox) for h in hits if (h.text.strip() or h.detection_score>=.8)
        and not any(_inside(h.bbox,b,3) for b in regions))
    from .page_policy import _display_box
    observed=_legal_text(''.join(h.text for h in sorted(hits,key=lambda h:(h.bbox[1],h.bbox[0]))))
    # Independent native ink survives even if a raster OCR proposal misses
    # it or an overbroad form rectangle contains it. Parser guesses do not
    # have that authority over a source-native paragraph.
    guards.extend(_TextGuard(_display_box(page,l.bbox)) for l in page.lines
        if l.source=='native' and l.text.strip() and
        (not any(_inside(_display_box(page,l.bbox),b,3) for b in regions)
         or _legal_text(l.text) not in observed))
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
    guards,source_proofs=source_artifacts(document,page,regions,guards,observations=hits,
        decision_schema_proof=decision_details,display_sample_pitch=1/scale)
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
            'decision_schema_proof':decision_details if kind=='decision' else None,
            'source_field_reads':field_reads,
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
