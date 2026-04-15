#!/usr/bin/env python3
# coding:utf-8
"""
Async HTTP Server using aiohttp.

Drop-in replacement for http_server.HTTPServer that uses asyncio/aiohttp
internally while exposing the same interface. Allows handlers to be
either sync or async callables.

Usage:
    from async_http_server import AsyncHTTPServer

    server = AsyncHTTPServer(('127.0.0.1', 8080), my_handler, args=my_args)
    server.start()
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, parse_qs

from aiohttp import web

import utils
from xlog import getLogger
xlog = getLogger("async_http_server")

import async_loop


class AsyncWebRequest:
    def __init__(self, request: web.Request, args: Any) -> None:
        self.request = request
        self.args = args
        self.method: str = request.method
        self.path: str = request.path
        self.query: Dict[str, str] = dict(request.query)
        self.headers: Dict[str, str] = dict(request.headers)
        self._body: Optional[bytes] = None

    async def body(self) -> bytes:
        if self._body is None:
            self._body = await self.request.read()
        return self._body

    async def json(self) -> Any:
        raw = await self.body()
        return json.loads(raw)


class AsyncWebResponse:
    def __init__(self) -> None:
        self.status: int = 200
        self.headers: Dict[str, str] = {}
        self.body: bytes = b""
        self.content_type: str = "text/plain"

    def set_status(self, status: int) -> None:
        self.status = status

    def set_header(self, key: str, value: str) -> None:
        self.headers[key] = value

    def set_body(self, data: Union[str, bytes], content_type: str = "text/plain") -> None:
        if isinstance(data, str):
            data = data.encode('utf-8')
        self.body = data
        self.content_type = content_type

    def set_json(self, obj: Any) -> None:
        self.body = json.dumps(obj, indent=0, sort_keys=True).encode('utf-8')
        self.content_type = "application/json"

    def set_redirect(self, url: str, status: int = 307) -> None:
        self.status = status
        self.headers["Location"] = url


class AsyncHTTPServer:
    def __init__(self, addresses: Union[Tuple[Union[str, bytes], int], List[Tuple[Union[str, bytes], int]]],
                 handler: Callable, args: Any = (), use_https: bool = False,
                 cert: str = "", logger: Any = xlog, max_thread: int = 1024,
                 check_listen_interval: Optional[float] = None) -> None:
        if isinstance(addresses, tuple):
            addresses = [addresses]

        self.addresses = []
        for addr in addresses:
            ip, port = addr
            if isinstance(ip, bytes):
                ip = ip.decode('ascii', errors='ignore')
            self.addresses.append((ip, port))

        self.handler = handler
        self.logger = logger
        self.args = args
        self.use_https = use_https
        self.cert = cert
        self.max_thread = max_thread
        self.running = False
        self.sites: List[web.TCPSite] = []
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None

    async def _handle_request(self, request: web.Request) -> web.Response:
        req = AsyncWebRequest(request, self.args)
        resp = AsyncWebResponse()

        try:
            result = self.handler(req, resp)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            self.logger.exception("handler error: %r", e)
            return web.Response(status=500, text="Internal Server Error")

        response = web.Response(
            status=resp.status,
            body=resp.body,
            content_type=resp.content_type,
        )
        for key, value in resp.headers.items():
            response.headers[key] = value
        return response

    def init_socket(self) -> None:
        self._app = web.Application()
        self._app.router.add_route('*', '/{path:.*}', self._handle_request)
        self._app.router.add_route('*', '/', self._handle_request)
        self.logger.info("AsyncHTTPServer initialized for %s", self.addresses)

    def start(self) -> None:
        if not self._app:
            self.init_socket()

        async_loop.start()

        async def _start_server():
            self._runner = web.AppRunner(self._app)
            await self._runner.setup()
            for addr in self.addresses:
                site = web.TCPSite(self._runner, addr[0], addr[1])
                await site.start()
                self.sites.append(site)
                self.logger.info("async server %s:%d started.", addr[0], addr[1])

        async_loop.run_async(_start_server())
        self.running = True

    def serve_forever(self) -> None:
        self.start()
        while self.running:
            import time
            time.sleep(1)

    def shutdown(self) -> None:
        self.running = False

        async def _cleanup():
            if self._runner:
                await self._runner.cleanup()

        try:
            async_loop.run_async(_cleanup(), timeout=5)
        except Exception:
            pass
        self.sites = []
        self.logger.info("async shutdown")

    def server_close(self) -> None:
        self.shutdown()
