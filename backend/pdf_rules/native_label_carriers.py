"""Read-only native glyph proof for duplicated raster panel labels."""
import math


def native_text_only(document, page, bbox, lines, allowed_strokes=()):
    """Require the actual native text layer to explain every visible pixel.

    Unavailable originals, rotated coordinates and incomplete glyph evidence
    retain the observation. This never changes the PDF or its image inventory.
    """
    if page.display_rotation or not document.path.is_file():
        return False
    if not all(math.isfinite(v) for v in bbox) or bbox[2]<=bbox[0] or bbox[3]<=bbox[1]:
        return False
    glyphs=[]
    for line in lines:
        covered=set()
        for start,end,box in line.text_regions:
            if end-start!=1 or not (0<=start<end<=len(line.text)):
                continue
            if not line.text[start:end].strip():
                continue
            if not all(math.isfinite(v) for v in box) or box[2]<=box[0] or box[3]<=box[1]:
                return False
            if box[0]<bbox[0]-2 or box[1]<bbox[1]-2 or box[2]>bbox[2]+2 or box[3]>bbox[3]+2:
                return False
            covered.add(start);glyphs.append(box)
        if any(c.strip() and i not in covered for i,c in enumerate(line.text)):
            return False
    if not glyphs:
        return False
    try:
        import pymupdf
        # Work on a one-page in-memory diagnostic copy. Original content and
        # image inventory are never rewritten. Comparing actual glyph ink,
        # rather than its bounding rectangles, preserves graphics printed in
        # the whitespace of a character box and italic overhanging strokes.
        with pymupdf.open(document.path) as pdf, pymupdf.open() as diagnostic:
            native=pdf[page.number-1]
            if native.rotation:
                return False
            diagnostic.insert_pdf(pdf,from_page=page.number-1,to_page=page.number-1)
            native=diagnostic[0]
            options=dict(matrix=pymupdf.Matrix(3,3),clip=pymupdf.Rect(bbox),
                         colorspace=pymupdf.csRGB,alpha=False,annots=False)
            pix=native.get_pixmap(**options)
            native.add_redact_annot(pymupdf.Rect(bbox),fill=False,cross_out=False)
            native.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
                                    graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                                    text=pymupdf.PDF_REDACT_TEXT_NONE)
            # A caller may independently prove native mathematical fraction
            # rules. Recreate only those exact straight strokes after removing
            # all graphic ink, then require byte-for-byte pixel equivalence.
            for start,end,width,color in allowed_strokes:
                native.draw_line(start,end,width=width,color=color)
            text=native.get_pixmap(**options)
            if (pix.width,pix.height,pix.x,pix.y)!=(text.width,text.height,text.x,text.y):
                return False
            samples=pix.samples
            return samples==text.samples and any(value!=255 for value in samples)
    except (OSError,ValueError,RuntimeError,IndexError):
        return False
