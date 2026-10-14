"""Actual raster paper texture must not manufacture unread body text.

These optional corpus fixtures are original rendered pixels, individually
reviewed in the independent audit; no detector-generated expected labels.
"""
import json
from pathlib import Path
import numpy as np
from PIL import Image
import pytest
from pdf_rules.local_ocr import signature_remainder_view


@pytest.mark.parametrize('ident,page',[(239,146),(273,180),(277,142),(294,261),(309,180)])
def test_visually_verified_paper_texture_cannot_manufacture_text_guards(ident,page):
    root=Path(__file__).resolve().parents[3]
    case=root/'output/full_detector_repair_20261009/signature-review-recheck/attempt02/cases'/f'{ident:03}'
    if not case.is_dir():
        pytest.skip('Independent actual-page evidence is unavailable')
    manifest=json.loads((case/'worker-manifest.json').read_text(encoding='utf8'))
    picture=next(p for p in manifest['original_source_pixels'] if p['page']==page)
    data=json.loads((case/f'{ident:03}-repair-page-check.json').read_text(encoding='utf8'))
    evidence=next(e for e in data['evidence'] if e['page']==page)
    original=np.asarray(Image.open(picture['path']).convert('L'))
    view,guards,_=signature_remainder_view(original,picture['scale'],evidence['administrative_regions'])
    assert not guards, 'Paper clouds and narrow scanner creases are not undecoded body letters'
    assert np.count_nonzero(view!=np.bincount(original.ravel(),minlength=256).argmax()), 'Actual retained ink still reaches OCR'
