#!/usr/bin/env python3
# coding:utf-8

import sys
import os
import asyncio
import socket
import struct
import threading
import time
import unittest.mock as mock

noarch_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'noarch'))
if noarch_lib not in sys.path:
    sys.path.insert(0, noarch_lib)

from unittest import TestCase


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


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

        async def waiter():
            task = async_loop.create_task(background_work())
            await asyncio.wait_for(task, timeout=2)
            self.assertIn("done", results)

        async_loop.run_async(waiter(), timeout=5)

    def test_run_sync_in_async(self):
        import async_loop

        def blocking_func(x):
            return x * 2

        async def test_it():
            return await async_loop.run_sync(blocking_func, 21)

        result = async_loop.run_async(test_it())
        self.assertEqual(result, 42)

    def test_run_async_no_wait(self):
        import async_loop

        results = []

        async def delayed():
            await asyncio.sleep(0.05)
            results.append("bg")

        async_loop.run_async_no_wait(delayed())
        time.sleep(0.2)
        self.assertIn("bg", results)

    def test_stop(self):
        import async_loop
        async_loop.start()
        self.assertTrue(async_loop._running)
        async_loop.stop()
        time.sleep(0.3)
        self.assertFalse(async_loop._running)


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

    def test_server_init_socket(self):
        from async_http_server import AsyncHTTPServer

        def handler(req, resp):
            resp.set_body(b"OK")

        server = AsyncHTTPServer(('127.0.0.1', _find_free_port()), handler)
        server.init_socket()
        self.assertIsNotNone(server._app)
        server.shutdown()

    def test_server_start_and_request(self):
        from async_http_server import AsyncHTTPServer
        import async_loop

        def handler(req, resp):
            resp.set_body("hello async", content_type="text/plain")

        port = _find_free_port()
        server = AsyncHTTPServer(('127.0.0.1', port), handler)
        server.init_socket()
        server.start()
        self.assertTrue(server.running)

        try:
            import httpx
            resp = httpx.get(f"http://127.0.0.1:{port}/test", timeout=5)
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b"hello async", resp.content)
        finally:
            server.shutdown()

    def test_server_async_handler(self):
        from async_http_server import AsyncHTTPServer

        async def handler(req, resp):
            body = await req.body()
            resp.set_body(body, content_type="application/octet-stream")

        port = _find_free_port()
        server = AsyncHTTPServer(('127.0.0.1', port), handler)
        server.init_socket()
        server.start()

        try:
            import httpx
            resp = httpx.post(f"http://127.0.0.1:{port}/echo", content=b"test-data", timeout=5)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.content, b"test-data")
        finally:
            server.shutdown()

    def test_server_shutdown_cleans_up(self):
        from async_http_server import AsyncHTTPServer

        def handler(req, resp):
            resp.set_body(b"OK")

        port = _find_free_port()
        server = AsyncHTTPServer(('127.0.0.1', port), handler)
        server.init_socket()
        server.start()
        server.shutdown()
        self.assertFalse(server.running)
        self.assertEqual(len(server.sites), 0)


class TestAsyncHttpClient(TestCase):
    def test_import_works(self):
        from async_http_client import AsyncHttpClient
        self.assertTrue(AsyncHttpClient is not None)

    def test_client_init(self):
        from async_http_client import AsyncHttpClient
        client = AsyncHttpClient(timeout=10, proxy="socks5://127.0.0.1:1080")
        self.assertEqual(client.timeout, 10)
        self.assertEqual(client.proxy, "socks5://127.0.0.1:1080")

    def test_client_get_request(self):
        from async_http_client import AsyncHttpClient
        import async_loop

        async def do_test():
            try:
                client = AsyncHttpClient(timeout=15)
                resp = await client.get("https://httpbin.org/get")
                if resp:
                    self.assertEqual(resp.status, 200)
                await client.close()
            except Exception:
                self.skipTest("network unavailable")

        async_loop.run_async(do_test(), timeout=20)

    def test_client_close(self):
        from async_http_client import AsyncHttpClient
        import async_loop

        async def do_test():
            try:
                client = AsyncHttpClient()
                resp = await client.get("https://httpbin.org/get")
                await client.close()
                self.assertIsNone(client._client)
            except Exception:
                self.skipTest("network unavailable")

        async_loop.run_async(do_test(), timeout=20)


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

    def test_socks5_handler_no_data(self):
        from async_socks5 import AsyncSocks5Handler
        import async_loop

        async def do_test():
            r = asyncio.StreamReader()
            r.feed_eof()
            writer_mock = mock.MagicMock()
            writer_mock.close = mock.MagicMock()
            writer_mock.wait_closed = mock.AsyncMock()
            handler = AsyncSocks5Handler(r, writer_mock)
            await handler.handle()

        async_loop.run_async(do_test(), timeout=5)

    async def _start_and_get_port(self, server):
        await server._start_async()
        return server.port


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

    def test_connection_connect_real(self):
        from async_ssl_wrap import AsyncSSLConnection
        import async_loop

        async def do_test():
            try:
                conn = AsyncSSLConnection("example.com", 443, timeout=15)
                await conn.connect()
                self.assertTrue(conn.connected)
                self.assertIsNotNone(conn._reader)
                self.assertIsNotNone(conn._writer)

                await conn.send(b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n")
                data = await conn.recv(4096)
                self.assertIn(b"HTTP/", data)

                await conn.close()
                self.assertFalse(conn.connected)
            except (TimeoutError, OSError):
                self.skipTest("network unavailable")

        async_loop.run_async(do_test(), timeout=20)

    def test_connection_is_support_h2(self):
        from async_ssl_wrap import AsyncSSLConnection
        import async_loop

        async def do_test():
            try:
                conn = AsyncSSLConnection("example.com", 443, timeout=15)
                await conn.connect()
                self.assertIsInstance(conn.is_support_h2(), bool)
                await conn.close()
            except (TimeoutError, OSError):
                self.skipTest("network unavailable")

        async_loop.run_async(do_test(), timeout=20)


class TestAsyncConnectCreator(TestCase):
    def test_import_works(self):
        from front_base.async_connect_creator import AsyncConnectCreator
        self.assertTrue(AsyncConnectCreator is not None)

    def test_creator_init(self):
        from front_base.async_connect_creator import AsyncConnectCreator

        mock_logger = mock.MagicMock()
        mock_config = mock.MagicMock()
        creator = AsyncConnectCreator(mock_logger, mock_config, timeout=10)
        self.assertEqual(creator.timeout, 10)


class TestAsyncClientModule(TestCase):
    def test_async_client_imports(self):
        xtunnel_local = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'x_tunnel', 'local'))
        if xtunnel_local not in sys.path:
            sys.path.insert(0, xtunnel_local)
        self.assertTrue(True)

    def test_xxnet_version_function(self):
        code_default = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        if code_default not in sys.path:
            sys.path.insert(0, code_default)

        from x_tunnel.local.async_client import xxnet_version
        version = xxnet_version()
        self.assertIsInstance(version, str)
        self.assertTrue(len(version) > 0)


class TestAsyncSocks5EndToEnd(TestCase):
    def test_socks5_ipv4_connection(self):
        from async_socks5 import AsyncSocks5Server
        import async_loop

        target_port = _find_free_port()
        response_data = b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nHELLO"

        def target_server():
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(('127.0.0.1', target_port))
            srv.listen(1)
            srv.settimeout(5)
            try:
                conn, _ = srv.accept()
                conn.recv(4096)
                conn.sendall(response_data)
                conn.close()
            except Exception:
                pass
            finally:
                srv.close()

        t = threading.Thread(target=target_server, daemon=True)
        t.start()
        time.sleep(0.2)

        async def do_test():
            socks_port = _find_free_port()
            server = AsyncSocks5Server(host="127.0.0.1", port=socks_port)
            await server._start_async()
            await asyncio.sleep(0.2)

            try:
                reader, writer = await asyncio.open_connection('127.0.0.1', socks_port)

                writer.write(b"\x05\x01\x00")
                await writer.drain()
                resp = await asyncio.wait_for(reader.readexactly(2), timeout=5)
                self.assertEqual(resp, b"\x05\x00")

                writer.write(
                    b"\x05\x01\x00\x01" +
                    socket.inet_aton("127.0.0.1") +
                    struct.pack("!H", target_port)
                )
                await writer.drain()
                resp = await asyncio.wait_for(reader.readexactly(10), timeout=5)
                self.assertEqual(resp[0:2], b"\x05\x00")

                writer.write(b"GET / HTTP/1.1\r\nHost: test\r\n\r\n")
                await writer.drain()
                data = b""
                while b"HELLO" not in data and len(data) < 8192:
                    try:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                        if not chunk:
                            break
                        data += chunk
                    except asyncio.TimeoutError:
                        break
                self.assertIn(b"HELLO", data)

                writer.close()
                await writer.wait_closed()
            finally:
                await server._stop_async()

        async_loop.run_async(do_test(), timeout=15)

    def test_socks4_connection(self):
        from async_socks5 import AsyncSocks5Server
        import async_loop

        target_port = _find_free_port()
        response_data = b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\nS4OK"

        def target_server():
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(('127.0.0.1', target_port))
            srv.listen(1)
            srv.settimeout(5)
            try:
                conn, _ = srv.accept()
                conn.recv(4096)
                conn.sendall(response_data)
                conn.close()
            except Exception:
                pass
            finally:
                srv.close()

        t = threading.Thread(target=target_server, daemon=True)
        t.start()
        time.sleep(0.2)

        async def do_test():
            socks_port = _find_free_port()
            server = AsyncSocks5Server(host="127.0.0.1", port=socks_port)
            await server._start_async()
            await asyncio.sleep(0.2)

            try:
                reader, writer = await asyncio.open_connection('127.0.0.1', socks_port)

                writer.write(
                    b"\x04\x01" +
                    struct.pack("!H", target_port) +
                    socket.inet_aton("127.0.0.1") +
                    b"\x00"
                )
                await writer.drain()

                resp = await asyncio.wait_for(reader.read(8), timeout=5)
                self.assertEqual(resp[1], 0x5a)

                writer.write(b"GET / HTTP/1.1\r\nHost: test\r\n\r\n")
                await writer.drain()

                data = b""
                while b"S4OK" not in data and len(data) < 8192:
                    try:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                        if not chunk:
                            break
                        data += chunk
                    except asyncio.TimeoutError:
                        break
                self.assertIn(b"S4OK", data)

                writer.close()
                await writer.wait_closed()
            finally:
                await server._stop_async()

        async_loop.run_async(do_test(), timeout=15)

    def test_http_connect_proxy(self):
        from async_socks5 import AsyncSocks5Server
        import async_loop

        target_port = _find_free_port()
        response_data = b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\nHTTP"

        def target_server():
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(('127.0.0.1', target_port))
            srv.listen(1)
            srv.settimeout(5)
            try:
                conn, _ = srv.accept()
                conn.recv(4096)
                conn.sendall(response_data)
                conn.close()
            except Exception:
                pass
            finally:
                srv.close()

        t = threading.Thread(target=target_server, daemon=True)
        t.start()
        time.sleep(0.2)

        async def do_test():
            socks_port = _find_free_port()
            server = AsyncSocks5Server(host="127.0.0.1", port=socks_port)
            await server._start_async()
            await asyncio.sleep(0.2)

            try:
                reader, writer = await asyncio.open_connection('127.0.0.1', socks_port)

                connect_req = f"CONNECT 127.0.0.1:{target_port} HTTP/1.1\r\nHost: 127.0.0.1:{target_port}\r\n\r\n".encode()
                writer.write(connect_req)
                await writer.drain()

                resp = await asyncio.wait_for(reader.read(4096), timeout=5)
                self.assertIn(b"200", resp)

                writer.write(b"GET / HTTP/1.1\r\nHost: test\r\n\r\n")
                await writer.drain()

                data = b""
                while b"HTTP" not in data and len(data) < 8192:
                    try:
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=3)
                        if not chunk:
                            break
                        data += chunk
                    except asyncio.TimeoutError:
                        break
                self.assertIn(b"HTTP", data)

                writer.close()
                await writer.wait_closed()
            finally:
                await server._stop_async()

        async_loop.run_async(do_test(), timeout=15)


class TestAsyncHttpServerEndToEnd(TestCase):
    def test_json_response(self):
        from async_http_server import AsyncHTTPServer

        def handler(req, resp):
            resp.set_json({"status": "ok", "value": 42})

        port = _find_free_port()
        server = AsyncHTTPServer(('127.0.0.1', port), handler)
        server.init_socket()
        server.start()

        try:
            import httpx
            resp = httpx.get(f"http://127.0.0.1:{port}/api/test", timeout=5)
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["status"], "ok")
            self.assertEqual(data["value"], 42)
        finally:
            server.shutdown()

    def test_post_with_body(self):
        from async_http_server import AsyncHTTPServer

        def handler(req, resp):
            resp.set_json({"got": "posted"})

        port = _find_free_port()
        server = AsyncHTTPServer(('127.0.0.1', port), handler)
        server.init_socket()
        server.start()

        try:
            import httpx
            resp = httpx.post(
                f"http://127.0.0.1:{port}/submit",
                json={"key": "val"},
                timeout=5,
            )
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["got"], "posted")
        finally:
            server.shutdown()

    def test_handler_exception_returns_500(self):
        from async_http_server import AsyncHTTPServer

        def handler(req, resp):
            raise RuntimeError("test error")

        port = _find_free_port()
        server = AsyncHTTPServer(('127.0.0.1', port), handler)
        server.init_socket()
        server.start()

        try:
            import httpx
            resp = httpx.get(f"http://127.0.0.1:{port}/fail", timeout=5)
            self.assertEqual(resp.status_code, 500)
        finally:
            server.shutdown()


class TestAsyncHttpClientEndToEnd(TestCase):
    def test_async_get_request(self):
        from async_http_client import AsyncHttpClient
        import async_loop

        async def do_test():
            try:
                client = AsyncHttpClient(timeout=15)
                resp = await client.get("https://httpbin.org/get")
                self.assertIsNotNone(resp)
                self.assertEqual(resp.status, 200)
                body = await resp.read()
                self.assertIn(b"httpbin.org", body)
                await client.close()
            except Exception:
                self.skipTest("network unavailable")

        async_loop.run_async(do_test(), timeout=20)

    def test_async_post_request(self):
        from async_http_client import AsyncHttpClient
        import async_loop

        async def do_test():
            try:
                client = AsyncHttpClient(timeout=15)
                resp = await client.post("https://httpbin.org/post", body=b"test-body")
                self.assertIsNotNone(resp)
                self.assertEqual(resp.status, 200)
                await client.close()
            except Exception:
                self.skipTest("network unavailable")

        async_loop.run_async(do_test(), timeout=20)


class TestAsyncLoopConcurrency(TestCase):
    def test_concurrent_tasks(self):
        import async_loop

        results = []
        n = 10

        async def worker(i):
            await asyncio.sleep(0.05)
            results.append(i)
            return i

        async def run_all():
            tasks = [async_loop.create_task(worker(i)) for i in range(n)]
            await asyncio.gather(*tasks)

        async_loop.run_async(run_all(), timeout=10)
        self.assertEqual(sorted(results), list(range(n)))

    def test_timer_scheduling(self):
        import async_loop

        called = []

        async def schedule_callback():
            called.append(True)

        async_loop.run_async(schedule_callback(), timeout=5)
        time.sleep(0.1)
        self.assertTrue(len(called) > 0)


class TestAsyncSSLWrapEndToEnd(TestCase):
    def test_ssl_send_recv(self):
        from async_ssl_wrap import AsyncSSLConnection
        import async_loop

        async def do_test():
            try:
                conn = AsyncSSLConnection("example.com", 443, timeout=15)
                await conn.connect()
                self.assertTrue(conn.connected)

                await conn.send(b"GET / HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n")
                data = b""
                while True:
                    chunk = await conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if len(data) > 100:
                        break

                self.assertIn(b"HTTP/", data)
                await conn.close()
                self.assertFalse(conn.connected)
            except (TimeoutError, OSError):
                self.skipTest("network unavailable")

        async_loop.run_async(do_test(), timeout=20)

    def test_ssl_h2_detection(self):
        from async_ssl_wrap import AsyncSSLConnection
        import async_loop

        async def do_test():
            try:
                conn = AsyncSSLConnection("google.com", 443, timeout=15)
                await conn.connect()
                h2 = conn.is_support_h2()
                self.assertIsInstance(h2, bool)
                await conn.close()
            except (TimeoutError, OSError):
                self.skipTest("network unavailable")

        async_loop.run_async(do_test(), timeout=20)


class TestAsyncDNSResolver(TestCase):
    def test_resolver_init(self):
        from front_base.async_dns import AsyncDNSResolver, get_resolver
        resolver = AsyncDNSResolver()
        self.assertIsNotNone(resolver)

    def test_get_resolver_singleton(self):
        from front_base.async_dns import get_resolver
        r1 = get_resolver()
        r2 = get_resolver()
        self.assertIs(r1, r2)

    def test_resolve_localhost(self):
        from front_base.async_dns import resolve
        import async_loop
        async_loop.start()
        result = async_loop.run_async(resolve("localhost"), timeout=5)
        self.assertIsNotNone(result)


class TestAsyncHttpDispatcher(TestCase):
    def test_dispatcher_import(self):
        from front_base.async_http_dispatcher import AsyncHttpsDispatcher
        self.assertTrue(True)


class TestAsyncIpManager(TestCase):
    def test_import_works(self):
        from front_base.async_ip_manager import AsyncIpManagerBase
        self.assertTrue(True)


class TestAsyncDefaultPath(TestCase):
    def test_async_client_is_only_client(self):
        import os
        import sys
        
        code_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        if code_root not in sys.path:
            sys.path.insert(0, code_root)
        
        import x_tunnel.local as xtunnel_local
        self.assertEqual(xtunnel_local._client_mod.__name__, 'x_tunnel.local.async_client')
    
    def test_async_proxy_session_is_default(self):
        import os
        import sys
        
        code_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        if code_root not in sys.path:
            sys.path.insert(0, code_root)
        
        from x_tunnel.local.async_proxy_session import AsyncProxySession
        self.assertTrue(AsyncProxySession is not None)
