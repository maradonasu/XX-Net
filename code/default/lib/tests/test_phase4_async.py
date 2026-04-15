#!/usr/bin/env python3
# coding:utf-8

import sys
import os
import asyncio
import threading
import time

noarch_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'noarch'))
if noarch_lib not in sys.path:
    sys.path.insert(0, noarch_lib)

from unittest import TestCase


class TestAsyncLoop(TestCase):
    def test_get_loop(self):
        import async_loop
        loop = async_loop.get_loop()
        self.assertIsNotNone(loop)
        self.assertFalse(loop.is_closed())

    def test_run_async(self):
        import async_loop

        async def simple_coro():
            return 42

        result = async_loop.run_async(simple_coro())
        self.assertEqual(result, 42)

    def test_run_async_with_exception(self):
        import async_loop

        async def failing_coro():
            raise ValueError("test error")

        with self.assertRaises(ValueError):
            async_loop.run_async(failing_coro())

    def test_create_task(self):
        import async_loop

        results = []

        async def background_work():
            await asyncio.sleep(0.05)
            results.append("done")

        async_loop.create_task(background_work())
        time.sleep(0.2)
        self.assertIn("done", results)

    def test_run_sync_in_async(self):
        import async_loop

        def blocking_func(x):
            return x * 2

        async def test_it():
            return await async_loop.run_sync(blocking_func, 21)

        result = async_loop.run_async(test_it())
        self.assertEqual(result, 42)


class TestAsyncLoopInfrastructure(TestCase):
    def test_loop_thread_is_daemon(self):
        import async_loop
        async_loop.start()
        self.assertTrue(async_loop._thread.daemon)

    def test_multiple_start_calls_safe(self):
        import async_loop
        async_loop.start()
        async_loop.start()
        async_loop.start()
        loop1 = async_loop.get_loop()
        loop2 = async_loop.get_loop()
        self.assertEqual(loop1, loop2)


class TestAsyncHttpServer(TestCase):
    def test_import_works(self):
        from async_http_server import AsyncHTTPServer
        self.assertTrue(AsyncHTTPServer is not None)

    def test_server_init(self):
        from async_http_server import AsyncHTTPServer

        def handler(req, resp):
            resp.set_body(b"OK")

        server = AsyncHTTPServer(('127.0.0.1', 0), handler)
        self.assertFalse(server.running)
        self.assertEqual(len(server.addresses), 1)

    def test_server_init_multiple_addresses(self):
        from async_http_server import AsyncHTTPServer

        def handler(req, resp):
            pass

        addrs = [('127.0.0.1', 8080), ('127.0.0.1', 8081)]
        server = AsyncHTTPServer(addrs, handler)
        self.assertEqual(len(server.addresses), 2)


class TestAsyncHttpClient(TestCase):
    def test_import_works(self):
        from async_http_client import AsyncHttpClient
        self.assertTrue(AsyncHttpClient is not None)

    def test_client_init(self):
        from async_http_client import AsyncHttpClient
        client = AsyncHttpClient(timeout=10, proxy="socks5://127.0.0.1:1080")
        self.assertEqual(client.timeout, 10)
        self.assertEqual(client.proxy, "socks5://127.0.0.1:1080")


class TestAsyncSocks5(TestCase):
    def test_import_works(self):
        from async_socks5 import AsyncSocks5Server, AsyncSocks5Handler
        self.assertTrue(AsyncSocks5Server is not None)
        self.assertTrue(AsyncSocks5Handler is not None)

    def test_server_init(self):
        from async_socks5 import AsyncSocks5Server
        server = AsyncSocks5Server(host="127.0.0.1", port=1080)
        self.assertEqual(server.host, "127.0.0.1")
        self.assertEqual(server.port, 1080)
        self.assertFalse(server.running)


class TestAsyncSSLWrap(TestCase):
    def test_import_works(self):
        from async_ssl_wrap import AsyncSSLConnection, async_connect_ssl
        self.assertTrue(AsyncSSLConnection is not None)
        self.assertTrue(async_connect_ssl is not None)

    def test_connection_init(self):
        from async_ssl_wrap import AsyncSSLConnection
        conn = AsyncSSLConnection("example.com", 443)
        self.assertEqual(conn.host, "example.com")
        self.assertEqual(conn.port, 443)
        self.assertFalse(conn.connected)
        self.assertIsNone(conn._reader)
        self.assertIsNone(conn._writer)


class TestAsyncConnectCreator(TestCase):
    def test_import_works(self):
        from front_base.async_connect_creator import AsyncConnectCreator
        self.assertTrue(AsyncConnectCreator is not None)

    def test_creator_init(self):
        from front_base.async_connect_creator import AsyncConnectCreator
        import unittest.mock as mock

        mock_logger = mock.MagicMock()
        mock_config = mock.MagicMock()
        creator = AsyncConnectCreator(mock_logger, mock_config, timeout=10)
        self.assertEqual(creator.timeout, 10)
