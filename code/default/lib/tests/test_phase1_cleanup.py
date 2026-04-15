import sys
import os
import importlib
import subprocess

from unittest import TestCase


class TestNoSixDependency(TestCase):
    """Phase 1.1.1-1.1.4: Verify all 'six' references are removed from non-vendored code."""

    NON_VENDORED_FILES = [
        os.path.join('lib', 'noarch', 'utils.py'),
        os.path.join('lib', 'noarch', 'xlog.py'),
        os.path.join('lib', 'noarch', 'socks.py'),
        os.path.join('lib', 'noarch', 'front_base', 'http2_connection.py'),
        os.path.join('lib', 'noarch', 'front_base', 'http_dispatcher.py'),
        os.path.join('lib', 'noarch', 'front_base', 'ip_manager.py'),
    ]

    def _code_root(self):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

    def test_no_from_six_import(self):
        for rel in self.NON_VENDORED_FILES:
            fpath = os.path.join(self._code_root(), rel)
            if not os.path.isfile(fpath):
                continue
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            self.assertNotIn('from six', content,
                             f'{rel} still contains "from six" import')

    def test_no_import_six(self):
        for rel in self.NON_VENDORED_FILES:
            fpath = os.path.join(self._code_root(), rel)
            if not os.path.isfile(fpath):
                continue
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                for i, line in enumerate(f, 1):
                    stripped = line.strip()
                    if stripped.startswith('#'):
                        continue
                    self.assertFalse(
                        stripped.startswith('import six') and 'six.moves' not in stripped,
                        f'{rel}:{i} still has "import six"'
                    )

    def test_six_py_deleted(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'six.py')
        self.assertFalse(os.path.isfile(fpath), 'six.py should be deleted')


class TestNoPy3Compat(TestCase):
    """Phase 1.1.5-1.1.6: Verify py3_compat.py is removed."""

    def _code_root(self):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

    def test_py3_compat_deleted(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'py3_compat.py')
        self.assertFalse(os.path.isfile(fpath), 'py3_compat.py should be deleted')

    def test_no_py3_compat_import_in_start(self):
        fpath = os.path.join(self._code_root(), 'launcher', 'start.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertNotIn('py3_compat', content,
                         'launcher/start.py still imports py3_compat')

    def test_no_py3_compat_import_in_web_control(self):
        fpath = os.path.join(self._code_root(), 'launcher', 'web_control.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertNotIn('py3_compat', content,
                         'launcher/web_control.py still imports py3_compat')


class TestNoPython2VersionChecks(TestCase):
    """Phase 1.1.7: Verify sys.version_info Python 2 checks are removed."""

    FILES_TO_CHECK = [
        os.path.join('lib', 'noarch', 'front_base', 'ssl_wrap.py'),
        os.path.join('lib', 'noarch', 'front_base', 'openssl_wrap.py'),
        os.path.join('lib', 'noarch', 'front_base', 'connect_creator.py'),
    ]

    def _code_root(self):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

    def test_no_python2_version_checks(self):
        for rel in self.FILES_TO_CHECK:
            fpath = os.path.join(self._code_root(), rel)
            if not os.path.isfile(fpath):
                continue
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                for i, line in enumerate(f, 1):
                    if line.strip().startswith('#'):
                        continue
                    self.assertNotIn('sys.version_info[0] == 2', line,
                                     f'{rel}:{i} has Python 2 version check')
                    self.assertNotIn("sys.version_info >= (2, 7, 5)", line,
                                     f'{rel}:{i} has Python 2.7.5 version check')


class TestNoPython2Shebang(TestCase):
    """Phase 1.1.8: Verify no python2 shebangs remain."""

    SHEBANG_FILES = [
        os.path.join('x_tunnel', 'local', 'cloudflare_front', 'test.py'),
        os.path.join('x_tunnel', 'local', 'cloudfront_front', 'test.py'),
        os.path.join('x_tunnel', 'local', 'cloudfront_front', 'check_ip.py'),
        os.path.join('x_tunnel', 'local', 'seley_front', 'test.py'),
        os.path.join('x_tunnel', 'local', 'tls_relay_front', 'test.py'),
    ]

    def _code_root(self):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

    def test_no_python2_shebang(self):
        for rel in self.SHEBANG_FILES:
            fpath = os.path.join(self._code_root(), rel)
            if not os.path.isfile(fpath):
                continue
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                first_line = f.readline()
            self.assertNotIn('python2', first_line,
                             f'{rel} still has python2 shebang')


class TestPyOpenSSLWrapDeleted(TestCase):
    """Phase 1.2.1: Verify pyopenssl_wrap.py is deleted."""

    def _code_root(self):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

    def test_pyopenssl_wrap_deleted(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'front_base', 'pyopenssl_wrap.py')
        self.assertFalse(os.path.isfile(fpath), 'pyopenssl_wrap.py should be deleted')


class TestOpenSSLWrapSimplified(TestCase):
    """Phase 1.2.2: Verify openssl_wrap.py no longer has Python 2 branches."""

    def _code_root(self):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

    def test_openssl_wrap_no_python2_branch(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'front_base', 'openssl_wrap.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertNotIn('sys.version_info', content,
                         'openssl_wrap.py should not have version checks')
        self.assertNotIn('pyopenssl_wrap', content,
                         'openssl_wrap.py should not reference pyopenssl_wrap')


class TestNoSelectors2(TestCase):
    """Phase 1.3.1: Verify selectors2.py is deleted and not imported."""

    def _code_root(self):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

    def test_selectors2_deleted(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'selectors2.py')
        self.assertFalse(os.path.isfile(fpath), 'selectors2.py should be deleted')

    def test_no_selectors2_import(self):
        code_root = self._code_root()
        search_dirs = [
            os.path.join(code_root, 'lib', 'noarch'),
            os.path.join(code_root, 'x_tunnel'),
        ]
        dirs_to_skip = ['ecdsa', 'hyper', 'pyasn1', 'sortedcontainers',
                        'asn1crypto', 'dnslib', 'scrypto', '__pycache__']
        for search_root in search_dirs:
            for root, dirs, files in os.walk(search_root):
                dirs[:] = [d for d in dirs if d not in dirs_to_skip]
                for fname in files:
                    if not fname.endswith('.py'):
                        continue
                    fpath = os.path.join(root, fname)
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    self.assertNotIn('import selectors2', content,
                                     f'{fpath} still imports selectors2')
                    self.assertNotIn('from selectors2', content,
                                     f'{fpath} still imports from selectors2')


class TestNoSSLv3Fallback(TestCase):
    """Phase 1.3.2: Verify SSLv3/SSLv2 protocol fallbacks are removed."""

    def _code_root(self):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

    def test_no_sslv3_sslv2_in_ssl_wrap(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'front_base', 'ssl_wrap.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertNotIn('PROTOCOL_SSLv3', content,
                         'ssl_wrap.py should not reference PROTOCOL_SSLv3')
        self.assertNotIn('PROTOCOL_SSLv2', content,
                         'ssl_wrap.py should not reference PROTOCOL_SSLv2')


class TestUtilsFunctionsStillWork(TestCase):
    """Verify utils.py functions work correctly after removing six dependency."""

    def test_to_bytes_with_str(self):
        import utils
        self.assertEqual(utils.to_bytes('hello'), b'hello')

    def test_to_bytes_with_bytes(self):
        import utils
        self.assertEqual(utils.to_bytes(b'hello'), b'hello')

    def test_to_bytes_with_int(self):
        import utils
        self.assertEqual(utils.to_bytes(42), b'42')

    def test_to_str_with_bytes(self):
        import utils
        self.assertEqual(utils.to_str(b'hello'), 'hello')

    def test_to_str_with_str(self):
        import utils
        self.assertEqual(utils.to_str('hello'), 'hello')

    def test_to_str_with_int(self):
        import utils
        self.assertEqual(utils.to_str(42), '42')

    def test_check_ip_valid4(self):
        import utils
        self.assertTrue(utils.check_ip_valid4('192.168.1.1'))
        self.assertTrue(utils.check_ip_valid4(b'192.168.1.1'))
        self.assertFalse(utils.check_ip_valid4('not-an-ip'))

    def test_get_ip_port_ipv4(self):
        import utils
        ip, port = utils.get_ip_port('1.2.3.4:8080')
        self.assertEqual(ip, b'1.2.3.4')
        self.assertEqual(port, 8080)

    def test_get_ip_port_ipv4_no_port(self):
        import utils
        ip, port = utils.get_ip_port('1.2.3.4')
        self.assertEqual(ip, b'1.2.3.4')
        self.assertEqual(port, 443)

    def test_merge_two_dict(self):
        import utils
        x = {'a': 1, 'b': 2}
        y = {'b': 3, 'c': 4}
        z = utils.merge_two_dict(x, y)
        self.assertEqual(z, {'a': 1, 'b': 3, 'c': 4})
