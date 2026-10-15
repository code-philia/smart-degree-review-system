"""Actual isolated page pixels and frozen independent CPU OCR observations."""
import json
from dataclasses import replace
from pathlib import Path
from time import monotonic
from unittest.mock import patch

import numpy as np
import pymupdf
import pytest

from pdf_rules.local_ocr import OcrText
from pdf_rules.model import PdfDocument,PdfLine,PdfPage
from pdf_rules.page_policy import signature_page_reasons
from pdf_rules.signature_ocr import has_signature_structure_candidates
from pdf_rules.signature_structure import recover_structure

FIXTURES=Path(__file__).parent/'fixtures/admin_scans_20261013'
FACTS=json.loads((FIXTURES/'ocr-observations.json').read_text())


def scanned_page(name):
    path=FIXTURES/(name+'.pdf')
    fact=FACTS[name]
    w,h=fact['dimensions']
    page=PdfPage(1,w,h,(),unreadable=True,images=((0,0,w,h),),display_rotation=fact['display_rotation'])
    doc=PdfDocument(path,(page,))
    with pymupdf.open(path) as source:
        raw=source[0];scale=min(2,2400/max(raw.rect.width,raw.rect.height))
        pix=raw.get_pixmap(matrix=pymupdf.Matrix(scale,scale),colorspace=pymupdf.csGRAY,alpha=False)
        gray=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width).copy()
        transform=tuple(raw.derotation_matrix)
    hits=tuple(OcrText(**{**h,'bbox':tuple(h['bbox'])}) for h in fact['ocr'])
    return doc,page,(gray,scale,hits,transform)


def prove(name, *, extra_native=(), dropped=()):
    doc,page,reading=scanned_page(name)
    if extra_native:page=replace(page,lines=tuple(extra_native));doc=replace(doc,pages=(page,))
    gray,scale,hits,transform=reading
    reading=(gray,scale,tuple(h for h in hits if not any(t in h.text for t in dropped)),transform)
    with patch('pdf_rules.signature_structure.display_read',return_value=reading):
        return doc,recover_structure(doc,None,page,monotonic()+30)


def test_full_scanned_signing_page_gets_a_cpu_schema_attempt_without_tail_position():
    doc,page,_=scanned_page('wrapped_originality')
    assert has_signature_structure_candidates(doc,{1})
    research=replace(page,lines=(PdfLine(1,'第1章 实验结果',(80,80,300,100),page.width,page.height),))
    assert not has_signature_structure_candidates(replace(doc,pages=(research,)),{1})


@pytest.mark.parametrize('name',['wrapped_authorization','rotated_handwritten_decision'])
def test_actual_whole_scanned_form_has_bounded_pixel_and_schema_proof(name):
    doc,answer=prove(name)
    assert answer is not None
    updated,record=answer
    assert updated is not None, record
    assert record['status']=='proved_signature_structure'
    assert record['outside_ink']==[]
    recovered=replace(doc,pages=(updated,))
    assert 1 in signature_page_reasons(recovered)


def test_handwritten_decision_missing_vote_schema_is_not_excluded():
    _,answer=prove('rotated_handwritten_decision',dropped=('投票表决结果',))
    assert answer is None or answer[0] is None


def test_complete_form_cannot_exclude_an_independent_native_research_paragraph():
    fact=FACTS['wrapped_originality'];w,h=fact['dimensions']
    research=PdfLine(1,'本人实验得到的频率响应说明该方法适用于噪声环境。',(80,500,500,518),w,h)
    doc,answer=prove('wrapped_originality',extra_native=(research,))
    assert answer is None or answer[0] is None
    assert not signature_page_reasons(doc)


@pytest.mark.parametrize('content',['faint_reference','photo','faint_photo'])
def test_aligned_alpha_source_layer_keeps_independent_research_pixels(tmp_path,content):
    # A full-page aligned alpha layer must not inherit signing ownership.
    # These source pixels are absent from the frozen text OCR observations.
    from PIL import Image
    doc,page,reading=scanned_page('wrapped_originality')
    path=tmp_path/'source-layer-research.pdf'
    with pymupdf.open(doc.path) as pdf:
        box=pymupdf.Rect(pdf[0].get_image_info(xrefs=True)[0]['bbox'])
        with pymupdf.open() as vector:
            canvas=vector.new_page(width=box.width,height=box.height)
            if content=='faint_reference':
                canvas.insert_text((80,510),'图9.9',fontname='china-s',fontsize=4,color=(.99,)*3)
            else:
                canvas.draw_rect((100,500,180,565),fill=(.99,)*3 if content=='faint_photo' else (.4,.6,.2),color=None)
            pix=canvas.get_pixmap(matrix=pymupdf.Matrix(3,3),colorspace=pymupdf.csRGB,alpha=False)
            rgb=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width,3).copy()
            alpha=(np.any(rgb<255,axis=2)*255).astype('uint8')
            rgba=np.dstack((rgb,alpha))
            import io
            encoded=io.BytesIO();Image.fromarray(rgba).save(encoded,format='PNG')
        pdf[0].insert_image(box,stream=encoded.getvalue(),keep_proportion=False)
        pdf.save(path,garbage=4,deflate=True)
    with pymupdf.open(path) as pdf:
        source=pdf[0]
        transforms=[i['transform'] for i in source.get_image_info() if i['width']>1000]
        assert len(transforms)==2
        assert max(abs(a-b) for a,b in zip(*transforms))<.5
        pix=source.get_pixmap(matrix=pymupdf.Matrix(2,2),colorspace=pymupdf.csGRAY,alpha=False)
        gray=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width).copy()
    view=replace(doc,path=path)
    with patch('pdf_rules.signature_structure.display_read',return_value=(gray,2,reading[2],reading[3])):
        answer=recover_structure(view,None,page,monotonic()+30)
    assert answer is None or answer[0] is None
    if answer is not None:
        assert answer[1]['outside_ink']
        assert any(b[0]<181 and b[2]>78 and b[1]<566 and b[3]>500 for b in answer[1]['outside_ink'])


def test_native_research_inside_form_bbox_keeps_its_own_obligation():
    fact=FACTS['rotated_handwritten_decision'];w,h=fact['dimensions']
    # Displayed y300 is inside the administrative table; native coordinates
    # reflect its actual 180-degree page rotation.
    research=PdfLine(1,'本人实验得到的频率响应说明该方法适用于噪声环境。',(80,h-318,500,h-300),w,h)
    _,answer=prove('rotated_handwritten_decision',extra_native=(research,))
    assert answer is None or answer[0] is None


@pytest.mark.parametrize('text',['图9.9','附录Z'])
def test_jpeg_background_proof_cannot_own_faint_research_glyphs(tmp_path,text):
    from PIL import Image
    import io
    doc,page,reading=scanned_page('wrapped_originality')
    path=tmp_path/'jpeg-faint-research.pdf'
    with pymupdf.open(doc.path) as source:
        raw=source[0];raw.insert_text((80,510),text,fontname='china-s',fontsize=4,color=(.99,)*3)
        pix=raw.get_pixmap(matrix=pymupdf.Matrix(3,3),colorspace=pymupdf.csRGB,alpha=False)
        encoded=io.BytesIO();Image.frombytes('RGB',(pix.width,pix.height),pix.samples).save(encoded,format='JPEG',quality=95,subsampling=0)
    with pymupdf.open() as source:
        source.new_page(width=page.width,height=page.height).insert_image((0,0,page.width,page.height),stream=encoded.getvalue())
        source.save(path)
    with pymupdf.open(path) as source:
        pix=source[0].get_pixmap(matrix=pymupdf.Matrix(2,2),colorspace=pymupdf.csGRAY,alpha=False)
        gray=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width).copy()
    with patch('pdf_rules.signature_structure.display_read',return_value=(gray,2,reading[2],reading[3])):
        answer=recover_structure(replace(doc,path=path),None,page,monotonic()+30)
    assert answer is not None and answer[0] is None
    assert any(b[0]<100 and b[2]>78 and b[1]<512 and b[3]>502 for b in answer[1]['outside_ink'])


def test_originality_jpeg_background_proof_retains_an_unexplained_nonrepeating_block():
    _,answer=prove('wrapped_originality')
    assert answer is not None and answer[0] is None
    record=answer[1]
    assert record['status']=='unproved_outside_ink'
    repeated=[a for a in record['scan_artifacts'] if a['kind']=='repeated_source_jpeg_background_blocks']
    assert len(repeated)==2
    assert all(len(b['exact_repetitions'])>=3 for a in repeated for b in a['blocks'])
    assert any(b[0]<=150 and b[2]>=151 for b in record['outside_ink'])


def test_horizontal_scanner_strips_trigger_schema_reading_without_native_prose():
    width,height=600,840
    strips=tuple((2,10+i*91,598,10+(i+1)*91) for i in range(9))
    page=PdfPage(1,width,height,(),unreadable=True,images=strips)
    doc=PdfDocument(Path('unseen-striped-scan.pdf'),(page,))
    assert has_signature_structure_candidates(doc,{1})
    chapter=PdfLine(1,'第1章 实验结果',(80,50,320,68),width,height)
    assert not has_signature_structure_candidates(replace(doc,pages=(replace(page,lines=(chapter,)),)),{1})


def test_complete_decision_with_one_unfilled_signature_cell_keeps_positive_signed_rows():
    from pdf_rules.signature_structure import _decision_regions
    _,page,(gray,scale,hits,_)=scanned_page('freeflow_review_decision')
    details={}
    assert _decision_regions(hits,page.width,page.height,gray,scale,details)
    assert details['committee_rows']==6
    assert 3<=details['signed_rows']<6
    assert details['chair_has_signature_ink']
