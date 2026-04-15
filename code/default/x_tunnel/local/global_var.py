#!/usr/bin/env python3
# coding:utf-8
"""
Backward-compatible global state module backed by XTunnelContext.

All attribute access is delegated to a singleton XTunnelContext instance.
Existing ``from . import global_var as g`` usage continues to work.

New code can import the context directly::

    from .context import ctx
"""

import sys
from .context import XTunnelContext


class _GlobalVarProxy:
    def __init__(self, ctx: XTunnelContext) -> None:
        self.__dict__['_ctx'] = ctx

    def __getattr__(self, name: str):
        return getattr(self._ctx, name)

    def __setattr__(self, name: str, value) -> None:
        setattr(self._ctx, name, value)

    def __delattr__(self, name: str) -> None:
        delattr(self._ctx, name)


ctx = XTunnelContext()
_proxy = _GlobalVarProxy(ctx)
sys.modules[__name__] = _proxy
