#!/usr/bin/env python3
# coding:utf-8

import os
import sys
import unittest
import socket
import asyncio
import time
from unittest import TestCase

code_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if code_root not in sys.path:
    sys.path.insert(0, code_root)
lib_path = os.path.join(code_root, 'lib', 'noarch')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

import async_loop


class TestAsyncWaitQueue(TestCase):
    def test_init(self):
        from x_tunnel.local.async_base_container import AsyncWaitQueue
        
        async def do_test():
            q = AsyncWaitQueue()
            self.assertTrue(q._running)
        
        async_loop.run_async(do_test(), timeout=5)
    
    def test_wait_and_notify(self):
        from x_tunnel.local.async_base_container import AsyncWaitQueue
        
        async def do_test():
            q = AsyncWaitQueue()
            results = []
            
            async def waiter():
                r = await q.wait(timeout=2)
                results.append(r)
            
            task = asyncio.create_task(waiter())
            await asyncio.sleep(0.1)
            self.assertEqual(results, [])
            
            q.notify()
            await asyncio.sleep(0.1)
            self.assertEqual(results, [True])
        
        async_loop.run_async(do_test(), timeout=5)
    
    def test_wait_timeout(self):
        from x_tunnel.local.async_base_container import AsyncWaitQueue
        
        async def do_test():
            q = AsyncWaitQueue()
            result = await q.wait(timeout=0.5)
            self.assertFalse(result)
        
        async_loop.run_async(do_test(), timeout=5)
    
    def test_stop(self):
        from x_tunnel.local.async_base_container import AsyncWaitQueue
        
        async def do_test():
            q = AsyncWaitQueue()
            q.stop()
            result = await q.wait(timeout=1)
            self.assertFalse(result)
        
        async_loop.run_async(do_test(), timeout=5)


class TestAsyncSendBuffer(TestCase):
    def test_init(self):
        from x_tunnel.local.async_base_container import AsyncSendBuffer
        
        async def do_test():
            buf = AsyncSendBuffer()
            self.assertEqual(buf.pool_size, 0)
        
        async_loop.run_async(do_test(), timeout=5)
    
    def test_add_and_get(self):
        from x_tunnel.local.async_base_container import AsyncSendBuffer
        
        async def do_test():
            buf = AsyncSendBuffer(max_payload=10)
            await buf.add(b"hello world test")
            self.assertEqual(buf.pool_size, 16)
            
            payload = await buf.get_payload()
            self.assertEqual(payload, b"hello worl")
            self.assertEqual(buf.pool_size, 6)
            
            payload = await buf.get_payload()
            self.assertEqual(payload, b"d test")
            self.assertEqual(buf.pool_size, 0)
        
        async_loop.run_async(do_test(), timeout=5)
    
    def test_get_empty(self):
        from x_tunnel.local.async_base_container import AsyncSendBuffer
        
        async def do_test():
            buf = AsyncSendBuffer()
            payload = await buf.get_payload()
            self.assertIsNone(payload)
        async_loop.run_async(do_test(), timeout=5)
    
    def test_reset(self):
        from x_tunnel.local.async_base_container import AsyncSendBuffer
        
        async def do_test():
            buf = AsyncSendBuffer()
            await buf.add(b"test")
            await buf.reset()
            self.assertEqual(buf.pool_size, 0)
        async_loop.run_async(do_test(), timeout=5)


class TestAsyncConnectionPipe(TestCase):
    def test_init(self):
        from x_tunnel.local.async_base_container import AsyncConnectionPipe
        
        async def do_test():
            class FakeSession:
                pass
            pipe = AsyncConnectionPipe(FakeSession(), None)
            self.assertFalse(pipe.running)
        async_loop.run_async(do_test(), timeout=5)
    
    def test_start_stop(self):
        from x_tunnel.local.async_base_container import AsyncConnectionPipe
        
        async def do_test():
            class FakeSession:
                pass
            pipe = AsyncConnectionPipe(FakeSession(), None)
            await pipe.start()
            self.assertTrue(pipe.running)
            await pipe.stop()
            self.assertFalse(pipe.running)
        async_loop.run_async(do_test(), timeout=5)


class TestAsyncConn(TestCase):
    def test_init(self):
        from x_tunnel.local.async_base_container import AsyncConn
        
        async def do_test():
            class FakeSession:
                pass
            
            conn = AsyncConn(FakeSession(), 1, None, "127.0.0.1", 80, None)
            self.assertEqual(conn.conn_id, 1)
            self.assertEqual(conn.host, "127.0.0.1")
            self.assertTrue(conn.running)
        async_loop.run_async(do_test(), timeout=5)
    
    def test_status(self):
        from x_tunnel.local.async_base_container import AsyncConn
        
        async def do_test():
            class FakeSession:
                pass
            
            conn = AsyncConn(FakeSession(), 1, None, "127.0.0.1", 80, None)
            status = conn.status()
            self.assertIn("AsyncConn[1]", status)
        async_loop.run_async(do_test(), timeout=5)


class TestAsyncBlockReceivePool(TestCase):
    def test_init(self):
        from x_tunnel.local.async_base_container import AsyncBlockReceivePool
        
        async def do_test():
            pool = AsyncBlockReceivePool(lambda cid, data: None, None)
            self.assertIsNotNone(pool)
        async_loop.run_async(do_test(), timeout=5)


class TestAsyncEndToEnd(TestCase):
    def test_conn_on_data_received_flow(self):
        from x_tunnel.local.async_base_container import AsyncConn
        
        async def do_test():
            received_cmds = []
            
            class FakeSession:
                def __init__(self):
                    self.connection_pipe = None
                
                async def send_conn_data(self, conn_id, data):
                    received_cmds.append((conn_id, data))
                
                async def remove_conn_async(self, conn_id):
                    pass
            
            session = FakeSession()
            conn = AsyncConn(session, 1, None, "test", 80, None)
            conn.next_recv_seq = 1
            
            await conn.on_data_received(b"hello async")
            
            self.assertEqual(len(received_cmds), 1)
            conn_id, data = received_cmds[0]
            self.assertEqual(conn_id, 1)
            raw = bytes(data)
            self.assertGreater(len(raw), 5)
            
            cmd_id = raw[4]
            self.assertEqual(cmd_id, 1)
            
            payload = raw[5:]
            self.assertEqual(payload, b"hello async")
        
        async_loop.run_async(do_test(), timeout=10)