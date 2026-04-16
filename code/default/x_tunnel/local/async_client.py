#!/usr/bin/env python3
# coding:utf-8

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
import time
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
from async_socks5 import AsyncSocks5Handler, AsyncSocks5Server

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


class SessionProxyHandler(AsyncSocks5Handler):
    async def _handle_connect(self, host: str, port: int) -> None:
        if not g.session or not g.session.running:
            self.writer.write(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
            await self.writer.drain()
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
            self.writer.write(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
            await self.writer.drain()
            return

        if conn_id is None:
            local_sock.close()
            remote_sock.close()
            self.writer.write(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
            await self.writer.drain()
            return

        self.writer.write(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
        await self.writer.drain()

        await self._relay_via_socketpair(local_sock, conn_id)

    async def _handle_socks4_connect(self, host: str, port: int) -> None:
        if not g.session or not g.session.running:
            self.writer.write(b"\x00\x5b\x00\x00\x00\x00\x00\x00")
            await self.writer.drain()
            return

        loop = asyncio.get_event_loop()
        local_sock, remote_sock = socket.socketpair()

        try:
            conn_id = await loop.run_in_executor(
                None,
                functools.partial(g.session.create_conn, remote_sock, host, port, True)
            )
        except Exception as e:
            xlog.debug("socks4 create_conn failed: %r", e)
            local_sock.close()
            remote_sock.close()
            self.writer.write(b"\x00\x5b\x00\x00\x00\x00\x00\x00")
            await self.writer.drain()
            return

        if conn_id is None:
            local_sock.close()
            remote_sock.close()
            self.writer.write(b"\x00\x5b\x00\x00\x00\x00\x00\x00")
            await self.writer.drain()
            return

        self.writer.write(b"\x00\x5a\x00\x00\x00\x00\x00\x00")
        await self.writer.drain()

        await self._relay_via_socketpair(local_sock, conn_id)

    async def _relay_via_socketpair(self, local_sock: socket.socket, conn_id: int):
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
                    data = await self.reader.read(65536)
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
                    self.writer.write(data)
                    await self.writer.drain()
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


class SessionProxySocks5Server(AsyncSocks5Server):
    def __init__(self, host: str = "127.0.0.1", port: int = 1080) -> None:
        super().__init__(host, port)
        self._server: Optional[asyncio.AbstractServer] = None

    async def _handle_connection(self, reader: asyncio.StreamReader,
                                  writer: asyncio.StreamWriter) -> None:
        handler = SessionProxyHandler(reader, writer)
        await handler.handle()


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
            socks_server = SessionProxySocks5Server(host=listen_ips[0], port=port)
            await socks_server._start_async()
            bind_port = port
            break
        except Exception:
            continue

    if not socks_server:
        xlog.error("Failed to bind SOCKS5 server")
        return

    xlog.info("Async Socks5 server listen:%s:%d.", listen_ips, bind_port)
    g.bind_port = bind_port
    g.socks5_server = socks_server
    g.ready = True

    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        g.running = False
        await socks_server._stop_async()
        xlog.info("Async SOCKS5 server stopped")


def start(args):
    async_loop.start()
    loop = async_loop.get_loop()

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
