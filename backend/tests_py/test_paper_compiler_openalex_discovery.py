"""Targeted OpenAlex discovery does not weaken bibliographic identity checks."""
import copy
import json
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from paper_compiler import evidence
from paper_compiler.identity import resolve_identity

TITLE = 'Attention Is All You Need'
DOI = '10.48550/arxiv.1706.03762'
CANONICAL = '10.65215/2q58a426'


def openalex_work(*, year=2025, doi=CANONICAL, identifier='W2626778328'):
    return {'id': 'https://openalex.org/' + identifier, 'display_name': TITLE,
            'publication_year': year, 'doi': 'https://doi.org/' + doi if doi else None,
            'authorships': [{'author': {'display_name': 'Ashish Vaswani'}}],
            'locations': [{'doi': 'https://doi.org/' + DOI}], 'abstract_inverted_index': {}}


def record(work, identifier='e1'):
    return {'id': identifier, 'status': 'ok', 'provider': 'openalex', 'work': work}


def test_title_discovery_has_a_scoped_year_independent_query():
    urls = list(evidence._urls('openalex', {'title': TITLE, 'year': 2017}))
    scoped = [parse_qs(urlsplit(url).query) for url in urls if 'search.title=' in url]
    assert scoped, 'title discovery currently searches abstracts/fulltext only'
    assert scoped[0]['search.title'] == ['"Attention Is All You Need"']
    assert 'filter' not in scoped[0]
    assert len(urls) <= 3
    assert any('publication_year' in url for url in urls), 'retain the bounded legacy fallback'


def test_doi_discovery_is_exact_and_independent_of_title_and_year():
    urls = list(evidence._urls('openalex', {'doi': 'https://doi.org/' + DOI, 'year': 2017}))
    assert len(urls) == 1
    params = parse_qs(urlsplit(urls[0]).query)
    assert params['filter'] == ['doi:https://doi.org/' + DOI]
    assert 'search' not in params and 'search.title' not in params


def test_literal_title_cannot_inject_boolean_operators_or_grow_an_unbounded_url():
    title = 'A "quoted" title OR * ' + '研究' * 1000
    urls = list(evidence._urls('openalex', {'title': title}))
    scoped = next((url for url in urls if 'search.title=' in url), None)
    assert scoped is not None
    value = parse_qs(urlsplit(scoped).query)['search.title'][0]
    assert value.startswith('"A \\"quoted\\" title OR * ') and value.endswith('"')
    assert len(scoped.encode()) < 4094


def test_gateway_recalls_scoped_candidates_beyond_the_old_five_result_cap(tmp_path):
    calls = []
    def transport(url):
        calls.append(url)
        if 'search.title=' not in url:
            return 200, json.dumps({'results': []}).encode()
        rows = [dict(openalex_work(identifier='W' + str(i)), display_name='Other paper ' + str(i)) for i in range(8)]
        rows.append(openalex_work())
        return 200, json.dumps({'results': rows}).encode()
    rows = evidence.EvidenceGateway(tmp_path, providers=['openalex'], transport=transport).lookup({'title': TITLE, 'authors': ['Vaswani'], 'year': 2025})
    target = [row for row in rows if row.get('work', {}).get('title') == TITLE]
    assert target, 'the exact candidate at rank nine must be retained'
    assert target[0]['work']['openalex_id'] == 'https://openalex.org/W2626778328'
    assert target[0]['work']['doi_aliases'] == [DOI]
    answer = resolve_identity({'title': TITLE, 'authors': ['Vaswani'], 'year': 2025}, rows)
    assert answer['state'] == 'observed'
    assert len(calls) <= 3


def test_old_frozen_retrieval_is_not_refreshed_by_a_new_discovery_plan(tmp_path):
    query = {'title': TITLE, 'year': 2017}
    legacy_url = 'https://api.openalex.org/works?' + urlencode({'search': TITLE, 'per-page': 5, 'filter': 'publication_year:2017'})
    old = evidence.EvidenceGateway(tmp_path, providers=['openalex'], transport=lambda url: (429, b''), snapshot_id='old-round')
    cached = old._retrieve('openalex', legacy_url)
    calls = []
    def unexpected(url):
        calls.append(url)
        return 200, json.dumps({'results': [openalex_work()]}).encode()
    records = evidence.EvidenceGateway(tmp_path, providers=['openalex'], transport=unexpected, snapshot_id='old-round').lookup(query)
    assert records == [{key: value for key, value in cached.items() if key != 'works'}]
    assert calls == []


def test_new_frozen_lookup_pins_its_query_plan_across_strategy_changes(tmp_path, monkeypatch):
    calls = []
    def transport(url):
        calls.append(url)
        return 200, json.dumps({'results': [openalex_work()]}).encode()
    gateway = evidence.EvidenceGateway(tmp_path, providers=['openalex'], transport=transport, snapshot_id='new-round')
    query = {'title': TITLE, 'year': 2025}
    first = gateway.lookup(query)
    count = len(calls)
    monkeypatch.setattr(evidence, '_urls', lambda provider, query: iter(['https://api.openalex.org/works?search=changed']))
    assert gateway.lookup(query) == first
    assert len(calls) == count


def test_doi_url_and_provider_reported_alias_preserve_identifier_identity():
    work = {'title': TITLE, 'authors': ['Ashish Vaswani'], 'year': 2025,
            'doi': CANONICAL, 'doi_aliases': [DOI], 'openalex_id': 'https://openalex.org/W2626778328'}
    result = resolve_identity({'title': TITLE, 'authors': ['Vaswani'], 'doi': 'https://doi.org/' + DOI}, [record(work)])
    assert result['state'] == 'observed'
    assert result['metadata_conflicts'] == []


def test_same_title_and_authors_do_not_override_a_known_year_conflict():
    work = {'title': TITLE, 'authors': ['Ashish Vaswani'], 'year': 2025, 'doi': CANONICAL, 'doi_aliases': [DOI]}
    entry = {'title': TITLE, 'authors': ['Vaswani'], 'year': 2017, 'doi': DOI}
    assert resolve_identity(entry, [record(work)])['state'] == 'unknown'


def test_distinct_doi_less_openalex_identities_remain_ambiguous():
    work = {'title': TITLE, 'authors': ['Ashish Vaswani'], 'year': 2017, 'doi': ''}
    one = record({**work, 'openalex_id': 'https://openalex.org/W1'})
    two = record({**work, 'openalex_id': 'https://openalex.org/W2'}, 'e2')
    assert resolve_identity({'title': TITLE, 'authors': ['Vaswani'], 'year': 2017}, [one, two])['state'] == 'unknown'


def test_repeated_same_openalex_identity_is_not_a_new_work():
    work = {'title': TITLE, 'authors': ['Ashish Vaswani'], 'year': 2017, 'doi': '', 'openalex_id': 'https://openalex.org/W1'}
    result = resolve_identity({'title': TITLE, 'authors': ['Vaswani'], 'year': 2017}, [record(work), record(copy.deepcopy(work), 'e2')])
    assert result['state'] == 'observed'


@pytest.mark.parametrize('changes', [{'title': 'An entirely different scientific work'}, {'authors': ['Alice Smith']}])
def test_an_exact_alias_doi_does_not_erase_conflicting_work_metadata(changes):
    work = {'title': TITLE, 'authors': ['Ashish Vaswani'], 'year': 2017, 'doi': CANONICAL, 'doi_aliases': [DOI]}
    entry = {'title': TITLE, 'authors': ['Vaswani'], 'year': 2017, 'doi': DOI, **changes}
    assert resolve_identity(entry, [record(work)])['state'] == 'unknown'


def test_a_new_query_in_a_new_snapshot_does_not_mistake_shared_cache_for_a_legacy_round(tmp_path):
    calls = []
    def transport(url):
        calls.append(url)
        return 200, json.dumps({'results': [openalex_work()]}).encode()
    gateway = evidence.EvidenceGateway(tmp_path, providers=['openalex'], transport=transport, snapshot_id='new-round')
    query = {'title': TITLE, 'year': 2025}
    gateway.lookup(query)
    calls.clear()
    records = gateway.lookup({**query, 'doi': 'https://doi.org/' + DOI})
    assert any(parse_qs(urlsplit(url).query).get('filter') == ['doi:https://doi.org/' + DOI] for url in calls)
    assert any('filter=doi' in row['url'] for row in records)
