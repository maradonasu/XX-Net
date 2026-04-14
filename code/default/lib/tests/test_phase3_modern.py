import os
import re
from unittest import TestCase


class TestNoBareExcept(TestCase):
    """Phase 3.3: Verify no bare except: in project code (excluding vendored libs)."""

    VENDORED_DIRS = {
        'hyper', 'tlslite', 'scrypto', 'idna', 'boringssl',
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
        fpath = os.path.join(self._code_root(), 'x_tunnel', 'local', 'base_container.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('from __future__ import annotations', content)
        self.assertIn('from typing import', content)
        self.assertIn('def __init__(self, s: Optional[bytes]', content)
        self.assertIn('def __init__(self, session: Any, xlog: Any)', content)

    def test_proxy_handler_has_type_annotations(self):
        fpath = os.path.join(self._code_root(), 'x_tunnel', 'local', 'proxy_handler.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('from __future__ import annotations', content)
        self.assertIn('from typing import', content)
        self.assertIn('def netloc_to_host_port(netloc: ', content)
        self.assertIn('def __init__(self, sock: socket.socket', content)
        self.assertIn('def read_bytes(self, size: int)', content)

    def test_proxy_session_has_type_annotations(self):
        fpath = os.path.join(self._code_root(), 'x_tunnel', 'local', 'proxy_session.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('from typing import', content)
        self.assertIn('def encrypt_data(data: ', content)
        self.assertIn('def decrypt_data(data: ', content)
        self.assertIn('def create_conn(self, sock: socket.socket', content)
        self.assertIn('def login_session(self) -> bool', content)
