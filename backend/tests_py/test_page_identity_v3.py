"""Page resources and administrative forms must not become academic figures."""
import io
from pathlib import Path
import pymupdf
from PIL import Image, ImageDraw
import pytest
from pdf_rules.pdf_extract import extract_pdf
from pdf_rules.model import PdfDocument, PdfLine, PdfPage
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import nonresearch_page, recover_document, prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules


def png(color='white', mark=False, transparent=False):
    image = Image.new('RGB', (100, 100), color)
    if mark:
        ImageDraw.Draw(image).line((10, 80, 90, 15), fill='black', width=3)
    if transparent:
        image = image.convert('RGBA')
        image.putalpha(160)
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()


@pytest.mark.parametrize("transparent", [False, True])
def test_white_background_tiles_and_offpage_instances_keep_real_chart(tmp_path, transparent):
    path = tmp_path / 'tiled.pdf'
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=600, height=800)
        for x in (0, 400, 800):
            for y in (0, 400, 800):
                page.insert_image((x, y, x+401, y+401), stream=png(), keep_proportion=False)
        page.insert_text((60, 80), 'Chapter 2 Experimental results')
        page.insert_image((100, 150, 400, 400), stream=png(mark=True, transparent=transparent), keep_proportion=False)
        page.insert_text((150, 430), 'Figure 2.1 Measurements')
        streams = page.get_contents()
        content = b'\n'.join(pdf.xref_stream(xref) for xref in streams)
        pdf.update_stream(streams[0], b'q 0 0 600 800 re W n\n' + content + b'\nQ')
        page.set_contents(streams[0])
        pdf.save(path)
    document = extract_pdf(path)
    page = document.pages[0]
    assert page.images == ((100.0, 150.0, 400.0, 400.0),)
    assert not page.unreadable
    objects = prepare_caption_layout([], document)
    assert len([obj for obj in objects if obj.kind == 'figure']) == 1
    assert detect_caption_rules(objects, [13], document)['13']['findings'] == []


def test_offpage_instances_do_not_disable_form_clipping(tmp_path):
    path = tmp_path / 'clipped.pdf'
    with pymupdf.open() as source, pymupdf.open() as pdf:
        original = source.new_page(width=600, height=800)
        original.insert_image((0, 0, 600, 800), stream=png('blue'), keep_proportion=False)
        original.insert_image((800, 0, 1000, 200), stream=png('red'))
        page = pdf.new_page(width=600, height=800)
        page.show_pdf_page(pymupdf.Rect(100, 100, 500, 200), source, 0, clip=pymupdf.Rect(0, 0, 600, 150))
        page.insert_text((60, 400), 'Native body text is fully readable.')
        pdf.save(path)
    page = extract_pdf(path).pages[0]
    assert not page.unreadable
    assert len(page.images) == 1
    assert page.images[0] == pytest.approx((100, 100, 500, 200), abs=.1)


def test_partly_offpage_real_image_keeps_visible_fragment(tmp_path):
    path = tmp_path / 'visible-fragment.pdf'
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=600, height=800)
        page.insert_image((-100, 100, 100, 300), stream=png(mark=True))
        page.insert_text((60, 400), 'Native body text is fully readable.')
        pdf.save(path)
    assert extract_pdf(path).pages[0].images == ((0.0, 100.0, 100.0, 300.0),)


def line(text, y, role=''):
    return PdfLine(1, text, (80, y, 520, y+20), 600, 800, role=role)


def test_generic_degree_cover_requires_identity_fields_and_no_research():
    fields = [line('示例大学学位论文', 180), line('姓名：某同学', 400),
              line('学号：2026001', 440), line('导师：某教授', 480), line('专业：计算机', 520)]
    assert nonresearch_page(PdfPage(1, 600, 800, tuple(fields)))
    assert not nonresearch_page(PdfPage(1, 600, 800, tuple(fields + [line('图2.1 实验结果', 620)])))


def test_vector_declaration_title_uses_parsed_title_and_legal_body():
    lines = (line('本人郑重声明：所呈交的学位论文由本人独立完成。', 170),
             line('本人完全知晓本声明的法律后果由本人承担。', 220),
             line('学位论文作者签名：', 300), line('日期：2026年6月', 340))
    page = PdfPage(1, 600, 800, lines, images=((420, 290, 505, 330),))
    objects = [LayoutObject('text', 1, (180, 100, 420, 125), '学位论文原创性声明', 600, 800, 'title')]
    document = recover_document(PdfDocument(Path('form.pdf'), (page,)), objects)
    assert nonresearch_page(document.pages[0])
    assert not any(obj.kind == 'figure' for obj in prepare_caption_layout(objects, document))


def test_quoted_declaration_title_cannot_hide_academic_figure():
    page = PdfPage(1, 600, 800, (line('学位论文原创性声明', 100),
        line('本文分析学位论文声明的分类方法，结果如图2.1所示。', 200),
        line('图2.1 声明分类结果', 500)), images=((100, 250, 500, 470),))
    assert not nonresearch_page(page)

def test_soft_mask_image_uses_the_painted_objects_clip(tmp_path):
    path = tmp_path / 'soft-mask.pdf'
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=600, height=800)
        mask_image = pdf.get_new_xref()
        pdf.update_object(mask_image, '<< /Type /XObject /Subtype /Image /Width 10 /Height 10 /ColorSpace /DeviceGray /BitsPerComponent 8 >>')
        pdf.update_stream(mask_image, bytes([120, 255] * 50))
        form = pdf.get_new_xref()
        pdf.update_object(form, f'<< /Type /XObject /Subtype /Form /BBox [0 0 600 800] /Group << /S /Transparency /CS /DeviceGray >> /Resources << /XObject << /MaskImage {mask_image} 0 R >> >> >>')
        pdf.update_stream(form, b'q 600 0 0 800 0 0 cm /MaskImage Do Q')
        gs = pdf.get_new_xref()
        pdf.update_object(gs, f'<< /Type /ExtGState /SMask << /S /Luminosity /G {form} 0 R >> >>')
        resources = int(pdf.xref_get_key(page.xref, 'Resources')[1].split()[0])
        pdf.xref_set_key(resources, 'ExtGState', f'<< /MaskState {gs} 0 R >>')
        stream = pdf.get_new_xref()
        pdf.update_object(stream, '<< >>')
        pdf.update_stream(stream, b'q 100 600 200 100 re W n /MaskState gs 0 0 1 rg 0 0 600 800 re f Q')
        page.set_contents(stream)
        page.insert_text((60, 400), 'Native body remains fully readable.')
        pdf.save(path)
    page = extract_pdf(path).pages[0]
    assert not page.unreadable
    assert page.images == ((100.0, 100.0, 300.0, 200.0),)


@pytest.mark.parametrize("clip",[False,True])
def test_white_rgb_with_variable_alpha_keeps_visible_plot(tmp_path,clip):
    path=tmp_path/'white-alpha.pdf'
    image=Image.new('RGBA',(100,100),(255,255,255,64))
    ImageDraw.Draw(image).line((10,80,90,15),fill=(255,255,255,255),width=3)
    stream=io.BytesIO();image.save(stream,format='PNG')
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=800)
        page.draw_rect((100,100,400,400),color=None,fill=(0,0,0))
        page.insert_image((100,100,400,400),stream=stream.getvalue())
        if clip:
            streams=page.get_contents()
            data=b'\n'.join(pdf.xref_stream(x) for x in streams)
            pdf.update_stream(streams[0],b'q 0 0 600 800 re W n\n'+data+b'\nQ')
            page.set_contents(streams[0])
        pdf.save(path)
    assert extract_pdf(path).pages[0].images==((100.0,100.0,400.0,400.0),)
