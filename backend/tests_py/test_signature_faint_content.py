"""Source render regressions: faint body text and body bar charts remain evidence."""
import numpy as np
import pymupdf
import pytest
from pdf_rules.local_ocr import signature_remainder_view


@pytest.mark.parametrize('fontsize',[4,5,6])
def test_uniform_one_level_faint_body_reference_is_not_erased(fontsize):
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=800)
        page.insert_text((80,650),'See Figure 5.3.',fontsize=fontsize,color=(254/255,)*3)
        pix=page.get_pixmap(matrix=pymupdf.Matrix(3,3),colorspace=pymupdf.csGRAY,alpha=False)
        gray=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width)
    assert np.count_nonzero(gray<255)>0
    view,guards,_=signature_remainder_view(gray,3,[(60,100,540,400)])
    assert np.count_nonzero(view<255)>0
    assert guards, 'An undecoded faint text line cannot be declared blank paper'


@pytest.mark.parametrize('vertical',[True,False])
def test_twelve_equal_body_bars_are_not_a_page_margin_barcode(vertical):
    gray=np.full((800,600),255,np.uint8)
    for i in range(12):
        if vertical:gray[500:520,160+4*i:163+4*i]=0
        else:gray[500+4*i:503+4*i,160:180]=0
    view,guards,artifacts=signature_remainder_view(gray,1,[(60,100,540,400)])
    assert np.count_nonzero(view<255)==np.count_nonzero(gray<255)
    assert guards, 'Unexplained body graphics must remain unread, not become a clean page'
    assert not any(a['kind']=='parallel_barcode_bars' for a in artifacts)


def test_real_top_margin_barcode_still_has_positive_artifact_evidence():
    gray=np.full((800,600),255,np.uint8)
    for i in range(24):gray[12:32,430+2*i:431+2*i]=0
    view,guards,artifacts=signature_remainder_view(gray,1,[(60,100,540,400)])
    assert not np.count_nonzero(view<255)
    assert not guards
    assert any(a['kind']=='parallel_barcode_bars' for a in artifacts)


def test_barcode_on_rotated_display_header_is_still_an_artifact():
    gray=np.full((600,800),255,np.uint8)
    for i in range(24):gray[430+2*i:431+2*i,12:32]=0
    view,guards,artifacts=signature_remainder_view(gray,1,[],display_rotation=90)
    assert not np.count_nonzero(view<255)
    assert not guards
    assert any(a['kind']=='parallel_barcode_bars' for a in artifacts)


def test_raw_top_bars_rotated_into_body_edge_do_not_become_header_artifacts():
    gray=np.full((600,800),255,np.uint8)
    for i in range(24):gray[12:32,430+2*i:431+2*i]=0
    view,guards,artifacts=signature_remainder_view(gray,1,[],display_rotation=90)
    assert np.count_nonzero(view<255)==np.count_nonzero(gray<255)
    assert guards
    assert not any(a['kind']=='parallel_barcode_bars' for a in artifacts)


@pytest.mark.parametrize('text',['Fig. 1','See App. Z','Table 1','图1','表1','附录Z'])
@pytest.mark.parametrize('fontsize',[4,5,6])
def test_short_faint_references_remain_text_candidates(text,fontsize):
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=800)
        page.insert_text((100,650),text,fontsize=fontsize,color=(254/255,)*3,
                         fontname='china-s' if any(ord(c)>127 for c in text) else 'helv')
        pix=page.get_pixmap(matrix=pymupdf.Matrix(3,3),colorspace=pymupdf.csGRAY,alpha=False)
        gray=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width)
    assert np.count_nonzero(gray<255)>0
    view,guards,_=signature_remainder_view(gray,3,[(60,100,540,400)])
    assert np.count_nonzero(view<255)>0
    assert guards, 'A short faint body reference cannot be mistaken for blank paper'


@pytest.mark.parametrize('top',[402,405,410])
@pytest.mark.parametrize('vertical',[True,False])
def test_body_bars_just_outside_form_are_not_grid_borders(top,vertical):
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=800)
        for i in range(12):
            box=(160+4*i,top,162+4*i,top+20) if vertical else (160,top+4*i,180,top+2+4*i)
            page.draw_rect(box,fill=(0,0,0),color=None)
        pix=page.get_pixmap(matrix=pymupdf.Matrix(3,3),colorspace=pymupdf.csGRAY,alpha=False)
        gray=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width)
    view,guards,_=signature_remainder_view(gray,3,[(60,100,540,400)])
    assert np.count_nonzero(view<255)==np.count_nonzero(gray<255)
    assert guards


@pytest.mark.parametrize('font',['helv','hebo','tiro','tibo','cour','cobo'])
@pytest.mark.parametrize('text',['Fig. 1','Table1','See App. Z'])
def test_three_point_faint_references_are_not_blank(text,font):
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=800)
        page.insert_text((100,650),text,fontsize=3,color=(254/255,)*3,fontname=font)
        pix=page.get_pixmap(matrix=pymupdf.Matrix(3,3),colorspace=pymupdf.csGRAY,alpha=False)
        gray=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width)
    assert np.count_nonzero(gray<255)>0
    view,guards,_=signature_remainder_view(gray,3,[(60,100,540,400)])
    assert np.count_nonzero(view<255)>0
    assert guards


def test_close_outer_grid_can_enclose_overlapping_verified_fragments():
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=800)
        page.draw_rect((80,350,483,465),color=(0,0,0),width=.6)
        pix=page.get_pixmap(matrix=pymupdf.Matrix(3,3),colorspace=pymupdf.csGRAY,alpha=False)
        gray=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width)
    fragments=[(198.6,361.8,460.2,464.1),(83.2,366.9,358.8,389.9),
               (83.2,394.9,369.8,421),(256.6,430,369.8,447.1)]
    view,guards,_=signature_remainder_view(gray,3,fragments)
    assert not np.count_nonzero(view<255)
    assert not guards


def _microtexture_reference(text=None,fontsize=4):
    import random
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=800)
        if text:page.insert_text((100,650),text,fontsize=fontsize,color=(254/255,)*3,
                                 fontname='china-s' if any(ord(c)>127 for c in text) else 'helv')
        pix=page.get_pixmap(matrix=pymupdf.Matrix(3,3),colorspace=pymupdf.csGRAY,alpha=False)
        gray=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width).copy()
    rng=random.Random(419)
    for _ in range(1600):
        x=rng.randrange(40,gray.shape[1]-40);y=rng.randrange(40,gray.shape[0]-40)
        if 1850<=y<=2000:continue
        if 300<=y<=1200 and 180<=x<=1620:continue
        w=rng.randrange(2,7);h=rng.randrange(3,10)
        # Low-level scanner remnants, including narrow solid and sparse islands.
        shape=np.random.default_rng(x+y).random((h,w))>.4
        gray[y:y+h,x:x+w][shape]=253
    return gray


def test_widespread_scanner_microtexture_is_not_flat_paper_text_evidence():
    gray=_microtexture_reference()
    _,guards,artifacts=signature_remainder_view(gray,3,[(60,100,540,400)])
    assert not guards
    assert artifacts[-1]['source_flat_paper'] is False


def test_faint_body_reference_on_microtexture_still_has_a_text_guard():
    gray=_microtexture_reference('See Figure 5.3.')
    view,guards,_=signature_remainder_view(gray,3,[(60,100,540,400)])
    assert np.count_nonzero(view[1930:1970,280:450]<255)>0
    assert any(box[1]>640 and box[3]<660 for box in guards)


@pytest.mark.parametrize('text',['Fig. 1','图1','表1'])
def test_three_point_short_reference_on_microtexture_remains_guarded(text):
    gray=_microtexture_reference(text,fontsize=3)
    view,guards,_=signature_remainder_view(gray,3,[(60,100,540,400)])
    assert np.count_nonzero(view[1930:1970,280:450]<255)>0
    assert any(box[1]>640 and box[3]<660 for box in guards)


@pytest.mark.parametrize('font,text',[('cour','Fig. 1'),('cobo','Fig. 1'),('cobo','Table 1')])
def test_separated_faint_reference_below_actual_frame_keeps_every_source_pixel(font,text):
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=800)
        page.draw_rect((60,100,540,400),color=(0,0,0),width=.5)
        page.insert_text((100,402.5),text,fontsize=3,fontname=font,color=(254/255,)*3)
        pix=page.get_pixmap(matrix=pymupdf.Matrix(3,3),colorspace=pymupdf.csGRAY,alpha=False)
        gray=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width)
    faint=np.equal(gray,254)
    assert np.count_nonzero(faint)>0
    assert np.nonzero(faint)[0].min()/3>400
    view,guards,_=signature_remainder_view(gray,3,[(60,100,540,400)])
    assert np.array_equal(view[faint],gray[faint]), 'A grid halo does not own separated exterior letters'
    assert guards


def test_body_bars_connected_to_actual_frame_keep_their_exterior_strokes():
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=800)
        page.draw_rect((60,100,540,400),color=(0,0,0),width=.5)
        for i in range(12):page.draw_rect((160+4*i,400,162+4*i,420),color=None,fill=(0,0,0))
        pix=page.get_pixmap(matrix=pymupdf.Matrix(3,3),colorspace=pymupdf.csGRAY,alpha=False)
        gray=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width)
    view,guards,_=signature_remainder_view(gray,3,[(60,100,540,400)])
    exterior=(slice(402*3,420*3),slice(155*3,210*3))
    assert np.array_equal(view[exterior],gray[exterior]), 'Only the actual frame edge belongs to the form'
    assert guards


@pytest.mark.parametrize('height',[80,350])
def test_long_body_bars_attached_to_frame_remain_original_unread_graphics(height):
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=800)
        page.draw_rect((60,100,540,400),color=(0,0,0),width=.5)
        for i in range(12):page.draw_rect((160+4*i,400,162+4*i,400+height),color=None,fill=(0,0,0))
        pix=page.get_pixmap(matrix=pymupdf.Matrix(3,3),colorspace=pymupdf.csGRAY,alpha=False)
        gray=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width)
    view,guards,_=signature_remainder_view(gray,3,[(60,100,540,400)])
    exterior=(slice(402*3,(400+height)*3),slice(155*3,210*3))
    assert np.array_equal(view[exterior],gray[exterior]), 'Long connected body bars cannot inherit grid ownership'
    assert guards


def _raster_body_bars(vertical,shade):
    with pymupdf.open() as vector:
        page=vector.new_page(width=600,height=800)
        for i in range(12):
            box=(160+4*i,500,162+4*i,520) if vertical else (160,500+4*i,180,502+4*i)
            page.draw_rect(box,color=None,fill=(shade/255,)*3)
        png=page.get_pixmap(matrix=pymupdf.Matrix(3,3),colorspace=pymupdf.csGRAY,alpha=False).tobytes('png')
    with pymupdf.open() as raster:
        page=raster.new_page(width=600,height=800)
        page.insert_image((0,0,600,800),stream=png)
        pdfbytes=raster.tobytes(garbage=4,deflate=True,no_new_id=True)
    with pymupdf.open(stream=pdfbytes,filetype='pdf') as raster:
        assert not raster[0].get_text()
        assert len(raster[0].get_images())==1
        pix=raster[0].get_pixmap(matrix=pymupdf.Matrix(3,3),colorspace=pymupdf.csGRAY,alpha=False)
        return np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width)


@pytest.mark.parametrize('vertical',[True,False])
@pytest.mark.parametrize('shade',[254,249,242])
def test_faint_body_bars_survive_actual_scan_pdf_roundtrip(vertical,shade):
    gray=_raster_body_bars(vertical,shade)
    source_ink=gray<255
    assert np.count_nonzero(source_ink)==4320
    view,guards,artifacts=signature_remainder_view(gray,3,[(60,100,540,400)])
    assert np.array_equal(view[source_ink],gray[source_ink]), 'Low contrast cannot erase repeated body graphics'
    assert guards
    assert not any(a['kind']=='parallel_barcode_bars' for a in artifacts)


@pytest.mark.parametrize('vertical',[True,False])
def test_one_level_body_bars_receive_real_cpu_ocr_without_becoming_blank(vertical):
    from time import monotonic
    from pdf_rules.local_ocr import read_remainder,has_unread_text
    gray=_raster_body_bars(vertical,254)
    view,guards,artifacts=signature_remainder_view(gray,3,[(60,100,540,400)])
    observations=[]
    hits,tiles=read_remainder(view,3,deadline=monotonic()+30,observations=observations,
        guard_boxes=guards,source_flat_paper=artifacts[-1]['source_flat_paper'])
    assert tiles>0, 'An all-white temporary view must not bypass real CPU OCR'
    assert has_unread_text(hits), 'Undecoded body graphics cannot become a clean completed page'
