from dataclasses import replace
import pytest
import test_signature_page_content as fixtures
from pdf_rules.model import PdfDocument, PdfPage, PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules


@pytest.fixture
def scan():
    fixture=fixtures.SignaturePageContentTests();fixture.setUp()
    yield fixture.document
    fixture.doCleanups()


def obj(box,role='image_body',source_id='ocr:test:1:0:grid/tile'):
    return LayoutObject('figure',2,box,'',600,800,role,source_id=source_id)


def findings(document,objects):
    return detect_caption_rules(prepare_caption_layout(objects,document),[13],document)['13']['findings']


def test_empty_grid_ocr_fragment_on_verified_signature_scan_is_not_a_figure(scan):
    doc=scan(noise=True)
    assert findings(doc,[obj((0,300,390,650))])==[]


def test_padded_physical_bitmap_with_only_verified_form_ink_is_a_scan_carrier(scan):
    doc=scan(noise=True)
    assert findings(doc,[obj((40,60,560,700),'native_figure','')])==[]


def test_independent_untitled_graphic_outside_signature_form_remains_a_finding(scan):
    doc=scan(graphic=True)
    result=findings(doc,[obj((100,500,220,610))])
    assert any(f['location']['bounding_rect']['y1']==500 for f in result)


def test_large_graphic_outside_form_cannot_be_discarded_as_an_empty_scan_tile(scan):
    doc=scan(graphic=True)
    result=findings(doc,[obj((0,300,390,650))])
    assert result


def test_blank_tile_without_verified_form_context_retains_its_obligation(scan):
    doc=scan(noise=True)
    first=PdfPage(1,600,800,(PdfLine(1,'实验结果与相关工作',(60,80,540,100),600,800),))
    doc=PdfDocument(doc.path,(first,doc.pages[1]))
    assert findings(doc,[obj((0,300,390,650))])
