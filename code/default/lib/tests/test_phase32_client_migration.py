import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'noarch'))


class TestSimpleHttpClientDeleted(unittest.TestCase):
    """Phase 3.2 final: simple_http_client.py shim must be deleted."""

    def _code_root(self):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

    def test_simple_http_client_file_deleted(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'simple_http_client.py')
        self.assertFalse(os.path.exists(fpath),
                         'simple_http_client.py should be deleted')

    def test_no_simple_http_client_imports_remain(self):
        code_root = self._code_root()
        violations = []
        for root, dirs, files in os.walk(code_root):
            dirs[:] = [d for d in dirs if d not in {'__pycache__', 'tests', '.git'}]
            for fname in files:
                if not fname.endswith('.py'):
                    continue
                fpath = os.path.join(root, fname)
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                    for i, line in enumerate(f, 1):
                        if re.search(r'\bsimple_http_client\b', line):
                            violations.append('%s:%d' % (fpath, i))
        self.assertEqual(len(violations), 0,
                         'simple_http_client refs found in:\n' + '\n'.join(violations))


class TestHttp1DirectImport(unittest.TestCase):
    """Verify http1.py imports http_response_parser directly, not via alias."""

    def _front_base(self):
        return os.path.join(os.path.dirname(__file__), '..', 'noarch', 'front_base')

    def test_http1_no_simple_http_client_alias(self):
        fpath = os.path.join(self._front_base(), 'http1.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertNotIn('as simple_http_client', content,
                         'http1.py should not alias http_response_parser as simple_http_client')
        self.assertNotIn('simple_http_client', content,
                         'http1.py should not reference simple_http_client at all')

    def test_http1_imports_response(self):
        fpath = os.path.join(self._front_base(), 'http1.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertTrue(
            re.search(r'from\s+http_response_parser\s+import.*Response', content) is not None
            or 'import http_response_parser' in content,
            'http1.py should import Response from http_response_parser directly'
        )

    def test_http1_uses_response_class_directly(self):
        fpath = os.path.join(self._front_base(), 'http1.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertNotIn('simple_http_client.Response', content)
        self.assertIn('Response(', content,
                       'http1.py should use Response class directly')


class TestHttp2StreamDirectImport(unittest.TestCase):
    """Verify http2_stream.py imports from http_response_parser directly."""

    def _front_base(self):
        return os.path.join(os.path.dirname(__file__), '..', 'noarch', 'front_base')

    def test_http2_stream_no_simple_http_client(self):
        fpath = os.path.join(self._front_base(), 'http2_stream.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertNotIn('simple_http_client', content,
                         'http2_stream.py should not reference simple_http_client')

    def test_http2_stream_imports_base_response(self):
        fpath = os.path.join(self._front_base(), 'http2_stream.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('from http_response_parser import', content,
                       'http2_stream.py should import from http_response_parser')


class TestHttpCommonDirectImport(unittest.TestCase):
    """Verify http_common.py imports from http_response_parser directly."""

    def _front_base(self):
        return os.path.join(os.path.dirname(__file__), '..', 'noarch', 'front_base')

    def test_http_common_no_simple_http_client(self):
        fpath = os.path.join(self._front_base(), 'http_common.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertNotIn('simple_http_client', content)

    def test_http_common_imports_base_response(self):
        fpath = os.path.join(self._front_base(), 'http_common.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('from http_response_parser import BaseResponse', content)


class TestHttpResponseParserClasses(unittest.TestCase):
    """Verify http_response_parser classes work correctly."""

    def test_base_response_status_and_reason(self):
        from http_response_parser import BaseResponse
        r = BaseResponse(status=200, reason=b'OK')
        self.assertEqual(r.status, 200)
        self.assertEqual(r.reason, b'OK')

    def test_base_response_headers_titlecased(self):
        from http_response_parser import BaseResponse
        r = BaseResponse(status=200, headers={b'content-type': b'text/html'})
        self.assertEqual(r.getheader(b'Content-Type'), b'text/html')

    def test_base_response_getheader_default(self):
        from http_response_parser import BaseResponse
        r = BaseResponse(status=200)
        self.assertEqual(r.getheader('X-Missing', b'fallback'), b'fallback')

    def test_base_response_text_body(self):
        from http_response_parser import BaseResponse
        r = BaseResponse(status=200, body=b'hello')
        self.assertEqual(r.text, b'hello')

    def test_txt_response_parse_ok(self):
        from http_response_parser import TxtResponse
        buf = b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nhello'
        r = TxtResponse(buf)
        self.assertEqual(r.status, 200)
        self.assertEqual(r.version, b'HTTP/1.1')
        self.assertEqual(r.body, b'hello')

    def test_txt_response_parse_404(self):
        from http_response_parser import TxtResponse
        buf = b'HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n'
        r = TxtResponse(buf)
        self.assertEqual(r.status, 404)
        self.assertEqual(r.info, b'Not Found')

    def test_txt_response_headers(self):
        from http_response_parser import TxtResponse
        buf = b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nX-Cost: 0.5\r\n\r\n'
        r = TxtResponse(buf)
        self.assertEqual(r.headers[b'Content-Type'], b'text/plain')
        self.assertEqual(r.headers[b'X-Cost'], b'0.5')


class TestHttpClientModule(unittest.TestCase):
    """Verify http_client.py high-level API."""

    def test_client_class_exists(self):
        from http_client import Client
        c = Client()
        self.assertIsNone(c.proxy)

    def test_request_function_exists(self):
        from http_client import request
        self.assertTrue(callable(request))

    def test_client_with_proxy_dict(self):
        from http_client import Client
        proxy = {"type": "socks5", "host": "127.0.0.1", "port": 1080}
        c = Client(proxy=proxy)
        self.assertEqual(c.proxy["type"], "socks5")
        self.assertEqual(c.proxy["host"], "127.0.0.1")


if __name__ == '__main__':
    unittest.main()
