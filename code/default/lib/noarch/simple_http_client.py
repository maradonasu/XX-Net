#!/usr/bin/env python3
# coding:utf-8
"""Compatibility shim — re-exports from http_client and http_response_parser.

All high-level HTTP client functionality (Client, request) now lives in
http_client.py (backed by httpx).  Low-level socket response parsing
(Response, TxtResponse, Connection) lives in http_response_parser.py.
BaseResponse is defined in http_response_parser.py and re-exported by both.

Existing ``import simple_http_client`` and ``from simple_http_client import X``
continue to work unchanged.
"""

from http_client import Client, request  # noqa: F401
from http_response_parser import (  # noqa: F401
    BaseResponse,
    Connection,
    Response,
    TxtResponse,
)
