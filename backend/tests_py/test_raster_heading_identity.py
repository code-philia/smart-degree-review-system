"""Rasterized heading glyphs are text; small research figures remain figures."""
from pathlib import Path
import tempfile
import pymupdf
from pdf_rules.pdf_extract import extract_pdf
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules
from pdf_rules.mineru_layout import LayoutObject


def document(prefix, *, split=False):
    folder=tempfile.TemporaryDirectory()
    path=Path(folder.name)/'glyphs.pdf'
    with pymupdf.open() as pdf:
        p=pdf.new_page(width=600,height=840)
        left=100
        texts=list(prefix) if split else [prefix]
        for text in texts:
            with pymupdf.open() as source:
                q=source.new_page(width=16*len(text)+2,height=20)
                q.insert_text((1,16),text,fontsize=16,fontname='china-s')
                png=q.get_pixmap(matrix=pymupdf.Matrix(4,4),alpha=False).tobytes('png')
            width=16*len(text)+2
            p.insert_image((left,120,left+width,140),stream=png)
            left+=width
        p.insert_text((left+8,136),'方法与实验',fontsize=16,fontname='china-s')
        p.insert_text((80,220),'普通正文，用于说明当前方法与实验，正文采用独立字号并保持完整的段落排版。',fontsize=12,fontname='china-s')
        pdf.save(path)
    return folder,path,extract_pdf(path)


def test_raster_chapter_prefix_is_not_an_untitled_figure():
    for prefix in ('第2章','第九章'):
        folder,path,doc=document(prefix)
        try:
            result=detect_caption_rules(prepare_caption_layout([],doc),[13],doc)['13']
            assert result['findings']==[]
        finally:folder.cleanup()


def test_separate_chapter_glyph_images_are_owned_by_the_same_text_row():
    folder,path,doc=document('第3章',split=True)
    try:
        assert detect_caption_rules(prepare_caption_layout([],doc),[13],doc)['13']['findings']==[]
    finally:folder.cleanup()


def test_a_small_diagram_next_to_prose_is_not_exempted_by_size():
    folder,path,doc=document('网络')
    try:
        assert len(detect_caption_rules(prepare_caption_layout([],doc),[13],doc)['13']['findings'])==1
    finally:folder.cleanup()


def test_a_deliberately_captioned_heading_screenshot_remains_a_figure():
    folder,path,doc=document('第2章')
    try:
        box=doc.pages[0].images[0]
        objects=[LayoutObject('figure_caption',1,(100,150,300,165),'图1.2 章节标题样式',600,840)]
        layout=prepare_caption_layout(objects,doc)
        assert any(o.kind=='figure' for o in layout)
    finally:folder.cleanup()


def test_independent_line_ocr_can_confirm_a_bitmap_prefix_the_crop_ocr_missed():
    from unittest.mock import patch
    folder,path,doc=document('第3章',split=True)
    try:
        objects=[LayoutObject('text',1,(98,118,245,143),'第3章 方法与实验',600,840,'title',
                              text_lines=(('第3章 方法与实验',(98,118,245,143)),))]
        with patch('pdf_rules.raster_text._chapter_pixels',return_value=False):
            assert detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)['13']['findings']==[]
    finally:folder.cleanup()


def test_unrelated_line_ocr_cannot_hide_a_small_bitmap():
    from unittest.mock import patch
    folder,path,doc=document('网络')
    try:
        objects=[LayoutObject('text',1,(98,118,245,143),'第3章 其他标题',600,840,'title',
                              text_lines=(('第3章 其他标题',(98,118,245,143)),))]
        with patch('pdf_rules.raster_text._chapter_pixels',return_value=False):
            assert detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)['13']['findings']
    finally:folder.cleanup()


def test_normal_font_directory_entry_can_own_confirmed_chapter_glyphs():
    from dataclasses import replace
    folder,path,doc=document('第3章',split=True)
    try:
        page=doc.pages[0]
        lines=tuple(replace(l,text=l.text+' ........ 17',font_size=12,bold=False) if l.bbox[1]<150 else l for l in page.lines)
        doc=replace(doc,pages=(replace(page,lines=lines),))
        assert detect_caption_rules(prepare_caption_layout([],doc),[13],doc)['13']['findings']==[]
    finally:folder.cleanup()
