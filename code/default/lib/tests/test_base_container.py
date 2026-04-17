#!/usr/bin/env python3
# coding:utf-8

import asyncio
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
import x_tunnel.local.async_base_container as bc

class TestWriteBuffer(TestCase):
    def test_init_with_bytes(self):
        wb = bc.WriteBuffer(b"test")
        self.assertEqual(len(wb), 4)
        self.assertEqual(wb.to_bytes(), b"test")

    def test_init_with_none(self):
        wb = bc.WriteBuffer()
        self.assertEqual(len(wb), 0)
        self.assertEqual(wb.to_bytes(), b"")

    def test_append_bytes(self):
        wb = bc.WriteBuffer(b"hello")
        wb.append(b" world")
        self.assertEqual(len(wb), 11)
        self.assertEqual(wb.to_bytes(), b"hello world")

    def test_append_write_buffer(self):
        wb1 = bc.WriteBuffer(b"hello")
        wb2 = bc.WriteBuffer(b" world")
        wb1.append(wb2)
        self.assertEqual(len(wb1), 11)
        self.assertEqual(wb1.to_bytes(), b"hello world")

    def test_insert_bytes(self):
        wb = bc.WriteBuffer(b"world")
        wb.insert(b"hello ")
        self.assertEqual(len(wb), 11)
        self.assertEqual(wb.to_bytes(), b"hello world")

    def test_insert_write_buffer(self):
        wb1 = bc.WriteBuffer(b"world")
        wb2 = bc.WriteBuffer(b"hello ")
        wb1.insert(wb2)
        self.assertEqual(len(wb1), 11)
        self.assertEqual(wb1.to_bytes(), b"hello world")

    def test_reset(self):
        wb = bc.WriteBuffer(b"test")
        wb.reset()
        self.assertEqual(len(wb), 0)
        self.assertEqual(wb.to_bytes(), b"")

    def test_bytes_conversion(self):
        wb = bc.WriteBuffer(b"test")
        self.assertEqual(bytes(wb), b"test")

    def test_str_conversion(self):
        wb = bc.WriteBuffer(b"test")
        self.assertEqual(str(wb), "test")

    def test_add_operator(self):
        wb = bc.WriteBuffer(b"hello")
        wb + b" world"
        self.assertEqual(len(wb), 11)

class TestReadBuffer(TestCase):
    def test_init_basic(self):
        rb = bc.ReadBuffer(b"test data")
        self.assertEqual(len(rb), 9)

    def test_init_with_begin(self):
        rb = bc.ReadBuffer(b"test data", begin=5)
        self.assertEqual(len(rb), 4)

    def test_init_with_begin_and_size(self):
        rb = bc.ReadBuffer(b"test data", begin=0, size=4)
        self.assertEqual(len(rb), 4)

    def test_get_all(self):
        rb = bc.ReadBuffer(b"test")
        data = rb.get()
        self.assertEqual(bytes(data), b"test")
        self.assertEqual(len(rb), 0)

    def test_get_partial(self):
        rb = bc.ReadBuffer(b"test data")
        data = rb.get(4)
        self.assertEqual(bytes(data), b"test")
        self.assertEqual(len(rb), 5)

    def test_get_multiple(self):
        rb = bc.ReadBuffer(b"test data")
        first = rb.get(4)
        second = rb.get(5)
        self.assertEqual(bytes(first), b"test")
        self.assertEqual(bytes(second), b" data")
        self.assertEqual(len(rb), 0)

    def test_get_buf(self):
        rb = bc.ReadBuffer(b"test data")
        buf = rb.get_buf(4)
        self.assertEqual(len(buf), 4)
        self.assertEqual(len(rb), 5)

    def test_bytes_conversion(self):
        rb = bc.ReadBuffer(b"test")
        self.assertEqual(bytes(rb), b"test")

    def test_str_conversion(self):
        rb = bc.ReadBuffer(b"test")
        self.assertEqual(str(rb), "test")


class TestAsyncReceiveProcess(TestCase):
    def test_out_of_order_packets_are_delivered_in_sequence(self):
        received = []

        async def handler(data):
            received.append(data)

        async def scenario():
            from x_tunnel.local.async_proxy_session import AsyncReceiveProcess

            proc = AsyncReceiveProcess(handler, mock.Mock())
            await proc.put(2, b"two")
            self.assertEqual(received, [])
            await proc.put(1, b"one")
            self.assertEqual(received, [b"one", b"two"])

        asyncio.run(scenario())


class TestAsyncConn(TestCase):
    def test_do_connect_uses_async_resolution_and_connect(self):
        class FakeSocket:
            def __init__(self):
                self.options = []
                self.blocking = True

            def setsockopt(self, *args):
                self.options.append(args)

            def setblocking(self, value):
                self.blocking = value

        class FakeLoop:
            def __init__(self):
                self.calls = []

            async def getaddrinfo(self, host, port, **kwargs):
                self.calls.append(("getaddrinfo", host, port, kwargs))
                return [(mock.sentinel.family, mock.sentinel.socktype, 0, "", ("1.2.3.4", port))]

            async def sock_connect(self, sock, address):
                self.calls.append(("sock_connect", sock, address))

        async def scenario():
            fake_loop = FakeLoop()
            fake_socket = FakeSocket()
            session = mock.AsyncMock()
            conn = bc.AsyncConn(session, 1, None, "example.com", 443, mock.Mock())

            with mock.patch("x_tunnel.local.async_base_container.asyncio.get_event_loop", return_value=fake_loop), \
                 mock.patch("x_tunnel.local.async_base_container.socket.socket", return_value=fake_socket), \
                 mock.patch("x_tunnel.local.async_base_container.utils.check_ip_valid4", return_value=False):
                sock, ok = await conn._do_connect("example.com", 443)

            self.assertTrue(ok)
            self.assertIs(sock, fake_socket)
            self.assertEqual(fake_loop.calls[0][0], "getaddrinfo")
            self.assertEqual(fake_loop.calls[1][0], "sock_connect")
            self.assertFalse(fake_socket.blocking)

        asyncio.run(scenario())
