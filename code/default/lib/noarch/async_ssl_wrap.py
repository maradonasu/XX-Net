#!/usr/bin/env python3
# coding:utf-8
"""
Async SSL Connection using asyncio.open_connection(ssl=...).

Provides async equivalent of ssl_wrap.SSLConnection for
non-blocking TLS connections managed by the asyncio event loop.
"""

from __future__ import annotations

import asyncio
import ssl
from typing import Any, Callable, Optional, Tuple, Union

from xlog import getLogger
xlog = getLogger("async_ssl")

import async_loop


class AsyncSSLConnection:
    def __init__(self, host: str, port: int, sni: Optional[str] = None,
                 ssl_context: Optional[ssl.SSLContext] = None,
                 on_close: Optional[Callable] = None,
                 timeout: float = 10) -> None:
        self.host = host
        self.port = port
        self.sni = sni or host
        self.ssl_context = ssl_context
        self.on_close = on_close
        self.timeout = timeout
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self.connected = False
        self.peer_cert: Optional[dict] = None

    async def connect(self) -> None:
        ssl_ctx = self.ssl_context or ssl.create_default_context()
        server_name = self.sni or self.host

        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(
                self.host, self.port,
                ssl=ssl_ctx,
                server_hostname=server_name,
            ),
            timeout=self.timeout,
        )

        ssl_object = self._writer.get_extra_info('ssl_object')
        if ssl_object:
            der_cert = ssl_object.getpeercert(binary_form=True)
            if der_cert:
                self.peer_cert = ssl_object.getpeercert()

        self.connected = True

    async def send(self, data: bytes) -> int:
        if not self._writer:
            raise ConnectionError("not connected")
        self._writer.write(data)
        await self._writer.drain()
        return len(data)

    async def recv(self, size: int = 65536) -> bytes:
        if not self._reader:
            raise ConnectionError("not connected")
        return await self._reader.read(size)

    async def close(self, reason: str = "") -> None:
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self.connected = False
        if self.on_close:
            self.on_close(self.host, self.sni, reason=reason)

    def is_support_h2(self) -> bool:
        if not self._writer:
            return False
        ssl_object = self._writer.get_extra_info('ssl_object')
        if ssl_object:
            alpn = ssl_object.selected_alpn_protocol()
            return alpn == "h2"
        return False


async def async_connect_ssl(host: str, port: int, sni: Optional[str] = None,
                             ssl_context: Optional[ssl.SSLContext] = None,
                             timeout: float = 10) -> AsyncSSLConnection:
    conn = AsyncSSLConnection(host, port, sni, ssl_context, timeout=timeout)
    await conn.connect()
    return conn
