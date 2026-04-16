#!/usr/bin/env python3
# coding:utf-8
"""
Async DNS resolver using asyncio built-in DNS.
"""

from __future__ import annotations

import asyncio
import socket
from typing import List, Optional, Tuple

from log_buffer import getLogger
xlog = getLogger("async_dns")


class AsyncDNSResolver:
    def __init__(self) -> None:
        self._cache: dict = {}
        self._cache_lock = asyncio.Lock()

    async def resolve_ipv4(self, hostname: str) -> Optional[str]:
        try:
            loop = asyncio.get_running_loop()
            results = await loop.getaddrinfo(hostname, 0, family=socket.AF_INET, type=socket.SOCK_STREAM)
            if results:
                return results[0][4][0]
            return None
        except socket.gaierror as e:
            xlog.debug("DNS resolve %s failed: %r", hostname, e)
            return None

    async def resolve_ipv6(self, hostname: str) -> Optional[str]:
        try:
            loop = asyncio.get_running_loop()
            results = await loop.getaddrinfo(hostname, 0, family=socket.AF_INET6, type=socket.SOCK_STREAM)
            if results:
                return results[0][4][0]
            return None
        except socket.gaierror as e:
            xlog.debug("DNS resolve IPv6 %s failed: %r", hostname, e)
            return None

    async def resolve_all(self, hostname: str) -> Tuple[List[str], List[str]]:
        ipv4, ipv6 = await asyncio.gather(
            self.resolve_ipv4(hostname),
            self.resolve_ipv6(hostname),
            return_exceptions=True
        )
        ipv4_list = [ipv4] if ipv4 and not isinstance(ipv4, Exception) else []
        ipv6_list = [ipv6] if ipv6 and not isinstance(ipv6, Exception) else []
        return ipv4_list, ipv6_list


_resolver: Optional[AsyncDNSResolver] = None


def get_resolver() -> AsyncDNSResolver:
    global _resolver
    if _resolver is None:
        _resolver = AsyncDNSResolver()
    return _resolver


async def resolve(hostname: str) -> Optional[str]:
    return await get_resolver().resolve_ipv4(hostname)