#!/usr/bin/env python3
# coding:utf-8
"""
Async IP Manager wrapper.
Wraps synchronous IpManagerBase with asyncio for gradual migration.
"""

from __future__ import annotations

import asyncio
from typing import Any, List, Optional

import async_loop


class AsyncIpManagerBase:
    def __init__(self, sync_manager) -> None:
        self._sync = sync_manager
        self._lock = asyncio.Lock()

    async def get_ip(self) -> Optional[str]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync.get_ip)

    async def get_good_ip(self) -> Optional[str]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync.get_good_ip)

    async def report_bad_ip(self, ip_str: str) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._sync.report_bad_ip(ip_str))

    async def report_good_ip(self, ip_str: str, rtt: float) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self._sync.report_good_ip(ip_str, rtt))

    async def stop(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._sync.stop)