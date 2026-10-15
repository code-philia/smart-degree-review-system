"""Assign native panel annotations and physical components one retained title.

PDF resources prove paint ownership; they do not, by themselves, prove figure
identity. A component sequence, original/reconstruction roles, or a native
declaration must independently establish the namespace. No detector is disabled.
"""
from dataclasses import replace
from pathlib import Path
import re

from .figure_identity_repair import _area, _inside, _union, _xover, _join
from .caption_physical_ownership import _PageInk, _do_spans, _native_caption, _native_caption_text
from .caption_rules import _matches, detect_caption_rules
from .numbering import FIGURE_CAPTION, normalize_text

_TAG=re.compile(r'^\s*[（(]\s*([a-z])\s*[）)]')
_SOURCE=re.compile(r'^mineru:[0-9a-f]{64}:\d+:para_blocks:\d+(?::blocks:\d+)?(?::lines:\d+)?$')


class _OriginalPageInk(_PageInk):
    """Retain document rendering resources when a page import changes paint."""
    def __init__(self,source,number,path):
        import pymupdf,numpy as np
        self.np=np;self.fit=pymupdf
        self.copy=pymupdf.open(stream=Path(path).read_bytes(),filetype='pdf')
        self.page=self.copy[number-1];self.scale=2;self.data=self.page.read_contents();self.spans=_do_spans(self.data)
        self.xref=self.copy.get_new_xref();self.copy.update_object(self.xref,'<<>>')
        self.copy.update_stream(self.xref,self.data);self.page.set_contents(self.xref)
        pix=self.page.get_pixmap(matrix=pymupdf.Matrix(2,2),colorspace=pymupdf.csGRAY,alpha=False)
        original=source[number-1].get_pixmap(matrix=pymupdf.Matrix(2,2),colorspace=pymupdf.csGRAY,alpha=False)
        self.valid=(pix.width,pix.height,pix.samples)==(original.width,original.height,original.samples)
        self.base=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width)
        self.height=pix.height;self.width=pix.width;self.cache={}


def _covered(line):
    covered={i for a,z,b in line.text_regions if 0<z-a<=3 and _area(b)>0 for i in range(a,z)}
    # Native extraction can emit a zero-width continuation for a single ff,
    # fi or fl glyph. Its anchor must coincide with the preceding real glyph.
    regions={a:b for a,z,b in line.text_regions if z-a==1}
    for i,c in enumerate(line.text):
        b=regions.get(i);previous=regions.get(i-1)
        if (i and b and previous and _area(b)==0 and b[3]>b[1] and _area(previous)>0
                and line.text[i-1:i+1] in ('ff','fi','fl')
                and abs(b[0]-previous[2])<.05 and abs(b[1]-previous[1])<.05
                and abs(b[3]-previous[3])<.05):covered.add(i)
    return covered


def _native(line):
    covered=_covered(line)
    return line.source=='native' and all(i in covered for i,c in enumerate(line.text) if c.strip())


def _namespace(objects,cap,page):
    sideways=cap.bbox[3]-cap.bbox[1]>3*(cap.bbox[2]-cap.bbox[0])
    captions=[o for o in objects if o.kind=='figure_caption' and o.page_number==page.number and o is not cap]
    # A bilingual title may have two adjacent source caption observations.
    other=[o for o in captions if not (o.parent_id and o.parent_id==cap.parent_id
        and abs(o.bbox[1]-cap.bbox[3])<20 and _xover(o.bbox,cap.bbox)>.5)]
    if sideways:
        group=[o for o in objects if o.kind=='figure' and o.page_number==page.number
               and o.bbox[0]<cap.bbox[0] and max(0,min(o.bbox[3],cap.bbox[3])-max(o.bbox[1],cap.bbox[1]))>0]
    else:
        low=max((o.bbox[3] for o in other if o.bbox[3]<cap.bbox[1]-20),default=page.height*.08)
        group=[o for o in objects if o.kind=='figure' and o.page_number==page.number
               and low-2<=o.bbox[1] and o.bbox[3]<=cap.bbox[1]+2 and _xover(o.bbox,cap.bbox)>0]
    return group,other,sideways


def _owners(group,cap,ink,sideways,page=None):
    envelope=_union([o.bbox for o in group]);out=[]
    names=[(name,'form') for x,name,p,b in ink.page.get_xobjects() if p==0]
    names += [(r[7],'raster') for r in ink.page.get_images(full=True) if r[9]==0]
    used={name for name,a,b in ink.spans};names=[r for r in names if r[0] in used]
    if len(names)>48:return []
    for name,kind in dict.fromkeys(names):
        owner=ink.removal({name})
        if owner is None or _area(owner['box'])<600:continue
        b=owner['box']
        bound=(envelope[0]-20,envelope[1]-20,
               cap.bbox[0]+2 if sideways else envelope[2]+20,
               envelope[3]+20 if sideways else cap.bbox[1]+2)
        if _inside(b,bound)<.95:continue
        touched=0
        for obj in group:
            for r in obj.panel_boxes or (obj.bbox,):
                x0,y0,x1,y1=[int(round(v*2)) for v in r]
                touched+=int(owner['mask'][max(y0,0):min(y1,ink.height),max(x0,0):min(x1,ink.width)].sum())
        # A sideways parser crop can observe only the first chart. The next
        # source Forms still belong to the declared (a)/(b)/(c) namespace when
        # their own retained native panel TAGs actually paint beside the Forms.
        # Untagged neighbouring resources cannot expand this namespace.
        labelled=(sideways and page is not None and kind=='form' and any(_native(line)
                  and _TAG.match(normalize_text(line.text))
                  and _line_near(line,b,True) and _painted_panel_label(line,ink)
                  for line in page.lines))
        if touched>=64 or labelled:out.append(dict(owner,kind=kind))
    return out


def _painted_panel_label(line,ink):
    # These labels may be native page text beside an imported chart Form.
    # Only the TAG identifies a panel; long explanation text cannot replace
    # an absent or wrong letter. Import after module initialization because
    # the shared glyph audit itself uses this module's native-line predicate.
    from .native_raster_observation_ownership import _identifying_characters_exist, _identifying_characters_painted
    match=_TAG.match(normalize_text(line.text))
    if match is None:return False
    required={i for i,char in enumerate(line.text[:match.end()]) if char.strip()}
    boxes=_identifying_characters_exist(line,required,ink)
    return (len(boxes)==len(required)
            and _identifying_characters_painted(line,required,boxes,ink))


def _line_near(line,box,sideways=False):
    if _inside(line.bbox,box)>.75:return True
    if sideways:
        overlap=max(0,min(line.bbox[3],box[3])-max(line.bbox[1],box[1]))
        return overlap>min(line.bbox[3]-line.bbox[1],box[3]-box[1])*.4 and -15<=line.bbox[0]-box[2]<=45
    gap=line.bbox[1]-box[3]
    return -15<=gap<=45 and _xover(line.bbox,box)>.3


def _canonical_tags(lines):
    tags=[]
    for line in sorted(lines,key=lambda l:(l.bbox[1],l.bbox[0])):
        m=_TAG.match(normalize_text(line.text))
        if not m:continue
        letter=m.group(1).lower()
        # Bilingual descriptions name the same panel; disjoint repeated (a)
        # markers still represent different namespaces and fail the sequence.
        alias=next((item for item in tags if item[0]==letter and _xover(item[1].bbox,line.bbox)>.4
                    and abs(item[1].bbox[1]-line.bbox[1])<=25),None)
        if alias is None:tags.append((letter,line))
    return tags


def _source_labels(page,objects,owners,group,sideways,ink):
    envelope=_union([o.bbox for o in group]);lines=[]
    for line in page.lines:
        if not _native(line) or not _TAG.match(normalize_text(line.text)):continue
        if any(_line_near(line,o['box'],sideways) for o in owners):lines.append(line)
    tags=_canonical_tags(lines)
    labels=[t for t,l in tags]
    sequence=(len(labels)>=2 and len(labels)==len(set(labels))
              and set(labels)=={chr(97+i) for i in range(len(labels))})
    if (sequence and all(any(_line_near(l,o['box'],sideways) for _,l in tags) for o in owners)
            and all(any(_line_near(l,obj.bbox,sideways) for _,l in tags) for obj in group)):
        return lines,True
    # Outlined imported plot labels can lack a text layer. Their parser label
    # pixels must belong to the exact Form, and a retained native axis must
    # agree across every source chart. An OCR label outside source paint fails.
    if not sideways and len(owners)>=3 and all(o['kind']=='form' for o in owners):
        local=[];axes=[];raw=[]
        for owner in owners:
            found=[o for o in objects if o.page_number==page.number
                   and o.kind=='text' and o.role=='chart_caption'
                   and _SOURCE.fullmatch(o.source_id or '') and _TAG.match(normalize_text(o.text))
                   and _inside(o.bbox,owner['box'])>.5 and ink.owns(o,owner)]
            if len(found)!=1:break
            local.append(_TAG.match(normalize_text(found[0].text)).group(1).lower());raw.extend(found)
            axes.append({normalize_text(l.text) for l in page.lines if _native(l)
                         and _inside(l.bbox,owner['box'])>.8 and ink.glyph_owned(l.bbox,owner)
                         and len(re.findall(r'[A-Za-z\u4e00-\u9fff]',l.text))>=3})
        if (len(local)==len(owners) and len(set(local))==len(local)
                and set(local)=={chr(97+i) for i in range(len(local))} and set.intersection(*axes)):
            boxes=sorted((o['box'] for o in owners),key=lambda b:b[1])
            if all(_xover(a,b)>.85 and -2<=b[1]-a[3]<=30 for a,b in zip(boxes,boxes[1:])):
                return lines,True
    return lines,False


def _declared(text):
    tags=set(re.findall(r'[（(]\s*([a-z])\s*[）)]',text,re.I))
    for a,b in re.findall(r'[（(]\s*([a-z])\s*[-–—]\s*([a-z])\s*[）)]',text,re.I):
        if ord(b.lower())-ord(a.lower()) in range(1,9):tags.update(chr(i) for i in range(ord(a.lower()),ord(b.lower())+1))
    tags={t.lower() for t in tags}
    return tags if len(tags)>=2 and tags=={chr(97+i) for i in range(len(tags))} else set()


def _raster_columns(owner,ink):
    b=owner['box'];x0,y0,x1,y1=[int(round(v*2)) for v in b]
    crop=owner['mask'][max(y0,0):min(y1,ink.height),max(x0,0):min(x1,ink.width)]
    # This profile identifies panel gutters, not paint ownership. The later
    # ownership check still counts every non-white pixel, including grey 254.
    strong=crop&(ink.base[max(y0,0):min(y1,ink.height),max(x0,0):min(x1,ink.width)]<245)
    for axis in (0,1):
        a=strong if axis==0 else strong.T
        a=a[int(a.shape[0]*.06):int(a.shape[0]*.94),:]
        active=a.mean(axis=0)>.015;start=int(len(active)*.3);stop=int(len(active)*.7)
        run=best=0
        for value in active[start:stop]:
            run=0 if value else run+1;best=max(best,run)
        if best>=8:return True
    return False


def _title_text(cap,page):
    chunks=[]
    for line in page.lines:
        if line.source!='native' or not line.bold or _inside(line.bbox,cap.bbox)<.8:continue
        covered=_covered(line)
        chunks.append(''.join(c if not c.strip() or i in covered else ' ' for i,c in enumerate(line.text)))
    return ' '.join(chunks)


def _role_headers(page,owners):
    raster=[o for o in owners if o['kind']=='raster']
    if len(raster)!=len(owners) or len(raster)<3:return []
    boxes=sorted((o['box'] for o in raster),key=lambda b:b[0]);first=boxes[0]
    original=[l for l in page.lines if _native(l) and re.search(r'原始图像|original image',l.text,re.I)
              and -25<=first[1]-l.bbox[3]<=15 and _xover(l.bbox,first)>.5]
    reconstructed=[l for l in page.lines if _native(l) and re.search(r'重构结果|reconstruct(?:ed|ion)',l.text,re.I)
                   and -25<=boxes[1][1]-l.bbox[3]<=15 and _xover(l.bbox,_union(boxes[1:]))>.5]
    panel_labels=[l for l in page.lines if _native(l) and _TAG.match(normalize_text(l.text))]
    if (original and reconstructed and all(abs(b[1]-first[1])<=5 and abs(b[3]-first[3])<=5 for b in boxes)
            and all(-2<=b[0]-a[2]<=20 for a,b in zip(boxes,boxes[1:]))
            and all(any(_line_near(l,b) for l in panel_labels) for b in boxes[1:])):return original+reconstructed
    return []


def _roles(title,page,owners,ink):
    declared=_declared(title)
    raster=[o for o in owners if o['kind']=='raster']
    if declared and len(raster)==len(owners):
        # One bitmap is already one physical graphic; the retained title
        # explicitly declares the multiple roles which the parser split.
        if len(raster)==1:return True
        if len(declared)==2*len(raster) and all(_raster_columns(o,ink) for o in raster):return True
    if _role_headers(page,owners):return True
    if len(owners)==1 and owners[0]['kind']=='form':
        if not (re.search(r'\bgraph\b|分解图|关系图',title,re.I)
                and re.search(r'\bnodes?\b|节点',title,re.I)
                and re.search(r'\bedges?\b|向边|边表示',title,re.I)):return False
        # A visual input strip and the associated vector node/edge diagram are
        # a mixed source composition. Two charts merely sharing a Form fail.
        b=owners[0]['box'];nested=[]
        for record in ink.page.get_images(full=True):
            if not record[9]:continue
            nested.extend(tuple(r) for r in ink.page.get_image_rects(record[0]) if _inside(tuple(r),b)>.9)
        return bool(len(set(nested))==1 and (r:=nested[0])[2]-r[0]>(b[2]-b[0])*.6
                    and r[3]-r[1]<(b[3]-b[1])*.2 and r[1]-b[1]<10)
    return False


def _annotations(objects,page,labels,owners,ink):
    families={o.parent_id for o in objects if o.page_number==page.number
              and o.kind=='text' and o.parent_kind in ('image_caption','chart_caption')
              and _SOURCE.fullmatch(o.source_id or '') and _TAG.match(normalize_text(o.text))
              and any(_inside(l.bbox,(o.bbox[0]-4,o.bbox[1]-4,o.bbox[2]+4,o.bbox[3]+4))>.7 for l in labels)}
    chosen=[]
    for obj in objects:
        if obj.page_number!=page.number:continue
        sibling=any(-2<=obj.bbox[1]-l.bbox[3]<=20 and _xover(obj.bbox,l.bbox)>.6
                    and obj.bbox[2]-obj.bbox[0]<=(l.bbox[2]-l.bbox[0])*1.5 for l in labels)
        if (obj.kind!='text' or obj.parent_kind not in ('image_caption','chart_caption')
                or not _SOURCE.fullmatch(obj.source_id or '') or not (obj.parent_id in families or sibling)):continue
        box=(obj.bbox[0]-4,obj.bbox[1]-4,obj.bbox[2]+4,obj.bbox[3]+4)
        local=[l for l in page.lines if _native(l) and _inside(l.bbox,box)>.7]
        native=''.join(re.findall(r'[\w\u4e00-\u9fff]+',''.join(l.text for l in local))).casefold()
        observed=''.join(re.findall(r'[\w\u4e00-\u9fff]+',obj.text)).casefold()
        if local and (native==observed or len(set(native)&set(observed))>=len(set(observed))*.8):chosen.extend(local)
    return list({id(line):line for line in labels+chosen}.values())


def _text_mask(lines,ink):
    mask=ink.np.zeros_like(ink.base,dtype=bool)
    if not lines:return mask
    with ink.fit.open() as copy:
        copy.insert_pdf(ink.copy,from_page=0,to_page=0);p=copy[0]
        for line in lines:p.add_redact_annot(ink.fit.Rect(line.bbox),fill=None)
        p.apply_redactions(images=ink.fit.PDF_REDACT_IMAGE_NONE,graphics=ink.fit.PDF_REDACT_LINE_ART_NONE,
                           text=ink.fit.PDF_REDACT_TEXT_REMOVE)
        pix=p.get_pixmap(matrix=ink.fit.Matrix(2,2),colorspace=ink.fit.csGRAY,alpha=False)
        if (pix.height,pix.width)!=(ink.height,ink.width):return mask
        after=ink.np.frombuffer(pix.samples,dtype=ink.np.uint8).reshape(ink.height,ink.width)
        return (ink.base<255)&(after==255)


def _combined_mask(names,lines,ink):
    """Bind joint source/text paint without borrowing unknown glyphs."""
    if not lines:
        resource=ink.removal(names)
        return None if resource is None else resource['mask']
    from .native_text_paint import native_text_paint
    return native_text_paint(ink,lines,source_names=names)


def repair_source_native_caption_ownership(objects,document):
    if document is None or not Path(document.path).is_file():return list(objects)
    pending={f['page'] for f in detect_caption_rules(objects,[13],document)['13']['findings']}
    if not pending:return list(objects)
    import pymupdf
    result=list(objects)
    try:source=pymupdf.open(document.path)
    except (OSError,ValueError,RuntimeError):return result
    with source:
        for page in document.pages:
            if page.number not in pending or page.display_rotation or not 1<=page.number<=len(source) or page.width*page.height>2000000:continue
            caps=[o for o in result if o.kind=='figure_caption' and o.page_number==page.number and _native_caption(o,page)]
            if not caps:continue
            ink=None
            try:
                for cap in caps:
                    group,other,sideways=_namespace(result,cap,page)
                    if not group:continue
                    box=_union([o.bbox for o in group])
                    if any(re.search(r'[（(][a-z]\d+[）)]',normalize_text(l.text),re.I)
                           and _inside(l.bbox,(box[0]-25,box[1]-25,box[2]+25,cap.bbox[3]))>.5 for l in page.lines):continue
                    # A native source observation can duplicate a parser crop.
                    # Unknown overlapping independent observations cannot.
                    if any(a is not b and _inside(a.bbox,b.bbox)>.8
                           and not (_SOURCE.fullmatch(a.source_id or '') or a.source_id.startswith('native-source:')
                               or not a.source_id and a.role=='declared_vector_panel'
                                   and any(max(abs(x-y) for x,y in zip(a.bbox,b))<.01 for b in page.graphics))
                           for a in group for b in group):continue
                    if any(_matches(o,c) and abs(c.bbox[1]-o.bbox[3])<=abs(cap.bbox[1]-o.bbox[3])+2
                           for o in group for c in other):continue
                    if ink is None:
                        ink=_PageInk(source,page.number)
                        if not ink.valid:
                            ink.close();ink=_OriginalPageInk(source,page.number,document.path)
                    if not ink.valid:continue
                    owners=_owners(group,cap,ink,sideways,page)
                    if not owners:continue
                    labels,sequence=_source_labels(page,result,owners,group,sideways,ink)
                    title=_title_text(cap,page)
                    if not sequence and not _roles(title,page,owners,ink):continue
                    annotation=_annotations(result,page,labels,owners,ink)+_role_headers(page,owners)
                    # Removing all participating resources also resolves true
                    # overlapping raster placements, which separate removal
                    # observations cannot explain exclusively.
                    owner=ink.removal({name for o in owners for name in o['names']})
                    if owner is None:continue
                    title_lines=[l for l in page.lines if _native(l) and _inside(l.bbox,cap.bbox)>.8]
                    mask=_combined_mask({name for o in owners for name in o['names']},annotation+title_lines,ink)
                    if mask is None:continue
                    proof={'mask':mask}
                    if not all(ink.owns(o,proof) for o in group):continue
                    bounds=[o.bbox for o in group]+[o['box'] for o in owners]+[l.bbox for l in annotation]
                    extended=_union(bounds)
                    if (not sideways and cap.bbox[1]-extended[3]>80
                            or sideways and cap.bbox[0]-extended[2]>80):continue
                    # Native prose in the enclosing gaps remains a barrier
                    # unless original resource paint or a proven caption
                    # annotation owns its actual glyphs.
                    if any((_native(l) or len(re.findall(r'[\u4e00-\u9fff]',l.text))>=18
                            or len(re.findall(r'[A-Za-z]{2,}',l.text))>=5) and _inside(l.bbox,extended)>.8
                           and (not _native(l) or not ink.glyph_owned(l.bbox,proof)) for l in page.lines):continue
                    joined=replace(_join(group,'figure'),bbox=extended,role='source_native_caption_components',
                                   panel_boxes=tuple(b for o in group for b in o.panel_boxes or (o.bbox,)))
                    chosen={id(o) for o in group};result=[o for o in result if id(o) not in chosen]+[joined]
            except (ValueError,IndexError,RuntimeError):continue
            finally:
                if ink is not None:ink.close()
    return result
