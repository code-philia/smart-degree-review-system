import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pymupdf

from pdf_rules.mineru_api import MinerUError, UrllibHttpClient, parse_layout


def fake_zip(page_index=0, width=600, height=800):
    payload = {"pdf_info": [{"page_idx": page_index, "page_size": [width, height],
                            "para_blocks": [{"type": "image", "bbox": [100, 200, 300, 350 if width == 300 else 400]},
                                            {"type": "image_caption", "bbox": [100, 355 if width == 300 else 410, 300, 380 if width == 300 else 430],
                                             "lines": [{"spans": [{"content": "图 1 示例"}]}]}]}]}
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("layout.json", json.dumps(payload))
    return data.getvalue()


class FakeHttp:
    def __init__(self, archive=None, failure=None):
        self.calls = []
        self.archive = archive or fake_zip()
        self.failure = failure

    def request(self, method, url, *, headers=None, data=None, timeout=30):
        self.calls.append((method, url, headers or {}, data))
        if self.failure:
            raise RuntimeError("signed-url-secret token-secret " + self.failure)
        if method == "POST":
            number = sum(call[0] == "POST" for call in self.calls)
            return {"code": 0, "data": {"batch_id": f"batch-{number}",
                                        "file_urls": [f"https://upload.test/{number}?signed-url-secret"]}}
        if method == "PUT":
            return {}
        if "/extract-results/batch/" in url:
            return {"code": 0, "data": {"extract_result": [
                {"state": "done", "full_zip_url": "https://download.test/result?signed-url-secret"}]}}
        return self.archive


class MinerUApiTests(unittest.TestCase):
    def pdf(self, pages):
        temporary = tempfile.TemporaryDirectory()
        path = Path(temporary.name) / "paper.pdf"
        doc = pymupdf.open()
        for _ in range(pages):
            doc.new_page(width=600, height=800)
        doc.save(path)
        doc.close()
        self.addCleanup(temporary.cleanup)
        return path

    def test_upload_poll_and_zip(self):
        http = FakeHttp()
        objects = parse_layout(self.pdf(1), "token-secret", http)
        self.assertEqual([obj.kind for obj in objects], ["figure", "figure_caption"])
        self.assertEqual(objects[0].page_number, 1)
        self.assertEqual(objects[0].bbox, (100.0, 200.0, 300.0, 400.0))
        self.assertEqual([call[0] for call in http.calls], ["POST", "PUT", "GET", "GET"])
        self.assertEqual(json.loads(http.calls[0][3])["model_version"], "vlm")
        self.assertEqual(http.calls[0][2]["Authorization"], "Bearer token-secret")
        self.assertNotIn("Content-Type", http.calls[1][2])

    def test_chunk_page_mapping(self):
        http = FakeHttp(fake_zip(page_index=40, width=300, height=400))
        objects = parse_layout(self.pdf(221), "token-secret", http, page_limit=180)
        self.assertEqual(len([call for call in http.calls if call[0] == "POST"]), 2)
        self.assertEqual([obj.page_number for obj in objects if obj.kind == "figure"], [41, 221])
        self.assertEqual(objects[-2].bbox, (200.0, 400.0, 600.0, 700.0))

    def test_signed_put_has_no_implicit_form_content_type(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b""
        with patch("urllib.request.urlopen", return_value=response) as opener:
            UrllibHttpClient().request("PUT", "https://upload.test/signed", headers={}, data=b"pdf")
        request = opener.call_args.args[0]
        self.assertTrue(request.has_header("Content-type"))
        self.assertFalse(any(key.lower() == "content-type" for key, _ in request.header_items()))
    def test_api_failure_is_sanitized(self):
        with self.assertRaises(MinerUError) as raised:
            parse_layout(self.pdf(1), "token-secret", FakeHttp(failure="failure"))
        self.assertNotIn("token-secret", str(raised.exception))
        self.assertNotIn("signed-url-secret", str(raised.exception))


