import json

from paper_compiler.serpapi_scholar import SerpApiScholar, SerpApiError


def test_hit_is_persisted_and_reused(tmp_path, monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")
    calls = []
    body = json.dumps({"organic_results": [{"title": "A Known Work", "link": "https://scholar.google.com/x", "publication_info": {"summary": "A. Author - 2024"}}]}).encode()
    def transport(url):
        calls.append(url)
        return 200, body
    provider = SerpApiScholar(tmp_path, transport=transport)
    query = {"title": "A Known Work", "authors": ["A. Author"], "year": 2024}
    records, meta = provider.lookup(query)
    assert records and meta["status"] == "ok" and len(calls) == 1
    records, meta = provider.lookup(query)
    assert records and meta["cached"] and len(calls) == 1
    assert list(tmp_path.glob("*.json"))


def test_successful_empty_is_negative(tmp_path, monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")
    provider = SerpApiScholar(tmp_path, transport=lambda url: (200, b'{"organic_results":[]}'))
    records, meta = provider.lookup({"title": "Missing Work"})
    assert records == [] and meta["status"] == "empty"


def test_api_failure_is_not_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")
    provider = SerpApiScholar(tmp_path, transport=lambda url: (503, b""))
    try:
        provider.lookup({"title": "Unavailable Work"})
    except SerpApiError:
        pass
    else:
        raise AssertionError("API failure must not become a negative existence result")
