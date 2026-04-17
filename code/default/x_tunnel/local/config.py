import sys
import os

from dataclasses import dataclass, field

import env_info

data_path = env_info.data_path
data_xtunnel_path = os.path.join(data_path, 'x_tunnel')

import config_manager
from log_buffer import getLogger

xlog = getLogger("x_tunnel")


@dataclass
class XTunnelConfig:
    log_level: str = "DEBUG"
    upload_logs: bool = True
    write_log_file: int = 0
    save_start_log: int = 1500
    show_debug: int = 0
    delay_collect_log: int = 3 * 60
    delay_collect_log2: int = 30

    encrypt_data: int = 0
    encrypt_password: str = "encrypt_pass"
    encrypt_method: str = "aes-256-cfb"

    api_server: str = "center.xx-net.org"
    scan_servers: list = field(default_factory=lambda: ["scan1"])
    server_host: str = ""
    server_port: int = 443
    use_https: int = 1
    port_range: int = 1

    login_account: str = ""
    login_password: str = ""

    conn_life: int = 30

    socks_host: str = "127.0.0.1"
    socks_port: int = 1080
    update_cloudflare_domains: bool = True

    concurent_thread_num: int = 12
    min_on_road: int = 2
    server_time_max_deviation: float = 0.6
    send_timeout_retry: int = 3
    server_download_timeout_retry: int = 3
    send_delay: int = 5
    resend_timeout: int = 3000
    ack_delay: int = 150
    max_payload: int = 256 * 1024
    roundtrip_timeout: int = 20
    network_timeout: int = 5
    windows_size: int = 10 * 1024 * 1024

    timeout_threshold: int = 2
    report_interval: int = 5 * 60

    enable_cloudflare: int = 1
    enable_cloudfront: int = 0
    enable_seley: int = 1
    enable_tls_relay: int = 1
    enable_direct: int = 0
    local_auto_front: int = 1
    check_local_network_rules: str = "normal"


def load_config():
    if len(sys.argv) > 2 and sys.argv[1] == "-f":
        path = sys.argv[2]
    else:
        path = os.path.join(data_xtunnel_path, 'client.json')

    xlog.info("use config_path:%s", path)

    config = config_manager.TypedConfig(XTunnelConfig, path)

    config.windows_ack = 0.05 * config.windows_size
    config.windows_size = config.max_payload * config.concurent_thread_num * 2
    xlog.info("X-Tunnel window:%d", config.windows_size)

    if config.local_auto_front:
        if "localhost" in config.server_host or "127.0.0.1" in config.server_host:
            config.enable_cloudflare = 0
            config.enable_tls_relay = 0
            config.enable_seley = 0
            config.enable_direct = 1
            xlog.info("Only enable Direct front for localhost")

    if config.write_log_file:
        xlog.log_to_file(os.path.join(data_path, "client.log"))

    xlog.setLevel(config.log_level)
    xlog.set_buffer(200)
    xlog.save_start_log = config.save_start_log
    return config
