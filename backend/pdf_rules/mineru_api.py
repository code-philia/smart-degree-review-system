"""Private-PDF MinerU API transport. No token or signed URL is included in errors."""
import io
import json
import time
import urllib.request
import zipfile
from pathlib import Path

import pymupdf

from .mineru_layout import normalize_layout


BASE = "https://mineru.net/api/v4"
MAX_POLL_SECONDS = 240
MAX_ARCHIVE_BYTES = 150 * 1024 * 1024


class MinerUError(Exception):
    pass


class UrllibHttpClient:
    def request(self, method, url, *, headers=None, data=None, timeout=30):
        request = urllib.request.Request(url, data=data, method=method, headers=headers or {})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read(MAX_ARCHIVE_BYTES + 1)
        if len(payload) > MAX_ARCHIVE_BYTES:
            raise MinerUError("MinerU result is too large")
        if method == "PUT":
            return {}
        try:
            return json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            return payload


def _call(client, method, url, **kwargs):
    try:
        return client.request(method, url, **kwargs)
    except MinerUError:
        raise
    except Exception as exc:
        raise MinerUError("MinerU network request failed") from None


def _data(result):
    if not isinstance(result, dict) or result.get("code") != 0:
        raise MinerUError("MinerU API rejected the request")
    data = result.get("data")
    if not isinstance(data, dict):
        raise MinerUError("MinerU API response is incomplete")
    return data


def _layout_from_zip(payload):
    try:
        if not isinstance(payload, bytes) or len(payload) > MAX_ARCHIVE_BYTES:
            raise ValueError("Invalid archive")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = [n for n in archive.namelist() if n == "layout.json" or n.endswith("/layout.json")]
            if len(names) != 1:
                raise ValueError("layout.json missing or ambiguous")
            info = archive.getinfo(names[0])
            if info.file_size > MAX_ARCHIVE_BYTES:
                raise ValueError("Oversized layout")
            data = json.loads(archive.read(info))
        pages = data["pdf_info"]
        if not isinstance(pages, list):
            raise ValueError("Invalid pages")
        return pages
    except (KeyError, ValueError, TypeError, zipfile.BadZipFile) as exc:
        raise MinerUError("MinerU layout archive is invalid") from None


def _submit_and_fetch(payload, token, client, *, poll_interval, deadline):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    post = json.dumps({"files": [{"name": "paper.pdf", "data_id": "pdf-rule-scan"}],
                       "model_version": "vlm"}, ensure_ascii=False).encode("utf-8")
    data = _data(_call(client, "POST", f"{BASE}/file-urls/batch",
                       headers=headers, data=post, timeout=30))
    upload_urls = data.get("file_urls")
    batch_id = data.get("batch_id")
    if not isinstance(upload_urls, list) or len(upload_urls) != 1 or not isinstance(batch_id, str):
        raise MinerUError("MinerU upload response is incomplete")
    _call(client, "PUT", upload_urls[0], headers={}, data=payload, timeout=120)
    while time.monotonic() < deadline:
        result = _data(_call(client, "GET", f"{BASE}/extract-results/batch/{batch_id}",
                             headers={"Authorization": f"Bearer {token}"}, timeout=30))
        entries = result.get("extract_result")
        if not isinstance(entries, list) or len(entries) != 1:
            raise MinerUError("MinerU task response is incomplete")
        state = entries[0].get("state")
        if state == "done":
            zip_url = entries[0].get("full_zip_url")
            if not isinstance(zip_url, str):
                raise MinerUError("MinerU result URL is missing")
            archive = _call(client, "GET", zip_url, headers={}, timeout=90)
            return _layout_from_zip(archive)
        if state in ("failed", "error"):
            raise MinerUError("MinerU could not parse this PDF")
        if state not in ("pending", "running", "converting", "waiting-file", "waiting"):
            raise MinerUError("MinerU returned an unknown task state")
        time.sleep(poll_interval)
    raise MinerUError("MinerU task timed out")


def parse_layout(pdf_path, token, http_client=None, page_limit=180, *,
                 poll_interval=2.0, max_seconds=MAX_POLL_SECONDS):
    if not token:
        raise MinerUError("MinerU API token is not configured")
    if not 1 <= page_limit <= 200:
        raise ValueError("page_limit must be between 1 and 200")
    client = http_client or UrllibHttpClient()
    try:
        document = pymupdf.open(Path(pdf_path))
        try:
            total = len(document)
            if total < 1:
                raise MinerUError("PDF has no pages")
            deadline = time.monotonic() + max_seconds
            objects = []
            for start in range(0, total, page_limit):
                stop = min(start + page_limit, total)
                if start == 0 and stop == total:
                    payload = Path(pdf_path).read_bytes()
                else:
                    chunk = pymupdf.open()
                    chunk.insert_pdf(document, from_page=start, to_page=stop - 1)
                    payload = chunk.tobytes(garbage=4, deflate=True)
                    chunk.close()
                if len(payload) > 200 * 1024 * 1024:
                    raise MinerUError("MinerU PDF segment exceeds 200 MB")
                sizes = [(float(document[i].rect.width), float(document[i].rect.height))
                         for i in range(start, stop)]
                pages = _submit_and_fetch(payload, token, client, poll_interval=poll_interval,
                                          deadline=deadline)
                objects.extend(normalize_layout(pages, start + 1, sizes))
            return objects
        finally:
            document.close()
    except MinerUError:
        raise
    except Exception:
        raise MinerUError("PDF layout parsing failed") from None



