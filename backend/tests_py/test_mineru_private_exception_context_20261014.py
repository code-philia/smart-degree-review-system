"""Sanitized exceptions must not retain private response/parser exception objects."""
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile
import pymupdf
from pdf_rules import mineru_api
from test_mineru_api import FakeHttp
MARKER='fixture-private-response-data'

def bad_archive():
 stream=io.BytesIO()
 with zipfile.ZipFile(stream,'w') as archive:
  archive.writestr('layout.json',('{"pdf_info":["'+MARKER+'"],').encode())
 return stream.getvalue()

class PrivateExceptionContextTests(unittest.TestCase):
 def assert_private_removed(self,exc):
  self.assertIsNone(exc.__context__)
  self.assertIsNone(exc.__cause__)
  self.assertNotIn(MARKER,str(exc))
 def test_full_archive_invalid_json_does_not_retain_response(self):
  with self.assertRaises(mineru_api.MinerUError) as caught:mineru_api._layout_from_zip(bad_archive())
  self.assert_private_removed(caught.exception)
 def test_range_archive_invalid_json_does_not_retain_response(self):
  payload=bad_archive()
  class RangeClient(mineru_api.UrllibHttpClient):
   def request(self,method,url,**kw):
    return {'range_supported':True,'body':payload,'headers':{'content-range':f'bytes 0-{len(payload)-1}/{len(payload)}'}}
  with self.assertRaises(mineru_api.MinerUError) as caught:
   mineru_api._fetch_layout_pages(RangeClient(),'https://fixture.invalid/private',deadline=time.monotonic()+20)
  self.assert_private_removed(caught.exception)
 def pdf(self):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);path=Path(temp.name)/'paper.pdf'
  with pymupdf.open() as pdf:pdf.new_page();pdf.save(path)
  return path
 def test_normalize_failure_does_not_retain_private_parser_exception(self):
  with patch.dict(os.environ,{'MINERU_CACHE_DIR':''}),patch.object(mineru_api,'normalize_layout',side_effect=ValueError(MARKER)):
   with self.assertRaises(mineru_api.MinerUError) as caught:
    mineru_api.parse_layout(self.pdf(),'fixture-token',FakeHttp())
  self.assert_private_removed(caught.exception)
 def test_pdf_open_failure_does_not_retain_private_source_exception(self):
  with patch.object(mineru_api.pymupdf,'open',side_effect=ValueError(MARKER)):
   with self.assertRaises(mineru_api.MinerUError) as caught:
    mineru_api.parse_layout('fixture.pdf','fixture-token',FakeHttp())
  self.assert_private_removed(caught.exception)
 def test_invalid_proxy_port_does_not_retain_private_config_exception(self):
  with patch.dict(os.environ,{'MINERU_PROXY_URL':'http://fixture.invalid:'+MARKER}):
   with self.assertRaises(mineru_api.MinerUError) as caught:mineru_api._proxy_configuration()
  self.assert_private_removed(caught.exception)
if __name__=='__main__':unittest.main()
