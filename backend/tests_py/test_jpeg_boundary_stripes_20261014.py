"""Exact original codec blocks own only repeating source-boundary stripes."""
from pathlib import Path
import json
import numpy as np
import pymupdf
import pytest
from PIL import Image
from pdf_rules.signature_source_artifacts import _jpeg_block_background,source_artifacts
from pdf_rules.model import PdfDocument,PdfPage

FIXTURE=Path(__file__).parent/'fixtures/jpeg_boundary_stripes_20261014'
def pixels():return np.asarray(Image.open(FIXTURE/'wang163-original-paper.jpg').convert('L'))

@pytest.mark.parametrize('box',[(310,3665,320,3670),(326,3665,344,3670)])
def test_actual_complete_repeating_boundary_stripes_are_source_proved(box):
    proof=_jpeg_block_background(pixels(),box,{})
    assert proof is not None
    assert all(len(b['exact_repetitions'])>=3 for b in proof)
    assert all(not b['has_glyph_counter'] for b in proof)

def test_row_constant_research_grid_in_body_cannot_borrow_boundary_ownership():
    original=pixels();a=np.full_like(original,255);block=original[3664:3672,328:336]
    for x in (320,520,800):a[800:808,x:x+8]=block
    assert _jpeg_block_background(a,(320,800,328,808),{}) is None

def test_boundary_stripe_without_three_distant_exact_copies_stays_unproved():
    original=pixels();a=np.full_like(original,255)
    a[3664:3672,312:320]=original[3664:3672,312:320]
    assert _jpeg_block_background(a,(312,3664,320,3672),{}) is None

def test_boundary_counter_glyph_cannot_borrow_repeating_row_stripe_proof():
    a=np.full_like(pixels(),255);block=np.full((8,8),255,np.uint8)
    block[2:6,2:6]=253;block[3:5,3:5]=255
    for x in (320,520,800):a[3664:3672,x:x+8]=block
    assert _jpeg_block_background(a,(320,3664,328,3672),{}) is None

@pytest.mark.parametrize('guard_type',['_TextGuard','_GraphicGuard','_IndependentInkGuard','_VisibleInkGuard'])
def test_explicit_content_guard_retains_original_boundary_stripe_obligation(monkeypatch,guard_type):
    facts=json.loads((FIXTURE/'provenance.json').read_text())
    pdf=pymupdf.open();raw=pdf.new_page(width=595,height=842)
    raw.insert_image(facts['source_bbox'],filename=str(FIXTURE/'wang163-original-paper.jpg'))
    # Only the file-open boundary is substituted; original pixels and source
    # artifact classification remain real, and no test PDF is written.
    monkeypatch.setattr('pdf_rules.signature_source_artifacts.pymupdf.open',lambda *_:pdf)
    Guard=type(guard_type,(tuple,),{})
    guard=Guard((85.,839.5,89.,840.5))
    page=PdfPage(1,595,842,(),unreadable=True)
    retained,_=source_artifacts(PdfDocument(Path('unused-test-source.pdf'),(page,)),page,
        ((61.,50.,541.,298.),),(guard,))
    assert any(type(item).__name__==guard_type and tuple(item)==tuple(guard) for item in retained)
