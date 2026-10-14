from pathlib import Path
from dataclasses import replace
import pytest
import pymupdf
from pdf_rules.pdf_extract import extract_pdf
from pdf_rules.model import PdfDocument
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.logical_objects import remove_native_label_observations


def actual_label_fixture(tmp_path,extra_ink=False):
    path=tmp_path/'unseen-label-carrier.pdf'
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=840)
        page.insert_text((175,270),'(a) Result',fontsize=12)
        if extra_ink:page.draw_rect(pymupdf.Rect(155,259,165,269),color=(0,0,0),fill=(0,0,0))
        pdf.save(path)
    native=extract_pdf(path);line=next(l for l in native.lines if '(a)' in l.text)
    strip=(150,line.bbox[1]-2,250,line.bbox[3]+2);body=(100,100,300,line.bbox[1]-20)
    page=replace(native.pages[0],images=(body,strip),graphics=())
    doc=PdfDocument(path,(page,))
    parent=LayoutObject('figure',1,body,'',600,840,'image_body')
    marker=LayoutObject('figure',1,strip,'',600,840,'native_figure')
    return doc,parent,marker


def test_a_label_bitmap_is_not_independent_content_when_all_ink_is_native_text(tmp_path):
    doc,parent,marker=actual_label_fixture(tmp_path)
    assert marker not in remove_native_label_observations([parent,marker],doc)


def test_bitmap_containing_real_nontext_ink_keeps_its_own_obligation(tmp_path):
    doc,parent,marker=actual_label_fixture(tmp_path,extra_ink=True)
    assert marker in remove_native_label_observations([parent,marker],doc)


def test_absent_original_or_incomplete_native_character_evidence_cannot_prove_text_only(tmp_path):
    doc,parent,marker=actual_label_fixture(tmp_path)
    incomplete=replace(doc.pages[0],lines=tuple(replace(l,text_regions=()) for l in doc.pages[0].lines))
    doc=replace(doc,pages=(incomplete,))
    assert marker in remove_native_label_observations([parent,marker],doc)
    doc=replace(doc,path=Path('unavailable-original-label.pdf'))
    assert marker in remove_native_label_observations([parent,marker],doc)


@pytest.mark.parametrize('color',[(255,0,0),(0,0,0)])
def test_nontext_bitmap_ink_inside_a_native_character_rectangle_remains_independent(tmp_path,color):
    import io
    from PIL import Image,ImageDraw
    doc,parent,marker=actual_label_fixture(tmp_path)
    line=doc.lines[0];word=line.text.index('Result')
    boxes=[box for start,end,box in line.text_regions if word<=start<len(line.text)]
    x0=min(b[0] for b in boxes)+.5;x1=max(b[2] for b in boxes)-.5
    y0=min(b[1] for b in boxes)+.5;y1=y0+2
    image=Image.new('RGB',(300,round((marker.bbox[3]-marker.bbox[1])*3)),(255,255,255))
    ImageDraw.Draw(image).rectangle(((x0-marker.bbox[0])*3,(y0-marker.bbox[1])*3,
                                    (x1-marker.bbox[0])*3,(y1-marker.bbox[1])*3),fill=color)
    stream=io.BytesIO();image.save(stream,format='PNG');path=tmp_path/'independent-inner-bitmap-ink.pdf'
    with pymupdf.open(doc.path) as pdf:
        pdf[0].insert_image(pymupdf.Rect(marker.bbox),stream=stream.getvalue(),overlay=False)
        pdf.save(path)
    native=extract_pdf(path)
    doc=replace(native,pages=(replace(native.pages[0],images=(parent.bbox,marker.bbox)),))
    assert marker in remove_native_label_observations([parent,marker],doc)


@pytest.mark.parametrize('font',['heit','tiit'])
def test_pure_italic_native_glyph_overhang_does_not_become_independent_bitmap_content(tmp_path,font):
    path=tmp_path/'unseen-italic-label.pdf'
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=840)
        page.insert_text((175,270),'(a) leaf',fontname=font,fontsize=12)
        pdf.save(path)
    native=extract_pdf(path);line=native.lines[0]
    body=(100,100,300,line.bbox[1]-20)
    strip=(line.bbox[0]-2,line.bbox[1]-2,line.bbox[2]+2,line.bbox[3]+2)
    doc=replace(native,pages=(replace(native.pages[0],images=(body,strip)),))
    parent=LayoutObject('figure',1,body,'',600,840,'image_body')
    marker=LayoutObject('figure',1,strip,'',600,840,'native_figure')
    assert marker not in remove_native_label_observations([parent,marker],doc)
