"""Single-provider Google Scholar lookup for rule 32.

The provider deliberately distinguishes a successful empty Scholar response
from an API/transport failure.  Only the former is a negative existence fact.
Successful hits are stored in a small, deduplicated local reference library.
"""
import hashlib
import json
import os
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .identity import normalize_doi
from .storage import json_bytes, write_json_atomic


class SerpApiError(RuntimeError):
    pass


QUERY_PLAN_VERSION = "serpapi-scholar-query-plan/2.0"


def _norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _key():
    for name in ("SERPAPI_API_KEY", "SERPAPI_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    config = os.environ.get("SERPAPI_CONFIG", "")
    if config:
        path = Path(config)
        if not path.is_file() or path.stat().st_mode & 0o077:
            raise SerpApiError("SERPAPI_CONFIG must be a private regular file")
        for line in path.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() in {"SERPAPI_API_KEY", "SERPAPI_KEY"}:
                return value.strip().strip("\"'")
    return ""


def _identity_key(query, *, search_query=None, query_kind=None):
    doi = normalize_doi(query.get("doi"))
    identity = {"doi": doi, "title": _norm(query.get("title")),
                "authors": [_norm(a) for a in query.get("authors", [])],
                "year": query.get("year")}
    # The historical title-only cache key is kept byte-for-byte compatible.
    # Fallback strategies must have independent keys so a miss from one query
    # cannot mask a later title+author or DOI query.
    if query_kind and query_kind != "title":
        identity["query_kind"] = query_kind
        identity["search_query"] = str(search_query or "")
    return hashlib.sha256(json_bytes(identity)).hexdigest()


def _result_work(item):
    publication = item.get("publication_info") or {}
    authors = publication.get("authors") or item.get("authors") or []
    if isinstance(authors, list):
        authors = [a.get("name", "") if isinstance(a, dict) else str(a)
                   for a in authors]
    elif isinstance(authors, str):
        authors = [authors]
    year = None
    match = re.search(r"\b(19|20)\d{2}\b", str(publication.get("summary", "")))
    if match:
        year = int(match.group(0))
    raw_title = item.get("title")
    return {
        "title": raw_title.strip() if isinstance(raw_title, str) else "",
        "authors": [str(a).strip() for a in authors if str(a).strip()],
        "year": year,
        "url": item.get("link", ""),
        "snippet": str(item.get("snippet", "")).strip(),
        "serp_result_id": item.get("result_id", ""),
    }


class SerpApiScholar:
    endpoint = "https://serpapi.com/search.json"

    def __init__(self, library_dir, *, transport=None, clock=time.time):
        self.library_dir = Path(library_dir)
        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.transport = transport or self._request
        self.clock = clock

    def _request(self, url):
        try:
            with urlopen(Request(url, headers={"User-Agent": "SJTU-PaperCompiler/1.0",
                                               "Accept": "application/json"}), timeout=20) as response:
                return response.status, response.read(4 * 1024 * 1024)
        except HTTPError as error:
            return error.code, error.read(1024)
        except OSError as error:
            raise SerpApiError(type(error).__name__) from error

    def _cached(self, key):
        path = self.library_dir / (key + ".json")
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if data.get("schema_version") == "serpapi-scholar-library/1" else None
        except (OSError, ValueError, TypeError):
            return None

    def _query_plans(self, query):
        """Return bounded, deterministic Scholar query fallbacks.

        Scholar often returns no title-only hit for older conference papers even
        when the title plus the cited authors is indexed.  DOI-only queries are
        retained as a final exact-identifier fallback.  The original title
        query remains first and keeps its legacy cache key.
        """
        title = str(query.get("title") or "").strip()
        if title:
            yield "title", title
            authors = query.get("authors") or []
            if isinstance(authors, list):
                surnames = []
                for author in authors:
                    value = str(author or "").strip()
                    if not value or value.casefold() in {"et al", "et al."}:
                        continue
                    parts = re.findall(r"[A-Za-z][A-Za-z'\-]*", value)
                    if not parts:
                        continue
                    # Bibliography extraction commonly returns ``SURNAME I``;
                    # also handle ``I. Surname`` and ordinary full names.
                    if len(parts) > 1 and len(parts[0].rstrip('.')) <= 2 and len(parts[-1]) > 2:
                        surname = parts[-1]
                    elif len(parts) > 1 and len(parts[-1].rstrip('.')) <= 2 and len(parts[0]) > 2:
                        surname = parts[0]
                    else:
                        surname = parts[-1] if len(parts) > 1 else parts[0]
                    if surname not in surnames:
                        surnames.append(surname)
                if surnames:
                    yield "title_authors", title + " " + " ".join(surnames[:4])
        doi = normalize_doi(query.get("doi"))
        if doi:
            yield "doi", doi

    def _lookup_one(self, query, search_query, query_kind):
        legacy_key = query_kind == "title" and search_query == str(query.get("title") or "").strip()
        key = (_identity_key(query) if legacy_key else
               _identity_key(query, search_query=search_query, query_kind=query_kind))
        cached = self._cached(key)
        public_query = {k: query.get(k) for k in ("title", "authors", "year", "doi")}
        public_query.update({"search_query": search_query, "query_kind": query_kind})
        if cached is not None:
            return cached.get("records", []), {"status": cached.get("status"),
                                                "cached": True,
                                                "library_key": key,
                                                "query": public_query}
        api_key = _key()
        if not api_key:
            raise SerpApiError("SERPAPI_API_KEY is not configured")
        if not search_query:
            return [], {"status": "empty", "cached": False,
                         "library_key": key, "query": public_query}
        params = {"engine": "google_scholar", "q": search_query,
                  "api_key": api_key, "num": 10}
        status, body = self.transport(self.endpoint + "?" + urlencode(params))
        if status != 200:
            raise SerpApiError("HTTP_" + str(status))
        try:
            payload = json.loads(body)
        except (ValueError, TypeError) as error:
            raise SerpApiError("invalid_json") from error
        works = [_result_work(item) for item in (payload.get("organic_results") or [])
                 if isinstance(item, dict) and item.get("title")]
        target = _norm(query.get("title"))
        matched = ([w for w in works if target and
                    SequenceMatcher(None, target, _norm(w["title"])).ratio() >= 0.88])
        records = []
        for index, work in enumerate(matched):
            records.append({"id": "serpapi-scholar-" + key[:16] + "-" + str(index),
                            "provider": "serpapi", "engine": "google_scholar",
                            "status": "ok", "retrieved_at": self.clock(),
                            "query": public_query, "work": work})
        status_name = "ok" if records else "empty"
        artifact = {"schema_version": "serpapi-scholar-library/1", "key": key,
                    "provider": "serpapi", "engine": "google_scholar",
                    "status": status_name, "retrieved_at": self.clock(),
                    "query": public_query, "records": records}
        write_json_atomic(self.library_dir / (key + ".json"), artifact)
        return records, {"status": status_name, "cached": False,
                         "library_key": key, "query": public_query}

    def lookup(self, query):
        """Run the historical single title query (backwards-compatible API)."""
        title = str(query.get("title") or "").strip()
        return self._lookup_one(query, title, "title")

    def lookup_many(self, query):
        """Try title, title+authors, then DOI, stopping at the first valid hit.

        Empty attempts are returned as evidence records, so Rule 32 can explain
        which fallback paths were exhausted.  Transport/API failures propagate
        and remain UNKNOWN rather than becoming a false nonexistence result.
        """
        attempts = []
        empty = []
        for query_kind, search_query in self._query_plans(query):
            records, meta = self._lookup_one(query, search_query, query_kind)
            attempts.append(meta)
            if records:
                return records + empty, {"status": "ok", "attempts": attempts,
                                         "matched_query_kind": query_kind}
            key = meta.get("library_key", "")
            empty.append({"id": "serpapi-scholar-empty-" + key[:16],
                          "provider": "serpapi", "engine": "google_scholar",
                          "status": "empty", "retrieved_at": self.clock(),
                          "query": meta.get("query", query), "works": []})
        return empty, {"status": "empty", "attempts": attempts}
