"""Native Tab. translations must not become body barriers above a table."""
from dataclasses import replace
from pathlib import Path
import hashlib
import json

import pytest

from pdf_rules.caption_rules import detect_caption_rules
from pdf_rules.layout_context import prepare_caption_layout, recover_document
from pdf_rules.mineru_layout import LayoutObject, _caption_kind
from pdf_rules.model import PdfDocument, PdfLine, PdfPage
from pdf_rules.numbering import TABLE_CAPTION, normalize_label

FIXTURE = Path(__file__).parent / 'fixtures/tab_abbreviation_caption_20261014/actual14-080.json'
FACTS = json.loads(FIXTURE.read_text())


def tuples(value):
    if isinstance(value, list):
        return tuple(tuples(item) for item in value)
    if isinstance(value, dict):
        return {key: tuples(item) for key, item in value.items()}
    return value


@pytest.mark.parametrize('fixture_name', ['actual14-080.json', 'actual14-093.json'])
def test_actual_native_bilingual_title_captions_its_original_table(fixture_name):
    facts = json.loads(FIXTURE.with_name(fixture_name).read_text())
    source = Path(facts['source_pdf'])
    if not source.exists():
        pytest.skip('read-only original source PDF unavailable')
    assert hashlib.sha256(source.read_bytes()).hexdigest() == facts['source_pdf_sha256']
    values = tuples(facts['native_page'])
    values['lines'] = tuple(PdfLine(**line) for line in values['lines'])
    document = PdfDocument(source, (PdfPage(**values),))
    raw = [LayoutObject(**tuples(item)) for item in facts['raw_layout']]
    recovered = recover_document(document, raw)
    prepared = prepare_caption_layout(raw, recovered)
    assert detect_caption_rules(prepared, [14], recovered)['14']['findings'] == []
    assert hashlib.sha256(source.read_bytes()).hexdigest() == facts['source_pdf_sha256']


def sample(translation='Tab.1-1 Wake patterns around different Reynolds numbers'):
    chinese = PdfLine(1, '表1-1 不同流态', (180, 300, 400, 312), 600, 840, font_size=10)
    english = PdfLine(1, translation, (145, 316, 460, 328), 600, 840, font_size=10)
    page = PdfPage(1, 600, 840, (chinese, english))
    document = PdfDocument(Path('/nonexistent-tab-translation.pdf'), (page,))
    body = LayoutObject('table', 1, (75, 330, 525, 500), '', 600, 840, role='table_body')
    title = LayoutObject('table_caption', 1, chinese.bbox, chinese.text, 600, 840)
    return document, body, title


@pytest.mark.parametrize('prefix', ['Tab.', 'Table'])
def test_numbered_translation_does_not_block_the_retained_chinese_title(prefix):
    document, body, title = sample(prefix + '1-1 Wake patterns around different Reynolds numbers')
    assert detect_caption_rules([body, title], [14], document)['14']['findings'] == []


@pytest.mark.parametrize('prose', [
    'Tab.1-1 shows a different flow pattern that requires further examination.',
    'The wake pattern varies with Reynolds number and the surrounding geometry.',
])
def test_actual_prose_between_title_and_table_still_blocks_association(prose):
    document, body, title = sample(prose)
    assert _caption_kind(prose) is None
    assert len(detect_caption_rules([body, title], [14], document)['14']['findings']) == 1


def test_deleting_both_title_lines_preserves_the_missing_caption_obligation():
    document, body, title = sample()
    document = replace(document, pages=(replace(document.pages[0], lines=()),))
    assert len(detect_caption_rules([body], [14], document)['14']['findings']) == 1


def test_neighboring_localized_abbreviated_title_cannot_caption_another_table():
    left = LayoutObject('table', 1, (50, 330, 260, 500), '', 600, 840, role='table_body')
    right = replace(left, bbox=(320, 330, 550, 500))
    chinese = PdfLine(1, '表1-1 左表流态', (75, 300, 235, 312), 600, 840)
    english = PdfLine(1, 'Tab.1-1 Localized original table', (55, 316, 255, 328), 600, 840)
    document = PdfDocument(Path('/nonexistent-neighbor-tables.pdf'), (PdfPage(1, 600, 840, (chinese, english)),))
    captions = [LayoutObject('table_caption', 1, line.bbox, line.text, 600, 840) for line in (chinese, english)]
    findings = detect_caption_rules([left, right] + captions, [14], document)['14']['findings']
    assert len(findings) == 1 and findings[0]['location']['bounding_rect']['x1'] == 320


def test_abbreviated_caption_keeps_original_number_string_and_character_offsets():
    match = TABLE_CAPTION.match('Tab.1- 2 Wake patterns')
    assert match is not None and match.group('number') == '1- 2'
    assert match.span('number') == (4, 8)
    assert normalize_label(match.group('number')) == '1.2'


def test_actual14_080_frozen_v3_mutant_still_reports_its_untitled_table():
    facts = json.loads(FIXTURE.with_name('actual14-080-mutant.json').read_text())
    source = Path(facts['source_pdf'])
    if not source.exists():
        pytest.skip('read-only frozen V3 source PDF unavailable')
    assert hashlib.sha256(source.read_bytes()).hexdigest() == facts['source_pdf_sha256']
    values = tuples(facts['native_page'])
    values['lines'] = tuple(PdfLine(**line) for line in values['lines'])
    document = PdfDocument(source, (PdfPage(**values),))
    raw = [LayoutObject(**tuples(item)) for item in facts['raw_layout']]
    recovered = recover_document(document, raw)
    prepared = prepare_caption_layout(raw, recovered)
    findings = detect_caption_rules(prepared, [14], recovered)['14']['findings']
    assert len(findings) == 1
    box = findings[0]['location']['bounding_rect']
    assert box['page_number'] == 21 and 385 < box['y1'] < 395 and 545 < box['y2'] < 557
    assert hashlib.sha256(source.read_bytes()).hexdigest() == facts['source_pdf_sha256']
