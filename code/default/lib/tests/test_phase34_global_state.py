import os
import re
import sys
import threading
import time
from unittest import TestCase
from unittest import mock


class TestNoGlobalKeywords(TestCase):
    """Phase 3.4: Verify no 'global' keyword in migrated x_tunnel/local modules."""

    MIGRATED_FILES = [
        'apis.py',
        'openai_handler.py',
        'proxy_session.py',
        'front_dispatcher.py',
        'async_client.py',
        'client.py',
    ]

    def _x_tunnel_local_path(self):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'x_tunnel', 'local'))

    def test_no_global_in_migrated_files(self):
        xt_path = self._x_tunnel_local_path()
        violations = []
        for fname in self.MIGRATED_FILES:
            fpath = os.path.join(xt_path, fname)
            if not os.path.exists(fpath):
                continue
            with open(fpath, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f, 1):
                    if re.match(r'^\s*global\s+', line):
                        violations.append('%s:%d' % (fpath, i))
        self.assertEqual(len(violations), 0,
                         'global keyword found in:\n' + '\n'.join(violations))


class TestContextAttributes(TestCase):
    """Phase 3.4: Verify XTunnelContext has all required attributes."""

    def _import_context(self):
        code_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        if code_root not in sys.path:
            sys.path.insert(0, code_root)
        lib_path = os.path.join(code_root, 'lib', 'noarch')
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        from x_tunnel.local.context import XTunnelContext
        return XTunnelContext

    def test_context_has_ready(self):
        XTunnelContext = self._import_context()
        ctx = XTunnelContext()
        self.assertFalse(ctx.ready)
        ctx.ready = True
        self.assertTrue(ctx.ready)

    def test_context_has_center_login_process(self):
        XTunnelContext = self._import_context()
        ctx = XTunnelContext()
        self.assertFalse(ctx.center_login_process)

    def test_context_has_workable_call_times(self):
        XTunnelContext = self._import_context()
        ctx = XTunnelContext()
        self.assertEqual(ctx.workable_call_times, 0)

    def test_context_has_openai_cache_attrs(self):
        XTunnelContext = self._import_context()
        ctx = XTunnelContext()
        self.assertIsNone(ctx.openai_proxy_host)
        self.assertIsNone(ctx.openai_auth_str)

    def test_context_has_front_dispatcher_attrs(self):
        XTunnelContext = self._import_context()
        ctx = XTunnelContext()
        self.assertEqual(ctx.all_fronts, [])
        self.assertEqual(ctx.light_fronts, [])
        self.assertEqual(ctx.session_fronts, [])
        self.assertIsNone(ctx.statistic_thread)
        self.assertFalse(ctx._front_initialized)
        self.assertFalse(ctx._statistic_running)
        self.assertEqual(ctx._front_fail_counts, {})
        self.assertEqual(ctx._front_last_fail_time, {})


class TestApisNoModuleGlobal(TestCase):
    """Phase 3.4: apis.py workable_call_times is on ctx, not module."""

    def _import_modules(self):
        code_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        if code_root not in sys.path:
            sys.path.insert(0, code_root)
        lib_path = os.path.join(code_root, 'lib', 'noarch')
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        from x_tunnel.local import apis
        from x_tunnel.local import global_var as g
        return apis, g

    def test_no_module_level_workable_call_times(self):
        apis, g = self._import_modules()
        self.assertFalse(hasattr(apis, 'workable_call_times'),
                         "apis.py should not have module-level workable_call_times")

    def test_ctx_workable_call_times_exists(self):
        _, g = self._import_modules()
        self.assertTrue(hasattr(g, 'workable_call_times'))


class TestOpenaiHandlerNoModuleGlobals(TestCase):
    """Phase 3.4: openai_handler.py host/auth_str are on ctx."""

    def _import_modules(self):
        code_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        if code_root not in sys.path:
            sys.path.insert(0, code_root)
        lib_path = os.path.join(code_root, 'lib', 'noarch')
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        from x_tunnel.local import openai_handler
        from x_tunnel.local import global_var as g
        return openai_handler, g

    def test_no_module_level_host(self):
        openai_handler, g = self._import_modules()
        self.assertFalse(hasattr(openai_handler, 'host'),
                         "openai_handler.py should not have module-level 'host'")

    def test_no_module_level_auth_str(self):
        openai_handler, g = self._import_modules()
        self.assertFalse(hasattr(openai_handler, 'auth_str'),
                         "openai_handler.py should not have module-level 'auth_str'")

    def test_ctx_has_openai_proxy_host(self):
        _, g = self._import_modules()
        self.assertTrue(hasattr(g, 'openai_proxy_host'))

    def test_ctx_has_openai_auth_str(self):
        _, g = self._import_modules()
        self.assertTrue(hasattr(g, 'openai_auth_str'))


class TestProxySessionNoModuleGlobal(TestCase):
    """Phase 3.4: proxy_session.py center_login_process is on ctx."""

    def _import_modules(self):
        code_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        if code_root not in sys.path:
            sys.path.insert(0, code_root)
        lib_path = os.path.join(code_root, 'lib', 'noarch')
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        from x_tunnel.local import proxy_session
        from x_tunnel.local import global_var as g
        return proxy_session, g

    def test_no_module_level_center_login_process(self):
        proxy_session, g = self._import_modules()
        self.assertFalse(hasattr(proxy_session, 'center_login_process'),
                         "proxy_session.py should not have module-level center_login_process")

    def test_ctx_has_center_login_process(self):
        _, g = self._import_modules()
        self.assertTrue(hasattr(g, 'center_login_process'))


class TestClientNoModuleGlobalReady(TestCase):
    """Phase 3.4: client.py and async_client.py 'ready' is on ctx."""

    def _import_modules(self):
        code_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        if code_root not in sys.path:
            sys.path.insert(0, code_root)
        lib_path = os.path.join(code_root, 'lib', 'noarch')
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        from x_tunnel.local import global_var as g
        return g

    def test_ctx_ready_default_false(self):
        g = self._import_modules()
        self.assertFalse(g.ready)

    def test_ctx_ready_settable(self):
        g = self._import_modules()
        g.ready = True
        self.assertTrue(g.ready)
        g.ready = False
        self.assertFalse(g.ready)


class TestFrontDispatcherStateOnCtx(TestCase):
    """Phase 3.4: front_dispatcher state lives on ctx, module __getattr__ proxies."""

    def _import_modules(self):
        code_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        if code_root not in sys.path:
            sys.path.insert(0, code_root)
        lib_path = os.path.join(code_root, 'lib', 'noarch')
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        from x_tunnel.local import front_dispatcher
        from x_tunnel.local import global_var as g
        return front_dispatcher, g

    def test_no_module_level_all_fronts(self):
        fd, g = self._import_modules()
        self.assertNotIn('all_fronts', fd.__dict__,
                         "front_dispatcher should not have 'all_fronts' in __dict__")

    def test_module_getattr_proxies_all_fronts(self):
        fd, g = self._import_modules()
        g.all_fronts = ['test_front']
        self.assertEqual(fd.all_fronts, ['test_front'])
        g.all_fronts = []

    def test_module_getattr_proxies_session_fronts(self):
        fd, g = self._import_modules()
        g.session_fronts = ['session_front']
        self.assertEqual(fd.session_fronts, ['session_front'])
        g.session_fronts = []

    def test_module_getattr_proxies_cloudflare_front(self):
        fd, g = self._import_modules()
        self.assertIsNone(fd.cloudflare_front)

    def test_module_getattr_raises_on_unknown(self):
        fd, g = self._import_modules()
        with self.assertRaises(AttributeError):
            _ = fd.nonexistent_attr_xyz


class TestInitModuleReadyAccess(TestCase):
    """Phase 3.4: __init__.py is_ready() reads from ctx."""

    def _import_modules(self):
        code_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        if code_root not in sys.path:
            sys.path.insert(0, code_root)
        lib_path = os.path.join(code_root, 'lib', 'noarch')
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        import x_tunnel.local as xt_local
        from x_tunnel.local import global_var as g
        return xt_local, g

    def test_is_ready_false_initially(self):
        xt_local, g = self._import_modules()
        g.ready = False
        self.assertFalse(xt_local.is_ready())

    def test_is_ready_true_when_ctx_ready(self):
        xt_local, g = self._import_modules()
        g.ready = True
        self.assertTrue(xt_local.is_ready())
        g.ready = False


class TestFrontDispatcherInitStop(TestCase):
    """Phase 3.4: Verify front_dispatcher init/stop correctly manages ctx state."""

    def _import_modules(self):
        code_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        if code_root not in sys.path:
            sys.path.insert(0, code_root)
        lib_path = os.path.join(code_root, 'lib', 'noarch')
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        from x_tunnel.local import front_dispatcher
        from x_tunnel.local import global_var as g
        return front_dispatcher, g

    def test_init_sets_front_initialized(self):
        fd, g = self._import_modules()
        g._front_initialized = False
        g.all_fronts = []
        g.session_fronts = []
        g.light_fronts = []
        g._front_fail_counts = {}
        g._front_last_fail_time = {}

        class FakeConfig:
            enable_cloudflare = False
            enable_cloudfront = False
            enable_seley = False
            enable_tls_relay = False
            enable_direct = False
            show_state_debug = False
        g.config = FakeConfig()

        fd.init()
        self.assertTrue(g._front_initialized)

        fd.stop()
        self.assertFalse(g._front_initialized)
        self.assertEqual(g.all_fronts, [])
        self.assertEqual(g.session_fronts, [])
        self.assertEqual(g.light_fronts, [])

    def test_init_idempotent_via_ctx(self):
        fd, g = self._import_modules()
        g._front_initialized = False
        g.all_fronts = []
        g.session_fronts = []
        g.light_fronts = []
        g._front_fail_counts = {}
        g._front_last_fail_time = {}

        class FakeConfig:
            enable_cloudflare = False
            enable_cloudfront = False
            enable_seley = False
            enable_tls_relay = False
            enable_direct = False
            show_state_debug = False
        g.config = FakeConfig()

        fd.init()
        call_count = [0]
        orig_init = g._front_initialized
        fd.init()
        self.assertTrue(g._front_initialized)

        fd.stop()

    def test_stop_resets_fail_counts(self):
        fd, g = self._import_modules()
        g._front_initialized = False
        g._statistic_running = False
        g.all_fronts = []
        g._front_fail_counts = {"test": 5}
        g._front_last_fail_time = {"test": 100.0}
        g.statistic_thread = None

        fd.stop()
        self.assertEqual(g._front_fail_counts, {})
        self.assertEqual(g._front_last_fail_time, {})

    def test_getattr_proxies_initialized_correctly(self):
        fd, g = self._import_modules()
        orig = g._front_initialized
        g._front_initialized = True
        self.assertTrue(fd._initialized)
        g._front_initialized = orig

    def test_record_fail_increments_via_ctx(self):
        fd, g = self._import_modules()
        g._front_fail_counts = {}
        g._front_last_fail_time = {}

        class FakeFront:
            name = "test_front"
        fd._record_front_fail(FakeFront())
        self.assertEqual(g._front_fail_counts["test_front"], 1)
        self.assertIn("test_front", g._front_last_fail_time)
        g._front_fail_counts = {}
        g._front_last_fail_time = {}


class TestCenterLoginProcessFlow(TestCase):
    """Phase 3.4: Verify center_login_process works correctly via ctx."""

    def test_center_login_process_via_g(self):
        code_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        if code_root not in sys.path:
            sys.path.insert(0, code_root)
        lib_path = os.path.join(code_root, 'lib', 'noarch')
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        from x_tunnel.local import global_var as g

        g.center_login_process = False
        self.assertFalse(g.center_login_process)
        g.center_login_process = True
        self.assertTrue(g.center_login_process)
        g.center_login_process = False
