"""Large unrelated ZIP assets cannot prevent fetching the exact layout member."""
import io
import json
import random
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest
import zipfile
from unittest.mock import patch

from pdf_rules import mineru_api
from test_mineru_api import fake_zip


def large_archive():
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('paper/layout.json',json.dumps({'pdf_info':[{'page_idx':0,'page_size':[600,800],'para_blocks':[]}]}))
        archive.writestr('paper/images/unneeded.bin',random.Random(17).randbytes(3*1024*1024))
    return stream.getvalue()


class Response:
    def __init__(self,body,status=206,headers=None):
        self.body=io.BytesIO(body);self.status=status;self.headers=headers or {};self.length=len(body)
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read1(self,count):
        result=self.body.read(count);self.length-=len(result);return result
    read=read1


class ArchiveRangeTests(unittest.TestCase):
    def setUp(self):
        self.archive=large_archive();self.requested=[];self.read_bytes=0

    def serve(self,request,timeout,deadline):
        header=request.get_header('Range');self.requested.append(header)
        if header:
            raw=header.removeprefix('bytes=')
            if raw.startswith('-'):first=max(0,len(self.archive)-int(raw[1:]));last=len(self.archive)-1
            else:first,last=map(int,raw.split('-'))
            body=self.archive[first:last+1];self.read_bytes+=len(body)
            return Response(body,headers={'Content-Range':f'bytes {first}-{last}/{len(self.archive)}','ETag':'"fixture-v1"'})
        self.read_bytes+=len(self.archive)
        return Response(self.archive,status=200)

    def fetch(self):
        import time
        return mineru_api._fetch_layout_pages(mineru_api.UrllibHttpClient(),'https://fixture.test/zip?private-signature',deadline=time.monotonic()+30)

    def test_large_image_payload_is_not_downloaded_to_get_same_layout(self):
        with patch('pdf_rules.mineru_api._open',side_effect=self.serve):pages=self.fetch()
        self.assertEqual(pages,mineru_api._layout_from_zip(self.archive))
        self.assertLess(self.read_bytes,200000)
        self.assertTrue(all(self.requested))

    def test_ignored_range_falls_back_to_whole_archive(self):
        def ignore(request,timeout,deadline):
            self.requested.append(request.get_header('Range'))
            return Response(self.archive,status=200)
        with patch('pdf_rules.mineru_api._open',side_effect=ignore):pages=self.fetch()
        self.assertEqual(pages,mineru_api._layout_from_zip(self.archive))
        self.assertEqual(len(self.requested),2)
        self.assertIsNone(self.requested[-1])

    def test_malformed_content_range_cannot_be_trusted(self):
        def invalid(request,timeout,deadline):
            if request.get_header('Range'):
                return Response(self.archive[-100:],headers={'Content-Range':'bytes 0-99/999'})
            return self.serve(request,timeout,deadline)
        with patch('pdf_rules.mineru_api._open',side_effect=invalid):
            self.assertEqual(self.fetch(),mineru_api._layout_from_zip(self.archive))

    def test_archive_version_change_is_rejected_without_exposing_url(self):
        count=0
        def changing(request,timeout,deadline):
            nonlocal count
            response=self.serve(request,timeout,deadline);count+=1
            if count>1:response.headers['ETag']='"different-v2"'
            return response
        with patch('pdf_rules.mineru_api._open',side_effect=changing):
            with self.assertRaises(mineru_api.MinerUError) as error:self.fetch()
        self.assertNotIn('private-signature',str(error.exception))

    def test_duplicate_layout_members_are_rejected(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            archive.writestr('a/layout.json',json.dumps({'pdf_info':[]}))
            archive.writestr('b/layout.json',json.dumps({'pdf_info':[]}))
        self.archive=stream.getvalue()
        with patch('pdf_rules.mineru_api._open',side_effect=self.serve):
            with self.assertRaises(mineru_api.MinerUError):self.fetch()

    def test_non_range_client_retains_existing_download_contract(self):
        from test_mineru_api import FakeHttp
        http=FakeHttp(fake_zip())
        pages=mineru_api._fetch_layout_pages(http,'https://fixture.test/zip',deadline=__import__('time').monotonic()+30)
        self.assertEqual(len(pages),1)
        self.assertEqual(len(http.calls),1)

    def test_real_http_range_and_zip_crc_keep_layout_exact(self):
        source=self.archive;transferred=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                header=self.headers.get('Range')
                if header.startswith('bytes=-'):
                    first=max(0,len(source)-int(header[7:]));last=len(source)-1
                else:first,last=map(int,header[6:].split('-'))
                body=source[first:last+1];transferred.append(len(body))
                self.send_response(206)
                self.send_header('Content-Range',f'bytes {first}-{last}/{len(source)}')
                self.send_header('Content-Length',str(len(body)))
                self.send_header('ETag','"immutable-fixture"');self.end_headers()
                self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            pages=mineru_api._fetch_layout_pages(mineru_api.UrllibHttpClient(),
                f'http://127.0.0.1:{server.server_port}/archive',deadline=__import__('time').monotonic()+10)
            self.assertEqual(pages,mineru_api._layout_from_zip(source))
            self.assertLess(sum(transferred),200000)
        finally:
            server.shutdown();server.server_close();worker.join(timeout=2)

    def test_corrupt_layout_crc_is_never_success(self):
        data=bytearray(self.archive)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info=archive.getinfo('paper/layout.json')
        name_length=int.from_bytes(data[26:28],'little');extra_length=int.from_bytes(data[28:30],'little')
        data[30+name_length+extra_length+info.compress_size//2]^=1
        self.archive=bytes(data)
        with patch('pdf_rules.mineru_api._open',side_effect=self.serve):
            with self.assertRaises(mineru_api.MinerUError):self.fetch()


if __name__=='__main__':unittest.main()
