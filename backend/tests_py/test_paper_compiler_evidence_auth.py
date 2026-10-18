"""Authentication boundaries: private config, host scoping, and cache isolation."""
import json
import time
import pytest
from paper_compiler import evidence

DUMMY_KEY = 'test-openalex-key-not-a-real-credential'

@pytest.fixture
def private_config(tmp_path, monkeypatch):
    path = tmp_path / 'evidence.env'
    path.write_text('OPENALEX_API_KEY=' + DUMMY_KEY + '\n')
    path.chmod(0o600)
    monkeypatch.setenv('PAPER_COMPILER_EVIDENCE_CONFIG', str(path))
    monkeypatch.delenv('OPENALEX_API_KEY', raising=False)
    return path


def http_boundary(monkeypatch, abstract_word='verified'):
    requests = []
    body = json.dumps({'results': [{'id': 'https://openalex.org/W123',
        'display_name': 'A known scientific work', 'doi': 'https://doi.org/10.1234/work',
        'publication_year': 2020, 'authorships': [],
        'abstract_inverted_index': {abstract_word: [0]}}]}).encode()
    class Reply:
        status = 200
        headers = {'Content-Type': 'application/json'}
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, size): return body[:size]
    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            return Reply()
    monkeypatch.setattr(evidence, 'build_opener', lambda *args: Opener())
    return requests


def test_private_key_authenticates_real_gateway_without_entering_urls_or_cache(tmp_path, monkeypatch, private_config):
    requests = http_boundary(monkeypatch, DUMMY_KEY)
    cache = tmp_path / 'cache'
    rows = evidence.EvidenceGateway(cache, providers=['openalex']).lookup({'title': 'A known scientific work'})
    assert rows[0]['status'] == 'ok'
    assert rows[0]['work']['doi'] == '10.1234/work'
    assert requests[0].get_header('Authorization') == 'Bearer ' + DUMMY_KEY
    assert DUMMY_KEY not in requests[0].full_url
    assert DUMMY_KEY not in json.dumps(rows)
    assert all(DUMMY_KEY not in p.read_text() for p in cache.rglob('*.json'))


@pytest.mark.parametrize('url', [
    'https://api.crossref.org/works/10.1234/test',
    'https://api.datacite.org/dois/10.1234/test',
    'https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=test',
    'https://export.arxiv.org/pdf/1706.03762'])
def test_other_sources_never_receive_openalex_authorization(monkeypatch, private_config, url):
    requests = http_boundary(monkeypatch)
    response = evidence._http(url)
    assert response[0] == 200
    assert requests[0].get_header('Authorization') is None


def test_environment_key_takes_precedence_over_private_file(monkeypatch, private_config):
    monkeypatch.setenv('OPENALEX_API_KEY', 'different-test-key')
    requests = http_boundary(monkeypatch)
    evidence._http('https://api.openalex.org/works?search=test')
    assert requests[0].get_header('Authorization') == 'Bearer different-test-key'


def test_missing_config_preserves_anonymous_access(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENALEX_API_KEY', raising=False)
    monkeypatch.setenv('PAPER_COMPILER_EVIDENCE_CONFIG', str(tmp_path / 'missing.env'))
    requests = http_boundary(monkeypatch)
    assert evidence._http('https://api.openalex.org/works?search=test')[0] == 200
    assert requests[0].get_header('Authorization') is None


def test_world_readable_config_is_rejected_without_disclosing_credential(monkeypatch, private_config):
    private_config.chmod(0o644)
    requests = http_boundary(monkeypatch)
    with pytest.raises(evidence.EvidenceError) as error:
        evidence._http('https://api.openalex.org/works?search=test')
    assert DUMMY_KEY not in str(error.value)
    assert requests == []


def test_control_characters_in_key_are_rejected_before_request(monkeypatch, private_config):
    monkeypatch.setenv('OPENALEX_API_KEY', 'key\nInjected-Header: value')
    requests = http_boundary(monkeypatch)
    with pytest.raises(evidence.EvidenceError):
        evidence._http('https://api.openalex.org/works?search=test')
    assert requests == []


def test_old_anonymous_backoff_does_not_block_a_new_authenticated_identity(tmp_path, monkeypatch, private_config):
    cache = tmp_path / 'cache'
    cache.mkdir()
    (cache / 'openalex-rate-state.json').write_text(json.dumps({'cooldown_until': time.time() + 3600}))
    requests = http_boundary(monkeypatch)
    result = evidence.EvidenceGateway(cache, providers=['openalex']).lookup({'title': 'A known scientific work'})
    assert result[0]['status'] == 'ok'
    assert result[0]['request_sent'] is True
    assert requests[0].get_header('Authorization') == 'Bearer ' + DUMMY_KEY


def test_new_authentication_does_not_refresh_a_frozen_failure(tmp_path, monkeypatch, private_config):
    query = {'title': 'A known scientific work'}
    old = evidence.EvidenceGateway(tmp_path / 'cache', providers=['openalex'],
        transport=lambda url: (429, b''), snapshot_id='old-round').lookup(query)
    requests = http_boundary(monkeypatch)
    new = evidence.EvidenceGateway(tmp_path / 'cache', providers=['openalex'], snapshot_id='old-round').lookup(query)
    assert new == old
    assert requests == []
