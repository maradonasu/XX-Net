import os
import re
from unittest import TestCase


class TestNoBareExcept(TestCase):
    """Phase 3.3: Verify no bare except: in project code (excluding vendored libs)."""

    VENDORED_DIRS = {
        'scrypto', 'idna',
        '__pycache__', 'tests',
    }

    def _code_root(self):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

    def test_no_bare_except_in_project_code(self):
        code_root = self._code_root()
        bare_except_re = re.compile(r'^\s*except\s*:\s*$')
        violations = []

        for root, dirs, files in os.walk(code_root):
            dirs[:] = [d for d in dirs if d not in self.VENDORED_DIRS]
            for fname in files:
                if not fname.endswith('.py'):
                    continue
                fpath = os.path.join(root, fname)
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                    for i, line in enumerate(f, 1):
                        if bare_except_re.match(line):
                            violations.append('%s:%d' % (fpath, i))

        self.assertEqual(len(violations), 0,
                         'Bare except: found in:\n' + '\n'.join(violations))


class TestTypeAnnotations(TestCase):
    """Phase 3.5: Verify core modules have type annotations."""

    def _code_root(self):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

    def test_utils_has_type_annotations(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'utils.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('from typing import', content)
        self.assertIn('def check_ip_valid4(ip: ', content)
        self.assertIn('def get_ip_port(ip_str: ', content)
        self.assertIn('def to_bytes(data: ', content)
        self.assertIn('def to_str(data: ', content)
        self.assertIn('def merge_two_dict(x: dict', content)

    def test_base_container_has_type_annotations(self):
        fpath = os.path.join(self._code_root(), 'x_tunnel', 'local', 'async_base_container.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('from typing import', content)
        self.assertIn('class WriteBuffer:', content)
        self.assertIn('class ReadBuffer:', content)
        self.assertIn('def __init__(self, s: Optional[bytes] = None)', content)

    def test_proxy_session_has_type_annotations(self):
        fpath = os.path.join(self._code_root(), 'x_tunnel', 'local', 'async_proxy_session.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('from typing import', content)
        
        api_fpath = os.path.join(self._code_root(), 'x_tunnel', 'local', 'api_client.py')
        with open(api_fpath, 'r', encoding='utf-8') as f:
            api_content = f.read()
        self.assertIn('def encrypt_data(data: ', api_content)
        self.assertIn('def decrypt_data(data: ', api_content)

    def test_connect_creator_has_type_annotations(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'front_base', 'connect_creator.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('from __future__ import annotations', content)
        self.assertIn('from typing import', content)
        self.assertIn('def __init__(self, logger: Any', content)
        self.assertIn('def connect_ssl(self, ip_str: ', content)

    def test_front_dispatcher_has_type_annotations(self):
        fpath = os.path.join(self._code_root(), 'x_tunnel', 'local', 'front_dispatcher.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('from __future__ import annotations', content)
        self.assertIn('from typing import', content)
        self.assertIn('FRONT_FAIL_BASE_PENALTY: int', content)
        self.assertIn('def get_front(host: str', content)
        self.assertIn('def request(method: str', content)

    def test_context_class_exists(self):
        fpath = os.path.join(self._code_root(), 'x_tunnel', 'local', 'context.py')
        self.assertTrue(os.path.exists(fpath))
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('class XTunnelContext', content)
        self.assertIn('def is_running(self) -> bool', content)
        self.assertIn('class _GlobalVarProxy', content)
        self.assertIn('ctx: _GlobalVarProxy', content)
        self.assertIn('_context: XTunnelContext', content)

    def test_global_var_deleted(self):
        fpath = os.path.join(self._code_root(), 'x_tunnel', 'local', 'global_var.py')
        self.assertFalse(os.path.exists(fpath), "global_var.py should be deleted")

    def test_context_is_singleton(self):
        import sys
        code_root = self._code_root()
        if code_root not in sys.path:
            sys.path.insert(0, code_root)
        lib_path = os.path.join(code_root, 'lib', 'noarch')
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        from x_tunnel.local.context import ctx, _context, XTunnelContext, _GlobalVarProxy
        self.assertIsInstance(ctx, _GlobalVarProxy)
        self.assertIsInstance(_context, XTunnelContext)
        self.assertIs(ctx._ctx, _context)

    def test_ctx_and_g_share_same_context(self):
        import sys
        code_root = self._code_root()
        if code_root not in sys.path:
            sys.path.insert(0, code_root)
        lib_path = os.path.join(code_root, 'lib', 'noarch')
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)

        from x_tunnel.local.context import ctx, _context

        ctx.test_di_attr = 'via_ctx'
        self.assertEqual(_context.test_di_attr, 'via_ctx')

        _context.test_di_attr2 = 'via_context'
        self.assertEqual(ctx.test_di_attr2, 'via_context')

        self.assertIs(ctx._ctx, _context)

        del _context.test_di_attr
        del _context.test_di_attr2

    def test_http_server_uses_stdlib(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'http_server.py')
        self.assertTrue(os.path.exists(fpath))
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('from http.server import', content)
        self.assertIn('from socketserver import ThreadingMixIn', content)
        self.assertIn('class ThreadedHTTPServer', content)
        self.assertIn('class HttpServerHandler(BaseHTTPRequestHandler)', content)

    def test_connect_manager_has_type_annotations(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'front_base', 'connect_manager.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('from typing import', content)
        self.assertIn('def get_ssl_connection(self, timeout: float', content)
        self.assertIn('def _create_ssl_connection(self, host_info: dict', content)
        self.assertIn('def stop(self) -> None', content)

    def test_simple_http_server_deleted(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'simple_http_server.py')
        self.assertFalse(os.path.exists(fpath))

    def test_http_server_direct_import(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'http_server.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('class HTTPServer', content)
        self.assertIn('class HttpServerHandler', content)
        self.assertIn('class TestHttpServer', content)

    def test_no_simple_http_server_imports_remain(self):
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
                        if 'simple_http_server' in line and 'test_' not in fname:
                            violations.append('%s:%d' % (fpath, i))
        self.assertEqual(len(violations), 0,
                         'simple_http_server imports found in:\n' + '\n'.join(violations))

    def test_simple_http_client_deleted(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'simple_http_client.py')
        self.assertFalse(os.path.exists(fpath),
                         'simple_http_client.py shim should be deleted')

    def test_http_client_uses_httpx(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'http_client.py')
        self.assertTrue(os.path.exists(fpath))
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('import httpx', content)
        self.assertIn('class Client', content)
        self.assertIn('httpx.Client(', content)

    def test_http_response_parser_exists(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'http_response_parser.py')
        self.assertTrue(os.path.exists(fpath))
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('class Response', content)
        self.assertIn('class TxtResponse', content)
        self.assertIn('class BaseResponse', content)
