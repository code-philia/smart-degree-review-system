from pathlib import Path
import pymupdf
import numpy as np
from PIL import Image
import io
from pdf_rules.pdf_extract import extract_pdf
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules


def make_pdf(path,alpha=3,count=3,real_figure=False):
    pixels=np.zeros((420,300,4),dtype=np.uint8)
    pixels[:,:,:3]=[255,255,85];pixels[:,:,3]=alpha
    stream=io.BytesIO();Image.fromarray(pixels).save(stream,format='PNG')
    pdf=pymupdf.open();xref=0
    for i in range(count):
        p=pdf.new_page(width=600,height=840)
        xref=p.insert_image(p.rect,stream=stream.getvalue(),xref=xref)
        p.insert_text((80,130),'Normal original thesis text and document content.',fontsize=12)
        if real_figure and i==0:
            draw=np.zeros((50,80,3),dtype=np.uint8);draw[:,:,0]=80
            pic=io.BytesIO();Image.fromarray(draw).save(pic,format='PNG')
            p.insert_image((100,300,260,400),stream=pic.getvalue())
    pdf.save(path);pdf.close()
    return extract_pdf(path)


def test_repeated_uniform_low_opacity_full_page_layer_is_a_decoration(tmp_path):
    doc=make_pdf(tmp_path/'layer.pdf')
    assert detect_caption_rules(prepare_caption_layout([],doc),[13],doc)['13']['findings']==[]


def test_independent_untitled_figure_above_a_repeated_canvas_remains(tmp_path):
    doc=make_pdf(tmp_path/'layer.pdf',real_figure=True)
    found=detect_caption_rules(prepare_caption_layout([],doc),[13],doc)['13']['findings']
    assert len(found)==1
    assert found[0]['location']['bounding_rect']['y1']==300


def test_single_faint_scientific_image_is_not_removed_for_low_opacity(tmp_path):
    doc=make_pdf(tmp_path/'single.pdf',count=1)
    assert detect_caption_rules(prepare_caption_layout([],doc),[13],doc)['13']['findings']


def test_repeated_opaque_image_is_not_a_low_opacity_decoration(tmp_path):
    doc=make_pdf(tmp_path/'opaque.pdf',alpha=255)
    assert len(detect_caption_rules(prepare_caption_layout([],doc),[13],doc)['13']['findings'])==3


def test_proven_background_layer_does_not_make_an_otherwise_native_page_unreadable(tmp_path):
    from pdf_rules.decorative_layers import remove_decorative_layers
    doc=make_pdf(tmp_path/'layer.pdf')
    assert any(p.unreadable for p in doc.pages)
    _,clean=remove_decorative_layers([],doc)
    assert all(not p.unreadable for p in clean.pages)


def test_small_images_do_not_require_decoding_hashes(tmp_path, monkeypatch):
    from pdf_rules.decorative_layers import _canvases
    path=tmp_path/'small.pdf'
    with pymupdf.open() as pdf:
        p=pdf.new_page(width=600,height=840)
        pic=io.BytesIO();Image.new('RGB',(80,50),'red').save(pic,format='PNG')
        p.insert_image((100,300,260,400),stream=pic.getvalue())
        pdf.save(path)
    original=pymupdf.Page.get_image_info
    calls=[]
    def traced(page, hashes=False, xrefs=False):
        calls.append((hashes,xrefs))
        return original(page,hashes=hashes,xrefs=xrefs)
    monkeypatch.setattr(pymupdf.Page,'get_image_info',traced)
    stat=path.stat()
    assert _canvases(str(path),stat.st_mtime_ns,stat.st_size)=={}
    assert calls and not any(hashes or xrefs for hashes,xrefs in calls)
