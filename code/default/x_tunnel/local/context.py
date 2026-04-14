#!/usr/bin/env python3
# coding:utf-8
"""
XTunnelContext - Encapsulated global state for X-Tunnel module.

This class replaces the module-level globals pattern with a class instance,
providing better type safety and encapsulation while maintaining backward
compatibility through the global_var module.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field


@dataclass
class XTunnelStat:
    roundtrip_num: int = 0
    slow_roundtrip: int = 0
    timeout_roundtrip: int = 0
    resend: int = 0


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
        self.quota_list: Dict[str, Any] = field(default_factory=dict)
        self.quota: int = 0
        self.paypal_button_id: str = ""
        self.plans: Dict[str, Any] = field(default_factory=dict)

        self.server_host: str = ""
        self.server_port: int = 0
        self.selectable: List[Any] = field(default_factory=list)
        self.balance: float = 0.0
        self.openai_balance: float = 0.0
        self.openai_proxies: List[Any] = field(default_factory=list)
        self.tls_relays: Dict[str, Any] = field(default_factory=dict)

        self.stat: XTunnelStat = XTunnelStat()

    def reset_stat(self) -> None:
        self.stat.roundtrip_num = 0
        self.stat.slow_roundtrip = 0
        self.stat.timeout_roundtrip = 0
        self.stat.resend = 0

    def is_running(self) -> bool:
        return self.running