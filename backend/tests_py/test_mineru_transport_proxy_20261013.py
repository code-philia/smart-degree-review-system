"""Real local sockets reproduce a disappearing inherited SSH HTTP proxy."""
import errno
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from pdf_rules import mineru_api


class TransportProxyTests(unittest.TestCase):
    def setUp(self):
        self.received = []
        self.origin = self.server('origin')
        self.proxy = self.server('inherited_proxy')
        self.dedicated = self.server('dedicated_proxy')
        inherited = f'http://127.0.0.1:{self.proxy.server_port}'
        self.environment = {
            'http_proxy': inherited, 'HTTP_PROXY': inherited,
            'https_proxy': inherited, 'HTTPS_PROXY': inherited,
            'all_proxy': '', 'ALL_PROXY': '', 'no_proxy': '', 'NO_PROXY': '',
            'MINERU_PROXY_URL': '', 'MINERU_TRUST_ENV_PROXY': '',
        }

    def server(self, route):
        received = self.received

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                body = json.dumps({'route': route}).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_PUT(self):
                remaining = int(self.headers['Content-Length'])
                size = remaining
                digest = hashlib.sha256()
                while remaining:
                    piece = self.rfile.read(min(65536, remaining))
                    if not piece:
                        break
                    digest.update(piece)
                    remaining -= len(piece)
                received.append({'route': route, 'bytes': size - remaining,
                                 'sha256': digest.hexdigest(), 'content_type': self.headers.get('Content-Type')})
                self.send_response(200)
                self.send_header('Content-Length', '0')
                self.end_headers()

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def cleanup():
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.addCleanup(cleanup)
        return server

    def get(self):
        return mineru_api.UrllibHttpClient().request(
            'GET', f'http://127.0.0.1:{self.origin.server_port}/resource', timeout=3)

    def test_default_direct_does_not_inherit_ssh_shell_proxy(self):
        with patch.dict(os.environ, self.environment):
            self.assertEqual(self.get(), {'route': 'origin'})

    def test_dedicated_mineru_proxy_overrides_an_unrelated_shell_proxy(self):
        environment = {**self.environment, 'MINERU_PROXY_URL': f'http://127.0.0.1:{self.dedicated.server_port}'}
        with patch.dict(os.environ, environment):
            self.assertEqual(self.get(), {'route': 'dedicated_proxy'})

    def test_explicit_environment_proxy_opt_in_retains_urllib_policy(self):
        with patch.dict(os.environ, {**self.environment, 'MINERU_TRUST_ENV_PROXY': '1'}):
            self.assertEqual(self.get(), {'route': 'inherited_proxy'})

    def test_invalid_dedicated_proxy_fails_safely_before_any_request(self):
        with patch.dict(os.environ, {**self.environment, 'MINERU_PROXY_URL': 'socks5://secret-password@invalid.test:1'}):
            with self.assertRaises(mineru_api.MinerUError) as raised:
                self.get()
        self.assertEqual(str(raised.exception), 'MinerU proxy configuration is invalid')
        self.assertNotIn('secret-password', repr(raised.exception))

    def test_direct_large_signed_put_preserves_all_bytes_and_no_content_type(self):
        payload = b'a' * (32 * 1024 * 1024 + 7)
        with patch.dict(os.environ, self.environment):
            response = mineru_api.UrllibHttpClient().request(
                'PUT', f'http://127.0.0.1:{self.origin.server_port}/signed?private-signature',
                data=payload, timeout=10, deadline=time.monotonic() + 10)
        self.assertEqual(response, {})
        self.assertEqual(self.received, [{'route': 'origin', 'bytes': len(payload),
                         'sha256': hashlib.sha256(payload).hexdigest(), 'content_type': None}])

    def test_connection_refusal_keeps_safe_method_subtype_and_errno(self):
        class RefusedClient:
            def request(self, method, url, **kwargs):
                raise URLError(ConnectionRefusedError(errno.ECONNREFUSED, 'secret-url-token'))
        with patch('pdf_rules.mineru_api.time.sleep'):
            with self.assertRaises(mineru_api.MinerUError) as raised:
                mineru_api._call(RefusedClient(), 'PUT', 'https://private.invalid?signature=secret-url-token')
        self.assertEqual(str(raised.exception), 'MinerU network request failed')
        self.assertEqual(raised.exception.diagnostics['operation'], 'PUT')
        self.assertEqual(raised.exception.diagnostics['reason_type'], 'ConnectionRefusedError')
        self.assertEqual(raised.exception.diagnostics['errno'], errno.ECONNREFUSED)
        self.assertEqual(raised.exception.diagnostics['attempts'], 4)
        self.assertNotIn('secret-url-token', json.dumps(raised.exception.diagnostics))

    def test_http_auth_rejection_retains_safe_status_and_does_not_retry(self):
        class DeniedClient:
            calls = 0
            def request(self, method, url, **kwargs):
                self.calls += 1
                raise HTTPError(url, 401, 'secret-signed-url', {}, None)
        client = DeniedClient()
        with self.assertRaises(mineru_api.MinerUError) as raised:
            mineru_api._call(client, 'POST', 'https://private.invalid?signature=secret-signed-url')
        self.assertEqual(client.calls, 1)
        self.assertEqual(raised.exception.diagnostics['http_status'], 401)
        self.assertNotIn('secret-signed-url', json.dumps(raised.exception.diagnostics))


if __name__ == '__main__':
    unittest.main()
