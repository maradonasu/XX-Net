#!/usr/bin/env python3
# coding:utf-8
"""
Asyncio event loop manager for XX-Net.

Provides a dedicated asyncio event loop running in a background thread,
allowing gradual migration from threading-based to asyncio-based I/O.
"""

from __future__ import annotations

import asyncio
import functools
import threading
from typing import Any, Coroutine, Optional, TypeVar

T = TypeVar('T')

_loop: Optional[asyncio.AbstractEventLoop] = None
_thread: Optional[threading.Thread] = None
_running: bool = False


def get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None or _loop.is_closed() or not _loop.is_running():
        start()
    return _loop


def start() -> None:
    global _loop, _thread, _running
    if _running and _loop and not _loop.is_closed() and _loop.is_running():
        return

    if _loop and not _loop.is_closed():
        _loop.close()

    _loop = asyncio.new_event_loop()
    _running = True

    def _run_loop():
        asyncio.set_event_loop(_loop)
        _loop.run_forever()

    _thread = threading.Thread(target=_run_loop, name="asyncio_loop", daemon=True)
    _thread.start()


def stop() -> None:
    global _running
    _running = False
    if _loop and not _loop.is_closed():
        _loop.call_soon_threadsafe(_loop.stop)


def run_async(coro: Coroutine[Any, Any, T], timeout: Optional[float] = 30) -> T:
    loop = get_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


def run_async_no_wait(coro: Coroutine[Any, Any, Any]) -> None:
    loop = get_loop()
    asyncio.run_coroutine_threadsafe(coro, loop)


async def run_sync(func: Any, *args: Any, **kwargs: Any) -> Any:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))


def create_task(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    loop = get_loop()
    return loop.create_task(coro)
