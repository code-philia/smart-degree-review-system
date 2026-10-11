from dataclasses import replace
import pytest
from test_usage_short_reference_tail_20261011 import row
from pathlib import Path
from pdf_rules.model import PdfPage,PdfDocument,DocumentIndex,Label
from pdf_rules.local_rules import detect_rules

def example(reference=True, independent=False, continuation=True):
    before=row('模型分析中使用了多种计算方法进行实验数据比较。',(84,180,550,196))
    start=row('图7-4 将',(108,200,165,216))
    right=row('=0.075工况下的阻力和运动时历曲线结合在一起，',(183,200,550,216))
    after=row('研究三者之间的关系，计算结果说明模型具有较高可靠性。',(84,220,550,236))
    cap=replace(row('图7-4 运动时历曲线',(180,600,420,614),page=2,size=10),source='local_caption_prefix_ocr')
    lines=[before,after]+([start]+([right] if continuation else []) if reference else [])
    images=((95,140,178,195),) if independent else ()
    pages=(PdfPage(1,600,800,tuple(lines),images=images),PdfPage(2,600,800,(cap,),images=((80,390,520,580),)))
    return DocumentIndex(PdfDocument(Path('none.pdf'),pages),figures=([Label('7.4',start,'body')] if reference else [])+[Label('7.4',cap,'body')])

def test_formula_split_body_reference_reaches_literal_ocr_title():
    assert not detect_rules(example(),[15])['15']['findings']

@pytest.mark.parametrize('kw',[{'reference':False},{'independent':True},{'continuation':False}])
def test_no_body_evidence_preserves_true_title_obligation(kw):
    assert detect_rules(example(**kw),[15])['15']['findings']
