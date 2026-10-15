"""Independent synthetic negatives. Source PDFs are only copied into tmp paths."""
from pathlib import Path
from time import monotonic
from unittest.mock import patch
from io import BytesIO
import numpy as np,pymupdf as f
from PIL import Image
from pdf_rules.model import PdfDocument,PdfPage
from pdf_rules.signature_structure import recover_structure
from pdf_rules.signature_source_artifacts import source_artifacts
from pdf_rules.scan_boundary_proof import prove_continuous_source_boundary
from test_admin_source_fields_20261014 import P,page,read
class _VisibleInkGuard(tuple):pass

def test_independent_native_vector_inside_signing_field_remains_guarded(tmp_path):
    p=page("authorization_far_adviser");path=tmp_path/"native-vector-in-field.pdf"
    with f.open(P/"authorization_far_adviser.pdf") as pdf:
        pdf[0].draw_rect((532,348,554,377),fill=(.4,.6,.2),color=None)
        pdf.save(path)
    with f.open(path) as pdf:
        assert any(tuple(g["rect"])==(532,348,554,377) for g in pdf[0].get_drawings())
        pm=pdf[0].get_pixmap(matrix=f.Matrix(2,2),colorspace=f.csGRAY,alpha=False)
        gray=np.frombuffer(pm.samples,np.uint8).reshape(pm.height,pm.width).copy()
    reading=read("authorization_far_adviser");document=PdfDocument(path,(p,))
    # Freeze independently observed source form text; new graphic has no text.
    with patch("pdf_rules.signature_structure.display_read",return_value=(gray,2,reading[2],reading[3])):
        answer=recover_structure(document,None,p,monotonic()+30)
    assert answer is None or answer[0] is None,answer[1]

def test_partial_binary_edge_cannot_bypass_strict_whole_source_proof(tmp_path):
    pixels=np.full((1680,1200),255,np.uint8);pixels[:1,:1120]=0
    stream=BytesIO();Image.fromarray(pixels).convert("1").save(stream,format="PNG")
    path=tmp_path/"partial-edge.pdf"
    with f.open() as pdf:
        pdf.new_page(width=600,height=840).insert_image((0,0,600,840),stream=stream.getvalue(),keep_proportion=False)
        pdf.save(path)
    guard=_VisibleInkGuard((0,0,600,.5))
    strict=prove_continuous_source_boundary(pixels,source_bbox=(0,0,600,840),source_to_display=(600,0,0,840,0,0),page_bbox=(0,0,600,840),guard=guard,guard_kind="_VisibleInkGuard",display_sample_pitch=.5)
    assert strict is None
    kept,proofs=source_artifacts(PdfDocument(path,()),PdfPage(1,600,840,()),[],[guard],display_sample_pitch=.5)
    assert guard in kept,proofs

import pytest
@pytest.mark.parametrize("kind",["opaque_photo","localized_alpha_photo","localized_alpha_faint_photo"])
def test_small_independent_image_inside_signing_field_remains_guarded(tmp_path,kind):
    p=page("authorization_far_adviser");path=tmp_path/(kind+".pdf")
    shade=252 if "faint" in kind else 140
    pixels=np.full((87,66,4) if "alpha" in kind else (87,66,3),shade,np.uint8)
    if "alpha" in kind:
        pixels[:,:,3]=255;pixels[0,:,3]=0
    stream=BytesIO();Image.fromarray(pixels).save(stream,format="PNG")
    with f.open(P/"authorization_far_adviser.pdf") as pdf:
        pdf[0].insert_image((532,348,554,377),stream=stream.getvalue(),keep_proportion=False)
        pdf.save(path)
    with f.open(path) as pdf:
        assert any(i["width"]==66 and i["height"]==87 for i in pdf[0].get_image_info())
        pm=pdf[0].get_pixmap(matrix=f.Matrix(2,2),colorspace=f.csGRAY,alpha=False)
        gray=np.frombuffer(pm.samples,np.uint8).reshape(pm.height,pm.width).copy()
    reading=read("authorization_far_adviser")
    with patch("pdf_rules.signature_structure.display_read",return_value=(gray,2,reading[2],reading[3])):
        answer=recover_structure(PdfDocument(path,(p,)),None,p,monotonic()+30)
    assert answer is None or answer[0] is None,None if answer is None else answer[1]["status"]

def full_form_alpha_answer(tmp_path,*,extra_faint_reference):
    p=page("authorization_far_adviser")
    path=tmp_path/("full-form-alpha-extra.pdf" if extra_faint_reference else "full-form-alpha-control.pdf")
    with f.open(P/"authorization_far_adviser.pdf") as source:
        if extra_faint_reference:
            source[0].insert_text((535,370),"Fig9.9",fontsize=5,color=(.99,)*3)
        pm=source[0].get_pixmap(matrix=f.Matrix(2,2),colorspace=f.csGRAY,alpha=False)
        pixels=np.frombuffer(pm.samples,np.uint8).reshape(pm.height,pm.width).copy()
    alpha=(pixels<255).astype(np.uint8)*255
    encoded=BytesIO();Image.fromarray(np.dstack((pixels,pixels,pixels,alpha))).save(encoded,format="PNG")
    with f.open() as source:
        raw=source.new_page(width=p.width,height=p.height)
        blank=BytesIO();Image.fromarray(np.full_like(pixels,255)).save(blank,format="PNG")
        raw.insert_image(raw.rect,stream=blank.getvalue(),keep_proportion=False)
        raw.insert_image(raw.rect,stream=encoded.getvalue(),keep_proportion=False)
        source.save(path)
    with f.open(path) as source:
        pm=source[0].get_pixmap(matrix=f.Matrix(2,2),colorspace=f.csGRAY,alpha=False)
        gray=np.frombuffer(pm.samples,np.uint8).reshape(pm.height,pm.width).copy()
    reading=read("authorization_far_adviser")
    # Source-layer CPU OCR remains real; only original full-display text is frozen.
    with patch("pdf_rules.signature_structure.display_read",return_value=(gray,2,reading[2],reading[3])):
        return recover_structure(PdfDocument(path,(p,)),None,p,monotonic()+30)

def test_complete_independently_read_alpha_form_is_not_photo_density(tmp_path):
    answer=full_form_alpha_answer(tmp_path,extra_faint_reference=False)
    assert answer is not None and answer[0] is not None,None if answer is None else answer[1]["status"]

def test_complete_alpha_form_cannot_own_extra_faint_research_glyphs(tmp_path):
    answer=full_form_alpha_answer(tmp_path,extra_faint_reference=True)
    assert answer is None or answer[0] is None,None if answer is None else answer[1]["status"]


def test_actual_printed_alpha_authorization_remains_supported():
    from test_admin_source_fields_20261014 import recover
    answer=recover("authorization_blank_expiry")
    assert answer is not None and answer[0] is not None,None if answer is None else answer[1]["outside_ink"]


@pytest.mark.parametrize("kind",["outline","faint_outline","polyline"])
def test_independent_native_strokes_inside_signature_field_remain_guarded(tmp_path,kind):
 p=page("authorization_far_adviser");path=tmp_path/(kind+".pdf")
 with f.open(P/"authorization_far_adviser.pdf") as pdf:
  if kind=="polyline":
   pdf[0].draw_polyline([(532,348),(538,370),(547,356),(554,377)],color=(.2,.2,.2),width=.3)
  else:
   shade=.99 if kind=="faint_outline" else .2
   pdf[0].draw_rect((532,348,554,377),color=(shade,)*3,fill=None,width=.3)
  pdf.save(path)
 with f.open(path) as pdf:
  assert pdf[0].get_drawings()
  pm=pdf[0].get_pixmap(matrix=f.Matrix(2,2),colorspace=f.csGRAY,alpha=False)
  gray=np.frombuffer(pm.samples,np.uint8).reshape(pm.height,pm.width).copy()
 reading=read("authorization_far_adviser")
 with patch("pdf_rules.signature_structure.display_read",return_value=(gray,2,reading[2],reading[3])):
  answer=recover_structure(PdfDocument(path,(p,)),None,p,monotonic()+30)
 assert answer is None or answer[0] is None,None if answer is None else answer[1]["status"]

@pytest.mark.parametrize("shade",[230,240,249])
def test_whole_page_source_component_cannot_own_attached_gray_body_ink(tmp_path,shade):
 a=np.full((1680,1200),250,np.uint8)
 a[:2,:]=shade;a[-2:,:]=shade;a[:,:2]=shade;a[:,-2:]=shade
 a[1:81,60:62]=shade;a[79:81,60:140]=shade;a[:4,:4]=0
 encoded=BytesIO();Image.fromarray(a).save(encoded,format="PNG")
 path=tmp_path/(str(shade)+"-source-perimeter-body.pdf")
 with f.open() as pdf:
  pdf.new_page(width=600,height=840).insert_image((0,0,600,840),stream=encoded.getvalue(),keep_proportion=False)
  pdf.save(path)
 guard=_VisibleInkGuard((0,0,2,2))
 kept,proofs=source_artifacts(PdfDocument(path,()),PdfPage(1,600,840,()),[],[guard],display_sample_pitch=.5)
 assert guard in kept,proofs
