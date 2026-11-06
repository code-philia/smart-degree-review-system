"""Partial compilation relaxes section grammar, never document identity."""
import pymupdf
import pytest

from paper_compiler.frontend import build_paper
from check_paper_document import check_document
from test_paper_structure_compilation import thesis
from test_document_admission import pdf_with_text


@pytest.mark.parametrize('heading,section', [
    ('摘要', '摘要'), ('Abstract', '英文摘要'), ('参考文献', '参考文献'),
    ('目录', '目录'), ('第一章 绪论', '引言'), ('第四章 结论', '结论'),
])
def test_partial_compilation_retains_specific_missing_sections(tmp_path, heading, section):
    path = thesis(tmp_path, missing=heading)
    ir = build_paper(path, include_citations=False, allow_incomplete_structure=True)
    assert ir['nodes'][0]['kind'] == 'Paper'
    admission = ir['metadata']['document_admission']
    assert admission['stage'] == 'partial'
    assert admission['status'] == 'accepted'
    assert admission['structure']['missing_sections'] == [section]
    assert admission['structure']['incomplete_sections'] == []
    assert check_document(path)['compiled'] is True


def test_partial_compilation_retains_incomplete_english_abstract(tmp_path):
    path = tmp_path / 'truncated-english-abstract.pdf'
    with pymupdf.open(thesis(tmp_path)) as doc:
        doc[2].add_redact_annot(pymupdf.Rect(40, 760, 550, 810))
        doc[2].apply_redactions()
        doc.save(path)
    proof = check_document(path)
    assert proof['compiled'] is True
    assert proof['stage'] == 'partial'
    assert proof['structure']['missing_sections'] == []
    assert proof['structure']['incomplete_sections'] == ['英文摘要']
    assert '英文摘要（Abstract）不完整' in proof['reason']


def test_compiler_cli_can_explicitly_build_partial_papers_offline(tmp_path):
    import json
    from paper_compiler_cli import parser, execute
    path = thesis(tmp_path, missing='Abstract')
    output = tmp_path / 'partial-ir.json'
    args = parser().parse_args(['build', '--pdf', str(path), '--out', str(output),
        '--allow-incomplete-structure', '--offline', '--cache', str(tmp_path / 'cache'),
        '--ledger', str(tmp_path / 'ledger.sqlite3')])
    pytest.importorskip('re2', reason='Full compiler CLI requires its declared google-re2 runtime')
    execute(args)
    ir = json.loads(output.read_text(encoding='utf-8'))
    assert ir['metadata']['document_admission']['stage'] == 'partial'
    assert ir['metadata']['document_admission']['structure']['missing_sections'] == ['英文摘要']


@pytest.mark.parametrize('title', [
    'CCF博士学位论文激励计划推荐表（单位）', '软件系统用户手册',
    '个人简历', '增值税电子普通发票', '教学课件：软件工程',
])
def test_partial_opt_in_cannot_create_paper_nodes_from_non_papers(tmp_path, monkeypatch, title):
    import paper_compiler.frontend as frontend
    path = pdf_with_text(tmp_path, title + '\n摘要\n参考文献\n说明材料。' * 8)
    constructed = []
    monkeypatch.setattr(frontend, '_build_source_tree', lambda *a, **kw: constructed.append(True))
    with pytest.raises(ValueError, match='论文身份'):
        build_paper(path, include_citations=False, allow_incomplete_structure=True)
    assert constructed == []
    proof = check_document(path)
    assert proof['compiled'] is False
    assert proof['status'] == 'rejected'
    assert proof['stage'] == 'identity'
