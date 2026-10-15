"""Repeated PDF text must not redo Unicode work or share mutable citations."""
from pdf_rules import numbering, source_cited_usage


def test_repeated_pdf_text_normalizes_once(monkeypatch):
    numbering.normalize_text.cache_clear()
    text = '图９–７ 热路径专用样例①²'
    original = numbering.unicodedata.normalize
    calls = []

    def counted(form, value):
        calls.append(value)
        return original(form, value)

    monkeypatch.setattr(numbering.unicodedata, 'normalize', counted)
    assert numbering.normalize_text(text) == '图9-7 热路径专用样例①²'
    first_count = len(calls)
    assert first_count > 0
    for _ in range(20):
        assert numbering.normalize_text(text) == '图9-7 热路径专用样例①²'
    assert len(calls) == first_count


def test_repeated_citation_parse_reuses_work_without_sharing_sets(monkeypatch):
    source_cited_usage._citation_values.cache_clear()
    text = '独立的缓存解析样例［７–９，１２］ [0-2] [9-7] [1-102]'
    original = source_cited_usage.normalize_text
    calls = []

    def counted(value):
        calls.append(value)
        return original(value)

    monkeypatch.setattr(source_cited_usage, 'normalize_text', counted)
    first = source_cited_usage._citations(text)
    assert first == {7, 8, 9, 12}
    first.clear()
    for _ in range(20):
        assert source_cited_usage._citations(text) == {7, 8, 9, 12}
    assert len(calls) == 1
