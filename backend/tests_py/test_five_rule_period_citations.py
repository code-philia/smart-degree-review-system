"""Period-space citation recovery must not hide genuinely unused references."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from five_rule_detector import Line, detect_lines


def line(page, text, y=100):
    return Line(page, text, (70, y, 530, y + 12), 600, 800)


def review(text, labels=(79, 80, 81)):
    lines = [line(1, 'Chapter 1 Introduction', 50),
             line(1, 'Previous work [79] introduces the method.', 100),
             line(24, text), line(79, 'References', 50)]
    lines += [line(79, f'[{number}] Author. Research paper.', 90 + index * 24)
              for index, number in enumerate(labels)]
    return detect_lines(lines, [22, 24])


@pytest.mark.parametrize('text', [
    'Figure 2.1 Traditional GIS-Based MPM approach [79. 80]',
    'Table 3.4 Comparison of existing approaches [79. 80].',
    '图2.1 传统方法的结构 [79. 80]',
    '参见文献[79. 80]。',
    'See references [79. 80] for the original methods.',
    'See refs. ［79.\u00a080］ for details.',
])
def test_citation_context_recovers_period_space_group_and_keeps_unused_reference(text):
    result = review(text)
    assert result['22']['findings'] == []
    assert [finding['token'] for finding in result['24']['findings']] == ['81']


def test_period_space_group_can_recover_three_existing_references():
    result = review('See references [79. 80. 81].', (79, 80, 81, 82))
    assert [finding['token'] for finding in result['24']['findings']] == ['82']


@pytest.mark.parametrize('text', [
    'Figure 2.1 Traditional method [79.80]',
    'See references [79.80] for details.',
    '[79. 80]',
    'Numeric vector [79. 80]',
    'The array [79. 80] stores the values.',
    'Figure 2.1 Numeric vector [79. 80]',
    'Figure 2.1 Matrix dimensions [79. 80]',
    'Figure 2.1 The range [79. 80]',
    'Figure 2.1 x = [79. 80]',
    'Figure 2.1 A[79. 80] = B',
    'Figure 2.1 Shape [79. 80]',
    'Section [79. 80] explains the method.',
    'See section [79. 80] for details.',
    '图2.1 向量取值 [79. 80]',
    'Figure 2.1 Data [79. 80]',
    'Figure 2.1 [79. 80]',
    '图2.1 [79. 80]',
    'See references [079. 80].',
    'See references [79. 80.5].',
    'See references [79. -80].',
    'See references [79. 80; 81].',
])
def test_decimal_section_and_numeric_data_do_not_hide_uncited_references(text):
    result = review(text)
    assert result['22']['findings'] == []
    assert [finding['token'] for finding in result['24']['findings']] == ['80', '81']


def test_section_numbers_are_not_recovered_even_when_bibliography_contains_them():
    result = review('See section [2. 3] for details.', (2, 3, 79))
    assert [finding['token'] for finding in result['24']['findings']] == ['2', '3']


def test_period_recovery_does_not_change_missing_target_rule():
    result = review('See references [79. 99]; another work [100] is cited.')
    assert [finding['token'] for finding in result['22']['findings']] == ['100']
    assert [finding['token'] for finding in result['24']['findings']] == ['80', '81']


def test_unknown_period_member_does_not_partially_recover_known_references():
    result = review('Figure 2.1 Existing approaches [79. 80. 99]')
    assert result['22']['findings'] == []
    assert [finding['token'] for finding in result['24']['findings']] == ['80', '81']
