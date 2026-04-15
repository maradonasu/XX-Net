#!/usr/bin/env python3
# coding:utf-8
"""
Async Connect Creator using asyncio SSL connections.

Provides async equivalent of front_base.connect_creator.ConnectCreator.
"""

from __future__ import annotations

import ssl
from typing import Any, Callable, Optional

import async_ssl_wrap
from xlog import getLogger
xlog = getLogger("async_connect_creator")


class AsyncConnectCreator:
    def __init__(self, logger: Any, config: Any,
                 ssl_context: Optional[ssl.SSLContext] = None,
                 timeout: int = 5) -> None:
        self.logger = logger
        self.config = config
        self.ssl_context = ssl_context
        self.timeout = timeout

    async def connect_ssl(self, ip_str: str, sni: str, host: str) -> async_ssl_wrap.AsyncSSLConnection:
        import utils
        ip_str = utils.to_str(ip_str)
        ip, port = utils.get_ip_port(ip_str)
        ip = utils.to_str(ip)

        conn = await async_ssl_wrap.async_connect_ssl(
            host=ip, port=port, sni=sni,
            ssl_context=self.ssl_context,
            timeout=self.timeout,
        )

        conn.host = host
        conn.h2 = conn.is_support_h2()

        return conn
