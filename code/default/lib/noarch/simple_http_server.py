#!/usr/bin/env python3
# coding:utf-8
"""
Compatibility shim for simple_http_server -> http_server migration.

This module imports from the new stdlib-based http_server module
to maintain backward compatibility with existing code.
"""

import sys
import os

_current_path = os.path.dirname(os.path.abspath(__file__))
if _current_path not in sys.path:
    sys.path.insert(0, _current_path)

from http_server import (
    GetReqTimeout,
    ParseReqFail,
    HttpServerHandler,
    HTTPServer,
    TestHttpServer,
    main,
)

__all__ = [
    'GetReqTimeout',
    'ParseReqFail',
    'HttpServerHandler',
    'HTTPServer',
    'TestHttpServer',
    'main',
]
