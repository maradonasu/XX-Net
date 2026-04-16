#!/usr/bin/env python3
# coding:utf-8
"""
Async HTTP Dispatcher wrapper.
Wraps synchronous HttpsDispatcher with asyncio.run_in_executor for gradual migration.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from log_buffer import getLogger
xlog = getLogger("async_http_dispatcher")

import async_loop
from .http_dispatcher import HttpsDispatcher


class AsyncHttpsDispatcher:
    def __init__(self, logger, config, ip_manager, connection_manager,
                 http1worker=None, http2worker=None,
                 get_host_fn=None, get_path_fn=None) -> None:
        self._sync_dispatcher: Optional[HttpsDispatcher] = None
        self._init_args = (logger, config, ip_manager, connection_manager,
                          http1worker, http2worker, get_host_fn, get_path_fn)
        self._lock = asyncio.Lock()

    async def _get_dispatcher(self) -> HttpsDispatcher:
        if self._sync_dispatcher is None:
            async with self._lock:
                if self._sync_dispatcher is None:
                    loop = asyncio.get_event_loop()
                    self._sync_dispatcher = await loop.run_in_executor(
                        None,
                        lambda: HttpsDispatcher(*self._init_args)
                    )
        return self._sync_dispatcher

    async def request(self, method: str, host: str, path: str,
                      headers: Optional[Dict] = None,
                      payload: Optional[bytes] = None,
                      timeout: float = 30) -> Any:
        dispatcher = await self._get_dispatcher()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: dispatcher.request(method, host, path, headers, payload, timeout)
        )

    async def stop(self) -> None:
        if self._sync_dispatcher:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._sync_dispatcher.stop)
            self._sync_dispatcher = None