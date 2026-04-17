#!/usr/bin/env python3
# coding:utf-8

import os
import sys
import unittest
import asyncio
from unittest import TestCase

code_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if code_root not in sys.path:
    sys.path.insert(0, code_root)
lib_path = os.path.join(code_root, 'lib', 'noarch')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

import async_loop


class TestAsyncProxySession(TestCase):
    def test_import(self):
        from x_tunnel.local.async_proxy_session import AsyncProxySession
        self.assertTrue(True)
    
    def test_session_init(self):
        from x_tunnel.local.async_proxy_session import AsyncProxySession
        
        async def do_test():
            session = AsyncProxySession()
            self.assertFalse(session.running)
            self.assertEqual(len(session.conn_list), 0)
        
        async_loop.run_async(do_test(), timeout=5)
    
    def test_session_status(self):
        from x_tunnel.local.async_proxy_session import AsyncProxySession
        
        async def do_test():
            session = AsyncProxySession()
            status = session.status()
            self.assertIn("AsyncProxySession", status)
            self.assertIn("running: False", status)
        
        async_loop.run_async(do_test(), timeout=5)
    
    def test_traffic_readable(self):
        from x_tunnel.local.async_proxy_session import traffic_readable
        
        self.assertEqual(traffic_readable(0), "0.0 B")
        self.assertEqual(traffic_readable(1024), "1.0 KB")
        self.assertEqual(traffic_readable(1048576), "1.0 MB")
    
    def test_get_login_extra_info(self):
        from x_tunnel.local.async_proxy_session import AsyncProxySession
        
        info = AsyncProxySession.get_login_extra_info()
        self.assertIsInstance(info, str)
        data = __import__('json').loads(info)
        self.assertIn("version", data)
        self.assertIn("system", data)
        self.assertIn("device", data)


class TestAsyncProxySessionLifecycle(TestCase):
    def test_start_stop_without_server(self):
        from x_tunnel.local.async_proxy_session import AsyncProxySession
        
        async def do_test():
            session = AsyncProxySession()
            result = await session.start()
            self.assertFalse(result)
            self.assertFalse(session.running)
            await session.stop()
        
        async_loop.run_async(do_test(), timeout=10)
    
    def test_stop_when_not_running(self):
        from x_tunnel.local.async_proxy_session import AsyncProxySession
        
        async def do_test():
            session = AsyncProxySession()
            await session.stop()
            self.assertFalse(session.running)
        
        async_loop.run_async(do_test(), timeout=5)


class TestAsyncProxySessionConnections(TestCase):
    def test_create_conn_id_increment(self):
        from x_tunnel.local.async_proxy_session import AsyncProxySession
        
        async def do_test():
            session = AsyncProxySession()
            session.running = True
            conn_id = await session.create_conn(None, "test", 80)
            self.assertEqual(session.last_conn_id, 2)
        
        async_loop.run_async(do_test(), timeout=5)
    
    def test_remove_conn(self):
        from x_tunnel.local.async_proxy_session import AsyncProxySession
        
        async def do_test():
            session = AsyncProxySession()
            await session.remove_conn_async(1)
            self.assertEqual(len(session.conn_list), 0)
        
        async_loop.run_async(do_test(), timeout=5)


class TestLoginProcess(TestCase):
    def test_login_process_import(self):
        from x_tunnel.local.async_proxy_session import async_login_process, async_create_conn
        self.assertTrue(True)