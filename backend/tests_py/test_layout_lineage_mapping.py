"""Source identity and all geometry must survive real OCR-view mappings."""
from dataclasses import replace
import pymupdf

from pdf_rules import engine, mineru_api
from pdf_rules.mineru_layout import normalize_layout
from pdf_rules.model import PdfDocument, PdfPage


def raw_page(width=600, height=800):
    return {"page_idx": 0, "page_size": [width, height], "para_blocks": [
        {"type": "image", "bbox": [10, 10, 200, 100], "blocks": [
            {"type": "image_body", "bbox": [20, 20, 180, 60], "lines": []},
            {"type": "image_caption", "bbox": [20, 70, 180, 90],
             "lines": [{"bbox": [20, 70, 180, 90],
                        "spans": [{"content": "Figure 1.1 Comparison"}]}]}]}]}


def create_pdf(path, count=3, rotation=0):
    with pymupdf.open() as doc:
        for _ in range(count):
            page = doc.new_page(width=600, height=800)
            page.set_rotation(rotation)
        path.write_bytes(doc.tobytes())


def fake_parse(path, *_args, **_kwargs):
    with pymupdf.open(path) as doc:
        result = []
        for index, page in enumerate(doc):
            obj = normalize_layout([raw_page(page.rect.width, page.rect.height)],
                                   index + 1, [(page.rect.width, page.rect.height)])[0]
            result.append(replace(obj, panel_boxes=((20, 20, 180, 60),)))
        return result


def test_sparse_ocr_view_cannot_collide_with_an_original_page(tmp_path, monkeypatch):
    path = tmp_path / "three-pages.pdf"
    create_pdf(path)
    document = PdfDocument(path, tuple(PdfPage(i, 600, 800, (), unreadable=i == 3)
                                      for i in (1, 2, 3)))
    monkeypatch.setattr(engine, "parse_layout", fake_parse)
    ordinary = normalize_layout([raw_page()], 1, [(600, 800)])[0]
    fresh = engine._ocr_missing_pages(path, document, "offline", None)
    merged = engine._replace_ocr_text([ordinary], fresh)
    assert fresh[0].page_number == 3
    assert len({o.source_id for o in merged}) == 2
    assert fresh[0].parent_id != ordinary.parent_id


def test_grid_ocr_translates_parent_and_every_physical_panel(tmp_path, monkeypatch):
    path = tmp_path / "grid.pdf"
    create_pdf(path, 1)
    document = PdfDocument(path, (PdfPage(1, 600, 800, (), unreadable=True),))
    monkeypatch.setattr(engine, "parse_layout", fake_parse)
    objects = engine._ocr_missing_pages(path, document, "offline", None, tiled="grid")
    right = objects[1]
    assert right.bbox == (230, 20, 390, 60)
    assert right.parent_bbox == (220, 10, 410, 100)
    assert right.panel_boxes == ((230, 20, 390, 60),)
    assert len({o.source_id for o in objects}) == 6


def test_rotated_parse_derotates_parent_together_with_children(tmp_path, monkeypatch):
    path = tmp_path / "rotated.pdf"
    create_pdf(path, 1, 90)
    monkeypatch.setenv("MINERU_CACHE_DIR", str(tmp_path / "raw-cache"))
    monkeypatch.setattr(mineru_api, "_submit_and_fetch", lambda *_a, **_k: [raw_page(800, 600)])
    result = mineru_api.parse_layout(path, "offline", http_client=object(), respect_rotation=True)
    with pymupdf.open(path) as doc:
        matrix = doc[0].derotation_matrix
        expected_parent = tuple(pymupdf.Rect(10, 10, 200, 100) * matrix)
        expected_body = tuple(pymupdf.Rect(20, 20, 180, 60) * matrix)
    assert result[0].bbox == expected_body
    assert result[0].parent_bbox == expected_parent


def test_same_pdf_parsed_by_different_models_has_distinct_source_identity(tmp_path, monkeypatch):
    path = tmp_path / "model-views.pdf"
    create_pdf(path, 1)
    monkeypatch.setenv("MINERU_CACHE_DIR", str(tmp_path / "raw-cache"))
    monkeypatch.setattr(mineru_api, "_submit_and_fetch", lambda *_a, **_k: [raw_page()])
    a = mineru_api.parse_layout(path, "offline", http_client=object())
    b = mineru_api.parse_layout(path, "offline", http_client=object(), force_ocr=True)
    assert a[0].source_id != b[0].source_id
    assert a[0].parent_id != b[0].parent_id
