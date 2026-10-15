from pathlib import Path
import pytest
import pymupdf
from pdf_rules.pdf_extract import extract_pdf
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules

PREFIX=Path(__file__).parent/'fixtures/raster_caption_prefix_1_2.png'

def make_pdf(path, *, prefix=True, gap=1, next_page=False):
    pdf=pymupdf.open();p=pdf.new_page(width=600,height=800)
    p.insert_text((60,100),'The complete experimental comparison is shown in Fig. 1-2 and Fig. 9-9.',fontsize=12)
    if next_page:p=pdf.new_page(width=600,height=800)
    p.draw_rect((100,150,500,330),fill=(.8,.8,.8))
    if prefix:p.insert_image(pymupdf.Rect(140,351,180,363),filename=str(PREFIX))
    p.insert_text((180+gap,361),'Experimental comparison of the measured responses',fontsize=10)
    p.insert_text((60,600),'Independent body text describes the experimental evaluation in sufficient detail.',fontsize=12)
    pdf.save(path)

def test_raster_prefix_creates_literal_caption_and_true_missing_reference_remains(tmp_path):
    path=tmp_path/'prefix.pdf';make_pdf(path)
    doc=extract_pdf(path);ix=build_index(doc)
    assert any(t.number=='1.2' for t in ix.figures)
    assert [f['token'] for f in detect_rules(ix,[11])['11']['findings']]==['9.9']
    assert not doc.pages[0].images

def test_caption_on_next_page_resolves_typed_reference(tmp_path):
    path=tmp_path/'next.pdf';make_pdf(path,next_page=True)
    assert [f['token'] for f in detect_rules(build_index(extract_pdf(path)),[11])['11']['findings']]==['9.9']

def test_absent_prefix_cannot_be_guessed_from_prose_reference(tmp_path):
    path=tmp_path/'missing.pdf';make_pdf(path,prefix=False)
    assert [f['token'] for f in detect_rules(build_index(extract_pdf(path)),[11])['11']['findings']]==['1.2','9.9']

def test_separate_small_graphic_is_not_joined_across_gap(tmp_path):
    path=tmp_path/'gap.pdf';make_pdf(path,gap=70)
    doc=extract_pdf(path)
    assert doc.pages[0].images
    assert not build_index(doc).figures

@pytest.mark.parametrize('text,score',[('Fig.1-2',.8),('x/L',.999),('Eq.1-2',.999),('1-2',.999)])
def test_uncertain_axis_equation_and_bare_number_stay_graphics(tmp_path,monkeypatch,text,score):
    from pdf_rules import caption_raster_prefixes
    # Recognition is the external dependency here; test only acceptance and
    # geometry preservation, while the first two cases above run real OCR.
    monkeypatch.setattr(caption_raster_prefixes,'_recognize_pixels',lambda batch:tuple((text,score) for _ in batch))
    path=tmp_path/'unproved.pdf';make_pdf(path)
    doc=extract_pdf(path)
    assert doc.pages[0].images
    assert not any(l.source=='local_caption_prefix_ocr' for l in doc.lines)
    assert [f['token'] for f in detect_rules(build_index(doc),[11])['11']['findings']]==['1.2','9.9']
