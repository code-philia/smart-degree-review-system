"""Primary arXiv source identity must not merge an alias-only conference edition."""
from copy import deepcopy
import pytest
from paper_compiler.identity import resolve_identity


def candidates():
    entry = {'title': 'An Example Research Work', 'authors': ['Jane Smith'],
             'year': 2018, 'url': 'https://arxiv.org/abs/1807.04320'}
    common = {'title': entry['title'], 'authors': ['Jane Smith'], 'year': 2018}
    conference = dict(common, doi='10.1000/conference',
                      url='https://doi.org/10.1000/conference',
                      doi_aliases=['10.48550/arxiv.1807.04320'],
                      openalex_id='https://openalex.org/W123', pages='10-20')
    return entry, [
        {'id': 'datacite-preprint', 'status': 'ok', 'work': dict(common,
            doi='10.48550/arxiv.1807.04320', url='https://arxiv.org/abs/1807.04320')},
        {'id': 'openalex-title', 'status': 'ok', 'work': deepcopy(conference)},
        {'id': 'openalex-search', 'status': 'ok', 'work': deepcopy(conference)}]


@pytest.mark.parametrize('anchor', ['primary_doi', 'primary_url'])
def test_primary_arxiv_identity_wins_over_alias_only_conference_records(anchor):
    entry, records = candidates()
    if anchor == 'primary_doi':
        records[0]['work'].pop('url')
    else:
        records[0]['work'].pop('doi')
    before = deepcopy((entry, records))
    result = resolve_identity(entry, records)
    assert result['state'] == 'observed' and result['value'] is True
    assert result['evidence_ids'] == ['datacite-preprint']
    assert result['method'] == 'source_backed_arxiv_url'
    assert 'pages' not in result['work'] and 'openalex_id' not in result['work']
    assert (entry, records) == before


def test_explicit_conference_doi_conflicting_with_primary_arxiv_url_stays_unknown():
    entry, records = candidates()
    entry['doi'] = '10.1000/conference'
    result = resolve_identity(entry, records)
    assert result['state'] == 'unknown'
    assert result['reason'] == 'conflicting explicit DOI and arXiv URL identities'
    assert 'work' not in result


def test_alias_only_records_without_a_primary_arxiv_anchor_do_not_merge_conflicting_dois():
    entry, records = candidates()
    records = records[1:]
    records[1]['work'].update(doi='10.1000/different-edition',
                              url='https://doi.org/10.1000/different-edition')
    result = resolve_identity(entry, records)
    assert result['state'] == 'unknown'
    assert result['reason'] == 'multiple conflicting work identities'
    assert 'work' not in result
