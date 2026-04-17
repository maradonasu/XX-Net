#!/usr/bin/env python3
# coding:utf-8

from __future__ import annotations

import asyncio
import socket
import struct
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from log_buffer import getLogger
xlog = getLogger("x_tunnel")

import utils


class WriteBuffer:
    def __init__(self, s: Optional[bytes] = None) -> None:
        if isinstance(s, bytes):
            self.string_len: int = len(s)
            self.buffer_list: list[bytes] = [s]
        elif s is None:
            self.reset()
        else:
            raise Exception("WriteBuffer init not bytes or None")

    def reset(self) -> None:
        self.buffer_list = []
        self.string_len = 0

    def __len__(self) -> int:
        return self.string_len

    def __add__(self, other: Union[bytes, WriteBuffer]) -> WriteBuffer:
        self.append(other)
        return self

    def insert(self, s: Union[bytes, WriteBuffer]) -> None:
        if isinstance(s, WriteBuffer):
            self.buffer_list = s.buffer_list + self.buffer_list
            self.string_len += s.string_len
        elif isinstance(s, bytes):
            self.buffer_list.insert(0, s)
            self.string_len += len(s)
        else:
            raise Exception("WriteBuffer insert not bytes or WriteBuffer")

    def append(self, s: Union[bytes, WriteBuffer]) -> None:
        if isinstance(s, WriteBuffer):
            self.buffer_list.extend(s.buffer_list)
            self.string_len += s.string_len
        elif isinstance(s, bytes):
            self.buffer_list.append(s)
            self.string_len += len(s)
        else:
            raise Exception("WriteBuffer append not bytes or WriteBuffer")

    def to_bytes(self) -> bytes:
        return b"".join(self.buffer_list)

    def __bytes__(self) -> bytes:
        return self.to_bytes()

    def __str__(self) -> str:
        return self.to_bytes().decode("ascii", errors="replace")


class ReadBuffer:
    def __init__(self, buf, begin: int = 0, size: Optional[int] = None) -> None:
        if isinstance(buf, ReadBuffer):
            buf = buf.to_bytes()
            if begin == 0:
                begin = 0
        buf_len = len(buf)
        if size is None:
            size = buf_len - begin
        self.buf: bytes = buf
        self.begin: int = begin
        self.size: int = size

    def __len__(self) -> int:
        return self.size

    def get(self, size: Optional[int] = None) -> bytes:
        if size is None:
            size = self.size
        if size > self.size:
            size = self.size
        data = self.buf[self.begin:self.begin + size]
        self.begin += size
        self.size -= size
        return data

    def get_buf(self, size: Optional[int] = None) -> ReadBuffer:
        if size is None:
            size = self.size
        if size > self.size:
            size = self.size
        new_buf = ReadBuffer(self.buf, self.begin, size)
        self.begin += size
        self.size -= size
        return new_buf

    def get_all(self) -> bytes:
        return self.get(self.size)

    def to_bytes(self) -> bytes:
        return self.buf[self.begin:self.begin + self.size]

    def __bytes__(self) -> bytes:
        return self.to_bytes()

    def __str__(self) -> str:
        return self.to_bytes().decode("ascii", errors="replace")


class AsyncWaitQueue:
    def __init__(self) -> None:
        self._event: asyncio.Event = asyncio.Event()
        self._running: bool = True
        self._waiters: int = 0
    
    async def wait(self, timeout: Optional[float] = None) -> bool:
        if not self._running:
            return False
        self._waiters += 1
        try:
            if timeout:
                await asyncio.wait_for(self._event.wait(), timeout)
            else:
                await self._event.wait()
            return self._running
        except asyncio.TimeoutError:
            return False
        finally:
            self._waiters -= 1
    
    def notify(self) -> None:
        self._event.set()
        self._event = asyncio.Event()
    
    def stop(self) -> None:
        self._running = False
        self._event.set()
    
    def reset(self) -> None:
        self._running = True
        self._waiters = 0
        self._event = asyncio.Event()
    
    @property
    def waiters(self) -> int:
        return self._waiters


class AsyncSendBuffer:
    def __init__(self, max_payload: int = 65536) -> None:
        self.max_payload: int = max_payload
        self.pool_size: int = 0
        self._lock: asyncio.Lock = asyncio.Lock()
        self.head_sn: int = 1
        self.tail_sn: int = 1
        self._block_list: Dict[int, WriteBuffer] = {}
        self._last_block: WriteBuffer = WriteBuffer()
        self.last_put_time: float = time.time()
    
    async def add(self, data: bytes) -> None:
        if not data:
            return
        self.last_put_time = time.time()
        async with self._lock:
            self.pool_size += len(data)
            self._last_block.append(data)
            while len(self._last_block) > self.max_payload:
                block_data = self._last_block.to_bytes()[:self.max_payload]
                self._block_list[self.head_sn] = WriteBuffer(block_data)
                self.head_sn += 1
                remaining = self._last_block.to_bytes()[self.max_payload:]
                self._last_block = WriteBuffer(remaining)
    
    async def get(self) -> Tuple[Union[bytes, WriteBuffer], int]:
        async with self._lock:
            if self.tail_sn < self.head_sn:
                data = self._block_list[self.tail_sn]
                del self._block_list[self.tail_sn]
                sn = self.tail_sn
                self.tail_sn += 1
                self.pool_size -= len(data)
                return data, sn
            
            if len(self._last_block) > 0:
                data = self._last_block
                sn = self.tail_sn
                self._last_block = WriteBuffer()
                self.head_sn += 1
                self.tail_sn += 1
                self.pool_size -= len(data)
                return data, sn
        
        return b"", 0
    
    async def get_payload(self) -> Optional[bytes]:
        data, sn = await self.get()
        if not data:
            return None
        if isinstance(data, WriteBuffer):
            return data.to_bytes()
        return bytes(data)
    
    async def reset(self) -> None:
        async with self._lock:
            self.pool_size = 0
            self.head_sn = 1
            self.tail_sn = 1
            self._block_list = {}
            self._last_block = WriteBuffer()
    
    def __len__(self) -> int:
        return self.pool_size
    
    def status(self) -> str:
        out = "AsyncSendBuffer:\n"
        out += f" size: {self.pool_size}\n"
        out += f" head_sn: {self.head_sn}\n"
        out += f" tail_sn: {self.tail_sn}\n"
        out += f" blocks: {len(self._block_list)}\n"
        return out


class AsyncConnectionPipe:
    def __init__(self, session: Any, logger: Any) -> None:
        self.session = session
        self.xlog = logger
        self.running: bool = False
        self._tasks: Dict[int, asyncio.Task] = {}
        self._conn_map: Dict[int, Any] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
    
    async def start(self) -> None:
        self.running = True
        self._conn_map = {}
        self._tasks = {}
    
    async def stop(self) -> None:
        self.running = False
        async with self._lock:
            for task in self._tasks.values():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=0.5)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass
            self._tasks.clear()
            self._conn_map.clear()
    
    async def add_sock(self, sock: socket.socket, conn: Any) -> None:
        if not sock or not self.running:
            return
        
        try:
            if sock.fileno() < 0:
                return
        except Exception:
            return
        
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        
        def protocol_factory():
            return asyncio.StreamReaderProtocol(reader)
        
        try:
            transport, protocol = await loop.connect_accepted_socket(
                protocol_factory, sock=sock
            )
            writer = asyncio.StreamWriter(transport, protocol, reader, loop)
        except Exception as e:
            if self.xlog:
                self.xlog.warn("add_sock connect_accepted_socket failed: %r", e)
            try:
                sock.close()
            except Exception:
                pass
            return
        
        async with self._lock:
            conn._reader = reader
            conn._writer = writer
            self._conn_map[conn.conn_id] = conn
            
            task = asyncio.create_task(self._conn_reader_loop(conn))
            self._tasks[conn.conn_id] = task
    
    async def _conn_reader_loop(self, conn: Any) -> None:
        try:
            while conn.running and self.running:
                data = await conn._reader.read(65536)
                if not data:
                    if self.xlog:
                        self.xlog.debug("conn %d reader got empty data", conn.conn_id)
                    break
                await conn.on_data_received(data)
        except asyncio.CancelledError:
            if self.xlog:
                self.xlog.debug("conn %d reader cancelled", conn.conn_id)
        except Exception as e:
            if self.xlog:
                self.xlog.debug("conn %d reader error: %r", conn.conn_id, e)
        finally:
            await self._remove_conn(conn.conn_id)
    
    async def _remove_conn(self, conn_id: int) -> None:
        async with self._lock:
            if conn_id in self._tasks:
                del self._tasks[conn_id]
            if conn_id in self._conn_map:
                conn = self._conn_map[conn_id]
                del self._conn_map[conn_id]
                await conn.stop_async("reader_end")
    
    async def send_to_conn(self, conn_id: int, data: bytes) -> bool:
        async with self._lock:
            conn = self._conn_map.get(conn_id)
            if not conn or not conn._writer:
                return False
        
        try:
            conn._writer.write(data)
            await conn._writer.drain()
            return True
        except Exception as e:
            if self.xlog:
                self.xlog.debug("send_to_conn %d error: %r", conn_id, e)
            return False
    
    async def reset_all_connections(self) -> None:
        async with self._lock:
            for conn_id, conn in list(self._conn_map.items()):
                try:
                    await conn.stop_async("reset_all")
                except Exception:
                    pass
            self._conn_map.clear()
            self._tasks.clear()
    
    def status(self) -> str:
        out = "AsyncConnectionPipe:\n"
        out += f" running: {self.running}\n"
        out += f" connections: {list(self._conn_map.keys())}\n"
        out += f" tasks: {len(self._tasks)}\n"
        return out


class AsyncConn:
    def __init__(self, session: Any, conn_id: int, sock: Optional[socket.socket],
                 host: str, port: int, logger: Any,
                 windows_size: int = 65536, windows_ack: int = 40,
                 is_client: bool = True) -> None:
        self.host = host
        self.port = port
        self.session = session
        self.conn_id = conn_id
        self.sock = sock
        self.xlog = logger
        
        self.windows_size = windows_size
        self.windows_ack = windows_ack
        self.is_client = is_client
        
        self.running: bool = True
        self.blocked: bool = False
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._lock: asyncio.Lock = asyncio.Lock()
        
        self.send_buffer: Optional[bytes] = None
        self.received_position: int = 0
        self.remote_acked_position: int = 0
        self.sended_position: int = 0
        self.sent_window_position: int = 0
        self.create_time = time.time()
        self.last_active = time.time()
        
        self.transferred_close_to_peer: bool = False
        self.next_recv_seq: int = 1
        self.next_cmd_seq: int = 1 if sock else 0
        
        self._cmd_queue: Dict[int, Any] = {}
        self._cmd_lock: asyncio.Lock = asyncio.Lock()
    
    async def start(self) -> None:
        if self.sock:
            await self.session.connection_pipe.add_sock(self.sock, self)
    
    async def on_data_received(self, data: bytes) -> None:
        self.last_active = time.time()
        await self.transfer_received_data(data)
    
    async def send(self, data: bytes) -> bool:
        if not self._writer or not self.running:
            return False
        
        try:
            self._writer.write(data)
            await self._writer.drain()
            self.sended_position += len(data)
            if self.sended_position - self.sent_window_position > self.windows_ack:
                self.sent_window_position = self.sended_position
                await self.transfer_ack(self.sended_position)
            return True
        except Exception as e:
            if self.xlog:
                self.xlog.debug("AsyncConn %d send error: %r", self.conn_id, e)
            return False
    
    async def put_cmd_data(self, data: Any) -> None:
        if not self.running:
            return
        
        seq = struct.unpack("<I", data.get(4))[0]
        if seq < self.next_cmd_seq:
            return
        
        should_process = False
        async with self._cmd_lock:
            self._cmd_queue[seq] = data.get_buf()
            if seq == self.next_cmd_seq:
                should_process = True
        
        if should_process:
            await self._process_next_cmd()
    
    async def _process_next_cmd(self) -> None:
        while self.running:
            async with self._cmd_lock:
                if self.next_cmd_seq not in self._cmd_queue:
                    return
                data = self._cmd_queue[self.next_cmd_seq]
                del self._cmd_queue[self.next_cmd_seq]
                cmd_id_bytes = data.get(1)
                cmd_id = struct.unpack("<B", cmd_id_bytes)[0]
                
                if cmd_id == 1:
                    payload = bytes(data.get())
                elif cmd_id == 3:
                    position = struct.unpack("<Q", data.get(8))[0]
                elif cmd_id == 2:
                    reason = data.get()
                    if isinstance(reason, memoryview):
                        reason = bytes(reason)
                elif cmd_id == 0:
                    sock_type = struct.unpack("<B", data.get(1))[0]
                    host_len = struct.unpack("<H", data.get(2))[0]
                    host_data = data.get(host_len)
                    port = struct.unpack("<H", data.get(2))[0]
                
                self.next_cmd_seq += 1
            
            self.last_active = time.time()
            
            if cmd_id == 1:
                await self._send_to_writer(payload)
            elif cmd_id == 3:
                if position > self.remote_acked_position:
                    self.remote_acked_position = position
            elif cmd_id == 2:
                if self.xlog:
                    self.xlog.debug("conn %d peer close: %s", self.conn_id, reason)
                if self.is_client:
                    await self.transfer_peer_close("finish")
                    if b"exceed the max connection" in reason:
                        await self.session.reset()
                await self.stop_async("peer close")
                return
            elif cmd_id == 0:
                host_str = host_data.decode('ascii', errors='replace')
                self.host = host_str
                self.port = port
                sock, ok = await self._do_connect(self.host, self.port)
                if not ok:
                    await self.transfer_peer_close("connect fail")
                else:
                    self.sock = sock
                    await self.session.connection_pipe.add_sock(sock, self)
            else:
                if self.xlog:
                    self.xlog.error("conn %d unknown cmd_id: %d", self.conn_id, cmd_id)
    
    async def _send_to_writer(self, data: bytes) -> None:
        if not self._writer or not self.running:
            return
        try:
            self._writer.write(data)
            await self._writer.drain()
            self.sended_position += len(data)
            if self.sended_position - self.sent_window_position > self.windows_ack:
                self.sent_window_position = self.sended_position
                await self.transfer_ack(self.sended_position)
        except Exception as e:
            if self.xlog:
                self.xlog.debug("conn %d send_to_writer error: %r", self.conn_id, e)
            self.blocked = True
    
    async def _do_connect(self, host: str, port: int) -> Tuple[Optional[socket.socket], bool]:
        try:
            loop = asyncio.get_event_loop()
            if ':' in host or utils.check_ip_valid4(host):
                family = socket.AF_INET6 if ':' in host else socket.AF_INET
                addr_info = [(family, socket.SOCK_STREAM, 0, "", (host, port))]
            else:
                addr_info = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)

            family, sock_type, proto, _, address = addr_info[0]
            sock = socket.socket(family, sock_type, proto)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)
            sock.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, True)
            sock.setblocking(False)
            await loop.sock_connect(sock, address)
            sock.setblocking(False)
            return sock, True
        except Exception as e:
            if self.xlog:
                self.xlog.debug("conn %d connect %s:%d fail: %r", self.conn_id, host, port, e)
            return e, False
    
    async def transfer_peer_close(self, reason: str = "") -> None:
        if self.transferred_close_to_peer:
            return
        self.transferred_close_to_peer = True
        
        cmd = struct.pack("<IB", self.next_recv_seq, 2)
        if isinstance(reason, str):
            reason = reason.encode("utf-8")
        await self.session.send_conn_data(self.conn_id, cmd + reason)
        self.next_recv_seq += 1
    
    async def transfer_received_data(self, data: bytes) -> None:
        if self.transferred_close_to_peer:
            return
        
        buf = WriteBuffer(struct.pack("<IB", self.next_recv_seq, 1))
        buf.append(data)
        self.next_recv_seq += 1
        self.received_position += len(data)
        
        await self.session.send_conn_data(self.conn_id, buf)
        
        if self.received_position > self.remote_acked_position + self.windows_size:
            if self.xlog:
                self.xlog.debug("conn %d recv blocked, rcv:%d ack:%d",
                                self.conn_id, self.received_position, self.remote_acked_position)
    
    async def transfer_ack(self, position: int) -> None:
        if self.transferred_close_to_peer:
            return
        
        cmd = struct.pack("<IBQ", self.next_recv_seq, 3, position)
        await self.session.send_conn_data(self.conn_id, cmd)
        self.next_recv_seq += 1
    
    async def stop_async(self, reason: str = "") -> None:
        if not self.running and reason != "reader_end":
            return
        self.running = False
        if self.xlog:
            self.xlog.debug("AsyncConn %d %s:%d stop: %s",
                            self.conn_id, self.host, self.port, reason)
        
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None
        
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        
        await self.session.remove_conn_async(self.conn_id)
    
    def status(self) -> str:
        out = f"AsyncConn[{self.conn_id}]: {self.host}:{self.port}\n"
        out += f" running: {self.running}\n"
        out += f" received: {self.received_position}\n"
        out += f" acked: {self.remote_acked_position}\n"
        out += f" sent: {self.sended_position}\n"
        out += f" window: {self.sent_window_position}\n"
        out += f" next_cmd_seq: {self.next_cmd_seq}\n"
        out += f" next_recv_seq: {self.next_recv_seq}\n"
        out += f" blocked: {self.blocked}\n"
        out += f" transferred_close: {self.transferred_close_to_peer}\n"
        out += f" created: {datetime.fromtimestamp(self.create_time)}\n"
        out += f" last_active: {datetime.fromtimestamp(self.last_active)}\n"
        return out


class AsyncBlockReceivePool:
    def __init__(self, handler: callable, logger: Any) -> None:
        self._handler = handler
        self.xlog = logger
        self._pool: Dict[int, List[bytes]] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
    
    async def add(self, conn_id: int, data: bytes) -> None:
        async with self._lock:
            if conn_id not in self._pool:
                self._pool[conn_id] = []
            self._pool[conn_id].append(data)
    
    async def process(self) -> None:
        async with self._lock:
            for conn_id, data_list in list(self._pool.items()):
                for data in data_list:
                    try:
                        await self._handler(conn_id, data)
                    except Exception as e:
                        if self.xlog:
                            self.xlog.warn("BlockReceivePool handler error: %r", e)
                self._pool[conn_id] = []
    
    async def reset(self) -> None:
        async with self._lock:
            self._pool = {}
    
    def status(self) -> str:
        return f"AsyncBlockReceivePool: {len(self._pool)} connections"
