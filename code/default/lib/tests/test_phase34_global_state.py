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
        'front_dispatcher.py',
        'async_client.py',
        'async_proxy_session.py',
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
        from x_tunnel.local.context import ctx
        return apis, ctx

    def test_no_module_level_workable_call_times(self):
        apis, ctx = self._import_modules()
        self.assertFalse(hasattr(apis, 'workable_call_times'),
                         "apis.py should not have module-level workable_call_times")

    def test_ctx_workable_call_times_exists(self):
        _, ctx = self._import_modules()
        self.assertTrue(hasattr(ctx, 'workable_call_times'))


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
        from x_tunnel.local.context import ctx
        return openai_handler, ctx

    def test_no_module_level_host(self):
        openai_handler, ctx = self._import_modules()
        self.assertFalse(hasattr(openai_handler, 'host'),
                         "openai_handler.py should not have module-level 'host'")

    def test_no_module_level_auth_str(self):
        openai_handler, ctx = self._import_modules()
        self.assertFalse(hasattr(openai_handler, 'auth_str'),
                         "openai_handler.py should not have module-level 'auth_str'")

    def test_ctx_has_openai_proxy_host(self):
        _, ctx = self._import_modules()
        self.assertTrue(hasattr(ctx, 'openai_proxy_host'))

    def test_ctx_has_openai_auth_str(self):
        _, ctx = self._import_modules()
        self.assertTrue(hasattr(ctx, 'openai_auth_str'))


class TestApiClientNoModuleGlobal(TestCase):
    """Phase 3.4: api_client.py functions are available."""

    def test_api_client_imports_work(self):
        code_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        if code_root not in sys.path:
            sys.path.insert(0, code_root)
        lib_path = os.path.join(code_root, 'lib', 'noarch')
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        from x_tunnel.local import api_client
        self.assertTrue(hasattr(api_client, 'request_balance'))
        self.assertTrue(hasattr(api_client, 'async_request_balance'))

    def test_ctx_has_center_login_process(self):
        code_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        if code_root not in sys.path:
            sys.path.insert(0, code_root)
        lib_path = os.path.join(code_root, 'lib', 'noarch')
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        from x_tunnel.local.context import ctx
        self.assertTrue(hasattr(ctx, 'center_login_process'))


class TestClientNoModuleGlobalReady(TestCase):
    """Phase 3.4: async_client.py 'ready' is on ctx."""

    def _import_modules(self):
        code_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        if code_root not in sys.path:
            sys.path.insert(0, code_root)
        lib_path = os.path.join(code_root, 'lib', 'noarch')
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        from x_tunnel.local.context import ctx
        return ctx

    def test_ctx_ready_default_false(self):
        ctx = self._import_modules()
        ctx.ready = False
        self.assertFalse(ctx.ready)

    def test_ctx_ready_settable(self):
        ctx = self._import_modules()
        ctx.ready = True
        self.assertTrue(ctx.ready)
        ctx.ready = False
        self.assertFalse(ctx.ready)


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
        from x_tunnel.local.context import ctx
        return front_dispatcher, ctx

    def test_no_module_level_all_fronts(self):
        fd, ctx = self._import_modules()
        self.assertNotIn('all_fronts', fd.__dict__,
                         "front_dispatcher should not have 'all_fronts' in __dict__")

    def test_module_getattr_proxies_all_fronts(self):
        fd, ctx = self._import_modules()
        ctx.all_fronts = ['test_front']
        self.assertEqual(fd.all_fronts, ['test_front'])
        ctx.all_fronts = []

    def test_module_getattr_proxies_session_fronts(self):
        fd, ctx = self._import_modules()
        ctx.session_fronts = ['session_front']
        self.assertEqual(fd.session_fronts, ['session_front'])
        ctx.session_fronts = []

    def test_module_getattr_proxies_cloudflare_front(self):
        fd, ctx = self._import_modules()
        self.assertIsNone(fd.cloudflare_front)

    def test_module_getattr_raises_on_unknown(self):
        fd, ctx = self._import_modules()
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
        from x_tunnel.local.context import ctx
        return xt_local, ctx

    def test_is_ready_false_initially(self):
        xt_local, ctx = self._import_modules()
        ctx.ready = False
        self.assertFalse(xt_local.is_ready())

    def test_is_ready_true_when_ctx_ready(self):
        xt_local, ctx = self._import_modules()
        ctx.ready = True
        self.assertTrue(xt_local.is_ready())
        ctx.ready = False


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
        from x_tunnel.local.context import ctx
        return front_dispatcher, ctx

    def test_init_sets_front_initialized(self):
        fd, ctx = self._import_modules()
        ctx._front_initialized = False
        ctx.all_fronts = []
        ctx.session_fronts = []
        ctx.light_fronts = []
        ctx._front_fail_counts = {}
        ctx._front_last_fail_time = {}

        class FakeConfig:
            enable_cloudflare = False
            enable_cloudfront = False
            enable_seley = False
            enable_tls_relay = False
            enable_direct = False
            show_state_debug = False
        ctx.config = FakeConfig()

        fd.init()
        self.assertTrue(ctx._front_initialized)

        fd.stop()
        self.assertFalse(ctx._front_initialized)
        self.assertEqual(ctx.all_fronts, [])
        self.assertEqual(ctx.session_fronts, [])
        self.assertEqual(ctx.light_fronts, [])

    def test_init_idempotent_via_ctx(self):
        fd, ctx = self._import_modules()
        ctx._front_initialized = False
        ctx.all_fronts = []
        ctx.session_fronts = []
        ctx.light_fronts = []
        ctx._front_fail_counts = {}
        ctx._front_last_fail_time = {}

        class FakeConfig:
            enable_cloudflare = False
            enable_cloudfront = False
            enable_seley = False
            enable_tls_relay = False
            enable_direct = False
            show_state_debug = False
        ctx.config = FakeConfig()

        fd.init()
        call_count = [0]
        orig_init = ctx._front_initialized
        fd.init()
        self.assertTrue(ctx._front_initialized)

        fd.stop()

    def test_stop_resets_fail_counts(self):
        fd, ctx = self._import_modules()
        ctx._front_initialized = False
        ctx._statistic_running = False
        ctx.all_fronts = []
        ctx._front_fail_counts = {"test": 5}
        ctx._front_last_fail_time = {"test": 100.0}
        ctx.statistic_thread = None

        fd.stop()
        self.assertEqual(ctx._front_fail_counts, {})
        self.assertEqual(ctx._front_last_fail_time, {})

    def test_record_fail_increments_via_ctx(self):
        fd, ctx = self._import_modules()
        ctx._front_fail_counts = {}
        ctx._front_last_fail_time = {}

        class FakeFront:
            name = "test_front"
        fd._record_front_fail(FakeFront())
        self.assertEqual(ctx._front_fail_counts["test_front"], 1)
        self.assertIn("test_front", ctx._front_last_fail_time)
        ctx._front_fail_counts = {}
        ctx._front_last_fail_time = {}


class TestCenterLoginProcessFlow(TestCase):
    """Phase 3.4: Verify center_login_process works correctly via ctx."""

    def test_center_login_process_via_ctx(self):
        code_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        if code_root not in sys.path:
            sys.path.insert(0, code_root)
        lib_path = os.path.join(code_root, 'lib', 'noarch')
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)
        from x_tunnel.local.context import ctx

        ctx.center_login_process = False
        self.assertFalse(ctx.center_login_process)
        ctx.center_login_process = True
        self.assertTrue(ctx.center_login_process)
        ctx.center_login_process = False
