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

from .context import ctx
from . import front_dispatcher
from . import config
from . import web_control
from .async_proxy_session import AsyncProxySession, async_login_process, async_create_conn


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
        if not ctx.session:
            xlog.debug("_handle_connect: no session")
            self.writer.write(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
            await self.writer.drain()
            return

        await async_login_process()
        
        if not ctx.session.running:
            xlog.warn("_handle_connect: session not running")
            self.writer.write(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
            await self.writer.drain()
            return
        
        local_sock, remote_sock = socket.socketpair()
        
        try:
            conn_id = await ctx.session.create_conn(remote_sock, host, port, True)
        except Exception as e:
            xlog.debug("create_conn failed: %r", e)
            local_sock.close()
            remote_sock.close()
            self.writer.write(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
            await self.writer.drain()
            return
        
        if conn_id is None:
            xlog.debug("_handle_connect: conn_id is None")
            local_sock.close()
            remote_sock.close()
            self.writer.write(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
            await self.writer.drain()
            return
        
        self.writer.write(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
        await self.writer.drain()
        
        conn = ctx.session.conn_list.get(conn_id)
        await self._start_relay_and_conn(local_sock, conn)

    async def _start_relay_and_conn(self, local_sock: socket.socket, conn: Any) -> None:
        loop = asyncio.get_event_loop()
        local_sock.setblocking(False)
        
        _local_reader = asyncio.StreamReader()
        
        def protocol_factory():
            return asyncio.StreamReaderProtocol(_local_reader)
        
        try:
            transport, protocol = await loop.connect_accepted_socket(
                protocol_factory,
                sock=local_sock,
            )
        except Exception as e:
            xlog.exception("_start_relay_and_conn: connect_accepted_socket failed: %r", e)
            return
        
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
        
        if conn:
            if hasattr(conn, 'transferred_close_to_peer') and not conn.transferred_close_to_peer:
                if hasattr(conn, 'transfer_peer_close'):
                    await conn.transfer_peer_close("relay_end")
            if hasattr(conn, 'stop_async'):
                await conn.stop_async("relay_end")
            elif hasattr(conn, 'stop'):
                await loop.run_in_executor(None, conn.stop)

    async def _handle_socks4_connect(self, host: str, port: int) -> None:
        if not ctx.session:
            self.writer.write(b"\x00\x5b\x00\x00\x00\x00\x00\x00")
            await self.writer.drain()
            return

        await async_login_process()
        
        if not ctx.session.running:
            self.writer.write(b"\x00\x5b\x00\x00\x00\x00\x00\x00")
            await self.writer.drain()
            return
        
        local_sock, remote_sock = socket.socketpair()
        
        try:
            conn_id = await ctx.session.create_conn(remote_sock, host, port, True)
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
        
        conn = ctx.session.conn_list.get(conn_id)
        
        self.writer.write(b"\x00\x5a\x00\x00\x00\x00\x00\x00")
        await self.writer.drain()
        
        await self._start_relay_and_conn(local_sock, conn)


class _HandlerCompat:
    handle_num: int = 0


class SessionProxySocks5Server(AsyncSocks5Server):
    def __init__(self, host: str = "127.0.0.1", port: int = 1080) -> None:
        super().__init__(host, port)
        self._server: Optional[asyncio.AbstractServer] = None
        self.handler = _HandlerCompat()

    async def _handle_connection(self, reader: asyncio.StreamReader,
                                  writer: asyncio.StreamWriter) -> None:
        handler = SessionProxyHandler(reader, writer)
        await handler.handle()


async def _async_main(config_args):
    loop = asyncio.get_event_loop()

    def _exception_handler(loop, context):
        exception = context.get('exception')
        if isinstance(exception, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return
        if exception and isinstance(exception, OSError) and exception.winerror in (10054, 10053, 10038):
            return
        loop.default_exception_handler(context)

    loop.set_exception_handler(_exception_handler)

    ctx.xxnet_version = xxnet_version()
    ctx.client_uuid = get_launcher_uuid()
    ctx.system = os_platform.platform + "|" + platform.version() + "|" + str(platform.architecture()) + "|" + sys.version

    ctx.config = config.load_config()

    await loop.run_in_executor(None, front_dispatcher.init)

    ctx.data_path = data_path
    xlog.info("version:%s", ctx.xxnet_version)

    ctx.running = True
    if not ctx.server_host or not ctx.server_port:
        if ctx.config.server_host and ctx.config.server_port == 443:
            xlog.info("Session Server:%s:%d", ctx.config.server_host, ctx.config.server_port)
            ctx.server_host = ctx.config.server_host
            ctx.server_port = ctx.config.server_port
            ctx.balance = 99999999
        elif ctx.config.api_server:
            pass
        else:
            xlog.debug("please check x-tunnel server in config")

    ctx.http_client = front_dispatcher

    xlog.info("Using AsyncProxySession")
    ctx.session = AsyncProxySession()
    await ctx.session.start()

    socks_port = config_args.get("socks_port", ctx.config.socks_port)
    allow_remote = config_args.get("allow_remote", 0)

    listen_ips = ctx.config.socks_host
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
    ctx.bind_port = bind_port
    ctx.socks5_server = socks_server
    ctx.ready = True
    xlog.debug("_async_main: entering wait loop, ctx.running=%s", ctx.running)

    try:
        while ctx.running:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        xlog.warn("_async_main: CancelledError received!")
    except Exception as e:
        xlog.exception("_async_main: unexpected exception: %r", e)
    finally:
        xlog.debug("_async_main: exiting, ctx.running=%s", ctx.running)
        ctx.running = False
        await socks_server._stop_async()
        if ctx.session:
            if isinstance(ctx.session, AsyncProxySession):
                await ctx.session.stop()
            else:
                ctx.session.stop()
        xlog.info("Async SOCKS5 server stopped")


def start(args):
    async_loop.start()
    loop = async_loop.get_loop()

    try:
        asyncio.run_coroutine_threadsafe(_async_main(args), loop)

        for _ in range(300):
            if ctx.ready:
                break
            time.sleep(0.1)

        while getattr(ctx, 'running', False):
            time.sleep(1)
    except KeyboardInterrupt:
        stop()


def stop():
    ctx.running = False

    if hasattr(ctx, 'http_client') and ctx.http_client:
        try:
            ctx.http_client.stop()
        except Exception:
            pass

    try:
        front_dispatcher.stop()
    except Exception:
        pass

    if ctx.session:
        xlog.info("Stopping session")
        if isinstance(ctx.session, AsyncProxySession):
            loop = async_loop.get_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(ctx.session.stop(), loop)
        else:
            ctx.session.stop()
        ctx.session = None

    async_loop.stop()
    ctx.ready = False


if __name__ == '__main__':
    try:
        start({})
    except KeyboardInterrupt:
        stop()
        sys.exit()