from pathlib import Path
import pymupdf
from fast_local_detector import run
from test_paper_structure_compilation import thesis


def test_no_abstract_or_keyword_block_cannot_pass_keyword_count(tmp_path):
    path = tmp_path / 'no-abstract-keywords.pdf'
    with pymupdf.open(thesis(tmp_path)) as doc:
        doc.delete_pages([1, 2, 3])
        doc.save(path)
    result = run(path, [36], allow_incomplete_structure=True)['rules']['36']
    assert result['status'] == 'unsupported'
    assert '关键词' in result['reason']
    assert result['findings'] == []
