#!/usr/bin/env python3
# coding:utf-8
"""
Async base containers for X-Tunnel.
Provides async versions of WaitQueue, SendBuffer, ConnectionPipe, Conn.
"""

from __future__ import annotations

import asyncio
import socket
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from log_buffer import getLogger
xlog = getLogger("x_tunnel")

import utils


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
        self._buffer: bytearray = bytearray()
        self._lock: asyncio.Lock = asyncio.Lock()
    
    async def add(self, data: bytes) -> None:
        async with self._lock:
            self._buffer.extend(data)
            self.pool_size = len(self._buffer)
    
    async def get_payload(self) -> Optional[bytes]:
        async with self._lock:
            if len(self._buffer) == 0:
                return None
            payload = bytes(self._buffer[:self.max_payload])
            self._buffer = self._buffer[self.max_payload:]
            self.pool_size = len(self._buffer)
            return payload
    
    async def reset(self) -> None:
        async with self._lock:
            self._buffer = bytearray()
            self.pool_size = 0
    
    def __len__(self) -> int:
        return self.pool_size


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
            self.xlog.debug("send_to_conn %d error: %r", conn_id, e)
            return False
    
    def status(self) -> str:
        out = "AsyncConnectionPipe:\n"
        out += f" running: {self.running}\n"
        out += f" connections: {list(self._conn_map.keys())}\n"
        out += f" tasks: {len(self._tasks)}\n"
        return out


class AsyncConn:
    def __init__(self, session: Any, conn_id: int, sock: socket.socket,
                 host: str, port: int, logger: Any) -> None:
        self.host = host
        self.port = port
        self.session = session
        self.conn_id = conn_id
        self.sock = sock
        self.xlog = logger
        
        self.running: bool = True
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._lock: asyncio.Lock = asyncio.Lock()
        
        self.send_buffer: bytearray = bytearray()
        self.received_position: int = 0
        self.remote_acked_position: int = 0
        self.sended_position: int = 0
        self.create_time = time.time()
        self.last_active = time.time()
        
        self._data_handler: Optional[callable] = None
    
    def set_data_handler(self, handler: callable) -> None:
        self._data_handler = handler
    
    async def on_data_received(self, data: bytes) -> None:
        self.last_active = time.time()
        async with self._lock:
            self.received_position += len(data)
        
        if self._data_handler:
            await self._data_handler(self.conn_id, data)
        else:
            await self.session.on_conn_data(self.conn_id, data)
    
    async def send(self, data: bytes) -> bool:
        if not self._writer or not self.running:
            return False
        
        try:
            self._writer.write(data)
            await self._writer.drain()
            async with self._lock:
                self.sended_position += len(data)
            return True
        except Exception as e:
            self.xlog.debug("AsyncConn %d send error: %r", self.conn_id, e)
            return False
    
    async def start(self) -> None:
        await self.session.connection_pipe.add_sock(self.sock, self)
    
    async def stop_async(self, reason: str = "") -> None:
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
        out += f" sent: {self.sended_position}\n"
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
                        self.xlog.warn("BlockReceivePool handler error: %r", e)
                self._pool[conn_id] = []
    
    async def reset(self) -> None:
        async with self._lock:
            self._pool = {}
    
    def status(self) -> str:
        return f"AsyncBlockReceivePool: {len(self._pool)} connections"