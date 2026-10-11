from pathlib import Path
import pytest
from pdf_rules.model import PdfLine,PdfPage,PdfDocument,DocumentIndex,Label
from pdf_rules.local_rules import detect_rules
from pdf_rules.usage_reference_evidence import recover_usage_index

def row(text, box, page=1, size=12):
    return PdfLine(page,text,box,600,800,font_size=size,text_regions=((0,len(text),box),),block_id=int(box[1]))

def example(*, next_page=False, intro=True, independent=False, with_reference=True):
    first=row('本研究所得计算结果和模型验证的详细对比分别展示在表7-3 和',(84,200,550,216))
    tail=row('图7-4 当中。',(60,220,150,236))
    cap=row('图7-4 模型验证结果',(180,600,420,614),page=2 if next_page else 1,size=10)
    lines=([first] if intro else [])+([tail] if with_reference else [])
    figures=([Label('7.4',tail,'body')] if with_reference else [])+[Label('7.4',cap,'body')]
    images=((40,170,170,215),) if independent else ()
    if next_page:
        pages=(PdfPage(1,600,800,tuple(lines),images=images),PdfPage(2,600,800,(cap,),images=((80,390,520,580),)))
    else:
        pages=(PdfPage(1,600,800,tuple(lines+[cap]),images=images+((80,390,520,580),)),)
    return DocumentIndex(PdfDocument(Path('not-on-disk.pdf'),pages),figures=figures)

@pytest.mark.parametrize('next_page',[False,True])
def test_short_typed_tail_is_body_reference_to_same_or_next_page(next_page):
    ix=example(next_page=next_page)
    out=recover_usage_index(ix,explicit_only=True)
    assert len(out.figures)==1
    assert not detect_rules(ix,[15])['15']['findings']

@pytest.mark.parametrize('intro,independent',[(False,False),(True,True)])
def test_words_alone_cannot_discard_independent_caption(intro,independent):
    ix=example(intro=intro,independent=independent)
    out=recover_usage_index(ix,explicit_only=True)
    assert len(out.figures)==2
    assert len(detect_rules(ix,[15])['15']['findings'])==2

def test_without_body_typed_tail_true_target_still_warns():
    findings=detect_rules(example(with_reference=False),[15])['15']['findings']
    assert [(f['token'],f['page']) for f in findings]==[('7.4',1)]
