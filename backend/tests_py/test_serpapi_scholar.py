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


def test_lookup_many_falls_back_to_title_and_authors(tmp_path, monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")
    calls=[]
    def transport(url):
        calls.append(url)
        from urllib.parse import parse_qs, urlsplit
        q=parse_qs(urlsplit(url).query).get("q", [""])[0]
        if q == "A Known Work Author":
            return 200, json.dumps({"organic_results":[{
                "title":"A Known Work", "publication_info":{"summary":"A. Author - 2024"}
            }]}).encode()
        return 200, b'{"organic_results":[]}'
    provider=SerpApiScholar(tmp_path,transport=transport)
    records,meta=provider.lookup_many({"title":"A Known Work","authors":["A. Author"],"year":2024})
    assert meta["status"]=="ok" and meta["matched_query_kind"]=="title_authors"
    assert len(calls)==2 and records[0]["status"]=="ok"
    assert records[0]["query"]["query_kind"]=="title_authors"
    assert any(item["status"]=="empty" for item in records)


def test_lookup_many_uses_doi_after_title_author_miss(tmp_path, monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")
    calls=[]
    def transport(url):
        calls.append(url)
        from urllib.parse import parse_qs, urlsplit
        q=parse_qs(urlsplit(url).query).get("q", [""])[0]
        if q == "10.1145/100216.100273":
            return 200, json.dumps({"organic_results":[{
                "title":"Public-key cryptosystems provably secure against chosen ciphertext attacks",
                "publication_info":{"summary":"M. Naor, M. Yung - 1990"}
            }]}).encode()
        return 200, b'{"organic_results":[]}'
    provider=SerpApiScholar(tmp_path,transport=transport)
    records,meta=provider.lookup_many({
        "title":"Public-key cryptosystems provably secure against chosen ciphertext attacks",
        "authors":["NAOR M","YUNG M"],"year":"1990","doi":"10.1145/100216.100273"})
    assert meta["status"]=="ok" and meta["matched_query_kind"]=="doi"
    assert len(calls)==3 and any(r.get("query",{}).get("query_kind")=="doi" for r in records if r["status"]=="ok")
    assert sum(r["status"]=="empty" for r in records)==2
