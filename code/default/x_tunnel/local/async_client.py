#!/usr/bin/env python3
# coding:utf-8
"""
Async X-Tunnel Client.

Replaces the threading-based client.py with an asyncio-based implementation.
Uses async_socks5 for SOCKS5 server, wraps proxy_session in executor threads
for safe migration.
"""

from __future__ import annotations

import asyncio
import functools
import json
import os
import platform
import socket
import struct
import sys
import threading
from typing import Any, Dict, Optional

current_path = os.path.dirname(os.path.abspath(__file__))
python_path = os.path.abspath(os.path.join(current_path, os.pardir, os.pardir))

noarch_lib = os.path.abspath(os.path.join(python_path, 'lib', 'noarch'))
sys.path.append(noarch_lib)

root_path = os.path.abspath(os.path.join(current_path, os.pardir, os.pardir))
sys.path.append(root_path)

import env_info
data_path = env_info.data_path
data_xtunnel_path = os.path.join(data_path, 'x_tunnel')

lib_path = os.path.abspath(os.path.join(current_path, os.pardir, 'common'))
sys.path.append(lib_path)

from log_buffer import getLogger
xlog = getLogger("x_tunnel", log_path=data_xtunnel_path, save_start_log=1500, save_warning_log=True)

import os_platform
import async_loop
import async_socks5
from async_http_server import AsyncHTTPServer
from async_http_client import AsyncHttpClient

from . import global_var as g
from . import proxy_session
from . import front_dispatcher
from . import config
from . import web_control


def create_data_path():
    if not os.path.isdir(data_path):
        os.mkdir(data_path)
    if not os.path.isdir(data_xtunnel_path):
        os.mkdir(data_xtunnel_path)


create_data_path()


def xxnet_version():
    version_file = os.path.join(root_path, "version.txt")
    try:
        with open(version_file, "r") as fd:
            version = fd.read()
        return version
    except Exception as e:
        xlog.exception("get version fail")
    return "get_version_fail"


def get_launcher_uuid():
    launcher_config_fn = os.path.join(data_path, "launcher", "config.json")
    try:
        with open(launcher_config_fn, "r", encoding='utf-8') as fd:
            info = json.load(fd)
            return info.get("update_uuid")
    except Exception as e:
        xlog.exception("get_launcher_uuid except:%r", e)
        return ""


async def _async_socks5_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    loop = asyncio.get_event_loop()

    try:
        version = await asyncio.wait_for(reader.read(1), timeout=30)
        if not version:
            writer.close()
            await writer.wait_closed()
            return

        if version == b"\x05":
            await _handle_socks5(reader, writer)
        elif version == b"\x04":
            await _handle_socks4(reader, writer)
        elif version in (b"C", b"G", b"P", b"D", b"O", b"H", b"T"):
            await _handle_http_connect(reader, writer, version)
        else:
            xlog.debug("unknown protocol: %s", version)
    except asyncio.TimeoutError:
        pass
    except Exception as e:
        xlog.debug("async socks5 handler error: %r", e)
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def _handle_socks5(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    num_methods = (await reader.read(1))[0]
    await reader.read(num_methods)

    writer.write(b"\x05\x00")
    await writer.drain()

    header = await reader.read(4)
    if len(header) < 4 or header[0] != 5:
        return

    cmd = header[1]
    atyp = header[3]

    if atyp == 1:
        addr_bytes = await reader.read(4)
        target_host = ".".join(str(b) for b in addr_bytes)
    elif atyp == 3:
        addr_len = (await reader.read(1))[0]
        target_host = (await reader.read(addr_len)).decode()
    elif atyp == 4:
        addr_bytes = await reader.read(16)
        target_host = socket.inet_ntop(socket.AF_INET6, addr_bytes)
    else:
        return

    port_bytes = await reader.read(2)
    target_port = struct.unpack("!H", port_bytes)[0]

    if cmd == 1:
        await _proxy_via_session(reader, writer, target_host, target_port)
    else:
        writer.write(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
        await writer.drain()


async def _handle_socks4(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    header = await reader.read(7)
    if len(header) < 7:
        return

    port = struct.unpack("!H", header[0:2])[0]
    ip_bytes = header[2:6]

    while True:
        byte = await reader.read(1)
        if not byte or byte == b"\x00":
            break

    target_host = ".".join(str(b) for b in ip_bytes)
    await _proxy_via_session(reader, writer, target_host, port, socks4=True)


async def _handle_http_connect(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, first_byte: bytes):
    buf = first_byte
    while b"\r\n\r\n" not in buf:
        chunk = await reader.read(4096)
        if not chunk:
            return
        buf += chunk

    header_part = buf.split(b"\r\n\r\n")[0]
    lines = header_part.split(b"\r\n")
    if not lines:
        return

    parts = lines[0].split(b" ")
    if len(parts) < 2:
        return

    method = parts[0]
    if method == b"CONNECT":
        host_port = parts[1]
        if b":" in host_port:
            host, port_str = host_port.rsplit(b":", 1)
            port = int(port_str)
        else:
            host = host_port
            port = 443
        await _proxy_via_session(reader, writer, host.decode(), port)
    else:
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
        await writer.drain()


async def _proxy_via_session(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                              host: str, port: int, socks4: bool = False):
    if not g.session or not g.session.running:
        status = b"\x00\x5b" if socks4 else b"\x05\x05"
        writer.write(status + b"\x00\x01\x00\x00\x00\x00\x00\x00")
        await writer.drain()
        return

    loop = asyncio.get_event_loop()

    local_sock, remote_sock = socket.socketpair()

    try:
        conn_id = await loop.run_in_executor(
            None,
            functools.partial(g.session.create_conn, remote_sock, host, port, True)
        )
    except Exception as e:
        xlog.debug("create_conn failed: %r", e)
        local_sock.close()
        remote_sock.close()
        status = b"\x00\x5b" if socks4 else b"\x05\x05"
        writer.write(status + b"\x00\x01\x00\x00\x00\x00\x00\x00")
        await writer.drain()
        return

    if conn_id is None:
        local_sock.close()
        remote_sock.close()
        status = b"\x00\x5b" if socks4 else b"\x05\x05"
        writer.write(status + b"\x00\x01\x00\x00\x00\x00\x00\x00")
        await writer.drain()
        return

    if socks4:
        writer.write(b"\x00\x5a\x00\x00\x00\x00\x00\x00")
    else:
        writer.write(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
    await writer.drain()

    await _relay_async_to_sync(reader, writer, local_sock, conn_id)


async def _relay_async_to_sync(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                                local_sock, conn_id: int):
    loop = asyncio.get_event_loop()

    local_sock.setblocking(False)

    transport, protocol = await loop.connect_accepted_connection(
        asyncio.StreamReaderProtocol,
        asyncio.StreamReader(),
        sock=local_sock,
    )
    _local_reader = protocol._reader
    _local_writer = asyncio.StreamWriter(transport, protocol, _local_reader, loop)

    async def _client_to_session():
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                _local_writer.write(data)
                await _local_writer.drain()
        except Exception:
            pass
        finally:
            try:
                _local_writer.close()
                await _local_writer.wait_closed()
            except Exception:
                pass

    async def _session_to_client():
        try:
            while True:
                data = await _local_reader.read(65536)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except Exception:
            pass

    await asyncio.gather(
        _client_to_session(),
        _session_to_client(),
        return_exceptions=True,
    )

    if conn_id in g.session.conn_list:
        conn = g.session.conn_list.get(conn_id)
        if conn:
            await loop.run_in_executor(None, conn.stop)


async def _run_socks5_server(hosts, port):
    server = await asyncio.start_server(_async_socks5_handler, hosts, port)
    addr = server.sockets[0].getsockname()
    xlog.info("async SOCKS5 server listening on %s:%d", addr[0], addr[1])
    return server


async def _async_main(config_args):
    loop = asyncio.get_event_loop()

    g.xxnet_version = xxnet_version()
    g.client_uuid = get_launcher_uuid()
    g.system = os_platform.platform + "|" + platform.version() + "|" + str(platform.architecture()) + "|" + sys.version

    g.config = config.load_config()

    await loop.run_in_executor(None, front_dispatcher.init)

    g.data_path = data_path
    xlog.info("version:%s", g.xxnet_version)

    g.running = True
    if not g.server_host or not g.server_port:
        if g.config.server_host and g.config.server_port == 443:
            xlog.info("Session Server:%s:%d", g.config.server_host, g.config.server_port)
            g.server_host = g.config.server_host
            g.server_port = g.config.server_port
            g.balance = 99999999
        elif g.config.api_server:
            pass
        else:
            xlog.debug("please check x-tunnel server in config")

    g.http_client = front_dispatcher

    g.session = await loop.run_in_executor(None, proxy_session.ProxySession)

    socks_port = config_args.get("socks_port", g.config.socks_port)
    allow_remote = config_args.get("allow_remote", 0)

    listen_ips = g.config.socks_host
    if isinstance(listen_ips, str):
        listen_ips = [listen_ips]
    else:
        listen_ips = list(listen_ips)

    if allow_remote and ("0.0.0.0" not in listen_ips or "::" not in listen_ips):
        listen_ips = ["0.0.0.0"]

    socks_server = None
    bind_port = socks_port

    for port in range(socks_port, socks_port + 2000):
        try:
            socks_server = await _run_socks5_server(listen_ips, port)
            bind_port = port
            break
        except Exception:
            continue

    if not socks_server:
        xlog.error("Failed to bind SOCKS5 server")
        return

    xlog.info("Async Socks5 server listen:%s:%d.", listen_ips, bind_port)
    g.bind_port = bind_port
    g.ready = True

    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        g.running = False
        socks_server.close()
        await socks_server.wait_closed()
        xlog.info("Async SOCKS5 server stopped")


def start(args):
    async_loop.start()
    loop = async_loop.get_loop()

    import time

    try:
        asyncio.run_coroutine_threadsafe(_async_main(args), loop)

        for _ in range(300):
            if g.ready:
                break
            time.sleep(0.1)

        while getattr(g, 'running', False):
            time.sleep(1)
    except KeyboardInterrupt:
        stop()


def stop():
    g.running = False

    if hasattr(g, 'http_client') and g.http_client:
        try:
            g.http_client.stop()
        except Exception:
            pass

    try:
        front_dispatcher.stop()
    except Exception:
        pass

    if g.session:
        xlog.info("Stopping session")
        g.session.stop()
        g.session = None

    async_loop.stop()
    g.ready = False


if __name__ == '__main__':
    try:
        start({})
    except KeyboardInterrupt:
        stop()
        sys.exit()
