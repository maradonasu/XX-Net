#!/usr/bin/env python3
# coding:utf-8
"""
XTunnelContext - Encapsulated global state for X-Tunnel module.

All module-level globals are now attributes of a single XTunnelContext instance.

Usage::

    from .context import ctx

The ``ctx`` proxy delegates every attribute access to the underlying
XTunnelContext singleton.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class XTunnelStat:
    __slots__ = ('roundtrip_num', 'slow_roundtrip', 'timeout_roundtrip', 'resend')

    def __init__(
        self,
        roundtrip_num: int = 0,
        slow_roundtrip: int = 0,
        timeout_roundtrip: int = 0,
        resend: int = 0,
    ) -> None:
        self.roundtrip_num = roundtrip_num
        self.slow_roundtrip = slow_roundtrip
        self.timeout_roundtrip = timeout_roundtrip
        self.resend = resend

    def __getitem__(self, key: str) -> int:
        return getattr(self, key)

    def __setitem__(self, key: str, value: int) -> None:
        setattr(self, key, value)

    def get(self, key: str, default: int = 0) -> int:
        return getattr(self, key, default)


class XTunnelContext:
    def __init__(self) -> None:
        self.xxnet_version: str = ""
        self.client_uuid: str = ""
        self.system: str = ""

        self.running: bool = True
        self.protocol_version: int = 4
        self.bind_port: int = 0
        self.last_refresh_time: float = 0.0
        self.login_process: bool = False
        self.data_path: Optional[str] = None

        self.config: Any = None
        self.http_client: Any = None
        self.cloudflare_front: Any = None
        self.cloudfront_front: Any = None
        self.tls_relay_front: Any = None
        self.seley_front: Any = None

        self.session: Any = None
        self.socks5_server: Any = None
        self.last_api_error: str = ""

        self.promote_code: str = ""
        self.promoter: str = ""
        self.quota_list: Dict[str, Any] = {}
        self.quota: int = 0
        self.paypal_button_id: str = ""
        self.plans: Dict[str, Any] = {}

        self.server_host: str = ""
        self.server_port: int = 0
        self.selectable: List[Any] = []
        self.balance: float = 0.0
        self.openai_balance: float = 0.0
        self.openai_proxies: List[Any] = []
        self.tls_relays: Dict[str, Any] = {}

        self.stat: XTunnelStat = XTunnelStat()

        self.ready: bool = False

        self.center_login_process: bool = False
        self.openai_proxy_host: Optional[str] = None
        self.openai_auth_str: Optional[str] = None
        self.workable_call_times: int = 0

        self.all_fronts: List[Any] = []
        self.light_fronts: List[Any] = []
        self.session_fronts: List[Any] = []
        self.statistic_thread: Optional[Any] = None
        self._front_initialized: bool = False
        self._statistic_running: bool = False
        self._front_fail_counts: Dict[str, int] = {}
        self._front_last_fail_time: Dict[str, float] = {}
        self._front_disabled: Dict[str, float] = {}
        self._front_success_counts: Dict[str, int] = {}

    def reset_stat(self) -> None:
        self.stat.roundtrip_num = 0
        self.stat.slow_roundtrip = 0
        self.stat.timeout_roundtrip = 0
        self.stat.resend = 0

    def is_running(self) -> bool:
        return self.running


class _GlobalVarProxy:
    def __init__(self, ctx: XTunnelContext) -> None:
        self.__dict__['_ctx'] = ctx

    def __getattr__(self, name: str):
        return getattr(self._ctx, name)

    def __setattr__(self, name: str, value) -> None:
        setattr(self._ctx, name, value)

    def __delattr__(self, name: str) -> None:
        delattr(self._ctx, name)


_context: XTunnelContext = XTunnelContext()
ctx: _GlobalVarProxy = _GlobalVarProxy(_context)
