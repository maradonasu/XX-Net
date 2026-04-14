import sys
import os
import importlib
import subprocess
import tempfile
import json

from unittest import TestCase


class TestBundledLibsRemoved(TestCase):
    """Phase 2.1.1/2.3.1-2.3.4: Verify bundled libs are deleted."""

    def _code_root(self):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

    def test_pyasn1_deleted(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'pyasn1')
        self.assertFalse(os.path.isdir(fpath), 'bundled pyasn1/ should be deleted')

    def test_dnslib_deleted(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'dnslib')
        self.assertFalse(os.path.isdir(fpath), 'bundled dnslib/ should be deleted')

    def test_sortedcontainers_deleted(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'sortedcontainers')
        self.assertFalse(os.path.isdir(fpath), 'bundled sortedcontainers/ should be deleted')

    def test_asn1crypto_deleted(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'asn1crypto')
        self.assertFalse(os.path.isdir(fpath), 'bundled asn1crypto/ should be deleted')

    def test_ecdsa_deleted(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'ecdsa')
        self.assertFalse(os.path.isdir(fpath), 'bundled ecdsa/ should be deleted')

    def test_socks_deleted(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'socks.py')
        self.assertFalse(os.path.isfile(fpath), 'bundled socks.py should be deleted')

    def test_hyper_deleted(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'hyper')
        self.assertFalse(os.path.isdir(fpath), 'bundled hyper/ should be deleted')


class TestPipImportsWork(TestCase):
    """Phase 2: Verify pip-installed packages work as imports."""

    def _code_root(self):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

    def test_pyasn1_import(self):
        from pyasn1.codec.der.decoder import decode
        from pyasn1.type import univ
        self.assertTrue(callable(decode))

    def test_dnslib_import(self):
        from dnslib.dns import DNSRecord
        self.assertTrue(callable(DNSRecord))

    def test_asn1crypto_import(self):
        from asn1crypto.x509 import Certificate
        self.assertTrue(callable(Certificate))

    def test_ecdsa_import(self):
        from ecdsa.keys import VerifyingKey
        self.assertTrue(callable(VerifyingKey))

    def test_socks_import(self):
        import socks
        self.assertTrue(hasattr(socks, 'socksocket'))
        self.assertTrue(hasattr(socks, 'set_default_proxy'))

    def test_h2_import(self):
        from h2.connection import H2Connection
        self.assertTrue(callable(H2Connection))

    def test_hpack_import(self):
        from hpack import Encoder, Decoder
        self.assertTrue(callable(Encoder))
        self.assertTrue(callable(Decoder))

    def test_hyperframe_import(self):
        from hyperframe.frame import DataFrame, HeadersFrame, SettingsFrame
        self.assertTrue(callable(DataFrame))
        self.assertTrue(callable(HeadersFrame))
        self.assertTrue(callable(SettingsFrame))

    def test_hyper_compat_import(self):
        sys.path.insert(0, os.path.join(self._code_root(), 'lib', 'noarch'))
        from hyper_compat import HTTP20Connection, BufferedSocket, FlowControlManager
        self.assertTrue(callable(HTTP20Connection))
        self.assertTrue(callable(BufferedSocket))
        self.assertTrue(callable(FlowControlManager))


class TestXlogStdlibLogging(TestCase):
    """Phase 2.2.1-2.2.5: Verify xlog uses stdlib logging internally."""

    def _code_root(self):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

    def test_xlog_imports_logging(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'xlog.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn('import logging', content,
                      'xlog.py should import stdlib logging')

    def test_xlog_getLogger_returns_logger(self):
        from xlog import getLogger
        logger = getLogger("test_phase2")
        self.assertTrue(hasattr(logger, 'debug'))
        self.assertTrue(hasattr(logger, 'info'))
        self.assertTrue(hasattr(logger, 'warn'))
        self.assertTrue(hasattr(logger, 'error'))
        self.assertTrue(hasattr(logger, 'exception'))

    def test_xlog_log_levels(self):
        from xlog import getLogger
        logger = getLogger("test_phase2_levels", buffer_size=10)
        logger.info("test info message")
        logger.warn("test warn message")
        logger.error("test error message")
        logger.debug("test debug message")
        self.assertTrue(len(logger.buffer) >= 4)

    def test_xlog_buffer_works(self):
        from xlog import getLogger
        logger = getLogger("test_phase2_buffer", buffer_size=5)
        for i in range(10):
            logger.info("msg %d", i)
        self.assertTrue(len(logger.buffer) <= 5)

    def test_xlog_setLevel(self):
        from xlog import getLogger
        logger = getLogger("test_phase2_level")
        logger.setLevel("ERROR")
        self.assertEqual(logger.min_level, 40)

    def test_xlog_get_last_lines(self):
        from xlog import getLogger
        logger = getLogger("test_phase2_lastlines", buffer_size=100)
        logger.info("line1")
        logger.info("line2")
        lines = logger.get_last_lines(2)
        data = json.loads(lines)
        self.assertEqual(len(data), 2)


class TestXconfigNoXlogImport(TestCase):
    """Phase 2.2.6-2.2.9: Verify xconfig no longer imports xlog."""

    def _code_root(self):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

    def test_xconfig_no_xlog_import(self):
        fpath = os.path.join(self._code_root(), 'lib', 'noarch', 'xconfig.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertNotIn('import xlog', content,
                         'xconfig.py should not import xlog')
        self.assertIn('import logging', content,
                      'xconfig.py should use stdlib logging')

    def test_xconfig_works(self):
        import xconfig
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            path = f.name
        try:
            config = xconfig.Config(path)
            config.set_var("test_key", "test_value")
            config.load()
            self.assertEqual(config.test_key, "test_value")

            config.test_key = "new_value"
            config.save()
            with open(path, 'r') as f:
                data = json.load(f)
            self.assertEqual(data["test_key"], "new_value")
        finally:
            os.unlink(path)


class TestRequirementsUpdated(TestCase):
    """Phase 2.3.6: Verify requirements.txt has all new dependencies."""

    def _root(self):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

    def test_requirements_has_pyasn1(self):
        with open(os.path.join(self._root(), 'requirements.txt'), 'r') as f:
            content = f.read()
        self.assertIn('pyasn1', content)
        self.assertIn('dnslib', content)
        self.assertIn('asn1crypto', content)
        self.assertIn('ecdsa', content)
        self.assertIn('PySocks', content)
        self.assertIn('sortedcontainers', content)
        self.assertIn('h2', content)
        self.assertIn('hpack', content)
        self.assertIn('hyperframe', content)
