"""Paper source tiling changes encoding, never administrative ownership."""
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from time import monotonic
from unittest.mock import patch
import numpy as np
import pymupdf
from PIL import Image
from test_admin_scan_recovery_20261013 import scanned_page
from pdf_rules.model import PdfDocument

def split_source(tmp_path, *, research=False):
    doc,page,reading=scanned_page('wrapped_authorization')
    gray,scale,hits,transform=reading
    pixels=gray.copy()
    if research:
        # A real non-form image island in the original source must survive.
        pixels[round(400*scale):round(430*scale),round(20*scale):round(50*scale)]=80
    path=tmp_path/'paper-in-native-strips.pdf'
    with pymupdf.open() as pdf:
        raw=pdf.new_page(width=page.width,height=page.height)
        bounds=np.linspace(0,pixels.shape[0],10).astype(int)
        for top,bottom in zip(bounds,bounds[1:]):
            image=BytesIO()
            Image.fromarray(pixels[top:bottom]).save(image,format='PNG')
            raw.insert_image((0,top/scale,page.width,bottom/scale),stream=image.getvalue(),keep_proportion=False)
        pdf.save(path)
    with pymupdf.open(path) as pdf:
        raw=pdf[0]
        images=tuple(tuple(i['bbox']) for i in raw.get_image_info())
        pix=raw.get_pixmap(matrix=pymupdf.Matrix(scale,scale),colorspace=pymupdf.csGRAY,alpha=False)
        rendered=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width).copy()
        assert len(images)==9
        assert np.array_equal(rendered,pixels)
    return replace(doc,path=path,pages=(replace(page,images=images,display_rotation=0),)),replace(page,images=images,display_rotation=0),(rendered,scale,hits,tuple(pymupdf.Matrix(1,0,0,1,0,0)))

def test_native_paper_strips_preserve_the_same_complete_form_obligation(tmp_path):
    from pdf_rules.signature_structure import recover_structure
    doc,page,reading=split_source(tmp_path)
    with patch('pdf_rules.signature_structure.display_read',return_value=reading):
        answer=recover_structure(doc,None,page,monotonic()+30)
    assert answer is not None
    assert answer[0] is not None,answer[1]
    assert answer[1]['status']=='proved_signature_structure'
    assert answer[1]['outside_ink']==[]

def test_paper_strip_reassembly_does_not_own_an_independent_body_graphic(tmp_path):
    from pdf_rules.signature_structure import recover_structure
    doc,page,reading=split_source(tmp_path,research=True)
    with patch('pdf_rules.signature_structure.display_read',return_value=reading):
        answer=recover_structure(doc,None,page,monotonic()+30)
    assert answer is not None and answer[0] is None
    assert any(b[0]<51 and b[2]>19 and b[1]<431 and b[3]>399 for b in answer[1]['outside_ink'])
