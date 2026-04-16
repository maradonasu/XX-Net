#!/usr/bin/env python3
# coding:utf-8
"""
Async HTTP Client using httpx.AsyncClient.

Provides async request() interface compatible with simple_http_client.Client.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional, Union

import httpx
from log_buffer import getLogger
xlog = getLogger("async_http_client")

import async_loop


class AsyncResponse:
    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        self.status: int = response.status_code
        self.headers: Dict[str, str] = dict(response.headers)
        self._body: Optional[bytes] = None

    async def read(self) -> bytes:
        if self._body is None:
            self._body = self._response.content
        return self._body

    async def text(self) -> str:
        return self._response.text

    async def json(self) -> Any:
        return self._response.json()


class AsyncHttpClient:
    def __init__(self, timeout: int = 10, proxy: Optional[str] = None) -> None:
        self.timeout = timeout
        self.proxy = proxy
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            kwargs: Dict[str, Any] = {
                'timeout': self.timeout,
                'http2': True,
                'follow_redirects': True,
            }
            if self.proxy:
                kwargs['proxy'] = self.proxy
            self._client = httpx.AsyncClient(**kwargs)
        return self._client

    async def request(self, method: str, url: str, headers: Optional[Dict[str, str]] = None,
                      body: Optional[bytes] = None, **kwargs: Any) -> Optional[AsyncResponse]:
        try:
            client = await self._get_client()
            req_kwargs: Dict[str, Any] = {}
            if headers:
                req_kwargs['headers'] = headers
            if body:
                req_kwargs['content'] = body

            response = await client.request(method, url, **req_kwargs)
            return AsyncResponse(response)
        except Exception as e:
            xlog.warn("async request %s %s fail: %r", method, url, e)
            return None

    async def get(self, url: str, **kwargs: Any) -> Optional[AsyncResponse]:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, body: Optional[bytes] = None, **kwargs: Any) -> Optional[AsyncResponse]:
        return await self.request("POST", url, body=body, **kwargs)

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
