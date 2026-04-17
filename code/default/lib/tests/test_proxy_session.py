#!/usr/bin/env python3
# coding:utf-8

import asyncio
import importlib
import sys
import os
import unittest.mock as mock

noarch_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'noarch'))
if noarch_lib not in sys.path:
    sys.path.append(noarch_lib)

code_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if code_dir not in sys.path:
    sys.path.append(code_dir)

from unittest import TestCase


class TestAsyncProxySessionHelpers(TestCase):
    def test_traffic_readable(self):
        from x_tunnel.local.async_proxy_session import traffic_readable
        
        self.assertEqual(traffic_readable(0), '0.0 B')
        self.assertEqual(traffic_readable(512), '512.0 B')
        self.assertEqual(traffic_readable(1024), '1.0 KB')
        self.assertEqual(traffic_readable(1024 * 1024), '1.0 MB')
        self.assertEqual(traffic_readable(1024 * 1024 * 1024), '1.0 GB')

    def test_traffic_readable_custom_units(self):
        from x_tunnel.local.async_proxy_session import traffic_readable
        
        custom_units = ('bytes', 'KB', 'MB', 'GB')
        self.assertEqual(traffic_readable(1024, custom_units), '1.0 KB')


class TestApiClientHelpers(TestCase):
    def test_get_app_name(self):
        from x_tunnel.local.api_client import get_app_name
        
        app_name = get_app_name()
        self.assertIsInstance(app_name, str)
        self.assertEqual(app_name, "XX-Net")

    def test_encrypt_decrypt_data(self):
        from x_tunnel.local.api_client import encrypt_data, decrypt_data
        from x_tunnel.local.context import ctx
        
        ctx.config = None
        original = b"test data"
        encrypted = encrypt_data(original)
        decrypted = decrypt_data(encrypted)
        self.assertEqual(decrypted, original)


class TestXTunnelLocalImports(TestCase):
    def tearDown(self):
        for name in list(sys.modules.keys()):
            if name == 'x_tunnel.local' or name.startswith('x_tunnel.local.'):
                sys.modules.pop(name, None)

    def test_package_import_does_not_import_web_control(self):
        import x_tunnel.local as xtunnel_local

        self.assertEqual(xtunnel_local._client_mod.__name__, 'x_tunnel.local.async_client')
        self.assertNotIn('x_tunnel.local.web_control', sys.modules)


class TestWebControlSessionDispatch(TestCase):
    def setUp(self):
        from x_tunnel.local.context import ctx
        self.ctx = ctx
        self.old_session = getattr(ctx, 'session', None)
        self.old_config = getattr(ctx, 'config', None)
        self.old_server_host = getattr(ctx, 'server_host', None)
        self.old_server_port = getattr(ctx, 'server_port', None)
        self.old_selectable = getattr(ctx, 'selectable', None)
        self.old_promoter = getattr(ctx, 'promoter', None)

    def tearDown(self):
        self.ctx.session = self.old_session
        self.ctx.config = self.old_config
        self.ctx.server_host = self.old_server_host
        self.ctx.server_port = self.old_server_port
        self.ctx.selectable = self.old_selectable
        self.ctx.promoter = self.old_promoter

    def test_run_session_action_awaits_async_session(self):
        from x_tunnel.local import web_control

        async def async_reset():
            return "ok"

        session = mock.Mock()
        session.reset = mock.Mock(side_effect=async_reset)

        with mock.patch('x_tunnel.local.web_control.async_loop.run_async', return_value="ok") as run_async:
            result = web_control.run_session_action(session, 'reset')

        self.assertEqual(result, "ok")
        run_async.assert_called_once()
        coro = run_async.call_args.args[0]
        self.assertTrue(asyncio.iscoroutine(coro))
        coro.close()

    def test_run_session_action_calls_sync_session_directly(self):
        from x_tunnel.local import web_control

        session = mock.Mock()
        session.stop = mock.Mock(return_value="stopped")

        with mock.patch('x_tunnel.local.web_control.async_loop.run_async') as run_async:
            result = web_control.run_session_action(session, 'stop')

        self.assertEqual(result, "stopped")
        run_async.assert_not_called()

    def test_token_login_uses_config_api_server(self):
        from x_tunnel.local import web_control

        self.ctx.config = mock.Mock()
        self.ctx.config.api_server = "center.xx-net.org"
        self.ctx.config.update_cloudflare_domains = False
        self.ctx.config.save = mock.Mock()
        self.ctx.server_host = ""
        self.ctx.server_port = 0
        self.ctx.selectable = []
        self.ctx.promoter = ""
        self.ctx.session = mock.Mock()
        self.ctx.session.start = mock.Mock(return_value="started")

        handler = object.__new__(web_control.ControlHandler)
        handler.postvars = {'login_token': 'eyJsb2dpbl9hY2NvdW50IjogInUxQGV4YW1wbGUuY29tIiwgImxvZ2luX3Bhc3N3b3JkIjogIjAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWYiLCAidGxzX3JlbGF5IjogeyJpcHMiOiBbXX19'}
        handler.response_json = mock.Mock(side_effect=lambda data: data)

        with mock.patch('x_tunnel.local.web_control.api_client.request_balance', return_value=(False, 'bad token')):
            result = handler.req_token_login_handler()

        self.assertEqual(self.ctx.config.api_server, "center.xx-net.org")
        self.assertEqual(result["res"], "fail")
