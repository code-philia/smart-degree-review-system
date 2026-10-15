"""Real independent processes must not compete in unrestricted signed uploads."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import pymupdf
from unittest.mock import patch

from pdf_rules import mineru_api


class UploadConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.release = threading.Event()
        self.two_arrived = threading.Event()
        self.one_arrived = threading.Event()
        self.mutex = threading.Lock()
        self.active = self.maximum = self.received = 0
        self.api_mode = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_PUT(self):
                self.rfile.read(int(self.headers['Content-Length']))
                with owner.mutex:
                    owner.active += 1
                    owner.received += 1
                    owner.maximum = max(owner.maximum, owner.active)
                    owner.one_arrived.set()
                    if owner.active >= 2:
                        owner.two_arrived.set()
                owner.release.wait(8)
                with owner.mutex:
                    owner.active -= 1
                try:
                    self.send_response(200)
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
                body = (json.dumps({'code':0,'data':{'batch_id':'fixture-batch',
                    'file_urls':[owner.url]}}).encode() if owner.api_mode else b'{"ok": true}')
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        def cleanup():
            self.release.set()
            self.server.shutdown()
            self.server.server_close()
            thread.join(timeout=2)
        self.addCleanup(cleanup)
        self.url = f'http://127.0.0.1:{self.server.server_port}/signed-upload-fixture'
        self.environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]),
            PYTHONDONTWRITEBYTECODE='1', MINERU_UPLOAD_CONCURRENCY='2',
            MINERU_UPLOAD_LOCK_DIR=str(Path(self.folder.name)/'slots'),
            MINERU_PROXY_URL='', MINERU_TRUST_ENV_PROXY='')
        self.processes = []
        self.addCleanup(self.stop_processes)

    def stop_processes(self):
        self.release.set()
        for process in self.processes:
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

    def child_put(self, environment=None):
        code = ("from pdf_rules.mineru_api import UrllibHttpClient; import sys,time; "
                "UrllibHttpClient().request('PUT',sys.argv[1],data=b'payload',"
                "timeout=6,deadline=time.monotonic()+6)")
        process = subprocess.Popen([sys.executable, '-c', code, self.url],
            env=environment or self.environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.processes.append(process)
        return process

    def test_signed_put_limit_is_shared_across_independent_processes(self):
        processes = [self.child_put() for _ in range(5)]
        self.assertTrue(self.two_arrived.wait(4), 'two admitted uploads did not start')
        time.sleep(.5)
        with self.mutex:
            maximum = self.maximum
        self.release.set()
        for process in processes:
            self.assertEqual(process.wait(timeout=6), 0)
        self.assertLessEqual(maximum, 2, 'more than two independent processes uploaded simultaneously')
        self.assertEqual(self.received, 5, 'queued uploads must eventually preserve all requests')

    def test_upload_slot_wait_honors_absolute_deadline_without_sending_body(self):
        environment = {**self.environment, 'MINERU_UPLOAD_CONCURRENCY':'1'}
        self.child_put(environment)
        self.assertTrue(self.one_arrived.wait(4))
        started = time.monotonic()
        with patch.dict(os.environ, environment):
            with self.assertRaises(mineru_api.MinerUError) as raised:
                mineru_api._call(mineru_api.UrllibHttpClient(), 'PUT', self.url,
                    data=b'queued-body', timeout=5, deadline=started+.2)
        self.assertLess(time.monotonic()-started, 1)
        self.assertEqual(raised.exception.diagnostics.get('timeout_phase'), 'upload_slot')
        self.assertEqual(self.received, 1, 'expired queued body must never reach the server')

    def test_layout_segment_deadline_preserves_the_upload_wait_failure_phase(self):
        environment = {**self.environment, 'MINERU_UPLOAD_CONCURRENCY':'1', 'MINERU_CACHE_DIR':''}
        self.child_put(environment)
        self.assertTrue(self.one_arrived.wait(4))
        self.api_mode = True
        pdf = Path(self.folder.name)/'two-pages.pdf'
        with pymupdf.open() as document:
            document.new_page()
            document.new_page()
            document.save(pdf)
        with patch.dict(os.environ, environment), patch.object(mineru_api, 'BASE', self.url):
            with self.assertRaises(mineru_api.MinerUError) as raised:
                mineru_api.parse_layout(pdf, 'fixture-token', max_seconds=.2)
        self.assertEqual(raised.exception.diagnostics.get('timeout_phase'), 'upload_slot')
        self.assertEqual(self.received, 1)

    def test_control_requests_bypass_an_occupied_upload_slot(self):
        environment = {**self.environment, 'MINERU_UPLOAD_CONCURRENCY':'1'}
        self.child_put(environment)
        self.assertTrue(self.one_arrived.wait(4))
        with patch.dict(os.environ, environment):
            result = mineru_api.UrllibHttpClient().request('POST', self.url, data=b'{}',
                        timeout=1, deadline=time.monotonic()+1)
        self.assertEqual(result, {'ok':True})

    def test_process_exit_releases_its_upload_slot(self):
        environment = {**self.environment, 'MINERU_UPLOAD_CONCURRENCY':'1'}
        process = self.child_put(environment)
        self.assertTrue(self.one_arrived.wait(4))
        process.terminate()
        process.wait(timeout=3)
        self.release.set()
        with patch.dict(os.environ, environment):
            result = mineru_api.UrllibHttpClient().request('PUT', self.url, data=b'replacement',
                        timeout=2, deadline=time.monotonic()+2)
        self.assertEqual(result, {})

    def test_large_body_timeout_does_not_become_tcp_connect_timeout(self):
        self.release.set()
        seen = []
        original = socket.create_connection
        def connect(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, *args, **kwargs):
            seen.append(timeout)
            return original(address, timeout, *args, **kwargs)
        with patch.dict(os.environ, self.environment), patch('socket.create_connection', side_effect=connect):
            result = mineru_api.UrllibHttpClient().request('PUT', self.url, data=b'payload',
                        timeout=120, deadline=time.monotonic()+120)
        self.assertEqual(result, {})
        self.assertTrue(seen)
        self.assertLessEqual(max(seen), 30, 'TCP connection must have its own bounded budget')

    def test_forward_progressing_large_upload_is_not_one_socket_timeout_window(self):
        left, right = socket.socketpair()
        left.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        right.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        left.settimeout(.12)
        received = bytearray()
        def drain():
            while True:
                piece = right.recv(8192)
                if not piece:
                    break
                received.extend(piece)
                time.sleep(.005)
        thread = threading.Thread(target=drain, daemon=True)
        thread.start()
        payload = b'x' * (512 * 1024 + 7)
        try:
            mineru_api._DeadlineSocket(left, time.monotonic()+3).sendall(payload)
        finally:
            left.close()
            thread.join(timeout=3)
            right.close()
        self.assertEqual(bytes(received), payload)

    def test_progressing_large_upload_still_stops_at_its_absolute_deadline(self):
        left, right = socket.socketpair()
        left.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        left.settimeout(.12)
        stop = threading.Event()
        def drain():
            while not stop.is_set():
                piece = right.recv(8192)
                if not piece:
                    break
                time.sleep(.005)
        thread = threading.Thread(target=drain, daemon=True)
        thread.start()
        started = time.monotonic()
        try:
            with self.assertRaises((mineru_api.MinerUError, TimeoutError)):
                mineru_api._DeadlineSocket(left, started+.15).sendall(b'x'*(2*1024*1024))
            self.assertLess(time.monotonic()-started, .5)
        finally:
            stop.set()
            left.close()
            thread.join(timeout=2)
            right.close()

    def test_invalid_upload_limit_fails_safely_before_transport(self):
        self.release.set()
        with patch.dict(os.environ, {**self.environment, 'MINERU_UPLOAD_CONCURRENCY':'private-marker'}):
            with self.assertRaises(mineru_api.MinerUError) as raised:
                mineru_api.UrllibHttpClient().request('PUT', self.url, data=b'payload', timeout=1)
        self.assertNotIn('private-marker', str(raised.exception))
        self.assertEqual(self.received, 0)


if __name__ == '__main__':
    unittest.main()
