"""Native English publication-list headings with typography below the large-title threshold."""
import copy
from pathlib import Path
import sys
import pytest
import pymupdf

sys.path[:0] = [str(Path(__file__).resolve().parents[1])]
from paper_compiler.frontend import _build_source_tree
from paper_compiler.local_checks import detect_ir

PART = '学术论文和科研成果目录'
TITLE = 'List of Publications'

def native_ir(tmp_path, *, size=14.04, bold=True, centered=True, y=110, prior=False,
              following='As first author:', header_only=False):
    pdf = tmp_path / 'understated-publications.pdf'
    with pymupdf.open() as doc:
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 120), 'References', fontsize=18, fontname='tibo')
        page.insert_text((72, 180), '393. Author. A real journal article[J]. Journal of Tests, 2026.', fontsize=12, fontname='tiro')
        page = doc.new_page(width=612, height=792)
        page.insert_text((260, 60), TITLE, fontsize=12, fontname='tiro')
        if prior:
            page.insert_text((72, 155), 'This preceding reference continues as ordinary body text.', fontsize=12, fontname='tiro')
        if not header_only:
            font = 'tibo' if bold else 'tiro'
            width = pymupdf.get_text_length(TITLE, fontname=font, fontsize=size)
            page.insert_text(((612-width)/2 if centered else 72, y), TITLE, fontsize=size, fontname=font)
            page.insert_text((72, y+35), following, fontsize=12, fontname='tibo')
            page.insert_text((72, y+65), '1) Author. Published research article. Journal of Tests, 2026.', fontsize=12, fontname='tiro')
        doc.save(pdf)
    return _build_source_tree(pdf, include_citations=False)

def missing(ir):
    return [f for f in detect_ir(ir, [34])['34']['findings'] if f['token'] == PART]

@pytest.mark.parametrize('size', [14.04, 12.0])
def test_centered_bold_english_publication_heading_is_recovered(tmp_path, size):
    ir = native_ir(tmp_path, size=size)
    before = copy.deepcopy(ir)
    assert not any(n['kind']=='Heading' and n.get('text','').strip()==TITLE for n in ir['nodes'])
    assert missing(ir) == []
    assert ir == before

@pytest.mark.parametrize('following', ['As co-author:', '1) Author. A published paper[J]. Journal, 2026.', '[1] Author. A published paper[J]. Journal, 2026.'])
def test_publication_list_context_is_accepted(tmp_path, following):
    assert missing(native_ir(tmp_path, following=following)) == []

@pytest.mark.parametrize('options', [
    {'bold':False}, {'centered':False}, {'size':10.0}, {'y':60},
    {'prior':True,'y':260}, {'header_only':True},
    {'following':'Journal of Tests, volume20, pp12-18.'},
])
def test_heading_like_reference_text_does_not_hide_missing_directory(tmp_path, options):
    assert len(missing(native_ir(tmp_path, **options))) == 1

def test_partial_bold_is_not_a_publication_heading(tmp_path):
    ir = native_ir(tmp_path)
    line = next(line for line in ir['layout']['pages'][1]['lines'] if line['font_size'] > 13)
    for char in line['chars'][1:]:
        char['flags'] &= ~16
    assert len(missing(ir)) == 1

def test_deleted_live_title_is_not_recovered_from_pdf_observations(tmp_path):
    ir = native_ir(tmp_path)
    for node in ir['nodes']:
        if node.get('text'):
            node['text'] = node['text'].replace(TITLE, 'Some Other Material')
    assert len(missing(ir)) == 1
