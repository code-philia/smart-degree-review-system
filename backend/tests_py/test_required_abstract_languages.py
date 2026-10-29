"""Required abstract languages must be checked independently using native IR."""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from paper_compiler.frontend import build_paper
from paper_compiler.local_checks import compact, detect_ir
from test_fast_local_checks import sample_ir


def without_heading(ir, names):
    removed = {n['id'] for n in ir['nodes'] if compact(n.get('text')) in names}
    ir['nodes'] = [n for n in ir['nodes'] if n['id'] not in removed]
    for node in ir['nodes']:
        node['children'] = [nid for nid in node['children'] if nid not in removed]
    return ir


def with_english_heading(ir, kind='Heading', text='Abstract'):
    without_heading(ir, {'abstract', '英文摘要'})
    node = copy.deepcopy(next(n for n in sample_ir()['nodes'] if n['id'] == 'abstract-heading'))
    node.update(id='english-abstract-heading', kind=kind, text=text)
    node['provenance'][0].update(bbox=[60, 240, 200, 260], node_text_end=len(text))
    ir['nodes'].append(node)
    return ir


def tokens(ir):
    return [f['token'] for f in detect_ir(ir, [34])['34']['findings']]


def test_chinese_abstract_does_not_replace_english_abstract():
    ir = without_heading(sample_ir(), {'abstract', '英文摘要'})
    assert tokens(ir) == ['英文摘要']


def test_english_abstract_does_not_replace_chinese_abstract():
    ir = with_english_heading(without_heading(sample_ir(), {'摘要', '中文摘要'}))
    assert tokens(ir) == ['摘要']


def test_both_abstracts_are_required_when_both_missing():
    ir = without_heading(sample_ir(), {'摘要', '中文摘要', 'abstract', '英文摘要'})
    assert tokens(ir) == ['摘要', '英文摘要']


def test_contents_entry_does_not_supply_missing_english_abstract():
    ir = without_heading(sample_ir(), {'abstract', '英文摘要'})
    with_english_heading(ir, kind='ToCEntry')
    assert tokens(ir) == ['英文摘要']


def test_complete_bilingual_abstracts_pass():
    ir = without_heading(sample_ir(), {'abstract', '英文摘要'})
    assert tokens(with_english_heading(ir)) == []


def test_spaced_uppercase_english_heading_is_recognized():
    ir = without_heading(sample_ir(), {'abstract', '英文摘要'})
    assert tokens(with_english_heading(ir, text='A B S T R A C T')) == []


def test_real_draft_reports_missing_english_abstract():
    import pytest
    pdf = Path('/data/results/false-positive-20261029/90b6e38f-00b4-4a28-9c1a-2c7a26432f33.pdf')
    if not pdf.exists():
        pytest.skip('optional original PDF regression fixture')
    ir = build_paper(pdf, include_citations=False)
    assert '英文摘要' in tokens(ir)
    assert '摘要' not in tokens(ir)
