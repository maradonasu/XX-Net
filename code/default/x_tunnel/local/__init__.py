__all__ = ["local", "start"]

import os

_current_path = os.path.dirname(os.path.abspath(__file__))
_root_path = os.path.abspath(os.path.join(_current_path, os.pardir, os.pardir))
_noarch_lib = os.path.abspath(os.path.join(_root_path, 'lib', 'noarch'))

import sys
if _noarch_lib not in sys.path:
    sys.path.append(_noarch_lib)

from . import apis
from .context import ctx as _ctx

from . import async_client as _client_mod


def is_ready():
    return _ctx.ready


def start(args):
    _client_mod.start(args)


def stop():
    _client_mod.stop()
