#!/usr/bin/env python3
# coding:utf-8
"""
Async SOCKS5 Proxy Handler using asyncio streams.

Replaces proxy_handler.py's threading-based SOCKS5 handling with
asyncio-based implementation for better concurrency.
"""

from __future__ import annotations

import asyncio
import struct
from typing import Optional, Tuple

from xlog import getLogger
xlog = getLogger("async_socks5")

import async_loop


class AsyncSocks5Handler:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                 session_factory: Any = None) -> None:
        self.reader = reader
        self.writer = writer
        self.session_factory = session_factory
        self._buffer = b""

    async def handle(self) -> None:
        try:
            version = await self.reader.read(1)
            if not version:
                return

            if version == b"\x05":
                await self._handle_socks5()
            elif version == b"\x04":
                await self._handle_socks4()
            elif version in (b"C", b"G", b"P", b"D", b"O", b"H", b"T"):
                self._buffer = version
                await self._handle_http()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            xlog.debug("async socks5 handler error: %r", e)
        finally:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass

    async def _handle_socks5(self) -> None:
        auth_methods = await self.reader.read(1)
        if not auth_methods:
            return

        num_methods = auth_methods[0]
        methods = await self.reader.read(num_methods)

        self.writer.write(b"\x05\x00")
        await self.writer.drain()

        header = await self.reader.read(4)
        if len(header) < 4 or header[0] != 5:
            return

        cmd = header[1]
        atyp = header[3]

        if atyp == 1:
            addr_bytes = await self.reader.read(4)
            target_host = ".".join(str(b) for b in addr_bytes)
        elif atyp == 3:
            addr_len = await self.reader.read(1)
            addr_bytes = await self.reader.read(addr_len[0])
            target_host = addr_bytes.decode()
        elif atyp == 4:
            addr_bytes = await self.reader.read(16)
            import socket
            target_host = socket.inet_ntop(socket.AF_INET6, addr_bytes)
        else:
            return

        port_bytes = await self.reader.read(2)
        target_port = struct.unpack("!H", port_bytes)[0]

        if cmd == 1:
            await self._handle_connect(target_host, target_port)
        else:
            self.writer.write(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
            await self.writer.drain()

    async def _handle_connect(self, host: str, port: int) -> None:
        try:
            remote_reader, remote_writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=10
            )
        except Exception as e:
            xlog.debug("connect to %s:%d failed: %r", host, port, e)
            self.writer.write(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
            await self.writer.drain()
            return

        self.writer.write(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
        await self.writer.drain()

        await self._relay(remote_reader, remote_writer)

    async def _relay(self, remote_reader: asyncio.StreamReader,
                     remote_writer: asyncio.StreamWriter) -> None:
        async def _forward_local_to_remote():
            try:
                while True:
                    data = await self.reader.read(65536)
                    if not data:
                        break
                    remote_writer.write(data)
                    await remote_writer.drain()
            except Exception:
                pass
            finally:
                try:
                    remote_writer.close()
                    await remote_writer.wait_closed()
                except Exception:
                    pass

        async def _forward_remote_to_local():
            try:
                while True:
                    data = await remote_reader.read(65536)
                    if not data:
                        break
                    self.writer.write(data)
                    await self.writer.drain()
            except Exception:
                pass
            finally:
                try:
                    self.writer.close()
                    await self.writer.wait_closed()
                except Exception:
                    pass

        await asyncio.gather(
            _forward_local_to_remote(),
            _forward_remote_to_local(),
            return_exceptions=True,
        )

    async def _handle_socks4(self) -> None:
        header = await self.reader.read(7)
        if len(header) < 7:
            return

        port = struct.unpack("!H", header[0:2])[0]
        ip_bytes = header[2:6]

        while True:
            byte = await self.reader.read(1)
            if not byte or byte == b"\x00":
                break

        target_host = ".".join(str(b) for b in ip_bytes)

        try:
            remote_reader, remote_writer = await asyncio.wait_for(
                asyncio.open_connection(target_host, port), timeout=10
            )
            self.writer.write(b"\x00\x5a\x00\x00\x00\x00\x00\x00")
            await self.writer.drain()
            await self._relay(remote_reader, remote_writer)
        except Exception:
            self.writer.write(b"\x00\x5b\x00\x00\x00\x00\x00\x00")
            await self.writer.drain()

    async def _handle_http(self) -> None:
        while b"\r\n\r\n" not in self._buffer:
            chunk = await self.reader.read(4096)
            if not chunk:
                return
            self._buffer += chunk

        header_part = self._buffer.split(b"\r\n\r\n")[0]
        lines = header_part.split(b"\r\n")
        if not lines:
            return

        parts = lines[0].split(b" ")
        if len(parts) < 2:
            return

        method = parts[0]
        if method == b"CONNECT":
            host_port = parts[1]
            if b":" in host_port:
                host, port_str = host_port.rsplit(b":", 1)
                port = int(port_str)
            else:
                host = host_port
                port = 443

            try:
                remote_reader, remote_writer = await asyncio.wait_for(
                    asyncio.open_connection(host.decode(), port), timeout=10
                )
                self.writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await self.writer.drain()
                await self._relay(remote_reader, remote_writer)
            except Exception:
                self.writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                await self.writer.drain()
        else:
            url_str = parts[1].decode('iso-8859-1', errors='ignore')
            self.writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
            await self.writer.drain()


class AsyncSocks5Server:
    def __init__(self, host: str = "127.0.0.1", port: int = 1080,
                 session_factory: Any = None) -> None:
        self.host = host
        self.port = port
        self.session_factory = session_factory
        self._server: Optional[asyncio.AbstractServer] = None
        self.running = False

    async def _handle_connection(self, reader: asyncio.StreamReader,
                                  writer: asyncio.StreamWriter) -> None:
        handler = AsyncSocks5Handler(reader, writer, self.session_factory)
        await handler.handle()

    async def _start_async(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_connection, self.host, self.port
        )
        self.running = True
        xlog.info("async SOCKS5 server started on %s:%d", self.host, self.port)

    def start(self) -> int:
        async_loop.start()
        async_loop.run_async(self._start_async())
        return self.port

    async def _stop_async(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        self.running = False

    def stop(self) -> None:
        try:
            async_loop.run_async(self._stop_async(), timeout=5)
        except Exception:
            pass
        xlog.info("async SOCKS5 server stopped")
