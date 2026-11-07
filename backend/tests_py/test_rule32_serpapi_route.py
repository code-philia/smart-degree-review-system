"""Exercise the production R32 gateway with synthetic Scholar HTTP responses."""
import json
from urllib.parse import urlsplit
import pytest
from paper_compiler.evidence import EvidenceGateway
from paper_compiler.serpapi_scholar import SerpApiScholar, SerpApiError
from paper_compiler.analysis import _prefetch_rule32

QUERY = {'title': 'A Known Work', 'authors': ['A. Author'], 'year': 2024}

def test_gateway_calls_scholar_and_reuses_cache(tmp_path, monkeypatch):
    monkeypatch.setenv('SERPAPI_API_KEY', 'synthetic-test-key')
    monkeypatch.delenv('PAPER_COMPILER_REFERENCE_LIBRARY', raising=False)
    calls = []
    def transport(self, url):
        calls.append(urlsplit(url).hostname)
        return 200, json.dumps({'organic_results': [{'title': QUERY['title'],
            'publication_info': {'summary': 'A. Author - 2024'}}]}).encode()
    monkeypatch.setattr(SerpApiScholar, '_request', transport)
    gateway = EvidenceGateway(tmp_path, transport=lambda _: pytest.fail('public lookup must not run'))
    monkeypatch.setattr(gateway, 'prefetch_rule32', lambda _: pytest.fail('public prefetch must not run'))
    nodes = [{'id': 'ref'}]
    fields = {'ref': {name: {'state': 'observed', 'value': value} for name, value in QUERY.items()}}
    assert _prefetch_rule32(nodes, fields, gateway)['ref'][0][0]['provider'] == 'serpapi'
    assert gateway.lookup_rule32(QUERY)[0]['provider'] == 'serpapi'
    assert calls == ['serpapi.com']

def test_quota_survives_parallel_prefetch_and_blocks_repeated_requests(tmp_path, monkeypatch):
    monkeypatch.setenv('SERPAPI_API_KEY', 'synthetic-test-key')
    monkeypatch.delenv('PAPER_COMPILER_REFERENCE_LIBRARY', raising=False)
    calls = []
    def transport(self, url):
        calls.append(urlsplit(url).hostname)
        return 429, b'{"error":"Your account has run out of searches."}'
    monkeypatch.setattr(SerpApiScholar, '_request', transport)
    gateway = EvidenceGateway(tmp_path, transport=lambda _: pytest.fail('public fallback must not run'))
    fields = {'ref': {'title': {'state': 'observed', 'value': QUERY['title']}}}
    records, error = _prefetch_rule32([{'id': 'ref'}], fields, gateway)['ref']
    assert records == []
    assert error == 'SerpApiError: SERPAPI_QUOTA_EXHAUSTED'
    assert calls == ['serpapi.com']
    with pytest.raises(SerpApiError, match='SERPAPI_QUOTA_EXHAUSTED'):
        gateway.lookup_rule32({'title': 'Another Uncached Work'})
    assert len(calls) == 1
    assert json.loads((tmp_path / 'reference-library/serpapi-status.json').read_text())['status'] == 'exhausted'

def test_prefetch_does_not_publish_sensitive_exception_text():
    class Gateway:
        def lookup_rule32(self, query):
            raise SerpApiError('https://example.invalid/?api_key=synthetic-secret')
    _, error = _prefetch_rule32([{'id': 'ref'}], {'ref': {'title': {'state': 'observed', 'value': 'Work'}}}, Gateway())['ref']
    assert error == 'SerpApiError'

def test_real_analysis_and_rule_pipeline_preserves_quota_as_unknown(tmp_path, monkeypatch):
    from test_paper_compiler_fixed_r32 import checked
    monkeypatch.setenv('SERPAPI_API_KEY', 'synthetic-test-key')
    monkeypatch.delenv('PAPER_COMPILER_REFERENCE_LIBRARY', raising=False)
    calls = []
    def transport(self, url):
        calls.append(urlsplit(url).hostname)
        return 429, b'{"error":"Your account has run out of searches."}'
    monkeypatch.setattr(SerpApiScholar, '_request', transport)
    gateway = EvidenceGateway(tmp_path / 'gateway', transport=lambda _: pytest.fail('public lookup must not run'))
    _, _, analysis, row = checked(tmp_path, gateway=gateway)
    assert calls == ['serpapi.com']
    assert row['status'] == 'UNKNOWN'
    assert any('SERPAPI_QUOTA_EXHAUSTED' in reason for reason in row['reasons'])
    assert 'serpapi-scholar/' in analysis['policy']['reference_lookup']
