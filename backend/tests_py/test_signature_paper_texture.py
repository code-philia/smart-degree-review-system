import numpy as np
from pdf_rules.local_ocr import signature_remainder_view, has_unread_text, OcrText


def test_pixel_guard_requires_original_uniform_paper_and_retains_ocr_pixels():
    gray=np.full((400,300),250,dtype=np.uint8)
    gray[:200]=249
    gray[240:250,100:106]=248
    view,guards,artifacts=signature_remainder_view(gray,1,[])
    assert not guards
    assert view[240:250,100:106].min()==248
    evidence=next(a for a in artifacts if a['kind']=='scan_background_and_isolated_speckles')
    assert evidence['source_flat_paper'] is False


def test_the_same_faint_island_on_uniform_paper_is_still_unread():
    gray=np.full((400,300),250,dtype=np.uint8)
    gray[240:250,100:106]=248
    view,guards,artifacts=signature_remainder_view(gray,1,[])
    assert guards
    assert view[240:250,100:106].min()==248


def test_strong_undecoded_ocr_detection_remains_unread_on_textured_paper():
    assert has_unread_text([OcrText('',0,(10,10,40,25),.95)])


def test_sparse_ocr_tiles_crop_blank_padding_without_moving_read_text():
    from unittest.mock import patch
    from pdf_rules.local_ocr import read_remainder
    from time import monotonic
    gray=np.full((600,600),255,dtype=np.uint8)
    gray[75:85,70:100]=0
    gray[510:520,480:510]=0
    shapes=[]
    def reader(tile):
        shapes.append(tile.shape)
        ys,xs=np.nonzero(tile<255)
        if not len(xs):return []
        return [OcrText('图9.9',1,(float(xs.min()),float(ys.min()),float(xs.max()+1),float(ys.max()+1)),1)]
    with patch('pdf_rules.local_ocr._read_tile',side_effect=reader):
        hits,_=read_remainder(gray,1,deadline=monotonic()+20,guard_boxes=[])
    assert shapes and all(h<=70 and w<=75 for h,w in shapes)
    assert {(h.bbox[0],h.bbox[1],h.bbox[2],h.bbox[3]) for h in hits}=={(70,75,100,85),(480,510,510,520)}
