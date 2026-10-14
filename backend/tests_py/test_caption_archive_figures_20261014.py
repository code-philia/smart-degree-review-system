"""Three exact archive caption regressions, with source/glyph negative controls."""
from dataclasses import replace
from pathlib import Path
import hashlib,json
import pytest
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.caption_rules import detect_caption_rules
from pdf_rules.logical_objects import shared_title_groups
from pdf_rules.native_raster_observation_ownership import repair_native_raster_observation_ownership

def frozen(value):
    if isinstance(value,list):return tuple(frozen(x) for x in value)
    return value

def load(number):
    data=json.loads(Path(__file__).with_name(f"caption_archive_figure_{number}_20261014.json").read_text())
    pages=[]
    for raw in data["document"]["pages"]:
        raw=dict(raw)
        raw["lines"]=[PdfLine(**{k:frozen(v) for k,v in l.items()}) for l in raw["lines"]]
        pages.append(PdfPage(**{k:frozen(v) if k!="lines" else v for k,v in raw.items()}))
    document=PdfDocument(data["document"]["path"],pages)
    objects=[LayoutObject(**{k:frozen(v) for k,v in o.items()}) for o in data["prepared_objects"]]
    return data,objects,document

def repaired(number,objects,document):
    if number==3:
        targets=[o for o in objects if o.kind=="figure"]
        captions=[o for o in objects if o.kind=="figure_caption"]
        return shared_title_groups(targets,captions,document)+captions
    if number==6:
        if not Path(document.path).is_file():pytest.skip("original archive source PDF unavailable")
        return repair_native_raster_observation_ownership(objects,document)
    return objects

@pytest.mark.parametrize("number",[3,5,6])
def test_real_archive_figure_has_its_title(number):
    data,objects,document=load(number)
    if number==6:
        if not Path(document.path).is_file():pytest.skip("original archive source PDF unavailable")
        assert hashlib.sha256(Path(document.path).read_bytes()).hexdigest()==data["pdf_sha"]
    assert detect_caption_rules(repaired(number,objects,document),[13],document)["13"]["findings"]==[]

@pytest.mark.parametrize("number",[3,5,6])
def test_removing_every_caption_keeps_missing_title_report(number):
    data,objects,document=load(number)
    objects=[o for o in objects if not o.kind.endswith("_caption")]
    assert detect_caption_rules(repaired(number,objects,document),[13],document)["13"]["findings"]

@pytest.mark.parametrize("number",[3,6])
def test_cached_caption_cannot_replace_native_identifying_glyphs(number):
    data,objects,document=load(number)
    for page in document.pages:page.lines[:]=[replace(line,text_regions=()) for line in page.lines]
    assert detect_caption_rules(repaired(number,objects,document),[13],document)["13"]["findings"]

def test_figure_body_prose_still_blocks_caption():
    data,objects,document=load(5)
    for page in document.pages:
        page.lines[:]=[replace(line,font_size=12,bold=False) if 298<line.bbox[1]<309 else line for line in page.lines]
    assert detect_caption_rules(objects,[13],document)["13"]["findings"]


def test_empty_native_title_glyph_rectangles_cannot_prove_annotation_ownership():
    data,objects,document=load(5)
    for page in document.pages:
        page.lines[:]=[replace(line,text_regions=tuple((a,z,(b[0],b[1],b[0],b[1]))
                       for a,z,b in line.text_regions)) for line in page.lines]
    assert detect_caption_rules(objects,[13],document)["13"]["findings"]
