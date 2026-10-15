"""Production engine must apply identity repairs while preserving real violations."""
from pathlib import Path
from unittest.mock import patch
import pymupdf
from pdf_rules.engine import detect
from pdf_rules.model import PdfDocument, PdfPage, PdfLine


def source(tmp_path, body):
    path=tmp_path/'unseen-original.pdf'
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=800)
        page.draw_rect((80,200,520,400),color=(0,0,0))
        page.insert_text((100,300),'Original measured chart')
        pdf.save(path)
    lines=(PdfLine(1,body,(80,100,520,116),600,800,font_size=12),
           PdfLine(1,'Figure 5.6 Experimental comparison',(130,420,470,434),600,800,font_size=10,bold=True))
    return path,PdfDocument(path,(PdfPage(1,600,800,lines,images=((80,200,520,400),)),))


def test_printed_period_after_figure_recovers_actual_reference_in_engine(tmp_path):
    path,document=source(tmp_path,'As shown in Figure. 5.6, the measured result improves.')
    with patch('pdf_rules.engine.extract_pdf',return_value=document):
        result=detect(path,[11,15])['rules']
    assert result['11']['status']==result['15']['status']=='completed'
    assert not result['11']['findings']
    assert not result['15']['findings']


def test_wrong_literal_number_still_reports_missing_target_and_unused_real_chart(tmp_path):
    path,document=source(tmp_path,'As shown in Figure. 5.9, the measured result improves.')
    with patch('pdf_rules.engine.extract_pdf',return_value=document):
        result=detect(path,[11,15])['rules']
    assert [f['token'] for f in result['11']['findings']]==['5.9']
    assert [f['token'] for f in result['15']['findings']]==['5.6']


def test_caption_self_number_does_not_supply_a_missing_body_reference(tmp_path):
    path,document=source(tmp_path,'The experiment evaluates the independent methods.')
    with patch('pdf_rules.engine.extract_pdf',return_value=document):
        result=detect(path,[11,15])['rules']
    assert not result['11']['findings']
    assert [f['token'] for f in result['15']['findings']]==['5.6']
