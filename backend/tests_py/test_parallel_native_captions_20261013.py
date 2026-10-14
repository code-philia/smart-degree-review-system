"""Shared PDF baselines need independent physical and native character proof."""
from pathlib import Path
from dataclasses import replace

from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules
from pdf_rules.model import PdfDocument, PdfLine, PdfPage
from pdf_rules.reference_identity_repair import repair_reference_identity


def caption_pair(kind='figure', *, owners=True, regions=True, gap=120):
    word = '图' if kind == 'figure' else '表'
    first = f'{word}8-7 联合水槽[82]'
    second = f'{word}8-8 内流施加装置[83]'
    text = first + ' ' * 20 + second
    boxes = []
    for i, char in enumerate(text):
        if i < len(first):
            x = 110 + i * 5
        elif i >= len(first) + 20:
            x = 110 + len(first) * 5 + gap + (i-len(first)-20) * 5
        else:
            x = 110 + len(first) * 5 + (i-len(first)) * gap/20
        boxes.append((i, i+1, (x, 610, x+5, 622)))
    line = PdfLine(1, text, (110, 610, boxes[-1][2][2], 622), 600, 840,
        text_regions=tuple(boxes) if regions else (), font_size=10)
    body = PdfLine(1, '两套装置分别见图8-7和图8-8。', (70,110,400,124),600,840,font_size=12)
    objects = ((80,460,260,602),(300,460,510,602)) if owners else ((80,460,510,602),)
    page = PdfPage(1,600,840,(body,line), images=objects if kind=='figure' else (),
                   tables=tuple((a,640,b,790) for a,_,b,_ in objects) if kind=='table' else ())
    return PdfDocument(Path('unseen-parallel.pdf'),(page,)), line


def extract_fragments(doc):
    from pdf_rules.parallel_captions import recover_parallel_native_captions
    return recover_parallel_native_captions(doc)


def test_second_parallel_title_resolves_an_existing_reference():
    doc, first = caption_pair()
    recovered = extract_fragments(doc)
    index = repair_reference_identity(build_index(recovered))
    assert {label.number for label in index.figures} == {'8.7','8.8'}
    assert detect_rules(index,[11])['11']['findings'] == []
    assert recovered.pages[0].lines[1] == first
    assert next(label for label in index.figures if label.number=='8.7').line.bbox == first.bbox


def test_parallel_title_does_not_reference_itself_when_body_usage_is_deleted():
    doc, _ = caption_pair()
    doc = replace(doc,pages=(replace(doc.pages[0], lines=doc.pages[0].lines[1:]),))
    index = repair_reference_identity(build_index(extract_fragments(doc)))
    result = detect_rules(index,[15])['15']
    assert result['status'] == 'completed'
    assert sorted(f['token'] for f in result['findings']) == ['8.7','8.8']


def test_two_mentions_in_one_composite_are_not_two_main_titles():
    doc, _ = caption_pair(owners=False)
    assert extract_fragments(doc) == doc


def test_unmeasured_or_narrow_space_cannot_establish_parallel_titles():
    for kwargs in ({'regions':False}, {'gap':4}):
        doc, _ = caption_pair(**kwargs)
        assert extract_fragments(doc) == doc


def test_parallel_tables_have_the_same_independent_geometry_requirement():
    doc, _ = caption_pair('table')
    doc = replace(doc,pages=(replace(doc.pages[0], lines=doc.pages[0].lines[1:]),))
    index = repair_reference_identity(build_index(extract_fragments(doc)))
    assert sorted(f['token'] for f in detect_rules(index,[16])['16']['findings']) == ['8.7','8.8']


def test_a_comparison_in_one_caption_stays_a_reference():
    text='图8-7 与图8-8比较'
    line=PdfLine(1,text,(100,610,270,622),600,840,font_size=10,
        text_regions=tuple((i,i+1,(100+i*5,610,105+i*5,622)) for i in range(len(text))))
    page=PdfPage(1,600,840,(line,),images=((80,460,260,602),(300,460,510,602)))
    doc=PdfDocument(Path('unseen-comparison.pdf'),(page,))
    assert extract_fragments(doc)==doc
