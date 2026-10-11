from pathlib import Path
import pymupdf
from pdf_rules.pdf_extract import extract_pdf
PREFIX=Path(__file__).parent/'fixtures/numbered_section_prefix_2_2_4.png'
def make_pdf(path, *, title='Turbulence model', toc=True, heading=True):
 pdf=pymupdf.open()
 for is_toc in [True,False]:
  p=pdf.new_page(width=600,height=800)
  if (is_toc and toc) or (not is_toc and heading):p.insert_image((70,130,94,139),filename=str(PREFIX))
  text='Turbulence model ............... 46' if is_toc else title
  p.insert_text((97,139),text,fontsize=11)
 pdf.save(path)
def test_actual_numeric_prefix_requires_matching_toc_and_heading(tmp_path):
 p=tmp_path/'paired.pdf';make_pdf(p)
 d=extract_pdf(p)
 assert all(not p.images for p in d.pages)
 assert len([l for l in d.lines if l.source=='local_numbered_prefix_ocr'])==2
 assert all(l.text.startswith('2.2.4 ') for l in d.lines)
def test_numbered_bitmap_without_matching_heading_is_not_removed(tmp_path):
 p=tmp_path/'unmatched.pdf';make_pdf(p,title='Different experiment')
 d=extract_pdf(p)
 assert all(p.images for p in d.pages)
def test_missing_heading_prefix_is_never_inferred_from_toc(tmp_path):
 p=tmp_path/'missing.pdf';make_pdf(p,heading=False)
 d=extract_pdf(p)
 assert d.pages[0].images
 assert not any(l.source=='local_numbered_prefix_ocr' for l in d.lines)
def test_standalone_small_bitmap_number_without_toc_retains_figure_identity(tmp_path):
 p=tmp_path/'standalone.pdf';make_pdf(p,toc=False)
 d=extract_pdf(p)
 assert d.pages[1].images
 assert not any(l.source=='local_numbered_prefix_ocr' for l in d.lines)
