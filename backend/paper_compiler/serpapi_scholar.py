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


def _identity_key(query):
    doi = normalize_doi(query.get("doi"))
    identity = {"doi": doi, "title": _norm(query.get("title")),
                "authors": [_norm(a) for a in query.get("authors", [])],
                "year": query.get("year")}
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
    return {
        "title": str(item.get("title", "")).strip(),
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

    def lookup(self, query):
        key = _identity_key(query)
        cached = self._cached(key)
        if cached is not None:
            return cached.get("records", []), {"status": cached.get("status"), "cached": True,
                                               "library_key": key}
        api_key = _key()
        if not api_key:
            raise SerpApiError("SERPAPI_API_KEY is not configured")
        title = str(query.get("title", "")).strip()
        if not title:
            return [], {"status": "empty", "cached": False, "library_key": key}
        params = {"engine": "google_scholar", "q": title, "api_key": api_key,
                  "num": 10}
        status, body = self.transport(self.endpoint + "?" + urlencode(params))
        if status != 200:
            raise SerpApiError("HTTP_" + str(status))
        try:
            payload = json.loads(body)
        except (ValueError, TypeError) as error:
            raise SerpApiError("invalid_json") from error
        works = [_result_work(item) for item in (payload.get("organic_results") or [])
                 if isinstance(item, dict) and item.get("title")]
        target = _norm(title)
        # A Scholar result is accepted only when it is the queried work, not an
        # unrelated result returned for a broad title query.
        matched = [w for w in works if SequenceMatcher(None, target, _norm(w["title"])).ratio() >= 0.88]
        records = []
        for index, work in enumerate(matched):
            records.append({"id": "serpapi-scholar-" + key[:16] + "-" + str(index),
                            "provider": "serpapi", "engine": "google_scholar",
                            "status": "ok", "retrieved_at": self.clock(),
                            "query": {k: query.get(k) for k in ("title", "authors", "year", "doi")},
                            "work": work})
        status_name = "ok" if records else "empty"
        artifact = {"schema_version": "serpapi-scholar-library/1", "key": key,
                    "provider": "serpapi", "engine": "google_scholar",
                    "status": status_name, "retrieved_at": self.clock(),
                    "query": {k: query.get(k) for k in ("title", "authors", "year", "doi")},
                    "records": records}
        write_json_atomic(self.library_dir / (key + ".json"), artifact)
        return records, {"status": status_name, "cached": False, "library_key": key}
