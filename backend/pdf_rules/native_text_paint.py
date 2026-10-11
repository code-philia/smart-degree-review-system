"""Prove text paint by the actual source glyphs lost during suppression."""
from collections import Counter
import unicodedata

from .figure_identity_repair import _area
from .source_native_caption_ownership import _native
from .caption_physical_ownership import _do_spans


def _text(value):
    return unicodedata.normalize('NFKC',value)


def _filled_glyphs(page):
    """Retain each visible fill/stroke paint with its real source glyph."""
    result=Counter()
    for span in page.get_texttrace():
        if span['type'] not in (0,1):continue
        for code,glyph,origin,box in span['chars']:
            # MuPDF emits unpainted, zero-width continuation records for
            # ligatures. The real first glyph still carries the full paint.
            if glyph==-1 and box[0]==box[2]:continue
            key=(span['font'],round(span['size'],3),_text(chr(code)),
                 tuple(round(v,3) for v in origin),tuple(round(v,3) for v in box),
                 span['type'])
            result[key]+=1
    return result


def _raw_boxes(page):
    """Corroborate the source's two native bounding-box conventions."""
    boxes={}
    import pymupdf
    flags=pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES
    for block in page.get_text('rawdict',flags=flags)['blocks']:
        if block['type']!=0:continue
        for line in block['lines']:
            for span in line['spans']:
                for char in span['chars']:
                    key=(span['font'],round(span['size'],3),_text(char['c']),
                         tuple(round(v,3) for v in char['origin']))
                    boxes.setdefault(key,[]).append(tuple(char['bbox']))
    return boxes


def _align_remaining(remaining,original):
    # MuPDF may round retained text matrices by a thousandth of a point when
    # rebuilding a redacted stream. Correlate only the same real character,
    # font, size and paint mode with a unique original origin and outline
    # within .01pt. Filling and stroking remain separate source obligations.
    by_character={}
    for key in original:by_character.setdefault((key[:3],key[5]),[]).append(key)
    aligned=Counter()
    for key,count in remaining.items():
        if key in original:aligned[key]+=count;continue
        matches=[old for old in by_character.get((key[:3],key[5]),[])
                 if max(abs(a-b) for a,b in zip(key[3]+key[4],old[3]+old[4]))<.01]
        aligned[matches[0] if len(matches)==1 else key]+=count
    return aligned


def _text_object_modes(data):
    """Find BT/ET and real Tr operands, excluding strings and inline images."""
    i=0;n=len(data);start=None;out=[];depth=0;previous=None;modes=[]
    render_mode=0;state_stack=[];nested_state=False;shows_text=False
    while i<n:
        c=data[i]
        if c in b'\x00\t\n\r\x0c ':i+=1;continue
        if c==37:
            z=data.find(b'\n',i);i=n if z<0 else z+1;continue
        if c==40:
            i+=1;balance=1
            while i<n and balance:
                if data[i]==92:i+=2;continue
                if data[i]==40:balance+=1
                if data[i]==41:balance-=1
                i+=1
            if balance:return []
            previous=None;continue
        if c==60 and data[i:i+2]!=b'<<':
            z=data.find(b'>',i+1)
            if z<0:return []
            i=z+1;previous=None;continue
        if c in b'[]' or data[i:i+2] in (b'<<',b'>>'):
            depth+=1 if c==91 or data[i:i+2]==b'<<' else -1
            if depth<0:return []
            i+=2 if data[i:i+2] in (b'<<',b'>>') else 1
            previous=None;continue
        a=i
        if c==47:i+=1
        while i<n and data[i] not in b'\x00\t\n\r\x0c ()<>[]{}/%':i+=1
        if i==a:return []
        token=data[a:i]
        if token==b'BI':return []
        if depth:continue
        if token==b'q':
            if start is not None:nested_state=True
            state_stack.append(render_mode)
        elif token==b'Q':
            if not state_stack:return []
            if start is not None:nested_state=True
            render_mode=state_stack.pop()
        elif token==b'BT':
            if start is not None:return []
            start=a;modes=[];nested_state=False;shows_text=False
        elif token==b'ET':
            if start is None:return []
            # Some source generators wrap a Form Do in BT/ET with q/Q but
            # show no page text. Leave that whole graphics object untouched;
            # it does not invalidate other independently safe text objects.
            # State nesting around actual text cannot be suppressed safely.
            if nested_state and shows_text:return []
            if not nested_state:out.append((start,i,tuple(modes),render_mode))
            start=None
        elif token==b'Tr':
            if previous is None:return []
            try:value=float(previous[2])
            except ValueError:return []
            # Text clipping modes change the actual clip on ET. Suppressing
            # their paint cannot preserve that effect, so do not use these
            # streams to prove that an unexpected glyph never paints.
            if not value.is_integer() or not 0<=value<=3:return []
            render_mode=int(value)
            if start is not None:modes.append((previous[0],i))
        elif start is not None and token in (b'Tj',b'TJ',b"'",b'"'):
            shows_text=True
        previous=(a,i,token)
    # A remaining saved state ends at the page boundary; no Q is invented.
    return out if start is None and depth==0 else []


def _hide_text_objects(data,objects):
    # Ranges always refer to the original source. Work from right to left so
    # inserted Tr operands cannot move a preceding object's coordinates.
    result=data
    for a,z,modes,render_mode in sorted(objects,reverse=True):
        body=bytearray(data[a:z])
        for left,right in reversed(modes):body[left-a:right-a]=b'3 Tr'
        # Preserve original colour, opacity, font and all other state side
        # effects. An enclosing q/Q would undo legitimate changes in this BT
        # and could make an independent path conceal an unknown glyph.
        restore=str(render_mode).encode('ascii')+b' Tr ET'
        result=result[:a]+b'BT 3 Tr '+bytes(body[2:-2])+restore+result[z:]
    return result


def _nonpainting_source_glyphs(ink,unexpected,original,approved,source_names):
    """Require no paint both before and after approved owners are removed.

    Clipped text traces can disappear during rectangle redaction without
    ever contributing paint. Text covered by an approved resource or native
    title is different: it reappears when that owner is removed. Suppress
    actual complete BT/ET objects only when every lost glyph belongs to the
    approved native evidence, then test the unknown object against that
    exposed source context. Both whole-page RGB and gray must be unchanged.
    """
    template=ink.copy.tobytes();objects=_text_object_modes(ink.data)
    def observe(data,paint=True):
        with ink.fit.open(stream=template,filetype='pdf') as copy:
            page=copy[ink.page.number]
            xref=copy.get_new_xref();copy.update_object(xref,'<<>>')
            copy.update_stream(xref,data);page.set_contents(xref)
            remaining=_align_remaining(_filled_glyphs(page),original)
            if not paint:return remaining,None,None
            return remaining,page.get_pixmap(matrix=ink.fit.Matrix(2,2),colorspace=ink.fit.csGRAY,alpha=False),page.get_pixmap(matrix=ink.fit.Matrix(2,2),colorspace=ink.fit.csRGB,alpha=False)
    def same_pixels(left,right):
        return all((a.height,a.width,a.samples)==(b.height,b.width,b.samples) for a,b in zip(left,right))
    original_pixels=(ink.page.get_pixmap(matrix=ink.fit.Matrix(2,2),colorspace=ink.fit.csGRAY,alpha=False),ink.page.get_pixmap(matrix=ink.fit.Matrix(2,2),colorspace=ink.fit.csRGB,alpha=False))
    known=[];candidates=[]
    for obj in objects:
        data=_hide_text_objects(ink.data,(obj,))
        remaining,gray,rgb=observe(data,paint=False)
        lost=original-remaining
        if not lost or remaining-original:continue
        if not lost-approved:known.append(obj)
        if not lost-unexpected:
            _,gray,rgb=observe(data)
            if same_pixels((gray,rgb),original_pixels):candidates.append(obj)
    if not candidates:return Counter()
    source=bytearray(ink.data);names=set(source_names)
    for name,a,z in _do_spans(ink.data):
        if name in names:source[a:z]=b' '*(z-a)
    source=bytes(source)
    context,gray,rgb=observe(_hide_text_objects(source,known))
    if context-original or (original-context)-approved:return Counter()
    context_pixels=(gray,rgb);proven=Counter()
    for obj in candidates:
        # A title object cannot also be an independent unknown object.
        if obj in known:continue
        remaining,gray,rgb=observe(_hide_text_objects(source,known+[obj]))
        lost=context-remaining
        if not lost or remaining-context or lost-unexpected:continue
        if same_pixels((gray,rgb),context_pixels):proven|=lost
    return proven


def native_text_paint(ink,lines,source_names=()):
    """Remove only corroborated character regions, and audit every lost glyph.

    Rectangle redaction may also remove a neighbouring source character.
    The resulting mask is rejected if even one lost nonblank glyph is not
    present in the retained native character evidence. Images and paths stay
    intact, and paint is credited only where suppression reveals exact white.
    """
    empty=ink.np.zeros_like(ink.base,dtype=bool)
    lines=[line for line in lines if _native(line)]
    if not lines or not ink.valid:return empty
    original=_filled_glyphs(ink.page);raw=_raw_boxes(ink.page)
    # Native extraction can index regions either before or after expanding a
    # Unicode ligature (ﬁ -> fi). Each interpretation still has to match the
    # same actual source character and its exact original box independently.
    regions=[(_text(text[a:z]),tuple(box)) for line in lines
             for text in dict.fromkeys((line.text,_text(line.text)))
             for a,z,box in line.text_regions if 0<z-a<=3]
    approved=Counter();redactions=[];by_character={}
    for key in original:by_character.setdefault(key[2],[]).append(key)
    for text,region in dict.fromkeys(regions):
        matches=[key for key in by_character.get(text,[]) if any(
            max(abs(a-b) for a,b in zip(box,region))<.05 for box in [key[4]]+raw.get(key[:4],[]))]
        # PDF Tr=2 emits one fill and one stroke trace for the same glyph.
        # A single native region may corroborate each mode once, only when
        # every matched trace has the identical source font/character/geometry.
        if not matches or len({key[:5] for key in matches})!=1:continue
        for key in matches:approved[key]+=1
        if _area(region)>0:redactions.append(region)
    if not redactions:return empty
    try:
        with ink.fit.open(stream=ink.copy.tobytes(),filetype='pdf') as copy:
            page=copy[ink.page.number]
            # Joint resource/text removal can expose a header glyph painted
            # on a dark resource pixel. Every separately approved resource
            # glyph is identified by its actual disappearance after Do removal;
            # no resource rectangle or guessed clipping envelope is credited.
            if source_names:
                data=bytearray(page.read_contents());selected=set(source_names)
                for name,a,z in _do_spans(bytes(data)):
                    if name in selected:data[a:z]=b' '*(z-a)
                xref=copy.get_new_xref();copy.update_object(xref,'<<>>')
                copy.update_stream(xref,bytes(data));page.set_contents(xref)
                resource_remaining=_align_remaining(_filled_glyphs(page),original)
                if resource_remaining-original:return empty
                approved+=original-resource_remaining
            for box in dict.fromkeys(redactions):page.add_redact_annot(ink.fit.Rect(box),fill=None)
            page.apply_redactions(images=ink.fit.PDF_REDACT_IMAGE_NONE,
                                  graphics=ink.fit.PDF_REDACT_LINE_ART_NONE,
                                  text=ink.fit.PDF_REDACT_TEXT_REMOVE)
            remaining=_align_remaining(_filled_glyphs(page),original);lost=original-remaining
            unexpected=lost-approved
            if unexpected:
                unexpected-=_nonpainting_source_glyphs(ink,unexpected,original,approved,source_names)
            if not lost or remaining-original or any(not key[2].isspace() for key in unexpected):
                return empty
            pix=page.get_pixmap(matrix=ink.fit.Matrix(2,2),colorspace=ink.fit.csGRAY,alpha=False)
            if (pix.height,pix.width)!=(ink.height,ink.width):return empty
            after=ink.np.frombuffer(pix.samples,dtype=ink.np.uint8).reshape(ink.height,ink.width)
            return (ink.base<255)&(after==255)
    except (ValueError,RuntimeError,IndexError):return empty
