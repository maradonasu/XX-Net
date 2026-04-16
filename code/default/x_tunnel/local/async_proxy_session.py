#!/usr/bin/env python3
# coding:utf-8
"""
Async Proxy Session for X-Tunnel.
Fully async version of ProxySession using asyncio.
"""

from __future__ import annotations

import asyncio
import json
import time
import xstruct as struct
from typing import Any, Dict, List, Optional, Tuple, Union

from log_buffer import getLogger, keep_log
xlog = getLogger("x_tunnel")

import utils
from . import global_var as g
from .async_base_container import (
    AsyncWaitQueue, AsyncSendBuffer, AsyncConnectionPipe, 
    AsyncConn, AsyncBlockReceivePool
)


def traffic_readable(num: float, units: Tuple[str, str, str, str] = ('B', 'KB', 'MB', 'GB')) -> str:
    for unit in units:
        if num >= 1024:
            num /= 1024.0
        else:
            break
    return '{:.1f} {}'.format(num, unit)


class AsyncProxySession:
    def __init__(self) -> None:
        self.config = g.config
        
        max_payload = 65536
        if self.config and hasattr(self.config, 'max_payload'):
            max_payload = self.config.max_payload
        
        self.wait_queue = AsyncWaitQueue()
        self.send_buffer = AsyncSendBuffer(max_payload=max_payload)
        self.connection_pipe = AsyncConnectionPipe(self, xlog)
        self.lock: asyncio.Lock = asyncio.Lock()
        
        self.running: bool = False
        self._tasks: List[asyncio.Task] = []
        self.session_id: bytes = utils.to_bytes(utils.generate_random_lowercase(8))
        self.conn_list: Dict[int, AsyncConn] = {}
        self.last_conn_id: int = 0
        self.last_transfer_no: int = 0
        
        self.wait_ack_send_list: Dict[int, Tuple[bytes, float]] = {}
        self.transfer_list: Dict[int, Dict[str, Any]] = {}
        self.received_sn: List[int] = []
        self.receive_next_sn: int = 1
        
        self.traffic_upload: int = 0
        self.traffic_download: int = 0
        self.last_traffic_upload: int = 0
        self.last_traffic_download: int = 0
        self.last_traffic_reset_time: float = time.time()
        self.upload_speed: float = 0.0
        self.download_speed: float = 0.0
        
        self.last_send_time: float = 0
        self.last_receive_time: float = 0
        self.server_time_offset: float = 0
        self.server_time_deviation: float = 9999
        self.target_on_roads: int = 0
        self.on_road_num: int = 0
    
    async def start(self) -> bool:
        async with self.lock:
            if self.running:
                xlog.warn("AsyncProxySession try to start but already running")
                return True
            
            self.session_id = utils.to_bytes(utils.generate_random_lowercase(8))
            self.last_conn_id = 0
            self.last_transfer_no = 0
            self.conn_list = {}
            self.transfer_list = {}
            self.wait_ack_send_list = {}
            self.received_sn = []
            self.receive_next_sn = 1
            self.last_send_time = time.time()
            self.last_receive_time = 0
            
            self.traffic_upload = 0
            self.traffic_download = 0
            self.last_traffic_upload = 0
            self.last_traffic_download = 0
            self.last_traffic_reset_time = time.time()
            
            if not await self.login_session():
                xlog.warn("AsyncProxySession login failed")
                return False
            
            self.running = True
            
            for i in range(g.config.concurent_thread_num):
                task = asyncio.create_task(self.round_trip_worker(i), name=f"roundtrip_{i}")
                self._tasks.append(task)
            
            task = asyncio.create_task(self.timeout_checker(), name="timeout_checker")
            self._tasks.append(task)
            
            await self.connection_pipe.start()
            xlog.info("AsyncProxySession started")
            return True
    
    async def stop(self) -> None:
        if not self.running:
            return
        
        self.running = False
        self.wait_queue.stop()
        
        async with self.lock:
            for task in self._tasks:
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=1)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass
            self._tasks.clear()
            
            await self.close_all_connections()
            await self.send_buffer.reset()
            await self.connection_pipe.stop()
        
        xlog.info("AsyncProxySession stopped")
    
    async def round_trip_worker(self, worker_id: int) -> None:
        xlog.debug("round_trip_worker %d started", worker_id)
        try:
            while self.running:
                await self.wait_queue.wait(timeout=1)
                if not self.running:
                    break
                
                payload = await self.send_buffer.get_payload()
                if payload:
                    await self._send_round_trip(payload, worker_id)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            xlog.exception("round_trip_worker %d error: %r", worker_id, e)
    
    async def _send_round_trip(self, payload: bytes, worker_id: int) -> None:
        transfer_no = self.last_transfer_no + 1
        self.last_transfer_no = transfer_no
        
        start_time = time.time()
        
        async with self.lock:
            self.transfer_list[transfer_no] = {
                "stat": "sending",
                "start_time": start_time,
                "server_timeout": g.config.send_timeout,
                "retry": 0,
                "payload": payload,
                "worker_id": worker_id,
            }
            self.on_road_num += 1
        
        try:
            content, status = await self._http_request(payload)
            
            async with self.lock:
                if transfer_no not in self.transfer_list:
                    return
                
                self.transfer_list[transfer_no]["stat"] = "done"
                self.on_road_num -= 1
            
            if status == 200 and content:
                await self._process_response(content)
                self.last_receive_time = time.time()
            else:
                xlog.debug("_send_round_trip %d status: %d", transfer_no, status)
                
        except Exception as e:
            xlog.debug("_send_round_trip %d error: %r", transfer_no, e)
            async with self.lock:
                if transfer_no in self.transfer_list:
                    self.transfer_list[transfer_no]["stat"] = "failed"
                    self.on_road_num -= 1
    
    async def _http_request(self, payload: bytes) -> Tuple[Optional[bytes], int]:
        if not g.server_host:
            return None, 0
        
        try:
            magic = b"P"
            pack_type = 2
            head = struct.pack("<cBB8sIH", magic, g.protocol_version, pack_type,
                              self.session_id, len(payload), transfer_no)
            
            data = head + payload
            
            loop = asyncio.get_event_loop()
            content, status, response = await loop.run_in_executor(
                None,
                lambda: g.http_client.request(
                    method="POST",
                    host=g.server_host,
                    path="/data",
                    data=data,
                    timeout=g.config.network_timeout
                )
            )
            
            return content, status
        except Exception as e:
            xlog.debug("_http_request error: %r", e)
            return None, 0
    
    async def _process_response(self, content: bytes) -> None:
        if len(content) < 6:
            return
        
        try:
            pos = 0
            magic = content[pos:pos+1]
            pos += 1
            
            if magic != b"P":
                return
            
            protocol_version = content[pos]
            pos += 1
            
            pack_type = content[pos]
            pos += 1
            
            if pack_type == 2:
                await self._process_data_pack(content, pos)
            elif pack_type == 3:
                await self._process_ack_pack(content, pos)
        except Exception as e:
            xlog.debug("_process_response error: %r", e)
    
    async def _process_data_pack(self, content: bytes, pos: int) -> None:
        try:
            session_id = content[pos:pos+8]
            pos += 8
            
            sn_len = struct.unpack("<H", content[pos:pos+2])[0]
            pos += 2
            
            sn_list = []
            for i in range(sn_len):
                sn = struct.unpack("<I", content[pos:pos+4])[0]
                pos += 4
                sn_list.append(sn)
            
            payload_len = struct.unpack("<I", content[pos:pos+4])[0]
            pos += 4
            
            payload = content[pos:pos+payload_len]
            
            await self._dispatch_payload(payload)
        except Exception as e:
            xlog.debug("_process_data_pack error: %r", e)
    
    async def _dispatch_payload(self, payload: bytes) -> None:
        if len(payload) < 4:
            return
        
        try:
            pos = 0
            while pos < len(payload):
                conn_id = struct.unpack("<H", payload[pos:pos+2])[0]
                pos += 2
                
                data_len = struct.unpack("<H", payload[pos:pos+2])[0]
                pos += 2
                
                data = payload[pos:pos+data_len]
                pos += data_len
                
                await self.on_conn_data(conn_id, data)
        except Exception as e:
            xlog.debug("_dispatch_payload error: %r", e)
    
    async def _process_ack_pack(self, content: bytes, pos: int) -> None:
        pass
    
    async def timeout_checker(self) -> None:
        try:
            while self.running:
                await asyncio.sleep(2)
                await self._check_timeout()
        except asyncio.CancelledError:
            pass
    
    async def _check_timeout(self) -> None:
        now = time.time()
        timeout_threshold = now - g.config.send_timeout_retry
        
        async with self.lock:
            for sn, data_info in list(self.transfer_list.items()):
                if data_info["stat"] != "timeout":
                    if data_info["start_time"] + data_info["server_timeout"] < timeout_threshold:
                        data_info["stat"] = "timeout"
                        xlog.warn("transfer %d timeout", sn)
    
    async def create_conn(self, sock: Any, host: str, port: int, is_client: bool = True) -> Optional[int]:
        async with self.lock:
            conn_id = self.last_conn_id + 1
            self.last_conn_id = conn_id
            
            conn = AsyncConn(self, conn_id, sock, host, port, xlog)
            self.conn_list[conn_id] = conn
        
        await conn.start()
        return conn_id
    
    async def on_conn_data(self, conn_id: int, data: bytes) -> None:
        async with self.lock:
            if conn_id not in self.conn_list:
                return
            conn = self.conn_list[conn_id]
        
        await conn.send(data)
    
    async def remove_conn_async(self, conn_id: int) -> None:
        async with self.lock:
            if conn_id in self.conn_list:
                del self.conn_list[conn_id]
    
    async def close_all_connections(self) -> None:
        async with self.lock:
            for conn_id, conn in list(self.conn_list.items()):
                try:
                    await conn.stop_async("session_stop")
                except Exception:
                    pass
            self.conn_list.clear()
    
    async def login_session(self) -> bool:
        if not g.server_host:
            return False
        
        start_time = time.time()
        while time.time() - start_time < 30:
            try:
                magic = b"P"
                pack_type = 1
                head = struct.pack("<cBB8sIHIIHH", magic, g.protocol_version, pack_type,
                                  self.session_id,
                                  g.config.max_payload, g.config.send_delay, g.config.windows_size,
                                  int(g.config.windows_ack), g.config.resend_timeout, g.config.ack_delay)
                head += struct.pack("<H", len(g.config.login_account)) + utils.to_bytes(g.config.login_account)
                head += struct.pack("<H", len(g.config.login_password)) + utils.to_bytes(g.config.login_password)
                
                extra_info = self.get_login_extra_info()
                head += struct.pack("<H", len(extra_info)) + utils.to_bytes(extra_info)
                
                loop = asyncio.get_event_loop()
                content, status, response = await loop.run_in_executor(
                    None,
                    lambda: g.http_client.request(
                        method="POST",
                        host=g.server_host,
                        path="/data",
                        data=head,
                        timeout=g.config.network_timeout
                    )
                )
                
                if status != 200:
                    xlog.warn("login status: %d", status)
                    await asyncio.sleep(1)
                    continue
                
                if len(content) < 6:
                    xlog.warn("login response too short")
                    await asyncio.sleep(1)
                    continue
                
                return self._parse_login_response(content)
                
            except Exception as e:
                xlog.debug("login error: %r", e)
                await asyncio.sleep(1)
        
        return False
    
    def _parse_login_response(self, content: bytes) -> bool:
        try:
            pos = 0
            magic = content[pos:pos+1]
            pos += 1
            
            if magic != b"P":
                return False
            
            protocol_version = content[pos]
            pos += 1
            
            pack_type = content[pos]
            pos += 1
            
            if pack_type != 1:
                return False
            
            balance = struct.unpack("<I", content[pos:pos+4])[0]
            pos += 4
            
            g.balance = balance
            xlog.info("login success, balance: %d", balance)
            return True
        except Exception as e:
            xlog.debug("_parse_login_response error: %r", e)
            return False
    
    @staticmethod
    def get_login_extra_info() -> str:
        data = {
            "version": g.xxnet_version,
            "system": g.system,
            "device": g.client_uuid
        }
        return json.dumps(data)
    
    def status(self) -> str:
        out = f"AsyncProxySession:\n"
        out += f" running: {self.running}\n"
        out += f" session_id: {utils.to_str(self.session_id)}\n"
        out += f" connections: {len(self.conn_list)}\n"
        out += f" upload: {traffic_readable(self.traffic_upload)}\n"
        out += f" download: {traffic_readable(self.traffic_download)}\n"
        out += f" upload_speed: {traffic_readable(self.upload_speed)}/s\n"
        out += f" download_speed: {traffic_readable(self.download_speed)}/s\n"
        out += self.connection_pipe.status()
        return out
    
    async def check_upload(self) -> Optional[bool]:
        if len(self.send_buffer) > 0:
            self.wait_queue.notify()
            return True
        return None
    
    def is_idle(self) -> bool:
        return time.time() - self.last_send_time > 60


def login_process() -> None:
    if not g.session:
        return
    
    loop = asyncio.get_event_loop()
    if g.session.running:
        return
    
    async def do_login():
        await g.session.start()
    
    if loop.is_running():
        asyncio.run_coroutine_threadsafe(do_login(), loop)
    else:
        loop.run_until_complete(do_login())