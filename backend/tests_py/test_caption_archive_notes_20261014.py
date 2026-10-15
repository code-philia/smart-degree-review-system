"""Real native source pages: caption continuations and legends are not body prose."""
from dataclasses import fields, replace
from pathlib import Path
import json
import pytest
from pdf_rules.model import PdfDocument, PdfLine, PdfPage
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.caption_rules import _body_between, detect_caption_rules

CASES=json.loads(Path(__file__).with_name("caption_archive_notes_20261014.json").read_text())
LINE_FIELDS={f.name for f in fields(PdfLine)}-{"page_number","page_width","page_height"}

def context(case, target, caption):
    return [target,caption]+[LayoutObject(**o) for o in case["annotation_objects"]]

def sample(case):
    lines=[PdfLine(page_number=case["page"],page_width=case["width"],page_height=case["height"],
                   **{k:v for k,v in line.items() if k in LINE_FIELDS}) for line in case["lines"]]
    page=PdfPage(case["page"],case["width"],case["height"],lines)
    target=LayoutObject(**case["target"]);caption=LayoutObject(**case["caption"])
    return target,caption,PdfDocument("real-source-snapshot.pdf",[page])

@pytest.mark.parametrize("case",CASES,ids=lambda c:"alarm-"+c["alarm_id"]+"-"+c["caption"]["text"][:5])
def test_real_title_and_notes_keep_caption_association(case):
    target,caption,document=sample(case)
    assert not _body_between(target,caption,document,context(case,target,caption))
    assert detect_caption_rules(context(case,target,caption),[14],document)["14"]["findings"]==[]

@pytest.mark.parametrize("case",CASES,ids=lambda c:"alarm-"+c["alarm_id"])
def test_true_missing_caption_still_reports(case):
    target,caption,document=sample(case)
    assert len(detect_caption_rules([target],[14],document)["14"]["findings"])==1

@pytest.mark.parametrize("case",CASES,ids=lambda c:"alarm-"+c["alarm_id"])
def test_body_sized_paragraph_remains_a_boundary(case):
    target,caption,document=sample(case)
    upper,lower=sorted((target,caption),key=lambda x:x.bbox[1])
    page=document.pages[0]
    prose=PdfLine(page.number,"This ordinary intervening paragraph discusses a different object.",
                  (70,upper.bbox[3]+2,520,min(upper.bbox[3]+14,lower.bbox[1]-1)),
                  page.width,page.height,font_size=12,bold=False,block_id=999)
    page.lines.append(prose)
    assert _body_between(target,caption,document,context(case,target,caption))
    assert len(detect_caption_rules(context(case,target,caption),[14],document)["14"]["findings"])==1


def test_real_small_scholarly_prose_is_still_a_boundary():
    case=next(c for c in CASES if c["alarm_id"]=="4")
    target,caption,document=sample(case)
    page=document.pages[0]
    prose=PdfLine(page.number,"尽管本文采用P90尾时延作为性能指标，但该模型具有一般性，也可以很容易扩展到其他指标，例如P95",
                  (65.61,118.32,510.24,127.32),page.width,page.height,
                  font_size=9,bold=False,block_id=999)
    page.lines[:]=[line for line in page.lines if not caption.bbox[3]<=line.bbox[1]<target.bbox[1]]+[prose]
    assert _body_between(target,caption,document,context(case,target,caption))


def test_shared_common_word_does_not_prove_table_note_definition():
    case=next(c for c in CASES if c["alarm_id"]=="7")
    target,caption,document=sample(case)
    page=document.pages[0]
    prose=PdfLine(page.number,"Comparison of Model-based Algorithms and Model-free Algorithms (Agent vs. Adversary)",
                  (100,243,507,252),page.width,page.height,font_size=6.102,bold=False,block_id=999)
    page.lines[:]=[line for line in page.lines if not caption.bbox[3]<=line.bbox[1]<target.bbox[1]]+[prose]
    assert _body_between(target,caption,document,context(case,target,caption))
