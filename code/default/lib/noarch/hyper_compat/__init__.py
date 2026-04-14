# -*- coding: utf-8 -*-
"""
Hyper compatibility shim - provides hyper interfaces using pip packages.

This module replaces the bundled hyper library with h2, hpack, and hyperframe
from pip, maintaining the same interface for existing code.
"""

from __future__ import annotations

import socket
import errno
import threading
import queue
import time
import zlib
import struct

from hyperframe.frame import (
    DataFrame, HeadersFrame, PushPromiseFrame, RstStreamFrame,
    SettingsFrame, Frame, WindowUpdateFrame, GoAwayFrame, PingFrame,
    ContinuationFrame, FRAME_MAX_ALLOWED_LEN, FRAME_MAX_LEN, FRAMES
)

from hpack import Encoder, Decoder


__all__ = [
    'BufferedSocket',
    'ConnectionResetError',
    'HTTPHeaderMap',
    'ProtocolError',
    'StreamResetError',
    'h2_safe_headers',
    'strip_headers',
    'to_host_port_tuple',
    'to_native_string',
    'to_bytestring',
    'BaseFlowControlManager',
    'BlockedFrame',
    'FlowControlManager',
    'HTTP20Connection',
    'HTTP20Response',
    'DataFrame', 'HeadersFrame', 'PushPromiseFrame', 'RstStreamFrame',
    'SettingsFrame', 'Frame', 'WindowUpdateFrame', 'GoAwayFrame', 'PingFrame',
    'ContinuationFrame', 'FRAME_MAX_ALLOWED_LEN', 'FRAME_MAX_LEN', 'FRAMES',
    'Encoder', 'Decoder',
]


DEFAULT_WINDOW_SIZE = 65535


class ConnectionResetError(socket.error):
    pass


class ProtocolError(Exception):
    pass


class StreamResetError(Exception):
    def __init__(self, error_code: int, stream_id: int):
        self.error_code = error_code
        self.stream_id = stream_id
        super().__init__(f"Stream {stream_id} reset with error code {error_code}")


class HTTPHeaderMap(dict):
    def __getitem__(self, key):
        key = key.lower() if isinstance(key, str) else key
        return super().__getitem__(key)
    
    def __setitem__(self, key, value):
        key = key.lower() if isinstance(key, str) else key
        if isinstance(value, str):
            value = value.encode('utf-8')
        super().__setitem__(key, value)
    
    def __contains__(self, key):
        key = key.lower() if isinstance(key, str) else key
        return super().__contains__(key)
    
    def get(self, key, default=None):
        key = key.lower() if isinstance(key, str) else key
        return super().get(key, default)


class BlockedFrame(Frame):
    type = 0xb
    
    def __init__(self, stream_id: int):
        super().__init__(stream_id)
    
    def parse_body(self, data: memoryview) -> None:
        pass
    
    def serialize_body(self) -> bytes:
        return b''


FRAMES[BlockedFrame.type] = BlockedFrame


def h2_safe_headers(headers: HTTPHeaderMap) -> list:
    result = []
    for k, v in headers.items():
        if isinstance(k, str):
            k = k.encode('utf-8')
        if isinstance(v, str):
            v = v.encode('utf-8')
        result.append((k, v))
    return result


def strip_headers(headers: HTTPHeaderMap) -> None:
    for name in list(headers.keys()):
        if isinstance(name, bytes) and name.startswith(b':'):
            del headers[name]
        elif isinstance(name, str) and name.startswith(':'):
            del headers[name]


def to_host_port_tuple(host_port: str, default_port: int = 443) -> tuple:
    if isinstance(host_port, bytes):
        host_port = host_port.decode('utf-8')
    if ':' in host_port and not host_port.startswith('['):
        host, port_str = host_port.rsplit(':', 1)
        try:
            port = int(port_str)
        except ValueError:
            port = default_port
        return (host, port)
    return (host_port, default_port)


def to_native_string(s):
    if isinstance(s, bytes):
        return s.decode('utf-8', errors='replace')
    return s


def to_bytestring(s):
    if isinstance(s, str):
        return s.encode('utf-8')
    if isinstance(s, memoryview):
        return bytes(s)
    return s


class BaseFlowControlManager:
    def __init__(self, initial_window_size: int):
        self.initial_window_size = initial_window_size
        self.window_size = initial_window_size
    
    def _handle_frame(self, frame_size: int) -> int:
        self.window_size -= frame_size
        return self.increase_window_size(frame_size)
    
    def increase_window_size(self, frame_size: int) -> int:
        future_window_size = self.window_size - frame_size
        if future_window_size < (self.initial_window_size * 3 / 4):
            return self.initial_window_size - future_window_size
        if future_window_size < 1000:
            return self.initial_window_size - future_window_size
        return 0
    
    def blocked(self) -> int:
        return self.initial_window_size - self.window_size
    
    def process_window_update(self, increment: int) -> None:
        self.window_size += increment


class FlowControlManager(BaseFlowControlManager):
    def increase_window_size(self, frame_size: int) -> int:
        future_window_size = self.window_size - frame_size
        if ((future_window_size < (self.initial_window_size * 3 / 4)) or
            (future_window_size < 1000)):
            return self.initial_window_size - future_window_size
        return 0
    
    def blocked(self) -> int:
        return self.initial_window_size - self.window_size


class BufferedSocket:
    def __init__(self, sock: socket.socket, buffer_size: int = 65535):
        self._sock = sock
        self._buffer_size = buffer_size
        self._buffer = b''
        self.bytes_received = 0
        self.bytes_sent = 0
    
    def recv(self, size: int) -> bytes:
        if self._buffer:
            data = self._buffer[:size]
            self._buffer = self._buffer[size:]
            return data
        
        try:
            data = self._sock.recv(self._buffer_size)
        except socket.error as e:
            if e.errno in (errno.ECONNRESET, errno.EPIPE):
                raise ConnectionResetError(str(e))
            raise
        
        self.bytes_received += len(data)
        
        if len(data) > size:
            self._buffer = data[size:]
            return data[:size]
        
        return data
    
    def send(self, data: bytes, flush: bool = True) -> int:
        try:
            sent = self._sock.send(data)
            self.bytes_sent += sent
            return sent
        except socket.error as e:
            if e.errno in (errno.ECONNRESET, errno.EPIPE):
                raise ConnectionResetError(str(e))
            raise
    
    def flush(self) -> None:
        pass
    
    def close(self) -> None:
        self._sock.close()
    
    def fileno(self) -> int:
        return self._sock.fileno()
    
    def settimeout(self, timeout: float) -> None:
        self._sock.settimeout(timeout)
    
    def gettimeout(self) -> float:
        return self._sock.gettimeout()


class HTTP20Response:
    def __init__(self, headers: dict, stream):
        self.reason = ''
        status = headers.get(b':status', [b'200'])[0]
        if isinstance(status, list):
            status = status[0]
        self.status = int(status)
        
        strip_headers(headers)
        self.headers = headers
        self._trailers = None
        self._stream = stream
        self._data_buffer = b''
        
        ce = self.headers.get(b'content-encoding', [])
        if isinstance(ce, list):
            ce = ce[0] if ce else b''
        if b'gzip' in ce:
            self._decompressobj = zlib.decompressobj(16 + zlib.MAX_WBITS)
        elif b'deflate' in ce:
            self._decompressobj = zlib.decompressobj()
        else:
            self._decompressobj = None
    
    def read(self, amt: int = None, decode_content: bool = True) -> bytes:
        if amt is None:
            data = b''
            while True:
                chunk = self._stream.recv_data()
                if not chunk:
                    break
                data += chunk
            if decode_content and self._decompressobj:
                try:
                    data = self._decompressobj.decompress(data)
                except Exception:
                    pass
            return data
        
        while len(self._data_buffer) < amt:
            chunk = self._stream.recv_data()
            if not chunk:
                break
            self._data_buffer += chunk
        
        data = self._data_buffer[:amt]
        self._data_buffer = self._data_buffer[amt:]
        
        if decode_content and self._decompressobj:
            try:
                data = self._decompressobj.decompress(data)
            except Exception:
                pass
        
        return data
    
    def close(self) -> None:
        pass


class H2Stream:
    def __init__(self, stream_id: int, conn: 'HTTP20Connection'):
        self.stream_id = stream_id
        self._conn = conn
        self._data_queue = queue.Queue()
        self._headers = None
        self._closed = False
    
    def recv_data(self) -> bytes:
        try:
            return self._data_queue.get(timeout=5)
        except queue.Empty:
            return b''
    
    def getheaders(self) -> dict:
        while self._headers is None:
            time.sleep(0.01)
            if self._closed:
                return {}
        return self._headers
    
    def close(self) -> None:
        self._closed = True


class HTTP20Connection:
    def __init__(self, ssl_sock, host: str = None, ip: str = None, port: int = None,
                 secure: bool = None, window_manager=None, enable_push: bool = False,
                 ssl_context=None, proxy_host=None, proxy_port=None, **kwargs):
        self.ip = ip
        self.host = host
        self.port = port or 443
        self.secure = secure if secure is not None else (self.port == 443)
        
        self.network_buffer_size = 65536
        self.streams = {}
        self.next_stream_id = 1
        self.encoder = Encoder()
        self.decoder = Decoder()
        
        self._settings = {
            SettingsFrame.INITIAL_WINDOW_SIZE: DEFAULT_WINDOW_SIZE,
            SettingsFrame.MAX_FRAME_SIZE: FRAME_MAX_LEN,
        }
        
        if ssl_sock:
            self._sock = BufferedSocket(ssl_sock, self.network_buffer_size)
            self._send_preamble()
            threading.Thread(target=self._recv_loop, name="h2_recv", daemon=True).start()
        else:
            self._sock = None
    
    def _send_preamble(self) -> None:
        self._sock.send(b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n')
        f = SettingsFrame(0)
        f.settings[SettingsFrame.ENABLE_PUSH] = 0
        data = f.serialize()
        self._sock.send(data)
    
    def _recv_loop(self) -> None:
        while True:
            try:
                header = self._sock.recv(9)
                if not header:
                    break
                frame, length = Frame.parse_frame_header(header)
                if length:
                    data = self._sock.recv(length)
                    frame.parse_body(memoryview(data))
                
                if frame.type == SettingsFrame.type:
                    if b'ACK' not in frame.flags:
                        ack = SettingsFrame(0)
                        ack.flags.add(b'ACK')
                        self._sock.send(ack.serialize())
                elif frame.type == HeadersFrame.type:
                    if frame.stream_id in self.streams:
                        stream = self.streams[frame.stream_id]
                        headers = self.decoder.decode(frame.data)
                        stream._headers = HTTPHeaderMap()
                        for k, v in headers:
                            stream._headers[k] = v
                elif frame.type == DataFrame.type:
                    if frame.stream_id in self.streams:
                        stream = self.streams[frame.stream_id]
                        stream._data_queue.put(bytes(frame.data))
                elif frame.type == GoAwayFrame.type:
                    break
                elif frame.type == WindowUpdateFrame.type:
                    pass
                
            except Exception:
                break
    
    def request(self, method: str, url: str, body: bytes = None, headers: dict = {}) -> int:
        stream_id = self._putrequest(method, url)
        
        for name, value in headers.items():
            self._putheader(name, value, stream_id)
        
        if body:
            body = to_bytestring(body)
        
        self._endheaders(body, stream_id)
        
        return stream_id
    
    def _putrequest(self, method: str, url: str) -> int:
        stream_id = self.next_stream_id
        self.next_stream_id += 2
        
        stream = H2Stream(stream_id, self)
        self.streams[stream_id] = stream
        
        req_headers = [
            (b':method', method.encode('utf-8')),
            (b':path', url.encode('utf-8')),
            (b':scheme', b'https'),
            (b':authority', self.host.encode('utf-8') if self.host else b''),
        ]
        
        encoded = self.encoder.encode(req_headers)
        f = HeadersFrame(stream_id)
        f.data = encoded
        f.flags.add(b'END_HEADERS')
        self._sock.send(f.serialize())
        
        return stream_id
    
    def _putheader(self, name: str, value: str, stream_id: int) -> None:
        name_bytes = to_bytestring(name)
        value_bytes = to_bytestring(value)
        
    def _endheaders(self, body: bytes, stream_id: int) -> None:
        if body:
            f = DataFrame(stream_id)
            f.data = body
            f.flags.add(b'END_STREAM')
            self._sock.send(f.serialize())
        else:
            f = DataFrame(stream_id)
            f.data = b''
            f.flags.add(b'END_STREAM')
            self._sock.send(f.serialize())
    
    def get_response(self, stream_id: int = None) -> HTTP20Response:
        if stream_id is None:
            stream_id = min(self.streams.keys()) if self.streams else None
        
        if stream_id is None or stream_id not in self.streams:
            raise Exception("No stream available")
        
        stream = self.streams[stream_id]
        headers = stream.getheaders()
        return HTTP20Response(headers, stream)
    
    def close(self) -> None:
        if self._sock:
            self._sock.close()