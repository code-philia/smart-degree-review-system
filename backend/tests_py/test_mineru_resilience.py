"""Automatic transient recovery and raw-cache reuse in the deployed parser."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import pymupdf
from pdf_rules.mineru_api import MinerUError, parse_layout
from test_mineru_api import FakeHttp, fake_zip

class ResilienceTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/'paper.pdf'
        with pymupdf.open() as pdf:
            pdf.new_page(width=600,height=800);pdf.save(self.path)
        self.cache=Path(self.folder.name)/'cache'
    def successful(self,http,**kwargs):
        try:return parse_layout(self.path,'fixture-token',http,**kwargs)
        except MinerUError as exc:self.fail('Recoverable request escaped: '+str(exc))
    def test_temporary_poll_503_recovers_same_task_without_reupload(self):
        class TemporaryHttp(FakeHttp):
            failures=0
            def request(self,method,url,**kwargs):
                if '/extract-results/' in url and self.failures<2:
                    self.failures+=1
                    raise HTTPError(url,503,'secret',{},None)
                return super().request(method,url,**kwargs)
        http=TemporaryHttp()
        with patch('pdf_rules.mineru_api.time.sleep'):
            objects=self.successful(http)
        self.assertEqual(objects[0].kind,'figure')
        self.assertEqual(http.failures,2)
        self.assertEqual(sum(c[0]=='POST' for c in http.calls),1)
    def test_service_busy_response_is_retried_without_exposing_message(self):
        class BusyHttp(FakeHttp):
            requests=0
            def request(self,method,url,**kwargs):
                if method=='POST':
                    self.requests+=1
                    if self.requests==1:return {'code':-10001,'msg':'private signed URL'}
                return super().request(method,url,**kwargs)
        http=BusyHttp()
        with patch('pdf_rules.mineru_api.time.sleep'):
            self.successful(http)
        self.assertEqual(http.requests,2)
    def test_request_timeouts_never_exceed_remaining_parse_budget(self):
        class TimedHttp(FakeHttp):
            timeouts=[]
            def request(self,method,url,**kwargs):
                self.timeouts.append(kwargs.get('timeout'))
                return super().request(method,url,**kwargs)
        http=TimedHttp();self.successful(http,max_seconds=5)
        self.assertTrue(all(0<t<=5 for t in http.timeouts),http.timeouts)
    def test_completed_raw_layout_is_cached_by_exact_pdf_and_model(self):
        with patch.dict(os.environ,{'MINERU_CACHE_DIR':str(self.cache)}):
            first=FakeHttp();a=self.successful(first)
            second=FakeHttp();b=self.successful(second)
            self.assertEqual(second.calls,[], 'A finished raw parse was uploaded again')
            self.assertEqual(a,b)
            third=FakeHttp();self.successful(third,force_ocr=True)
            self.assertGreater(len(third.calls),0,'OCR and VLM raw results must not share a key')
        records=list(self.cache.glob('*.json'))
        self.assertTrue(records)
        self.assertTrue(all('fixture-token' not in p.read_text() and 'signed-url-secret' not in p.read_text() for p in records))
    def test_wrong_page_count_is_never_cached_as_a_success(self):
        with pymupdf.open() as pdf:
            pdf.new_page();pdf.new_page();pdf.save(self.path)
        with patch.dict(os.environ,{'MINERU_CACHE_DIR':str(self.cache)}):
            with self.assertRaises(MinerUError):parse_layout(self.path,'fixture-token',FakeHttp(fake_zip()))
            successful=list(self.cache.glob('*.json')) if self.cache.exists() else []
            self.assertFalse(any(json.loads(p.read_text()).get('pages') for p in successful))
    def test_interrupted_polling_resumes_uploaded_task_from_disk(self):
        class InterruptedHttp(FakeHttp):
            offline=True
            posts=0
            def request(self,method,url,**kwargs):
                if method=='POST':self.posts+=1
                if self.offline and '/extract-results/' in url:raise OSError('temporary disconnect')
                return super().request(method,url,**kwargs)
        http=InterruptedHttp()
        with patch.dict(os.environ,{'MINERU_CACHE_DIR':str(self.cache)}),patch('pdf_rules.mineru_api.time.sleep'):
            with self.assertRaises(MinerUError):parse_layout(self.path,'fixture-token',http)
            http.offline=False
            self.successful(http)
        self.assertEqual(http.posts,1, 'Recovery must resume polling, not re-upload this completed submission')
    def test_stalled_large_task_splits_automatically_with_original_page_numbers(self):
        with pymupdf.open() as pdf:
            for _ in range(4):pdf.new_page(width=600,height=800)
            pdf.save(self.path)
        class Clock:
            value=0
            def monotonic(self):return self.value
            def sleep(self,delay):self.value+=delay
        clock=Clock()
        class StalledHttp(FakeHttp):
            def request(self,method,url,**kwargs):
                if '/extract-results/' in url and self.chunk_pages>2:
                    clock.value+=185
                    return {'code':0,'data':{'extract_result':[{'state':'running'}]}}
                return super().request(method,url,**kwargs)
        http=StalledHttp(lambda count:fake_zip(page_count=count))
        with patch('pdf_rules.mineru_api.time.monotonic',clock.monotonic),patch('pdf_rules.mineru_api.time.sleep',clock.sleep):
            objects=self.successful(http,max_seconds=450)
        self.assertEqual([o.page_number for o in objects if o.kind=='figure'],[1,3])
        self.assertLess(clock.value,450)

    def test_interrupted_download_is_retried_on_the_same_finished_task(self):
        from http.client import IncompleteRead
        class InterruptedDownload(FakeHttp):
            downloads=0
            def request(self,method,url,**kwargs):
                if 'download.test' in url:
                    self.downloads+=1
                    if self.downloads==1:raise IncompleteRead(b'partial zip',20)
                return super().request(method,url,**kwargs)
        http=InterruptedDownload()
        with patch('pdf_rules.mineru_api.time.sleep'):
            self.successful(http)
        self.assertEqual(http.downloads,2)
        self.assertEqual(sum(c[0]=='POST' for c in http.calls),1)

    def test_slow_continuous_download_cannot_overrun_its_absolute_deadline(self):
        from pdf_rules.mineru_api import UrllibHttpClient
        class Clock:
            value=0
            def monotonic(self):return self.value
        clock=Clock()
        class SlowResponse:
            socket_timeouts=[]
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,limit):
                # A whole buffered read can take much longer than each I/O.
                clock.value+=20;return b'{}'
            def read1(self,limit):
                clock.value+=4;return b'x'
        response=SlowResponse()
        with patch('pdf_rules.mineru_api.time.monotonic',clock.monotonic),patch('pdf_rules.mineru_api._open',return_value=response):
            with self.assertRaises(MinerUError):
                UrllibHttpClient().request('GET','https://fixture.test/result',timeout=5)
        self.assertLessEqual(clock.value,8)

    def test_real_content_length_truncation_retries_the_download(self):
        import io,time
        from http.client import HTTPResponse
        from pdf_rules.mineru_api import UrllibHttpClient,_call
        archive=fake_zip()
        class DataSocket:
            def __init__(self,payload):self.payload=payload
            def makefile(self,*args):return io.BytesIO(self.payload)
        def response(body):
            wire=b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(archive)).encode()+b'\r\n\r\n'+body
            result=HTTPResponse(DataSocket(wire));result.begin();return result
        with patch('pdf_rules.mineru_api._open',side_effect=[response(archive[:-15]),response(archive)]) as opener,patch('pdf_rules.mineru_api.time.sleep'):
            payload=_call(UrllibHttpClient(),'GET','https://fixture.test/result',deadline=time.monotonic()+10)
        self.assertEqual(opener.call_count,2)
        self.assertEqual(payload,archive)

    def test_slow_header_bytes_obey_absolute_deadline_on_real_socket(self):
        import socket,threading,time
        from http.client import HTTPResponse
        from pdf_rules.mineru_api import _DeadlineSocket
        left,right=socket.socketpair();left.settimeout(1)
        self.addCleanup(left.close);self.addCleanup(right.close)
        def drip():
            try:
                for byte in b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}':
                    right.send(bytes([byte]));time.sleep(.04)
            except OSError:pass
        writer=threading.Thread(target=drip,daemon=True);writer.start()
        started=time.monotonic()
        response=HTTPResponse(_DeadlineSocket(left,started+.2))
        self.addCleanup(response.close)
        with self.assertRaises((OSError,MinerUError)):response.begin()
        self.assertLess(time.monotonic()-started,.6)

    def test_nonrecoverable_auth_failure_is_not_retried_or_split(self):
        class DeniedHttp(FakeHttp):
            requests=0
            def request(self,method,url,**kwargs):
                self.requests+=1
                raise HTTPError(url,401,'fixture-token',{},None)
        http=DeniedHttp()
        with self.assertRaises(MinerUError) as raised:parse_layout(self.path,'fixture-token',http)
        self.assertEqual(http.requests,1)
        self.assertNotIn('fixture-token',str(raised.exception))

if __name__=='__main__':unittest.main()
