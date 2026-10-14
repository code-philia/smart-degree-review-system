from pathlib import Path
import pytest
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules


def line(text,box):return PdfLine(1,text,box,600,800)


def run(reference,graphics,layout=()):
    ls=(line(reference,(105,235,310,247)),line('图7.2 终端输出',(200,460,400,472)))
    page=PdfPage(1,600,800,ls,images=((80,270,520,450),),graphics=graphics)
    return detect_rules(build_index(PdfDocument(Path('unseen.pdf'),(page,)),layout),[11,15])


def test_short_body_reference_separates_code_background_from_figure():
    r=run('检测输出示例如图7.2所示。',((80,200,520,220),))
    assert r['15']['findings']==[]


def test_missing_reference_in_short_body_is_not_hidden_by_expanded_graphic():
    r=run('检测输出示例如图7.9所示。',((80,200,520,220),))
    assert [f['token'] for f in r['11']['findings']]==['7.9']


def test_captioned_diagram_internal_sentence_is_still_excluded():
    r=run('处理完成后如图7.9所示。',((80,200,520,450),))
    assert r['11']['findings']==[]


def test_cloud_merge_cannot_hide_prose_in_native_gap():
    from pdf_rules.mineru_layout import LayoutObject
    region=LayoutObject('figure',1,(80,195,520,450),'',600,800,role='image_body')
    r=run('检测输出示例如图7.2所示。',((80,200,520,220),),(region,))
    assert r['15']['findings']==[]


def test_cloud_merge_cannot_hide_missing_reference_in_native_gap():
    from pdf_rules.mineru_layout import LayoutObject
    region=LayoutObject('figure',1,(80,195,520,450),'',600,800,role='image_body')
    r=run('检测输出示例如图7.9所示。',((80,200,520,220),),(region,))
    assert [f['token'] for f in r['11']['findings']]==['7.9']
