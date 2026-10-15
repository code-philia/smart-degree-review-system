"""Painted pattern instances must not revive clipped PDF image resources."""
import base64
import io
import pymupdf
from PIL import Image
import pytest
from pdf_rules.visible_images import visible_images


def bitmap(color="blue"):
    stream=io.BytesIO()
    Image.new("RGB",(20,20),color).save(stream,format="PNG")
    return stream.getvalue()


def patterned_page(pdf):
    page=pdf.new_page(width=600,height=800)
    hidden=page.insert_image((400,300,500,400),stream=bitmap("red"))
    real=page.insert_image((80,100,180,200),stream=bitmap("blue"))
    # Reuse a real image resource in a native PDF tiling pattern.
    pattern=pdf.get_new_xref()
    pdf.update_object(pattern,f"<< /Type /Pattern /PatternType 1 /PaintType 1 /TilingType 1 /BBox [0 0 20 20] /XStep 20 /YStep 20 /Resources << /XObject << /Tile {real} 0 R >> >> >>")
    pdf.update_stream(pattern,b"q 20 0 0 20 0 0 cm /Tile Do Q")
    resources=int(pdf.xref_get_key(page.xref,"Resources")[1].split()[0])
    pdf.xref_set_key(resources,"Pattern",f"<< /Painted {pattern} 0 R >>")
    contents=page.get_contents()
    hidden_data=pdf.xref_stream(contents[0])
    real_data=pdf.xref_stream(contents[1])
    # The first image is inside the viewport but completely outside its clip.
    stream=pdf.get_new_xref();pdf.update_object(stream,"<< >>")
    pdf.update_stream(stream,b"q 10 10 20 20 re W n\n"+hidden_data+b"\nQ\n"+real_data+b"\nq /Pattern cs /Painted scn 200 500 60 40 re f Q")
    page.set_contents(stream)
    return page


def test_pattern_paint_does_not_restore_a_completely_clipped_image():
    with pymupdf.open() as pdf:
        page=patterned_page(pdf)
        fallback=tuple(tuple(pymupdf.Rect(i["bbox"]) & page.rect) for i in page.get_image_info() if not (pymupdf.Rect(i["bbox"]) & page.rect).is_empty)
        result=visible_images(page,fallback)
        assert not any(pymupdf.Rect(b).intersects(pymupdf.Rect(400,300,500,400)) for b in result)
        assert any(b==pytest.approx((80,100,180,200),abs=.1) for b in result)
        # A tiled texture owns the painted region, rather than its first tile.
        assert any(b==pytest.approx((200,260,260,300),abs=.1) for b in result)


class SvgPage:
    rotation=0
    rect=pymupdf.Rect(0,0,600,800)
    def __init__(self,svg,count):self.svg,self.count=svg,count
    def get_image_info(self,xrefs=False):return [{"bbox":(0,0,600,800),"xref":0} for _ in range(self.count)]
    def get_cdrawings(self,extended=True):return [{"type":"clip"}]
    def get_svg_image(self,text_as_path=False):return self.svg


def svg_pattern(reference="#tile",units="userSpaceOnUse",consumer='rect x="100" y="200" width="50" height="60"'):
    data=base64.b64encode(bitmap()).decode()
    return f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><defs><image id="tile" width="20" height="20" xlink:href="data:image/png;base64,{data}"/><pattern id="paint" patternUnits="{units}" patternContentUnits="userSpaceOnUse" width="20" height="20"><use xlink:href="{reference}"/></pattern></defs><{consumer} fill="url(#paint)"/></svg>'


def test_supported_pattern_paint_keeps_its_whole_consumer_region():
    fallback=((0,0,20,20),)
    assert visible_images(SvgPage(svg_pattern(),1),fallback)==((100.0,200.0,150.0,260.0),)


@pytest.mark.parametrize("svg",[svg_pattern("#unknown"),svg_pattern(units="objectBoundingBox"),svg_pattern(consumer='path d="M100 200 C120 100 170 240 150 260 Z"')])
def test_unknown_or_unsupported_pattern_keeps_conservative_fallback(svg):
    fallback=((0,0,20,20),)
    assert visible_images(SvgPage(svg,1),fallback)==fallback


def test_no_silent_loss_when_the_display_list_still_contains_unparsed_images():
    fallback=((0,0,20,20),(300,400,350,450))
    assert visible_images(SvgPage(svg_pattern(),2),fallback)==fallback
