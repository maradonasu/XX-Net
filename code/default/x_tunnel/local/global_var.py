#!/usr/bin/env python3
# coding:utf-8
"""
Backward-compatible shim that re-exports the singleton proxy from context.py.

All attribute access is delegated to a single XTunnelContext instance.
Existing ``from . import global_var as g`` usage continues to work.
New code can import the proxy directly::

    from .context import ctx
"""

import sys
from .context import ctx, _context

sys.modules[__name__] = ctx
