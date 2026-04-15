#!/usr/bin/env python3
# coding:utf-8

import sys
import os

noarch_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'noarch'))
if noarch_lib not in sys.path:
    sys.path.insert(0, noarch_lib)

code_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if code_dir not in sys.path:
    sys.path.insert(0, code_dir)

from unittest import TestCase
import x_tunnel.local.base_container as bc

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

class TestAckPool(TestCase):
    def test_init(self):
        ap = bc.AckPool()
        self.assertEqual(len(ap.ack_buffer), 0)

    def test_put_and_get(self):
        ap = bc.AckPool()
        ap.put(b"data1")
        ap.put(b"data2")
        data = ap.get()
        self.assertEqual(len(data), 10)
        self.assertEqual(data.to_bytes(), b"data1data2")

    def test_get_empty(self):
        ap = bc.AckPool()
        data = ap.get()
        self.assertEqual(len(data), 0)

    def test_reset(self):
        ap = bc.AckPool()
        ap.put(b"data")
        ap.reset()
        self.assertEqual(len(ap.ack_buffer), 0)

    def test_multiple_gets(self):
        ap = bc.AckPool()
        ap.put(b"data1")
        first = ap.get()
        self.assertEqual(len(first), 5)
        
        ap.put(b"data2")
        second = ap.get()
        self.assertEqual(len(second), 5)

class TestWaitQueue(TestCase):
    def test_init(self):
        wq = bc.WaitQueue()
        self.assertTrue(wq.running)
        self.assertEqual(len(wq.waiters), 0)

    def test_stop(self):
        wq = bc.WaitQueue()
        wq.stop()
        self.assertFalse(wq.running)

    def test_notify_without_waiters(self):
        wq = bc.WaitQueue()
        wq.notify()
        self.assertEqual(len(wq.waiters), 0)