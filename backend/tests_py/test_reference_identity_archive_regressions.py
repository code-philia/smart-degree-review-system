from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from reference_verification_extract import parse_entry


@pytest.mark.parametrize('authors,want', [
    ('KINGMA D P, BA J', ['KINGMA D P', 'BA J']),
    ('LIU X, LIU S, GU D, et al.', ['LIU X', 'LIU S', 'GU D']),
    ('MOLAIB K M, SUN X, RAM N, et al.', ['MOLAIB K M', 'SUN X', 'RAM N']),
    ('YE W, XU Z, GUI N', ['YE W', 'XU Z', 'GUI N']),
    ('CHENG G, HAN J, LU X', ['CHENG G', 'HAN J', 'LU X']),
])
def test_short_uppercase_surnames_do_not_merge_with_previous_author(authors, want):
    text = f'[1] {authors}. Reliable evidence for reference identity[J]. Journal of Tests, 2023.'
    row = parse_entry(text)
    assert row['authors'] == want
    assert row['text'] == text


def test_apa_initial_fragments_still_join_their_surnames():
    row = parse_entry('Smith, J. P., & Doe, R. (2023). Reliable evidence for reference identity. Journal of Tests.')
    assert row['authors'] == ['Smith J. P', 'Doe R']


@pytest.mark.parametrize('identifier,year', [('2001.08361', 2020), ('2005.07421', 2020), ('1907.11692', 2019)])
def test_arxiv_identifier_prefix_does_not_become_publication_year(identifier, year):
    text = f'[7] KAPLAN J, MCCANDLISH S. Scaling laws for neural language models[J]. arXiv preprint arXiv:{identifier}, {year}.'
    row = parse_entry(text)
    assert row['year'] == year
    assert row['arxiv_id'] == identifier


def test_title_quotation_does_not_truncate_its_unquoted_subtitle():
    row = parse_entry('[78] ZIMMER M. “But the data is already public”: On the ethics of research in Facebook[J/OL]. Ethics and Information Technology, 2010, 12: 313-325. DOI: 10.1007/s10676-010-9227-5.')
    assert row['title'] == '“But the data is already public”: On the ethics of research in Facebook'
    assert row['authors'] == ['ZIMMER M']


def test_compound_surname_initial_does_not_end_author_field():
    row = parse_entry('[57] AGUIRRE S. L P, SHEN Y, GUO M. LCA: Deep Reinforcement Learning-Based Congestion Avoidance Routing Model in SDN[J/OL]. Computer Networks, 2025, 268: 111371. DOI: 10.1016/j.comnet.2025.111371.')
    assert row['title'] == 'LCA: Deep Reinforcement Learning-Based Congestion Avoidance Routing Model in SDN'
    assert row['authors'] == ['AGUIRRE S. L P', 'SHEN Y', 'GUO M']


@pytest.mark.parametrize('author,title,kind,year', [('ASIMOV I', 'I, Robot', 'M', 1950), ('SMITH J', 'A, B, and C: A study of alphabetic patterns', 'J', 2023)])
def test_single_letter_title_word_is_not_mistaken_for_unfinished_author_initials(author, title, kind, year):
    row = parse_entry(f'[1] {author}. {title}[{kind}]. Publisher, {year}.')
    assert row['title'] == title
    assert row['authors'] == [author]


def test_full_stop_after_bracketed_number_does_not_become_author_separator():
    row = parse_entry('[3]. FREITAS L M C, MORGADO-DIAS F. Correlated multiple sampling technique[J/OL]. Analog Integrated Circuits, 2022, 110: 547-555.')
    assert row['title'] == 'Correlated multiple sampling technique'
    assert row['authors'] == ['FREITAS L M C', 'MORGADO-DIAS F']


def test_explicit_arxiv_version_is_not_lost_in_native_fields():
    row = parse_entry('[1] SMITH J. Reliable evidence for reference identity[J]. arXiv:2301.01234v2, 2023.')
    assert row['arxiv_id'] == '2301.01234v2'


def test_full_quoted_ieee_title_remains_supported():
    row = parse_entry('[1] J. Smith and R. Doe, "Reliable evidence for reference identity," IEEE Access, 2023, doi:10.1234/example.')
    assert row['title'] == 'Reliable evidence for reference identity'
    assert row['authors'] == ['J. Smith', 'R. Doe']
