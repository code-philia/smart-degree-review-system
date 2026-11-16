"""Derived fixtures for saved keyword and edited abstract evidence failures."""
import importlib.util
from pathlib import Path

import pymupdf as fitz
import pytest


def lint_module():
    path = Path(__file__).parents[1] / 'scripts/run_bilingual_semantic_lint.py'
    spec = importlib.util.spec_from_file_location('evidence_semantic_test', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_abstract_quote_follows_visual_order_after_a_line_was_reinserted(tmp_path):
    lint = lint_module()
    path = tmp_path / 'edited-abstract.pdf'
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), 'Abstract starts on the previous page.')
    page = doc.new_page()
    page.insert_text((72, 72), 'To address these challenges,')
    page.insert_text((72, 92), 'this dissertation proposes a compilation sys-')
    page.insert_text((72, 132), 'automated scheduling.')
    page.insert_text((72, 152), 'Unrelated next sentence must stay unhighlighted.')
    page.insert_text((72, 760), 'IV')
    # Like the saved report, an edited line is last in PDF stream order.
    page.insert_text((72, 112), 'tem using program analysis, branch prediction, and')
    doc.save(path)
    doc.close()
    quote = ('To address these challenges,\nthis dissertation proposes a compilation '
             'sys-tem using program analysis, branch prediction, and automated scheduling.')
    anchors, evidence = lint._abstract_issue_anchors(
        {'source_artifacts': [{'kind': 'pdf', 'path': str(path)}]},
        {'english_abstract': quote, 'locations': {'english_abstract': {'page_number': 1}}},
        {'english_claim': quote})
    location = anchors[0]['location']
    assert location['type'] == 'pdf_bbox'
    assert location['page_number'] == 2
    assert len(location['rects']) == 4
    assert all(r['page_number'] == 2 and r['y2'] < 140 for r in location['rects'])
    assert evidence[0]['quote'] == quote


@pytest.mark.parametrize('language', ['chinese', 'english'])
def test_keywords_have_exact_rectangles_for_the_complete_evidence_quote(tmp_path, monkeypatch, language):
    lint = lint_module()
    path = tmp_path / 'keywords.pdf'
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), 'Unrelated abstract sentence.')
    if language == 'chinese':
        quote = '测试方法，数据流架构'
        label = '关键词：'
        page.insert_text((72, 140), label + quote, fontname='china-s')
    else:
        quote = 'FPGA, Operator Parallelism, Dataflow Architecture, Computation-Communication Overlap'
        label = 'Key words: '
        page.insert_text((72, 140), label + 'FPGA, Operator Parallelism,')
        page.insert_text((72, 160), 'Dataflow Architecture, Computation-Communication Overlap')
    doc.save(path)
    doc.close()
    facts = {
        'chinese_keywords': {'text': quote if language == 'chinese' else '关键词'},
        'english_keywords': {'text': quote if language == 'english' else 'Keywords'},
        'locations': {language + '_keywords': {'page_number': 1, 'text_excerpt': label + quote.split(', Dataflow')[0]}},
    }
    monkeypatch.setattr(lint, 'request_json', lambda _: ({'outcome': 'inconsistent', 'summary': '关键词不对应。'}, {}))
    run = lint._run_semantic_rule({'source_artifacts': [{'kind': 'pdf', 'path': str(path)}]},
                                  facts, 'bilingual_keywords_correspondence_check')
    finding = run['findings'][0]
    location = finding['anchors'][0]['location']
    assert location['type'] == 'pdf_bbox'
    assert location['page_number'] == 1
    assert len(location['rects']) == (1 if language == 'chinese' else 2)
    assert all(120 < r['y1'] < r['y2'] < 170 for r in location['rects'])
    assert finding['evidence'][0]['quote'] == quote
    assert finding['location'] == location


@pytest.mark.parametrize('text,quote', [
    ('The evidence is absent.', 'A nonexistent source sentence.'),
    ('Same evidence. Same evidence.', 'Same evidence.'),
])
def test_absent_or_ambiguous_quotes_do_not_acquire_rectangles(text, quote):
    lint = lint_module()
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), text)
    try:
        assert lint._quote_rects(doc, 0, quote) == []
    finally:
        doc.close()

@pytest.mark.parametrize('failure', ['missing', 'unreadable', 'extract'])
@pytest.mark.parametrize('kind', ['keywords', 'abstract'])
def test_optional_geometry_failure_preserves_the_semantic_evidence(tmp_path, monkeypatch, failure, kind):
    lint = lint_module()
    path = tmp_path / 'source.pdf'
    quote = 'The method uses branch prediction.'
    if failure == 'unreadable':
        path.write_text('This is not a PDF.')
    elif failure == 'extract':
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), quote)
        doc.save(path)
        doc.close()
        def unavailable(*_args, **_kwargs):
            raise RuntimeError('Optional glyph extraction unavailable')
        monkeypatch.setattr(fitz.Page, 'get_text', unavailable)
    ir = {'source_artifacts': [{'kind': 'pdf', 'path': str(path)}]}
    if kind == 'keywords':
        facts = {'chinese_keywords': {'text': '测试方法'}, 'english_keywords': {'text': quote},
                 'locations': {'english_keywords': {'page_number': 1, 'text_excerpt': quote}}}
        monkeypatch.setattr(lint, 'request_json', lambda _: ({'outcome': 'inconsistent', 'summary': '关键词不对应。'}, {}))
        run = lint._run_semantic_rule(ir, facts, 'bilingual_keywords_correspondence_check')
        assert run['execution_status'] == 'completed'
        assert run['outcome'] == 'issues_found'
        finding = run['findings'][0]
        assert finding['message'] == '关键词不对应。'
        anchors, evidence = finding['anchors'], finding['evidence']
    else:
        anchors, evidence = lint._abstract_issue_anchors(ir,
            {'english_abstract': quote, 'locations': {'english_abstract': {'page_number': 1}}},
            {'english_claim': quote})
    assert anchors[0]['location'] == {'type': 'pdf_page', 'page_number': 1, 'text_excerpt': quote}
    assert evidence[0]['quote'] == quote
