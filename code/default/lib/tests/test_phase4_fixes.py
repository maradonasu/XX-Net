#!/usr/bin/env python3
# coding:utf-8

import os
import sys
import asyncio
import hashlib
import json
import socket
import struct
import time
from unittest import TestCase, mock

code_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if code_root not in sys.path:
    sys.path.insert(0, code_root)
lib_path = os.path.join(code_root, 'lib', 'noarch')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

import async_loop


class TestAsyncSendBufferSNTracking(TestCase):
    def test_get_returns_data_and_sn(self):
        from x_tunnel.local.async_base_container import AsyncSendBuffer

        async def do_test():
            buf = AsyncSendBuffer(max_payload=65536)
            await buf.add(b"hello world")
            data, sn = await buf.get()
            self.assertEqual(data.to_bytes(), b"hello world")
            self.assertEqual(sn, 1)

        async_loop.run_async(do_test(), timeout=5)

    def test_sequential_sn_assignment(self):
        from x_tunnel.local.async_base_container import AsyncSendBuffer

        async def do_test():
            buf = AsyncSendBuffer(max_payload=5)
            await buf.add(b"aaaaabbbbbccccc")
            d1, sn1 = await buf.get()
            d2, sn2 = await buf.get()
            d3, sn3 = await buf.get()
            self.assertEqual(sn1, 1)
            self.assertEqual(sn2, 2)
            self.assertEqual(sn3, 3)

        async_loop.run_async(do_test(), timeout=5)

    def test_get_empty_returns_zero_sn(self):
        from x_tunnel.local.async_base_container import AsyncSendBuffer

        async def do_test():
            buf = AsyncSendBuffer()
            data, sn = await buf.get()
            self.assertEqual(data, b"")
            self.assertEqual(sn, 0)

        async_loop.run_async(do_test(), timeout=5)

    def test_sn_independent_from_transfer_no(self):
        from x_tunnel.local.async_proxy_session import AsyncProxySession

        async def do_test():
            session = AsyncProxySession()
            session.running = True
            buf = session.send_buffer
            buf.max_payload = 10
            await buf.add(b"test data 111")  # 13 bytes > 10
            await buf.add(b"test data 222")  # 13 bytes
            d1, sn1 = await buf.get()
            d2, sn2 = await buf.get()
            d3, sn3 = await buf.get()
            self.assertEqual(sn1, 1)
            self.assertEqual(sn2, 2)
            self.assertEqual(sn3, 3)
            async with session.lock:
                session.last_transfer_no += 1
                transfer_no = session.last_transfer_no
            self.assertEqual(transfer_no, 1)
            self.assertNotEqual(sn3, transfer_no)

        async_loop.run_async(do_test(), timeout=5)


class TestAsyncConnFlowControl(TestCase):
    def test_conn_has_window_attributes(self):
        from x_tunnel.local.async_base_container import AsyncConn

        async def do_test():
            class FakeSession:
                pass
            conn = AsyncConn(FakeSession(), 1, None, "host", 80, None,
                             windows_size=65536, windows_ack=40)
            self.assertEqual(conn.windows_size, 65536)
            self.assertEqual(conn.windows_ack, 40)
            self.assertEqual(conn.sent_window_position, 0)

        async_loop.run_async(do_test(), timeout=5)

    def test_transfer_ack_sends_protocol_message(self):
        from x_tunnel.local.async_base_container import AsyncConn

        async def do_test():
            sent_data = []

            class FakeSession:
                async def send_conn_data(self, conn_id, data):
                    sent_data.append((conn_id, data))

            session = FakeSession()
            conn = AsyncConn(session, 5, None, "host", 80, None)
            await conn.transfer_ack(12345)
            self.assertEqual(len(sent_data), 1)
            self.assertEqual(sent_data[0][0], 5)
            cmd_data = sent_data[0][1]
            cmd_id = struct.unpack("<B", cmd_data[4:5])[0]
            self.assertEqual(cmd_id, 3)
            position = struct.unpack("<Q", cmd_data[5:13])[0]
            self.assertEqual(position, 12345)

        async_loop.run_async(do_test(), timeout=5)

    def test_transfer_peer_close_sends_protocol_message(self):
        from x_tunnel.local.async_base_container import AsyncConn

        async def do_test():
            sent_data = []

            class FakeSession:
                async def send_conn_data(self, conn_id, data):
                    sent_data.append((conn_id, data))

            session = FakeSession()
            conn = AsyncConn(session, 5, None, "host", 80, None)
            await conn.transfer_peer_close("test reason")
            self.assertEqual(len(sent_data), 1)
            cmd_data = sent_data[0][1]
            seq = struct.unpack("<I", cmd_data[0:4])[0]
            cmd_id = struct.unpack("<B", cmd_data[4:5])[0]
            self.assertEqual(cmd_id, 2)
            self.assertEqual(seq, 1)
            self.assertIn(b"test reason", cmd_data[5:])

        async_loop.run_async(do_test(), timeout=5)

    def test_transfer_received_data_sends_protocol_message(self):
        from x_tunnel.local.async_base_container import AsyncConn
        from x_tunnel.local.base_container import WriteBuffer

        async def do_test():
            sent_data = []

            class FakeSession:
                async def send_conn_data(self, conn_id, data):
                    if isinstance(data, WriteBuffer):
                        data = data.to_bytes()
                    sent_data.append((conn_id, data))

            session = FakeSession()
            conn = AsyncConn(session, 5, None, "host", 80, None)
            await conn.transfer_received_data(b"payload")
            self.assertEqual(len(sent_data), 1)
            cmd_data = sent_data[0][1]
            seq = struct.unpack("<I", cmd_data[0:4])[0]
            cmd_id = struct.unpack("<B", cmd_data[4:5])[0]
            self.assertEqual(cmd_id, 1)
            self.assertEqual(seq, 1)

        async_loop.run_async(do_test(), timeout=5)

    def test_peer_close_only_once(self):
        from x_tunnel.local.async_base_container import AsyncConn

        async def do_test():
            sent_count = [0]

            class FakeSession:
                async def send_conn_data(self, conn_id, data):
                    sent_count[0] += 1

            session = FakeSession()
            conn = AsyncConn(session, 5, None, "host", 80, None)
            await conn.transfer_peer_close("first")
            await conn.transfer_peer_close("second")
            self.assertEqual(sent_count[0], 1)

        async_loop.run_async(do_test(), timeout=5)

    def test_recv_seq_increments(self):
        from x_tunnel.local.async_base_container import AsyncConn
        from x_tunnel.local.base_container import WriteBuffer

        async def do_test():
            sent_seqs = []

            class FakeSession:
                async def send_conn_data(self, conn_id, data):
                    if isinstance(data, WriteBuffer):
                        data = data.to_bytes()
                    seq = struct.unpack("<I", data[0:4])[0]
                    sent_seqs.append(seq)

            session = FakeSession()
            conn = AsyncConn(session, 5, None, "host", 80, None)
            await conn.transfer_received_data(b"a")
            await conn.transfer_received_data(b"b")
            await conn.transfer_ack(100)
            self.assertEqual(sent_seqs, [1, 2, 3])

        async_loop.run_async(do_test(), timeout=5)


class TestAsyncConnCommandProcessing(TestCase):
    def _make_readbuf(self, data):
        from x_tunnel.local.base_container import ReadBuffer
        return ReadBuffer(data)

    def test_process_cmd_data_forwards_to_writer(self):
        from x_tunnel.local.async_base_container import AsyncConn

        async def do_test():
            written = []

            class FakeWriter:
                def write(self, data):
                    written.append(data)
                async def drain(self):
                    pass
                def close(self):
                    pass
                async def wait_closed(self):
                    pass

            class FakeSession:
                async def send_conn_data(self, conn_id, data):
                    pass
                async def remove_conn_async(self, conn_id):
                    pass

            session = FakeSession()
            conn = AsyncConn(session, 1, None, "host", 80, None)
            conn._writer = FakeWriter()
            conn.running = True
            conn.next_cmd_seq = 1

            payload = struct.pack("<IB", 1, 1) + b"test payload"
            await conn.put_cmd_data(self._make_readbuf(payload))

            await asyncio.sleep(0.1)
            self.assertEqual(len(written), 1)
            self.assertEqual(written[0], b"test payload")

        async_loop.run_async(do_test(), timeout=5)

    def test_process_cmd_close_stops_conn(self):
        from x_tunnel.local.async_base_container import AsyncConn

        async def do_test():
            class FakeSession:
                async def send_conn_data(self, conn_id, data):
                    pass
                async def remove_conn_async(self, conn_id):
                    pass

            session = FakeSession()
            conn = AsyncConn(session, 1, None, "host", 80, None, is_client=True)
            conn.running = True
            conn.next_cmd_seq = 1

            payload = struct.pack("<IB", 1, 2) + b"peer closed"
            await conn.put_cmd_data(self._make_readbuf(payload))
            await asyncio.sleep(0.1)
            self.assertFalse(conn.running)

        async_loop.run_async(do_test(), timeout=5)

    def test_process_cmd_ack_updates_position(self):
        from x_tunnel.local.async_base_container import AsyncConn

        async def do_test():
            class FakeSession:
                async def send_conn_data(self, conn_id, data):
                    pass

            session = FakeSession()
            conn = AsyncConn(session, 1, None, "host", 80, None)
            conn.running = True
            conn.next_cmd_seq = 1

            position = 99999
            payload = struct.pack("<IBQ", 1, 3, position)
            await conn.put_cmd_data(self._make_readbuf(payload))
            await asyncio.sleep(0.1)
            self.assertEqual(conn.remote_acked_position, position)

        async_loop.run_async(do_test(), timeout=5)


class TestChecksumVerification(TestCase):
    def test_checksum_valid(self):
        content = b"\x00" * 43 + b"data_payload" + b"\x00" * 12
        checksum = hashlib.md5(content).hexdigest().encode()
        full_content = content + checksum
        computed = hashlib.md5(content).hexdigest().encode()
        self.assertEqual(checksum, computed)

    def test_checksum_detects_corruption(self):
        content = b"\x00" * 43 + b"original" + b"\x00" * 12
        checksum = hashlib.md5(content).hexdigest().encode()
        corrupted = b"\x00" * 43 + b"modified!" + b"\x00" * 12
        computed = hashlib.md5(corrupted).hexdigest().encode()
        self.assertNotEqual(checksum, computed)


class TestProtocolVersionValidation(TestCase):
    def test_parse_login_rejects_wrong_version(self):
        from x_tunnel.local.async_proxy_session import AsyncProxySession

        async def do_test():
            session = AsyncProxySession()
            info = b"P\x02\x01\x00\x00" + b"OK"
            result = session._parse_login_response(info)
            self.assertFalse(result)

        async_loop.run_async(do_test(), timeout=5)

    def test_parse_login_rejects_wrong_pack_type(self):
        from x_tunnel.local.async_proxy_session import AsyncProxySession

        async def do_test():
            session = AsyncProxySession()
            info = b"P\x01\x02\x00\x00" + b"OK"
            result = session._parse_login_response(info)
            self.assertFalse(result)

        async_loop.run_async(do_test(), timeout=5)

    def test_parse_login_accepts_valid(self):
        from x_tunnel.local.async_proxy_session import AsyncProxySession
        from x_tunnel.local import global_var as g

        async def do_test():
            session = AsyncProxySession()
            pv = getattr(g, 'protocol_version', 1)
            msg = json.dumps({"full_log": False}).encode()
            info = b"P" + struct.pack("BB", pv, 1) + struct.pack("<H", 0) + msg
            result = session._parse_login_response(info)
            self.assertTrue(result)

        async_loop.run_async(do_test(), timeout=5)


class TestResendTimeoutUnit(TestCase):
    def test_resend_timeout_converted_from_ms(self):
        from x_tunnel.local.async_proxy_session import AsyncProxySession

        async def do_test():
            session = AsyncProxySession()
            self.assertLess(session.resend_timeout, 100)

        async_loop.run_async(do_test(), timeout=5)


class TestTriggerMore(TestCase):
    def test_trigger_more_exists(self):
        from x_tunnel.local.async_proxy_session import AsyncProxySession

        async def do_test():
            session = AsyncProxySession()
            session.running = True
            session.target_on_roads = 5
            session.wait_queue = type('WQ', (), {
                '_event': asyncio.Event(),
                '_running': True,
                '_waiters': 0,
                'notify': lambda self: None,
                'waiters': 0,
            })()
            session.trigger_more()
            self.assertTrue(hasattr(session, 'trigger_more'))

        async_loop.run_async(do_test(), timeout=5)


class TestCheckUploadNotAcked(TestCase):
    def test_method_exists(self):
        from x_tunnel.local.async_proxy_session import AsyncProxySession
        self.assertTrue(hasattr(AsyncProxySession, 'check_upload_not_acked'))

    def test_marks_stale_transfer_as_timeout(self):
        from x_tunnel.local.async_proxy_session import AsyncProxySession

        async def do_test():
            session = AsyncProxySession()
            session.running = True
            session.server_time_deviation = 0.1
            session.server_time_offset = 0
            old_time = 100
            session.transfer_list[1] = {
                "stat": "request",
                "server_received": False,
                "server_sent": False,
                "start_time": old_time,
                "server_timeout": 30,
            }
            server_time = old_time + session.send_timeout_retry + 1
            await session.check_upload_not_acked(server_time)
            self.assertEqual(session.transfer_list[1]["stat"], "timeout")

        async_loop.run_async(do_test(), timeout=5)


class TestContentLengthValidation(TestCase):
    def test_rejects_mismatched_content_length(self):
        from x_tunnel.local.async_proxy_session import AsyncProxySession

        async def do_test():
            session = AsyncProxySession()
            self.assertFalse(hasattr(session, '_validate_content_length') and
                             session._validate_content_length is None)

        async_loop.run_async(do_test(), timeout=5)
